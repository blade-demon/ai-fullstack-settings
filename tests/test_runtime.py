"""运行真实脚本；HTTP 服务和微型 JDK 包代替大型外部下载。"""
import hashlib
import http.server
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
KIT_ROOT = ROOT / "dev-kit/.support"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="环境 test ")
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
                    "SHELL": "/bin/zsh", "LC_ALL": "C", "JDK_AUTO_DETECT": "false"}
        self.project = self.base / "Java 项目"
        self.wrapper = self.project / "gradle/wrapper"
        self.wrapper.mkdir(parents=True)
        (self.project / "build.gradle").write_text("// fixture business project\n")
        (self.project / "gradlew").write_text("#!/bin/sh\nexit 99\n")
        (self.wrapper / "gradle-wrapper.jar").write_bytes(b"test wrapper placeholder")
        self.props = self.wrapper / "gradle-wrapper.properties"
        self.original = "# keep\ndistributionUrl=https\\://old.example/gradle.zip\nzipStorePath=wrapper/dists\n"
        self.props.write_text(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, name, *args, extra=None):
        return subprocess.run(["/bin/bash", str(KIT_ROOT / name), *args], cwd=self.base,
                              env={**self.env, **(extra or {})}, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_dry_run_defaults_and_custom_server_never_write_home(self):
        result = self.run_script("install_env.sh", "--dry-run")
        self.assert_ok(result)
        self.assertIn("http://127.0.0.1:8080/", result.stdout)
        result = self.run_script("install_env.sh", "--dry-run", "--project", str(self.project),
                                 extra={"SERVER_ADDR": "mirror.example:9000", "SERVER_SCHEME": "https"})
        self.assert_ok(result)
        self.assertIn("https://mirror.example:9000/resources/runtime/gradle/gradle-4.5.1-bin.zip", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.props.read_text(), self.original)
        self.assertFalse(self.props.with_suffix(".properties.bak").exists())

    def test_wrapper_update_preserves_settings_backup_and_is_idempotent(self):
        args = ("--project", str(self.project))
        result = self.run_script("scripts/runtime/config-gradle.sh", *args)
        self.assert_ok(result)
        expected = "# keep\ndistributionUrl=http\\://127.0.0.1:8080/resources/runtime/gradle/gradle-4.5.1-bin.zip\nzipStorePath=wrapper/dists\n"
        self.assertEqual(self.props.read_text(), expected)
        self.assertEqual(self.props.with_suffix(".properties.bak").read_text(), self.original)
        self.assert_ok(self.run_script("scripts/runtime/config-gradle.sh", *args))
        self.assertEqual(self.props.read_text(), expected)
        self.assertEqual(self.props.with_suffix(".properties.bak").read_text(), self.original)

    def test_wrapper_custom_path_and_checksum(self):
        old = self.original + "distributionSha256Sum=" + "a" * 64 + "\n"
        self.props.write_text(old)
        env = {"SERVER_ADDR": "mirror.example:9090", "SERVER_SCHEME": "https",
               "GRADLE_PACKAGE_PATH": "tools/gradle.zip", "GRADLE_SHA256": "B" * 64}
        self.assert_ok(self.run_script("scripts/runtime/config-gradle.sh", "--project", str(self.project), extra=env))
        contents = self.props.read_text()
        self.assertIn("distributionUrl=https\\://mirror.example:9090/tools/gradle.zip\n", contents)
        self.assertIn("distributionSha256Sum=" + "b" * 64 + "\n", contents)

    def test_relative_project_works_with_exported_cdpath(self):
        result = self.run_script("scripts/runtime/config-gradle.sh", "--project", self.project.name,
                                 extra={"CDPATH": str(self.base)})
        self.assert_ok(result)
        self.assertIn("127.0.0.1:8080", self.props.read_text())

    def test_repair_preview_accepts_project_without_complete_wrapper(self):
        (self.wrapper / "gradle-wrapper.jar").unlink()
        (self.project / "gradlew").unlink()
        result = self.run_script("install_env.sh", "--project", str(self.project), "--dry-run")
        self.assert_ok(result)
        self.assertIn("--no-daemon --console=plain build", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.props.read_text(), self.original)

    def test_invalid_arguments_and_addresses_do_not_mutate(self):
        for args, env in [(("--project",), {}), (("--unknown",), {}),
                          (("--dry-run",), {"SERVER_ADDR": "http://example:8080"}),
                          (("--dry-run",), {"SERVER_ADDR": "example\ninvalid"})]:
            result = self.run_script("install_env.sh", *args, extra=env)
            self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_utf8_terminal_can_preview_and_report_missing_build_definition(self):
        env = {"LC_ALL": "C.UTF-8"}
        self.assert_ok(self.run_script("install_env.sh", "--dry-run", extra=env))
        (self.project / "build.gradle").unlink()
        result = self.run_script("install_env.sh", "--project", str(self.project), extra=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("build.gradle", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def fixture_jdk(self, version="1.8.0_432"):
        package = self.base / "web/packages"
        package.mkdir(parents=True)
        source = self.base / "bundle/Example.jdk/Contents/Home/bin"
        source.mkdir(parents=True)
        (source.parent / "jre").mkdir()
        for name, output in [("java", f'openjdk version "{version}"'), ("javac", f"javac {version}")]:
            binary = source / name
            binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}' >&2\n")
            binary.chmod(0o755)
        archive = package / "fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(self.base / "bundle/Example.jdk", arcname="Example.jdk")
        handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(package.parent), **kwargs)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return {"SERVER_ADDR": f"127.0.0.1:{server.server_port}",
                "JDK_PACKAGE_PATH": "packages/fixture.tar.gz",
                "JDK_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest()}

    def test_jdk_download_install_and_repeat_with_quoted_paths(self):
        env = self.fixture_jdk()
        install = self.home / "Java 安装's dir"
        envfile = self.home / "env 配置's.sh"
        env.update(JDK_INSTALL_DIR=str(install), ENV_FILE=str(envfile), LC_ALL="C.UTF-8")
        result = self.run_script("scripts/runtime/config-jdk.sh", extra=env)
        self.assert_ok(result)
        profile = self.home / ".zshrc"
        first = profile.read_text()
        first_environment = envfile.read_bytes()
        environment_mtime = envfile.stat().st_mtime_ns
        # 重复运行不需下载，已安装 Java 8 可直接复用。
        env["SERVER_ADDR"] = "127.0.0.1:1"
        self.assert_ok(self.run_script("scripts/runtime/config-jdk.sh", extra=env))
        self.assertEqual(profile.read_text(), first)
        self.assertEqual(envfile.read_bytes(), first_environment)
        self.assertEqual(envfile.stat().st_mtime_ns, environment_mtime)
        command = '. "$1"; . "$1"; java -version; javac -version; printf "%s" "$JAVA_HOME"'
        for shell in ("/bin/bash", "/bin/zsh"):
            with self.subTest(shell=shell):
                result = subprocess.run([shell, "-f", "-c", command, "test", str(profile)],
                                        env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assert_ok(result)
                self.assertIn("javac 1.8.0_432", result.stdout)
                self.assertIn(str(install), result.stdout)

    def test_loading_environment_prioritizes_jdk8_over_another_java(self):
        env = self.fixture_jdk()
        self.assert_ok(self.run_script("scripts/runtime/config-jdk.sh", extra=env))
        java_home = next((self.home / ".local/share/java-dev/jdk8").rglob("bin/java")).parent.parent
        other_bin = self.base / "jdk17/bin"
        other_bin.mkdir(parents=True)
        other_java = other_bin / "java"
        other_java.write_text('#!/bin/sh\necho \'openjdk version "17.0.12"\'\n')
        other_java.chmod(0o755)
        path = f"{other_bin}:{java_home}/bin:/usr/bin:/bin"
        result = subprocess.run(["/bin/bash", "-c", '. "$1"; . "$1"; java -version; printf "%s" "$PATH"',
                                 "test", str(self.home / ".config/java-dev/env.sh")],
                                env={**self.env, "PATH": path}, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assert_ok(result)
        self.assertIn('version "1.8.', result.stdout)
        self.assertEqual(result.stdout.count(str(java_home / "bin")), 1)

    def test_scan_reports_jdk_ready_but_other_missing_components_still_need_repair(self):
        result = self.run_script("scripts/check-env.sh", "--project", str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout)
        env = self.fixture_jdk()
        self.assert_ok(self.run_script("scripts/runtime/config-jdk.sh", extra=env))
        scan = self.run_script("scripts/check-env.sh")
        self.assertEqual(scan.returncode, 1, scan.stdout)
        self.assertIn("[配置完整] JAVA_8_HOME=", scan.stdout)
        self.assertIn("[配置完整] JRE_HOME=", scan.stdout)
        self.assertIn("[待修复] 独立 Gradle", scan.stdout)
        self.assert_ok(self.run_script("scripts/verify-environment.sh", "--scope", "jdk"))
        checked = self.run_script("scripts/check-env.sh", "--project", str(self.project))
        self.assertEqual(checked.returncode, 1, checked.stdout)
        self.assertIn("[待构建验证]", checked.stdout)

    def test_bad_checksum_does_not_install_or_change_shell(self):
        env = self.fixture_jdk()
        env["JDK_SHA256"] = "0" * 64
        result = self.run_script("scripts/runtime/config-jdk.sh", extra=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / ".local/share/java-dev/jdk8").exists())

    def test_wrong_java_version_does_not_install(self):
        env = self.fixture_jdk("17.0.12")
        result = self.run_script("scripts/runtime/config-jdk.sh", extra=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / ".local/share/java-dev/jdk8").exists())

    def test_download_404_does_not_leave_install(self):
        env = self.fixture_jdk()
        env["JDK_PACKAGE_PATH"] = "missing.tar.gz"
        result = self.run_script("scripts/runtime/config-jdk.sh", extra=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / ".local/share/java-dev/jdk8").exists())

    def test_complete_jdk_environment_preserves_profile_modules_and_is_idempotent(self):
        jdk = self.home / "完整 JDK's"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "jre").mkdir()
        for name, banner in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            binary = jdk / "bin" / name
            binary.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(banner) + "\n")
            binary.chmod(0o755)
        config = self.home / ".config/java-dev"
        config.mkdir(parents=True)
        environment = config / "env.sh"
        environment.write_text("export CUSTOM_ENV_SETTING='preserve this'\n")
        gradle = self.home / "已有 Gradle's"
        (gradle / "bin").mkdir(parents=True)
        gradle_module = config / "gradle.sh"
        gradle_module.write_text("export GRADLE_HOME=" + shlex.quote(str(gradle.resolve())) + "\n")
        profile = self.home / ".zshrc"
        profile.write_text("# my settings\nexport CLASSPATH='my-existing-value'\n")
        before_profile = profile.read_bytes()
        before_env = environment.read_bytes()
        extra = {"JAVA_HOME": str(jdk), "JDK_INSTALL_DIR": str(jdk), "LC_ALL": "C.UTF-8"}
        self.assert_ok(self.run_script("scripts/runtime/config-jdk.sh", extra=extra))
        self.assertTrue(profile.with_name(profile.name + ".bak").exists())
        self.assertTrue(environment.with_name(environment.name + ".bak").exists())
        self.assertEqual(profile.with_name(profile.name + ".bak").read_bytes(), before_profile)
        self.assertEqual(environment.with_name(environment.name + ".bak").read_bytes(), before_env)
        self.assertIn("my settings", profile.read_text())
        self.assertEqual(gradle_module.read_text(), "export GRADLE_HOME=" + shlex.quote(str(gradle.resolve())) + "\n")
        files = (environment, config / "jdk.sh", profile)
        before = [(file.read_bytes(), file.stat().st_mtime_ns) for file in files]
        self.assert_ok(self.run_script("scripts/runtime/config-jdk.sh", extra=extra))
        self.assertEqual([(file.read_bytes(), file.stat().st_mtime_ns) for file in files], before)
        command = '. "$1"; . "$1"; printf "%s\\0" "$JAVA_HOME" "$JAVA_8_HOME" "$JRE_HOME" "$GRADLE_HOME" "$CUSTOM_ENV_SETTING" "$CLASSPATH" "$PATH"'
        for shell in ("/bin/bash", "/bin/zsh"):
            with self.subTest(shell=shell):
                result = subprocess.run([shell, "-f", "-c", command, "test", str(profile)],
                                        env=self.env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                values = result.stdout.decode().split("\0")[:-1]
                self.assertEqual(values[:6], [str(jdk.resolve()), str(jdk.resolve()), str((jdk / "jre").resolve()),
                                              str(gradle.resolve()), "preserve this", "my-existing-value"])
                self.assertEqual(values[6].split(":")[:2], [str(jdk.resolve() / "bin"), str(gradle.resolve() / "bin")])
                self.assertEqual(values[6].split(":").count(str(jdk.resolve() / "bin")), 1)
                self.assertEqual(values[6].split(":").count(str(gradle.resolve() / "bin")), 1)
        # 用户在受管区块之后追加覆盖时，不能只因文件写入成功便宣布环境已就绪。
        with environment.open("a") as stream:
            stream.write("\nexport JAVA_8_HOME=/incorrect-jdk\n")
        result = self.run_script("scripts/runtime/config-jdk.sh", extra=extra)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("JDK 8 已就绪", result.stdout)

    def test_jdk_without_actual_jre_directory_does_not_publish_environment(self):
        jdk = self.home / "incomplete-jdk"
        (jdk / "bin").mkdir(parents=True)
        for name, banner in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            binary = jdk / "bin" / name
            binary.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(banner) + "\n")
            binary.chmod(0o755)
        result = self.run_script("scripts/runtime/config-jdk.sh", extra={"JAVA_HOME": str(jdk), "JDK_INSTALL_DIR": str(jdk)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jre", result.stdout.lower())
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / ".config/java-dev/env.sh").exists())


if __name__ == "__main__":
    unittest.main()
