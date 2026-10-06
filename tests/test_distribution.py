"""运行真实打包与启动脚本；微型工具包避免启动实际安装程序。"""
import functools
import hashlib
import http.server
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
KIT_FILES = tuple(line for line in (ROOT / "tools/package-files.txt").read_text().splitlines()
                  if line and not line.startswith("#"))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="分发 ' test ")
        # macOS 的 /var 是系统符号链接；安全路径测试使用物理目录。
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "工具 源码's"
        self.repo.mkdir()
        shutil.copytree(ROOT / "tools", self.repo / "tools")
        shutil.copytree(ROOT / "server", self.repo / "server")
        self.kit = self.repo / "dev-kit"
        self.kit_files = tuple(line for line in (self.repo / "tools/package-files.txt")
                               .read_text(encoding="utf-8").splitlines()
                               if line and not line.startswith("#"))
        for name in self.kit_files:
            path = self.kit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# fixture\n")
            path.chmod(0o755 if name.endswith((".sh", ".command")) else 0o644)
        (self.kit / ".support/config/env.sh").write_text(
            'SERVER_ADDR="${SERVER_ADDR:-config.example:8088}"\n'
            'SERVER_SCHEME="${SERVER_SCHEME:-http}"\n'
        )
        (self.kit / "开始配置.command").write_text(
            '#!/bin/bash\n'
            'printf "%s\\n" "$SERVER_ADDR" "$SERVER_SCHEME" "$@" > "$RESULT_FILE"\n'
            'exit "${PAYLOAD_EXIT_CODE:-0}"\n'
        )
        self.home = self.base / "home"
        self.home.mkdir()
        self.tmp = self.base / "downloads"
        self.tmp.mkdir()
        self.output = self.base / "分发 目录's"
        self.result_file = self.base / "payload-result"
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
                    "TMPDIR": str(self.tmp), "LC_ALL": "C", "RESULT_FILE": str(self.result_file)}
        self.httpd = None

    def tearDown(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join()
        self.temp.cleanup()

    def package(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.repo / "tools/package.sh"),
                               "--output", str(self.output), *args], cwd=self.base,
                              env={**self.env, **(extra or {})}, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def launch(self, *args, extra=None, launcher=None):
        return subprocess.run(["/bin/bash", str(launcher or self.output / "start.command"), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def resources(self, *, unpinned=False, location=None):
        catalog = (location or self.repo / "resources") / "catalog.tsv"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        storage = location or catalog.parent
        entries = [("jdk8", "runtime", "8", "arm64", "runtime/jdk8.tar.gz", b"fixture jdk"),
                   ("setter", "plugins", "2.8.5", "any", "plugins/setter.zip", b"fixture plugin")]
        rows = ["# id\tgroup\tversion\tarch\tpath\turl\tsha256"]
        for resource_id, group, version, arch, relative, payload in entries:
            target = storage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            target.with_name(target.name + ".sha256").write_text(f"{digest}  {target.name}\n")
            rows.append("\t".join((resource_id, group, version, arch, relative,
                                    "https://official.invalid/" + relative,
                                    "-" if unpinned else digest)))
        catalog.write_text("\n".join(rows) + "\n")
        return storage, entries

    def published_files(self):
        return {str(path.relative_to(self.output)): path.read_bytes()
                for path in self.output.rglob("*") if path.is_file() and not path.is_symlink()}

    def serve(self, directory=None):
        handler = functools.partial(QuietHandler, directory=str(directory or self.output))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return f"127.0.0.1:{self.httpd.server_port}"

    def replace_payload(self, members):
        archive = self.output / "dev-env/team-dev-env.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name, content, kind in members:
                info = tarfile.TarInfo(name)
                info.mode = 0o755
                if kind == "file":
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
                else:
                    info.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                    info.linkname = content.decode()
                    tar.addfile(info)
        archive.with_suffix(".gz.sha256").write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  team-dev-env.tar.gz\n")

    def test_package_allowlist_checksums_and_executable_zip(self):
        for name in (".env", ".support/config/team.sh", ".support/config/passwords.txt",
                     "tests/test_private.py", "docs/internal.md", "__pycache__/cache.pyc"):
            path = self.kit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PRIVATE-MAINTAINER-DATA")
        self.assert_ok(self.package("--server", "intranet.example:9000", "--scheme", "https"))
        archive = self.output / "dev-env/team-dev-env.tar.gz"
        self.assertEqual(archive.with_suffix(".gz.sha256").read_text().split()[0],
                         hashlib.sha256(archive.read_bytes()).hexdigest())
        with tarfile.open(archive) as tar:
            names = {member.name for member in tar.getmembers() if member.isfile()}
            self.assertEqual(names, {"team-dev-env/" + name for name in self.kit_files} |
                             {"team-dev-env/.support/config/team.sh",
                              "team-dev-env/.support/config/resources.tsv",
                              "team-dev-env/.support/scripts/prepare-resources.sh"})
            self.assertTrue(tar.extractfile("team-dev-env/.support/config/resources.tsv")
                            .read().startswith(b"# id\tgroup\tversion\tarch\tpath\turl\tsha256\n"))
            self.assertEqual(tar.getmember("team-dev-env/开始配置.command").mode & 0o777, 0o755)
            for member in tar.getmembers():
                if member.isfile():
                    self.assertNotIn(b"PRIVATE-MAINTAINER-DATA", tar.extractfile(member).read())
            tar.extractall(self.base / "moved folder")
        config = self.base / "moved folder/team-dev-env/.support/config/team.sh"
        result = subprocess.run(["/bin/bash", "-c", 'source "$1"; printf "%s %s" "$SERVER_ADDR" "$SERVER_SCHEME"',
                                 "_", str(config)], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.stdout, "intranet.example:9000 https")
        result = subprocess.run(["/bin/bash", "-c", 'source "$1"; printf "%s %s" "$SERVER_ADDR" "$SERVER_SCHEME"',
                                 "_", str(config)], env={**self.env, "SERVER_ADDR": "other:81", "SERVER_SCHEME": "http"},
                                text=True, capture_output=True)
        self.assertEqual(result.stdout, "other:81 http")
        with zipfile.ZipFile(self.output / "team-dev-env.zip") as zipped:
            self.assertEqual({i.filename for i in zipped.infolist() if not i.is_dir()}, names)
            self.assertEqual((zipped.getinfo("team-dev-env/开始配置.command").external_attr >> 16) & 0o777, 0o755)
        with zipfile.ZipFile(self.output / "start.zip") as zipped:
            self.assertEqual(zipped.namelist(), ["开始配置.command"])
            self.assertEqual(zipped.read("开始配置.command"), (self.output / "start.command").read_bytes())
            self.assertEqual((zipped.getinfo("开始配置.command").external_attr >> 16) & 0o777, 0o755)

    def test_catalog_resolves_receipts_without_copying_resource_files_into_archives(self):
        _, entries = self.resources(unpinned=True)
        self.assert_ok(self.package())
        self.assertFalse((self.output / "resources").exists())
        with tarfile.open(self.output / "dev-env/team-dev-env.tar.gz") as archive:
            self.assertIn("team-dev-env/.support/config/resources.tsv", archive.getnames())
            manifest = archive.extractfile("team-dev-env/.support/config/resources.tsv").read().decode()
            for resource_id, group, version, arch, relative, payload in entries:
                self.assertIn("\t".join((resource_id, group, version, arch, relative,
                              "https://official.invalid/" + relative,
                              hashlib.sha256(payload).hexdigest())), manifest)
            self.assertFalse(any("runtime/jdk8.tar.gz" in item.name for item in archive.getmembers()))
            self.assertEqual(archive.extractfile("team-dev-env/.support/scripts/prepare-resources.sh").read(),
                             (self.repo / "tools/prepare-resources.sh").read_bytes())

    def test_with_resources_exports_only_catalog_files_and_reuses_existing_files(self):
        custom = self.base / "缓存 ' resources"
        storage, entries = self.resources(location=custom)
        (storage / "private.key").write_text("private")
        unknown = self.output / "resources/keep.bin"
        unknown.parent.mkdir(parents=True)
        unknown.write_bytes(b"keep")
        args = ("--with-resources", "--resources-dir", str(custom))
        self.assert_ok(self.package(*args))
        stats = {}
        for _, _, _, _, relative, payload in entries:
            target = self.output / "resources" / relative
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(target.with_name(target.name + ".sha256").read_text(),
                             f"{hashlib.sha256(payload).hexdigest()}  {target.name}\n")
            stats[relative] = (target.stat().st_ino, target.stat().st_mtime_ns)
        self.assertFalse((self.output / "resources/private.key").exists())
        self.assertEqual(unknown.read_bytes(), b"keep")
        self.assert_ok(self.package(*args))
        for relative, expected in stats.items():
            target = self.output / "resources" / relative
            self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns), expected)
        with zipfile.ZipFile(self.output / "team-dev-env.zip") as archive:
            self.assertFalse(any(name.endswith(("jdk8.tar.gz", "setter.zip")) for name in archive.namelist()))

    def test_resource_validation_finishes_before_replacing_published_files(self):
        self.assert_ok(self.package())
        before = self.published_files()
        storage, _ = self.resources(unpinned=True)
        (storage / "plugins/setter.zip").write_bytes(b"corrupted")
        self.assertNotEqual(self.package("--with-resources").returncode, 0)
        self.assertEqual(self.published_files(), before)
        self.assertNotEqual(self.package().returncode, 0)
        self.assertEqual(self.published_files(), before)

    def test_resource_destination_conflicts_are_preflighted_before_any_replacement(self):
        self.assert_ok(self.package())
        self.resources()
        target = self.output / "resources/plugins/setter.zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing different payload")
        before = self.published_files()
        result = self.package("--with-resources", "--server", "changed:88")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.published_files(), before)
        self.assertFalse((self.output / "resources/runtime/jdk8.tar.gz").exists())

    def test_resource_symlinks_never_publish_or_modify_external_files(self):
        self.assert_ok(self.package())
        storage, _ = self.resources()
        before = self.published_files()
        outside = self.base / "external"
        outside.mkdir()
        (self.output / "resources").symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.package("--with-resources").returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.published_files(), before)
        (self.output / "resources").unlink()
        source = storage / "plugins/setter.zip"
        source.rename(outside / "setter.zip")
        source.symlink_to(outside / "setter.zip")
        self.assertNotEqual(self.package("--with-resources").returncode, 0)
        self.assertEqual(self.published_files(), before)

    def test_with_resources_requires_catalog_and_unpinned_sources_require_receipts(self):
        self.assertNotEqual(self.package("--with-resources").returncode, 0)
        storage, _ = self.resources(unpinned=True)
        (storage / "plugins/setter.zip.sha256").unlink()
        self.assertNotEqual(self.package().returncode, 0)
        self.assertFalse((self.output / "start.command").exists())

    def test_accepted_receipt_without_final_newline_generates_pinned_manifest(self):
        storage, _ = self.resources(unpinned=True)
        receipt = storage / "plugins/setter.zip.sha256"
        receipt.write_bytes(receipt.read_bytes().rstrip(b"\n"))
        self.assert_ok(self.package())

    def test_output_symlink_with_trailing_slash_is_rejected(self):
        outside = self.base / "external output"
        outside.mkdir()
        self.output.symlink_to(outside, target_is_directory=True)
        result = self.package("--output", str(self.output) + "/")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_launcher_survives_move_dry_run_and_environment_override(self):
        self.assert_ok(self.package("--server", "intranet.example:9000", "--scheme", "https"))
        moved = self.base / "下载 单个'启动器.command"
        shutil.copy2(self.output / "start.command", moved)
        shutil.rmtree(self.output)
        result = self.launch("--dry-run", launcher=moved)
        self.assert_ok(result)
        self.assertIn("https://intranet.example:9000/dev-env/team-dev-env.tar.gz", result.stdout)
        self.assertNotIn("jdk", result.stdout.lower())
        result = self.launch("--project", "项目 ' test", "--dry-run", launcher=moved,
                             extra={"SERVER_ADDR": "mirror:9090", "SERVER_SCHEME": "http"})
        self.assert_ok(result)
        self.assertIn("http://mirror:9090/dev-env/team-dev-env.tar.gz", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertFalse(self.result_file.exists())
        self.assert_ok(self.launch("--help", launcher=moved))

    def test_defaults_come_from_config_and_environment(self):
        self.assert_ok(self.package())
        self.assertIn("http://config.example:8088/", self.launch("--dry-run").stdout)
        self.assert_ok(self.package(extra={"SERVER_ADDR": "environment:99", "SERVER_SCHEME": "https"}))
        self.assertIn("https://environment:99/", self.launch("--dry-run").stdout)

    def test_package_preserves_unknown_files_and_rejects_missing_sources(self):
        self.output.mkdir()
        keep = self.output / "existing-jdk.tar.gz"
        keep.write_bytes(b"do not change")
        self.assert_ok(self.package())
        original = (self.output / "start.command").read_bytes()
        (self.kit / ".support/menu.sh").unlink()
        self.assertNotEqual(self.package().returncode, 0)
        self.assertEqual(keep.read_bytes(), b"do not change")
        self.assertEqual((self.output / "start.command").read_bytes(), original)

    def test_rejects_invalid_urls_and_symlinked_source_before_publishing(self):
        for args in (("--scheme", "file"), ("--server", "example/path"), ("--server", "example's:8")):
            self.assertNotEqual(self.package(*args).returncode, 0)
        target = self.kit / ".support/config/env.sh"
        target.unlink()
        target.symlink_to(self.base / "private.sh")
        (self.base / "private.sh").write_text("PRIVATE-MAINTAINER-DATA")
        self.assertNotEqual(self.package().returncode, 0)

    def test_http_download_forwards_arguments_and_cleans_up(self):
        self.assert_ok(self.package())
        server = self.serve()
        result = self.launch("--project", "项目 path's", "--check",
                             extra={"SERVER_ADDR": server, "SERVER_SCHEME": "http"})
        self.assert_ok(result)
        self.assertEqual(self.result_file.read_text().splitlines(),
                         [server, "http", "--project", "项目 path's", "--check"])
        self.assertEqual(list(self.tmp.iterdir()), [])
        result = self.launch(extra={"SERVER_ADDR": server, "PAYLOAD_EXIT_CODE": "7"})
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_download_and_checksum_failures_never_execute_payload(self):
        self.assert_ok(self.package())
        server = self.serve()
        archive = self.output / "dev-env/team-dev-env.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"corruption")
        result = self.launch(extra={"SERVER_ADDR": server})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("校验", result.stdout)
        self.assertFalse(self.result_file.exists())
        self.assertEqual(list(self.tmp.iterdir()), [])
        archive.unlink()
        result = self.launch(extra={"SERVER_ADDR": server})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("下载", result.stdout)
        self.assertFalse(self.result_file.exists())

    def test_wrong_server_root_reports_404_url_and_deployment_root(self):
        self.assert_ok(self.package())
        self.assertTrue((self.output / "dev-env/team-dev-env.tar.gz").is_file())
        server = self.serve(self.base)
        result = self.launch(extra={"SERVER_ADDR": server, "LC_ALL": "C.UTF-8"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"http://{server}/dev-env/team-dev-env.tar.gz", result.stdout)
        self.assertIn("HTTP 404", result.stdout)
        self.assertIn("dist/server", result.stdout)
        self.assertFalse(self.result_file.exists())
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_preview_rejects_occupied_port_before_rebuilding(self):
        self.output.mkdir()
        server = self.serve()
        result = subprocess.run(["/bin/bash", str(self.repo / "tools/preview.sh"),
                                 "--port", server.rsplit(":", 1)[1]], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("端口已被占用", result.stdout + result.stderr)
        self.assertFalse((self.repo / "dist/server").exists())

    def test_rejects_path_traversal_symlink_and_hardlink_payloads(self):
        self.assert_ok(self.package())
        server = self.serve()
        for name, data, kind in (
            ("team-dev-env/../../escaped", b"bad", "file"),
            ("/tmp/escaped", b"bad", "file"),
            ("other-root/entry", b"bad", "file"),
            ("team-dev-env/link", b"../../escaped", "symlink"),
            ("team-dev-env/link", b"../../escaped", "hardlink"),
        ):
            with self.subTest(name=name, kind=kind):
                self.replace_payload([(name, data, kind)])
                result = self.launch(extra={"SERVER_ADDR": server})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("工具包", result.stdout)
                self.assertFalse(self.result_file.exists())
                self.assertEqual(list(self.tmp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
