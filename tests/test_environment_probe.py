"""只读环境探测：模拟 JDK 与真实微型缓存结构，绝不运行 Gradle。"""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.5.1"
URL = "http://intranet.example:8081/resources/runtime/gradle/gradle-4.5.1-bin.zip"


def url_hash(url):
    value = int(hashlib.md5(url.encode()).hexdigest(), 16)
    encoded = ""
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded or "0"


class EnvironmentProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="环境检查's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具 目录/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.project = self.base / "业务 项目's"
        self.project.mkdir()
        wrapper = self.project / "gradle/wrapper"
        wrapper.mkdir(parents=True)
        (wrapper / "gradle-wrapper.jar").write_bytes(b"fixture wrapper jar")
        self.marker = self.base / "should-not-run"
        (self.project / "gradlew").write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.marker)) + "\n")
        (self.project / "gradlew").chmod(0o755)
        self.props = wrapper / "gradle-wrapper.properties"
        self.write_props()
        self.cache = self.home / ".gradle"
        self.env_file = self.home / ".config/java-dev/env.sh"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LC_ALL": "C.UTF-8", "JDK_AUTO_DETECT": "false", "JAVA_HOME": "",
                    "JDK_INSTALL_DIR": str(self.home / "missing-jdk"), "ENV_FILE": str(self.env_file),
                    "GRADLE_VERSION": VERSION, "CDPATH": str(self.base)}

    def write_props(self, url=URL, extra="", crlf=False):
        contents = "distributionUrl=" + url.replace(":", "\\:") + "\n" + extra
        if crlf:
            contents = contents.replace("\n", "\r\n")
        self.props.write_bytes(contents.encode())

    def jdk(self, name="JDK 8", java='openjdk version "1.8.0_432"', javac="javac 1.8.0_432"):
        root = self.base / name
        (root / "bin").mkdir(parents=True)
        for executable, banner in (("java", java), ("javac", javac)):
            path = root / "bin" / executable
            path.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(banner) + " >&2\n")
            path.chmod(0o755)
        return root

    def distribution(self, root, version=VERSION):
        (root / "bin").mkdir(parents=True)
        (root / "lib").mkdir()
        executable = root / "bin/gradle"
        executable.write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.marker)) + "\nexit 99\n")
        executable.chmod(0o755)
        (root / f"lib/gradle-launcher-{version}.jar").write_bytes(b"fixture launcher")
        return root

    def cached(self, url=URL, dist_base=None, dist_path="wrapper/dists", zip_base=None,
               zip_path="wrapper/dists", complete=True, ok=True):
        name = url.split("?")[0].rsplit("/", 1)[1]
        stem = name.rsplit(".", 1)[0]
        dist_root = (dist_base or self.cache) / dist_path / stem / url_hash(url)
        zip_root = (zip_base or dist_base or self.cache) / zip_path / stem / url_hash(url)
        dist_root.mkdir(parents=True, exist_ok=True)
        zip_root.mkdir(parents=True, exist_ok=True)
        app = dist_root / f"gradle-{VERSION}"
        if complete:
            self.distribution(app)
        else:
            (zip_root / name).write_bytes(b"only a downloaded zip")
        if ok:
            (zip_root / (name + ".ok")).touch()
        return app

    def probe(self, kind="gradle", project=True, override=None, extra=None):
        variables = ("PROBE_JDK_HOME", "PROBE_JDK_SOURCE", "PROBE_JDK_VERSION", "JAVA_HOME", "PATH") if kind == "jdk" else (
            "PROBE_GRADLE_STATE", "PROBE_GRADLE_PATH", "PROBE_GRADLE_URL", "PROBE_GRADLE_NOTE",
            "PROBE_GRADLE_GLOBAL_COMMAND", "PROBE_GRADLE_GLOBAL_VERSION", "PROBE_GRADLE_CACHED_PATHS",
            "PROBE_WRAPPER_MISSING")
        action = "probe_jdk8" if kind == "jdk" else "probe_gradle " + shlex.quote(str(self.project) if project else "")
        if override is not None:
            action += " " + shlex.quote(override)
        script = "set -euo pipefail\nsource \"$1/scripts/lib/common.sh\"\nsource \"$1/scripts/lib/environment.sh\"\n" + action + "\n"
        script += "printf '%s\\0' " + " ".join('"${' + key + '-}"' for key in variables) + "\n"
        result = subprocess.run(["/bin/bash", "-c", script, "probe", str(self.support)],
                                cwd=self.base, env={**self.env, **(extra or {})}, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        values = result.stdout.decode().split("\0")[:-1]
        self.assertEqual(len(values), len(variables), result.stdout)
        return dict(zip(variables, values))

    def snapshot(self):
        return {str(path.relative_to(self.base)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.base.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_project_cache_requires_exact_url_and_complete_distribution(self):
        cached = self.cached()
        result = self.probe()
        self.assertEqual(result["PROBE_GRADLE_STATE"], "project_cached")
        self.assertEqual(result["PROBE_GRADLE_PATH"], str(cached))
        self.assertEqual(result["PROBE_GRADLE_URL"], URL)
        self.assertEqual(result["PROBE_GRADLE_CACHED_PATHS"], "")
        self.assertFalse(self.marker.exists())

    def test_wrong_url_cache_is_inventory_not_project_cache(self):
        other_url = URL.replace("intranet.example:8081", "another.example:9000")
        cached = self.cached(other_url)
        result = self.probe()
        self.assertEqual(result["PROBE_GRADLE_STATE"], "project_missing")
        self.assertEqual(result["PROBE_GRADLE_CACHED_PATHS"], str(cached))
        self.assertEqual(result["PROBE_GRADLE_PATH"], "")

    def test_zip_only_and_missing_ok_marker_do_not_count_as_installed(self):
        self.cached(complete=False)
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")
        shutil.rmtree(self.cache)
        self.cached(ok=False)
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")

    def test_truncated_launchers_and_ambiguous_versions_are_not_complete_cache(self):
        app = self.cached()
        for relative in ("bin/gradle", f"lib/gradle-launcher-{VERSION}.jar"):
            with self.subTest(relative=relative):
                path = app / relative
                original = path.read_bytes()
                path.write_bytes(b"")
                result = self.probe()
                self.assertEqual(result["PROBE_GRADLE_STATE"], "project_missing")
                self.assertEqual(result["PROBE_GRADLE_CACHED_PATHS"], "")
                path.write_bytes(original)
        (app / "lib/gradle-launcher-8.0.jar").write_bytes(b"another launcher")
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")
        self.assertFalse(self.marker.exists())

    def test_multiple_top_level_directories_and_wrong_launcher_are_incomplete(self):
        app = self.cached()
        (app.parent / "unexpected").mkdir()
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")
        (app.parent / "unexpected").rmdir()
        (app / f"lib/gradle-launcher-{VERSION}.jar").unlink()
        (app / "lib/gradle-launcher-8.0.jar").touch()
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")

    def test_custom_project_distribution_and_separate_zip_store_with_spaces_and_crlf(self):
        user_cache = self.base / "自定义 cache's"
        self.write_props(extra="distributionBase=PROJECT\ndistributionPath=cache\\ area's\n"
                         "zipStoreBase=GRADLE_USER_HOME\nzipStorePath=zip\\ store\n", crlf=True)
        app = self.cached(dist_base=self.project, dist_path="cache area's", zip_base=user_cache, zip_path="zip store")
        result = self.probe(extra={"GRADLE_USER_HOME": str(user_cache)})
        self.assertEqual(result["PROBE_GRADLE_STATE"], "project_cached")
        self.assertEqual(result["PROBE_GRADLE_PATH"], str(app))

    def test_url_override_uses_prospective_url_and_preserves_properties(self):
        other = URL.replace("intranet.example:8081", "old.example")
        self.write_props(other)
        self.cached()
        before = self.props.read_bytes()
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")
        result = self.probe(override=URL)
        self.assertEqual(result["PROBE_GRADLE_STATE"], "project_cached")
        self.assertEqual(result["PROBE_GRADLE_URL"], URL)
        self.assertEqual(self.props.read_bytes(), before)

    def test_unsupported_properties_uri_and_jvm_home_overrides_are_unknown(self):
        for extra_props in ("distributionPath=cache\\\n next\n", "distributionBase=PROJECT_PATH\n",
                            "distributionPath=\\u4e2d\n"):
            with self.subTest(extra_props=extra_props):
                self.write_props(extra=extra_props)
                result = self.probe()
                self.assertEqual(result["PROBE_GRADLE_STATE"], "unknown")
                self.assertTrue(result["PROBE_GRADLE_NOTE"])
        self.write_props(url="http://user:password@intranet.example/gradle.zip")
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "unknown")
        self.write_props()
        for name in ("JAVA_OPTS", "GRADLE_OPTS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS"):
            with self.subTest(name=name):
                result = self.probe(extra={name: '-Dgradle.user.home="/other cache"'})
                self.assertEqual(result["PROBE_GRADLE_STATE"], "unknown")

    def test_missing_wrapper_is_listed_without_execution(self):
        (self.project / "gradle/wrapper/gradle-wrapper.jar").unlink()
        result = self.probe()
        self.assertEqual(result["PROBE_GRADLE_STATE"], "wrapper_missing")
        self.assertIn("gradle/wrapper/gradle-wrapper.jar", result["PROBE_WRAPPER_MISSING"])
        self.assertFalse(self.marker.exists())

    def test_no_project_lists_complete_inventory_and_gradle_home_without_executing(self):
        app = self.cached()
        global_home = self.distribution(self.base / "全局 Gradle's", version="8.10")
        before = self.snapshot()
        result = self.probe(project=False, extra={"GRADLE_HOME": str(global_home)})
        self.assertEqual(result["PROBE_GRADLE_STATE"], "no_project")
        self.assertEqual(result["PROBE_GRADLE_CACHED_PATHS"], str(app))
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_COMMAND"], str(global_home / "bin/gradle"))
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_VERSION"], "8.10")
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.snapshot(), before)

    def test_no_project_with_jvm_override_labels_inventory_as_default_only(self):
        app = self.cached()
        result = self.probe(project=False, extra={"JAVA_OPTS": "-Dgradle.user.home=/elsewhere"})
        self.assertEqual(result["PROBE_GRADLE_STATE"], "no_project")
        self.assertEqual(result["PROBE_GRADLE_CACHED_PATHS"], str(app))
        self.assertIn("默认", result["PROBE_GRADLE_NOTE"])

    def test_non_ascii_uri_is_unknown_because_jvm_encoding_is_not_known(self):
        self.write_props(url="http://intranet.example/下载/gradle-4.5.1-bin.zip")
        result = self.probe()
        self.assertEqual(result["PROBE_GRADLE_STATE"], "unknown")
        self.assertIn("字符", result["PROBE_GRADLE_NOTE"])

    def test_path_gradle_unknown_version_is_reported_without_running_it(self):
        fake_bin = self.base / "PATH bin"
        fake_bin.mkdir()
        gradle = fake_bin / "gradle"
        gradle.write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.marker)) + "\n")
        gradle.chmod(0o755)
        result = self.probe(project=False, extra={"PATH": f"{fake_bin}:/usr/bin:/bin"})
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_COMMAND"], str(gradle))
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_VERSION"], "")
        self.assertFalse(self.marker.exists())

    def test_path_symlink_to_distribution_can_infer_version(self):
        app = self.distribution(self.base / "Gradle 分发", version="7.6.4")
        fake_bin = self.base / "bin"
        fake_bin.mkdir()
        command = fake_bin / "gradle"
        command.symlink_to(app / "bin/gradle")
        result = self.probe(project=False, extra={"PATH": f"{fake_bin}:/usr/bin:/bin"})
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_COMMAND"], str(command))
        self.assertEqual(result["PROBE_GRADLE_GLOBAL_VERSION"], "7.6.4")
        self.assertFalse(self.marker.exists())

    def test_wrong_java_or_javac_is_not_selected(self):
        wrong = self.jdk(java='openjdk version "17.0.1"', javac="javac 17.0.1")
        result = self.probe(kind="jdk", extra={"JAVA_HOME": str(wrong)})
        self.assertEqual(result["PROBE_JDK_HOME"], "")
        mixed = self.jdk(name="mixed JDK", javac="javac 17.0.1")
        result = self.probe(kind="jdk", extra={"JDK_INSTALL_DIR": str(mixed)})
        self.assertEqual(result["PROBE_JDK_HOME"], "")
        self.assertEqual(result["PROBE_JDK_SOURCE"], "")

    def test_generated_environment_is_detected_without_changing_caller(self):
        saved = self.jdk(name="已保存 JDK's")
        current = self.jdk(name="环境 JDK")
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text("export JAVA_HOME=" + shlex.quote(str(saved)) + "\nexport PATH=/nowhere\n")
        before = self.snapshot()
        result = self.probe(kind="jdk", extra={"JAVA_HOME": str(current)})
        self.assertEqual(result["PROBE_JDK_HOME"], str(saved))
        self.assertEqual(result["PROBE_JDK_SOURCE"], "env_file")
        self.assertEqual(result["PROBE_JDK_VERSION"], "1.8.0_432")
        self.assertEqual(result["JAVA_HOME"], str(current))
        self.assertEqual(result["PATH"], self.env["PATH"])
        self.assertEqual(self.snapshot(), before)

    def test_environment_and_managed_jdk_fallback(self):
        jdk = self.jdk()
        result = self.probe(kind="jdk", extra={"JAVA_HOME": str(jdk)})
        self.assertEqual(result["PROBE_JDK_SOURCE"], "environment")
        managed = self.base / "managed"
        managed.mkdir()
        shutil.move(str(jdk), str(managed / "nested.jdk"))
        result = self.probe(kind="jdk", extra={"JDK_INSTALL_DIR": str(managed)})
        self.assertEqual(result["PROBE_JDK_SOURCE"], "managed")
        self.assertEqual(result["PROBE_JDK_HOME"], str(managed / "nested.jdk"))

    def test_java_symlink_to_system_shim_is_never_passed_to_version_detection(self):
        root = self.base / "shim JDK"
        (root / "bin").mkdir(parents=True)
        # 用依赖边界记录替代真正的版本检测，避免红灯阶段触发 macOS 安装提示。
        script = ('set -euo pipefail\nsource "$1/scripts/lib/common.sh"\n'
                  'source "$1/scripts/lib/environment.sh"\n'
                  'shim_called=0\nis_jdk8() { shim_called=1; return 1; }\n'
                  'probe_jdk8\nprintf "%s" "$shim_called"\n')
        for shim in ("java", "javac"):
            with self.subTest(shim=shim):
                for name in ("java", "javac"):
                    executable = root / "bin" / name
                    if executable.exists() or executable.is_symlink():
                        executable.unlink()
                    if name == shim:
                        executable.symlink_to("/usr/bin/" + name)
                    else:
                        executable.write_text("#!/bin/sh\nexit 99\n")
                        executable.chmod(0o755)
                result = subprocess.run(["/bin/bash", "-c", script, "probe", str(self.support)],
                                        cwd=self.base, env={**self.env, "JAVA_HOME": str(root)},
                                        text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "0")

    def test_checks_do_not_create_gradle_cache_or_execute_property_text(self):
        self.write_props(extra="distributionPath=cache $(touch " + str(self.marker) + ")\n")
        before = self.snapshot()
        self.assertEqual(self.probe()["PROBE_GRADLE_STATE"], "project_missing")
        self.assertEqual(self.probe(kind="jdk")["PROBE_JDK_HOME"], "")
        self.assertFalse(self.cache.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
