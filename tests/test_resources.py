"""用本地 HTTP 服务与真实 curl 验证资源准备，不下载实际安装包。"""
import hashlib
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/prepare-resources.sh"
HEADER = "# id\tgroup\tversion\tarch\tpath\turl\tsha256\n"
PAYLOAD = b"official fixture archive\n"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class ResourceHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/archive")
            self.end_headers()
        elif self.path == "/unsafe-redirect":
            self.send_response(302)
            self.send_header("Location", "file:///etc/hosts")
            self.end_headers()
        elif self.path == "/missing":
            self.send_error(404)
        elif self.path == "/partial-once" and self.server.requests.count(self.path) == 1:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD[:3])
            self.close_connection = True
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="资源 ' test ")
        # macOS 的 /var 是系统符号链接；测试使用物理路径。
        self.base = Path(self.temp.name).resolve()
        self.output = self.base / "离线 资源's"
        self.catalog = self.base / "资源 清单.tsv"
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ResourceHandler)
        self.httpd.requests = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.base), "LC_ALL": "C"}

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.temp.cleanup()

    def row(self, ident="jdk", group="runtime", path="runtime/jdk/包 archive.tar.gz",
            sha=SHA, endpoint="/archive"):
        return [ident, group, "8.0.1", "macos-arm64", path, self.url + endpoint, sha]

    def write_catalog(self, *rows):
        self.catalog.write_text(HEADER + "".join("\t".join(row) + "\n" for row in rows))

    def run_script(self, *args, output=None):
        return subprocess.run(["/bin/bash", str(SCRIPT), "--catalog", str(self.catalog),
                               "--output", str(output or self.output), *args],
                              cwd=self.base, env=self.env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def target(self, row):
        return self.output / row[4]

    def seed(self, row, content=PAYLOAD, receipt=True):
        target = self.target(row)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if receipt:
            Path(str(target) + ".sha256").write_text(SHA + "  " + target.name + "\n")
        return target

    def test_download_atomic_receipt_and_reuse_from_unrelated_directory(self):
        row = self.row(endpoint="/redirect")
        self.write_catalog(row)
        self.assert_ok(self.run_script())
        target = self.target(row)
        self.assertEqual(target.read_bytes(), PAYLOAD)
        self.assertEqual(Path(str(target) + ".sha256").read_text(), SHA + "  " + target.name + "\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertEqual(Path(str(target) + ".sha256").stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.httpd.requests, ["/redirect", "/archive"])
        stamp = target.stat().st_mtime_ns
        self.assert_ok(self.run_script())
        self.assertEqual(target.stat().st_mtime_ns, stamp)
        self.assertEqual(self.httpd.requests, ["/redirect", "/archive"])
        self.assertFalse(list(self.output.rglob("*.part*")))

    def test_partial_transfer_is_retried_and_utf8_failure_message_is_readable(self):
        self.env["LC_ALL"] = "C.UTF-8"
        row = self.row(endpoint="/partial-once")
        self.write_catalog(row)
        self.assert_ok(self.run_script())
        self.assertEqual(self.target(row).read_bytes(), PAYLOAD)
        row = self.row(ident="missing", path="runtime/missing.zip", endpoint="/missing")
        self.write_catalog(row)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("下载失败", result.stdout)

    def test_no_upstream_hash_download_records_local_hash_and_detects_corruption(self):
        row = self.row(sha="-")
        self.write_catalog(row)
        result = self.run_script()
        self.assert_ok(result)
        self.assertIn("本地", result.stdout)
        self.assert_ok(self.run_script("--verify"))
        self.target(row).write_bytes(b"tampered")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.target(row).read_bytes(), b"tampered")
        self.assertEqual(self.httpd.requests, ["/archive"])

    def test_existing_unverified_file_is_preserved_and_requires_review(self):
        row = self.row(sha="-")
        self.write_catalog(row)
        target = self.seed(row, receipt=False)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("审核", result.stdout)
        self.assertEqual(target.read_bytes(), PAYLOAD)
        self.assertFalse(Path(str(target) + ".sha256").exists())
        self.assertEqual(self.httpd.requests, [])

    def test_upstream_hash_repairs_receipt_without_redownload(self):
        row = self.row()
        self.write_catalog(row)
        target = self.seed(row)
        receipt = Path(str(target) + ".sha256")
        receipt.write_text("0" * 64 + "  " + target.name + "\n")
        self.assert_ok(self.run_script())
        self.assertEqual(receipt.read_text(), SHA + "  " + target.name + "\n")
        self.assertEqual(self.httpd.requests, [])

    def test_existing_upstream_mismatch_is_never_overwritten(self):
        row = self.row()
        self.write_catalog(row)
        target = self.seed(row, content=b"keep my manually placed file")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("移走", result.stdout)
        self.assertEqual(target.read_bytes(), b"keep my manually placed file")
        self.assertEqual(self.httpd.requests, [])

    def test_failed_downloads_leave_no_final_file_or_partial(self):
        for endpoint, sha in (("/missing", SHA), ("/archive", "0" * 64),
                              ("/unsafe-redirect", SHA)):
            with self.subTest(endpoint=endpoint, sha=sha):
                row = self.row(endpoint=endpoint, sha=sha)
                self.write_catalog(row)
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse(self.target(row).exists())
                self.assertFalse(Path(str(self.target(row)) + ".sha256").exists())
                self.assertFalse([p for p in self.output.rglob("*") if p.is_file()])

    def test_dry_run_selects_group_without_network_or_writes(self):
        self.write_catalog(self.row(), self.row("idea", "software", "software/idea.dmg"),
                           self.row("lombok", "plugins", "plugins/lombok.zip"))
        result = self.run_script("--group", "plugins", "--dry-run")
        self.assert_ok(result)
        self.assertIn("lombok", result.stdout)
        self.assertNotIn("idea.dmg", result.stdout)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.httpd.requests, [])

    def test_download_group_preserves_unknown_files(self):
        runtime, software = self.row(), self.row("idea", "software", "software/idea.dmg")
        self.write_catalog(runtime, software)
        self.output.mkdir()
        extra = self.output / "my-resource.txt"
        extra.write_text("keep")
        self.assert_ok(self.run_script("--group", "software"))
        self.assertFalse(self.target(runtime).exists())
        self.assertEqual(self.target(software).read_bytes(), PAYLOAD)
        self.assertEqual(extra.read_text(), "keep")

    def test_id_and_arch_filters_include_common_artifacts_and_reject_unknown_id(self):
        arm = self.row("arm", path="runtime/arm.tar.gz")
        intel = self.row("intel", path="runtime/intel.tar.gz")
        intel[3] = "x64"
        common = self.row("gradle", path="runtime/gradle.zip")
        common[3] = "any"
        self.write_catalog(arm, intel, common)
        result = self.run_script("--arch", "arm64", "--dry-run")
        self.assert_ok(result)
        self.assertIn("arm.tar.gz", result.stdout)
        self.assertIn("gradle.zip", result.stdout)
        self.assertNotIn("intel.tar.gz", result.stdout)
        self.assert_ok(self.run_script("--id", "intel"))
        self.assertEqual(self.target(intel).read_bytes(), PAYLOAD)
        self.assertFalse(self.target(arm).exists())
        self.assertFalse(self.target(common).exists())
        self.assertNotEqual(self.run_script("--id", "missing").returncode, 0)
        self.assertNotEqual(self.run_script("--arch", "unsupported").returncode, 0)
        self.assertEqual(self.httpd.requests, ["/archive"])

    def test_verify_is_read_only_and_fails_for_missing_resources(self):
        row = self.row()
        self.write_catalog(row)
        self.assertNotEqual(self.run_script("--verify").returncode, 0)
        self.assertFalse(self.output.exists())
        target = self.seed(row, receipt=False)
        before = target.stat().st_mtime_ns
        self.assert_ok(self.run_script("--verify"))
        self.assertFalse(Path(str(target) + ".sha256").exists())
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual(self.httpd.requests, [])

    def test_bad_catalog_is_fully_validated_before_any_download(self):
        valid = self.row()
        invalid_rows = [
            self.row("bad", "unknown", "other.zip"),
            self.row("bad", path="/absolute.zip"),
            self.row("bad", path="../escape.zip"),
            self.row("bad", path="safe/../escape.zip"),
            self.row("bad", path="safe//double.zip"),
            self.row("bad", path="./dot.zip"),
            self.row("bad", sha="1234"),
            self.row("bad", sha=""),
            self.row("bad") + ["extra"],
            self.row("bad")[:5],
            self.row("jdk", path="duplicate-id.zip"),
            self.row("bad", path=valid[4]),
            self.row("bad", path=valid[4] + ".sha256"),
            self.row("bad", path="runtime/jdk"),
            ["bad", "runtime", "", "macos-arm64", "other.zip", self.url + "/archive", SHA],
            ["bad", "runtime", "1", "macos-arm64", "other.zip", "file:///etc/hosts", SHA],
        ]
        for invalid in invalid_rows:
            with self.subTest(invalid=invalid):
                self.write_catalog(valid, invalid)
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.httpd.requests, [])

    def test_unknown_group_and_conflicting_modes_fail_without_writes(self):
        self.write_catalog(self.row())
        for args in (("--group", "bad"), ("--dry-run", "--verify"), ("--group",), ("--unknown",)):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_script(*args).returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.httpd.requests, [])

    def test_symlink_and_directory_conflicts_rejected_before_download(self):
        valid, second = self.row(), self.row("idea", "software", "software/idea.dmg")
        self.write_catalog(valid, second)
        outside = self.base / "outside"
        outside.mkdir()
        for bad_path, directory in (("software", True), ("software/idea.dmg", False),
                                    ("software/idea.dmg.sha256", False)):
            with self.subTest(bad_path=bad_path):
                target = self.output / bad_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(outside if directory else outside / "not-created")
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse(self.target(valid).exists())
                self.assertEqual(self.httpd.requests, [])
                target.unlink()
        self.target(second).mkdir()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.httpd.requests, [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_output_directory_symlink_and_non_directory_ancestor_rejected(self):
        self.write_catalog(self.row())
        outside = self.base / "outside"
        outside.mkdir()
        self.output.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.output.unlink()
        self.output.write_text("existing file")
        self.assertNotEqual(self.run_script(output=self.output / "nested").returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.httpd.requests, [])

    def test_receipt_requires_matching_name_and_single_valid_digest(self):
        row = self.row(sha="-")
        self.write_catalog(row)
        target = self.seed(row)
        receipt = Path(str(target) + ".sha256")
        for bad in (SHA + "  another.zip\n", "malformed\n", SHA + "  " + target.name + "\nextra\n"):
            with self.subTest(receipt=bad):
                receipt.write_text(bad)
                self.assertNotEqual(self.run_script("--verify").returncode, 0)
                self.assertEqual(receipt.read_text(), bad)
        self.assertEqual(self.httpd.requests, [])

    def test_defaults_are_relative_to_script_not_current_directory(self):
        repo = self.base / "副本 项目"
        (repo / "tools").mkdir(parents=True)
        (repo / "resources").mkdir()
        shutil.copy2(SCRIPT, repo / "tools/prepare-resources.sh")
        row = self.row()
        (repo / "resources/catalog.tsv").write_text(HEADER + "\t".join(row) + "\n")
        result = subprocess.run(["/bin/bash", str(repo / "tools/prepare-resources.sh")],
                                cwd=self.base, env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((repo / "resources" / row[4]).read_bytes(), PAYLOAD)
        self.assertFalse((self.base / "resources").exists())


if __name__ == "__main__":
    unittest.main()
