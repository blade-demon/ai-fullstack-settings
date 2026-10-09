package main

import (
	tea "charm.land/bubbletea/v2"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type PlanComponent struct {
	ID                string `json:"id"`
	Title             string `json:"title"`
	Version           string `json:"version"`
	Target            string `json:"target"`
	Status            string `json:"status"`
	Ownership         string `json:"ownership"`
	DefaultBefore     string `json:"default_before"`
	DefaultAfter      string `json:"default_after"`
	DefaultImpact     string `json:"default_impact"`
	DefaultValidation string `json:"default_validation"`
}

type InstallPlan struct {
	Schema        int             `json:"schema"`
	GradleVersion string          `json:"gradle_version"`
	NodeVersion   string          `json:"node_version"`
	GradleDefault string          `json:"gradle_default"`
	Components    []PlanComponent `json:"components"`
	Inventory     []PlanComponent `json:"inventory"`
	Token         string          `json:"-"`
}

func (p *InstallPlan) component(id string) PlanComponent {
	if p != nil {
		for _, item := range p.Components {
			if item.ID == id {
				return item
			}
		}
		for _, item := range p.Inventory {
			if item.ID == id {
				return item
			}
		}
	}
	return PlanComponent{ID: id}
}

func (m *model) refreshHomepagePlan() {
	plan, err := m.runner.InstallPlan(Action{Args: []string{"scripts/manage-components.sh", "--components", "all"}})
	if err == nil {
		m.installPlan = plan
	} else {
		m.installPlan = nil
	}
}

func (r *Runner) InstallPlan(action Action) (*InstallPlan, error) {
	request := action
	request.Args = append(append([]string{}, action.Args...), "--plan-json")
	base, err := r.Command(request)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, base.Path, base.Args[1:]...)
	cmd.Dir = base.Dir
	cmd.Env = base.Env
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("安装计划生成失败：%w", err)
	}
	raw := strings.TrimSpace(string(out))
	var plan InstallPlan
	if err = json.Unmarshal([]byte(raw), &plan); err != nil || plan.Schema != 1 || len(plan.Components) == 0 {
		return nil, fmt.Errorf("安装计划格式无效")
	}
	digest := sha256.Sum256([]byte(raw))
	plan.Token = hex.EncodeToString(digest[:])
	return &plan, nil
}

func (m *model) refreshInstallPlan() error {
	action := m.selectionAction(false)
	if len(m.selectedIDs()) == 0 {
		action = Action{Args: []string{"scripts/manage-components.sh", "--components", "all"}}
	}
	plan, err := m.runner.InstallPlan(action)
	if err != nil {
		m.scanSummary = err.Error()
		return err
	}
	m.installPlan = plan
	m.scanSummary = "选择已就绪；Enter 开始安装"
	return nil
}

func (m model) startInstallation() (tea.Model, tea.Cmd) {
	plan, err := m.runner.InstallPlan(m.action)
	if err != nil {
		m.scanSummary = err.Error()
		return m, nil
	}
	if m.installPlan != nil && m.installPlan.Token != plan.Token {
		m.installPlan = plan
		m.scanSummary = "安装目录或默认配置已变化，请核对后再次按 Enter"
		return m, nil
	}
	m.installPlan = plan
	m.action.Args = append(m.action.Args, "--expected-plan", plan.Token)
	return m.beginAction()
}

type Component struct{ ID, Title, Description string }

func Components() []Component {
	home, _ := os.UserHomeDir()
	return []Component{
		{"jdk", "JDK 8", "安装并配置 JDK 8；" + filepath.Join(home, ".local/share/java-dev/jdk8")},
		{"gradle", "Gradle", "4.5.1 / 6.8；自动补齐 JDK，安装后通过 gradle_use 切换"},
		{"nvm", "nvm / Node", "Node 10/14/18/22 或仅 nvm；通过 nvm use 切换"},
		{"iterm2", "iTerm2", applicationInstallDescription() + "；不更改默认终端"},
		{"oh-my-zsh", "Oh My Zsh", "框架与四个推荐插件；保留用户主题"},
		{"idea", "IDEA / 插件", applicationInstallDescription() + "；包含六个推荐插件"},
	}
}

func componentSelection(value string) (map[string]bool, error) {
	selected := make(map[string]bool)
	if value == "" {
		return selected, nil
	}
	if value == "all" {
		for _, item := range Components() {
			selected[item.ID] = true
		}
		return selected, nil
	}
	for _, id := range strings.Split(value, ",") {
		found := false
		for _, item := range Components() {
			if item.ID == id {
				found = true
				selected[id] = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("未知组件：%s", id)
		}
	}
	return selected, nil
}

func (m model) selectedIDs() []string {
	var ids []string
	for _, item := range Components() {
		if m.components[item.ID] || (m.page == "install" && item.ID == "jdk" && m.components["gradle"]) {
			ids = append(ids, item.ID)
		}
	}
	return ids
}

func (m model) selectionAction(preview bool) Action {
	ids := m.selectedIDs()
	args := []string{"scripts/manage-components.sh", "--components", strings.Join(ids, ",")}
	action := Action{ID: "install-selected", Title: "安装与配置", Description: strings.Join(ids, "、")}
	if m.page == "cleanup" || m.page == "instances" {
		args[0] = "scripts/run-cleanup.sh"
		action.ID, action.Title, action.Interactive = "cleanup-run", "安全卸载所选组件", !preview
		if preview {
			args = append(args, "--dry-run")
			action.ID = "cleanup-preview"
		}
	} else {
		if m.components["gradle"] {
			args = append(args, "--gradle-version", m.gradleVersion)
		}
		if m.components["nvm"] {
			args = append(args, "--node-version", m.nodeVersion)
		}
	}
	if m.page == "instances" {
		var ids []string
		for _, item := range m.instances {
			if m.instanceSelection[item.ID] {
				ids = append(ids, item.ID)
			}
		}
		args = append(args, "--instances", strings.Join(ids, ","))
	}
	action.Args = args
	return action
}

func cycleVersion(current string, values []string, backwards bool) string {
	for i, value := range values {
		if value == current {
			if backwards {
				return values[(i+len(values)-1)%len(values)]
			}
			return values[(i+1)%len(values)]
		}
	}
	return values[0]
}

func progressBar(completed, total int64, width int) string {
	width = max(8, min(width, 32))
	if total <= 0 {
		return "[" + strings.Repeat("─", width) + "]"
	}
	filled := int(float64(completed) / float64(total) * float64(width))
	filled = max(0, min(width, filled))
	return "[" + strings.Repeat("█", filled) + strings.Repeat("░", width-filled) + "]"
}

type CleanupInstance struct {
	ID        string `json:"id"`
	Component string `json:"component"`
	Path      string `json:"path"`
	Label     string `json:"label"`
	Reason    string `json:"reason"`
	Removable bool   `json:"removable"`
}
type CleanupPlan struct {
	Schema    int               `json:"schema"`
	Instances []CleanupInstance `json:"instances"`
	Notes     []string          `json:"notes"`
	Blockers  []string          `json:"blockers"`
}

func (m model) menuActions() []Action {
	if m.page != "instances" {
		return ActionsFor(m.page)
	}
	actions := make([]Action, 0, len(m.instances))
	for _, item := range m.instances {
		label := safeLogLine(item.Label)
		if !item.Removable {
			label += "（保留）"
		}
		actions = append(actions, Action{ID: item.ID, Title: label, Description: safeLogLine(item.Path + " · " + item.Reason)})
	}
	return actions
}

func activityBar(frame, width int) string {
	width = max(8, min(width, 32))
	offset := frame % (width - 3)
	return "[" + strings.Repeat(" ", offset) + "━━━━" + strings.Repeat(" ", width-offset-4) + "]"
}
