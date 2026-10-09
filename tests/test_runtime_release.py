"""Runtime release contracts use tiny Mach-O fixtures and never build or upload."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

try:
    from .cleanup_fixture import cleanup_fixture
    from .tui_fixture import tui_fixture
except ImportError:
    from cleanup_fixture import cleanup_fixture
    from tui_fixture import tui_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/release-runtimes.py"
MEMBERS = (
    "resources/cleanup/THIRD_PARTY_NOTICES.txt",
    "resources/cleanup/cleanup-macos-universal2",
    "resources/cleanup/manifest.json",
    "resources/tui/THIRD_PARTY_NOTICES.txt",
    "resources/tui/manifest.json",
    "resources/tui/team-dev-env-amd64",
    "resources/tui/team-dev-env-arm64",
)
ARCHIVE = "team-dev-env-runtimes.zip"


class RuntimeReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.is_file():
            spec = importlib.util.spec_from_file_location("runtime_release", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "缺少运行文件发布包生成器")
        self.temp = tempfile.TemporaryDirectory(prefix="runtime release ' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "tools").mkdir()
        (self.root / "tools/uninstall_java_gradle.py").write_bytes(b"# cleanup fixture\n")
        tui_fixture(self.root)
        cleanup_fixture(self.root)
        self.output = self.root / "dist/runtime-release"
        self.lock = self.root / "resources/runtime-lock.json"

    def release(self, **kwargs):
        return self.module.release_runtimes(self.root, self.output, self.lock,
                                            "fixture-owner/fixture-repo", **kwargs)

    def snapshot(self):
        return {path.relative_to(self.root).as_posix():
                (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def seed_previous(self):
        self.output.mkdir(parents=True)
        for name in (ARCHIVE,):
            (self.output / name).write_bytes(("previous " + name).encode())
        self.lock.write_bytes(b"previous lock\n")

    def test_archive_is_deterministic_exact_and_uses_portable_metadata(self):
        (self.root / "resources/tui/README.md").write_text("not a release member")
        first = self.release()
        archive_bytes = (self.output / ARCHIVE).read_bytes()
        lock_bytes = self.lock.read_bytes()
        for name in MEMBERS:
            os.utime(self.root / name, (1234567890, 1234567890))
            (self.root / name).chmod(0o600)
        second = self.release()
        self.assertEqual(first, second)
        self.assertEqual((self.output / ARCHIVE).read_bytes(), archive_bytes)
        self.assertEqual(self.lock.read_bytes(), lock_bytes)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(archive.namelist(), list(MEMBERS))
            for member in archive.infolist():
                self.assertFalse(member.is_dir())
                self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(member.create_system, 3)
                mode = (member.external_attr >> 16) & 0xFFFF
                self.assertTrue(stat.S_ISREG(mode))
                self.assertEqual(stat.S_IMODE(mode),
                                 0o755 if "team-dev-env-" in member.filename
                                 or member.filename.endswith("cleanup-macos-universal2") else 0o644)
                self.assertEqual(archive.read(member), (self.root / member.filename).read_bytes())

    def test_lock_hashes_url_sizes_and_notes_describe_complete_release(self):
        result = self.release()
        archive = (self.output / ARCHIVE).read_bytes()
        digest = hashlib.sha256(archive).hexdigest()
        release = "runtimes-" + digest[:16]
        expected_sources = {
            kind: json.loads((self.root / ("resources/%s/manifest.json" % kind)).read_text())["source_sha256"]
            for kind in ("tui", "cleanup")}
        self.assertEqual(json.loads(self.lock.read_text()), result)
        self.assertEqual(set(result), {"schema", "release", "source_sha256", "archive", "files"})
        self.assertEqual(result["schema"], 1)
        self.assertEqual(result["release"], release)
        self.assertEqual(result["source_sha256"], expected_sources)
        self.assertEqual(result["archive"], {
            "url": "https://github.com/fixture-owner/fixture-repo/releases/download/%s/%s" % (release, ARCHIVE),
            "sha256": digest, "size": len(archive)})
        self.assertEqual(set(result["files"]), set(MEMBERS))
        for name in MEMBERS:
            payload = (self.root / name).read_bytes()
            self.assertEqual(result["files"][name], {
                "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)})
        self.assertEqual({p.name for p in self.output.iterdir()}, {ARCHIVE})
        notes = self.module.release_notes(result).decode("utf-8")
        for value in (release, digest, "Go", "Windows", *expected_sources.values(), *MEMBERS):
            self.assertIn(value, notes)

    def test_missing_corrupt_or_stale_inputs_preserve_previous_release(self):
        self.seed_previous()
        cases = (("resources/tui/team-dev-env-arm64", b"corrupt binary"),
                 ("resources/cleanup/cleanup-macos-universal2", None),
                 ("tui/main.go", b"package main\n// changed source\n"),
                 ("tools/uninstall_java_gradle.py", b"# changed cleanup\n"))
        for name, replacement in cases:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                if replacement is None:
                    path.unlink()
                else:
                    path.write_bytes(replacement)
                before = self.snapshot()
                with self.assertRaises((ValueError, OSError)):
                    self.release()
                self.assertEqual(self.snapshot(), before)
                path.write_bytes(original)

    def test_source_edit_during_archive_generation_preserves_previous_release(self):
        self.seed_previous()
        before = {p: data for p, data in self.snapshot().items() if p.startswith("dist/") or p.endswith("runtime-lock.json")}
        build_archive = self.module.build_archive

        def concurrent_edit(payloads):
            result = build_archive(payloads)
            (self.root / "tui/main.go").write_bytes(b"package main\n// concurrent edit\n")
            return result

        with mock.patch.object(self.module, "build_archive", side_effect=concurrent_edit):
            with self.assertRaisesRegex(ValueError, "源码|过期|变化"):
                self.release()
        after = {p: data for p, data in self.snapshot().items() if p.startswith("dist/") or p.endswith("runtime-lock.json")}
        self.assertEqual(after, before)

    def test_verify_only_does_not_write_and_rejects_archive_or_lock_tampering(self):
        self.release()
        before = self.snapshot()
        self.release(verify_only=True)
        self.assertEqual(self.snapshot(), before)
        for target in (self.output / ARCHIVE, self.lock):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.write_bytes(original + b"tamper")
                bad_snapshot = self.snapshot()
                with self.assertRaises((ValueError, OSError)):
                    self.release(verify_only=True)
                self.assertEqual(self.snapshot(), bad_snapshot)
                target.write_bytes(original)

    def test_verify_only_missing_release_does_not_create_output_or_lock(self):
        before = self.snapshot()
        with self.assertRaises((ValueError, OSError)):
            self.release(verify_only=True)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.lock.exists())

    def test_verify_only_rejects_boolean_schema_and_float_sizes(self):
        self.release()
        original = self.lock.read_bytes()
        for key in ("schema", "size"):
            with self.subTest(key=key):
                lock = json.loads(original)
                if key == "schema":
                    lock["schema"] = True
                else:
                    lock["archive"]["size"] = float(lock["archive"]["size"])
                self.lock.write_text(json.dumps(lock), encoding="utf-8")
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.release(verify_only=True)
                self.assertEqual(self.snapshot(), before)

    def test_verify_only_rejects_duplicate_lock_fields(self):
        self.release()
        original = self.lock.read_text(encoding="utf-8")
        self.lock.write_text(original.replace('"schema": 1', '"schema": 999, "schema": 1'), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.release(verify_only=True)
        self.assertEqual(self.snapshot(), before)

    def test_write_failure_rolls_back_all_replaced_files_and_modes(self):
        self.seed_previous()
        before = self.snapshot()
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                replace, calls = self.module.os.replace, 0

                def fail_once(source, target):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("injected replace failure")
                    return replace(source, target)

                with mock.patch.object(self.module.os, "replace", side_effect=fail_once):
                    with self.assertRaisesRegex(OSError, "injected replace failure"):
                        self.release()
                self.assertEqual(self.snapshot(), before)

    def test_source_edit_during_publish_rolls_back_release_and_lock(self):
        self.seed_previous()
        previous = {name: self.snapshot()[name] for name in (
            "dist/runtime-release/" + ARCHIVE,
            "resources/runtime-lock.json")}
        replace, calls = self.module.os.replace, 0

        def edit_after_lock(source, target):
            nonlocal calls
            calls += 1
            result = replace(source, target)
            if calls == 2:
                (self.root / "tools/uninstall_java_gradle.py").write_bytes(b"# concurrent cleanup edit\n")
            return result

        with mock.patch.object(self.module.os, "replace", side_effect=edit_after_lock):
            with self.assertRaisesRegex(ValueError, "源码|过期|变化"):
                self.release()
        after = self.snapshot()
        self.assertEqual({name: after[name] for name in previous}, previous)

    def test_invalid_repository_is_rejected_before_writing(self):
        for repository in ("https://github.com/owner/repo", "owner/repo/releases", "owner/..", "owner/repo?x=1"):
            with self.subTest(repository=repository):
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "owner/repo"):
                    self.module.release_runtimes(self.root, self.output, self.lock, repository)
                self.assertEqual(self.snapshot(), before)

    def test_windows_source_checkout_produces_same_lock_and_archive(self):
        self.release()
        lock = self.lock.read_bytes()
        archive = (self.output / ARCHIVE).read_bytes()
        sources = list((self.root / "tui").iterdir()) + [self.root / "tools/uninstall_java_gradle.py"]
        for source in sources:
            source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes().replace(b"\n", b"\r\n"))
        self.release(verify_only=True)
        self.release()
        self.assertEqual(self.lock.read_bytes(), lock)
        self.assertEqual((self.output / ARCHIVE).read_bytes(), archive)

    def test_cli_uses_defaults_and_returns_nonzero_on_invalid_bundle(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in ("--output", "--lock", "--repository", "--verify-only"):
            self.assertIn(option, result.stdout)
        with mock.patch.object(self.module, "ROOT", self.root):
            self.assertEqual(self.module.main([]), 0)
            lock = json.loads(self.lock.read_text())
            self.assertIn("github.com/blade-demon/ai-fullstack-settings/", lock["archive"]["url"])
            self.assertEqual(self.module.main(["--verify-only"]), 0)
            (self.root / MEMBERS[1]).unlink()
            self.assertEqual(self.module.main(["--verify-only"]), 1)


if __name__ == "__main__":
    unittest.main()
