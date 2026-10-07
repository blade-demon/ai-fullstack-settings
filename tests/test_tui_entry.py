"""Member TUI routing and integrity checks using inert dual-architecture fixtures."""
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'macOS member entry')
class TuiEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tui entry's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.kit = self.base / "工具包's 目录"
        self.support = self.kit / '.support'
        self.scripts = self.support / 'scripts'
        self.scripts.mkdir(parents=True)
        self.tui = self.support / 'tui'
        self.tui.mkdir()
        self.cleanup = self.support / 'cleanup'
        self.cleanup.mkdir()
        for relative in ('开始配置.command', '卸载环境.command',
                         '.support/scripts/run-tui.sh', '.support/scripts/run-cleanup.sh'):
            source = ROOT / 'dev-kit' / relative
            if source.exists():
                shutil.copy2(source, self.kit / relative)
        self.manifest = {'schema': 1, 'binaries': {}}
        for arch in ('arm64', 'amd64'):
            binary = self.tui / ('team-dev-env-' + arch)
            self.fixture(binary, 'tui-' + arch)
            self.manifest['binaries'][arch] = {'file': binary.name, 'sha256': self.sha(binary)}
        self.write_manifest()
        self.fixture(self.support / 'install_env.sh', 'install')
        self.fixture(self.support / 'menu.sh', 'menu')
        cleanup = self.cleanup / 'cleanup-macos'
        self.fixture(cleanup, 'cleanup')
        (self.cleanup / 'manifest.json').write_text(json.dumps({'schema': 1, 'sha256': self.sha(cleanup)}))
        self.arch = {'arm64': 'arm64', 'x86_64': 'amd64'}[os.uname().machine]
        self.record = self.base / 'record'
        self.home = self.base / 'home'
        self.home.mkdir()
        # An empty PATH proves the entry needs neither Go nor Python installed.
        self.env = {'HOME': str(self.home), 'PATH': '', 'ENTRY_RECORD': str(self.record), 'LC_ALL': 'C.UTF-8'}

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def fixture(self, path, name):
        path.write_text('#!/bin/bash\nprintf "%s\\0" "' + name + '" "$#" "$@" > "$ENTRY_RECORD"\n'
                        'printf "fixture completed\\n"\nexit "${ENTRY_EXIT:-0}"\n')
        path.chmod(0o755)

    def write_manifest(self):
        (self.tui / 'manifest.json').write_text(json.dumps(self.manifest))

    def recorded(self):
        return self.record.read_bytes().decode().split('\0')[:-1]

    def non_tty(self, entry, *args, extra=None, input=''):
        return subprocess.run(['/bin/bash', str(self.kit / entry), *args], input=input, text=True,
                              capture_output=True, timeout=5, env={**self.env, **(extra or {})})

    def terminal(self, entry, *args, extra=None, expect_pause=False):
        import pty
        master, slave = pty.openpty()
        process = subprocess.Popen(['/bin/bash', str(self.kit / entry), *args], stdin=slave,
                                   stdout=slave, stderr=slave, env={**self.env, **(extra or {})})
        data = b''
        saw_pause = False
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    data += chunk
                    if '按回车' in data.decode('utf-8', errors='replace') and not saw_pause:
                        saw_pause = True
                        self.assertIsNone(process.poll(), data.decode('utf-8', errors='replace'))
                        os.write(master, b'\n')
                if process.poll() is not None:
                    break
            self.assertEqual(saw_pause, expect_pause, data.decode('utf-8', errors='replace'))
            return process.wait(timeout=2), data.decode('utf-8', errors='replace')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            os.close(master)
            os.close(slave)

    def test_terminal_defaults_and_frontend_open_the_correct_page_without_pause(self):
        for entry, args, page in (('开始配置.command', (), 'home'),
                                  ('开始配置.command', ('--frontend',), 'frontend'),
                                  ('卸载环境.command', (), 'cleanup')):
            with self.subTest(entry=entry, page=page):
                code, output = self.terminal(entry, *args)
                self.assertEqual(code, 0, output)
                self.assertEqual(self.recorded(), ['tui-' + self.arch, '4', '--support-dir', str(self.support), '--page', page])

    def test_plain_is_removed_anywhere_and_never_touches_tui(self):
        shutil.rmtree(self.tui)
        project = str(self.base / "project's $(not-a-command)")
        result = self.non_tty('开始配置.command', '--project', project, '--plain', '--dry-run', '--plain')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['install', '3', '--project', project, '--dry-run'])
        code, output = self.terminal('开始配置.command', '--plain', '--frontend')
        self.assertEqual(code, 0, output)
        self.assertEqual(self.recorded(), ['install', '1', '--frontend'])
        result = self.non_tty('卸载环境.command', '--dry-run', '--plain')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['cleanup', '1', '--dry-run'])

    def test_plain_no_arguments_uses_bash_menu_even_with_pipe(self):
        result = self.non_tty('开始配置.command', '--plain', input='0\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['menu', '0'])

    def test_plain_cleanup_without_arguments_keeps_original_result_pause(self):
        code, output = self.terminal('卸载环境.command', '--plain', expect_pause=True)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.recorded(), ['cleanup', '0'])

    def test_explicit_business_parameters_keep_cli_and_exit_status(self):
        code, output = self.terminal('开始配置.command', '--frontend', '--component', 'node', extra={'ENTRY_EXIT': '23'})
        self.assertEqual(code, 23, output)
        self.assertEqual(self.recorded(), ['install', '3', '--frontend', '--component', 'node'])
        result = self.non_tty('卸载环境.command', '--plain', '--dry-run', extra={'ENTRY_EXIT': '19'})
        self.assertEqual(result.returncode, 19, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['cleanup', '1', '--dry-run'])

    def test_non_tty_defaults_do_not_enter_tui(self):
        result = self.non_tty('开始配置.command')
        self.assertEqual(result.returncode, 0)
        self.assertIn('命令行', result.stdout)
        self.assertFalse(self.record.exists())
        result = self.non_tty('卸载环境.command')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['cleanup', '0'])
        result = self.non_tty('开始配置.command', '--frontend')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ['install', '1', '--frontend'])

    def test_failed_tui_retains_status_and_keeps_terminal_open(self):
        for entry in ('开始配置.command', '卸载环境.command'):
            with self.subTest(entry=entry):
                code, output = self.terminal(entry, extra={'ENTRY_EXIT': '23'}, expect_pause=True)
                self.assertEqual(code, 23, output)
                self.assertEqual(self.recorded()[0], 'tui-' + self.arch)

    def test_tui_corruption_fails_without_running_or_falling_back(self):
        binary = self.tui / ('team-dev-env-' + self.arch)
        binary.write_text('#!/bin/bash\nexit 0\n')
        result = self.non_tty('.support/scripts/run-tui.sh', '--page', 'home')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists())
        self.assertIn('重新下载', result.stdout + result.stderr)
        self.assertIn('--plain', result.stdout + result.stderr)
        code, output = self.terminal('开始配置.command', expect_pause=True)
        self.assertNotEqual(code, 0, output)
        self.assertFalse(self.record.exists(), 'must not fall back to the installer')

    def test_tui_rejects_manifest_escape_invalid_schema_symlink_and_missing_runtime(self):
        binary = self.tui / ('team-dev-env-' + self.arch)
        manifest_path = self.tui / 'manifest.json'
        original_binary = binary.read_bytes()
        for damage in ('name', 'schema', 'hash', 'binary-symlink', 'manifest-symlink', 'manifest-missing', 'nonexecutable', 'missing'):
            with self.subTest(damage=damage):
                if binary.exists() or binary.is_symlink():
                    binary.unlink()
                binary.write_bytes(original_binary)
                binary.chmod(0o755)
                if manifest_path.exists() or manifest_path.is_symlink():
                    manifest_path.unlink()
                self.manifest['schema'] = 1
                self.manifest['binaries'][self.arch] = {'file': binary.name, 'sha256': self.sha(binary)}
                if damage == 'name':
                    self.manifest['binaries'][self.arch]['file'] = '../outside'
                elif damage == 'schema':
                    self.manifest['schema'] = 2
                elif damage == 'hash':
                    self.manifest['binaries'][self.arch]['sha256'] = 'invalid'
                elif damage == 'binary-symlink':
                    outside = self.base / 'outside-binary'
                    outside.write_bytes(original_binary)
                    outside.chmod(0o755)
                    binary.unlink()
                    binary.symlink_to(outside)
                elif damage == 'nonexecutable':
                    binary.chmod(0o644)
                elif damage == 'missing':
                    binary.unlink()
                self.write_manifest()
                if damage == 'manifest-symlink':
                    outside = self.base / 'outside-manifest'
                    shutil.copy2(manifest_path, outside)
                    manifest_path.unlink()
                    manifest_path.symlink_to(outside)
                elif damage == 'manifest-missing':
                    manifest_path.unlink()
                result = self.non_tty('.support/scripts/run-tui.sh', '--page', 'home')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.record.exists())
                self.assertIn('--plain', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
