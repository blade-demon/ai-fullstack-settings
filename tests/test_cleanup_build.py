"""构建元数据、跨平台源码摘要和损坏产物拒绝；不运行卸载。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build-cleanup.py"
NAME = "cleanup-macos-universal2"


def universal_fixture():
    """两个有效且不重叠的最小 Mach-O 头；无需在测试机执行。"""
    payload = bytearray(8224)
    struct.pack_into(">II", payload, 0, 0xCAFEBABE, 2)
    for index, cpu in enumerate((0x0100000C, 0x01000007)):
        offset = 4096 * (index + 1)
        struct.pack_into(">IIIII", payload, 8 + 20 * index, cpu, 0, offset, 32, 12)
        struct.pack_into("<IIIIIIII", payload, offset, 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0)
    return bytes(payload)


class CleanupBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.is_file():
            spec = importlib.util.spec_from_file_location("cleanup_build", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "缺少可验证的卸载构建入口")
        self.temp = tempfile.TemporaryDirectory(prefix="cleanup build ' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "uninstall_java_gradle.py"
        self.source.write_bytes(b"print('cleanup')\n")
        self.output = self.base / "output"
        self.output.mkdir()
        self.binary = self.output / NAME
        self.binary.write_bytes(universal_fixture())
        self.binary.chmod(0o755)
        self.notices = self.output / "THIRD_PARTY_NOTICES.txt"
        self.notices.write_text("Python Software Foundation / PyInstaller license fixture\n")
        self.manifest = {
            "schema": 1,
            "sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(b"print('cleanup')\n").hexdigest(),
            "architectures": ["arm64", "x86_64"],
            "python_version": "3.14.6",
            "pyinstaller_version": "6.22.3",
            "notices_sha256": hashlib.sha256(self.notices.read_bytes()).hexdigest(),
        }
        self.write_manifest()

    def write_manifest(self):
        (self.output / "manifest.json").write_text(json.dumps(self.manifest))

    def test_source_hash_accepts_windows_newlines_and_utf8_bom(self):
        self.source.write_bytes(b"\xef\xbb\xbfprint('cleanup')\r\n")
        self.assertEqual(self.module.source_sha256(self.source), self.manifest["source_sha256"])
        self.source.write_bytes(b"print('cleanup')\r")
        self.assertEqual(self.module.source_sha256(self.source), self.manifest["source_sha256"])

    def test_verify_accepts_matching_universal_binary(self):
        manifest = self.module.verify_bundle(self.output, self.source)
        self.assertEqual(manifest["architectures"], ["arm64", "x86_64"])

    def test_verify_rejects_binary_changed_since_manifest(self):
        with self.binary.open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaisesRegex(self.module.BuildError, "SHA-256"):
            self.module.verify_bundle(self.output, self.source)

    def test_verify_rejects_outdated_source(self):
        self.source.write_text("print('new cleanup')\n")
        with self.assertRaisesRegex(self.module.BuildError, "源码"):
            self.module.verify_bundle(self.output, self.source)

    def test_verify_rejects_declared_universal_binary_with_wrong_slice(self):
        payload = bytearray(self.binary.read_bytes())
        struct.pack_into(">I", payload, 28, 0x0100000C)
        self.binary.write_bytes(payload)
        self.manifest["sha256"] = hashlib.sha256(payload).hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(self.module.BuildError, "架构|Mach-O"):
            self.module.verify_bundle(self.output, self.source)

    def test_verify_rejects_truncated_fat_slice_even_with_updated_digest(self):
        self.binary.write_bytes(self.binary.read_bytes()[:8193])
        self.manifest["sha256"] = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(self.module.BuildError, "Mach-O"):
            self.module.verify_bundle(self.output, self.source)

    def test_verify_rejects_missing_license(self):
        self.notices.unlink()
        with self.assertRaisesRegex(self.module.BuildError, "许可|THIRD_PARTY"):
            self.module.verify_bundle(self.output, self.source)

    def test_verify_rejects_changed_license(self):
        self.notices.write_text("removed legal text")
        with self.assertRaisesRegex(self.module.BuildError, "许可|THIRD_PARTY"):
            self.module.verify_bundle(self.output, self.source)

    def test_non_mac_build_fails_before_touching_output(self):
        with mock.patch.object(self.module.sys, "platform", "win32"):
            result = self.module.main(["--output", str(self.base / "uncreated")])
        self.assertEqual(result, 1)
        self.assertFalse((self.base / "uncreated").exists())

    def test_failed_source_recheck_keeps_existing_release(self):
        previous = self.binary.read_bytes()
        self.source.write_text("print('concurrent edit')\n")
        with self.assertRaisesRegex(self.module.BuildError, "源码"):
            self.module.publish_bundle(self.output, self.binary, self.source,
                                       self.manifest["source_sha256"], self.manifest,
                                       self.notices.read_text())
        self.assertEqual(self.binary.read_bytes(), previous)

    def assert_publication_failure_preserves_existing_release(self, failed_replacement):
        self.binary.chmod(0o751)
        self.notices.chmod(0o640)
        (self.output / "manifest.json").chmod(0o600)
        unknown = self.output / "用户保留目录" / "自定义文件.txt"
        unknown.parent.mkdir()
        unknown.write_bytes(b"user-owned content")
        unknown.chmod(0o640)
        previous = {path.relative_to(self.output): (path.read_bytes(), path.stat().st_mode)
                    for path in self.output.rglob("*") if path.is_file()}
        candidate = self.base / "new-cleanup"
        candidate.write_bytes(universal_fixture() + b"new release")
        replace = self.module.os.replace
        calls = 0

        def fail_once(source, destination):
            nonlocal calls
            calls += 1
            if calls == failed_replacement:
                raise OSError("injected publication failure")
            return replace(source, destination)

        with mock.patch.object(self.module.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "injected publication failure"):
                self.module.publish_bundle(self.output, candidate, self.source,
                                           self.manifest["source_sha256"], self.manifest,
                                           "new license notice\n")
        current = {path.relative_to(self.output): (path.read_bytes(), path.stat().st_mode)
                   for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(current, previous)
        self.assertEqual(self.module.verify_bundle(self.output, self.source), self.manifest)

    def test_second_publish_replacement_failure_restores_old_bundle_and_modes(self):
        self.assert_publication_failure_preserves_existing_release(2)

    def test_third_publish_replacement_failure_restores_old_bundle_and_modes(self):
        self.assert_publication_failure_preserves_existing_release(3)

    def test_failed_rollback_keeps_recovery_files(self):
        candidate = self.base / "new-cleanup"
        candidate.write_bytes(universal_fixture() + b"new release")
        replace = self.module.os.replace
        calls = 0

        def fail_publication_and_rollback(source, destination):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("persistent write failure")
            return replace(source, destination)

        with mock.patch.object(self.module.os, "replace", side_effect=fail_publication_and_rollback):
            with self.assertRaisesRegex(self.module.BuildError, "回滚.*保留"):
                self.module.publish_bundle(self.output, candidate, self.source,
                                           self.manifest["source_sha256"], self.manifest,
                                           "new license notice\n")
        recovery = list(self.base.glob(".cleanup-publish-*"))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(self.module.verify_bundle(recovery[0] / "previous", self.source), self.manifest)

    def test_help_does_not_require_pyinstaller_or_create_output(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=self.base,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--verify-only", result.stdout)

    def test_failed_runtime_check_reports_underlying_error(self):
        error = subprocess.CalledProcessError(1, ["cleanup", "--help"], stderr=b"semctl: Operation not permitted")
        captured = io.StringIO()
        with mock.patch.object(self.module, "build", side_effect=error), mock.patch.object(self.module.sys, "stderr", captured):
            result = self.module.main(["--output", str(self.output)])
        self.assertEqual(result, 1)
        self.assertIn("semctl: Operation not permitted", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
