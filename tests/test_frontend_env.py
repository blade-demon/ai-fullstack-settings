"""前端安装调度实际执行进程边界，底层安装以临时替身隔离。"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FrontendEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="前端流程's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.kit = self.base / '工具包'
        shutil.copytree(ROOT / 'dev-kit', self.kit)
        self.support = self.kit / '.support'
        self.home = self.base / 'home'; self.home.mkdir()
        self.record = self.base / 'calls'
        self.env = {'HOME': str(self.home), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                    'SHELL': '/bin/zsh', 'FRONTEND_TEST_RECORD': str(self.record)}
        for component, script in [('node', 'runtime/install-node.sh'), ('iterm2', 'software/install-iterm2.sh'),
                                  ('zsh', 'software/install-zsh.sh')]:
            target = self.support / 'scripts' / script
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('#!/bin/bash\nprintf "%s:%s\\n" ' + component + ' "$*" >> "$FRONTEND_TEST_RECORD"\n'
                              + 'echo "fixture ' + component + '"\n'
                              + ('exit "${NODE_TEST_EXIT:-0}"\n' if component == 'node' else 'exit 0\n'))

    def run_entry(self, *args, extra=None, menu=False, typed=''):
        entry = self.support / 'scripts/frontend-env.sh'
        return subprocess.run(['/bin/bash', str(entry), *args], env={**self.env, **(extra or {})},
                              input=typed, text=True, capture_output=True, timeout=10)

    def test_frontend_route_previews_all_without_creating_home_files(self):
        result = self.run_entry('--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record.read_text().splitlines(),
                         ['node:--version 14 --dry-run', 'iterm2:--dry-run', 'zsh:--dry-run'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_selected_node_version_only_runs_node_and_records_success(self):
        result = self.run_entry('--component', 'node', '--node-version', '22')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record.read_text().splitlines(), ['node:--version 22'])
        report = next(self.home.glob('Library/Logs/team-java-env/frontend/*/result.tsv'))
        self.assertIn('SUCCEEDED\t0\tnode\t22', report.read_text())

    def test_component_failure_is_logged_and_preserves_exit_code(self):
        result = self.run_entry(extra={'NODE_TEST_EXIT': '43'})
        self.assertEqual(result.returncode, 43, result.stdout + result.stderr)
        self.assertEqual(len(self.record.read_text().splitlines()), 3)
        report = next(self.home.glob('Library/Logs/team-java-env/frontend/*/result.tsv'))
        self.assertIn('FAILED\t43\tall\t14', report.read_text())
        self.assertNotIn('前端环境安装验证通过', result.stdout)

    def test_invalid_component_or_version_never_invokes_installer(self):
        for arguments in [('--component', 'invalid'), ('--node-version', '16'), ('--component', '')]:
            with self.subTest(arguments=arguments):
                result = self.run_entry(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.record.exists())



if __name__ == '__main__':
    unittest.main()
