"""Cross-platform server contracts; only temporary payloads and loopback ports."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HEADER = "# id\tgroup\tversion\tarch\tpath\turl\tsha256"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="跨平台 server ' ")
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "源码 空间"
        self.repo.mkdir()
        shutil.copytree(ROOT / "tools", self.repo / "tools")
        if (ROOT / "server").exists():
            shutil.copytree(ROOT / "server", self.repo / "server")
        else:
            (self.repo / "server").mkdir()
        self.allowlist = [line for line in (self.repo / "tools/package-files.txt")
                          .read_text(encoding="utf-8").splitlines()
                          if line and not line.startswith("#")]
        for name in self.allowlist:
            path = self.repo / "dev-kit" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"#!/bin/bash\r\nprintf 'fixture\\n'\r\n")
        (self.repo / "dev-kit/.support/config/env.sh").write_bytes(
            b'SERVER_ADDR="${SERVER_ADDR:-config.example:8088}"\r\n'
            b'SERVER_SCHEME="${SERVER_SCHEME:-http}"\r\n'
            b'printf bad > "$HOME/MUST_NOT_EXIST"\r\n')
        self.output = self.base / "发布 output"
        self.manage = self.repo / "server/manage.py"
        self.env = {**os.environ, "PATH": "", "HOME": str(self.base / "home"),
                    "PYTHONIOENCODING": "utf-8"}
        self.env.pop("SERVER_ADDR", None)
        self.env.pop("SERVER_SCHEME", None)
        self.httpd = None
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join(timeout=5)
        self.temp.cleanup()

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(self.manage), *args],
                              cwd=self.base, env={**self.env, **(env or {})},
                              text=True, encoding="utf-8", stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=15)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def package(self, *args, **kwargs):
        return self.cli("package", "--output", str(self.output), *args, **kwargs)

    def fixture_server(self):
        source = self.base / "official fixtures"
        source.mkdir()
        self.httpd = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(source)))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return source, "http://127.0.0.1:" + str(self.httpd.server_port)

    def catalog(self, rows):
        path = self.repo / "resources/catalog.tsv"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes((HEADER + "\r\n" + "\r\n".join("\t".join(row) for row in rows)
                          + "\r\n").encode("utf-8"))
        return path

    def resources(self):
        rows = []
        for name, data, digest in [("runtime/jdk.bin", b"jdk\x00\r\n", True),
                                   ("plugins/plugin.zip", b"zip\x00\r\n", False)]:
            target = self.repo / "resources" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            target.with_name(target.name + ".sha256").write_text(
                sha + "  " + target.name + "\n", encoding="utf-8")
            rows.append((target.stem, name.split("/")[0], "1", "any", name,
                         "https://official.invalid/" + name, sha if digest else "-"))
        self.catalog(rows)
        return rows

    def test_package_without_shell_normalizes_text_and_preserves_unix_archive_modes(self):
        template = self.repo / "tools/start.command.in"
        template.write_bytes(template.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assert_ok(self.package())
        self.assertFalse((self.base / "home/MUST_NOT_EXIST").exists())
        launcher = (self.output / "start.command").read_bytes()
        self.assertIn(b"config.example:8088", launcher)
        self.assertNotIn(b"\r", launcher)
        archive_path = self.output / "dev-env/team-dev-env.tar.gz"
        self.assertEqual(archive_path.with_name(archive_path.name + ".sha256")
                         .read_text().split()[0], hashlib.sha256(archive_path.read_bytes()).hexdigest())
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                self.assertTrue(member.isfile() or member.isdir())
                if member.isfile():
                    self.assertNotIn(b"\r", archive.extractfile(member).read())
            self.assertEqual(archive.getmember("team-dev-env/开始配置.command").mode, 0o755)
            self.assertEqual(archive.getmember("team-dev-env/.support/menu.sh").mode, 0o755)
        with zipfile.ZipFile(self.output / "start.zip") as archive:
            entry = archive.getinfo("开始配置.command")
            self.assertEqual(entry.create_system, 3)
            self.assertEqual((entry.external_attr >> 16) & 0o777, 0o755)
            self.assertTrue(entry.flag_bits & 0x800)
            self.assertEqual(archive.read(entry), launcher)

    def test_package_resources_pins_receipts_preserves_binary_and_reuses_output(self):
        rows = self.resources()
        self.assert_ok(self.package("--with-resources"))
        target = self.output / "resources/runtime/jdk.bin"
        before = target.stat().st_mtime_ns
        self.assertEqual(target.read_bytes(), b"jdk\x00\r\n")
        extra = self.output / "resources/unknown.txt"
        extra.write_text("keep")
        self.assert_ok(self.package("--with-resources"))
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual(extra.read_text(), "keep")
        with tarfile.open(self.output / "dev-env/team-dev-env.tar.gz") as archive:
            data = archive.extractfile("team-dev-env/.support/config/resources.tsv").read().decode()
            self.assertNotIn("\t-\n", data)
            self.assertIn(hashlib.sha256(b"zip\x00\r\n").hexdigest(), data)
            self.assertFalse(any(name.endswith("jdk.bin") for name in archive.getnames()))

    def test_prepare_downloads_checks_hash_and_reuses_without_network(self):
        source, address = self.fixture_server()
        payload = b"binary\x00\r\n"
        (source / "artifact.bin").write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        self.catalog([("jdk", "runtime", "8", "arm64", "runtime/artifact.bin",
                       address + "/artifact.bin", digest),
                      ("plugin", "plugins", "1", "any", "plugins/plugin.zip",
                       address + "/artifact.bin", "-")])
        self.assert_ok(self.cli("prepare", "--arch", "arm64"))
        target = self.repo / "resources/runtime/artifact.bin"
        self.assertEqual(target.read_bytes(), payload)
        plugin = self.repo / "resources/plugins/plugin.zip"
        self.assertIn(digest, plugin.with_name(plugin.name + ".sha256").read_text())
        (source / "artifact.bin").unlink()
        before = target.stat().st_mtime_ns
        self.assert_ok(self.cli("prepare"))
        self.assertEqual(target.stat().st_mtime_ns, before)
        target.write_bytes(b"bad")
        self.assertNotEqual(self.cli("prepare", "--verify").returncode, 0)
        self.assertEqual(target.read_bytes(), b"bad")

    def test_prepare_rejects_hash_mismatch_without_final_asset_or_receipt(self):
        source, address = self.fixture_server()
        (source / "bad").write_bytes(b"bad")
        self.catalog([("bad", "runtime", "1", "any", "runtime/bad",
                       address + "/bad", "a" * 64)])
        result = self.cli("prepare")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stdout)
        self.assertFalse((self.repo / "resources/runtime/bad").exists())
        self.assertFalse(list((self.repo / "resources").rglob("*.part*")))

    def test_windows_paths_and_receipt_collisions_are_rejected_before_writes(self):
        for relative in ["C:/escape.bin", r"C:\escape.bin", r"..\escape.bin",
                         "../escape.bin", "runtime/CON.zip", "runtime/file:stream", "runtime/trailing. "]:
            with self.subTest(relative=relative):
                self.catalog([("bad", "runtime", "1", "any", relative,
                               "https://official.invalid/a", "a" * 64)])
                result = self.cli("prepare", "--dry-run", "--output", str(self.output))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("清单", result.stdout)
                self.assertFalse(self.output.exists())
        self.catalog([("a", "runtime", "1", "any", "runtime/a", "https://official.invalid/a", "a" * 64),
                      ("b", "runtime", "1", "any", "runtime/a.sha256", "https://official.invalid/b", "b" * 64)])
        self.assertNotEqual(self.cli("prepare", "--dry-run").returncode, 0)

    def test_json_config_windows_separators_and_cli_environment_precedence(self):
        config = self.repo / "server/config.json"
        config.write_text(json.dumps({"output": r"dist\发布", "server": "json.example:80",
                                      "scheme": "https"}), encoding="utf-8")
        self.assert_ok(self.cli("package"))
        target = self.repo / "dist/发布/start.command"
        self.assertIn("json.example:80", target.read_text(encoding="utf-8"))
        self.assert_ok(self.cli("package", env={"SERVER_ADDR": "env.example:81"}))
        self.assertIn("env.example:81", target.read_text(encoding="utf-8"))
        self.assert_ok(self.cli("package", "--server", "cli.example:82"))
        self.assertIn("cli.example:82", target.read_text(encoding="utf-8"))

    def test_source_and_destination_symlinks_preserve_existing_publication(self):
        self.assert_ok(self.package())
        previous = (self.output / "start.zip").read_bytes()
        target = self.repo / "dev-kit/.support/menu.sh"
        target.unlink()
        target.symlink_to(self.base / "outside")
        (self.base / "outside").write_text("private")
        self.assertNotEqual(self.package().returncode, 0)
        self.assertEqual((self.output / "start.zip").read_bytes(), previous)
        target.unlink()
        target.write_text("fixture")
        redirect = self.base / "redirect"
        redirect.symlink_to(self.output, target_is_directory=True)
        self.assertNotEqual(self.package("--output", str(redirect) + "/").returncode, 0)
        self.assertEqual((self.output / "start.zip").read_bytes(), previous)

    def test_preview_occupied_port_does_not_repackage(self):
        self.assert_ok(self.package())
        before = (self.output / "start.zip").read_bytes()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            result = self.cli("preview", "--port", str(listener.getsockname()[1]),
                              "--output", str(self.output))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("端口已被占用", result.stdout)
        self.assertEqual((self.output / "start.zip").read_bytes(), before)

    def test_serve_from_unrelated_cwd_serves_only_selected_root_read_only(self):
        self.assert_ok(self.package())
        secret = self.base / "secret.txt"
        secret.write_text("private")
        (self.output / "linked.txt").symlink_to(secret)
        (self.output / "nested").mkdir()
        (self.output / "nested/index.html").symlink_to(secret)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        log = self.base / "server.log"
        with log.open("wb") as output:
            process = subprocess.Popen([sys.executable, str(self.manage), "serve", "--directory",
                                        str(self.output), "--port", str(port)], cwd=self.base,
                                       env=self.env, stdout=output, stderr=subprocess.STDOUT)
        self.processes.append(process)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        address = "http://127.0.0.1:" + str(port)
        deadline = time.monotonic() + 8
        while True:
            try:
                with opener.open(address + "/start.zip", timeout=0.5) as response:
                    self.assertEqual(response.read(), (self.output / "start.zip").read_bytes())
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > deadline or process.poll() is not None:
                    self.fail(log.read_text(encoding="utf-8"))
                time.sleep(0.03)
        for path, status in [("/wrong-root/start.zip", 404), ("/linked.txt", 403), ("/nested/", 403),
                             ("/%2e%2e/secret.txt", 403)]:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(address + path)
                self.assertEqual(error.exception.code, status)
                error.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as error:
            opener.open(urllib.request.Request(address + "/new.txt", data=b"write", method="PUT"))
        self.assertIn(error.exception.code, (405, 501))
        error.exception.close()
        self.assertFalse((self.output / "new.txt").exists())

    def test_serve_refuses_unpacked_repository_directory(self):
        result = self.cli("serve", "--directory", str(self.repo), "--port", "12345")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("打包", result.stdout)


if __name__ == "__main__":
    unittest.main()
