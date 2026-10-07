"""Cross-platform server contracts; only temporary payloads and loopback ports."""
import functools
import contextlib
import hashlib
import http.server
import io
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
from unittest import mock
import urllib.error
import urllib.request
import zipfile

from server import manage

try:
    from .cleanup_fixture import cleanup_fixture
    from .tui_fixture import tui_fixture
except ImportError:
    from cleanup_fixture import cleanup_fixture
    from tui_fixture import tui_fixture


ROOT = Path(__file__).resolve().parents[1]
HEADER = "# id\tgroup\tversion\tarch\tpath\turl\tsha256"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class InteractiveInput(io.StringIO):
    def isatty(self):
        return True


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
        self.cleanup = cleanup_fixture(self.repo)
        self.tui = tui_fixture(self.repo)

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

    def free_port(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            return reservation.getsockname()[1]

    def start_once(self, arguments, candidates=None, stdin=None):
        """Keep real preparation/packaging/binding, stop before the endless HTTP loop."""
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(manage, "ROOT", self.repo))
            stack.enter_context(mock.patch.dict(os.environ, self.env, clear=True))
            stack.enter_context(mock.patch.object(manage, "discover_ipv4_addresses", create=True,
                                                 return_value=candidates or []))
            stack.enter_context(mock.patch.object(manage.DownloadServer, "serve_forever", return_value=None))
            stack.enter_context(mock.patch.object(sys, "stdin", stdin or io.StringIO()))
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(output))
            try:
                status = manage.main(arguments)
            except SystemExit as error:
                status = error.code
        return status, output.getvalue()

    def test_start_automatically_packages_lan_address_and_reuses_resources(self):
        self.resources()
        target = self.repo / "resources/runtime/jdk.bin"
        before = target.stat().st_mtime_ns
        port = self.free_port()
        status, output = self.start_once(
            ["start", "--port", str(port), "--output", str(self.output)], ["192.168.50.8"])
        self.assertEqual(status, 0, output)
        address = "192.168.50.8:%s" % port
        with zipfile.ZipFile(self.output / "start.zip") as archive:
            self.assertIn(address, archive.read("开始配置.command").decode())
        with tarfile.open(self.output / "dev-env/team-dev-env.tar.gz") as archive:
            self.assertIn(address, archive.extractfile("team-dev-env/.support/config/team.sh").read().decode())
        self.assertEqual((self.output / "resources/runtime/jdk.bin").read_bytes(), b"jdk\x00\r\n")
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertIn("http://" + address + "/start.zip", output)

    def test_no_arguments_starts_and_replaces_legacy_loopback_config_address(self):
        self.resources()
        port = self.free_port()
        (self.repo / "server/config.json").write_text(json.dumps({
            "server": "127.0.0.1:8080", "bind": "127.0.0.1", "port": port,
            "output": str(self.output)}))
        status, output = self.start_once([], ["10.10.0.6"])
        self.assertEqual(status, 0, output)
        self.assertIn("10.10.0.6:%s" % port, (self.output / "start.command").read_text())

    def test_start_ambiguous_addresses_require_selection_and_support_interactive_choice(self):
        self.resources()
        arguments = ["start", "--output", str(self.output), "--port", str(self.free_port())]
        candidates = ["10.10.0.6", "192.168.50.8"]
        status, output = self.start_once(arguments, candidates)
        self.assertNotEqual(status, 0)
        self.assertIn("--server", output)
        self.assertFalse(self.output.exists())
        status, output = self.start_once(arguments, candidates, InteractiveInput("2\n"))
        self.assertEqual(status, 0, output)
        self.assertIn("192.168.50.8:", (self.output / "start.command").read_text())

    def test_start_without_address_or_with_invalid_selection_does_not_publish(self):
        for candidates, stdin in [([], None), (["10.0.0.2", "10.0.1.2"], InteractiveInput("99\n")),
                                  (["10.0.0.2", "10.0.1.2"], InteractiveInput(""))]:
            with self.subTest(candidates=candidates, stdin=stdin):
                status, output = self.start_once(["start", "--output", str(self.output)], candidates, stdin)
                self.assertNotEqual(status, 0)
                self.assertIn("--server", output)
                self.assertFalse(self.output.exists())

    def test_start_occupied_port_preserves_publication_and_does_not_download(self):
        self.resources()
        self.assert_ok(self.package("--with-resources"))
        previous = (self.output / "start.zip").read_bytes()
        missing = self.repo / "resources/runtime/jdk.bin"
        missing.unlink()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            status, output = self.start_once(["start", "--server", "192.168.50.8",
                                             "--port", str(listener.getsockname()[1]),
                                             "--output", str(self.output)])
        self.assertNotEqual(status, 0)
        self.assertIn("端口", output)
        self.assertNotIn("下载：", output)
        self.assertFalse(missing.exists())
        self.assertEqual((self.output / "start.zip").read_bytes(), previous)

    def test_start_rejects_mismatched_port_and_https_before_publication(self):
        for options in [["--server", "team.example:8088", "--port", "8089"],
                        ["--server", "team.example:99999"], ["--server", "0.0.0.0"]]:
            with self.subTest(options=options):
                status, output = self.start_once(["start", "--output", str(self.output)] + options)
                self.assertNotEqual(status, 0)
                self.assertFalse(self.output.exists())
        (self.repo / "server/config.json").write_text(json.dumps({"scheme": "https"}))
        status, output = self.start_once(["start", "--server", "team.example", "--output", str(self.output)])
        self.assertNotEqual(status, 0)
        self.assertIn("HTTPS", output)
        self.assertFalse(self.output.exists())

    def test_start_command_line_port_overrides_inherited_address_port(self):
        self.resources()
        port = self.free_port()
        for source in ("config", "environment"):
            with self.subTest(source=source):
                if source == "config":
                    (self.repo / "server/config.json").write_text(json.dumps({"server": "team.example:8080"}))
                else:
                    (self.repo / "server/config.json").unlink()
                    self.env["SERVER_ADDR"] = "team.example:8080"
                status, output = self.start_once(["start", "--port", str(port), "--output", str(self.output)])
                self.assertEqual(status, 0, output)
                self.assertIn("team.example:%s" % port, (self.output / "start.command").read_text())

    def test_start_downloads_into_custom_resource_directory_and_serves_publication(self):
        source, address = self.fixture_server()
        payload = b"one-click-resource"
        (source / "artifact.bin").write_bytes(payload)
        self.catalog([("jdk", "runtime", "8", "any", "runtime/artifact.bin",
                       address + "/artifact.bin", hashlib.sha256(payload).hexdigest())])
        custom_catalog = self.repo / "custom.tsv"
        (self.repo / "resources/catalog.tsv").rename(custom_catalog)
        storage = self.base / "custom resources"
        port = self.free_port()
        log = self.base / "start.log"
        with log.open("wb") as output:
            process = subprocess.Popen([sys.executable, str(self.manage), "start", "--server", "127.0.0.1:%s" % port,
                                        "--output", str(self.output), "--resources-dir", str(storage),
                                        "--catalog", str(custom_catalog)], cwd=self.base,
                                       env=self.env, stdout=output, stderr=subprocess.STDOUT)
        self.processes.append(process)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 8
        while True:
            try:
                with opener.open("http://127.0.0.1:%s/start.zip" % port, timeout=0.3) as response:
                    data = response.read()
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline or process.poll() is not None:
                    self.fail(log.read_text(encoding="utf-8"))
                time.sleep(0.03)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn("127.0.0.1:%s" % port, archive.read("开始配置.command").decode())
        with opener.open("http://127.0.0.1:%s/resources/runtime/artifact.bin" % port) as response:
            self.assertEqual(response.read(), payload)
        self.assertEqual((storage / "runtime/artifact.bin").read_bytes(), payload)
        self.assertFalse((self.output / "runtime/artifact.bin").exists())

    def test_start_corrupt_resource_preserves_old_publication_and_releases_port(self):
        self.resources()
        self.assert_ok(self.package("--with-resources"))
        previous = (self.output / "start.zip").read_bytes()
        target = self.repo / "resources/runtime/jdk.bin"
        target.write_bytes(b"corrupt")
        port = self.free_port()
        status, output = self.start_once(["start", "--server", "team.example", "--port", str(port),
                                         "--output", str(self.output)])
        self.assertNotEqual(status, 0)
        self.assertIn("SHA-256", output)
        self.assertEqual(target.read_bytes(), b"corrupt")
        self.assertEqual((self.output / "start.zip").read_bytes(), previous)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))

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
                if (member.isfile() and member.name != "team-dev-env/.support/cleanup/cleanup-macos"
                        and not member.name.startswith("team-dev-env/.support/tui/team-dev-env-")):
                    self.assertNotIn(b"\r", archive.extractfile(member).read())
            self.assertEqual(archive.getmember("team-dev-env/开始配置.command").mode, 0o755)
            self.assertEqual(archive.getmember("team-dev-env/.support/menu.sh").mode, 0o755)
        with zipfile.ZipFile(self.output / "start.zip") as archive:
            entry = archive.getinfo("开始配置.command")
            self.assertEqual(entry.create_system, 3)
            self.assertEqual((entry.external_attr >> 16) & 0o777, 0o755)
            self.assertTrue(entry.flag_bits & 0x800)
            self.assertEqual(archive.read(entry), launcher)

    def test_package_embeds_verified_universal_cleanup_without_running_it(self):
        self.assert_ok(self.package())
        prefix = "team-dev-env/.support/cleanup/"
        payload = (self.cleanup / "cleanup-macos-universal2").read_bytes()
        with tarfile.open(self.output / "dev-env/team-dev-env.tar.gz") as archive:
            self.assertIn(prefix + "cleanup-macos", archive.getnames())
            self.assertEqual(archive.extractfile(prefix + "cleanup-macos").read(), payload)
            self.assertEqual(archive.getmember(prefix + "cleanup-macos").mode, 0o755)
            for name in ("manifest.json", "THIRD_PARTY_NOTICES.txt"):
                self.assertEqual(archive.getmember(prefix + name).mode, 0o644)
            self.assertFalse(any(name.endswith(".py") for name in archive.getnames()))
        with zipfile.ZipFile(self.output / "team-dev-env.zip") as archive:
            self.assertEqual(archive.read(prefix + "cleanup-macos"), payload)
            self.assertEqual((archive.getinfo(prefix + "cleanup-macos").external_attr >> 16) & 0o777, 0o755)

    def test_invalid_cleanup_preserves_every_published_file(self):
        self.assert_ok(self.package())
        before = {name: (self.output / name).read_bytes() for name in manage.PUBLISHED}
        binary = self.cleanup / "cleanup-macos-universal2"
        metadata = self.cleanup / "manifest.json"
        source = self.repo / "tools/uninstall_java_gradle.py"
        original_source = source.read_bytes()
        for problem in ("missing-binary", "missing-manifest", "missing-license", "corrupt-binary",
                        "old-source", "bad-json", "wrong-schema", "wrong-architectures", "thin-binary",
                        "truncated-fat", "mismatched-slice", "symlink-binary"):
            with self.subTest(problem=problem):
                if binary.is_symlink():
                    binary.unlink()
                source.write_bytes(original_source)
                cleanup_fixture(self.repo)
                manifest = json.loads(metadata.read_text())
                if problem == "missing-binary":
                    binary.unlink()
                elif problem == "missing-manifest":
                    metadata.unlink()
                elif problem == "missing-license":
                    (self.cleanup / "THIRD_PARTY_NOTICES.txt").unlink()
                elif problem == "corrupt-binary":
                    binary.write_bytes(b"corrupted")
                elif problem == "old-source":
                    source.write_bytes(original_source + b"\n# changed\n")
                elif problem == "bad-json":
                    metadata.write_text("not JSON")
                elif problem == "wrong-schema":
                    manifest["schema"] = 2
                elif problem == "wrong-architectures":
                    manifest["architectures"] = ["arm64"]
                elif problem == "thin-binary":
                    binary.write_bytes(binary.read_bytes()[48:80])
                elif problem == "truncated-fat":
                    binary.write_bytes(binary.read_bytes()[:50])
                elif problem == "mismatched-slice":
                    content = bytearray(binary.read_bytes())
                    content[52:56] = (0x01000007).to_bytes(4, "little")
                    binary.write_bytes(content)
                elif problem == "symlink-binary":
                    outside = self.base / "outside-runtime"
                    outside.write_bytes(binary.read_bytes())
                    binary.unlink()
                    binary.symlink_to(outside)
                if problem in ("thin-binary", "truncated-fat", "mismatched-slice"):
                    manifest["sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
                if problem in ("wrong-schema", "wrong-architectures", "thin-binary", "truncated-fat", "mismatched-slice"):
                    metadata.write_text(json.dumps(manifest))
                result = self.package("--server", "changed.example:90")
                self.assertNotEqual(result.returncode, 0, problem)
                self.assertIn("tools/build-cleanup.py", result.stdout)
                self.assertEqual({name: (self.output / name).read_bytes() for name in manage.PUBLISHED}, before)

    def test_cleanup_source_hash_allows_windows_line_endings_and_utf8_bom(self):
        source = self.repo / "tools/uninstall_java_gradle.py"
        source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assert_ok(self.package())

    def test_package_embeds_both_tui_binaries_with_modes_without_executing_them(self):
        self.assert_ok(self.package())
        prefix = "team-dev-env/.support/tui/"
        with tarfile.open(self.output / "dev-env/team-dev-env.tar.gz") as archive:
            with zipfile.ZipFile(self.output / "team-dev-env.zip") as zipped:
                for name in ("team-dev-env-arm64", "team-dev-env-amd64", "manifest.json", "THIRD_PARTY_NOTICES.txt"):
                    mode = 0o755 if name.startswith("team-dev-env-") else 0o644
                    self.assertEqual(archive.extractfile(prefix + name).read(), (self.tui / name).read_bytes())
                    self.assertEqual(archive.getmember(prefix + name).mode, mode)
                    self.assertEqual(zipped.read(prefix + name), (self.tui / name).read_bytes())
                    self.assertEqual((zipped.getinfo(prefix + name).external_attr >> 16) & 0o777, mode)

    def test_invalid_tui_preserves_all_published_files(self):
        self.assert_ok(self.package())
        previous = {name: (self.output / name).read_bytes() for name in manage.PUBLISHED}
        source = self.repo / "tui/main.go"
        original_source = source.read_bytes()
        for problem in ("missing-binary", "corrupt-binary", "old-source", "missing-license", "changed-license",
                        "wrong-cpu", "not-executable", "bad-json", "wrong-file", "symlink-binary"):
            with self.subTest(problem=problem):
                binary = self.tui / "team-dev-env-arm64"
                if binary.is_symlink():
                    binary.unlink()
                source.write_bytes(original_source)
                tui_fixture(self.repo)
                metadata = self.tui / "manifest.json"
                manifest = json.loads(metadata.read_text())
                if problem == "missing-binary":
                    binary.unlink()
                elif problem == "corrupt-binary":
                    binary.write_bytes(binary.read_bytes() + b"changed")
                elif problem == "old-source":
                    source.write_bytes(original_source + b"// changed\n")
                elif problem == "missing-license":
                    (self.tui / "THIRD_PARTY_NOTICES.txt").unlink()
                elif problem == "changed-license":
                    (self.tui / "THIRD_PARTY_NOTICES.txt").write_text("removed notices")
                elif problem in ("wrong-cpu", "not-executable"):
                    payload = bytearray(binary.read_bytes())
                    offset, value = (4, 0x01000007) if problem == "wrong-cpu" else (12, 6)
                    payload[offset:offset + 4] = value.to_bytes(4, "little")
                    binary.write_bytes(payload)
                    manifest["binaries"]["arm64"]["sha256"] = hashlib.sha256(payload).hexdigest()
                elif problem == "bad-json":
                    metadata.write_text("not json")
                elif problem == "wrong-file":
                    manifest["binaries"]["arm64"]["file"] = "../../outside"
                elif problem == "symlink-binary":
                    outside = self.base / "outside-tui"
                    outside.write_bytes(binary.read_bytes())
                    binary.unlink()
                    binary.symlink_to(outside)
                if problem in ("wrong-cpu", "not-executable", "wrong-file"):
                    metadata.write_text(json.dumps(manifest))
                result = self.package("--server", "changed.example:91")
                self.assertNotEqual(result.returncode, 0, problem)
                self.assertIn("tools/build-tui.py", result.stdout)
                self.assertEqual({name: (self.output / name).read_bytes() for name in manage.PUBLISHED}, previous)

    def test_tui_source_hash_allows_windows_checkout_line_endings(self):
        for path in (self.repo / "tui").iterdir():
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
        self.assert_ok(self.package())

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
