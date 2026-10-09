"""Component plans and queue isolation; never installs real software."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComponentPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="component's plan ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / 'support'
        shutil.copytree(ROOT / 'dev-kit/.support', self.support)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'SERVER_ADDR': 'team.invalid:8080'}
        for key in ('NVM_DIR', 'ZSH', 'JAVA_HOME', 'GRADLE_HOME', 'ENV_FILE', 'SHELL_PROFILE'):
            self.env.pop(key, None)
        self.env['JDK_AUTO_DETECT'] = 'false'

    def run_plan(self, *args):
        return subprocess.run(['/bin/bash', str(self.support / 'scripts/manage-components.sh'), *args],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def plan(self, *args):
        result = self.run_plan('--plan-json', *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_all_has_six_components_in_execution_order_without_writes(self):
        data = self.plan('--components', 'all')
        self.assertEqual([item['id'] for item in data['components']],
                         ['jdk', 'gradle', 'nvm', 'iterm2', 'oh-my-zsh', 'idea'])
        self.assertEqual(data['gradle_version'], '4.5.1')
        self.assertEqual(data['node_version'], '14')
        self.assertEqual(list(self.home.iterdir()), [])

    def test_gradle_adds_jdk_once_and_ignores_selection_order(self):
        data = self.plan('--components', 'idea,gradle,jdk,gradle', '--gradle-version', 'all')
        self.assertEqual([item['id'] for item in data['components']], ['jdk', 'gradle', 'idea'])
        self.assertEqual(data['gradle_version'], 'all')

    def test_nvm_only_is_explicit_and_does_not_add_other_components(self):
        data = self.plan('--components', 'nvm', '--node-version', 'none')
        self.assertEqual([item['id'] for item in data['components']], ['nvm'])
        self.assertEqual(data['node_version'], 'none')

    def test_invalid_scope_or_version_fails_without_side_effects(self):
        for args in [('--components', 'all,jdk'), ('--components', 'jdk,'),
                     ('--components', 'frontend'), ('--components', 'nvm', '--node-version', '16'),
                     ('--components', 'jdk', '--node-version', '22'), ('--plain',)]:
            with self.subTest(args=args):
                result = self.run_plan('--plan-json', *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_noninteractive_install_requires_explicit_scope(self):
        result = self.run_plan()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_failed_component_preserves_status_and_independent_queue_order(self):
        record = self.base / 'calls'
        self.env['QUEUE_RECORD'] = str(record)
        for name, script in [('nvm','runtime/install-node.sh'),('iterm2','software/install-iterm2.sh'),
                             ('oh-my-zsh','software/install-zsh.sh')]:
            path=self.support / 'scripts' / script
            path.write_text('#!/bin/bash\ncase " $* " in *" --dry-run "*|*" --check-only "*) exit 0;; esac\nprintf "%s\\n" ' + name + ' >> "$QUEUE_RECORD"\nexit ' + ('37' if name=='nvm' else '0') + '\n')
        result=self.run_plan('--components','oh-my-zsh,iterm2,nvm','--node-version','none')
        self.assertEqual(result.returncode,37,result.stdout+result.stderr)
        self.assertEqual(record.read_text().splitlines(),['nvm','iterm2','oh-my-zsh'])
        reports=list(self.home.glob('Library/Logs/team-java-env/components/*/result.tsv'))
        self.assertEqual(len(reports),1)
        self.assertIn('FAILED',reports[0].read_text())

    def test_dependency_failure_skips_gradle_but_runs_independent_component(self):
        record=self.base / 'calls'; self.env['QUEUE_RECORD']=str(record)
        for name, script in [('jdk','runtime/config-jdk.sh'),('gradle','runtime/install-gradle.sh'),('iterm2','software/install-iterm2.sh')]:
            (self.support/'scripts'/script).write_text('#!/bin/bash\ncase " $* " in *" --dry-run "*|*" --check-only "*) exit 0;; esac\nprintf "%s\\n" '+name+' >> "$QUEUE_RECORD"\nexit '+('39' if name=='jdk' else '0')+'\n')
        result=self.run_plan('--components','gradle,iterm2')
        self.assertEqual(result.returncode,39,result.stdout+result.stderr)
        self.assertEqual(record.read_text().splitlines(),['jdk','iterm2'])

    def test_bad_gradle_target_blocks_jdk_before_install_or_report(self):
        record = self.base / 'calls'
        self.env['QUEUE_RECORD'] = str(record)
        (self.support / 'scripts/runtime/config-jdk.sh').write_text(
            '#!/bin/bash\ncase " $* " in *" --dry-run "*|*" --check-only "*) exit 0;; esac\n'
            'echo changed >> "$QUEUE_RECORD"\nexit 39\n')
        target = self.home / '.local/share/java-dev/gradle-4.5.1'
        target.parent.mkdir(parents=True)
        target.write_text('user file')
        result = self.run_plan('--components', 'gradle')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(record.exists(), result.stdout + result.stderr)
        self.assertEqual(target.read_text(), 'user file')
        self.assertFalse((self.home / 'Library/Logs').exists())

    def test_static_plan_discloses_state_ownership_and_default_change_without_sdk(self):
        default = self.home / '.config/java-dev/gradle-default'
        default.parent.mkdir(parents=True)
        default.write_text('4.5.1\n')
        nvm = self.home / '.nvm'
        (nvm / 'alias').mkdir(parents=True)
        (nvm / 'alias/default').write_text('v16.20.2\n')
        (nvm / 'nvm.sh').write_text('echo loaded > "$HOME/loaded"; exit 91\n')
        data = self.plan('--components', 'gradle,nvm', '--gradle-version', '6.8', '--node-version', 'all')
        by_id = {item['id']: item for item in data['components']}
        for item in by_id.values():
            self.assertIn('status', item)
            self.assertIn('ownership', item)
        self.assertEqual(by_id['gradle']['default_before'], '4.5.1')
        self.assertEqual(by_id['gradle']['default_after'], '6.8')
        self.assertEqual(by_id['nvm']['default_before'], 'v16.20.2')
        self.assertEqual(by_id['nvm']['default_after'], 'v14.21.3')
        self.assertIn('失效', by_id['nvm']['default_impact'])
        self.assertFalse((self.home / 'loaded').exists())
        self.assertFalse((self.home / '.zshrc').exists())

    def test_cancelled_queue_records_current_and_unstarted_components(self):
        for name, script in [('nvm', 'runtime/install-node.sh'), ('iterm2', 'software/install-iterm2.sh')]:
            (self.support / 'scripts' / script).write_text(
                '#!/bin/bash\ncase " $* " in *" --dry-run "*|*" --check-only "*) exit 0;; esac\nexit '
                + ('130' if name == 'nvm' else '0') + '\n')
        self.env['TEAM_TUI_EVENTS'] = '1'
        result = self.run_plan('--components', 'nvm,iterm2', '--node-version', 'none')
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        report = next(self.home.glob('Library/Logs/team-java-env/components/*/steps.tsv')).read_text()
        self.assertIn('nvm\tcancelled\t130', report)
        self.assertIn('iterm2\tskipped\t130', report)
        self.assertIn('component\tnvm\tcancelled', result.stdout)
        self.assertIn('component\titerm2\tskipped', result.stdout)

    def test_each_gradle_target_conflict_blocks_queue_before_jdk(self):
        record = self.base / 'calls'
        self.env['QUEUE_RECORD'] = str(record)
        (self.support / 'scripts/runtime/config-jdk.sh').write_text(
            '#!/bin/bash\ncase " $* " in *" --dry-run "*|*" --check-only "*) exit 0;; esac\n'
            'echo changed >> "$QUEUE_RECORD"\nexit 39\n')
        target = self.home / '.local/share/java-dev/gradle-6.8'
        target.parent.mkdir(parents=True)
        for shape in ('symlink', 'incomplete', 'wrong-launcher'):
            with self.subTest(shape=shape):
                if shape == 'symlink': target.symlink_to(self.base, target_is_directory=True)
                else:
                    (target / 'bin').mkdir(parents=True)
                    (target / 'lib').mkdir()
                    binary = target / 'bin/gradle'; binary.write_text('#!/bin/sh\necho Gradle 4.5.1\n'); binary.chmod(0o755)
                    if shape == 'wrong-launcher': (target / 'lib/gradle-launcher-4.5.1.jar').write_text('jar')
                result = self.run_plan('--components', 'gradle', '--gradle-version', 'all')
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(record.exists(), result.stdout + result.stderr)
                if target.is_symlink(): target.unlink()
                else: shutil.rmtree(target)
        self.assertFalse((self.home / 'Library/Logs').exists())

    def test_wrong_kind_marker_is_not_reported_as_managed(self):
        target = self.home / '.nvm'; target.mkdir()
        (target / '.team-frontend-env-install.json').write_text(
            '{"schema":1,"tool":"team-frontend-env","kind":"iterm2"}')
        data = self.plan('--components', 'nvm', '--node-version', 'none')
        self.assertEqual(data['components'][0]['ownership'], '来源未知')

    def test_mixed_gradle_sources_are_not_claimed_as_all_managed(self):
        base = self.home / '.local/share/java-dev'
        for version in ('4.5.1', '6.8'):
            (base / f'gradle-{version}').mkdir(parents=True)
        (base / 'gradle-6.8/.team-java-env-install.json').write_text(
            '{"schema":1,"tool":"team-java-env","kind":"gradle"}')
        data = self.plan('--components', 'gradle', '--gradle-version', 'all')
        gradle = next(item for item in data['components'] if item['id'] == 'gradle')
        self.assertIn('混合', gradle['ownership'])


if __name__ == '__main__':
    unittest.main()
