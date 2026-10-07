#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

function fail(message) {
  process.stderr.write(`启动失败：${message}\n`);
  process.exitCode = 1;
}

function signalExitCode(signal) {
  return 128 + (os.constants.signals[signal] || 1);
}

function signalOwnedTree(pid, signal) {
  // A terminal already delivers Ctrl-C to the foreground process group. For
  // explicit TERM/HUP, reach only descendants of our launcher, never the user's
  // shell or unrelated processes sharing its terminal.
  const listing = spawnSync('/bin/ps', ['-axo', 'pid=,ppid='], {
    encoding: 'utf8', timeout: 1000, stdio: ['ignore', 'pipe', 'ignore']
  });
  const children = new Map();
  if (listing.status === 0) {
    for (const line of listing.stdout.split('\n')) {
      const fields = line.trim().match(/^(\d+)\s+(\d+)$/);
      if (!fields) continue;
      const child = Number(fields[1]);
      const parent = Number(fields[2]);
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(child);
    }
  }
  function forward(target) {
    for (const descendant of children.get(target) || []) forward(descendant);
    try { process.kill(target, signal); } catch (error) {
      if (error.code !== 'ESRCH') throw error;
    }
  }
  forward(pid);
}

function runLauncher(launcher, forwarded, environment) {
  return new Promise((resolve, reject) => {
    const terminal = Boolean(process.stdin.isTTY && process.stdout.isTTY);
    const child = spawn('/bin/bash', [launcher, ...forwarded], {
      stdio: 'inherit', env: environment, detached: !terminal
    });
    const handlers = new Map();
    let forwardedTermination = false;
    let launchError;
    for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
      const handler = () => {
        // In a TTY the foreground backend receives this same Ctrl-C directly.
        // Keep this parent alive so it can return the backend/TUI's final code.
        if (terminal && signal === 'SIGINT') return;
        if (forwardedTermination || !child.pid) return;
        forwardedTermination = true;
        try {
          if (terminal) signalOwnedTree(child.pid, signal);
          else process.kill(-child.pid, signal);
        } catch (error) {
          if (error.code !== 'ESRCH') {
            process.stderr.write(`无法传递终止信号：${error.message}\n`);
            child.kill(signal);
          }
        }
      };
      handlers.set(signal, handler);
      process.on(signal, handler);
    }
    child.once('error', error => { launchError = error; });
    child.once('close', (status, signal) => {
      for (const [name, handler] of handlers) process.removeListener(name, handler);
      if (launchError) reject(launchError);
      else resolve(status === null ? signalExitCode(signal) : status);
    });
  });
}

async function main(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(`用法：team-dev-env [install|frontend|uninstall] --server 主机:端口 [选项]

install     打开 Go TUI 主界面（默认）
frontend    打开前端工具页面；明确安装参数支持 --component all|node|iterm2|zsh 和 --node-version 14|16|18|all
uninstall   打开安全卸载页面；保留原 DELETE 确认
--plain     使用原文本菜单/命令行模式
--scheme    http 或 https，默认 http
--dry-run   仅显示下载地址与目标参数，不联网、不执行安装或卸载

也可使用 SERVER_ADDR、SERVER_SCHEME 环境变量指定团队服务。
npx 需要已有 Node/npm；尚未安装 Node 的电脑请使用 start.zip 双击入口。
`);
    return;
  }
  if (process.platform !== 'darwin') return fail('成员安装工具仅支持 macOS。');
  let mode = 'install';
  if (['install', 'frontend', 'uninstall'].includes(argv[0])) mode = argv.shift();
  let server = process.env.SERVER_ADDR || '';
  let scheme = process.env.SERVER_SCHEME || 'http';
  let preview = false;
  const forwarded = [];
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--server' || value === '--scheme') {
      const next = argv[++index];
      if (!next || next.startsWith('--')) return fail(`${value} 后需要值。`);
      if (value === '--server') server = next;
      else scheme = next;
    } else if (value.startsWith('--server=')) server = value.slice(9);
    else if (value.startsWith('--scheme=')) scheme = value.slice(9);
    else if (value === '--dry-run') preview = true;
    else forwarded.push(value);
  }
  if (!/^([A-Za-z0-9][A-Za-z0-9._-]*|\[[A-Fa-f0-9:]+\])(:[0-9]+)?$/.test(server)) {
    return fail('请用 --server 或 SERVER_ADDR 指定团队服务器（主机:端口，不含协议或路径）。');
  }
  if (!['http', 'https'].includes(scheme)) return fail('--scheme 只能为 http 或 https。');
  const entry = mode === 'uninstall' ? '卸载环境.command' : '开始配置.command';
  if (mode === 'frontend') forwarded.unshift('--frontend');
  if (preview) {
    process.stdout.write(`工具包：${scheme}://${server}/dev-env/team-dev-env.tar.gz\n`);
    process.stdout.write(`入口：${entry}\n参数：${forwarded.join(' ')}\n仅预演，未联网或执行。\n`);
    return;
  }
  const candidates = [path.join(__dirname, '../assets/start.command.in'), path.join(__dirname, '../../tools/start.command.in')];
  const templatePath = candidates.find(file => fs.existsSync(file));
  if (!templatePath) return fail('npm 包缺少下载模板，请重新获取完整包。');
  let temporary;
  try {
    const template = fs.readFileSync(templatePath, 'utf8')
      .split('@SERVER_ADDR@').join(server).split('@SERVER_SCHEME@').join(scheme)
      .split('@ENTRY_NAME@').join(entry).split('@ENTRY_LABEL@').join(mode === 'uninstall' ? '卸载' : '配置');
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'team-dev-env-npx-'));
    const launcher = path.join(temporary, 'launch.command');
    fs.writeFileSync(launcher, template, { mode: 0o700 });
    const childEnvironment = { ...process.env, SERVER_ADDR: server, SERVER_SCHEME: scheme };
    // npm exec 的临时 prefix 指向启动器的 Node，不能作为待安装 nvm 的全局目录。
    // 只处理 npm 命令上下文，不改用户 .npmrc 或父进程环境。
    if (process.env.npm_execpath) {
      for (const key of Object.keys(childEnvironment)) {
        if (key.toUpperCase() === 'NPM_CONFIG_PREFIX' || key === 'PREFIX') delete childEnvironment[key];
      }
    }
    process.exitCode = await runLauncher(launcher, forwarded, childEnvironment);
  } catch (error) {
    fail(error.message);
  } finally {
    if (temporary) fs.rmSync(temporary, { recursive: true, force: true });
  }
}

main(process.argv.slice(2)).catch(error => fail(error.message));
