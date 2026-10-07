package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode"

	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

type screen int

const (
	screenMenu screen = iota
	screenConfirm
	screenRunning
	screenResult
)

type jobStartedMsg struct {
	job *Job
	err error
}
type jobEventMsg struct{ Event }
type interactiveDoneMsg struct{ err error }

// The lifecycle survives model copies and handles terminal loss during Start.
// Close cancels and reaps any process, even when Start completes after the UI exits.
type jobLifecycle struct {
	ctx         context.Context
	interactive atomic.Bool
	mu          sync.Mutex
	pending     sync.WaitGroup
	job         *Job
	closing     bool
}

func (l *jobLifecycle) start(runner *Runner, action Action) (*Job, error) {
	l.mu.Lock()
	if l.closing {
		l.mu.Unlock()
		return nil, errors.New("界面已关闭，任务未启动")
	}
	l.pending.Add(1)
	l.mu.Unlock()
	defer l.pending.Done()
	job, err := runner.Start(action)
	if job != nil {
		l.attach(job)
	}
	return job, err
}
func (l *jobLifecycle) attach(job *Job) {
	l.mu.Lock()
	l.job = job
	closing := l.closing
	l.mu.Unlock()
	if closing {
		job.Cancel()
		job.Wait()
	}
}
func (l *jobLifecycle) close() {
	l.mu.Lock()
	l.closing = true
	job := l.job
	l.mu.Unlock()
	if job != nil {
		job.Cancel()
		job.Wait()
	}
	l.pending.Wait()
}

type model struct {
	runner          *Runner
	lifecycle       *jobLifecycle
	page            string
	cursor          int
	screen          screen
	action          Action
	job             *Job
	logs            []string
	stages          []Event
	logPath         string
	scanSummary     string
	resultStatus    string
	exitCode        int
	cancelRequested bool
	quitAfterDone   bool
	width, height   int
	spinner         spinner.Model
	viewport        viewport.Model
}

var (
	accent   = lipgloss.NewStyle().Foreground(lipgloss.Color("#75D7C8"))
	muted    = lipgloss.NewStyle().Foreground(lipgloss.Color("#8996A8"))
	heading  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#75D7C8"))
	selected = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#75D7C8"))
	warning  = lipgloss.NewStyle().Foreground(lipgloss.Color("#F1C675"))
	failure  = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF8D96"))
)

func newModel(runner *Runner, page string) model {
	if page == "" {
		page = "home"
	}
	v := viewport.New(viewport.WithWidth(74), viewport.WithHeight(12))
	v.SoftWrap = true
	m := model{
		runner: runner, lifecycle: &jobLifecycle{ctx: context.Background()}, page: page, screen: screenRunning,
		action:      Action{ID: "scan", Title: "检查当前环境", Description: "只读检查，不安装或修改任何工具。", Args: []string{"scripts/check-env.sh"}},
		scanSummary: "正在检查当前环境", width: 80, height: 24,
		spinner: spinner.New(spinner.WithSpinner(spinner.Dot), spinner.WithStyle(accent)), viewport: v,
	}
	if page == "cleanup" {
		m.screen = screenMenu
		m.action = Action{}
		m.scanSummary = "请先预览卸载清单，再选择安全卸载"
	}
	return m
}

func (m model) Init() tea.Cmd {
	if m.screen != screenRunning || m.action.ID != "scan" {
		return nil
	}
	return m.startCommand(m.action)
}
func (m model) startCommand(action Action) tea.Cmd {
	return func() tea.Msg {
		job, err := m.lifecycle.start(m.runner, action)
		return jobStartedMsg{job: job, err: err}
	}
}
func waitJob(job *Job) tea.Cmd {
	if job == nil {
		return nil
	}
	return func() tea.Msg {
		event, ok := <-job.Events
		if !ok {
			return jobEventMsg{Event{Kind: "done", Status: "failed", Code: 1, Line: "任务事件流意外结束"}}
		}
		return jobEventMsg{event}
	}
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = max(1, msg.Width), max(1, msg.Height)
		m.resizeViewport()
		return m, nil
	case jobStartedMsg:
		if msg.err != nil {
			m.addLog(msg.err.Error())
			return m.finish("failed", 1)
		}
		m.job = msg.job
		m.logPath = msg.job.LogPath
		if m.cancelRequested {
			m.job.Cancel()
		}
		return m, tea.Batch(waitJob(m.job), m.spinner.Tick)
	case jobEventMsg:
		switch msg.Kind {
		case "log":
			m.addLog(msg.Line)
		case "stage":
			replaced := false
			for i := range m.stages {
				if m.stages[i].ID == msg.ID {
					m.stages[i] = msg.Event
					replaced = true
					break
				}
			}
			if !replaced {
				m.stages = append(m.stages, msg.Event)
				if len(m.stages) > 128 {
					m.stages = m.stages[len(m.stages)-128:]
				}
			}
			m.resizeViewport()
		case "done":
			if msg.Line != "" {
				m.addLog(msg.Line)
			}
			return m.finish(msg.Status, msg.Code)
		}
		return m, waitJob(m.job)
	case interactiveDoneMsg:
		code := 0
		status := "succeeded"
		if msg.err != nil {
			status = "failed"
			code = 1
			var exitErr *exec.ExitError
			if errors.As(msg.err, &exitErr) {
				code = exitErr.ExitCode()
				if code < 0 {
					code = 130
				}
			}
			if code == 130 {
				status = "cancelled"
			}
			m.addLog(msg.err.Error())
		} else {
			m.addLog("安全卸载流程已返回。具体执行结果请查看卸载器输出；未确认的操作不会执行。")
		}
		return m.finish(status, code)
	case spinner.TickMsg:
		if m.screen == screenRunning {
			var cmd tea.Cmd
			m.spinner, cmd = m.spinner.Update(msg)
			return m, cmd
		}
		return m, nil
	case tea.KeyPressMsg:
		return m.handleKey(msg)
	}
	if m.screen == screenRunning || m.screen == screenResult {
		var cmd tea.Cmd
		m.viewport, cmd = m.viewport.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m model) handleKey(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	if (m.width < 52 || m.height < 16) && (key == "enter" || key == "y") {
		return m, nil
	}
	if m.screen == screenRunning {
		if key == "ctrl+c" || key == "esc" || key == "q" {
			m.cancelRequested = true
			m.quitAfterDone = m.quitAfterDone || key == "ctrl+c" || key == "q"
			if m.job != nil {
				m.job.Cancel()
			}
			return m, nil
		}
		if key == "enter" {
			return m, nil
		}
		var cmd tea.Cmd
		m.viewport, cmd = m.viewport.Update(msg)
		return m, cmd
	}
	if key == "q" || key == "ctrl+c" {
		return m, tea.Quit
	}
	if m.screen == screenResult {
		if key == "enter" || key == "esc" {
			m.screen = screenMenu
			return m, nil
		}
		var cmd tea.Cmd
		m.viewport, cmd = m.viewport.Update(msg)
		return m, cmd
	}
	if m.screen == screenConfirm {
		if key == "esc" || key == "n" {
			m.screen = screenMenu
			return m, nil
		}
		if key == "enter" || key == "y" {
			m.screen = screenRunning
			m.logs = nil
			m.stages = nil
			m.logPath = ""
			m.resultStatus = ""
			m.cancelRequested = false
			m.quitAfterDone = false
			m.viewport.SetContent("")
			m.resizeViewport()
			if m.action.Interactive {
				cmd, err := m.interactiveCommand()
				if err != nil {
					m.addLog(err.Error())
					return m.finish("failed", 1)
				}
				m.lifecycle.interactive.Store(true)
				return m, tea.ExecProcess(cmd, func(err error) tea.Msg {
					m.lifecycle.interactive.Store(false)
					return interactiveDoneMsg{err: err}
				})
			}
			return m, m.startCommand(m.action)
		}
		return m, nil
	}
	actions := ActionsFor(m.page)
	switch key {
	case "up", "k":
		if len(actions) > 0 {
			m.cursor = (m.cursor - 1 + len(actions)) % len(actions)
		}
	case "down", "j":
		if len(actions) > 0 {
			m.cursor = (m.cursor + 1) % len(actions)
		}
	case "home":
		m.cursor = 0
	case "end":
		m.cursor = max(0, len(actions)-1)
	case "esc", "backspace":
		if m.page != "home" {
			m.page = "home"
			m.cursor = 0
		} else {
			return m, tea.Quit
		}
	case "enter":
		if len(actions) == 0 {
			return m, nil
		}
		action := actions[m.cursor]
		if strings.HasPrefix(action.ID, "page:") {
			m.page = strings.TrimPrefix(action.ID, "page:")
			m.cursor = 0
			return m, nil
		}
		if action.ID == "back" {
			m.page = "home"
			m.cursor = 0
			return m, nil
		}
		m.action = action
		m.screen = screenConfirm
	}
	return m, nil
}

func (m model) interactiveCommand() (*exec.Cmd, error) {
	cmd, err := m.runner.Command(m.action)
	if err != nil {
		return nil, err
	}
	// ExecProcess connects the real terminal. Structured events are only for captured jobs.
	env := make([]string, 0, len(cmd.Env))
	for _, entry := range cmd.Env {
		if !strings.HasPrefix(entry, "TEAM_TUI_EVENTS=") {
			env = append(env, entry)
		}
	}
	interactive := exec.CommandContext(m.lifecycle.ctx, cmd.Path, cmd.Args[1:]...)
	interactive.Dir = cmd.Dir
	interactive.Env = env
	// Give the existing uninstaller (including a PyInstaller bootloader) the
	// chance to forward interruption and clean up its child before a hard stop.
	interactive.Cancel = func() error { return interactive.Process.Signal(os.Interrupt) }
	interactive.WaitDelay = 4 * time.Second
	return interactive, nil
}

func (m model) finish(status string, code int) (tea.Model, tea.Cmd) {
	m.job = nil
	m.resultStatus = status
	if m.cancelRequested && status == "" {
		m.resultStatus = "cancelled"
		if code == 0 {
			code = 130
		}
	}
	if m.resultStatus == "" {
		if code == 0 {
			m.resultStatus = "succeeded"
		} else {
			m.resultStatus = "failed"
		}
	}
	for i := range m.stages {
		if m.stages[i].Status != "running" {
			continue
		}
		switch m.resultStatus {
		case "cancelled", "failed":
			m.stages[i].Status = m.resultStatus
		default:
			// A process exit alone does not verify that a reported stage completed.
			m.stages[i].Status = "pending"
		}
	}
	if m.action.ID == "scan" {
		switch {
		case m.resultStatus == "cancelled":
			m.scanSummary = "环境检查已取消，可继续选择操作"
		case code == 0:
			m.scanSummary = "环境检查完成"
		default:
			m.scanSummary = "环境待配置，可按需选择安装"
		}
		m.screen = screenMenu
		if m.quitAfterDone {
			if m.resultStatus == "cancelled" {
				m.exitCode = code
			}
			return m, tea.Quit
		}
		return m, nil
	}
	m.exitCode = code
	m.screen = screenResult
	if m.quitAfterDone {
		return m, tea.Quit
	}
	return m, nil
}

func (m *model) addLog(line string) {
	// Scripts may emit color/control sequences; only their text belongs in the viewport.
	line = ansi.Strip(line)
	line = strings.Map(func(r rune) rune {
		if r == '\t' {
			return ' '
		}
		if unicode.IsControl(r) {
			return -1
		}
		return r
	}, line)
	runes := []rune(line)
	if len(runes) > 4096 {
		line = string(runes[:4095]) + "…"
	}
	atBottom := m.viewport.AtBottom()
	m.logs = append(m.logs, line)
	if len(m.logs) > 1000 {
		m.logs = m.logs[len(m.logs)-1000:]
	}
	m.viewport.SetContent(strings.Join(m.logs, "\n"))
	if atBottom {
		m.viewport.GotoBottom()
	}
}
func (m *model) resizeViewport() {
	m.viewport.SetWidth(max(1, m.width-4))
	m.viewport.SetHeight(max(1, m.height-14-min(3, len(m.stages))))
}
func clipped(s string, width int) string { return ansi.Truncate(s, max(1, width), "…") }
func pageTitle(page string) string {
	switch page {
	case "gradle":
		return "Gradle 版本"
	case "frontend":
		return "前端开发环境"
	case "cleanup":
		return "安全卸载"
	default:
		return "选择要配置的环境"
	}
}
func (m model) View() tea.View {
	if m.width < 52 || m.height < 16 {
		content := "终端较小\n请扩大到至少 52 列 × 16 行\n当前 " + fmt.Sprintf("%d × %d", m.width, m.height) + "\n"
		if m.screen == screenRunning {
			content += "任务仍在运行；Esc 取消，Ctrl+C 取消后退出"
		} else {
			content += "Esc 返回 · q 退出"
		}
		v := tea.NewView(lipgloss.NewStyle().MaxWidth(m.width).MaxHeight(m.height).Render(content))
		v.AltScreen = true
		return v
	}
	w := max(1, m.width-4)
	bodyHeight := max(1, m.height-7)
	header := heading.Render("TEAM DEV ENV  /  团队开发环境") + "\n" + muted.Render("Java · 前端工具 · 安全卸载")
	var body, footer string
	switch m.screen {
	case screenMenu:
		actions := ActionsFor(m.page)
		lines := []string{heading.Render(pageTitle(m.page)), muted.Render(clipped(m.scanSummary, w)), ""}
		visible := max(1, bodyHeight-7)
		start := max(0, m.cursor-visible+1)
		end := min(len(actions), start+visible)
		for i := start; i < end; i++ {
			prefix := "  "
			style := lipgloss.NewStyle()
			if i == m.cursor {
				prefix = "› "
				style = selected
			}
			lines = append(lines, style.Render(clipped(prefix+actions[i].Title, w)))
		}
		if end-start < len(actions) {
			lines = append(lines, muted.Render(fmt.Sprintf("  %d / %d · ↑↓ 浏览全部操作", m.cursor+1, len(actions))))
		}
		if len(actions) > 0 {
			lines = append(lines, "", muted.Render(clipped(actions[m.cursor].Description, w)))
		}
		body = strings.Join(lines, "\n")
		footer = "↑↓ 选择 · Enter 继续 · Esc 返回 · q 退出"
	case screenConfirm:
		lines := []string{heading.Render("确认操作"), "", m.action.Title, "", lipgloss.NewStyle().Width(w).Render(m.action.Description), ""}
		if m.action.Interactive {
			lines = append(lines, warning.Render("将进入安全卸载流程。"), "后续仍需选择范围并输入 DELETE 确认。")
		} else if containsArg(m.action.Args, "--dry-run") {
			lines = append(lines, "仅生成卸载预览，不删除任何文件。")
		} else {
			lines = append(lines, "确认后开始执行，期间可按 Esc 取消。")
		}
		body = strings.Join(lines, "\n")
		footer = "Enter 确认 · Esc 返回 · q 退出"
	case screenRunning, screenResult:
		status := m.spinner.View() + "正在执行"
		if m.action.ID == "scan" {
			status = m.spinner.View() + "只读检查"
		}
		if m.cancelRequested {
			status = warning.Render(m.spinner.View() + "正在取消，等待子进程退出…")
		}
		if m.screen == screenResult {
			switch m.resultStatus {
			case "cancelled":
				status = warning.Render("已取消")
			case "succeeded":
				status = accent.Render("执行完成")
			default:
				status = failure.Render(fmt.Sprintf("执行失败 · 退出码 %d", m.exitCode))
			}
		}
		lines := []string{heading.Render(clipped(m.action.Title, w)), status}
		stages := m.stages
		if len(stages) > 3 {
			stages = stages[len(stages)-3:]
		}
		for _, stage := range stages {
			marker := "○"
			switch stage.Status {
			case "running":
				marker = "◌"
			case "succeeded":
				marker = "✓"
			case "failed":
				marker = "✕"
			case "cancelled":
				marker = "–"
			}
			lines = append(lines, clipped(marker+" "+stage.Title+"  "+stageLabel(stage.Status), w))
		}
		lines = append(lines, "", muted.Render("执行日志 · ↑↓ / PgUp / PgDn 滚动"), m.viewport.View())
		if m.logPath != "" {
			lines = append(lines, muted.Render(clipped("完整日志："+m.logPath, w)))
		}
		body = strings.Join(lines, "\n")
		footer = "Esc 取消任务 · Ctrl+C 取消后退出 · End 跟随日志"
		if m.screen == screenResult {
			footer = "Enter / Esc 返回菜单 · ↑↓ 滚动日志 · q 退出"
		}
	}
	body = lipgloss.NewStyle().Width(w).Height(bodyHeight).MaxHeight(bodyHeight).Render(body)
	content := header + "\n\n" + body + "\n\n" + muted.Render(clipped(footer, w))
	content = lipgloss.NewStyle().Padding(1, 2).MaxWidth(m.width).MaxHeight(m.height).Render(content)
	v := tea.NewView(content)
	v.AltScreen = true
	return v
}
func stageLabel(status string) string {
	switch status {
	case "running":
		return "进行中"
	case "succeeded":
		return "已完成"
	case "failed":
		return "失败"
	case "pending":
		return "待配置"
	case "cancelled":
		return "已取消"
	default:
		return ""
	}
}
func containsArg(args []string, want string) bool {
	for _, arg := range args {
		if arg == want {
			return true
		}
	}
	return false
}
