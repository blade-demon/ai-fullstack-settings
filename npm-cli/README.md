# team-dev-env-preview

macOS 团队开发环境的薄启动入口。包内只有启动代码与共用下载模板，实际工具及资源由指定的团队服务器提供。无需全局安装；运行 npx 的电脑本身需已有 Node/npm。无 Node 的新电脑使用团队提供的 `start.zip`。

包名暂定，`private: true` 防止临时名称被发布；当前支持本地 npm 打包和 npx 验证。

```bash
team-dev-env --server 192.168.1.20:8080
team-dev-env frontend --server 192.168.1.20:8080
team-dev-env frontend --component node --node-version 16 --server 192.168.1.20:8080
team-dev-env uninstall --server 192.168.1.20:8080
team-dev-env frontend --server 192.168.1.20:8080 --dry-run
```

也可设置 `SERVER_ADDR`、`SERVER_SCHEME`。`--dry-run` 仅预览地址与参数，不下载或执行；Java 环境卸载保留原确认流程，新前端工具暂不在该卸载范围。

维护者在本目录执行 `npm pack`，会从仓库唯一的 `tools/start.command.in` 生成包内模板。包不包含服务器私有地址、SDK 安装包、卸载运行时或用户配置，也没有安装后自动修改系统的生命周期脚本。

定名后，将 `name` 改为有发布权限的正式名称，移除 `private`，检查 `npm pack --dry-run` 清单，再按团队选择的 registry 执行 `npm publish`。发布到 npm 之后，使用者通过 `npx 正式包名 ...` 运行。当前没有公开发布此临时包。

启动器隔离 npm 命令上下文中的临时 prefix 变量，避免干扰 nvm；不会修改用户持久 `.npmrc` 或父终端环境。

有交互终端且未指定业务参数时，install、frontend、uninstall分别打开Go TUI页面；成员无需安装Go。`--plain`保留原文本模式，明确组件参数继续直接调用脚本。
