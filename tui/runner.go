package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode"
	"unicode/utf8"
)

type Event struct {
	Kind, ID, Title, Status, Line string
	Code                          int
	Total, Completed, Attempt     int64
	Resource                      string
}

type Runner struct{ SupportDir, LogRoot string }

type Job struct {
	Events              <-chan Event
	LogPath             string
	events              chan Event
	done                chan struct{}
	cmd                 *exec.Cmd
	mu                  sync.Mutex
	cancelled, finished bool
	cancelDone          chan struct{}
	cancelError         error
	stopEvents          chan struct{}
}

func (j *Job) Done() <-chan struct{} { return j.done }
func (j *Job) Wait()                 { <-j.done }

func (j *Job) emit(event Event) {
	// Reserve one slot for done so cancellation can finish after the UI stops reading.
	if event.Kind == "done" {
		j.events <- event
		return
	}
	if len(j.events) >= cap(j.events)-1 && (event.Kind == "log" || event.Kind == "progress") {
		return
	}
	for len(j.events) >= cap(j.events)-1 {
		select {
		case <-j.stopEvents:
			return
		case <-time.After(5 * time.Millisecond):
		}
	}
	select {
	case j.events <- event:
	case <-j.stopEvents:
	}
}

func (j *Job) Cancel() {
	j.mu.Lock()
	if j.finished || j.cancelled {
		j.mu.Unlock()
		return
	}
	j.cancelled = true
	close(j.stopEvents)
	j.cancelDone = make(chan struct{})
	pid := j.cmd.Process.Pid
	signalProcessGroup(pid, syscall.SIGINT)
	j.mu.Unlock()
	go func() {
		defer close(j.cancelDone)
		for _, signal := range []syscall.Signal{syscall.SIGTERM, syscall.SIGKILL} {
			if waitProcessGroupExit(pid, 2*time.Second) {
				return
			}
			signalProcessGroup(pid, signal)
		}
		if !waitProcessGroupExit(pid, 2*time.Second) {
			j.mu.Lock()
			j.cancelError = errors.New("无法确认后台进程组退出，请检查完整日志后处理")
			j.mu.Unlock()
		}
	}()
}

func waitProcessGroupExit(pid int, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for processGroupAlive(pid) {
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(25 * time.Millisecond)
	}
	return true
}

// Command 用于需要交出真实终端的卸载流程；调用者自行连接 stdin/stdout。
func (r *Runner) Command(action Action) (*exec.Cmd, error) {
	if len(action.Args) == 0 {
		return nil, errors.New("操作没有执行脚本")
	}
	rel := action.Args[0]
	if filepath.IsAbs(rel) || filepath.Clean(rel) != rel || strings.HasPrefix(rel, "..") {
		return nil, errors.New("无效的执行脚本路径")
	}
	root, err := filepath.EvalSymlinks(r.SupportDir)
	if err != nil {
		return nil, err
	}
	root, err = filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	script, err := filepath.EvalSymlinks(filepath.Join(root, rel))
	if err != nil {
		return nil, err
	}
	within, err := filepath.Rel(root, script)
	if err != nil || within == ".." || strings.HasPrefix(within, ".."+string(os.PathSeparator)) {
		return nil, errors.New("执行脚本不能位于工具目录外")
	}
	info, err := os.Stat(script)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("执行目标不是普通文件")
	}
	cmd := exec.Command("/bin/bash", append([]string{script}, action.Args[1:]...)...)
	cmd.Dir = root
	cmd.Env = append(os.Environ(), "TEAM_TUI_EVENTS=1")
	return cmd, nil
}

func (r *Runner) Start(action Action) (*Job, error) {
	if action.Interactive {
		return nil, errors.New("交互确认操作必须使用终端接管模式")
	}
	cmd, err := r.Command(action)
	if err != nil {
		return nil, err
	}
	logRoot := r.LogRoot
	if logRoot == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		logRoot = filepath.Join(home, "Library", "Logs", "team-java-env", "tui")
	}
	if err = os.MkdirAll(logRoot, 0700); err != nil {
		return nil, err
	}
	file, err := os.CreateTemp(logRoot, time.Now().Format("20060102-150405")+"-*.log")
	if err != nil {
		return nil, err
	}
	events := make(chan Event, 257)
	job := &Job{Events: events, events: events, LogPath: file.Name(), cmd: cmd, done: make(chan struct{}), stopEvents: make(chan struct{})}
	output := &eventWriter{file: file, emit: job.emit}
	cmd.Stdout = output
	cmd.Stderr = output
	configureProcessGroup(cmd)
	if err = cmd.Start(); err != nil {
		file.Close()
		return nil, err
	}
	go func() {
		err := cmd.Wait()
		job.mu.Lock()
		cancelled := job.cancelled
		cancelDone := job.cancelDone
		if !cancelled {
			job.finished = true
		}
		job.mu.Unlock()
		// 父进程退出不代表后代结束；取消必须等整个进程组的升级清理完成。
		if cancelDone != nil {
			<-cancelDone
		}
		job.mu.Lock()
		job.finished = true
		cancelError := job.cancelError
		job.mu.Unlock()
		output.flush()
		if cancelError != nil {
			_, _ = fmt.Fprintln(file, cancelError.Error())
		}
		closeError := file.Close()
		code := 0
		if err != nil {
			code = 1
			var exit *exec.ExitError
			if errors.As(err, &exit) {
				code = exit.ExitCode()
				if code < 0 {
					code = 1
				}
			}
		}
		if closeError != nil && code == 0 {
			code = 1
		}
		if cancelled {
			code = 130
		}
		status := "succeeded"
		if code != 0 {
			status = "failed"
		}
		if cancelled {
			status = "cancelled"
		}
		detail := ""
		if cancelError != nil {
			code = 1
			status = "failed"
			detail = cancelError.Error()
		}
		job.emit(Event{Kind: "done", ID: action.ID, Status: status, Code: code, Line: detail})
		close(events)
		close(job.done)
	}()
	return job, nil
}

type eventWriter struct {
	mu   sync.Mutex
	file *os.File
	emit func(Event)
	line []byte
}

func (w *eventWriter) Write(data []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	n, err := w.file.Write(data)
	if err != nil {
		return n, err
	}
	for _, b := range data {
		if b == '\n' || b == '\r' {
			if len(w.line) > 0 {
				w.publish()
				w.line = w.line[:0]
			}
			continue
		}
		w.line = append(w.line, b)
		if len(w.line) >= 16384 {
			w.publish()
			w.line = w.line[:0]
		}
	}
	return n, nil
}

func (w *eventWriter) flush() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if len(w.line) > 0 {
		w.publish()
		w.line = nil
	}
}
func (w *eventWriter) publish() {
	line := string(w.line)
	parts := strings.Split(line, "\t")
	if len(parts) == 5 && parts[0] == "@@TEAM_TUI" {
		if parts[1] == "plan" && parts[2] == "components" {
			total, err := strconv.ParseInt(parts[3], 10, 64)
			if err == nil && total > 0 && total <= 6 {
				w.emit(Event{Kind: "plan", Total: total, Title: safeLogLine(parts[4])})
				return
			}
		}
		if parts[1] == "component" && parts[2] != "" {
			switch parts[3] {
			case "running", "succeeded", "failed", "skipped", "cancelled", "pending":
				w.emit(Event{Kind: "component", ID: safeLogLine(parts[2]), Status: parts[3], Title: safeLogLine(parts[4])})
				return
			}
		}
	}
	if len(parts) == 7 && parts[0] == "@@TEAM_TUI" && parts[1] == "progress" {
		attempt, e1 := strconv.ParseInt(parts[4], 10, 64)
		completed, e2 := strconv.ParseInt(parts[5], 10, 64)
		total, e3 := strconv.ParseInt(parts[6], 10, 64)
		if e1 == nil && e2 == nil && e3 == nil && attempt > 0 && completed >= 0 && total >= 0 && (total == 0 || completed <= total) {
			w.emit(Event{Kind: "progress", ID: safeLogLine(parts[2]), Resource: safeLogLine(parts[3]), Attempt: attempt, Completed: completed, Total: total})
			return
		}
	}
	fields := strings.SplitN(line, "\t", 5)
	if len(fields) == 5 && fields[0] == "@@TEAM_TUI" && fields[1] == "stage" && fields[2] != "" {
		switch fields[3] {
		case "running", "succeeded", "failed", "pending":
			w.emit(Event{Kind: "stage", ID: safeLogLine(fields[2]), Status: fields[3], Title: safeLogLine(fields[4])})
			return
		}
	}
	line = safeLogLine(line)
	if line != "" {
		w.emit(Event{Kind: "log", Line: line})
	}
}

// 日志属于子进程数据，不允许其中的终端控制序列改变 TUI 或剪贴板。
func safeLogLine(text string) string {
	var out strings.Builder
	for i := 0; i < len(text); {
		if text[i] == 27 {
			i++
			if i >= len(text) {
				break
			}
			switch text[i] {
			case '[':
				i++
				for i < len(text) {
					b := text[i]
					i++
					if b >= 0x40 && b <= 0x7e {
						break
					}
				}
			case ']':
				i++
				for i < len(text) {
					if text[i] == 7 {
						i++
						break
					}
					if text[i] == 27 && i+1 < len(text) && text[i+1] == '\\' {
						i += 2
						break
					}
					i++
				}
			default:
				i++
			}
			continue
		}
		r, size := utf8.DecodeRuneInString(text[i:])
		i += size
		if r == '\t' {
			r = ' '
		}
		if unicode.IsControl(r) {
			continue
		}
		if out.Len()+utf8.RuneLen(r) > 16380 {
			out.WriteString("…")
			break
		}
		out.WriteRune(r)
	}
	return out.String()
}

func (e Event) String() string { return fmt.Sprintf("%s %s %s", e.Kind, e.ID, e.Status) }
