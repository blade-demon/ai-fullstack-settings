package main

import (
	"bytes"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func uiKey(code rune) tea.KeyPressMsg { return tea.KeyPressMsg{Code: code} }
func uiUpdate(m model, msg tea.Msg) (model, tea.Cmd) {
	next, cmd := m.Update(msg)
	return next.(model), cmd
}
func readyUI(t *testing.T, page string) model {
	t.Helper()
	m := newModel(&Runner{SupportDir: t.TempDir(), LogRoot: t.TempDir()}, page)
	if m.screen == screenRunning {
		m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "done", Code: 1, Status: "failed"}})
	}
	m, _ = uiUpdate(m, tea.WindowSizeMsg{Width: 90, Height: 30})
	return m
}
func fixtureScript(t *testing.T, dir, name, body string) {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("#!/bin/bash\n"+body+"\n"), 0700); err != nil {
		t.Fatal(err)
	}
}
func receiveUIEvent(t *testing.T, job *Job) Event {
	t.Helper()
	select {
	case e, ok := <-job.Events:
		if !ok {
			t.Fatal("job closed before done")
		}
		return e
	case <-time.After(8 * time.Second):
		job.Cancel()
		t.Fatal("job did not finish")
		return Event{}
	}
}

// Removing the confirmation gate would start a script on the first Enter.
func TestUIRequiresConfirmationBeforeStarting(t *testing.T) {
	m := readyUI(t, "home")
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if m.screen != screenConfirm || cmd != nil || m.job != nil {
		t.Fatal("selection must only open confirmation")
	}
	m, cmd = uiUpdate(m, uiKey(tea.KeyEscape))
	if m.screen != screenMenu || cmd != nil {
		t.Fatal("escape must return without starting")
	}
}

// Missing tools at startup must never become an install or final exit failure.
func TestUIInitOnlyRunsReadOnlyScanAndMissingToolsAreNotFatal(t *testing.T) {
	support := t.TempDir()
	fixtureScript(t, support, "scripts/check-env.sh", "printf '缺少待配置工具\\n'; exit 1")
	m := newModel(&Runner{SupportDir: support, LogRoot: t.TempDir()}, "frontend")
	msg := m.Init()()
	started, ok := msg.(jobStartedMsg)
	if !ok || started.err != nil || started.job == nil {
		t.Fatalf("start scan: %#v", msg)
	}
	m, _ = uiUpdate(m, msg)
	for m.screen == screenRunning {
		m, _ = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
	}
	if m.screen != screenMenu || m.page != "frontend" || m.exitCode != 0 || !strings.Contains(m.scanSummary, "待配置") {
		t.Fatal("missing tools should leave frontend menu usable without failure status")
	}
}

// A second Enter while starting must not submit another process.
func TestUIConfirmedActionRunsOnceAndKeepsExitStatus(t *testing.T) {
	m := readyUI(t, "home")
	fixtureScript(t, m.runner.SupportDir, "fixture.sh", "printf '真实日志\\n'; exit 7")
	m.action = Action{ID: "fixture", Title: "测试任务", Args: []string{"fixture.sh"}}
	m.screen = screenConfirm
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if m.screen != screenRunning || cmd == nil {
		t.Fatal("confirm should start")
	}
	m, duplicate := uiUpdate(m, uiKey(tea.KeyEnter))
	if duplicate != nil {
		t.Fatal("running job must ignore repeated Enter")
	}
	started := cmd().(jobStartedMsg)
	m, _ = uiUpdate(m, started)
	for m.screen == screenRunning {
		m, _ = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
	}
	if m.exitCode != 7 || m.screen != screenResult || !strings.Contains(m.View().Content, "失败") {
		t.Fatal("task failure must remain visible with its exit code")
	}
	m, _ = uiUpdate(m, uiKey(tea.KeyEnter))
	if m.screen != screenMenu || m.exitCode != 7 {
		t.Fatal("return must preserve the latest task's exit code")
	}
}

// Ctrl-C must wait for a starting process to be attached, cancelled, and reaped.
func TestUICancelWhileStartingWaitsForDone(t *testing.T) {
	m := readyUI(t, "home")
	m.action = Action{ID: "fixture", Title: "测试任务", Args: []string{"fixture.sh"}}
	m.screen = screenConfirm
	m, _ = uiUpdate(m, uiKey(tea.KeyEnter))
	m, cmd := uiUpdate(m, tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl})
	if m.screen != screenRunning || !m.cancelRequested || !m.quitAfterDone || cmd != nil {
		t.Fatal("must wait while process is starting")
	}
	m, cmd = uiUpdate(m, jobEventMsg{Event{Kind: "done", Status: "cancelled", Code: 130}})
	if m.exitCode != 130 || cmd == nil {
		t.Fatal("cancelled exit should quit only after done")
	}
	if _, ok := cmd().(tea.QuitMsg); !ok {
		t.Fatal("expected deferred quit")
	}
}

func TestUIEscCancelsButLeavesResultAvailable(t *testing.T) {
	m := readyUI(t, "home")
	m.screen, m.action = screenRunning, Action{ID: "fixture", Title: "测试任务"}
	m, _ = uiUpdate(m, uiKey(tea.KeyEscape))
	if !m.cancelRequested || m.quitAfterDone {
		t.Fatal("escape should cancel without quitting")
	}
	m, cmd := uiUpdate(m, jobEventMsg{Event{Kind: "done", Status: "cancelled", Code: 130}})
	if m.screen != screenResult || cmd != nil || !strings.Contains(m.View().Content, "取消") {
		t.Fatal("cancel should show a result")
	}
}

// Window changes must fit Chinese text and keep viewport dimensions valid.
func TestUIResizesAndWarnsInSmallTerminals(t *testing.T) {
	for _, size := range [][2]int{{90, 30}, {60, 18}, {30, 9}, {3, 2}} {
		m := readyUI(t, "home")
		m, _ = uiUpdate(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		v := m.View().Content
		if lipgloss.Width(v) > size[0] || lipgloss.Height(v) > size[1] {
			t.Fatalf("view exceeds %dx%d: %dx%d", size[0], size[1], lipgloss.Width(v), lipgloss.Height(v))
		}
		if size[0] == 30 && !strings.Contains(v, "终端较小") {
			t.Fatal("small terminal needs a readable warning")
		}
	}
}

func TestUIMenuOpensPagesAndEscapeReturns(t *testing.T) {
	for _, page := range []string{"gradle", "frontend", "cleanup"} {
		m := readyUI(t, "home")
		found := false
		for i, a := range ActionsFor("home") {
			if a.ID == "page:"+page {
				m.cursor = i
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("missing %s submenu", page)
		}
		m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
		if m.page != page || m.screen != screenMenu || cmd != nil {
			t.Fatalf("must open %s without executing", page)
		}
		m, _ = uiUpdate(m, uiKey(tea.KeyEscape))
		if m.page != "home" {
			t.Fatal("escape should return home")
		}
	}
}

func TestUILogsAreBoundedAndStagesUseReportedStatus(t *testing.T) {
	m := readyUI(t, "home")
	m.screen, m.action = screenRunning, Action{ID: "fixture", Title: "任务"}
	for i := 0; i < 1200; i++ {
		m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "log", Line: "示例输出"}})
	}
	m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "log", Line: strings.Repeat("长", 5000)}})
	if len(m.logs) > 1000 || len([]rune(m.logs[len(m.logs)-1])) > 4096 {
		t.Fatal("in-memory logs must be bounded")
	}
	m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "stage", ID: "download", Title: "下载 JDK", Status: "running"}})
	view := m.View().Content
	if !strings.Contains(view, "下载 JDK") || strings.Contains(view, "100%") {
		t.Fatal("view must show actual stage without invented percentage")
	}
}

func TestCLIRejectsNonTTYBeforeExecutingScripts(t *testing.T) {
	var out, errout bytes.Buffer
	in, err := os.Open(os.DevNull)
	if err != nil {
		t.Fatal(err)
	}
	defer in.Close()
	code := runCLI([]string{"--support-dir", t.TempDir()}, in, &out, &errout)
	if code == 0 || !strings.Contains(errout.String(), "--plain") {
		t.Fatalf("non-TTY should explain plain mode: %d %s", code, errout.String())
	}
	out.Reset()
	errout.Reset()
	if code := runCLI([]string{"--help"}, in, &out, &errout); code != 0 || !strings.Contains(out.String(), "--page") {
		t.Fatal("help must work without TTY")
	}
}

func TestUIInteractiveCommandRetainsSafetyArguments(t *testing.T) {
	m := readyUI(t, "cleanup")
	fixtureScript(t, m.runner.SupportDir, "scripts/run-cleanup.sh", "exit 0")
	for _, a := range ActionsFor("cleanup") {
		if a.Interactive {
			m.action = a
		}
	}
	cmd, err := m.interactiveCommand()
	if err != nil {
		t.Fatal(err)
	}
	if len(cmd.Args) != 2 || cmd.Args[0] != "/bin/bash" || !strings.HasSuffix(cmd.Args[1], "/scripts/run-cleanup.sh") {
		t.Fatalf("interactive cleanup must retain its own prompts: %v", cmd.Args)
	}
	if cmd.Stdin != nil || cmd.Stdout != nil || cmd.SysProcAttr != nil {
		t.Fatal("ExecProcess must own the terminal for interactive cleanup")
	}
	for _, entry := range cmd.Env {
		if entry == "TEAM_TUI_EVENTS=1" {
			t.Fatal("interactive terminal must not print TUI protocol events")
		}
	}
	m.action.Args = []string{"../outside.sh"}
	if _, err := m.interactiveCommand(); err == nil {
		t.Fatal("interactive script may not escape support directory")
	}
}

func TestUISmallTerminalDoesNotStartHiddenConfirmation(t *testing.T) {
	m := readyUI(t, "home")
	m, _ = uiUpdate(m, uiKey(tea.KeyEnter))
	m, _ = uiUpdate(m, tea.WindowSizeMsg{Width: 30, Height: 9})
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if m.screen != screenConfirm || cmd != nil {
		t.Fatal("a hidden confirmation must not be accepted in a small terminal")
	}
}

func TestUICancellationBeforeStartedMessageCancelsRealJob(t *testing.T) {
	m := readyUI(t, "home")
	fixtureScript(t, m.runner.SupportDir, "fixture.sh", "trap 'exit 130' INT TERM; while :; do sleep 0.1; done")
	m.action = Action{ID: "fixture", Title: "测试任务", Args: []string{"fixture.sh"}}
	m.screen = screenConfirm
	m, start := uiUpdate(m, uiKey(tea.KeyEnter))
	m, _ = uiUpdate(m, tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl})
	started := start().(jobStartedMsg)
	if started.err != nil {
		t.Fatal(started.err)
	}
	m, _ = uiUpdate(m, started)
	var cmd tea.Cmd
	for m.screen == screenRunning {
		m, cmd = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
	}
	started.job.Wait()
	if m.exitCode != 130 || cmd == nil {
		t.Fatal("cancel during start must cancel the real process before quitting")
	}
}

func TestUILifecyclePreventsLateStartAfterTerminalCloses(t *testing.T) {
	m := readyUI(t, "home")
	marker := filepath.Join(m.runner.SupportDir, "started")
	fixtureScript(t, m.runner.SupportDir, "fixture.sh", "touch started")
	m.lifecycle.close()
	msg := m.startCommand(Action{ID: "fixture", Args: []string{"fixture.sh"}})().(jobStartedMsg)
	if msg.err == nil || msg.job != nil {
		t.Fatal("closing terminal must prevent a late command from starting")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("late start performed a side effect")
	}
}

// Opening cleanup must never execute installed SDKs through the general scanner.
func TestUICleanupStartsAtMenuWithoutAutomaticScan(t *testing.T) {
	support := t.TempDir()
	fixtureScript(t, support, "scripts/check-env.sh", "touch scanned")
	fixtureScript(t, support, "scripts/run-cleanup.sh", "printf '%s' \"$*\" > preview-args")
	m := newModel(&Runner{SupportDir: support, LogRoot: t.TempDir()}, "cleanup")
	if m.Init() != nil || m.job != nil || m.screen != screenMenu {
		t.Fatal("cleanup must open the menu without scheduling an environment scan")
	}
	if !strings.Contains(m.scanSummary, "预览") {
		t.Fatal("cleanup should guide the user to preview first")
	}
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if m.screen != screenConfirm || cmd != nil {
		t.Fatal("preview should still require an explicit selection and confirmation")
	}
	m, cmd = uiUpdate(m, uiKey(tea.KeyEnter))
	started := cmd().(jobStartedMsg)
	if started.err != nil {
		t.Fatal(started.err)
	}
	m, _ = uiUpdate(m, started)
	for m.screen == screenRunning {
		m, _ = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
	}
	args, err := os.ReadFile(filepath.Join(support, "preview-args"))
	if err != nil || string(args) != "--dry-run" {
		t.Fatalf("explicit preview must use --dry-run: %q %v", args, err)
	}
	if _, err := os.Stat(filepath.Join(support, "scanned")); !os.IsNotExist(err) {
		t.Fatal("cleanup executed the SDK scanner")
	}
}

func TestUINormalEntrypointsStillScanBeforeMenu(t *testing.T) {
	for _, page := range []string{"home", "frontend"} {
		t.Run(page, func(t *testing.T) {
			support := t.TempDir()
			fixtureScript(t, support, "scripts/check-env.sh", "printf checked > scanned")
			m := newModel(&Runner{SupportDir: support, LogRoot: t.TempDir()}, page)
			cmd := m.Init()
			if cmd == nil || m.screen != screenRunning {
				t.Fatal("normal entrypoint must perform its initial scan")
			}
			started := cmd().(jobStartedMsg)
			if started.err != nil {
				t.Fatal(started.err)
			}
			m, _ = uiUpdate(m, started)
			for m.screen == screenRunning {
				m, _ = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
			}
			contents, err := os.ReadFile(filepath.Join(support, "scanned"))
			if err != nil || string(contents) != "checked" || m.screen != screenMenu || m.page != page {
				t.Fatal("normal scan must finish at its requested menu")
			}
		})
	}
}

func TestUIFinishingResolvesUnfinishedStageStatus(t *testing.T) {
	for _, tc := range []struct {
		status      string
		code        int
		want, label string
	}{
		{"cancelled", 130, "cancelled", "已取消"},
		{"failed", 7, "failed", "失败"},
		{"succeeded", 0, "pending", "待配置"},
	} {
		t.Run(tc.status, func(t *testing.T) {
			m := readyUI(t, "home")
			m.screen, m.action = screenRunning, Action{ID: "fixture", Title: "任务"}
			m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "stage", ID: "complete", Title: "先前步骤", Status: "succeeded"}})
			m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "stage", ID: "active", Title: "当前步骤", Status: "running"}})
			m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "done", Status: tc.status, Code: tc.code}})
			if m.stages[0].Status != "succeeded" || m.stages[1].Status != tc.want {
				t.Fatalf("finished task left incorrect stage statuses: %#v", m.stages)
			}
			if strings.Contains(m.View().Content, "进行中") || !strings.Contains(m.View().Content, "当前步骤  "+tc.label) {
				t.Fatal("result page should show a terminal or pending stage label")
			}
		})
	}
}

func TestUICancelRequestPreservesConfirmedJobOutcome(t *testing.T) {
	for _, tc := range []struct {
		status   string
		code     int
		want     string
		wantCode int
	}{
		{"failed", 1, "failed", 1},
		{"succeeded", 0, "succeeded", 0},
		{"cancelled", 130, "cancelled", 130},
		{"", 0, "cancelled", 130},
	} {
		t.Run(tc.status, func(t *testing.T) {
			m := readyUI(t, "home")
			m.screen, m.action = screenRunning, Action{ID: "fixture", Title: "任务"}
			m.cancelRequested = true
			m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "done", Status: tc.status, Code: tc.code}})
			if m.resultStatus != tc.want || m.exitCode != tc.wantCode {
				t.Fatalf("request overrode actual job outcome: status %q code %d", m.resultStatus, m.exitCode)
			}
		})
	}
}

func TestUIStageHistoryIsBoundedAndRetainedStageCanUpdate(t *testing.T) {
	m := readyUI(t, "home")
	m.screen, m.action = screenRunning, Action{ID: "fixture", Title: "任务"}
	for i := 0; i < 200; i++ {
		m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "stage", ID: fmt.Sprintf("step-%d", i), Title: "步骤", Status: "running"}})
	}
	if len(m.stages) > 128 {
		t.Fatalf("stage history grew beyond its bound: %d", len(m.stages))
	}
	m, _ = uiUpdate(m, jobEventMsg{Event{Kind: "stage", ID: "step-199", Title: "最终步骤", Status: "succeeded"}})
	if last := m.stages[len(m.stages)-1]; last.ID != "step-199" || last.Status != "succeeded" {
		t.Fatalf("retained stage no longer updates: %#v", last)
	}
}
