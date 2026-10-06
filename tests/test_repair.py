"""真实修复调度与审计；安装动作使用可控进程替身，避免修改真实环境。"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="修复审计 ' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "kit/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "用户 home"; self.home.mkdir()
        self.project = self.base / "业务 project"; self.project.mkdir()
        (self.project / "build.gradle").write_text("// build fixture\n")
        self.history = self.home / "history"
        self.record = self.base / "actions"
        self.profile = self.home / ".zshrc"
        self.profile.write_text("# personal configuration\nexport PRIVATE_TOKEN='keep-secret'\n")
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "SHELL": "/bin/zsh", "LC_ALL": "C.UTF-8", "REPAIR_HISTORY_DIR": str(self.history),
                    "ACTIONS_RECORD": str(self.record), "JDK_AUTO_DETECT": "false"}
        actions = {
            "scripts/runtime/config-jdk.sh": "jdk",
            "scripts/runtime/install-gradle.sh": "gradle",
            "scripts/download-tools.sh": "idea",
            "scripts/software/install-idea-plugins.sh": "plugins",
            "scripts/runtime/verify-gradle.sh": "build",
        }
        for relative, name in actions.items():
            file = self.support / relative; file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('#!/bin/bash\nset -eu\n'
                            f'printf "%s\\n" "{name}:$*" >> "$ACTIONS_RECORD"\n'
                            f'if [ "${{FAIL_STAGE:-}}" = "{name}" ]; then echo "fixture failure"; exit 23; fi\n'
                            + ('mkdir -p "$HOME/.config/java-dev"\nprintf "export JAVA_HOME=/fixture/jdk8\\n" > "$HOME/.config/java-dev/env.sh"\nprintf "\\n# managed source\\n" >> "$HOME/.zshrc"\n' if name == 'jdk' else '')
                            + ('printf "BUILD SUCCESSFUL\\n"\n' if name == 'build' else f'echo "{name} verified"\n'))
        check = self.support / "scripts/check-env.sh"
        check.write_text('#!/bin/bash\necho "fixture scan"\nexit "${SCAN_EXIT:-0}"\n')
        verify = self.support / "scripts/verify-environment.sh"
        verify.write_text('#!/bin/bash\necho "runtime and IDE verified"\nexit "${VERIFY_EXIT:-0}"\n')

    def run_script(self, *args, extra=None):
        return subprocess.run(['/bin/bash', str(self.support/'scripts/repair-env.sh'), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, text=True,
                              capture_output=True, timeout=20)

    def latest(self):
        runs = sorted(p for p in self.history.iterdir() if p.is_dir())
        self.assertEqual(len(runs), 1)
        return runs[0]

    def test_project_success_requires_build_and_records_config_review(self):
        result = self.run_script('--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        actions = self.record.read_text()
        self.assertIn('build:--project', actions)
        run = self.latest()
        self.assertIn('PROJECT_BUILD_VERIFIED_IDEA_PENDING', (run/'result.tsv').read_text())
        report = (run/'report.md').read_text()
        self.assertIn(str(self.profile), report)
        self.assertIn('env.sh', report)
        self.assertIn('项目构建', report)
        self.assertNotIn('keep-secret', report)
        self.assertTrue((run/'config-changes.diff').is_file())
        self.assertNotIn('keep-secret', (run/'config-changes.diff').read_text())

    def test_terminal_build_success_keeps_unresolved_idea_sdk_pending(self):
        idea = self.project / '.idea'; idea.mkdir()
        (idea / 'misc.xml').write_text('<project><component name="ProjectRootManager" project-jdk-name="missing-sdk" /></project>')
        (idea / 'gradle.xml').write_text('<project><component name="GradleSettings"><option name="linkedExternalProjectsSettings"><GradleProjectSettings><option name="externalProjectPath" value="$PROJECT_DIR$" /><option name="gradleJvm" value="#PROJECT" /></GradleProjectSettings></option></component></project>')
        before = {p.name: p.read_bytes() for p in idea.iterdir()}
        result = self.run_script('--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = self.latest()
        self.assertIn('PROJECT_BUILD_VERIFIED_IDEA_PENDING', (run / 'result.tsv').read_text())
        self.assertIn('IDEA 项目配置预检\tpending', (run / 'steps.tsv').read_text())
        self.assertIn('IDEA 项目待配置', result.stdout)
        self.assertIn('Project Structure', result.stdout)
        self.assertNotIn('最终结果：修复及项目构建全部通过', result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in idea.iterdir()})

    def test_build_failure_is_final_failure_even_after_installations_succeed(self):
        result = self.run_script('--project', str(self.project), extra={'FAIL_STAGE': 'build'})
        self.assertNotEqual(result.returncode, 0)
        run = self.latest()
        self.assertIn('FAILED', (run/'result.tsv').read_text())
        self.assertIn('23', (run/'steps.tsv').read_text())
        self.assertNotIn('最终结果：修复及项目构建全部通过', result.stdout)
        self.assertTrue((run/'before-files.tsv').exists())
        self.assertTrue((run/'after-files.tsv').exists())

    def test_post_repair_verification_failure_cannot_succeed(self):
        result = self.run_script(extra={'VERIFY_EXIT': '9'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAILED', (self.latest()/'result.tsv').read_text())

    def test_report_write_failure_cannot_leave_success_metadata(self):
        plugin = self.support / 'scripts/software/install-idea-plugins.sh'
        plugin.write_text('#!/bin/bash\nmkdir "$REPAIR_RUN_DIR/report.md"\n')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAILED', (self.latest()/'result.tsv').read_text())
        self.assertNotIn('最终结果：环境验证通过', result.stdout)

    def test_existing_secret_without_final_newline_is_not_in_review_diff(self):
        self.profile.write_text("export PRIVATE_TOKEN='keep-secret'")
        jdk = self.support / 'scripts/runtime/config-jdk.sh'
        jdk.write_text('#!/bin/bash\nprintf "\\n# >>> team-java-env managed >>>\\n. /fixture/env.sh\\n# <<< team-java-env managed <<<\\n" >> "$HOME/.zshrc"\n')
        result = self.run_script('--scope', 'jdk')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        review = (self.latest() / 'config-changes.diff').read_text()
        self.assertIn('/fixture/env.sh', review)
        self.assertNotIn('keep-secret', review)
        self.assertNotIn('PRIVATE_TOKEN', review)

    def test_unclosed_managed_block_fails_review_without_exposing_personal_tail(self):
        self.profile.write_text("# >>> team-java-env managed >>>\nexport JAVA_HOME=/old\nexport PRIVATE_TOKEN='keep-secret'\n")
        result = self.run_script('--scope', 'jdk')
        self.assertNotEqual(result.returncode, 0)
        run = self.latest()
        self.assertIn('FAILED', (run/'result.tsv').read_text())
        self.assertIn('FAILED', (run/'report.md').read_text())
        self.assertNotIn('COMPONENT_VERIFIED', (run/'report.md').read_text())
        self.assertNotIn('keep-secret', (run/'config-changes.diff').read_text())

    def test_initial_snapshot_failure_records_failed_instead_of_running(self):
        bin_dir = self.base/'bin'; bin_dir.mkdir()
        cat = bin_dir/'cat'; cat.write_text('#!/bin/bash\nexit 41\n'); cat.chmod(0o755)
        result = self.run_script(extra={'PATH': str(bin_dir)+':'+self.env['PATH']})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAILED', (self.latest()/'result.tsv').read_text())
        self.assertFalse(self.record.exists())

    def test_no_project_is_explicitly_not_a_build_success(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('ENVIRONMENT_VERIFIED_NO_PROJECT', (self.latest()/'result.tsv').read_text())
        self.assertIn('未选择项目', result.stdout)
        self.assertNotIn('build:', self.record.read_text())

    def test_dry_run_does_not_install_or_create_history(self):
        before = self.profile.read_bytes()
        result = self.run_script('--dry-run', '--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('build', result.stdout)
        self.assertFalse(self.history.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self.profile.read_bytes(), before)

    def test_scoped_jdk_repair_does_not_install_other_components(self):
        result = self.run_script('--scope', 'jdk')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        actions = self.record.read_text()
        self.assertIn('jdk:', actions)
        self.assertNotIn('gradle:', actions)
        self.assertNotIn('idea:', actions)
        self.assertIn('COMPONENT_VERIFIED', (self.latest()/'result.tsv').read_text())


if __name__ == '__main__':
    unittest.main()
