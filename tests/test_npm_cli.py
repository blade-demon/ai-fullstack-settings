"""npm 薄入口的命令行契约；不下载真实 SDK、不运行安装。"""
import os
import fcntl
import select
import shlex
import signal
import sys
import termios
import time
import functools
import hashlib
import http.server
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


@unittest.skipUnless(NODE, 'requires Node for npm launcher tests')
class NpmCliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([NODE, str(ROOT / 'npm-cli/bin/team-dev-env.cjs'), *args],
                              env={'PATH': '/usr/bin:/bin', 'HOME': os.environ['HOME'], **(env or {})},
                              text=True, capture_output=True, timeout=5)

    def test_help_needs_no_server_or_network(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('frontend', result.stdout)
        self.assertIn('--server', result.stdout)

    def test_explicit_server_and_frontend_arguments_are_preserved_in_preview(self):
        result = self.run_cli('frontend', '--server', 'team.example:9090', '--scheme', 'https',
                              '--component', 'node', '--node-version', '16', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://team.example:9090/dev-env/team-dev-env.tar.gz', result.stdout)
        self.assertIn('--frontend --component node --node-version 16', result.stdout)

    def test_uninstall_preview_does_not_execute_or_add_apply(self):
        result = self.run_cli('uninstall', '--server', '127.0.0.1:8080', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('卸载环境.command', result.stdout)
        self.assertNotIn('--apply', result.stdout)

    def test_missing_or_unsafe_server_fails_before_download(self):
        for arguments in [[], ['--server', ''], ['--server', 'https://host/x'],
                          ['--server', 'x;echo unsafe'], ['--server', 'host', '--scheme', 'file']]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertNotEqual(result.returncode, 0)

    def test_team_environment_can_supply_server(self):
        result = self.run_cli('--dry-run', env={'SERVER_ADDR': 'mirror.example:8080', 'SERVER_SCHEME': 'https'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://mirror.example:8080/', result.stdout)

    def test_frontend_downloads_verified_payload_and_preserves_its_failure_status(self):
        with tempfile.TemporaryDirectory(prefix="npx route's ") as temporary:
            root = Path(temporary)
            (root / 'dev-env').mkdir()
            archive = root / 'dev-env/team-dev-env.tar.gz'
            payload = (b'#!/bin/bash\n'
                       b'[ -z "${npm_config_prefix:-}${NPM_CONFIG_PREFIX:-}${PREFIX:-}" ] || exit 44\n'
                       b'printf "%s\\0" "$@" > "$ENTRY_RECORD"\nexit 43\n')
            with tarfile.open(archive, 'w:gz') as package:
                info = tarfile.TarInfo('team-dev-env/开始配置.command')
                info.mode = 0o755; info.size = len(payload)
                package.addfile(info, io.BytesIO(payload))
            archive.with_name(archive.name + '.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '\n')
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *args): pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                record = root / 'arguments'
                result = self.run_cli('frontend', '--server', f'127.0.0.1:{server.server_port}',
                                      '--component', 'node', '--node-version', '16', env={
                                          'ENTRY_RECORD': str(record), 'npm_execpath': '/fixture/npm-cli.js',
                                          'npm_config_prefix': '/old/npm', 'NPM_CONFIG_PREFIX': '/old/npm', 'PREFIX': '/old/npm'})
                self.assertEqual(result.returncode, 43, result.stdout + result.stderr)
                self.assertEqual(record.read_bytes().decode().split('\0')[:-1],
                                 ['--frontend', '--component', 'node', '--node-version', '16'])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)

@unittest.skipUnless(NODE and sys.platform == 'darwin', 'macOS npx signal chain')
class NpmSignalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="npx signal's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.package = self.base / 'launcher'
        (self.package / 'bin').mkdir(parents=True)
        (self.package / 'assets').mkdir()
        shutil.copy2(ROOT / 'npm-cli/bin/team-dev-env.cjs', self.package / 'bin/team-dev-env.cjs')
        shutil.copy2(ROOT / 'tools/start.command.in', self.package / 'assets/start.command.in')
        self.web = self.base / 'web'
        (self.web / 'dev-env').mkdir(parents=True)
        archive = self.web / 'dev-env/team-dev-env.tar.gz'
        helper = ('#!/bin/bash\nexec ' + shlex.quote(sys.executable) + ' -u "$PAYLOAD_WORKER" "$@"\n').encode()
        self.worker = self.base / 'worker.py'
        self.worker.write_text(SIGNAL_WORKER)
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, content in [('卸载环境.command', (ROOT / 'dev-kit/卸载环境.command').read_bytes()),
                                  ('.support/scripts/run-tui.sh', helper),
                                  ('.support/scripts/run-cleanup.sh', helper)]:
                info = tarfile.TarInfo('team-dev-env/' + name)
                info.mode = 0o755
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
        archive.with_name(archive.name + '.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '\n')
        self.requested = threading.Event()
        self.release = threading.Event()
        self.block_download = False
        owner = self
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if owner.block_download:
                    owner.requested.set()
                    owner.release.wait(10)
                try:
                    super().do_GET()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(self.web)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.record = self.base / 'processes'
        self.downloads = self.base / 'downloads'
        self.downloads.mkdir()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'TMPDIR': str(self.downloads),
                    'PAYLOAD_WORKER': str(self.worker), 'PAYLOAD_RECORD': str(self.record), 'TERM': 'xterm-256color'}
        self.command = [NODE, str(self.package / 'bin/team-dev-env.cjs'), 'uninstall',
                        '--server', f'127.0.0.1:{self.server.server_port}']

    def stop_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def start_terminal(self):
        import pty
        master, slave = pty.openpty()
        def terminal():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        process = subprocess.Popen(self.command, stdin=slave, stdout=slave, stderr=slave,
                                   env=self.env, preexec_fn=terminal)
        os.close(slave)
        self.addCleanup(self.stop_process, process, master)
        return process, master

    def stop_process(self, process, master=None):
        if master is not None:
            os.close(master)
        if self.record.exists():
            for pid in self.record.read_text().split():
                try: os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError: pass
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)

    def read_until(self, process, master, expected, timeout=8):
        output = b''
        deadline = time.monotonic() + timeout
        while expected.encode() not in output and time.monotonic() < deadline:
            if select.select([master], [], [], .05)[0]:
                try: output += os.read(master, 65536)
                except OSError: break
            elif process.poll() is not None:
                break
        self.assertIn(expected, output.decode(errors='replace'))
        return output

    def wait_terminal(self, process, master, timeout=8):
        deadline = time.monotonic() + timeout
        while process.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], .05)[0]:
                try: os.read(master, 65536)
                except OSError: pass
        return process.wait(timeout=1)

    def assert_workers_gone(self):
        for text in self.record.read_text().split():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(text), 0)

    def test_terminal_ctrl_c_preserves_parent_until_payload_result_and_real_exit(self):
        process, master = self.start_terminal()
        self.read_until(process, master, 'READY')
        os.write(master, b'\x03')
        self.read_until(process, master, 'CANCELLED')
        self.assertIsNone(process.poll(), 'npx parent exited before the payload result page')
        os.write(master, b'q\n')
        self.assertEqual(self.wait_terminal(process, master), 0)
        self.assert_workers_gone()
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_real_npx_keeps_result_page_after_terminal_ctrl_c(self):
        npm, npx = shutil.which('npm'), shutil.which('npx')
        if not npm or not npx:
            self.skipTest('npm/npx required for the complete launcher chain')
        (self.package / 'package.json').write_text(json.dumps({
            'name': 'team-dev-env-signal-fixture', 'version': '0.0.0', 'private': True,
            'bin': {'team-dev-env': 'bin/team-dev-env.cjs'}, 'files': ['bin/', 'assets/']}))
        self.env['npm_config_cache'] = str(self.base / 'npm-cache')
        self.env['NODE_COMPILE_CACHE'] = str(self.base / 'node-compile-cache')
        packed = subprocess.run([npm, 'pack', '--ignore-scripts', '--json', '--pack-destination', str(self.base)],
                                cwd=self.package, env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
        tarball = self.base / json.loads(packed.stdout)[0]['filename']
        self.command = [npx, '--offline', '--yes', '--package', str(tarball), 'team-dev-env',
                        'uninstall', '--server', f'127.0.0.1:{self.server.server_port}']
        process, master = self.start_terminal()
        self.read_until(process, master, 'READY')
        os.write(master, b'\x03')
        self.read_until(process, master, 'CANCELLED')
        self.assertIsNone(process.poll(), 'outer npm exited before the result page')
        os.write(master, b'q\n')
        self.assertEqual(self.wait_terminal(process, master), 0)
        self.assert_workers_gone()
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_terminal_download_ctrl_c_stops_without_starting_payload(self):
        self.block_download = True
        process, master = self.start_terminal()
        self.assertTrue(self.requested.wait(5))
        os.write(master, b'\x03')
        self.assertEqual(self.wait_terminal(process, master), 130)
        self.assertFalse(self.record.exists())
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_noninteractive_interrupt_and_terminate_reap_payload_children(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                self.record.unlink(missing_ok=True)
                process = subprocess.Popen([*self.command, '--worker'], stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=self.env,
                                           start_new_session=True)
                self.addCleanup(self.stop_process, process)
                deadline = time.monotonic() + 8
                while not self.record.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(self.record.exists())
                process.send_signal(sig)
                output, _ = process.communicate(timeout=8)
                self.assertEqual(process.returncode, 128 + sig, output.decode(errors='replace'))
                self.assert_workers_gone()

    def test_external_term_and_hup_reach_tty_payload_and_reap_children(self):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                self.record.unlink(missing_ok=True)
                process, master = self.start_terminal()
                self.read_until(process, master, 'READY')
                process.send_signal(sig)
                self.assertEqual(self.wait_terminal(process, master), 128 + sig)
                self.assert_workers_gone()


SIGNAL_WORKER = r'''
import os, pathlib, signal, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
def reap():
    child.terminate()
    child.wait(timeout=3)
def handle(sig, frame):
    if sig == signal.SIGINT and '--worker' not in sys.argv:
        print('CANCELLED', flush=True)
        return
    reap()
    raise SystemExit(128 + sig)
signal.signal(signal.SIGINT, handle)
signal.signal(signal.SIGTERM, handle)
signal.signal(signal.SIGHUP, handle)
pathlib.Path(os.environ['PAYLOAD_RECORD']).write_text(f'{os.getpid()} {child.pid}')
print('READY', flush=True)
if '--worker' in sys.argv:
    while True: time.sleep(.1)
else:
    while sys.stdin.readline().strip() != 'q': pass
    reap()
'''


if __name__ == '__main__':
    unittest.main()
