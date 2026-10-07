"""真实 ZIP/JAR/XML 与微型 IDEA fixture；绝不修改当前用户的 IDEA 插件目录。"""
import hashlib
import io
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = (
    ("database-navigator", "DBNavigator", "DBN", "4.1.0.3"),
    ("mybatisx", "MybatisX", "com.baomidou.plugin.idea.mybatisx", "1.7.6"),
    ("generate-all-setter", "GenerateAllSetter", "com.bruce.intellijplugin.generatesetter", "2.8.5"),
    ("gsonformatplus", "GsonFormatPlus", "GsonFormatPlus", "1.6.1"),
    ("key-promoter-x", "Key Promoter X", "Key Promoter X", "2026.1.2"),
    ("lombok", "lombok", "Lombook Plugin", "243.28141.18"),
)


class IdeaPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="IDEA 插件's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.support = self.base / "工具/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.app = self.home / "Applications/IntelliJ IDEA CE.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/MacOS/idea").write_text("do not execute")
        (self.app / "Contents/MacOS/idea").chmod(0o755)
        with (self.app / "Contents/Info.plist").open("wb") as f:
            plistlib.dump({"CFBundleIdentifier": "com.jetbrains.intellij.ce",
                          "CFBundleShortVersionString": "2024.3.7.1",
                          "CFBundleVersion": "IC-243.28141.41"}, f)
        (self.app / "Contents/Resources").mkdir()
        (self.app / "Contents/Resources/product-info.json").write_text('{"dataDirectoryName":"IdeaIC2024.3"}')
        self.plugins = self.home / "Library/Application Support/JetBrains/IdeaIC2024.3/plugins"
        self.sources = self.base / "离线 fixture"
        self.sources.mkdir()
        self.catalog = self.support / "config/resources.tsv"
        self.audit = self.base / "审计 run"
        self.audit.mkdir()
        self.tmp = self.base / "tmp"
        self.tmp.mkdir()
        self.fakebin = self.base / "bin"
        self.fakebin.mkdir()
        (self.fakebin / "ps").write_text('#!/bin/sh\n[ -z "${FIXTURE_IDEA_RUNNING:-}" ] || printf "%s\\n" "$HOME/Applications/IntelliJ IDEA CE.app/Contents/MacOS/idea"\nexit 0\n')
        (self.fakebin / "ps").chmod(0o755)
        self.download_marker = self.base / "download calls"
        (self.support / "scripts/download-tools.sh").write_text(
            '#!/bin/bash\nset -eu\n[ "$1" = --id ]\nprintf "%s\\n" "$2" >> "$DOWNLOAD_RECORD"\n'
            'relative="$(awk -F "\\t" -v id="$2" \'$1==id {print $5}\' "$FIXTURE_CATALOG")"\n'
            'mkdir -p "$(dirname "$HOME/Downloads/team-java-env/$relative")"\n'
            'cp "$FIXTURE_DOWNLOAD_SOURCE/$2.zip" "$HOME/Downloads/team-java-env/$relative"\n')
        self.env = {"HOME": str(self.home), "PATH": f"{self.fakebin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "TMPDIR": str(self.tmp), "LC_ALL": "C", "REPAIR_RUN_DIR": str(self.audit),
                    "FIXTURE_DOWNLOAD_SOURCE": str(self.sources), "FIXTURE_CATALOG": str(self.catalog),
                    "DOWNLOAD_RECORD": str(self.download_marker)}
        self.rows = []
        for rid, directory, xml_id, version in PLUGINS:
            self.write_zip(rid, directory, xml_id, version, omit_id=rid in ("gsonformatplus", "key-promoter-x"))
        self.save_catalog()

    def jar(self, plugin_id, version, since="231", until="243.*", omit_id=False, dependency="com.intellij.modules.java"):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("META-INF/plugin.xml", '<idea-plugin>' +
                             ("" if omit_id else f"<id>{plugin_id}</id>") +
                             f'<name>{plugin_id}</name><version>{version}</version>'
                             f'<idea-version since-build="{since}" until-build="{until}"/>'
                             f'<depends>{dependency}</depends></idea-plugin>')
            archive.writestr("fixture/Plugin.class", b"fixture class bytes")
        return data.getvalue()

    def write_zip(self, rid, directory, xml_id, version, **kwargs):
        target = self.sources / f"{rid}.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr(f"{directory}/lib/plugin.jar", self.jar(xml_id, version, **kwargs))
            archive.writestr(f"{directory}/LICENSE", b"fixture license")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        row = [rid, "plugins", version, "any", f"plugins/idea/{rid}.zip", f"https://official.invalid/{rid}.zip", digest]
        self.rows = [r for r in self.rows if r[0] != rid] + [row]

    def save_catalog(self):
        self.catalog.write_text("# id\tgroup\tversion\tarch\tpath\turl\tsha256\n" +
                                "".join("\t".join(row) + "\n" for row in self.rows))

    def run_script(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/software/install-idea-plugins.sh"), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, capture_output=True, text=True, timeout=60)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self, directory):
        if not directory.exists():
            return {}
        return {str(p.relative_to(directory)): (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns)
                for p in directory.rglob("*") if p.is_file() and not p.is_symlink()}

    def install_old(self, directory="Old MyBatis", plugin_id=PLUGINS[1][2], version="1.0"):
        old = self.plugins / directory
        (old / "lib").mkdir(parents=True)
        (old / "lib/old.jar").write_bytes(self.jar(plugin_id, version))
        (old / "keep.txt").write_text("old user content")
        return old

    def test_installs_all_catalog_plugins_and_verifies_without_downloading_or_replacing_again(self):
        unknown = self.plugins / "Unrelated Plugin"
        unknown.mkdir(parents=True)
        (unknown / "private.txt").write_text("preserve")
        self.assert_ok(self.run_script())
        for rid, directory, _, _ in PLUGINS:
            self.assertTrue((self.plugins / directory / "lib/plugin.jar").is_file(), rid)
        before = self.snapshot(self.plugins)
        directory_stamp = self.plugins.stat().st_mtime_ns
        downloads = self.download_marker.read_bytes()
        self.assert_ok(self.run_script())
        self.assertEqual(self.snapshot(self.plugins), before)
        self.assertEqual(self.plugins.stat().st_mtime_ns, directory_stamp)
        self.assertEqual(self.download_marker.read_bytes(), downloads)
        shutil.rmtree(self.home / "Downloads")
        result = self.run_script("--verify-only")
        self.assert_ok(result)
        self.assertEqual(self.snapshot(self.plugins), before)
        self.assertEqual(self.download_marker.read_bytes(), downloads)
        self.assertIn("下次", result.stdout)
        self.assertIn("运行", result.stdout)
        rows = (self.audit / "plugins-result.tsv").read_text()
        for rid, _, _, version in PLUGINS:
            self.assertIn(f"{rid}\t{version}\t", rows)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_frontend_shell_plugins_are_not_treated_as_idea_plugins(self):
        self.rows.append(['oh-my-zsh', 'plugins', 'snapshot', 'any',
                          'frontend/zsh/oh-my-zsh.tar.gz', 'https://official.invalid/zsh.tar.gz', '-'])
        self.save_catalog()
        result = self.run_script('--dry-run')
        self.assert_ok(result)
        self.assertIn('全部 6 个插件', result.stdout)
        self.assertNotIn('oh-my-zsh', result.stdout)

    def test_dry_run_does_not_download_or_create_plugin_directory(self):
        self.assert_ok(self.run_script("--dry-run"))
        self.assertFalse(self.plugins.exists())
        self.assertFalse(self.download_marker.exists())

    def test_verify_only_missing_plugins_fails_without_download_or_profile_creation(self):
        result = self.run_script("--verify-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.plugins.exists())
        self.assertFalse(self.download_marker.exists())

    def test_hash_mismatch_and_incompatible_version_leave_all_plugins_uninstalled(self):
        rid, directory, xml_id, version = PLUGINS[-1]
        self.write_zip(rid, directory, xml_id, version, since="251")
        self.save_catalog()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.plugins / PLUGINS[0][1]).exists())
        self.write_zip(rid, directory, xml_id, version)
        self.save_catalog()
        (self.sources / f"{rid}.zip").write_bytes(b"bad hash")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.plugins / PLUGINS[0][1]).exists())

    def test_zip_path_traversal_and_symlink_are_rejected_before_extracting(self):
        rid = PLUGINS[0][0]
        for bad_name, symlink in (("DBNavigator/../../escaped", False), ("DBNavigator/escape", True)):
            with self.subTest(bad_name=bad_name):
                target = self.sources / f"{rid}.zip"
                with zipfile.ZipFile(target, "w") as archive:
                    info = zipfile.ZipInfo(bad_name)
                    if symlink:
                        info.create_system = 3
                        info.external_attr = (0o120777 << 16)
                    archive.writestr(info, "../../escaped" if symlink else "malicious")
                self.rows[0][-1] = hashlib.sha256(target.read_bytes()).hexdigest()
                self.save_catalog()
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertFalse((self.base / "escaped").exists())
                self.assertFalse((self.plugins / PLUGINS[0][1]).exists())

    def test_unrelated_destination_conflict_does_not_overwrite_any_plugin(self):
        old = self.install_old(directory=PLUGINS[-1][1], plugin_id="unrelated.plugin")
        before = self.snapshot(old)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(old), before)
        self.assertFalse((self.plugins / PLUGINS[0][1]).exists())

    def test_existing_known_old_version_is_backed_up_before_upgrade(self):
        old = self.install_old()
        original = (old / "lib/old.jar").read_bytes()
        self.assert_ok(self.run_script())
        self.assertFalse(old.exists())
        self.assertTrue((self.plugins / "MybatisX/lib/plugin.jar").exists())
        backups = list((self.audit / "plugin-backups").rglob("old.jar"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertIn("upgraded", (self.audit / "plugins-result.tsv").read_text())

    def test_verification_keeps_install_actions_and_backup_audit_intact(self):
        self.install_old()
        self.assert_ok(self.run_script())
        install_result = self.audit / "plugins-result.tsv"
        before = install_result.read_bytes()
        stamp = install_result.stat().st_mtime_ns
        self.assertIn(b"upgraded", before)
        self.assertIn(b"plugin-backups", before)
        self.assert_ok(self.run_script("--verify-only"))
        self.assertEqual(install_result.read_bytes(), before)
        self.assertEqual(install_result.stat().st_mtime_ns, stamp)
        verification = (self.audit / "plugins-verification.tsv").read_text()
        self.assertEqual(verification.count("\tverified\t"), len(PLUGINS))

    def test_corrupt_installed_jar_fails_verify_and_is_backed_up_during_repair(self):
        self.assert_ok(self.run_script())
        broken = self.plugins / "MybatisX/lib/plugin.jar"
        broken.write_bytes(b"truncated")
        before = self.snapshot(self.plugins)
        self.assertNotEqual(self.run_script("--verify-only").returncode, 0)
        self.assertEqual(self.snapshot(self.plugins), before)
        self.assert_ok(self.run_script())
        self.assertNotEqual(broken.read_bytes(), b"truncated")
        self.assertTrue(any(p.read_bytes() == b"truncated" for p in (self.audit / "plugin-backups").rglob("plugin.jar")))

    def test_missing_receipt_and_catalog_hash_change_are_not_reported_verified(self):
        self.assert_ok(self.run_script())
        self.rows[0][-1] = "0" * 64
        self.save_catalog()
        self.assertNotEqual(self.run_script("--verify-only").returncode, 0)

    def test_missing_receipt_can_be_adopted_only_after_matching_official_archive(self):
        manual = self.plugins / "Manual MyBatis"
        manual.mkdir(parents=True)
        with zipfile.ZipFile(self.sources / "mybatisx.zip") as archive:
            for name in archive.namelist():
                target = manual / name.split("/", 1)[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        inode = (manual / "lib/plugin.jar").stat().st_ino
        self.assertNotEqual(self.run_script("--verify-only").returncode, 0)
        self.assert_ok(self.run_script())
        self.assertEqual((manual / "lib/plugin.jar").stat().st_ino, inode)
        self.assertFalse((self.plugins / "MybatisX").exists())
        self.assert_ok(self.run_script("--verify-only"))

    def test_archive_version_must_match_catalog_even_when_hash_matches(self):
        rid, directory, xml_id, version = PLUGINS[0]
        self.write_zip(rid, directory, xml_id, "wrong-version")
        next(row for row in self.rows if row[0] == rid)[2] = version
        self.save_catalog()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse((self.plugins / directory).exists())

    def test_idea_opened_during_download_prevents_plugin_publication(self):
        running = self.base / "idea-opened"
        ps = self.fakebin / "ps"
        ps.write_text('#!/bin/sh\n[ ! -f "$IDEA_RUNNING_MARKER" ] || printf "%s\\n" "$HOME/Applications/IntelliJ IDEA CE.app/Contents/MacOS/idea"\nexit 0\n')
        downloader = self.support / "scripts/download-tools.sh"
        downloader.write_text(downloader.read_text() + '\ntouch "$IDEA_RUNNING_MARKER"\n')
        result = self.run_script(extra={"IDEA_RUNNING_MARKER": str(running)})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.plugins / PLUGINS[0][1]).exists())

    def test_running_idea_and_symlinked_plugin_directory_are_rejected(self):
        self.assertNotEqual(self.run_script(extra={"FIXTURE_IDEA_RUNNING": "1"}).returncode, 0)
        self.assertFalse(self.download_marker.exists())
        external = self.base / "external"
        external.mkdir()
        self.plugins.parent.mkdir(parents=True)
        self.plugins.symlink_to(external, target_is_directory=True)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_required_external_dependency_and_wrong_archive_version_are_rejected(self):
        rid, directory, xml_id, version = PLUGINS[0]
        self.write_zip(rid, directory, xml_id, version, dependency="unknown.required.plugin")
        self.save_catalog()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse((self.plugins / directory).exists())

    def test_failed_publication_keeps_old_backup_and_never_reports_all_success(self):
        self.install_old()
        fake_mv = self.fakebin / "mv"
        fake_mv.write_text('#!/bin/bash\ncase "$*" in *"/staged/MybatisX"*) exit 29;; esac\nexec /bin/mv "$@"\n')
        fake_mv.chmod(0o755)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(list((self.audit / "plugin-backups").rglob("old.jar")))
        self.assertNotIn("全部插件验证通过", result.stdout)

    def test_failed_audit_write_is_not_reported_as_overall_success(self):
        (self.audit / "plugins-result.tsv").mkdir()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("全部插件验证通过", result.stdout)

    def test_symlinked_backup_root_with_trailing_slash_is_rejected_before_publish(self):
        old = self.install_old()
        before = self.snapshot(self.plugins)
        outside = self.base / "outside backups"
        outside.mkdir()
        alias = self.base / "backup alias"
        alias.symlink_to(outside, target_is_directory=True)
        result = self.run_script(extra={"IDEA_PLUGIN_BACKUP_DIR": str(alias) + "/"})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertEqual(self.snapshot(self.plugins), before)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
