"""完整受管环境与真实构建判定；仅执行临时目录内的 SDK fixture。"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from test_gradle_install import GRADLE_FIXTURE

ROOT = Path(__file__).resolve().parents[1]


class ManagedBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="完整环境 build's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具's 目录/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "home"
        self.home.mkdir()
        self.project = self.base / "Java 项目's"
        self.project.mkdir()
        (self.project / "build.gradle.kts").write_text("// fixture\n")
        self.jdk = self.base / "JDK's 8"
        (self.jdk / "bin").mkdir(parents=True)
        (self.jdk / "jre").mkdir()
        for name, banner in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            binary = self.jdk / "bin" / name
            binary.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(banner) + "\n")
            binary.chmod(0o755)
        self.gradle = self.base / "Gradle's 4.5.1"
        (self.gradle / "bin").mkdir(parents=True)
        (self.gradle / "lib").mkdir()
        (self.gradle / "lib/gradle-launcher-4.5.1.jar").write_text("launcher fixture")
        (self.gradle / "bin/gradle").write_text(GRADLE_FIXTURE)
        (self.gradle / "bin/gradle").chmod(0o755)
        self.env_file = self.home / ".config/java-dev/env.sh"
        self.env_file.parent.mkdir(parents=True)
        variables = {"JAVA_HOME": str(self.jdk), "JAVA_8_HOME": str(self.jdk), "JRE_HOME": str(self.jdk / "jre"),
                     "GRADLE_HOME": str(self.gradle), "GRADLE_4_5_1_HOME": str(self.gradle),
                     "GRADLE_USER_HOME": str(self.home / ".gradle")}
        self.env_file.write_text("".join("export " + key + "=" + shlex.quote(value) + "\n" for key, value in variables.items()))
        self.calls = self.base / "calls"
        self.record = self.base / "record"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "SHELL": "/bin/zsh",
                    "ENV_FILE": str(self.env_file), "JDK_AUTO_DETECT": "false", "LC_ALL": "C.UTF-8",
                    "GRADLE_CALLS": str(self.calls), "BUILD_RECORD": str(self.record), "CDPATH": str(self.base)}

    def run_script(self, *args, extra=None, project=True):
        command = ["/bin/bash", str(self.support / "scripts/runtime/verify-gradle.sh")]
        if project:
            command += ["--project", str(self.project)]
        return subprocess.run([*command, *args], cwd=self.base, env={**self.env, **(extra or {})},
                              text=True, capture_output=True, timeout=15)

    def test_real_build_requires_exit_zero_and_success_marker(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("项目构建验证通过", result.stdout)
        self.assertIn("fixture build stderr", result.stdout + result.stderr)
        record = self.record.read_text().splitlines()
        self.assertEqual(record[0], str(self.project))
        self.assertEqual(record[1:5], [str(self.jdk), str(self.jdk), str(self.jdk / "jre"), str(self.gradle)])
        self.assertEqual(record[7:], ["3", "--no-daemon", "--console=plain", "build"])
        self.assertEqual(self.calls.read_text().splitlines(), ["--version", "--no-daemon", "--console=plain", "build"])

    def test_build_failure_exit_is_preserved_even_when_marker_exists(self):
        result = self.run_script(extra={"BUILD_EXIT": "37"})
        self.assertEqual(result.returncode, 37)
        self.assertIn("37", result.stdout + result.stderr)
        self.assertNotIn("项目构建验证通过", result.stdout)

    def test_zero_exit_without_marker_and_wrong_gradle_version_are_failure(self):
        result = self.run_script(extra={"BUILD_MARKER": "false"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("项目构建验证通过", result.stdout)
        self.record.unlink()
        result = self.run_script(extra={"FIXTURE_VERSION": "4.5.10"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists())

    def test_explicit_single_task_and_relative_project_are_supported(self):
        result = self.run_script("--project", self.project.name, project=False,
                                 extra={"GRADLE_BUILD_TASK": ":service:build"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record.read_text().splitlines()[-1], ":service:build")

    def test_task_options_and_injection_are_rejected_before_execution(self):
        for task in ("--version", "build --exclude-task test", "build;touch pwned", "$(touch pwned)"):
            with self.subTest(task=task):
                result = self.run_script(extra={"GRADLE_BUILD_TASK": task})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())
        self.assertFalse((self.base / "pwned").exists())

    def test_dry_run_does_not_source_managed_environment_or_run_sdk(self):
        marker = self.home / "loaded-env"
        self.env_file.write_text("touch " + shlex.quote(str(marker)) + "\nexit 97\n")
        before = self.env_file.read_bytes()
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--no-daemon --console=plain build", result.stdout)
        self.assertFalse(marker.exists())
        self.assertFalse(self.calls.exists())
        self.assertEqual(self.env_file.read_bytes(), before)

    def test_missing_jdk_or_build_definition_fails_before_build(self):
        (self.jdk / "bin/java").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())
        (self.project / "build.gradle.kts").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_profile_ready_is_read_only_and_does_not_source_env(self):
        marker = self.home / "loaded-env"
        self.env_file.write_text("touch " + shlex.quote(str(marker)) + "\n")
        profile = self.home / ".zshrc"
        quoted = "'" + str(self.env_file).replace("'", "'\\''") + "'"
        profile.write_text(". " + quoted + "\n")
        command = 'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/managed-env.sh"; managed_env_profile_ready'
        result = subprocess.run(["/bin/bash", "-c", command, "test", str(self.support)],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())

    def test_profile_source_after_user_overrides_is_moved_to_end_without_losing_custom_lines(self):
        profile = self.home / ".zshrc"
        command = ('source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/managed-env.sh"; '
                   'managed_env_write_jdk "$2"; managed_env_write_gradle "$3"')
        arguments = ["/bin/bash", "-c", command, "test", str(self.support), str(self.jdk), str(self.gradle)]
        first = subprocess.run(arguments, env=self.env, text=True, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        custom = "\n# preserve custom settings\nexport JAVA_HOME=/another/jdk\nexport PATH=/usr/bin:/bin\nexport MY_SETTING=unchanged\n"
        with profile.open("a") as stream:
            stream.write(custom)
        ready = subprocess.run(["/bin/bash", "-c",
                                'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/managed-env.sh"; managed_env_profile_ready',
                                "test", str(self.support)], env=self.env, capture_output=True)
        self.assertNotEqual(ready.returncode, 0)
        repaired = subprocess.run(arguments, env=self.env, text=True, capture_output=True)
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertIn(custom, profile.read_text())
        self.assertEqual(profile.read_text().count("# >>> team-java-env managed >>>"), 1)
        for shell in ("/bin/bash", "/bin/zsh"):
            observed = subprocess.run([shell, "-f", "-c", '. "$1"; printf "%s\\n" "$JAVA_HOME" "$(command -v java)" "$MY_SETTING"',
                                       "test", str(profile)], env=self.env, text=True, capture_output=True)
            self.assertEqual(observed.returncode, 0, observed.stderr)
            self.assertEqual(observed.stdout.splitlines(), [str(self.jdk), str(self.jdk / "bin/java"), "unchanged"])
        snapshot = (profile.read_bytes(), profile.stat().st_mtime_ns)
        repeated = subprocess.run(arguments, env=self.env, text=True, capture_output=True)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual((profile.read_bytes(), profile.stat().st_mtime_ns), snapshot)


if __name__ == "__main__":
    unittest.main()
