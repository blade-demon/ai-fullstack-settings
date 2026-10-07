"""两版 Gradle 的独立安装、切换与 JDK 8 边界；仅使用临时微型 SDK。"""
import csv
import hashlib
import os
import shlex
import subprocess
import unittest
import zipfile

import test_gradle_install as fixtures


class GradleVersionTests(unittest.TestCase):
    setUp = fixtures.GradleInstallTests.setUp
    server = fixtures.GradleInstallTests.server
    run_script = fixtures.GradleInstallTests.run_script
    run_verify = fixtures.GradleInstallTests.run_verify
    assert_ok = fixtures.GradleInstallTests.assert_ok

    def target_for(self, version):
        return self.home / ".local/share/java-dev" / ("gradle-" + version)

    def distribution(self, version):
        script = fixtures.GRADLE_FIXTURE.replace("${FIXTURE_VERSION:-4.5.1}",
                                                  "${FIXTURE_VERSION:-" + version + "}")
        # 最终环境验证使用 env -i，记录位置不能依赖父进程传入的测试变量。
        script = script.replace('#!/bin/sh\n', '#!/bin/sh\nGRADLE_CALLS="${GRADLE_CALLS:-$HOME/gradle-fixture-calls}"\n', 1)
        return [("bin/gradle", script, 0o100755),
                ("lib/gradle-launcher-" + version + ".jar", "fixture launcher", 0o100644)]

    def archive_for(self, version):
        self.archive = self.web / ("gradle-" + version + "-bin.zip")
        with zipfile.ZipFile(self.archive, "w") as archive:
            for path, data, mode in self.distribution(version):
                info = zipfile.ZipInfo("gradle-" + version + "/" + path)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        return self.server()

    def seed_version(self, version):
        target = self.target_for(version)
        for path, data, mode in self.distribution(version):
            file = target / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(data)
            file.chmod(mode & 0o777)
        return target

    def seed_environment(self, values):
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        self.env_file.write_text("".join("export " + key + "=" + shlex.quote(str(value)) + "\n"
                                         for key, value in values.items()))

    def environment_values(self, shell="/bin/bash"):
        command = r'. "$1"; . "$1"; printf "%s\0" "$JAVA_HOME" "${JAVA_8_HOME-}" "$JRE_HOME" "$GRADLE_HOME" "${GRADLE_4_5_1_HOME-}" "${GRADLE_6_8_HOME-}" "$PATH" "$(command -v java)" "$(command -v gradle)"'
        result = subprocess.run([shell, "-f", "-c", command, "test", str(self.env_file)],
                                env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode().split("\0")[:-1]

    def unsupported_jdk(self):
        home = self.base / "JDK 21's home"
        (home / "bin").mkdir(parents=True)
        # 即使错误配置伪装成旧 JDK 的完整目录和变量，也必须按真实版本拒绝。
        (home / "jre").mkdir()
        for name, banner in (("java", 'openjdk version "21.0.11"'), ("javac", "javac 21.0.11")):
            binary = home / "bin" / name
            binary.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(banner) + "\n")
            binary.chmod(0o755)
        return home

    def test_gradle68_downloads_pinned_distribution_and_builds_with_jdk8(self):
        result = self.run_script("--project", str(self.project),
                                 extra={**self.archive_for("6.8"), "GRADLE_VERSION": "6.8"})
        self.assert_ok(result)
        target = self.target_for("6.8")
        self.assertTrue(os.access(target / "bin/gradle", os.X_OK))
        self.assertFalse(self.target_for("4.5.1").exists())
        values = self.environment_values()
        self.assertEqual(values[:2], [str(self.jdk), str(self.jdk)])
        self.assertEqual(values[3:6], [str(target), "", str(target)])
        record = self.build_record.read_text().splitlines()
        self.assertEqual(record[:6], [str(self.project), str(self.jdk), str(self.jdk),
                                     str(self.jdk / "jre"), str(target), str(self.home / ".gradle")])
        self.assertEqual(record[7:], ["3", "--no-daemon", "--console=plain", "build"])
        self.assertIn("BUILD SUCCESSFUL", result.stdout)

    def test_gradle68_repair_scope_propagates_cli_version_through_final_verification_and_history(self):
        settings = self.archive_for("6.8")
        resources = self.web / "resources/runtime/gradle"
        resources.mkdir(parents=True)
        self.archive.replace(resources / self.archive.name)
        settings.pop("GRADLE_PACKAGE_PATH")
        history = self.home / "repair-history"
        result = subprocess.run(
            ["/bin/bash", str(self.support / "scripts/repair-env.sh"),
             "--scope", "gradle", "--gradle-version", "6.8"], cwd=self.base,
            env={**self.env, **settings, "REPAIR_HISTORY_DIR": str(history)},
            text=True, capture_output=True, timeout=30)
        self.assert_ok(result)
        target = self.target_for("6.8")
        self.assertTrue((target / "bin/gradle").is_file())
        self.assertFalse(self.target_for("4.5.1").exists())
        self.assertEqual(self.environment_values()[3:6], [str(target), "", str(target)])
        self.assertEqual((self.home / "gradle-fixture-calls").read_text().splitlines(), ["--version"])
        self.assertFalse(self.build_record.exists())
        runs = list(history.iterdir())
        self.assertEqual(len(runs), 1)
        with (runs[0] / "result.tsv").open() as stream:
            records = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(records, [{"status": "COMPONENT_VERIFIED", "exit_code": "0",
                                    "scope": "gradle", "project": ""}])
        with (runs[0] / "steps.tsv").open() as stream:
            steps = list(csv.DictReader(stream, delimiter="\t"))
        self.assertTrue(steps)
        self.assertTrue(all(step["status"] == "verified" and step["exit_code"] == "0" for step in steps), steps)
        self.assertIn("[验证通过] Gradle 6.8", result.stdout)
        self.assertIn("COMPONENT_VERIFIED", (runs[0] / "report.md").read_text())

    def test_two_distributions_remain_installed_and_can_switch_without_downloading(self):
        for version in ("4.5.1", "6.8"):
            self.assert_ok(self.run_script(extra={**self.archive_for(version), "GRADLE_VERSION": version}))
        target4, target6 = self.target_for("4.5.1"), self.target_for("6.8")
        initial = [(target / "bin/gradle").read_bytes() for target in (target4, target6)]
        for version, target in (("4.5.1", target4), ("6.8", target6)):
            self.assert_ok(self.run_script("--project", str(self.project), extra={"GRADLE_VERSION": version}))
            self.assertEqual(self.build_record.read_text().splitlines()[4], str(target))
            for shell in ("/bin/bash", "/bin/zsh"):
                values = self.environment_values(shell)
                self.assertEqual(values[3:6], [str(target), str(target4), str(target6)])
                self.assertEqual(values[6].split(":")[:2], [str(self.jdk / "bin"), str(target / "bin")])
                self.assertEqual(values[6].split(":").count(str(target / "bin")), 1)
                self.assertEqual(values[7:], [str(self.jdk / "bin/java"), str(target / "bin/gradle")])
        self.assertEqual(initial, [(target / "bin/gradle").read_bytes() for target in (target4, target6)])
        files = [self.env_file, self.env_file.parent / "jdk.sh", self.env_file.parent / "gradle.sh", self.home / ".zshrc"]
        snapshot = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
        self.assert_ok(self.run_script(extra={"GRADLE_VERSION": "6.8"}))
        self.assertEqual(snapshot, [(p.read_bytes(), p.stat().st_mtime_ns) for p in files])

    def test_gradle68_checksum_and_runtime_version_failures_never_publish(self):
        server = self.archive_for("6.8")
        for override in ({"GRADLE_SHA256": "0" * 64}, {"FIXTURE_VERSION": "6.8.1"}):
            with self.subTest(override=override):
                result = self.run_script(extra={**server, "GRADLE_VERSION": "6.8", **override})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.target_for("6.8").exists())
                self.assertFalse(self.env_file.exists())
                self.assertFalse(self.build_record.exists())

    def test_gradle68_rejects_wrong_version_alias_before_execution(self):
        target = self.seed_version("6.8")
        self.seed_environment({"JAVA_HOME": self.jdk, "JAVA_8_HOME": self.jdk, "JRE_HOME": self.jdk / "jre",
                               "GRADLE_HOME": target, "GRADLE_6_8_HOME": self.target_for("4.5.1"),
                               "GRADLE_USER_HOME": self.home / ".gradle"})
        result = self.run_verify(extra={"GRADLE_VERSION": "6.8"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GRADLE_6_8_HOME", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.build_record.exists())

    def test_external_unsupported_jdk_cannot_install_or_build_either_gradle(self):
        wrong_jdk = self.unsupported_jdk()
        for version, alias in (("4.5.1", "GRADLE_4_5_1_HOME"), ("6.8", "GRADLE_6_8_HOME")):
            with self.subTest(version=version):
                target = self.seed_version(version)
                self.seed_environment({"JAVA_HOME": wrong_jdk, "JAVA_8_HOME": wrong_jdk, "JRE_HOME": wrong_jdk / "jre",
                                       "GRADLE_HOME": target, alias: target, "GRADLE_USER_HOME": self.home / ".gradle"})
                before = self.env_file.read_bytes()
                settings = {"GRADLE_VERSION": version, "JAVA_HOME": str(wrong_jdk),
                            "JAVA_8_HOME": "", "JDK_INSTALL_DIR": str(wrong_jdk)}
                for invoke in (self.run_script, self.run_verify):
                    result = invoke(extra=settings)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self.calls.exists())
                    self.assertFalse(self.build_record.exists())
                    self.assertEqual(self.env_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
