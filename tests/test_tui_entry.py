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
        for relative in ('.support/scripts/run-tool.sh',
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
        self.fixture(self.scripts / 'manage-components.sh', 'install')
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
        return subprocess.run(['/bin/bash', *([str(self.scripts / 'run-tool.sh'), entry] if entry in ('install','uninstall') else [str(self.kit / entry)]), *args], input=input, text=True,
                              capture_output=True, timeout=5, env={**self.env, **(extra or {})})

    def terminal(self, entry, *args, extra=None, expect_pause=False):
        import pty
        master, slave = pty.openpty()
        process = subprocess.Popen(['/bin/bash', *([str(self.scripts / 'run-tool.sh'), entry] if entry in ('install','uninstall') else [str(self.kit / entry)]), *args], stdin=slave,
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

    def test_terminal_actions_open_correct_page_without_pause(self):
        for entry,page in [('install','install'),('uninstall','cleanup')]:
            code,output=self.terminal(entry)
            self.assertEqual(code,0,output)
            self.assertEqual(self.recorded(),['tui-'+self.arch,'4','--support-dir',str(self.support),'--page',page])

    def test_removed_modes_are_rejected_without_payload(self):
        for entry,args in [('install',('--plain',)),('install',('--frontend',)),('uninstall',('--plain','--dry-run'))]:
            result=self.non_tty(entry,*args)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse(self.record.exists())

    def test_explicit_components_in_tty_preselect_the_tui(self):
        code,output=self.terminal('install','--components','nvm','--node-version','22',extra={'ENTRY_EXIT':'23'})
        self.assertEqual(code,23,output)
        self.assertEqual(self.recorded(),['tui-'+self.arch,'8','--support-dir',str(self.support),'--page','install','--components','nvm','--node-version','22'])

    def test_business_preview_bypasses_tui_and_preserves_exit(self):
        result=self.non_tty('uninstall','--dry-run',extra={'ENTRY_EXIT':'19'})
        self.assertEqual(result.returncode,19,result.stderr)
        self.assertEqual(self.recorded(),['cleanup','1','--dry-run'])
        result=self.non_tty('install','--components','jdk','--dry-run')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.recorded(),['install','3','--components','jdk','--dry-run'])

    def test_literal_cleanup_path_is_not_evaluated(self):
        value=str(self.base/"path's $(not-a-command)")
        result=self.non_tty('uninstall','--profile',value,'--dry-run')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.recorded(),['cleanup','3','--profile',value,'--dry-run'])

    def test_tui_failure_exits_without_double_click_pause(self):
        for entry in ('install','uninstall'):
            code,output=self.terminal(entry,extra={'ENTRY_EXIT':'23'})
            self.assertEqual(code,23,output)
            self.assertEqual(self.recorded()[0],'tui-'+self.arch)

    def test_tui_corruption_stops_without_fallback(self):
        binary=self.tui/('team-dev-env-'+self.arch)
        binary.write_text('#!/bin/bash\nexit 0\n')
        code,output=self.terminal('install')
        self.assertNotEqual(code,0,output)
        self.assertFalse(self.record.exists())
        self.assertNotIn('--plain',output)

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
                self.assertNotIn('--plain', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
