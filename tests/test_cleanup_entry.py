"""成员卸载入口：不查找 Python，不自行授权删除，校验并保留运行结果。"""
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
class CleanupEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="卸载 entry's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.kit = self.base / "完整工具's 目录"
        self.cleanup = self.kit / '.support/cleanup'
        self.cleanup.mkdir(parents=True)
        scripts = self.kit / '.support/scripts'
        scripts.mkdir()
        shutil.copy2(ROOT / 'dev-kit/.support/scripts/run-cleanup.sh', scripts / 'run-cleanup.sh')
        self.entry = scripts / 'run-tool.sh'
        source = ROOT / 'dev-kit/.support/scripts/run-tool.sh'
        if source.exists():
            shutil.copy2(source, self.entry)
        self.binary = self.cleanup / 'cleanup-macos'
        self.binary.write_text('#!/bin/bash\nprintf "%s\\0" "$#" "$@" > "$ENTRY_RECORD"\n'
                               'printf "fixture completed\\n"\nexit "${ENTRY_EXIT:-0}"\n')
        self.binary.chmod(0o755)
        self.manifest = self.cleanup / 'manifest.json'
        self.manifest.write_text(json.dumps({'schema': 1, 'sha256': hashlib.sha256(self.binary.read_bytes()).hexdigest()}))
        self.home = self.base / 'home'
        self.home.mkdir()
        self.record = self.base / 'arguments'
        self.env = {'HOME': str(self.home), 'PATH': '', 'ENTRY_RECORD': str(self.record), 'LC_ALL': 'C.UTF-8'}

    def run_entry(self, *args, extra=None):
        return subprocess.run(['/bin/bash', str(self.entry), 'uninstall', *args], env={**self.env, **(extra or {})},
                              input='', text=True, capture_output=True, timeout=5)

    def test_arguments_forwarded_with_no_python_or_path_dependencies(self):
        result = self.run_entry('--dry-run', '--gradle-dir', str(self.base / "Gradle's 6.8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record.read_bytes().decode().split('\0')[:-1],
                         ['3', '--dry-run', '--gradle-dir', str(self.base / "Gradle's 6.8")])

    def test_no_arguments_never_inject_apply_or_yes(self):
        result = self.run_entry()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record.read_bytes().decode().split('\0')[0], '0')

    def test_runtime_error_status_is_preserved_without_noninteractive_pause(self):
        result = self.run_entry('--dry-run', extra={'ENTRY_EXIT': '23'})
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertNotIn('按回车', result.stdout)

    def test_corruption_or_missing_runtime_stops_before_execution(self):
        self.binary.write_text('#!/bin/sh\nexit 0\n')
        result = self.run_entry('--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists())
        self.assertIn('校验', result.stdout + result.stderr)
        self.binary.unlink()
        result = self.run_entry()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('重新下载', result.stdout + result.stderr)

    def test_invalid_manifest_stops_before_execution(self):
        self.manifest.write_text('{"schema":1,"sha256":"invalid"}')
        result = self.run_entry('--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists())

    def test_removed_plain_mode_is_rejected_without_running_runtime(self):
        result=self.run_entry('--plain')
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.record.exists())


if __name__ == '__main__':
    unittest.main()
