package main

import (
	tea "charm.land/bubbletea/v2"
	"strings"
	"testing"
)

func TestInstallSelectionEnterStartsWithoutConfirmation(t *testing.T) {
	m := readyUI(t, "install")
	fixtureScript(t, m.runner.SupportDir, "scripts/manage-components.sh", `printf '%s\n' '{"schema":1,"components":[{"id":"jdk","target":"/fixture/jdk"}]}'`)
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if cmd != nil || m.screen != screenMenu {
		t.Fatal("empty selection must not run")
	}
	m, _ = uiUpdate(m, uiKey(' '))
	if !strings.Contains(m.View().Content, "[x] JDK") {
		t.Fatal("space must select JDK")
	}
	m, cmd = uiUpdate(m, uiKey(tea.KeyEnter))
	if cmd == nil || m.screen != screenRunning || m.action.Interactive {
		t.Fatal("one Enter must start selected installation")
	}
	if strings.Join(m.action.Args[:3], " ") != "scripts/manage-components.sh --components jdk" || !containsArg(m.action.Args, "--expected-plan") {
		t.Fatalf("unselected versions must not be forwarded: %v", m.action.Args)
	}
}

func TestDefaultNvmSelectionExecutesNode14(t *testing.T) {
	m := readyUI(t, "install")
	m.components["nvm"] = true
	fixtureScript(t, m.runner.SupportDir, "scripts/manage-components.sh", `printf '%s\n' '{"schema":1,"components":[{"id":"nvm","version":"14"}]}'`)
	if err := m.refreshInstallPlan(); err != nil {
		t.Fatal(err)
	}
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if cmd == nil || m.screen != screenRunning {
		t.Fatal("default nvm selection must start installation")
	}
	if strings.Join(m.action.Args[:5], " ") != "scripts/manage-components.sh --components nvm --node-version 14" {
		t.Fatalf("default nvm selection installed an unintended Node version: %v", m.action.Args)
	}
}

func TestStructuredComponentProgressDoesNotCompleteOnDownload(t *testing.T) {
	runner, action := fixtureRunner(t, "printf '@@TEAM_TUI\\tplan\\tcomponents\\t6\\t安装计划\\n'; printf '@@TEAM_TUI\\tcomponent\\tjdk\\tsucceeded\\tJDK\\n'; printf '@@TEAM_TUI\\tprogress\\tnvm\\tnode18\\t1\\t60\\t60\\n'; exit 1\n")
	job, err := runner.Start(action)
	if err != nil {
		t.Fatal(err)
	}
	events := collectJob(t, job)
	m := readyUI(t, "install")
	m.screen = screenRunning
	m.action = action
	for _, event := range events {
		m, _ = uiUpdate(m, jobEventMsg{event})
	}
	view := m.View().Content
	if !strings.Contains(view, "1 / 6") {
		t.Fatalf("component completion missing: %s", view)
	}
	if m.resultStatus != "failed" {
		t.Fatal("failed task must stay failed")
	}
}

func TestCleanupSelectionLoadsInstancesBeforeDeletion(t *testing.T) {
	m := readyUI(t, "cleanup")
	m.components["jdk"] = true
	fixtureScript(t, m.runner.SupportDir, "scripts/run-cleanup.sh", `printf '%s\n' '{"schema":1,"instances":[{"id":"jdk:one","component":"jdk","path":"/fixture/jdk","label":"JDK 8","removable":true,"reason":"受管安装"}],"notes":["`+strings.Repeat("x", 5000)+`"],"blockers":[]}'`)
	m, cmd := uiUpdate(m, uiKey(tea.KeyEnter))
	if m.action.Interactive || !containsArg(m.action.Args, "--plan-json") {
		t.Fatal("component selection must first discover exact instances without deletion")
	}
	started := cmd().(jobStartedMsg)
	if started.err != nil {
		t.Fatal(started.err)
	}
	m, _ = uiUpdate(m, started)
	for m.screen == screenRunning {
		m, _ = uiUpdate(m, jobEventMsg{receiveUIEvent(t, started.job)})
	}
	if m.page != "instances" || m.screen != screenMenu {
		t.Fatal("expected instance selection")
	}
	m, _ = uiUpdate(m, uiKey(' '))
	m, cmd = uiUpdate(m, uiKey(tea.KeyEnter))
	if cmd == nil || !m.action.Interactive || !containsArg(m.action.Args, "jdk:one") || containsArg(m.action.Args, "--yes") {
		t.Fatalf("only selected instances must reach DELETE confirmation: %v", m.action.Args)
	}
}

func TestReviewDefaultImpactAndOwnershipVisibleBeforeEnter(t *testing.T) {
	m := readyUI(t, "install")
	m.components["gradle"], m.components["nvm"] = true, true
	fixtureScript(t, m.runner.SupportDir, "scripts/manage-components.sh", `printf '%s\n' '{"schema":1,"components":[{"id":"gradle","status":"待验证","ownership":"外部安装","default_before":"4.5.1","default_after":"6.8","default_impact":"新终端默认 4.5.1 → 6.8"},{"id":"nvm","status":"已存在，待验证","ownership":"受本工具管理","default_before":"v16.20.2","default_after":"v22.23.3","default_impact":"新终端默认 v16.20.2 → v22.23.3"}]}'`)
	if err := m.refreshInstallPlan(); err != nil {
		t.Fatal(err)
	}
	view := m.View().Content
	for _, want := range []string{"待验证", "外部安装", "受本工具管理", "4.5.1 → 6.8", "v16.20.2 → v22.23.3"} {
		if !strings.Contains(view, want) {
			t.Fatalf("missing %q before Enter: %s", want, view)
		}
	}
}

func TestReviewCancelledComponentsHaveTerminalState(t *testing.T) {
	m := readyUI(t, "install")
	m.totalComponents = 3
	m.componentStates = map[string]Event{"jdk": {Status: "succeeded"}, "gradle": {Status: "running"}, "nvm": {Status: "pending"}}
	next, _ := m.finish("cancelled", 130)
	m = next.(model)
	if m.componentStates["jdk"].Status != "succeeded" || m.componentStates["gradle"].Status != "cancelled" || m.componentStates["nvm"].Status != "skipped" {
		t.Fatalf("unterminated components: %#v", m.componentStates)
	}
	if !strings.Contains(m.View().Content, "1 / 3") || !strings.Contains(m.View().Content, "已取消，未执行") {
		t.Fatal(m.View().Content)
	}
}

func TestReviewFailureTerminatesRunningAndPendingComponents(t *testing.T) {
	m := readyUI(t, "install")
	m.totalComponents = 3
	m.componentStates = map[string]Event{"jdk": {Status: "failed"}, "gradle": {Status: "pending"}, "nvm": {Status: "running"}}
	next, _ := m.finish("failed", 31)
	m = next.(model)
	if m.componentStates["jdk"].Status != "failed" || m.componentStates["gradle"].Status != "skipped" || m.componentStates["nvm"].Status != "failed" {
		t.Fatalf("unterminated components: %#v", m.componentStates)
	}
	if strings.Contains(m.View().Content, "3 / 3") {
		t.Fatal("failure cannot complete progress")
	}
}

func TestReviewOldPlanMetadataIsConservativelyUnknown(t *testing.T) {
	m := readyUI(t, "install")
	m.components["jdk"] = true
	m.installPlan = &InstallPlan{Schema: 1}
	if !strings.Contains(m.View().Content, "检测未知 / 归属未知") {
		t.Fatal(m.View().Content)
	}
}

func TestReviewAllEntryDisclosesManagerDefaults(t *testing.T) {
	m := readyUI(t, "home")
	fixtureScript(t, m.runner.SupportDir, "scripts/manage-components.sh", `printf '%s\n' '{"schema":1,"gradle_version":"4.5.1","node_version":"all","components":[{"id":"gradle","default_impact":"默认 6.8 → 4.5.1"},{"id":"nvm","default_impact":"默认失效 → v14.21.3"}]}'`)
	m.refreshHomepagePlan()
	for i, a := range m.menuActions() {
		if a.ID == "install-all" {
			m.cursor = i
		}
	}
	if !strings.Contains(m.View().Content, "6.8 → 4.5.1") || !strings.Contains(m.View().Content, "失效 → v14.21.3") {
		t.Fatal(m.View().Content)
	}
}

func TestReviewPreflightFailureKeepsAllActionVersions(t *testing.T) {
	m := readyUI(t, "install")
	m.action = Action{ID: "install-all"}
	m.gradleVersion, m.nodeVersion = "6.8", "none"
	fixtureScript(t, m.runner.SupportDir, "scripts/manage-components.sh", `printf '%s\n' '{"schema":1,"gradle_version":"4.5.1","node_version":"all","components":[{"id":"jdk"}]}'`)
	m.refreshHomepagePlan()
	next, _ := m.finish("failed", 1)
	m = next.(model)
	if m.screen != screenMenu || m.page != "install" || m.gradleVersion != "4.5.1" || m.nodeVersion != "all" {
		t.Fatalf("action semantics changed after preflight: %s %s", m.gradleVersion, m.nodeVersion)
	}
}

func TestReviewCancelledShellSkippedEventKeepsCancellationReason(t *testing.T) {
	m := readyUI(t, "install")
	m.totalComponents = 2
	m.componentStates = map[string]Event{"nvm": {Status: "cancelled"}, "iterm2": {Status: "skipped", Title: "iTerm2：已取消，未执行"}}
	next, _ := m.finish("cancelled", 130)
	m = next.(model)
	if !strings.Contains(m.View().Content, "已取消，未执行") || strings.Contains(m.View().Content, "依赖失败") {
		t.Fatal(m.View().Content)
	}
}
