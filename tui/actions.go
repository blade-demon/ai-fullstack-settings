package main

import (
	"os"
	"path/filepath"
)

type Action struct {
	ID, Title, Description string
	Args                   []string
	Interactive            bool
}

func applicationInstallDescription() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "无法确定安装目录（HOME 未设置）"
	}
	return "安装到 " + filepath.Join(home, "Applications")
}

func ActionsFor(page string) []Action {
	if page == "install" || page == "cleanup" {
		actions := make([]Action, 0, 6)
		for _, item := range Components() {
			actions = append(actions, Action{ID: item.ID, Title: item.Title, Description: item.Description})
		}
		return actions
	}
	return []Action{
		{ID: "page:install", Title: "安装与配置", Description: "空格选择组件，左右键选择版本，Enter 开始安装。"},
		{ID: "page:cleanup", Title: "卸载工具", Description: "选择组件，预览具体清单并输入 DELETE 确认。"},
		{ID: "install-all", Title: "一键安装配置全部", Description: "JDK 8 → Gradle 4.5.1 → Node 14 → iTerm2 → Oh My Zsh → IDEA/插件", Args: []string{"scripts/manage-components.sh", "--components", "all"}},
	}
}
