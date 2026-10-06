"""Wrapper 配置前校验：真实脚本、独立 URL 缓存键与本机 HTTP 服务。"""
import hashlib
import http.server
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dev-kit/.support/scripts/runtime/config-gradle.sh"
PACKAGE_PATH = "resources/runtime/gradle/gradle-4.5.1-bin.zip"


def wrapper_key(url):
    number = int(hashlib.md5(url.encode("ascii")).hexdigest(), 16)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while number:
        number, remainder = divmod(number, 36)
        result = digits[remainder] + result
    return result or "0"


class WrapperValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Wrapper 校验 test ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.project = self.base / "Java 项目"
        self.wrapper = self.project / "gradle/wrapper"
        self.wrapper.mkdir(parents=True)
        self.marker = self.base / "wrapper-was-run"
        self.gradlew = self.project / "gradlew"
        self.gradlew.write_text(f"#!/bin/sh\ntouch '{self.marker}'\nexit 99\n")
        self.gradlew.chmod(0o640)
        (self.wrapper / "gradle-wrapper.jar").write_bytes(b"fixture wrapper jar")
        self.props = self.wrapper / "gradle-wrapper.properties"
        self.original = b"# preserve\ndistributionUrl=https\\://old.example/gradle-4.5.1-bin.zip\nzipStorePath=wrapper/dists\n"
        self.props.write_bytes(self.original)
        self.props.chmod(0o640)
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LC_ALL": "C.UTF-8", "SHELL": "/bin/zsh"}
        self.requests = []

    def server(self, status=200, delay=0, redirect=None):
        requests = self.requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                requests.append((self.command, self.path))
                if delay:
                    time.sleep(delay)
                if redirect and self.path == "/" + PACKAGE_PATH:
                    self.send_response(302)
                    self.send_header("Location", redirect)
                else:
                    self.send_response(status)
                    self.send_header("Content-Length", "500000000")
                self.end_headers()

            do_HEAD = respond
            do_GET = respond

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return {"SERVER_ADDR": f"127.0.0.1:{server.server_port}"}

    def target_url(self, extra):
        return f"http://{extra['SERVER_ADDR']}/{PACKAGE_PATH}"

    def run_script(self, extra, *args):
        return subprocess.run(["/bin/bash", str(SCRIPT), "--project", str(self.project), *args],
                              cwd=self.base, env={**self.env, **extra}, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=22)

    def snapshot(self):
        return [(path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
                for path in (self.props, self.gradlew)]

    def assert_unchanged(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(Path(str(self.props) + ".bak").exists())
        self.assertEqual(sorted(path.name for path in self.wrapper.iterdir()),
                         ["gradle-wrapper.jar", "gradle-wrapper.properties"])
        self.assertFalse(self.marker.exists())

    def cached(self, url, *, extracted=True, complete=True, ok=True,
               dist_base=None, dist_path="wrapper/dists", zip_base=None, zip_path="wrapper/dists"):
        name = "gradle-4.5.1-bin.zip"
        stem = "gradle-4.5.1-bin"
        dist_root = (dist_base or self.home / ".gradle") / dist_path / stem / wrapper_key(url)
        zip_root = (zip_base or dist_base or self.home / ".gradle") / zip_path / stem / wrapper_key(url)
        dist_root.mkdir(parents=True, exist_ok=True)
        zip_root.mkdir(parents=True, exist_ok=True)
        (zip_root / name).write_bytes(b"ZIP alone cannot provide an offline distribution")
        if ok:
            (zip_root / (name + ".ok")).touch()
        if extracted:
            distribution = dist_root / "gradle-4.5.1"
            (distribution / "bin").mkdir(parents=True)
            (distribution / "bin/gradle").write_text("#!/bin/sh\nexit 98\n")
            (distribution / "bin/gradle").chmod(0o755)
            if complete:
                (distribution / "lib").mkdir()
                (distribution / "lib/gradle-launcher-4.5.1.jar").write_bytes(b"fixture launcher")

    def test_unreachable_target_preserves_properties_backup_and_permissions(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            extra = {"SERVER_ADDR": f"127.0.0.1:{reserved.getsockname()[1]}"}
            before = self.snapshot()
            result = self.run_script(extra)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(self.target_url(extra), result.stdout)
        self.assert_unchanged(before)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_http_404_preserves_properties_backup_and_permissions(self):
        extra = self.server(status=404)
        before = self.snapshot()
        result = self.run_script(extra)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assert_unchanged(before)
        self.assertEqual(self.requests, [("HEAD", "/" + PACKAGE_PATH)])

    def test_reachable_target_uses_head_and_keeps_team_url(self):
        extra = self.server()
        result = self.run_script(extra)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.requests, [("HEAD", "/" + PACKAGE_PATH)])
        self.assertIn("distributionUrl=" + self.target_url(extra).replace(":", "\\:", 1), self.props.read_text())
        self.assertEqual(Path(str(self.props) + ".bak").read_bytes(), self.original)
        self.assertTrue(self.gradlew.stat().st_mode & 0o100)
        self.assertIn("配置文件已更新", result.stdout)
        self.assertIn("尚未运行", result.stdout)
        self.assertFalse(self.marker.exists())

    def test_redirect_checks_final_http_target_with_head(self):
        extra = self.server(redirect="/actual.zip")
        result = self.run_script(extra)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.requests, [("HEAD", "/" + PACKAGE_PATH), ("HEAD", "/actual.zip")])
        self.assertIn(self.target_url(extra).replace(":", "\\:", 1), self.props.read_text())

    def test_exact_target_cache_can_be_reused_without_network(self):
        extra = self.server(status=503)
        self.cached(self.target_url(extra))
        result = self.run_script(extra)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("缓存完整", result.stdout)
        self.assertEqual(self.requests, [])
        self.assertIn(self.target_url(extra).replace(":", "\\:", 1), self.props.read_text())
        self.assertFalse(self.marker.exists())

    def test_other_url_same_version_cache_does_not_skip_target_validation(self):
        extra = self.server(status=404)
        self.cached("https://services.gradle.org/distributions/gradle-4.5.1-bin.zip")
        before = self.snapshot()
        result = self.run_script(extra)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assert_unchanged(before)
        self.assertEqual(self.requests, [("HEAD", "/" + PACKAGE_PATH)])

    def test_zip_only_or_incomplete_target_cache_cannot_be_reused_offline(self):
        for fixture in ({"extracted": False}, {"complete": False}, {"ok": False}):
            with self.subTest(fixture=fixture):
                extra = self.server(status=404)
                self.cached(self.target_url(extra), **fixture)
                before = self.snapshot()
                result = self.run_script(extra)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assert_unchanged(before)
        self.assertEqual([method for method, _ in self.requests], ["HEAD", "HEAD", "HEAD"])

    def test_cache_validation_honors_project_distribution_and_custom_zip_home(self):
        extra = self.server(status=503)
        cache_home = self.base / "custom cache's"
        extra["GRADLE_USER_HOME"] = str(cache_home)
        self.props.write_bytes(self.original + b"distributionBase=PROJECT\ndistributionPath=cache\\ area\n"
                               b"zipStoreBase=GRADLE_USER_HOME\nzipStorePath=zip\\ store\n")
        self.cached(self.target_url(extra), dist_base=self.project, dist_path="cache area",
                    zip_base=cache_home, zip_path="zip store")
        result = self.run_script(extra)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("缓存完整", result.stdout)
        self.assertEqual(self.requests, [])

    def test_dry_run_does_not_contact_server_or_mutate_files(self):
        extra = self.server()
        before = self.snapshot()
        result = self.run_script(extra, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.requests, [])
        self.assert_unchanged(before)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_stalled_head_times_out_before_any_file_change(self):
        extra = self.server(delay=20)
        before = self.snapshot()
        started = time.monotonic()
        result = self.run_script(extra)
        elapsed = time.monotonic() - started
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertLess(elapsed, 18)
        self.assert_unchanged(before)


if __name__ == "__main__":
    unittest.main()
