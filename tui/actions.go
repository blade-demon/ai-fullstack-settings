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
	switch page {
	case "gradle":
		return []Action{
			{ID: "gradle-4", Title: "Gradle 4.5.1", Description: "安装或复用 Gradle 4.5.1，配置 JDK 8 与环境变量。", Args: []string{"scripts/repair-env.sh", "--scope", "gradle", "--gradle-version", "4.5.1"}},
			{ID: "gradle-6", Title: "Gradle 6.8", Description: "安装或复用 Gradle 6.8，配置 JDK 8 与环境变量。", Args: []string{"scripts/repair-env.sh", "--scope", "gradle", "--gradle-version", "6.8"}},
		}
	case "frontend":
		return []Action{
			{ID: "frontend-all", Title: "一键安装前端环境", Description: "nvm、Node 14/16/18、iTerm2、Oh My Zsh 和推荐插件。Node 14 在 Apple Silicon 上需要 Rosetta。", Args: []string{"scripts/frontend-env.sh"}},
			{ID: "node14", Title: "nvm + Node 14", Description: "旧项目兼容版本；Apple Silicon 需要已有 Rosetta。", Args: []string{"scripts/frontend-env.sh", "--component", "node", "--node-version", "14"}},
			{ID: "node16", Title: "nvm + Node 16", Description: "安装并验证固定 Node 16，设为 nvm 默认版本。", Args: []string{"scripts/frontend-env.sh", "--component", "node", "--node-version", "16"}},
			{ID: "node18", Title: "nvm + Node 18", Description: "安装并验证固定 Node 18，设为 nvm 默认版本。", Args: []string{"scripts/frontend-env.sh", "--component", "node", "--node-version", "18"}},
			{ID: "node-all", Title: "nvm + 全部 Node 版本", Description: "安装 14/16/18，保留已有默认版本；首次默认 18。", Args: []string{"scripts/frontend-env.sh", "--component", "node"}},
			{ID: "iterm2", Title: "iTerm2", Description: applicationInstallDescription() + "，要求 macOS 13+。", Args: []string{"scripts/frontend-env.sh", "--component", "iterm2"}},
			{ID: "zsh", Title: "Oh My Zsh 与推荐插件", Description: "需要可用 Git；保留用户主题和配置，修改前备份。", Args: []string{"scripts/frontend-env.sh", "--component", "zsh"}},
		}
	case "cleanup":
		return []Action{
			{ID: "cleanup-preview", Title: "预览卸载清单", Description: "只读取安装和配置，不删除文件。", Args: []string{"scripts/run-cleanup.sh", "--dry-run"}},
			{ID: "cleanup-run", Title: "进入安全卸载流程", Description: "下一步在终端选择 IDEA 范围、核对删除清单并输入 DELETE。前端工具不在该卸载范围。", Args: []string{"scripts/run-cleanup.sh"}, Interactive: true},
		}
	default:
		return []Action{
			{ID: "java-all", Title: "一键安装 Java 环境", Description: "JDK 8 + Gradle 4.5.1、IDEA 和全部六个插件。请先保存工作并退出 IDEA。", Args: []string{"scripts/repair-env.sh", "--scope", "all", "--gradle-version", "4.5.1"}},
			{ID: "jdk8", Title: "安装并配置 JDK 8", Description: "安装或复用完整 JDK 8，配置持久环境变量。", Args: []string{"scripts/repair-env.sh", "--scope", "jdk"}},
			{ID: "page:gradle", Title: "安装并配置 Gradle", Description: "选择 Gradle 4.5.1 或 6.8。"},
			{ID: "idea", Title: "安装 IDEA 软件", Description: applicationInstallDescription() + "；保留冲突应用。", Args: []string{"scripts/repair-env.sh", "--scope", "idea"}},
			{ID: "plugins", Title: "安装推荐 IDEA 插件", Description: "安装并验证全部六个插件；请先退出 IDEA。", Args: []string{"scripts/repair-env.sh", "--scope", "plugins"}},
			{ID: "page:frontend", Title: "安装前端环境", Description: "nvm / Node、iTerm2、Oh My Zsh。"},
			{ID: "page:cleanup", Title: "卸载环境", Description: "先预览，保留现有删除范围和 DELETE 确认。"},
		}
	}
}
