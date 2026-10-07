"""Fetch pinned runtime releases and safely repair caches without executing them."""
import contextlib
import hashlib
import http.server
import importlib.util
import json
from pathlib import Path
import shutil
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
import warnings
import zipfile
import urllib.error
import urllib.request

try:
    from .runtime_fixture import FILES, archive_fixture, lock_fixture, runtime_fixture
except ImportError:
    from runtime_fixture import FILES, archive_fixture, lock_fixture, runtime_fixture


MODULE = Path(__file__).resolve().parents[1] / "server/runtime_artifacts.py"


@contextlib.contextmanager
def serve(payload, headers=None, on_request=None):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if on_request:
                on_request(self.path)
            self.send_response(200)
            for name, value in (headers or {"Content-Length": str(len(payload))}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%s/mirror/" % httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class RuntimeArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.is_file():
            from server import runtime_artifacts
            cls.module = runtime_artifacts

    def setUp(self):
        self.assertTrue(MODULE.is_file(), "缺少可验证的运行文件自动补齐模块")
        self.temp = tempfile.TemporaryDirectory(prefix="运行文件 ' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "项目's 中文 空格"
        self.repo.mkdir()
        self.payloads = runtime_fixture(self.repo)
        self.archive = archive_fixture(self.payloads)
        self.lock = lock_fixture(self.payloads, self.archive)
        self.write_lock()

    def write_lock(self):
        path = self.repo / "resources/runtime-lock.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.lock), encoding="utf-8")

    def remove_runtimes(self):
        for folder in ("tui", "cleanup"):
            shutil.rmtree(self.repo / "resources" / folder)

    def snapshot(self):
        return {p.relative_to(self.repo).as_posix(): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in self.repo.rglob("*") if p.is_file()}

    def fetch(self, **kwargs):
        return self.module.ensure_runtimes(self.repo, report=lambda message: None, **kwargs)

    def test_clean_checkout_downloads_pinned_release_without_executing_any_program(self):
        self.remove_runtimes()
        requests = []
        with serve(self.archive, on_request=requests.append) as mirror, \
                mock.patch.object(subprocess, "run", side_effect=AssertionError("must not execute")):
            result = self.fetch(base_url=mirror)
        self.assertEqual(requests, ["/mirror/team-dev-env-runtimes.zip"])
        self.assertEqual(result, {"release": self.lock["release"], "downloaded": True,
                                  "source_sha256": self.lock["source_sha256"]})
        self.assertEqual({name: (self.repo / name).read_bytes() for name in FILES}, self.payloads)
        self.assertEqual(self.module.validate_local_runtimes(self.repo)["source_sha256"],
                         self.lock["source_sha256"])

    def test_tls_eof_retry_recovers_the_full_runtime_installation(self):
        self.remove_runtimes()
        original_open = urllib.request.OpenerDirector.open
        attempts = []

        def interrupted_once(opener, request, *args, **kwargs):
            attempts.append(request.full_url)
            if len(attempts) == 1:
                raise urllib.error.URLError(ssl.SSLEOFError(
                    8, "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"))
            return original_open(opener, request, *args, **kwargs)

        with serve(self.archive) as mirror, \
                mock.patch.object(urllib.request.OpenerDirector, "open", interrupted_once), \
                mock.patch("time.sleep", return_value=None):
            result = self.fetch(base_url=mirror)
        self.assertTrue(result["downloaded"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in FILES}, self.payloads)

    def test_custom_repository_generated_lock_downloads_through_explicit_mirror(self):
        script = MODULE.parents[1] / "tools/release-runtimes.py"
        spec = importlib.util.spec_from_file_location("runtime_release_for_fetch", script)
        release_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release_module)
        output = self.repo / "dist/runtime-release"
        for repository in ("custom-owner/Custom.repo_name", "A1/another-repo"):
            with self.subTest(repository=repository):
                runtime_fixture(self.repo)
                lock = release_module.release_runtimes(
                    self.repo, output, self.repo / "resources/runtime-lock.json", repository)
                expected_url = "https://github.com/%s/releases/download/%s/team-dev-env-runtimes.zip" % (
                    repository, lock["release"])
                self.assertEqual(lock["archive"]["url"], expected_url)
                archive = (output / "team-dev-env-runtimes.zip").read_bytes()
                self.remove_runtimes()
                with serve(archive) as mirror:
                    result = self.fetch(base_url=mirror)
                self.assertEqual(result, {"release": lock["release"], "downloaded": True,
                                          "source_sha256": lock["source_sha256"]})
                self.assertEqual({name: (self.repo / name).read_bytes() for name in FILES}, self.payloads)

    def test_valid_cache_needs_neither_network_nor_lock_even_when_offline(self):
        (self.repo / "resources/runtime-lock.json").unlink()
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            result = self.fetch(offline=True)
        self.assertFalse(result["downloaded"])
        self.assertEqual(result["source_sha256"], self.lock["source_sha256"])

    def test_source_hash_accepts_bom_and_windows_line_endings(self):
        for source in [self.repo / "tools/uninstall_java_gradle.py"] + list((self.repo / "tui").iterdir()):
            source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.fetch(offline=True)["source_sha256"], self.lock["source_sha256"])

    def test_offline_missing_runtime_reports_required_action_without_writing(self):
        self.remove_runtimes()
        before = self.snapshot()
        with self.assertRaisesRegex(self.module.RuntimeArtifactError, "离线"):
            self.fetch(offline=True)
        self.assertEqual(self.snapshot(), before)

    def test_stale_lock_for_either_source_is_rejected_before_download(self):
        self.remove_runtimes()
        for relative in ("tui/main.go", "tools/uninstall_java_gradle.py"):
            with self.subTest(source=relative):
                path = self.repo / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n# changed source\n")
                before = self.snapshot()
                with mock.patch("urllib.request.urlopen", side_effect=AssertionError("must not download")), \
                        self.assertRaisesRegex(self.module.RuntimeArtifactError, "源码|过期"):
                    self.fetch()
                self.assertEqual(self.snapshot(), before)
                path.write_bytes(original)

    def test_corrupt_local_file_is_repaired_and_unknown_content_is_preserved(self):
        damaged = self.repo / FILES[0]
        damaged.write_bytes(b"broken binary")
        unknown = self.repo / "resources/cleanup/user notes.txt"
        unknown.write_bytes(b"do not touch")
        with serve(self.archive) as mirror:
            self.assertTrue(self.fetch(base_url=mirror)["downloaded"])
        self.assertEqual(damaged.read_bytes(), self.payloads[FILES[0]])
        self.assertEqual(unknown.read_bytes(), b"do not touch")

    def test_bad_download_digest_truncation_and_extra_bytes_do_not_touch_cache(self):
        (self.repo / FILES[0]).write_bytes(b"old invalid artifact")
        before = self.snapshot()
        for payload in (b"!" + self.archive[1:], self.archive[:-5], self.archive + b"extra"):
            with self.subTest(length=len(payload)), serve(payload) as mirror:
                with self.assertRaises(self.module.RuntimeArtifactError):
                    self.fetch(base_url=mirror)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(list(self.repo.glob(".runtime-*")), [])

    def test_each_member_digest_is_checked_even_with_valid_archive_digest(self):
        self.remove_runtimes()
        modified = dict(self.payloads)
        modified[FILES[0]] += b"tampered"
        self.archive = archive_fixture(modified)
        revised = lock_fixture(self.payloads, self.archive)
        self.lock = revised
        self.write_lock()
        before = self.snapshot()
        with serve(self.archive) as mirror, self.assertRaises(self.module.RuntimeArtifactError):
            self.fetch(base_url=mirror)
        self.assertEqual(self.snapshot(), before)

    def test_streamed_body_without_length_still_rejects_extra_bytes(self):
        self.remove_runtimes()
        before = self.snapshot()
        with serve(self.archive + b"extra", headers={"X-Fixture": "no length"}) as mirror:
            with self.assertRaises(self.module.RuntimeArtifactError):
                self.fetch(base_url=mirror)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_deflate_stream_is_reported_without_writing_any_cache_files(self):
        self.remove_runtimes()
        broken = bytearray(self.archive)
        name_length, extra_length = struct.unpack_from("<HH", broken, 26)
        start = 30 + name_length + extra_length
        broken[start:start + 4] = b"\xff\xff\xff\xff"
        self.lock = lock_fixture(self.payloads, broken)
        self.write_lock()
        before = self.snapshot()
        with serve(broken) as mirror, self.assertRaises(self.module.RuntimeArtifactError):
            self.fetch(base_url=mirror)
        self.assertEqual(self.snapshot(), before)

    def test_truncated_chunked_response_is_reported_without_writing_cache(self):
        self.remove_runtimes()
        before = self.snapshot()
        with serve(b"5\r\nxx", headers={"Transfer-Encoding": "chunked"}) as mirror:
            with self.assertRaises(self.module.RuntimeArtifactError):
                self.fetch(base_url=mirror)
        self.assertEqual(self.snapshot(), before)

    def test_rejects_zip_traversal_duplicates_extra_missing_directories_and_links(self):
        self.remove_runtimes()
        link = zipfile.ZipInfo(FILES[0])
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        directory = zipfile.ZipInfo("resources/tui/")
        directory.external_attr = (stat.S_IFDIR | 0o755) << 16
        cases = [({**self.payloads, "../escape": b"bad"}, ()),
                 (self.payloads, [(FILES[0], b"duplicate")]),
                 ({**self.payloads, "resources/tui/extra": b"bad"}, ()),
                 ({name: data for name, data in self.payloads.items() if name != FILES[0]}, ()),
                 (self.payloads, [(directory, b"")]),
                 ({name: data for name, data in self.payloads.items() if name != FILES[0]}, [(link, b"target")])]
        for index, (payloads, extra) in enumerate(cases):
            with self.subTest(case=index), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive = archive_fixture(payloads, extra)
                self.lock = lock_fixture(self.payloads, archive)
                self.write_lock()
                before = self.snapshot()
                with serve(archive) as mirror, self.assertRaises(self.module.RuntimeArtifactError):
                    self.fetch(base_url=mirror)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse((self.base / "escape").exists())

    def test_rejects_unpinned_urls_and_invalid_lock_sizes_without_download(self):
        self.remove_runtimes()
        mutations = [lambda lock: lock.update(schema=True),
                     lambda lock: lock.update(release="latest"),
                     lambda lock: lock["archive"].update(url="http://attacker.invalid/runtime.zip"),
                     lambda lock: lock["archive"].update(size=-1),
                     lambda lock: lock["archive"].update(size=2 ** 60),
                     lambda lock: lock["files"][FILES[0]].update(size=True),
                     lambda lock: lock["files"].update({"../escape": {"size": 1, "sha256": "0" * 64}})]
        for mutate in mutations:
            self.lock = lock_fixture(self.payloads, self.archive)
            mutate(self.lock)
            self.write_lock()
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("must not download")), \
                    self.assertRaises(self.module.RuntimeArtifactError):
                self.fetch()

    def test_invalid_github_release_urls_are_rejected_even_with_explicit_mirror(self):
        self.remove_runtimes()
        suffix = "/releases/download/%s/team-dev-env-runtimes.zip" % self.lock["release"]
        valid = "https://github.com/custom-owner/repo" + suffix
        invalid_urls = [
            "http://github.com/custom-owner/repo" + suffix,
            "https://example.org/custom-owner/repo" + suffix,
            "https://github.com.attacker.invalid/custom-owner/repo" + suffix,
            "https://user:password@github.com/custom-owner/repo" + suffix,
            "https://github.com:443/custom-owner/repo" + suffix,
            "https://github.com/./repo" + suffix,
            "https://github.com/../repo" + suffix,
            "https://github.com/custom-owner/." + suffix,
            "https://github.com/custom-owner/.." + suffix,
            "https://github.com/custom_owner/repo" + suffix,
            "https://github.com/-owner/repo" + suffix,
            "https://github.com/custom-owner/percent%2frepo" + suffix,
            valid.replace(self.lock["release"], "latest"),
            valid.replace("team-dev-env-runtimes.zip", "another-asset.zip"),
            valid + "/", valid + "?download=1", valid + "#asset", valid + "\n",
            None,
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.lock["archive"]["url"] = url
                self.write_lock()
                before = self.snapshot()
                with mock.patch("urllib.request.urlopen", side_effect=AssertionError("must not download")), \
                        self.assertRaises(self.module.RuntimeArtifactError):
                    self.fetch(base_url="http://127.0.0.1:1/mirror")
                self.assertEqual(self.snapshot(), before)

    def test_tampered_notices_and_invalid_macho_rejected_with_matching_lock_digests(self):
        self.remove_runtimes()
        for name, replacement in (("resources/cleanup/THIRD_PARTY_NOTICES.txt", b"replaced license"),
                                  ("resources/tui/THIRD_PARTY_NOTICES.txt", b"replaced license"),
                                  (FILES[0], b"not a Mach-O")):
            with self.subTest(name=name):
                payloads = dict(self.payloads)
                payloads[name] = replacement
                if name == FILES[0]:
                    manifest = json.loads(payloads["resources/tui/manifest.json"])
                    manifest["binaries"]["arm64"]["sha256"] = hashlib.sha256(replacement).hexdigest()
                    payloads["resources/tui/manifest.json"] = json.dumps(manifest).encode()
                archive = archive_fixture(payloads)
                self.lock = lock_fixture(payloads, archive)
                self.write_lock()
                before = self.snapshot()
                with serve(archive) as mirror, self.assertRaises(self.module.RuntimeArtifactError):
                    self.fetch(base_url=mirror)
                self.assertEqual(self.snapshot(), before)

    def test_legacy_cleanup_notices_must_be_nonempty_for_local_cache(self):
        path = self.repo / "resources/cleanup/manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["notices_sha256"]
        path.write_text(json.dumps(manifest))
        self.assertFalse(self.fetch(offline=True)["downloaded"])
        (path.parent / "THIRD_PARTY_NOTICES.txt").write_bytes(b"  \n")
        with self.assertRaises(self.module.RuntimeArtifactError):
            self.fetch(offline=True)

    def test_publication_failures_restore_previous_files_and_modes(self):
        (self.repo / FILES[0]).write_bytes(b"previous broken file to repair")
        (self.repo / FILES[0]).chmod(0o640)
        (self.repo / "resources/tui/private.txt").write_text("preserve")
        before = self.snapshot()
        for fail_at in (2, 4, 7):
            with self.subTest(fail_at=fail_at):
                real_replace = self.module.os.replace
                calls = 0

                def fail_once(source, destination):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("injected publication failure")
                    return real_replace(source, destination)

                with serve(self.archive) as mirror, mock.patch.object(self.module.os, "replace", side_effect=fail_once):
                    with self.assertRaisesRegex(self.module.RuntimeArtifactError, "injected publication failure"):
                        self.fetch(base_url=mirror)
                self.assertEqual(self.snapshot(), before)

    def test_failed_first_install_removes_new_runtime_directories(self):
        self.remove_runtimes()
        before = self.snapshot()
        real_replace = self.module.os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("first installation failed")
            return real_replace(source, destination)

        with serve(self.archive) as mirror, mock.patch.object(self.module.os, "replace", side_effect=fail_second):
            with self.assertRaises(self.module.RuntimeArtifactError):
                self.fetch(base_url=mirror)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.repo / "resources/tui").exists())
        self.assertFalse((self.repo / "resources/cleanup").exists())

    def test_failed_rollback_preserves_complete_previous_bundle_for_recovery(self):
        (self.repo / FILES[0]).write_bytes(b"previous artifact to repair")
        previous = {name: (self.repo / name).read_bytes() for name in FILES}
        real_replace = self.module.os.replace
        calls = 0

        def fail_after_first(source, destination):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("persistent write failure")
            return real_replace(source, destination)

        with serve(self.archive) as mirror, mock.patch.object(self.module.os, "replace", side_effect=fail_after_first):
            with self.assertRaisesRegex(self.module.RuntimeArtifactError, "回滚.*保留"):
                self.fetch(base_url=mirror)
        recoveries = list(self.repo.glob(".runtime-stage-*/previous"))
        self.assertEqual(len(recoveries), 1)
        self.assertEqual({name: (recoveries[0] / name).read_bytes() for name in FILES}, previous)

    def test_cleanup_legacy_notices_are_still_pinned_when_downloading(self):
        self.remove_runtimes()
        payloads = dict(self.payloads)
        manifest = json.loads(payloads["resources/cleanup/manifest.json"])
        del manifest["notices_sha256"]
        payloads["resources/cleanup/manifest.json"] = json.dumps(manifest).encode()
        self.lock = lock_fixture(payloads)
        payloads["resources/cleanup/THIRD_PARTY_NOTICES.txt"] = b"replaced old notice\n"
        archive = archive_fixture(payloads)
        revised = lock_fixture(payloads, archive)
        self.lock["archive"], self.lock["release"] = revised["archive"], revised["release"]
        self.write_lock()
        with serve(archive) as mirror, self.assertRaises(self.module.RuntimeArtifactError):
            self.fetch(base_url=mirror)
        self.assertFalse((self.repo / "resources/cleanup").exists())

    def test_sources_changing_during_download_preserve_existing_files(self):
        (self.repo / FILES[0]).write_bytes(b"broken to trigger download")
        before = {name: (self.repo / name).read_bytes() for name in FILES}

        def edit_source(path):
            (self.repo / "tui/main.go").write_bytes(b"package main\n// changed\n")

        with serve(self.archive, on_request=edit_source) as mirror:
            with self.assertRaisesRegex(self.module.RuntimeArtifactError, "源码"):
                self.fetch(base_url=mirror)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in FILES}, before)

    def test_symlink_parent_or_managed_file_is_never_followed_or_replaced(self):
        outside = self.base / "outside"
        outside.mkdir()
        for relative in ("resources/tui", FILES[0]):
            with self.subTest(path=relative):
                target = self.repo / relative
                backup = target.with_name(target.name + ".safe")
                target.rename(backup)
                target.symlink_to(outside, target_is_directory=True)
                try:
                    with serve(self.archive) as mirror, self.assertRaisesRegex(self.module.RuntimeArtifactError, "链接|联接"):
                        self.fetch(base_url=mirror)
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(list(outside.iterdir()), [])
                finally:
                    target.unlink()
                    backup.rename(target)

    def test_windows_reparse_point_attribute_is_rejected_on_any_host(self):
        target = self.repo / "resources/tui"
        real_lstat = Path.lstat

        def reparse_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if path == target:
                return types.SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info

        with mock.patch.object(Path, "lstat", reparse_lstat):
            with self.assertRaisesRegex(self.module.RuntimeArtifactError, "链接|联接"):
                self.fetch(offline=True)

    def test_module_supports_direct_script_import_without_package_context(self):
        result = subprocess.run([sys.executable, "-c", "import runtime_artifacts; print(len(runtime_artifacts.FILES))"],
                                cwd=str(MODULE.parent), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "7")


if __name__ == "__main__":
    unittest.main()
