package main

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

func fixtureRunner(t *testing.T, body string) (*Runner, Action) {
	t.Helper()
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "scripts"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "scripts", "task.sh"), []byte("#!/bin/bash\n"+body), 0700); err != nil {
		t.Fatal(err)
	}
	return &Runner{SupportDir: root, LogRoot: filepath.Join(root, "logs")}, Action{ID: "test", Title: "测试", Args: []string{"scripts/task.sh"}}
}

func collectJob(t *testing.T, job *Job) []Event {
	t.Helper()
	var events []Event
	timer := time.NewTimer(8 * time.Second)
	defer timer.Stop()
	for {
		select {
		case event, ok := <-job.Events:
			if !ok {
				return events
			}
			events = append(events, event)
		case <-timer.C:
			job.Cancel()
			t.Fatal("job did not finish")
			return nil
		}
	}
}

func TestRunnerStreamsStageAndPreservesExit(t *testing.T) {
	runner, action := fixtureRunner(t, "printf '@@TEAM_TUI\\tstage\\tstep-1\\trunning\\t下载\\n'; echo output; echo problem >&2; exit 23\n")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	events := collectJob(t, job)
	if events[len(events)-1].Kind != "done" || events[len(events)-1].Code != 23 {
		t.Fatalf("events: %#v", events)
	}
	found := false
	for _, event := range events {
		if event.Kind == "stage" && event.ID == "step-1" && event.Status == "running" {
			found = true
		}
	}
	if !found {
		t.Fatal("missing structured stage")
	}
	log, err := os.ReadFile(job.LogPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(log), "output") || !strings.Contains(string(log), "problem") {
		t.Fatalf("incomplete log: %s", log)
	}
}

func TestRunnerCancelStopsProcessGroupAndCompletes(t *testing.T) {
	runner, action := fixtureRunner(t, "trap 'echo stopped; exit 130' INT TERM\necho ready\nsleep 30 &\nwait\n")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	select {
	case <-job.Events:
	case <-time.After(3 * time.Second):
		t.Fatal("not started")
	}
	job.Cancel()
	events := collectJob(t, job)
	if events[len(events)-1].Code != 130 {
		t.Fatalf("cancel exit: %#v", events)
	}
	job.Cancel()
	job.Wait()
}

func TestRunnerCancelReapsRedirectedDescendantAfterLeaderExits(t *testing.T) {
	runner, action := fixtureRunner(t, "trap 'exit 130' INT TERM\n(trap '' INT TERM; exec /bin/sleep 30) </dev/null >/dev/null 2>&1 &\necho $! > child.pid\necho ready\nwait\n")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	defer syscall.Kill(-job.cmd.Process.Pid, syscall.SIGKILL)
	select {
	case <-job.Events:
	case <-time.After(3 * time.Second):
		t.Fatal("not started")
	}
	data, err := os.ReadFile(filepath.Join(runner.SupportDir, "child.pid"))
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil {
		t.Fatal(err)
	}
	job.Cancel()
	events := collectJob(t, job)
	if events[len(events)-1].Code != 130 {
		t.Fatalf("cancel exit: %#v", events)
	}
	if err := syscall.Kill(pid, 0); err == nil {
		t.Fatal("redirected descendant survived completed cancellation")
	}
}

func TestRunnerRejectsEscapeAndInteractiveTasks(t *testing.T) {
	runner, action := fixtureRunner(t, "exit 0\n")
	for _, args := range [][]string{{"../outside.sh"}, {"/bin/bash"}, {"scripts/../task.sh"}, nil} {
		action.Args = args
		if _, err := runner.Start(action); err == nil {
			t.Fatalf("accepted unsafe arguments: %v", args)
		}
	}
	action.Args = []string{"scripts/task.sh"}
	action.Interactive = true
	if _, err := runner.Start(action); err == nil {
		t.Fatal("interactive task accepted by background runner")
	}
}

func TestRunnerDoesNotInterpretShellArguments(t *testing.T) {
	runner, action := fixtureRunner(t, "printf '%s\\n' \"$1\"\n")
	action.Args = append(action.Args, "$(touch unsafe); echo test")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	collectJob(t, job)
	data, _ := os.ReadFile(job.LogPath)
	if !strings.Contains(string(data), action.Args[1]) {
		t.Fatalf("argument changed: %s", data)
	}
	if _, err := os.Stat(filepath.Join(runner.SupportDir, "unsafe")); !os.IsNotExist(err) {
		t.Fatal("shell injection")
	}
}

func TestRunnerOutputIsBoundedAndTerminalControlsAreRemoved(t *testing.T) {
	runner, action := fixtureRunner(t, "printf '\\033]52;c;attack\\007'; printf '\\033[31mred\\033[0m\\n'; head -c 200000 /dev/zero | tr '\\0' x; echo; exit 0\n")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	for _, event := range collectJob(t, job) {
		if strings.ContainsRune(event.Line, '\x1b') || len(event.Line) > 16384 {
			t.Fatal("unsafe or unbounded UI log")
		}
	}
	data, _ := os.ReadFile(job.LogPath)
	if len(data) < 200000 {
		t.Fatal("full disk log was truncated")
	}
}

func TestActionsKeepJavaAndFrontendScopesIndependent(t *testing.T) {
	for _, action := range ActionsFor("home") {
		if action.ID == "java-all" && strings.Contains(strings.Join(action.Args, " "), "frontend") {
			t.Fatal("Java action includes frontend")
		}
	}
	for _, action := range ActionsFor("cleanup") {
		if strings.Contains(strings.Join(action.Args, " "), "--yes") {
			t.Fatal("cleanup bypasses confirmation")
		}
	}
}
