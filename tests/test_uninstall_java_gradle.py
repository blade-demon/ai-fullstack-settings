"""清理工具只操作临时安装和配置，不卸载本机软件。"""
import contextlib
import importlib.util
import io
import inspect
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/uninstall_java_gradle.py"
LEGACY_PATH_FIXTURE = r'''_java_dev_prefer_jdk() {
    local remaining="${PATH-}" entry cleaned='' separator='' more
    while :; do
        case "$remaining" in
            *:*) entry="${remaining%%:*}"; remaining="${remaining#*:}"; more=1 ;;
            *) entry="$remaining"; more=0 ;;
        esac
        if [ "$entry" != "$JAVA_HOME/bin" ]; then
            cleaned="${cleaned}${separator}${entry}"
            separator=':'
        fi
        [ "$more" -eq 1 ] || break
    done
    export PATH="$JAVA_HOME/bin${separator}${cleaned}"
}
_java_dev_prefer_jdk
unset -f _java_dev_prefer_jdk
'''


class UninstallJavaGradleTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        redirect = contextlib.redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.assertTrue(SCRIPT.is_file(), "尚未提供 JDK/Gradle 清理工具")
        spec = importlib.util.spec_from_file_location("cleanup_tool", SCRIPT)
        self.tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.tool
        spec.loader.exec_module(self.tool)
        self.temp = tempfile.TemporaryDirectory(prefix="清理 SDK's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "用户 home"
        self.home.mkdir()
        self.system = self.base / "Library/Java/JavaVirtualMachines"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}

    def cleaner(self, **kwargs):
        return self.tool.Cleaner(self.home, system_jvms=self.system,
                                 environ=self.env, **kwargs)

    def mark_owned(self, path, kind):
        self.write(path / ".team-java-env-install.json", json.dumps({"schema": 1, "tool": "team-java-env", "kind": kind}))

    def jdk(self, path, bundle=False, owned=True):
        home = path / "Contents/Home" if bundle else path
        (home / "bin").mkdir(parents=True)
        for binary in ("java", "javac"):
            (home / "bin" / binary).write_text("must never execute\n")
        if owned:
            self.mark_owned(path, "jdk")
        return path

    def gradle(self, path, owned=True):
        (path / "bin").mkdir(parents=True)
        (path / "lib").mkdir()
        (path / "bin/gradle").write_text("must never execute\n")
        (path / "lib/gradle-launcher-8.10.jar").write_text("fixture")
        if owned:
            self.mark_owned(path, "gradle")
        return path

    def test_unmarked_sdks_and_original_references_are_preserved_even_in_default_install_area(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk21", owned=False)
        gradle = self.gradle(self.home / ".local/share/java-dev/gradle-8.10", owned=False)
        body = 'export JAVA_HOME="{}"\nexport GRADLE_HOME="{}"\nexport PATH="$JAVA_HOME/bin:$GRADLE_HOME/bin:/keep:$PATH"\n'.format(jdk, gradle)
        profile = self.write(self.home / ".zshrc", body)
        self.cleaner(extra_jdks=[jdk], extra_gradles=[gradle]).scan().apply()
        self.assertTrue(jdk.exists())
        self.assertTrue(gradle.exists())
        self.assertEqual(profile.read_text(), body)

    def test_external_linked_parent_and_original_jdk_and_gradle_paths_do_not_block_owned_cleanup(self):
        external = self.base / "external SDKs"
        jdk = self.jdk(external / "jdk21", owned=False)
        gradle = self.gradle(external / "gradle8", owned=False)
        alias = self.home / "sdk-link"
        alias.symlink_to(external)
        body = 'export JAVA_HOME="{}"\nexport GRADLE_HOME="{}"\nexport PATH="{}/bin:$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"\n'.format(alias / "jdk21", alias / "gradle8", alias / "jdk21")
        profile = self.write(self.home / ".zshrc", body)
        owned = self.jdk(self.home / ".local/share/java-dev/jdk8")
        self.cleaner().scan().apply()
        self.assertFalse(owned.exists())
        self.assertTrue(jdk.exists())
        self.assertTrue(gradle.exists())
        self.assertTrue(alias.is_symlink())
        self.assertEqual(profile.read_text(), body)

    def test_external_references_outside_managed_block_in_env_file_are_preserved(self):
        external = self.jdk(self.home / "existing/jdk21", owned=False)
        retained = 'export JAVA_HOME="{}"\nexport PATH="$JAVA_HOME/bin:$PATH"\n'.format(external)
        environment = self.write(self.home / ".config/java-dev/env.sh", retained + '# >>> team-java-env managed >>>\nexport GRADLE_HOME=/old/gradle\n# <<< team-java-env managed <<<\n')
        self.cleaner().scan().apply()
        self.assertEqual(environment.read_text(), retained)
        self.assertTrue(external.exists())

    def test_external_variable_binding_is_preserved_after_removing_later_tool_override(self):
        external = self.jdk(self.home / "existing/jdk21", owned=False)
        owned = self.jdk(self.home / ".local/share/java-dev/jdk8")
        retained = 'export JAVA_HOME="{}"\nexport PATH="$JAVA_HOME/bin:$PATH"\n'.format(external)
        profile = self.write(self.home / ".zshrc", 'export JAVA_HOME="{}"\n# >>> team-java-env managed >>>\nexport JAVA_HOME="{}"\n# <<< team-java-env managed <<<\nexport PATH="$JAVA_HOME/bin:$PATH"\n'.format(external, owned))
        self.cleaner().scan().apply()
        self.assertEqual(profile.read_text(), retained)
        self.assertTrue(external.exists())
        self.assertFalse(owned.exists())

    def test_idea_jdk_json_sidecar_is_identified_and_preserved_with_external_jdk(self):
        jdk = self.jdk(self.home / "Library/Java/JavaVirtualMachines/azul-1.8.0_504", owned=False)
        metadata = self.write(jdk.parent / ".azul-1.8.0_504.intellij", json.dumps({
            "jdk_version": "1.8.0_504", "jdk_version_major": 8, "packages": [], "product": "ZULU", "vendor": "Azul"}))
        plan = self.cleaner().scan()
        self.assertEqual(plan.blockers, [])
        self.assertIn("IDEA JDK 辅助", plan.describe())
        plan.apply()
        self.assertTrue(jdk.exists())
        self.assertTrue(metadata.exists())

    def test_invalid_ownership_marker_never_authorizes_sdk_deletion(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8", owned=False)
        for body in ('not-json', '{"schema":1,"tool":"different-tool","kind":"jdk"}',
                     '{"schema":1,"tool":"team-java-env","kind":"gradle"}'):
            with self.subTest(body=body):
                self.write(jdk / ".team-java-env-install.json", body)
                self.cleaner().scan().apply()
                self.assertTrue(jdk.exists())

    def test_known_legacy_function_is_removed_while_reused_sdk_and_original_shell_config_are_kept(self):
        reused = self.jdk(self.home / "Library/Java/JavaVirtualMachines/azul8", bundle=True, owned=False)
        original = self.jdk(self.home / "existing/jdk21", owned=False)
        environment = self.write(self.home / ".config/java-dev/env.sh",
            '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="{}"\n'.format(reused / "Contents/Home") + LEGACY_PATH_FIXTURE +
            '\n# >>> team-java-env managed >>>\nexport JAVA_HOME="{}"\n# <<< team-java-env managed <<<\n'.format(reused / "Contents/Home"))
        retained = 'export JAVA_HOME="{}"\nexport PATH="{}/bin:$PATH"\n'.format(original, original)
        profile = self.write(self.home / ".zshrc", retained + '# >>> team-java-env managed >>>\n. "{}"\n# <<< team-java-env managed <<<\n'.format(environment))
        self.cleaner().scan().apply()
        self.assertFalse(environment.exists())
        self.assertEqual(profile.read_text(), retained)
        self.assertTrue(reused.exists())
        self.assertTrue(original.exists())

    def test_modified_legacy_function_is_left_intact_and_blocks_unsafe_rewrite(self):
        owned = self.jdk(self.home / ".local/share/java-dev/jdk8")
        changed = LEGACY_PATH_FIXTURE.replace("    while :; do", "    printf 'custom behaviour'\n    while :; do")
        body = 'export JAVA_HOME="{}"\n'.format(owned) + changed
        environment = self.write(self.home / ".config/java-dev/env.sh", body)
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner().scan().apply()
        self.assertEqual(environment.read_text(), body)
        self.assertTrue(owned.exists())

    def test_ownership_marker_changed_after_preview_blocks_deletion(self):
        owned = self.jdk(self.home / ".local/share/java-dev/jdk8")
        plan = self.cleaner().scan()
        (owned / ".team-java-env-install.json").write_text("{}")
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(owned.exists())

    def test_wrapper_install_root_marker_is_used_when_java_home_points_to_nested_home(self):
        root = self.home / "custom/jdk8"
        self.jdk(root / "vendor.jdk", bundle=True, owned=False)
        self.mark_owned(root, "jdk")
        self.env["JAVA_HOME"] = str(root / "vendor.jdk/Contents/Home")
        plan = self.cleaner().scan()
        self.assertIn(root, {item.path for item in plan.removals})
        plan.apply()
        self.assertFalse(root.exists())

    def test_empty_trailing_java_heading_is_removed_but_other_comments_remain(self):
        profile = self.write(self.home / ".zshrc", '# 其他设置\nexport EDITOR=vim\n\n# Java 开发环境\n\n')
        self.cleaner().scan().apply()
        self.assertEqual(profile.read_text(), '# 其他设置\nexport EDITOR=vim\n\n\n')

    def test_java_heading_with_retained_configuration_is_preserved(self):
        jdk = self.jdk(self.home / "existing/jdk21", owned=False)
        body = '# Java 开发环境\nexport JAVA_HOME="{}"\nexport PATH="$JAVA_HOME/bin:$PATH"\n'.format(jdk)
        profile = self.write(self.home / ".zshrc", body)
        self.cleaner().scan().apply()
        self.assertEqual(profile.read_text(), body)

    def test_recognized_old_tool_backup_and_empty_config_directory_are_removed(self):
        backup = self.write(self.home / ".config/java-dev/env.sh.bak",
                            '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="/external/jdk8"\n' + LEGACY_PATH_FIXTURE)
        plan = self.cleaner().scan()
        self.assertIn(str(backup), plan.describe())
        plan.apply()
        self.assertFalse(backup.exists())
        self.assertFalse(backup.parent.exists())
        self.assertTrue(backup.parent.parent.is_dir())

    def test_backup_with_user_content_keeps_config_directory(self):
        backup = self.write(self.home / ".config/java-dev/env.sh.bak",
                            '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="/external/jdk8"\n' + LEGACY_PATH_FIXTURE + 'export KEEP_ME=yes\n')
        before = backup.read_bytes()
        self.cleaner().scan().apply()
        self.assertEqual(backup.read_bytes(), before)
        self.assertTrue(backup.parent.is_dir())

    def test_legacy_assignment_with_attached_user_command_is_never_removed(self):
        for operator in (";", "&", "|", ">", "<"):
            with self.subTest(operator=operator):
                body = '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="/external/jdk8"' + operator + 'user_setup\n' + LEGACY_PATH_FIXTURE
                backup = self.write(self.home / ".config/java-dev/env.sh.bak", body)
                plan = self.cleaner().scan()
                self.assertNotIn(backup, {item.path for item in plan.removals})
                plan.apply()
                self.assertEqual(backup.read_text(), body)
                environment = self.write(backup.with_suffix(""), body)
                with self.assertRaises(self.tool.CleanupError):
                    self.cleaner().scan().apply()
                self.assertEqual(environment.read_text(), body)
                environment.unlink()

    def test_empty_tool_install_directory_is_removed_after_owned_sdk_cleanup(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        self.cleaner().scan().apply()
        self.assertFalse(jdk.parent.exists())
        self.assertTrue(jdk.parent.parent.is_dir())

    def test_unmarked_sdk_keeps_tool_install_parent_directory(self):
        gradle = self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1", owned=False)
        self.cleaner().scan().apply()
        self.assertTrue(gradle.is_dir())
        self.assertTrue(gradle.parent.is_dir())

    def test_new_file_added_after_preview_prevents_empty_directory_removal(self):
        root = self.home / ".config/java-dev"
        root.mkdir(parents=True)
        plan = self.cleaner().scan()
        keep = self.write(root / "keep.txt", "new user file")
        plan.apply()
        self.assertEqual(keep.read_text(), "new user file")

    def test_known_backup_changed_after_preview_is_not_deleted(self):
        backup = self.write(self.home / ".config/java-dev/env.sh.bak",
                            '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="/external/jdk8"\n' + LEGACY_PATH_FIXTURE)
        plan = self.cleaner().scan()
        backup.write_text("new user configuration\n")
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertEqual(backup.read_text(), "new user configuration\n")

    def write(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path


    def test_preview_has_no_side_effects_and_discovers_all_versions(self):
        jdks = [self.jdk(self.home / ".local/share/java-dev/jdk8"),
                self.jdk(self.home / "Library/Java/JavaVirtualMachines/jdk-21.jdk", True),
                self.jdk(self.home / ".sdkman/candidates/java/17.0.1-zulu"),
                self.jdk(self.home / ".jdks/corretto-11")]
        gradles = [self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1"),
                   self.gradle(self.home / ".sdkman/candidates/gradle/8.10")]
        profile = self.write(self.home / ".zshrc", 'export JAVA_HOME="{}"\nexport EDITOR=vim\n'.format(jdks[0]))
        before = profile.read_bytes()
        plan = self.cleaner().scan()
        self.assertEqual(set(jdks + gradles), {item.path for item in plan.removals})
        self.assertIn(".zshrc", plan.describe())
        self.assertEqual(profile.read_bytes(), before)
        self.assertTrue(all(path.exists() for path in jdks + gradles))
        self.assertFalse((self.home / "Library/Logs/team-java-env/cleanup").exists())

    def test_apply_removes_versions_without_backups_and_preserves_other_settings(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        gradle = self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1")
        body = ('export EDITOR=vim\nexport JAVA_HOME="' + str(jdk) + '"\n'
                'export GRADLE_HOME="' + str(gradle) + '"\n'
                'export PATH="/custom/bin:$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"\n'
                '# >>> team-java-env managed >>>\n. "$HOME/.config/java-dev/env.sh"\n'
                '# <<< team-java-env managed <<<\n')
        profile = self.write(self.home / ".zshrc", body)
        profile.chmod(0o640)
        env_file = self.write(self.home / ".config/java-dev/env.sh",
                              'export JAVA_HOME="{}"\nexport KEEP_ME=yes\n'.format(jdk))
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertFalse(gradle.exists())
        self.assertEqual(profile.read_text(), 'export EDITOR=vim\nexport PATH="/custom/bin:$PATH"\n. "$HOME/.config/java-dev/env.sh"\n')
        self.assertEqual(profile.stat().st_mode & 0o777, 0o640)
        self.assertEqual(env_file.read_text(), "export KEEP_ME=yes\n")
        records = self.home / "Library/Logs/team-java-env/cleanup"
        self.assertFalse(list(records.glob("*/files")))
        self.assertFalse(list(self.home.rglob("*.bak")))
        reports = list(records.glob("*/report.txt"))
        self.assertEqual(len(reports), 1)
        self.assertNotIn("KEEP_ME=yes", reports[0].read_text())
        self.assertNotIn("export EDITOR=vim", reports[0].read_text())
        first_mtime = profile.stat().st_mtime_ns
        self.cleaner().scan().apply()
        self.assertEqual(profile.stat().st_mtime_ns, first_mtime)

    def test_empty_dedicated_environment_files_are_deleted_but_shared_shell_file_is_kept(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        gradle = self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1")
        jdk_file = self.write(self.home / ".config/java-dev/jdk.sh", 'export JAVA_HOME="{}"\n'.format(jdk))
        gradle_file = self.write(self.home / ".config/java-dev/gradle.sh", 'export GRADLE_HOME="{}"\n'.format(gradle))
        profile = self.write(self.home / ".zshrc", 'export JAVA_HOME="{}"\n'.format(jdk))
        self.cleaner().scan().apply()
        self.assertFalse(jdk_file.exists())
        self.assertFalse(gradle_file.exists())
        self.assertTrue(profile.is_file())
        self.assertEqual(profile.read_text(), "")

    def test_unrelated_settings_inside_managed_shell_block_are_preserved(self):
        profile = self.write(self.home / ".zshrc",
                             'export BEFORE=yes\n'
                             '# >>> team-java-env managed >>>\n'
                             'export JAVA_HOME=/old/jdk\n'
                             'export EDITOR=vim\n'
                             'alias ll="ls -la"\n'
                             'export PATH="/custom/bin:$JAVA_HOME/bin:$PATH"\n'
                             '. "$HOME/.config/java-dev/env.sh"\n'
                             '# <<< team-java-env managed <<<\n'
                             'export AFTER=yes\n')
        self.cleaner().scan().apply()
        self.assertEqual(profile.read_text(), 'export BEFORE=yes\nexport EDITOR=vim\nalias ll="ls -la"\nexport PATH="/custom/bin:$PATH"\nexport AFTER=yes\n')

    def test_complex_mixed_settings_inside_managed_shell_block_abort_without_changes(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        body = '# >>> team-java-env managed >>>\nexport JAVA_HOME=/jdk EDITOR=vim\n# <<< team-java-env managed <<<\n'
        profile = self.write(self.home / ".zshrc", body)
        plan = self.cleaner().scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertEqual(profile.read_text(), body)
        self.assertTrue(jdk.exists())

    def test_shared_shell_profile_is_not_treated_as_dedicated_env_file_when_paths_overlap(self):
        self.env["ENV_FILE"] = str(self.home / ".zshrc")
        profile = self.write(self.home / ".zshrc", '# >>> team-java-env managed >>>\nexport EDITOR=vim\nexport JAVA_HOME=/old/jdk\n# <<< team-java-env managed <<<\n')
        self.cleaner().scan().apply()
        self.assertTrue(profile.is_file())
        self.assertEqual(profile.read_text(), "export EDITOR=vim\n")

    def test_shared_shell_profile_remains_present_when_overlapping_env_cleanup_leaves_it_empty(self):
        self.env["ENV_FILE"] = str(self.home / ".zshrc")
        profile = self.write(self.home / ".zshrc", '# >>> team-java-env managed >>>\nexport JAVA_HOME=/old/jdk\n# <<< team-java-env managed <<<\n')
        self.cleaner().scan().apply()
        self.assertTrue(profile.is_file())
        self.assertEqual(profile.read_text(), "")

    def test_explicit_shared_profiles_preserve_unrelated_block_settings_even_as_env_files(self):
        for setting in ("SHELL_PROFILE", "--profile"):
            with self.subTest(setting=setting):
                path = self.home / ("custom-shell-" + setting + ".sh")
                self.env["ENV_FILE"] = str(path)
                if setting == "SHELL_PROFILE":
                    self.env["SHELL_PROFILE"] = str(path)
                    profiles = []
                else:
                    self.env.pop("SHELL_PROFILE", None)
                    profiles = [path]
                self.write(path, '# >>> team-java-env managed >>>\nexport JAVA_HOME=/old/jdk\nexport EDITOR=vim\n# <<< team-java-env managed <<<\n')
                self.cleaner(extra_profiles=profiles).scan().apply()
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_text(), "export EDITOR=vim\n")

    def test_loading_shared_configuration_preserves_its_unrelated_settings(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        shared = self.home / "custom-shell.sh"
        self.env["ENV_FILE"] = str(shared)
        self.env["SHELL_PROFILE"] = str(shared)
        self.write(shared, 'export JAVA_HOME="{}"\nexport EDITOR=vim\n'.format(jdk))
        profile = self.write(self.home / ".zshrc", '. "{}"\n'.format(shared))
        self.cleaner().scan().apply()
        self.assertEqual(shared.read_text(), "export EDITOR=vim\n")
        self.assertEqual(profile.read_text(), '. "{}"\n'.format(shared))
        loaded = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", '. "$1"; printf "%s" "$EDITOR"', "test", str(profile)],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(loaded.stdout, "vim")

    def test_loading_environment_file_with_retained_user_settings_is_preserved(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        environment = self.write(self.home / ".config/java-dev/env.sh", 'export JAVA_HOME="{}"\nexport KEEP_ME=yes\n'.format(jdk))
        profile = self.write(self.home / ".zshrc", '. "{}"\n'.format(environment))
        self.cleaner().scan().apply()
        self.assertEqual(environment.read_text(), "export KEEP_ME=yes\n")
        self.assertEqual(profile.read_text(), '. "{}"\n'.format(environment))

    def test_source_chain_is_removed_when_all_dedicated_environment_files_become_empty(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        module = self.write(self.home / "jdk.sh", 'export JAVA_HOME="{}"\n'.format(jdk))
        environment = self.write(self.home / "custom-env.sh", '. "{}"\n'.format(module))
        self.env["ENV_FILE"] = str(environment)
        profile = self.write(self.home / ".zshrc", 'export EDITOR=vim\n. "{}"\n'.format(environment))
        self.cleaner().scan().apply()
        self.assertFalse(module.exists())
        self.assertFalse(environment.exists())
        self.assertEqual(profile.read_text(), "export EDITOR=vim\n")

    def test_sdkman_installs_links_and_other_tools_are_preserved(self):
        version = self.jdk(self.home / ".sdkman/candidates/java/17-zulu", owned=False)
        current = version.parent / "current"
        current.symlink_to(version)
        external = self.jdk(self.base / "外部 JDK", owned=False)
        alias = version.parent / "local-jdk"
        alias.symlink_to(external)
        maven = self.write(self.home / ".sdkman/candidates/maven/3.9/bin/mvn", "keep")
        self.cleaner().scan().apply()
        self.assertTrue(version.exists())
        self.assertTrue(current.is_symlink())
        self.assertTrue(alias.is_symlink())
        self.assertTrue(external.exists())
        self.assertEqual(maven.read_text(), "keep")

    def test_unknown_directory_and_idea_embedded_runtime_are_preserved(self):
        unknown = self.write(self.home / ".local/share/java-dev/jdk-unknown/keep", "keep")
        self.mark_owned(unknown.parent, "jdk")
        jbr = self.jdk(self.home / "Applications/IntelliJ IDEA CE.app/Contents/jbr")
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner(extra_jdks=[jbr]).scan()
        self.assertTrue(jbr.exists())
        self.assertEqual(unknown.read_text(), "keep")
        plan = self.cleaner().scan()
        self.assertIn("jdk-unknown", plan.describe())
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertEqual(unknown.read_text(), "keep")

    def test_dangerous_custom_paths_and_symlinked_parent_are_rejected(self):
        for path in (Path("/"), self.home, self.home / ".local", self.base):
            with self.subTest(path=path), self.assertRaises(self.tool.CleanupError):
                self.cleaner(extra_jdks=[path]).scan()
        external = self.jdk(self.base / "external/jdk8")
        link = self.home / ".local/share/java-dev"
        link.parent.mkdir(parents=True)
        link.symlink_to(external.parent)
        plan = self.cleaner().scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(external.exists())

    def test_mixed_parent_directories_are_not_deleted_as_sdks_or_caches(self):
        mixed_jdk = self.base / "混合 SDK 与资料"
        self.jdk(mixed_jdk / "jdk-21")
        self.write(mixed_jdk / "keep.txt", "keep")
        self.mark_owned(mixed_jdk, "jdk")
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner(extra_jdks=[mixed_jdk]).scan()
        for name in ("Desktop", "Documents", "Downloads"):
            broad = self.home / name
            self.jdk(broad / "jdk21")
            with self.subTest(name=name), self.assertRaises(self.tool.CleanupError):
                self.cleaner(extra_jdks=[broad]).scan()
        cache = self.base / "混合缓存与资料"
        self.write(cache / "gradle.properties", "fixture")
        keep = self.write(cache / "个人资料.txt", "keep")
        self.env["GRADLE_USER_HOME"] = str(cache)
        plan = self.cleaner(remove_caches=True).scan()
        plan.apply()
        self.assertEqual(keep.read_text(), "keep")

    def test_configuration_file_in_shared_gradle_cache_is_preserved(self):
        cache = self.home / ".gradle"
        profile = self.write(cache / "init.d/settings.sh", "export JAVA_HOME=/jdk\n")
        plan = self.cleaner(remove_caches=True, extra_profiles=[profile]).scan()
        plan.apply()
        self.assertTrue(cache.exists())
        self.assertEqual(profile.read_text(), "export JAVA_HOME=/jdk\n")

    def test_home_alias_of_sdkman_managed_version_does_not_make_parent_configuration_broken(self):
        # 同一目录的 PATH 可能写成 $HOME；静态识别不应求值 Shell。
        jdk = self.jdk(self.home / ".sdkman/candidates/java/21-zulu")
        profile = self.write(self.home / ".zshrc", 'export JAVA_HOME="$HOME/.sdkman/candidates/java/21-zulu"\nexport PATH="$HOME/.sdkman/candidates/java/21-zulu/bin:/keep:$PATH"\n')
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertEqual(profile.read_text(), 'export PATH="/keep:$PATH"\n')

    def test_custom_installs_and_cache_in_managed_blocks_are_discovered_without_loading_environment(self):
        jdk = self.jdk(self.home / "额外SDK/jdk-21")
        gradle = self.gradle(self.home / "额外SDK/gradle-8")
        cache = self.home / "额外缓存"
        properties = self.write(cache / "gradle.properties", "private=value\n")
        for filename, assignments in (("jdk.sh", 'export JAVA_HOME="{}"\n'.format(jdk)),
                                       ("gradle.sh", 'export GRADLE_HOME="{}"\nexport GRADLE_USER_HOME="{}"\n'.format(gradle, cache))):
            self.write(self.home / ".config/java-dev" / filename,
                       "# >>> team-java-env managed >>>\n" + assignments + "# <<< team-java-env managed <<<\n")
        plan = self.cleaner(remove_caches=True).scan()
        self.assertTrue({jdk, gradle}.issubset({item.path for item in plan.removals}))
        self.assertNotIn(cache, {item.path for item in plan.removals})
        plan.apply()
        self.assertFalse(jdk.exists())
        self.assertFalse(gradle.exists())
        self.assertEqual(properties.read_text(), "private=value\n")

    def test_finder_metadata_in_sdk_container_is_ignored_without_blocking_cleanup(self):
        jdk = self.jdk(self.home / ".jdks/temurin21")
        metadata = self.write(jdk.parent / ".DS_Store", "finder metadata")
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertTrue(metadata.exists())




    def test_system_installs_require_explicit_scope_and_are_listed_in_preview(self):
        system = self.jdk(self.system / "temurin-17.jdk", True)
        plan = self.cleaner().scan()
        self.assertIn(str(system), plan.describe())
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(system.exists())
        self.cleaner(include_system=True).scan().apply()
        self.assertFalse(system.exists())

    def test_shared_gradle_cache_and_configuration_are_preserved_even_with_cache_flag(self):
        properties = self.write(self.home / ".gradle/gradle.properties", "private=secret\n")
        distribution = self.write(self.home / ".gradle/wrapper/dists/gradle-8/x/bin/gradle", "fixture")
        self.cleaner().scan().apply()
        self.assertTrue(distribution.exists())
        self.assertTrue(properties.exists())
        self.cleaner(remove_caches=True).scan().apply()
        self.assertTrue(distribution.exists())
        self.assertEqual(properties.read_text(), "private=secret\n")
        records = self.home / "Library/Logs/team-java-env/cleanup"
        self.assertFalse(list(records.glob("*/files")))
        self.assertFalse(list(records.glob("*/report.txt")))

    def test_complex_or_malformed_configuration_aborts_before_any_deletion(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        for body in ('export JAVA_HOME="{}"; echo keep\n'.format(jdk),
                     'if true; then\n  export JAVA_HOME="{}"\nfi\n'.format(jdk),
                     '# >>> team-java-env managed >>>\nexport JAVA_HOME=/jdk\n'):
            with self.subTest(body=body):
                profile = self.write(self.home / ".zshrc", body)
                plan = self.cleaner().scan()
                with self.assertRaises(self.tool.CleanupError):
                    plan.apply()
                self.assertEqual(profile.read_text(), body)
                self.assertTrue(jdk.exists())

    def test_changed_or_replaced_config_is_rejected_before_deletion(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        profile = self.write(self.home / ".zshrc", 'export JAVA_HOME="{}"\n'.format(jdk))
        plan = self.cleaner().scan()
        profile.write_text("export JAVA_HOME=/new-jdk\n")
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(jdk.exists())
        self.assertEqual(profile.read_text(), "export JAVA_HOME=/new-jdk\n")

    def test_shared_assignment_and_pipeline_are_not_discarded_with_java_settings(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        for body in ('export JAVA_HOME="{}" EDITOR=vim\n'.format(jdk),
                     'JAVA_HOME="{}" echo keep\n'.format(jdk), 'export JAVA_HOME="{}" | cat\n'.format(jdk)):
            with self.subTest(body=body):
                profile = self.write(self.home / ".zshrc", body)
                plan = self.cleaner().scan()
                with self.assertRaises(self.tool.CleanupError):
                    plan.apply()
                self.assertTrue(jdk.exists())
                self.assertEqual(profile.read_text(), body)

    def test_complex_quoted_path_and_conditional_source_are_preserved_and_block_cleanup(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        for body in ('export PATH="$(printf \'%s:%s\' "$JAVA_HOME/bin" /unrelated/bin):$PATH"\n',
                     'export PATH="`some-path-command`:$JAVA_HOME/bin:$PATH"\n',
                     'if true; then\n. "$HOME/.config/java-dev/env.sh"\nfi\n'):
            with self.subTest(body=body):
                body = 'export JAVA_HOME="{}"\n'.format(jdk) + body
                profile = self.write(self.home / ".zshrc", body)
                plan = self.cleaner().scan()
                with self.assertRaises(self.tool.CleanupError):
                    plan.apply()
                self.assertTrue(jdk.exists())
                self.assertEqual(profile.read_text(), body)

    def test_literal_path_before_custom_sdk_assignment_is_cleaned_without_running_config(self):
        jdk = self.jdk(self.home / "自定义 JDK")
        profile = self.write(self.home / ".zshrc",
                             'export PATH="{}/bin:/custom/bin:$PATH"\n'
                             'export JAVA_HOME="{}"\n'
                             'touch "{}/MUST_NOT_EXIST"\n'.format(jdk, jdk, self.home))
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertEqual(profile.read_text(), 'export PATH="/custom/bin:$PATH"\ntouch "{}/MUST_NOT_EXIST"\n'.format(self.home))
        self.assertFalse((self.home / "MUST_NOT_EXIST").exists())

    def test_asdf_and_mise_installs_and_original_selections_are_preserved(self):
        java = self.jdk(self.home / ".asdf/installs/java/temurin-21", owned=False)
        gradle = self.gradle(self.home / ".local/share/mise/installs/gradle/8.10", owned=False)
        asdf = self.write(self.home / ".tool-versions", "java temurin-21\ngradle 8.10\nnodejs 22.0\n")
        mise = self.write(self.home / ".config/mise/config.toml", '[tools]\njava = "21"\ngradle = "8.10"\nnode = "22"\n\n[settings]\nexperimental = true\n')
        self.cleaner().scan().apply()
        self.assertTrue(java.exists())
        self.assertTrue(gradle.exists())
        self.assertEqual(asdf.read_text(), "java temurin-21\ngradle 8.10\nnodejs 22.0\n")
        self.assertEqual(mise.read_text(), '[tools]\njava = "21"\ngradle = "8.10"\nnode = "22"\n\n[settings]\nexperimental = true\n')

    def test_launchctl_java_environment_is_outside_static_shell_cleanup(self):
        # 只验证本工具不通过执行配置中的命令修改桌面会话。
        profile = self.write(self.home / ".zshrc", "launchctl setenv JAVA_HOME /jdk\n")
        plan = self.cleaner().scan()
        plan.apply()
        self.assertEqual(profile.read_text(), "launchctl setenv JAVA_HOME /jdk\n")



    def test_cli_requires_explicit_apply_and_confirmation(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        args = [sys.executable, str(SCRIPT)]
        preview = subprocess.run(args, env=self.env, text=True, capture_output=True)
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        self.assertTrue(jdk.exists())
        declined = subprocess.run(args + ["--apply"], env=self.env,
                                  input="NO\n", text=True, capture_output=True)
        self.assertNotEqual(declined.returncode, 0)
        self.assertTrue(jdk.exists())
        invalid = subprocess.run(args + ["--yes"], env=self.env, text=True, capture_output=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertTrue(jdk.exists())

    def test_preview_does_not_invoke_external_package_or_sdk_commands(self):
        binaries = self.base / "外部命令"
        record = self.base / "unexpected-command"
        for name in ("brew", "java", "javac", "gradle"):
            binary = self.write(binaries / name, '#!/bin/sh\nprintf "%s\\n" "$0" >> "$COMMAND_RECORD"\nexit 99\n')
            binary.chmod(0o755)
        env = {**self.env, "PATH": str(binaries) + ":/usr/bin:/bin", "COMMAND_RECORD": str(record)}
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"], env=env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(record.exists())
        self.assertTrue(jdk.exists())

    def idea(self, path, identifier="com.jetbrains.intellij.ce"):
        (path / "Contents/MacOS").mkdir(parents=True)
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": identifier, "CFBundleExecutable": "idea",
            "CFBundleShortVersionString": "2024.3.7.1"}))
        (path / "Contents/MacOS/idea").write_text("must never execute\n")
        self.jdk(path / "Contents/jbr")
        return path

    def idea_cleaner(self, **kwargs):
        self.assertIn("include_idea", inspect.signature(self.tool.Cleaner).parameters,
                      "清理工具尚未支持 IDEA")
        return self.cleaner(include_idea=True, system_apps=self.base / "系统 Applications",
                            process_reader=lambda: [], **kwargs)

    def test_idea_cleanup_is_opt_in_and_preview_never_changes_app_or_plugins(self):
        app = self.idea(self.home / "Applications/IntelliJ IDEA CE.app")
        plugin = self.write(self.home / "Library/Application Support/JetBrains/IdeaIC2024.3/plugins/demo/lib/demo.jar", "plugin")
        original = self.cleaner().scan()
        self.assertNotIn(app, {item.path for item in original.removals})
        plan = self.idea_cleaner().scan()
        self.assertIn(app, {item.path for item in plan.removals})
        self.assertIn("IDEA", plan.describe())
        self.assertTrue(app.exists())
        self.assertTrue(plugin.exists())
        self.assertFalse((self.home / "Library/Logs/team-java-env/cleanup").exists())

    def test_all_idea_versions_plugins_and_config_are_deleted_without_backups(self):
        apps = [self.idea(self.home / "Applications/IntelliJ IDEA CE.app"),
                self.idea(self.home / "Applications/Idea Ultimate 2026.app", "com.jetbrains.intellij")]
        configs = [self.write(self.home / "Library/Application Support/JetBrains" / version / "plugins/demo/lib/demo.jar", "plugin")
                   for version in ("IdeaIC2024.3", "IntelliJIdea2026.1")]
        old_plugin = self.write(self.home / "Library/Application Support/IntelliJIdea2019.3/plugins/demo/lib/demo.jar", "old plugin")
        preferences = self.write(self.home / "Library/Preferences/com.jetbrains.intellij.ce.plist", "private IDEA settings")
        webstorm = self.idea(self.home / "Applications/WebStorm.app", "com.jetbrains.WebStorm")
        keep = self.write(self.home / "Library/Application Support/JetBrains/WebStorm2026.1/options/editor.xml", "keep")
        project = self.write(self.home / "业务项目/.idea/workspace.xml", "keep project")
        self.idea_cleaner().scan().apply()
        self.assertTrue(all(not app.exists() for app in apps))
        self.assertTrue(all(not config.exists() for config in configs))
        self.assertFalse(old_plugin.exists())
        self.assertFalse(preferences.exists())
        self.assertTrue(webstorm.exists())
        self.assertEqual(keep.read_text(), "keep")
        self.assertEqual(project.read_text(), "keep project")
        self.assertFalse(list((self.home / "Library/Logs/team-java-env/cleanup").glob("*/files")))

    def test_idea_cache_logs_and_local_history_use_explicit_cache_flag(self):
        cache = self.write(self.home / "Library/Caches/JetBrains/IdeaIC2024.3/LocalHistory/changes", "local history")
        log = self.write(self.home / "Library/Logs/JetBrains/IdeaIC2024.3/idea.log", "log")
        self.idea_cleaner().scan().apply()
        self.assertTrue(cache.exists())
        self.assertTrue(log.exists())
        self.idea_cleaner(remove_caches=True).scan().apply()
        self.assertFalse(cache.exists())
        self.assertFalse(log.exists())

    def test_system_idea_requires_explicit_system_scope(self):
        app = self.idea(self.base / "系统 Applications/IntelliJ IDEA.app", "com.jetbrains.intellij")
        plan = self.idea_cleaner().scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(app.exists())
        self.idea_cleaner(include_system=True).scan().apply()
        self.assertFalse(app.exists())

    def test_running_idea_blocks_all_mutations_and_is_never_killed(self):
        self.assertIn("include_idea", inspect.signature(self.tool.Cleaner).parameters)
        app = self.idea(self.home / "Applications/IntelliJ IDEA CE.app")
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        cleaner = self.cleaner(include_idea=True, system_apps=self.base / "系统 Applications",
                               process_reader=lambda: [str(app / "Contents/MacOS/idea")])
        with self.assertRaises(self.tool.CleanupError):
            cleaner.scan().apply()
        self.assertTrue(app.exists())
        self.assertTrue(jdk.exists())
        self.assertFalse((self.home / "Library/Logs/team-java-env/cleanup").exists())

    def test_idea_symlink_config_and_unsafe_custom_plugins_are_preserved(self):
        external = self.write(self.base / "external/config/options.xml", "keep")
        link = self.home / "Library/Application Support/JetBrains/IdeaIC2024.3"
        link.parent.mkdir(parents=True)
        link.symlink_to(external.parent)
        with self.assertRaises(self.tool.CleanupError):
            self.idea_cleaner().scan().apply()
        self.assertEqual(external.read_text(), "keep")
        link.unlink()
        with self.assertRaises(self.tool.CleanupError):
            self.idea_cleaner(extra_idea_plugins=[self.home]).scan()
        unknown = self.write(self.home / "Documents/custom-plugins/个人资料.txt", "keep")
        with self.assertRaises(self.tool.CleanupError):
            self.idea_cleaner(extra_idea_plugins=[unknown.parent]).scan()
        self.assertEqual(unknown.read_text(), "keep")

    def test_shared_configuration_root_cannot_be_used_as_empty_idea_plugins_directory(self):
        config = self.home / ".config"
        config.mkdir()
        with self.assertRaises(self.tool.CleanupError):
            self.idea_cleaner(extra_idea_plugins=[config]).scan()
        self.assertTrue(config.exists())

    def test_idea_app_link_is_removed_without_deleting_external_application(self):
        app = self.idea(self.base / "外部/IntelliJ IDEA.app", "com.jetbrains.intellij")
        alias = self.home / "Applications/IntelliJ IDEA.app"
        alias.parent.mkdir()
        alias.symlink_to(app)
        self.idea_cleaner().scan().apply()
        self.assertFalse(alias.is_symlink())
        self.assertTrue(app.exists())

    def test_idea_runtime_inherited_as_java_home_is_removed_with_its_app(self):
        app = self.idea(self.home / "Applications/IntelliJ IDEA CE.app")
        self.env["JAVA_HOME"] = str(app / "Contents/jbr")
        self.idea_cleaner().scan().apply()
        self.assertFalse(app.exists())

    def test_legacy_hidden_idea_config_is_removed_but_cache_requires_cache_flag(self):
        settings = self.write(self.home / ".IdeaIC2019.3/config/options/editor.xml", "settings")
        plugin = self.write(self.home / ".IdeaIC2019.3/config/plugins/demo/lib/demo.jar", "plugin")
        history = self.write(self.home / ".IdeaIC2019.3/system/LocalHistory/history", "history")
        self.idea_cleaner().scan().apply()
        self.assertFalse(settings.exists())
        self.assertFalse(plugin.exists())
        self.assertTrue(history.exists())
        self.idea_cleaner(remove_caches=True).scan().apply()
        self.assertFalse(history.exists())

    def test_custom_idea_app_and_plugins_can_be_deleted_without_touching_parent(self):
        app = self.idea(self.home / "工具/IDEA自定义.app")
        plugins = self.home / "工具/custom-plugins"
        self.write(plugins / "demo/lib/demo.jar", "plugin")
        keep = self.write(plugins.parent / "keep", "keep")
        self.idea_cleaner(extra_idea_apps=[app], extra_idea_plugins=[plugins]).scan().apply()
        self.assertFalse(app.exists())
        self.assertFalse(plugins.exists())
        self.assertEqual(keep.read_text(), "keep")

    def test_broken_unrelated_plist_is_ignored_but_broken_idea_bundle_is_rejected(self):
        self.write(self.home / "Applications/Unrelated.app/Contents/Info.plist", "<not valid xml")
        valid = self.idea(self.home / "Applications/IntelliJ IDEA CE.app")
        self.idea_cleaner().scan().apply()
        self.assertFalse(valid.exists())
        broken = self.write(self.home / "Applications/IntelliJ IDEA Broken.app/Contents/Info.plist", "<not valid xml")
        plan = self.idea_cleaner().scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(broken.exists())




if __name__ == "__main__":
    unittest.main()
