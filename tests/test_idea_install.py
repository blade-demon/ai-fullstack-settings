"""假挂载、真实 ditto/plutil/mv；只使用临时 HOME 和微型应用包。"""
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2024.3.7.1"
BUILD = "IC-243.28141.41"
APP_NAME = "IntelliJ IDEA CE.app"


class IdeaInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="IDEA 安装's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具's 目录/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "Users/用户's home"
        self.home.mkdir(parents=True)
        self.bin = self.base / "fake-bin"
        self.bin.mkdir()
        self.tmp = self.base / "临时 mount's"
        self.tmp.mkdir()
        self.dmg = self.base / "IDEA's 安装包.dmg"
        self.dmg.write_bytes(b"fixture disk image")
        self.sha = hashlib.sha256(self.dmg.read_bytes()).hexdigest()
        self.app = self.base / "fixture.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        self.app.chmod(0o755)
        self.metadata = {"CFBundleIdentifier": "com.jetbrains.intellij.ce",
                         "CFBundleShortVersionString": VERSION, "CFBundleVersion": BUILD,
                         "CFBundleExecutable": "idea"}
        self.write_metadata(self.metadata)
        self.executable = self.app / "Contents/MacOS/idea"
        self.executable.write_text('#!/bin/sh\ntouch "$IDEA_EXEC_RECORD"\n')
        self.executable.chmod(0o755)
        self.mount_record = self.base / "mount-record"
        self.calls = self.base / "hdiutil-calls"
        self.exec_record = self.base / "executed-idea"
        hdiutil = self.bin / "hdiutil"
        hdiutil.write_text(
            '#!/bin/bash\nset -eu\nprintf "%s\\n" "$@" >> "$HDIUTIL_CALLS"\n'
            'case "$1" in\n'
            ' attach) shift; mountpoint=""; while [ "$#" -gt 0 ]; do\n'
            '   if [ "$1" = -mountpoint ]; then mountpoint="$2"; shift 2; else shift; fi\n'
            ' done\n'
            ' printf "%s\\n" "$mountpoint" > "$MOUNT_RECORD"\n'
            ' /usr/bin/ditto "$FIXTURE_APP" "$mountpoint/IntelliJ IDEA CE.app"\n'
            ' exit "${ATTACH_EXIT:-0}" ;;\n'
            ' detach) exit "${DETACH_EXIT:-0}" ;;\n'
            ' *) exit 91 ;;\n'
            'esac\n'
        )
        hdiutil.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "LC_ALL": "C.UTF-8", "TMPDIR": str(self.tmp), "FIXTURE_APP": str(self.app),
                    "MOUNT_RECORD": str(self.mount_record), "HDIUTIL_CALLS": str(self.calls),
                    "IDEA_EXEC_RECORD": str(self.exec_record), "CDPATH": str(self.base),
                    "USER": "other-login", "LOGNAME": "other-login"}
        self.target = self.home / "Applications" / APP_NAME

    def write_metadata(self, metadata, app=None):
        with ((app or self.app) / "Contents/Info.plist").open("wb") as stream:
            plistlib.dump(metadata, stream)

    def run_script(self, *args, extra=None, defaults=True):
        argv = ["/bin/bash", str(self.support / "scripts/software/install-idea.sh")]
        if defaults:
            argv.extend(("--dmg", str(self.dmg), "--sha256", self.sha, "--version", VERSION))
        return subprocess.run([*argv, *args], cwd=self.base, env={**self.env, **(extra or {})},
                              text=True, capture_output=True, timeout=15)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_clean(self):
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertFalse(list((self.home / "Applications").glob(".idea-install.*")))
        self.assertFalse(self.exec_record.exists())

    def fake_ditto(self, body):
        script = self.bin / "ditto"
        script.write_text("#!/bin/bash\nset -eu\n" + body)
        script.chmod(0o755)

    def test_install_to_user_applications_validates_and_cleans_mount(self):
        # HOME is authoritative, even if login variables or an inherited value differ.
        unexpected = self.base / "external-applications"
        result = self.run_script(extra={"USER_APPLICATIONS_DIR": str(unexpected)})
        self.assert_ok(result)
        self.assertIn(str(self.target), result.stdout)
        self.assertIn("已安装", result.stdout)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o755)
        self.assertTrue(os.access(self.target / "Contents/MacOS/idea", os.X_OK))
        self.assertFalse((self.home / "Users").exists())
        self.assertFalse((self.base / "Users/other-login").exists())
        self.assertFalse(unexpected.exists())
        with (self.target / "Contents/Info.plist").open("rb") as stream:
            self.assertEqual(plistlib.load(stream), self.metadata)
        calls = self.calls.read_text().splitlines()
        self.assertIn("-readonly", calls)
        self.assertIn("-nobrowse", calls)
        self.assertIn("detach", calls)
        self.assertNotIn("-force", calls)
        self.assert_clean()

    def test_same_build_is_reused_without_copying_or_replacing(self):
        self.assert_ok(self.run_script())
        inode = self.target.stat().st_ino
        sentinel = self.target / "keep-existing-file"
        sentinel.write_text("preserve")
        self.fake_ditto("exit 89\n")
        result = self.run_script()
        self.assert_ok(result)
        self.assertIn("复用", result.stdout)
        self.assertEqual(self.target.stat().st_ino, inode)
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assert_clean()

    def test_help_shows_expanded_install_destination_without_writing(self):
        result = self.run_script("--help", defaults=False)
        self.assert_ok(result)
        self.assertIn(str(self.target), result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_hash_failure_never_mounts_or_creates_applications(self):
        result = self.run_script("--sha256", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(list(self.home.iterdir()), [])
        self.assert_clean()

    def test_dry_run_does_not_mount_copy_hash_or_create_directories(self):
        # 预演只检查参数和文件存在；不将错误摘要当作真正完成的校验。
        result = self.run_script("--dry-run", "--sha256", "0" * 64)
        self.assert_ok(result)
        self.assertIn(str(self.target), result.stdout)
        self.assertFalse(self.calls.exists())
        self.assertEqual(list(self.home.iterdir()), [])
        self.assert_clean()

    def test_old_different_build_and_incomplete_existing_apps_are_preserved(self):
        for changes in ({"CFBundleShortVersionString": "2024.2"}, {"CFBundleVersion": "IC-old"},
                        {"CFBundleIdentifier": "com.jetbrains.intellij"}, {"CFBundleExecutable": "missing"}):
            with self.subTest(changes=changes):
                if self.target.exists():
                    shutil.rmtree(self.target)
                shutil.copytree(self.app, self.target)
                metadata = {**self.metadata, **changes}
                self.write_metadata(metadata, self.target)
                before = (self.target / "Contents/Info.plist").read_bytes()
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("保留", result.stderr)
                self.assertEqual((self.target / "Contents/Info.plist").read_bytes(), before)
                self.assert_clean()

    def test_symlinked_applications_or_target_is_rejected_without_touching_destination(self):
        outside = self.base / "outside"
        outside.mkdir()
        applications = self.home / "Applications"
        applications.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        applications.unlink()
        applications.mkdir()
        self.target.symlink_to(outside / "nonexistent")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.calls.exists())
        self.assert_clean()

    def test_bad_bundle_is_rejected_before_creating_target_and_detaches(self):
        for changes in ({"CFBundleIdentifier": "wrong"}, {"CFBundleShortVersionString": "2025.1"},
                        {"CFBundleVersion": ""}, {"CFBundleExecutable": "wrong"}):
            with self.subTest(changes=changes):
                self.write_metadata({**self.metadata, **changes})
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse(self.target.exists())
                self.assert_clean()
        self.write_metadata(self.metadata)
        self.executable.chmod(0o644)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_copy_failure_removes_only_own_staging(self):
        self.fake_ditto('mkdir -p "$2"\nprintf partial > "$2/partial"\nexit 19\n')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_copy_metadata_is_revalidated_before_publish(self):
        self.fake_ditto('/usr/bin/ditto "$@"\n/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier wrong" "$2/Contents/Info.plist"\n')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_target_created_during_copy_is_preserved(self):
        self.fake_ditto('/usr/bin/ditto "$@"\nmkdir -p "$HOME/Applications/IntelliJ IDEA CE.app"\nprintf existing > "$HOME/Applications/IntelliJ IDEA CE.app/keep"\n')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual((self.target / "keep").read_text(), "existing")
        self.assertFalse((self.target / "Contents").exists())
        self.assert_clean()

    def test_failed_attach_still_detaches_own_mount(self):
        self.assertNotEqual(self.run_script(extra={"ATTACH_EXIT": "7"}).returncode, 0)
        self.assertIn("detach", self.calls.read_text().splitlines())
        self.assertFalse(self.target.exists())
        self.assert_clean()

    def test_failed_detach_keeps_mount_directory_and_reports_it(self):
        result = self.run_script(extra={"DETACH_EXIT": "16"})
        self.assertNotEqual(result.returncode, 0)
        mount = Path(self.mount_record.read_text().strip())
        self.assertTrue((mount / APP_NAME).exists())
        self.assertIn(str(mount), result.stdout + result.stderr)
        self.assertNotIn("已安装", result.stdout)
        self.assertTrue(self.target.exists())
        self.assertFalse(list((self.home / "Applications").glob(".idea-install.*")))
        self.assertFalse(self.exec_record.exists())

    def test_required_arguments_help_and_missing_image(self):
        self.assert_ok(self.run_script("--help", defaults=False))
        for args in ((), ("--dmg",), ("--dmg", "--dry-run"), ("--dmg", ""),
                     ("--target", "/Applications/anything")):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_script(*args, defaults=False).returncode, 0)
        self.assertNotEqual(self.run_script("--sha256", "invalid").returncode, 0)
        self.assertNotEqual(self.run_script("--dmg", str(self.base / "missing"), "--dry-run").returncode, 0)
        self.assertFalse(self.calls.exists())
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
