package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"sync/atomic"
	"syscall"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/term"
)

var version = "0.1.0"

func main() { os.Exit(runCLI(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }

func runCLI(args []string, in *os.File, out, errout io.Writer) int {
	flags := flag.NewFlagSet("team-dev-env", flag.ContinueOnError)
	flags.SetOutput(errout)
	support := flags.String("support-dir", "", "支持文件目录（.support）")
	page := flags.String("page", "home", "起始页面：home、install 或 cleanup")
	components := flags.String("components", "", "预选组件，逗号分隔")
	gradleVersion := flags.String("gradle-version", "4.5.1", "4.5.1|6.8|all")
	nodeVersion := flags.String("node-version", "14", "none|10|14|18|22|all")
	showVersion := flags.Bool("version", false, "显示版本")
	flags.Usage = func() {
		fmt.Fprintln(out, "团队开发环境 · 交互终端界面\n\n用法：team-dev-env --support-dir PATH [--page home|install|cleanup]\n\n  --support-dir PATH  支持文件目录\n  --page PAGE         起始页面\n  --help              显示帮助\n  --version           显示版本\n\n需要交互终端；脚本或流水线请明确指定 install --components 或使用 --dry-run。")
	}
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *showVersion {
		fmt.Fprintln(out, "team-dev-env "+version)
		return 0
	}
	if flags.NArg() > 0 {
		fmt.Fprintln(errout, "不支持的位置参数；使用 --help 查看用法。")
		return 2
	}
	if *page != "home" && *page != "install" && *page != "cleanup" {
		fmt.Fprintln(errout, "--page 只能为 home、install 或 cleanup。")
		return 2
	}
	selection, selectionErr := componentSelection(*components)
	if selectionErr != nil {
		fmt.Fprintln(errout, selectionErr)
		return 2
	}
	if !containsArg([]string{"4.5.1", "6.8", "all"}, *gradleVersion) || !containsArg([]string{"none", "10", "14", "18", "22", "all"}, *nodeVersion) {
		fmt.Fprintln(errout, "版本选择无效")
		return 2
	}
	outputFile, ok := out.(*os.File)
	if in == nil || !term.IsTerminal(in.Fd()) || !ok || !term.IsTerminal(outputFile.Fd()) {
		fmt.Fprintln(errout, "交互界面需要 TTY 终端。请在终端打开启动器，或明确指定组件和非交互操作。")
		return 2
	}
	if *support == "" {
		fmt.Fprintln(errout, "请提供 --support-dir PATH；推荐通过项目启动器打开。")
		return 2
	}
	absSupport, err := filepath.Abs(*support)
	if err != nil {
		fmt.Fprintln(errout, err)
		return 2
	}
	info, err := os.Stat(filepath.Join(absSupport, "scripts", "check-env.sh"))
	if err != nil || info.IsDir() {
		fmt.Fprintln(errout, "支持目录不完整：缺少 scripts/check-env.sh。")
		return 2
	}
	m := newModel(&Runner{SupportDir: absSupport}, *page)
	m.components = selection
	m.gradleVersion = *gradleVersion
	m.nodeVersion = *nodeVersion
	if *page == "install" {
		_ = m.refreshInstallPlan()
	} else if *page == "home" {
		m.refreshHomepagePlan()
	}
	ctx, cancel := context.WithCancel(context.Background())
	m.lifecycle.ctx = ctx
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, syscall.SIGHUP, syscall.SIGTERM, syscall.SIGINT)
	var signalExit atomic.Int32
	handlerDone := make(chan struct{})
	go func() {
		defer close(handlerDone)
		for {
			select {
			case <-ctx.Done():
				return
			case received := <-signals:
				// ExecProcess gives Ctrl-C to the foreground uninstaller. While the
				// UI is paused, preserve Bubble Tea's normal SIGINT behavior.
				if received == syscall.SIGINT && m.lifecycle.interactive.Load() {
					continue
				}
				if sig, ok := received.(syscall.Signal); ok {
					signalExit.Store(int32(128 + sig))
				}
				cancel()
				// Task cleanup must not wait for the terminal renderer or input
				// reader to finish shutting down (for example, under PTY backpressure).
				m.lifecycle.close()
				return
			}
		}
	}()
	defer func() {
		signal.Stop(signals)
		cancel()
		<-handlerDone
	}()
	// Keep signals intercepted until task cleanup has finished. Closing a terminal
	// must not let a later signal bypass the cancellation and reaping below.
	defer m.lifecycle.close()
	final, err := tea.NewProgram(m, tea.WithInput(in), tea.WithOutput(out), tea.WithContext(ctx), tea.WithoutSignalHandler()).Run()
	m.lifecycle.close()
	if code := signalExit.Load(); code != 0 {
		return int(code)
	}
	if err != nil {
		fmt.Fprintln(errout, "终端界面已退出：", err)
		return 1
	}
	result, ok := final.(model)
	if !ok {
		fmt.Fprintln(errout, "终端界面返回了无效状态。")
		return 1
	}
	return result.exitCode
}
