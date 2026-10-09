package main

import (
	tea "charm.land/bubbletea/v2"
	"path/filepath"
	"strings"
	"testing"
)

// A literal tilde, USER-based reconstruction, or an extra Users directory would
// show a different destination from the scripts' HOME/Applications directory.
func TestApplicationInstallDirectoryViewsUseExpandedHome(t *testing.T) {
	home := filepath.Join(t.TempDir(), "Users", "中文用户名")
	want := home + "/Applications"
	t.Setenv("HOME", home)
	t.Setenv("USER", "different-login-name")

	for _, tc := range []struct{ page, id string }{
		{"install", "idea"},
		{"install", "iterm2"},
	} {
		t.Run(tc.id, func(t *testing.T) {
			m := applicationActionMenu(t, tc.page, tc.id)
			views := map[string]string{"menu": m.View().Content}
			m, cmd := uiUpdate(m, uiKey(' '))
			if m.screen != screenMenu || cmd != nil {
				t.Fatal("selection must stay on the component page")
			}
			views["confirmation"] = m.View().Content
			for name, view := range views {
				if !strings.Contains(view, want) {
					t.Errorf("%s must show expanded application directory %q: %s", name, want, strings.Join(strings.Fields(view), " "))
				}
				for _, wrong := range []string{"~/Applications", "different-login-name", home + "/Users/"} {
					if strings.Contains(view, wrong) {
						t.Errorf("%s shows an incorrect application directory %q", name, wrong)
					}
				}
			}
		})
	}
}

// An unavailable HOME must not appear to resolve to the system applications
// directory, a relative directory, or a guessed user account.
func TestApplicationInstallDirectoryViewsExplainMissingHome(t *testing.T) {
	t.Setenv("HOME", "")
	t.Setenv("USER", "different-login-name")

	for _, tc := range []struct{ page, id string }{
		{"install", "idea"},
		{"install", "iterm2"},
	} {
		t.Run(tc.id, func(t *testing.T) {
			m := applicationActionMenu(t, tc.page, tc.id)
			views := map[string]string{"menu": m.View().Content}
			m, _ = uiUpdate(m, uiKey(' '))
			views["confirmation"] = m.View().Content
			for name, view := range views {
				if !strings.Contains(view, "HOME") || !strings.Contains(view, "未设置") {
					t.Errorf("%s must explain the missing HOME: %s", name, strings.Join(strings.Fields(view), " "))
				}
				for _, wrong := range []string{"/Applications", "当前用户 Applications", "different-login-name"} {
					if strings.Contains(view, wrong) {
						t.Errorf("%s claims an application destination despite missing HOME: %q", name, wrong)
					}
				}
			}
		})
	}
}

func applicationActionMenu(t *testing.T, page, id string) model {
	t.Helper()
	m := readyUI(t, page)
	m, _ = uiUpdate(m, tea.WindowSizeMsg{Width: 240, Height: 40})
	for i, action := range ActionsFor(page) {
		if action.ID == id {
			m.cursor = i
			return m
		}
	}
	t.Fatalf("missing application action %q", id)
	return m
}
