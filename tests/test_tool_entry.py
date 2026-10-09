import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tool entry's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.scripts = self.base / 'scripts'
        self.scripts.mkdir()
        entry = ROOT / 'dev-kit/.support/scripts/run-tool.sh'
        if entry.exists():
            shutil.copy2(entry, self.scripts / 'run-tool.sh')
        self.record = self.base / 'args'
        self.env = {**os.environ, 'TOOL_RECORD': str(self.record)}
        for name in ('manage-components.sh', 'run-cleanup.sh'):
            (self.scripts / name).write_text('#!/bin/bash\nprintf "%s\\0" "' + name + '" "$@" > "$TOOL_RECORD"\nexit 37\n')

    def run_entry(self, *args):
        return subprocess.run(['/bin/bash', str(self.scripts / 'run-tool.sh'), *args],
                              env=self.env, text=True, capture_output=True, timeout=5)

    def test_action_is_consumed_and_arguments_are_preserved(self):
        for action, target in [('install', 'manage-components.sh'), ('uninstall', 'run-cleanup.sh')]:
            result = self.run_entry(action, '--components', 'jdk', '--dry-run')
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual(self.record.read_bytes().split(b'\0')[:-1],
                             [target.encode(), b'--components', b'jdk', b'--dry-run'])

    def test_removed_modes_never_start_a_payload(self):
        for args in [('frontend',), ('install', '--plain'), ('uninstall', '--frontend')]:
            self.assertEqual(self.run_entry(*args).returncode, 2)
        self.assertFalse(self.record.exists())


if __name__ == '__main__':
    unittest.main()
