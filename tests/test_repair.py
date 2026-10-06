"""真实修复调度与审计；安装动作使用可控进程替身，避免修改真实环境。"""
import base64
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
        # 同步核心会检查并运行 SDK；调度测试仅替换这个外部动作，保留真实审计。
        sync = self.support / 'scripts/runtime/config-idea-sdk.sh'
        sync.write_text('''#!/bin/bash
set -eu
source "$(dirname "$0")/../lib/common.sh"
printf 'sdk-sync:name=%s:%s\\n' "$IDEA_JDK_NAME" "$*" >> "$ACTIONS_RECORD"
[ "$#" -eq 2 ] && [ "$1" = --project ] || exit 24
if [ -n "${SDK_SYNC_FIXTURE_DIR:-}" ]; then
    mkdir -p "$IDEA_CONFIG_DIR/options" "$2/.idea"
    cp "$SDK_SYNC_FIXTURE_DIR/jdk.table.xml" "$IDEA_CONFIG_DIR/options/jdk.table.xml"
    cp "$SDK_SYNC_FIXTURE_DIR/misc.xml" "$2/.idea/misc.xml"
    cp "$SDK_SYNC_FIXTURE_DIR/gradle.xml" "$2/.idea/gradle.xml"
    cp "$SDK_SYNC_FIXTURE_DIR/module.iml" "$2/module.iml"
fi
if [ -n "${SDK_SYNC_EXIT:-}" ]; then exit "$SDK_SYNC_EXIT"; fi
[ -f "$2/.idea/misc.xml" ] && [ -f "$2/.idea/gradle.xml" ] || exit 2
echo 'sdk name synchronized'
''')

    def idea_xml(self, name='old-sdk', secret='private-before'):
        return {
            'jdk.table.xml': f'<application><component name="ProjectJdkTable"><jdk version="2"><name value="{name}" /><type value="JavaSDK" /><homePath value="/fixture/jdk8" /><additional><option name="token" value="{secret}" /></additional></jdk></component><component name="Other"><password value="{secret}" /></component></application>',
            'misc.xml': f'<project><component name="ProjectRootManager" project-jdk-name="{name}" project-jdk-type="JavaSDK" /><component name="Private"><option name="password" value="{secret}" /></component></project>',
            'gradle.xml': f'<project><component name="GradleSettings"><option name="linkedExternalProjectsSettings"><GradleProjectSettings><option name="externalProjectPath" value="$PROJECT_DIR$" /><option name="gradleJvm" value="{name}" /><option name="password" value="{secret}" /></GradleProjectSettings></option></component></project>',
            'module.iml': f'<module><component name="NewModuleRootManager"><orderEntry type="jdk" jdkName="{name}" jdkType="JavaSDK" /><option name="password" value="{secret}" /></component></module>',
        }

    def write_idea_xml(self, contents):
        config = self.home / 'idea-config'
        self.env['IDEA_CONFIG_DIR'] = str(config)
        (config / 'options').mkdir(parents=True, exist_ok=True)
        (self.project / '.idea').mkdir(exist_ok=True)
        paths = {'jdk.table.xml': config / 'options/jdk.table.xml',
                 'misc.xml': self.project / '.idea/misc.xml',
                 'gradle.xml': self.project / '.idea/gradle.xml',
                 'module.iml': self.project / 'module.iml'}
        for name, content in contents.items():
            paths[name].write_text(content)
        return paths

    def sdk_sync_changes(self, contents):
        directory = self.base / '同步结果'; directory.mkdir()
        for name, content in contents.items():
            (directory / name).write_text(content)
        return {'SDK_SYNC_FIXTURE_DIR': str(directory)}

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

    def test_sdk_sync_runs_after_plugins_before_project_build_with_default_name(self):
        self.write_idea_xml(self.idea_xml())
        result = self.run_script('--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actions = self.record.read_text()
        self.assertIn(f'sdk-sync:name=azul-1.8:--project {self.project}', actions)
        self.assertLess(actions.index('plugins:'), actions.index('sdk-sync:'))
        self.assertLess(actions.index('sdk-sync:'), actions.index('build:'))
        self.assertIn('IDEA SDK 名称同步\tverified\t0', (self.latest() / 'steps.tsv').read_text())

    def test_sdk_sync_uses_overridden_name(self):
        result = self.run_script('--scope', 'jdk', '--project', str(self.project),
                                 extra={'IDEA_JDK_NAME': 'team-java-8'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('sdk-sync:name=team-java-8:', self.record.read_text())

    def test_sdk_sync_pending_keeps_build_and_pending_result(self):
        (self.support / 'scripts/check-idea-project.sh').write_text('#!/bin/bash\nexit 0\n')
        result = self.run_script('--project', str(self.project), extra={'SDK_SYNC_EXIT': '2'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('IDEA SDK 名称同步\tpending\t2', (self.latest() / 'steps.tsv').read_text())
        self.assertIn('build:', self.record.read_text())
        self.assertIn('PROJECT_BUILD_VERIFIED_IDEA_PENDING', (self.latest() / 'result.tsv').read_text())

    def test_sdk_sync_failure_blocks_project_build(self):
        result = self.run_script('--project', str(self.project), extra={'SDK_SYNC_EXIT': '23'})
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertIn('IDEA SDK 名称同步\tfailed\t23', (self.latest() / 'steps.tsv').read_text())
        self.assertNotIn('build:', self.record.read_text())
        self.assertIn('FAILED', (self.latest() / 'result.tsv').read_text())

    def test_sdk_sync_only_runs_for_selected_project_and_supported_scopes(self):
        for scope in ['jdk', 'gradle', 'idea', 'plugins']:
            with self.subTest(scope=scope):
                if self.history.exists(): shutil.rmtree(self.history)
                self.record.unlink(missing_ok=True)
                result = self.run_script('--scope', scope, '--project', str(self.project))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual('sdk-sync:' in self.record.read_text(), scope != 'plugins')
        shutil.rmtree(self.history)
        self.record.unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('sdk-sync:', self.record.read_text())

    def test_sdk_sync_is_skipped_if_jdk_setup_failed(self):
        result = self.run_script('--project', str(self.project), extra={'FAIL_STAGE': 'jdk'})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sdk-sync:', self.record.read_text())
        self.assertNotIn('build:', self.record.read_text())

    def test_sdk_sync_dry_run_explains_name_without_writes(self):
        paths = self.write_idea_xml(self.idea_xml())
        before = {name: path.read_bytes() for name, path in paths.items()}
        result = self.run_script('--dry-run', '--project', str(self.project),
                                 extra={'IDEA_JDK_NAME': 'team-java-8'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('team-java-8', result.stdout)
        self.assertIn('SDK', result.stdout)
        self.assertFalse(self.record.exists())
        self.assertFalse(self.history.exists())
        self.assertEqual(before, {name: path.read_bytes() for name, path in paths.items()})

    def test_xml_audit_shares_only_sdk_fields_and_keeps_private_raw_backups(self):
        originals = self.idea_xml()
        # 目录和类型也发生变化，验证共享差异中只出现这些允许的字段。
        originals['jdk.table.xml'] = originals['jdk.table.xml'].replace('/fixture/jdk8', '/fixture/previous-jdk8').replace('JavaSDK', 'LegacySDK')
        paths = self.write_idea_xml(originals)
        extra = self.sdk_sync_changes(self.idea_xml('azul-1.8', 'private-after'))
        result = self.run_script('--scope', 'jdk', '--project', str(self.project), extra=extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = self.latest()
        review = (run / 'config-changes.diff').read_text()
        report = (run / 'report.md').read_text()
        before_manifest = (run / 'before-files.tsv').read_text()
        for name, path in paths.items():
            self.assertIn(str(path), before_manifest)
            self.assertIn(str(path), report)
            keys = [line.split('\t')[0] for line in before_manifest.splitlines()[1:]
                    if line.split('\t')[1] == str(path)]
            self.assertEqual(len(keys), 1)
            backup = run / 'before' / keys[0]
            self.assertEqual(backup.read_text(), originals[name])
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(run.stat().st_mode & 0o777, 0o700)
        self.assertIn('old-sdk', review)
        self.assertIn('azul-1.8', review)
        self.assertIn('/fixture/jdk8', review)
        self.assertIn('JavaSDK', review)
        for secret in ['private-before', 'private-after', 'password', 'token']:
            self.assertNotIn(secret, review)
            self.assertNotIn(secret, report)

    def test_xml_audit_is_limited_to_scopes_that_sync_sdk_names(self):
        paths = self.write_idea_xml(self.idea_xml())
        result = self.run_script('--scope', 'plugins', '--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = (self.latest() / 'before-files.tsv').read_text()
        for path in paths.values(): self.assertNotIn(str(path), manifest)

    def test_module_snapshot_discovery_failure_stops_repairs_and_records_failure(self):
        bin_dir = self.base / 'bin'; bin_dir.mkdir()
        finder = bin_dir / 'find'; finder.write_text('#!/bin/bash\nexit 41\n'); finder.chmod(0o755)
        result = self.run_script('--project', str(self.project),
                                 extra={'PATH': str(bin_dir) + ':' + self.env['PATH']})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists())
        self.assertIn('FAILED', (self.latest() / 'result.tsv').read_text())

    def test_unparseable_xml_before_does_not_prevent_failed_history(self):
        for broken in ['<project><secret>private-before',
                       '<!DOCTYPE project [<!ENTITY leak SYSTEM "file:///fixture/secret">]><project><secret>&leak;</secret></project>']:
            with self.subTest(xml=broken):
                if self.history.exists(): shutil.rmtree(self.history)
                originals = self.idea_xml()
                originals['misc.xml'] = broken
                self.write_idea_xml(originals)
                extra = {**self.sdk_sync_changes(self.idea_xml('azul-1.8', 'private-after')),
                         'SDK_SYNC_EXIT': '1'}
                result = self.run_script('--project', str(self.project), extra=extra)
                shutil.rmtree(Path(extra['SDK_SYNC_FIXTURE_DIR']))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                run = self.latest()
                self.assertIn('FAILED', (run / 'result.tsv').read_text())
                report = (run / 'report.md').read_text()
                self.assertIn('misc.xml', report)
                review = (run / 'config-changes.diff').read_text()
                self.assertIn('XML 无法安全解析', review)
                self.assertNotIn('private-before', review)
                self.assertNotIn('file:///fixture/secret', review)
                self.assertNotIn('build:', self.record.read_text())

    def test_audit_rejects_encoded_doctype_without_reading_entity_content(self):
        entity = self.base / 'harmless.txt'; entity.write_text('HARMLESS_EXTERNAL_ENTITY_CONTENT')
        body = f'<!DOCTYPE project [<!ENTITY leak SYSTEM "{entity.as_uri()}">]><project><component name="ProjectRootManager" project-jdk-name="old-sdk" project-jdk-type="JavaSDK" />&leak;</project>'
        utf7 = b'<?xml version="1.0" encoding="UTF-7"?>+' + base64.b64encode(body.encode('utf-16-be')).rstrip(b'=') + b'-'
        ibm037 = ('<?xml version="1.0" encoding="IBM037"?>' + body).encode('cp037')
        for encoded in [utf7, ibm037]:
            with self.subTest(encoded=encoded[:30]):
                if self.history.exists(): shutil.rmtree(self.history)
                paths = self.write_idea_xml(self.idea_xml())
                paths['misc.xml'].write_bytes(encoded)
                extra = {**self.sdk_sync_changes(self.idea_xml('azul-1.8', 'private-after')),
                         'SDK_SYNC_EXIT': '1'}
                result = self.run_script('--project', str(self.project), extra=extra)
                shutil.rmtree(Path(extra['SDK_SYNC_FIXTURE_DIR']))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                review = (self.latest() / 'config-changes.diff').read_text()
                self.assertIn('XML 无法安全解析', review)
                self.assertNotIn('HARMLESS_EXTERNAL_ENTITY_CONTENT', review + result.stdout + result.stderr)
                self.assertNotIn(entity.as_uri(), review)


if __name__ == '__main__':
    unittest.main()
