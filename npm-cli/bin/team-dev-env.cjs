#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

function fail(message, code = 1) {
  process.stderr.write(`启动失败：${message}\n`);
  process.exitCode = code;
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
  if (argv.includes('--plain') || argv.includes('--frontend')) {
    return fail('--plain/--frontend 已移除，请使用 install --components nvm,iterm2,oh-my-zsh。', 2);
  }
  let mode = 'install';
  if (['install', 'uninstall'].includes(argv[0])) mode = argv.shift();
  else if (argv[0] === 'help') {
    argv.shift();
    if (argv.length > 1 || (argv.length && !['install', 'uninstall'].includes(argv[0]))) {
      return fail('帮助目标仅支持 install 或 uninstall。', 2);
    }
    argv = ['--help'];
  } else if (argv[0] && !argv[0].startsWith('-')) return fail(`未知操作：${argv[0]}`, 2);
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(`用法：team-dev-env [install|uninstall] --server 主机:端口 [选项]

install     打开安装页，按 Enter 执行所选组件
uninstall   打开卸载页，保留 DELETE 确认
--components jdk,gradle,nvm,idea,iterm2,oh-my-zsh 或 all
--gradle-version 4.5.1|6.8|all
--node-version none|10|14|18|22|all
--scheme    http 或 https，默认 http
--dry-run   本地启动器预演，不联网、不执行

也可使用 SERVER_ADDR、SERVER_SCHEME 指定团队服务。
npx 需要 Node >=14.14；未安装 Node 时使用 bash devtool-helper.sh。
`);
    return;
  }
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
  for (let index = 0; index < forwarded.length; index += 1) {
    const arg = forwarded[index];
    let components;
    if (arg === '--components') components = forwarded[++index];
    else if (arg.startsWith('--components=')) components = arg.slice(13);
    else continue;
    if (!components || !components.split(',').every(item => ['jdk', 'gradle', 'nvm', 'idea', 'iterm2', 'oh-my-zsh', 'all'].includes(item)) ||
        (components !== 'all' && components.split(',').includes('all'))) return fail('组件范围无效。', 2);
  }
  if (!preview && mode === 'install' && !(process.stdin.isTTY && process.stdout.isTTY) &&
      !forwarded.some((arg, index) => (arg === '--components' && forwarded[index + 1] && !forwarded[index + 1].startsWith('-')) ||
                                  (arg.startsWith('--components=') && arg.length > 13))) {
    return fail('非交互安装必须明确 --components。', 2);
  }
  if (!/^([A-Za-z0-9][A-Za-z0-9._-]*|\[[A-Fa-f0-9:]+\])(:[0-9]+)?$/.test(server)) {
    return fail('请用 --server 或 SERVER_ADDR 指定团队服务器（主机:端口，不含协议或路径）。');
  }
  if (!['http', 'https'].includes(scheme)) return fail('--scheme 只能为 http 或 https。');
  if (preview) {
    process.stdout.write(`工具包：${scheme}://${server}/dev-env/team-dev-env.tar.gz\n`);
    process.stdout.write(`入口：.support/scripts/run-tool.sh ${mode}\n参数：${forwarded.join(' ')}\n仅预演，未联网或执行。\n`);
    return;
  }
  if (process.platform !== 'darwin') return fail('成员安装工具仅支持 macOS。');
  const candidates = [path.join(__dirname, '../assets/devtool-helper.sh.in'), path.join(__dirname, '../../tools/devtool-helper.sh.in')];
  const templatePath = candidates.find(file => fs.existsSync(file));
  if (!templatePath) return fail('npm 包缺少下载模板，请重新获取完整包。');
  let temporary;
  try {
    const template = fs.readFileSync(templatePath, 'utf8')
      .split('@SERVER_ADDR@').join(server).split('@SERVER_SCHEME@').join(scheme);
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'team-dev-env-npx-'));
    const launcher = path.join(temporary, 'devtool-helper.sh');
    fs.writeFileSync(launcher, template, { mode: 0o700 });
    const childEnvironment = { ...process.env, SERVER_ADDR: server, SERVER_SCHEME: scheme };
    // npm exec 的临时 prefix 指向启动器的 Node，不能作为待安装 nvm 的全局目录。
    // 只处理 npm 命令上下文，不改用户 .npmrc 或父进程环境。
    if (process.env.npm_execpath) {
      for (const key of Object.keys(childEnvironment)) {
        if (key.toUpperCase() === 'NPM_CONFIG_PREFIX' || key === 'PREFIX') delete childEnvironment[key];
      }
    }
    process.exitCode = await runLauncher(launcher, [mode, ...forwarded], childEnvironment);
  } catch (error) {
    fail(error.message);
  } finally {
    if (temporary) fs.rmSync(temporary, { recursive: true, force: true });
  }
}

main(process.argv.slice(2)).catch(error => fail(error.message));
