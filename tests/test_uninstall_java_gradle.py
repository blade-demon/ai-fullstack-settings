"""清理工具只操作临时安装、配置及假 Homebrew，不卸载本机软件。"""
import contextlib
import importlib.util
import io
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/uninstall_java_gradle.py"


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
                                 brews=(), environ=self.env, **kwargs)

    def jdk(self, path, bundle=False):
        home = path / "Contents/Home" if bundle else path
        (home / "bin").mkdir(parents=True)
        for binary in ("java", "javac"):
            (home / "bin" / binary).write_text("must never execute\n")
        return path

    def gradle(self, path):
        (path / "bin").mkdir(parents=True)
        (path / "lib").mkdir()
        (path / "bin/gradle").write_text("must never execute\n")
        (path / "lib/gradle-launcher-8.10.jar").write_text("fixture")
        return path

    def write(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def fake_brew(self, path, body):
        prefix = shlex.quote(str(path.parent.parent))
        path = self.write(path, '#!/bin/sh\nif [ "$1" = --prefix ]; then printf "%s\\n" ' + prefix + '; exit 0; fi\n' + body)
        path.chmod(0o755)
        return path

    def test_preview_has_no_side_effects_and_discovers_all_versions(self):
        jdks = [self.jdk(self.home / ".local/share/java-dev/jdk8"),
                self.jdk(self.home / "Library/Java/JavaVirtualMachines/jdk-21.jdk", True),
                self.jdk(self.home / ".sdkman/candidates/java/17.0.1-zulu"),
                self.jdk(self.home / ".jdks/corretto-11")]
        gradles = [self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1"),
                   self.gradle(self.home / ".sdkman/candidates/gradle/8.10")]
        profile = self.write(self.home / ".zshrc", "export JAVA_HOME='/old/jdk'\nexport EDITOR=vim\n")
        before = profile.read_bytes()
        plan = self.cleaner().scan()
        self.assertEqual(set(jdks + gradles), {item.path for item in plan.removals})
        self.assertIn(".zshrc", plan.describe())
        self.assertEqual(profile.read_bytes(), before)
        self.assertTrue(all(path.exists() for path in jdks + gradles))
        self.assertFalse((self.home / "Library/Logs/team-java-env/cleanup").exists())

    def test_apply_removes_versions_backs_up_configs_and_preserves_other_settings(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        gradle = self.gradle(self.home / ".local/share/java-dev/gradle-4.5.1")
        body = ('export EDITOR=vim\nexport JAVA_21_HOME="/old/jdk21"\n'
                'export GRADLE_8_10_HOME="/old/gradle"\n'
                'export PATH="/custom/bin:$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"\n'
                '# >>> team-java-env managed >>>\n. "$HOME/.config/java-dev/env.sh"\n'
                '# <<< team-java-env managed <<<\n')
        profile = self.write(self.home / ".zshrc", body)
        profile.chmod(0o640)
        env_file = self.write(self.home / ".config/java-dev/env.sh",
                              "export JAVA_HOME='/old/jdk'\nexport KEEP_ME=yes\n")
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertFalse(gradle.exists())
        self.assertEqual(profile.read_text(), 'export EDITOR=vim\nexport PATH="/custom/bin:$PATH"\n')
        self.assertEqual(profile.stat().st_mode & 0o777, 0o640)
        self.assertEqual(env_file.read_text(), "export KEEP_ME=yes\n")
        backups = list((self.home / "Library/Logs/team-java-env/cleanup").glob("*/files/**/.zshrc"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), body)
        first_mtime = profile.stat().st_mtime_ns
        self.cleaner().scan().apply()
        self.assertEqual(profile.stat().st_mtime_ns, first_mtime)

    def test_sdkman_links_are_unlinked_without_deleting_external_targets_or_other_tools(self):
        version = self.jdk(self.home / ".sdkman/candidates/java/17-zulu")
        current = version.parent / "current"
        current.symlink_to(version)
        external = self.jdk(self.base / "外部 JDK")
        alias = version.parent / "local-jdk"
        alias.symlink_to(external)
        maven = self.write(self.home / ".sdkman/candidates/maven/3.9/bin/mvn", "keep")
        self.cleaner().scan().apply()
        self.assertFalse(version.exists())
        self.assertFalse(current.is_symlink())
        self.assertFalse(alias.is_symlink())
        self.assertTrue(external.exists())
        self.assertEqual(maven.read_text(), "keep")

    def test_unknown_directory_and_idea_embedded_runtime_are_preserved(self):
        unknown = self.write(self.home / ".local/share/java-dev/jdk-unknown/keep", "keep")
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
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertEqual(keep.read_text(), "keep")

    def test_configuration_file_inside_removal_target_does_not_fail_after_sdk_deletion(self):
        cache = self.home / ".gradle"
        profile = self.write(cache / "init.d/settings.sh", "export JAVA_HOME=/jdk\n")
        plan = self.cleaner(remove_caches=True, extra_profiles=[profile]).scan()
        plan.apply()
        self.assertFalse(cache.exists())

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
        properties = self.write(cache / "gradle.properties", "keep-backup=true\n")
        for filename, assignments in (("jdk.sh", 'export JAVA_HOME="{}"\n'.format(jdk)),
                                       ("gradle.sh", 'export GRADLE_HOME="{}"\nexport GRADLE_USER_HOME="{}"\n'.format(gradle, cache))):
            self.write(self.home / ".config/java-dev" / filename,
                       "# >>> team-java-env managed >>>\n" + assignments + "# <<< team-java-env managed <<<\n")
        plan = self.cleaner(remove_caches=True).scan()
        self.assertTrue({jdk, gradle, cache}.issubset({item.path for item in plan.removals}))
        plan.apply()
        self.assertFalse(jdk.exists())
        self.assertFalse(gradle.exists())
        self.assertFalse(properties.exists())

    def test_finder_metadata_in_sdk_container_is_ignored_without_blocking_cleanup(self):
        jdk = self.jdk(self.home / ".jdks/temurin21")
        metadata = self.write(jdk.parent / ".DS_Store", "finder metadata")
        self.cleaner().scan().apply()
        self.assertFalse(jdk.exists())
        self.assertTrue(metadata.exists())

    def test_missing_homebrew_package_registration_blocks_direct_sdk_deletion(self):
        prefix = self.base / "brew-prefix"
        jdk = self.jdk(prefix / "Cellar/unknown-jdk/21")
        brew = self.fake_brew(prefix / "bin/brew", "exit 0\n")
        self.env["JAVA_HOME"] = str(jdk)
        plan = self.tool.Cleaner(self.home, system_jvms=self.system, brews=[brew],
                                 environ=self.env).scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(jdk.exists())

    def test_graalvm_homebrew_variants_are_included_without_running_java(self):
        brew = self.fake_brew(self.base / "brew",
                          'if [ "$2" = --formula ]; then echo graalvm;\n'
                          'else printf "graalvm-jdk17\\ngraalvm-community-jdk21\\ngraalvm-ce-java17\\n"; fi\n')
        plan = self.tool.Cleaner(self.home, system_jvms=self.system, brews=[brew],
                                 environ=self.env).scan()
        self.assertEqual({command[-1] for command, _ in plan.commands},
                         {"graalvm", "graalvm-jdk17", "graalvm-community-jdk21", "graalvm-ce-java17"})

    def test_homebrew_alias_uses_real_prefix_and_cleans_absolute_jdk_bin_path(self):
        prefix = self.base / "brew-prefix"
        jdk = self.jdk(prefix / "Cellar/openjdk@21/21.0/libexec/openjdk.jdk", True)
        brew = self.fake_brew(prefix / "bin/brew", 'if [ "$2" = --formula ]; then echo openjdk@21; fi\n')
        alias = self.home / "bin/brew"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(brew)
        self.env["JAVA_HOME"] = str(jdk / "Contents/Home")
        profile = self.write(self.home / ".zshrc", 'export PATH="{}/Contents/Home/bin:/keep:$PATH"\n'.format(jdk))
        plan = self.tool.Cleaner(self.home, system_jvms=self.system, brews=[alias], environ=self.env).scan()
        self.assertEqual(plan.blockers, [])
        self.assertEqual([edit.after.decode() for edit in plan.edits if edit.path == profile], ['export PATH="/keep:$PATH"\n'])
        self.assertNotIn(jdk, {item.path for item in plan.removals})

    def test_system_installs_require_explicit_scope_and_are_listed_in_preview(self):
        system = self.jdk(self.system / "temurin-17.jdk", True)
        plan = self.cleaner().scan()
        self.assertIn(str(system), plan.describe())
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(system.exists())
        self.cleaner(include_system=True).scan().apply()
        self.assertFalse(system.exists())

    def test_cache_is_opt_in_and_user_configuration_is_backed_up(self):
        properties = self.write(self.home / ".gradle/gradle.properties", "private=secret\n")
        distribution = self.write(self.home / ".gradle/wrapper/dists/gradle-8/x/bin/gradle", "fixture")
        self.cleaner().scan().apply()
        self.assertTrue(distribution.exists())
        self.assertTrue(properties.exists())
        self.cleaner(remove_caches=True).scan().apply()
        self.assertFalse(properties.parent.exists())
        backups = list((self.home / "Library/Logs/team-java-env/cleanup").glob("*/files/**/gradle.properties"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "private=secret\n")

    def test_complex_or_malformed_configuration_aborts_before_any_deletion(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        for body in ('export JAVA_HOME="/jdk"; echo keep\n',
                     'if true; then\n  export JAVA_HOME=/jdk\nfi\n',
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
        profile = self.write(self.home / ".zshrc", "export JAVA_HOME=/jdk\n")
        plan = self.cleaner().scan()
        profile.write_text("export JAVA_HOME=/new-jdk\n")
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertTrue(jdk.exists())
        self.assertEqual(profile.read_text(), "export JAVA_HOME=/new-jdk\n")

    def test_shared_assignment_and_pipeline_are_not_discarded_with_java_settings(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        for body in ("export JAVA_HOME=/jdk EDITOR=vim\n",
                     "JAVA_HOME=/jdk echo keep\n", "export JAVA_HOME=/jdk | cat\n"):
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

    def test_asdf_and_mise_versions_and_home_selections_are_cleaned_preserving_other_tools(self):
        java = self.jdk(self.home / ".asdf/installs/java/temurin-21")
        gradle = self.gradle(self.home / ".local/share/mise/installs/gradle/8.10")
        asdf = self.write(self.home / ".tool-versions", "java temurin-21\ngradle 8.10\nnodejs 22.0\n")
        mise = self.write(self.home / ".config/mise/config.toml", '[tools]\njava = "21"\ngradle = "8.10"\nnode = "22"\n\n[settings]\nexperimental = true\n')
        self.cleaner().scan().apply()
        self.assertFalse(java.exists())
        self.assertFalse(gradle.exists())
        self.assertEqual(asdf.read_text(), "nodejs 22.0\n")
        self.assertEqual(mise.read_text(), '[tools]\nnode = "22"\n\n[settings]\nexperimental = true\n')

    def test_launchctl_java_environment_is_outside_static_shell_cleanup(self):
        # 只验证本工具不通过执行配置中的命令修改桌面会话。
        profile = self.write(self.home / ".zshrc", "launchctl setenv JAVA_HOME /jdk\n")
        plan = self.cleaner().scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        self.assertEqual(profile.read_text(), "launchctl setenv JAVA_HOME /jdk\n")

    def test_homebrew_removes_all_jdk_versions_after_gradle_but_preserves_unrelated_packages(self):
        log = self.base / "brew-calls"
        brew = self.fake_brew(self.base / "brew",
                          'if [ "$1" = list ]; then\n'
                          '  if [ "$2" = --formula ]; then printf "openjdk@8\\nopenjdk@21\\ngradle\\npython@3.13\\n";\n'
                          '  else printf "temurin@17\\nvisual-studio-code\\n"; fi\n'
                          'elif [ "$1" = uninstall ]; then printf "%s\\n" "$*" >> "$BREW_RECORD";\n'
                          'else exit 12; fi\n')
        self.env["BREW_RECORD"] = str(log)
        cleaner = self.tool.Cleaner(self.home, system_jvms=self.system,
                                    brews=[brew], environ=self.env, include_system=True)
        plan = cleaner.scan()
        self.assertFalse(log.exists())
        plan.apply()
        self.assertEqual(log.read_text().splitlines(), [
            "uninstall --formula --force gradle", "uninstall --formula --force openjdk@8",
            "uninstall --formula --force openjdk@21", "uninstall --cask temurin@17"])

    def test_failed_homebrew_inventory_or_uninstall_is_reported_as_failure(self):
        brew = self.fake_brew(self.base / "brew",
                          'if [ "$1" = list ] && [ "$2" = --formula ]; then echo openjdk;\n'
                          'elif [ "$1" = list ]; then exit 0; else exit 23; fi\n')
        plan = self.tool.Cleaner(self.home, system_jvms=self.system, brews=[brew],
                                 environ=self.env).scan()
        with self.assertRaises(self.tool.CleanupError):
            plan.apply()
        brew.write_text("#!/bin/sh\nexit 19\n")
        with self.assertRaises(self.tool.CleanupError):
            self.tool.Cleaner(self.home, system_jvms=self.system, brews=[brew], environ=self.env).scan()

    def test_cli_requires_explicit_apply_and_confirmation(self):
        jdk = self.jdk(self.home / ".local/share/java-dev/jdk8")
        args = [sys.executable, str(SCRIPT), "--no-homebrew"]
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


if __name__ == "__main__":
    unittest.main()
