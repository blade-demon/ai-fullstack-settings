"""独立 Gradle 安装：微型 ZIP、假 JDK/Gradle 与本机 HTTP，不执行真实项目。"""
import functools
import hashlib
import http.server
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

GRADLE_FIXTURE = r'''#!/bin/sh
printf '%s\n' "$@" >> "$GRADLE_CALLS"
if [ "${1-}" = --version ]; then
    printf 'Gradle %s\n' "${FIXTURE_VERSION:-4.5.1}"
    exit "${VERSION_EXIT:-0}"
fi
printf '%s\n' "$PWD" "$JAVA_HOME" "$JAVA_8_HOME" "$JRE_HOME" "$GRADLE_HOME" "$GRADLE_USER_HOME" "$PATH" "$#" "$@" > "$BUILD_RECORD"
printf '%s\n' 'fixture build stdout'
printf '%s\n' 'fixture build stderr' >&2
if [ "${BUILD_MARKER:-true}" = true ]; then printf '%s\n' 'BUILD SUCCESSFUL in 1s'; fi
exit "${BUILD_EXIT:-0}"
'''

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class GradleInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Gradle 安装's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具's 目录/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "用户 home"
        self.home.mkdir()
        self.project = self.base / "Java 项目's dir"
        self.project.mkdir()
        (self.project / "build.gradle").write_text("// fixture project without Wrapper\n")
        self.jdk = self.base / "JDK 8's home"
        (self.jdk / "bin").mkdir(parents=True)
        (self.jdk / "jre").mkdir()
        for name, banner in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            binary = self.jdk / "bin" / name
            binary.write_text("#!/bin/sh\nprintf '%s\n' " + shlex.quote(banner) + "\n")
            binary.chmod(0o755)
        self.target = self.home / ".local/share/java-dev/gradle-4.5.1"
        self.calls = self.base / "gradle-calls"
        self.build_record = self.base / "build-record"
        self.env_file = self.home / ".config/java-dev/env.sh"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "SHELL": "/bin/zsh",
                    "LC_ALL": "C.UTF-8", "JDK_AUTO_DETECT": "false", "JDK_INSTALL_DIR": str(self.jdk),
                    "JAVA_HOME": str(self.jdk), "GRADLE_CALLS": str(self.calls), "BUILD_RECORD": str(self.build_record),
                    "SERVER_ADDR": "127.0.0.1:1", "ENV_FILE": str(self.env_file), "CDPATH": str(self.base)}
        self.web = self.base / "web"
        self.web.mkdir()
        self.archive = self.web / "gradle-4.5.1-bin.zip"
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, data, mode in (("gradle-4.5.1/bin/gradle", GRADLE_FIXTURE, 0o100755),
                                     ("gradle-4.5.1/lib/gradle-launcher-4.5.1.jar", "fixture launcher", 0o100644)):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def seed_install(self):
        (self.target / "bin").mkdir(parents=True)
        (self.target / "lib").mkdir()
        binary = self.target / "bin/gradle"
        binary.write_text(GRADLE_FIXTURE)
        binary.chmod(0o755)
        (self.target / "lib/gradle-launcher-4.5.1.jar").write_bytes(b"fixture launcher")

    def seed_environment(self):
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        values = {"JAVA_HOME": self.jdk, "JAVA_8_HOME": self.jdk, "JRE_HOME": self.jdk / "jre",
                  "GRADLE_HOME": self.target, "GRADLE_4_5_1_HOME": self.target,
                  "GRADLE_USER_HOME": self.home / ".gradle"}
        self.env_file.write_text("".join("export " + key + "=" + shlex.quote(str(value)) + "\n"
                                         for key, value in values.items()))

    def configure_idea_gradle(self, distribution=None, gradle_home=None):
        idea = self.project / ".idea"
        idea.mkdir(exist_ok=True)
        project = ET.Element("project", version="4")
        component = ET.SubElement(project, "component", name="GradleSettings")
        option = ET.SubElement(component, "option", name="linkedExternalProjectsSettings")
        settings = ET.SubElement(option, "GradleProjectSettings")
        ET.SubElement(settings, "option", name="externalProjectPath", value="$PROJECT_DIR$")
        if distribution is not None:
            ET.SubElement(settings, "option", name="distributionType", value=distribution)
        if gradle_home is not None:
            ET.SubElement(settings, "option", name="gradleHome", value=str(gradle_home))
        ET.ElementTree(project).write(idea / "gradle.xml", encoding="unicode")

    def seed_wrapper(self):
        self.wrapper_calls = self.base / "wrapper-calls"
        self.wrapper_record = self.base / "wrapper-build-record"
        wrapper = self.project / "gradlew"
        wrapper.write_text('#!/bin/sh\nexport GRADLE_CALLS="$WRAPPER_CALLS"\n'
                           'export BUILD_RECORD="$WRAPPER_BUILD_RECORD"\n'
                           'export FIXTURE_VERSION="${WRAPPER_VERSION:-4.5.1}"\n' + GRADLE_FIXTURE)
        wrapper.chmod(0o755)
        directory = self.project / "gradle/wrapper"
        directory.mkdir(parents=True)
        (directory / "gradle-wrapper.jar").write_bytes(b"fixture wrapper jar")
        (directory / "gradle-wrapper.properties").write_text(
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-4.5.1-bin.zip\n")
        self.env.update({"WRAPPER_CALLS": str(self.wrapper_calls),
                         "WRAPPER_BUILD_RECORD": str(self.wrapper_record)})

    def run_verify(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/verify-gradle.sh"),
                               "--project", str(self.project), *args], cwd=self.base,
                              env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=20)

    def server(self):
        handler = functools.partial(QuietHandler, directory=str(self.web))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return {"SERVER_ADDR": f"127.0.0.1:{server.server_port}", "GRADLE_PACKAGE_PATH": self.archive.name,
                "GRADLE_SHA256": self.sha}

    def run_script(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/install-gradle.sh"), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=20)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_same_version_repairs_complete_environment_without_project(self):
        self.seed_install()
        inode = self.target.stat().st_ino
        cache = self.home / "Gradle 缓存's"
        result = self.run_script(extra={"GRADLE_USER_HOME": str(cache)})
        self.assert_ok(result)
        self.assertIn("未执行构建", result.stdout)
        self.assertFalse(self.build_record.exists())
        self.assertEqual(self.target.stat().st_ino, inode)
        command = r'. "$1"; . "$1"; printf "%s\0" "$JAVA_HOME" "$JAVA_8_HOME" "$JRE_HOME" "$GRADLE_HOME" "$GRADLE_4_5_1_HOME" "$GRADLE_USER_HOME" "$PATH"; command -v java; command -v gradle'
        for shell in ("/bin/bash", "/bin/zsh"):
            result = subprocess.run([shell, "-f", "-c", command, "test", str(self.home / ".zshrc")],
                                    env=self.env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = result.stdout.decode().split("\0")
            self.assertEqual(values[:6], [str(self.jdk), str(self.jdk), str(self.jdk / "jre"),
                                         str(self.target), str(self.target), str(cache)])
            self.assertEqual(values[6].split(":")[:2], [str(self.jdk / "bin"), str(self.target / "bin")])
            self.assertEqual(values[6].split(":").count(str(self.target / "bin")), 1)
            self.assertEqual(values[7].splitlines(), [str(self.jdk / "bin/java"), str(self.target / "bin/gradle")])
        files = [self.env_file, self.env_file.parent / "jdk.sh", self.env_file.parent / "gradle.sh", self.home / ".zshrc"]
        snapshot = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
        self.assert_ok(self.run_script(extra={"GRADLE_USER_HOME": str(cache)}))
        self.assertEqual(snapshot, [(p.read_bytes(), p.stat().st_mtime_ns) for p in files])

    def test_install_downloads_pinned_zip_and_validates_before_publish(self):
        result = self.run_script(extra=self.server())
        self.assert_ok(result)
        self.assertTrue((self.target / "bin/gradle").is_file())
        self.assertTrue(os.access(self.target / "bin/gradle", os.X_OK))
        self.assertTrue(self.env_file.exists())
        self.assertFalse(self.build_record.exists())
        self.assertFalse(list(self.target.parent.glob(".gradle-install.*")))

    def test_download_checksum_and_version_failures_do_not_publish_install_or_environment(self):
        server = self.server()
        for override in ({"GRADLE_PACKAGE_PATH": "missing.zip"}, {"GRADLE_SHA256": "0" * 64},
                         {"FIXTURE_VERSION": "8.0"}, {"VERSION_EXIT": "17"}):
            with self.subTest(override=override):
                result = self.run_script(extra={**server, **override})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.target.exists())
                self.assertFalse(self.env_file.exists())
                self.assertFalse((self.home / ".zshrc").exists())
                self.assertFalse(list(self.target.parent.glob(".gradle-install.*")))

    def test_unknown_existing_directory_is_never_overwritten(self):
        self.target.mkdir(parents=True)
        keep = self.target / "keep"
        keep.write_text("preserve")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(keep.read_text(), "preserve")
        self.assertFalse(self.env_file.exists())

    def test_project_without_wrapper_runs_real_build_with_exact_arguments_and_environment(self):
        self.seed_install()
        result = self.run_script("--project", self.project.name)
        self.assert_ok(result)
        self.assertIn("BUILD SUCCESSFUL", result.stdout)
        record = self.build_record.read_text().splitlines()
        self.assertEqual(record[:6], [str(self.project), str(self.jdk), str(self.jdk), str(self.jdk / "jre"),
                                     str(self.target), str(self.home / ".gradle")])
        self.assertEqual(record[7:], ["3", "--no-daemon", "--console=plain", "build"])
        self.assertFalse((self.project / "gradlew").exists())
        self.assertIn("IDEA 项目未配置", result.stdout)

    def test_idea_wrapper_modes_execute_the_project_wrapper_even_when_sdk_is_pending(self):
        self.seed_install()
        self.seed_environment()
        self.seed_wrapper()
        for distribution in (None, "DEFAULT_WRAPPED", "WRAPPED"):
            with self.subTest(distribution=distribution):
                self.configure_idea_gradle(distribution)
                self.wrapper_calls.unlink(missing_ok=True)
                result = self.run_verify()
                self.assert_ok(result)
                self.assertFalse(self.calls.exists(), "IDEA 选择 Wrapper 时不能执行独立 Gradle")
                self.assertEqual(self.wrapper_calls.read_text().splitlines(),
                                 ["--version", "--no-daemon", "--console=plain", "build"])
                self.assertEqual(self.wrapper_record.read_text().splitlines()[7:],
                                 ["3", "--no-daemon", "--console=plain", "build"])

    def test_idea_wrapper_does_not_require_a_managed_gradle_distribution(self):
        self.seed_environment()
        self.seed_wrapper()
        self.configure_idea_gradle("DEFAULT_WRAPPED")
        self.assert_ok(self.run_verify())
        self.assertTrue(self.wrapper_record.exists())
        self.assertFalse(self.target.exists())

    def test_idea_wrapper_actual_version_must_match_the_team_target_before_build(self):
        self.seed_install()
        self.seed_environment()
        self.seed_wrapper()
        self.configure_idea_gradle("DEFAULT_WRAPPED")
        result = self.run_verify(extra={"WRAPPER_VERSION": "4.5.10"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("4.5.10", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.wrapper_record.exists())

    def test_idea_local_executes_its_configured_home_instead_of_managed_gradle(self):
        self.seed_environment()
        local_home = self.home / "IDEA local Gradle's home"
        (local_home / "bin").mkdir(parents=True)
        (local_home / "lib").mkdir()
        (local_home / "lib/gradle-launcher-4.5.1.jar").write_bytes(b"fixture launcher")
        local_calls = self.base / "idea-local-calls"
        binary = local_home / "bin/gradle"
        binary.write_text('#!/bin/sh\nexport GRADLE_CALLS="$IDEA_LOCAL_CALLS"\n' + GRADLE_FIXTURE)
        binary.chmod(0o755)
        self.configure_idea_gradle("LOCAL", "$USER_HOME$/" + local_home.name)
        result = self.run_verify(extra={"IDEA_LOCAL_CALLS": str(local_calls)})
        self.assert_ok(result)
        self.assertFalse(self.calls.exists())
        self.assertEqual(local_calls.read_text().splitlines(),
                         ["--version", "--no-daemon", "--console=plain", "build"])
        self.assertEqual(self.build_record.read_text().splitlines()[4], str(local_home))

    def test_idea_local_without_home_is_pending_and_never_falls_back_to_managed_gradle(self):
        self.seed_install()
        self.seed_environment()
        self.configure_idea_gradle("LOCAL")
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IDEA", result.stdout + result.stderr)
        self.assertIn("gradleHome", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.build_record.exists())

    def test_unknown_or_malformed_idea_distribution_never_executes_a_gradle(self):
        self.seed_install()
        self.seed_environment()
        for distribution in ("BUNDLED", "UNKNOWN"):
            with self.subTest(distribution=distribution):
                self.configure_idea_gradle(distribution)
                result = self.run_verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("IDEA", result.stdout + result.stderr)
                self.assertFalse(self.calls.exists())
        (self.project / ".idea/gradle.xml").write_text("<project><broken>")
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IDEA", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_idea_wrapper_requires_complete_executable_wrapper(self):
        self.seed_install()
        self.seed_environment()
        self.seed_wrapper()
        self.configure_idea_gradle("DEFAULT_WRAPPED")
        wrapper = self.project / "gradlew"
        wrapper.chmod(0o644)
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.wrapper_calls.exists())
        wrapper.chmod(0o755)
        (self.project / "gradle/wrapper/gradle-wrapper.jar").unlink()
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.wrapper_calls.exists())

    def test_idea_wrapper_preserves_actual_exit_codes_and_requires_build_success_marker(self):
        self.seed_install()
        self.seed_environment()
        self.seed_wrapper()
        self.configure_idea_gradle("DEFAULT_WRAPPED")
        for extra, expected in (({"VERSION_EXIT": "17"}, 17), ({"BUILD_EXIT": "23"}, 23),
                                ({"BUILD_MARKER": "false"}, 1)):
            with self.subTest(extra=extra):
                result = self.run_verify(extra=extra)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertNotIn("项目构建验证通过", result.stdout)
                self.assertFalse(self.calls.exists())

    def test_idea_wrapper_dry_run_does_not_load_environment_or_execute_commands(self):
        self.seed_wrapper()
        self.configure_idea_gradle("DEFAULT_WRAPPED")
        result = self.run_verify("--dry-run")
        self.assert_ok(result)
        self.assertIn("Wrapper", result.stdout)
        self.assertIn("build", result.stdout)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.wrapper_calls.exists())
        self.assertFalse(self.env_file.exists())

        # 完整 IDEA SDK 关联也不得让预演执行 java/javac 或加载受管环境。
        sdk_config = self.base / "IDEA config/options"
        sdk_config.mkdir(parents=True)
        table = ET.Element("application")
        component = ET.SubElement(table, "component", name="ProjectJdkTable")
        sdk = ET.SubElement(component, "jdk")
        ET.SubElement(sdk, "name", value="Team JDK 8")
        ET.SubElement(sdk, "type", value="JavaSDK")
        ET.SubElement(sdk, "homePath", value=str(self.jdk))
        ET.ElementTree(table).write(sdk_config / "jdk.table.xml", encoding="unicode")
        (self.project / ".idea/misc.xml").write_text(
            '<project version="4"><component name="ProjectRootManager" project-jdk-name="Team JDK 8" /></project>')
        java_calls = self.base / "jdk-calls"
        for name in ("java", "javac"):
            binary = self.jdk / "bin" / name
            binary.write_text('#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(name) +
                              ' >> "$JAVA_CALLS"\n' + binary.read_text().removeprefix("#!/bin/sh\n"))
        self.seed_environment()
        loaded = self.base / "environment-loaded"
        self.env_file.write_text('printf loaded > "$ENVIRONMENT_LOADED"\n' + self.env_file.read_text())
        before = self.env_file.read_bytes()
        result = self.run_verify("--dry-run", extra={"IDEA_CONFIG_DIR": str(sdk_config.parent),
                                 "JAVA_CALLS": str(java_calls), "ENVIRONMENT_LOADED": str(loaded)})
        self.assert_ok(result)
        self.assertFalse(java_calls.exists())
        self.assertFalse(loaded.exists())
        self.assertFalse(self.wrapper_calls.exists())
        self.assertEqual(self.env_file.read_bytes(), before)

    def test_build_failure_and_zero_exit_without_success_marker_are_not_success(self):
        self.seed_install()
        result = self.run_script("--project", str(self.project), extra={"BUILD_EXIT": "23"})
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertNotIn("项目构建验证通过", result.stdout)
        result = self.run_script("--project", str(self.project), extra={"BUILD_MARKER": "false"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("项目构建验证通过", result.stdout)

    def test_invalid_jdk_or_project_is_rejected_before_environment_changes(self):
        self.seed_install()
        result = self.run_script(extra={"JDK_INSTALL_DIR": str(self.base / "missing"), "JAVA_HOME": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.env_file.exists())
        (self.project / "build.gradle").unlink()
        result = self.run_script("--project", str(self.project))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.env_file.exists())

    def test_dry_run_never_executes_or_creates_environment(self):
        result = self.run_script("--project", str(self.project), "--dry-run")
        self.assert_ok(result)
        self.assertIn("build", result.stdout)
        self.assertIn("GRADLE_HOME", result.stdout)
        self.assertFalse(self.calls.exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_missing_checksum_refuses_download_without_creating_install(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stdout + result.stderr)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.env_file.exists())

    def test_wrong_existing_version_is_preserved_and_fails(self):
        self.seed_install()
        before = (self.target / "bin/gradle").read_bytes()
        result = self.run_script(extra={"FIXTURE_VERSION": "4.5.10"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / "bin/gradle").read_bytes(), before)
        self.assertFalse(self.env_file.exists())

    def test_help_and_bad_arguments(self):
        self.assert_ok(self.run_script("--help"))
        for args in (("--project",), ("--project", "--dry-run"), ("--unknown",)):
            self.assertNotEqual(self.run_script(*args).returncode, 0)
        self.assertFalse(self.calls.exists())

if __name__ == "__main__":
    unittest.main()
