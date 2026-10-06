"""IDEA SDK 同步：真实 XML fixture，不访问成员电脑的 IDEA 配置。"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class IdeaSdkSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="IDEA SDK 中文's & ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.project = self.base / "业务 项目's &"
        (self.project / ".idea").mkdir(parents=True)
        self.config = self.home / "Library/Application Support/JetBrains/IdeaIC2024.3"
        (self.config / "options").mkdir(parents=True)
        self.table = self.config / "options/jdk.table.xml"
        self.misc = self.project / ".idea/misc.xml"
        self.gradle = self.project / ".idea/gradle.xml"
        self.marker = self.base / "java-executed"
        self.jdk = self.make_jdk("真实 JDK's & 8")
        self.fakebin = self.base / "bin"
        self.fakebin.mkdir()
        ps = self.fakebin / "ps"
        ps.write_text('#!/bin/sh\n[ -z "${FIXTURE_IDEA_RUNNING:-}" ] || printf "%s\\n" "/Applications/IntelliJ IDEA.app/Contents/MacOS/idea"\nexit 0\n')
        ps.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": f"{self.fakebin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "LC_ALL": "C", "JAVA_HOME": str(self.jdk), "JDK_AUTO_DETECT": "false",
                    "JDK_INSTALL_DIR": str(self.jdk), "ENV_FILE": str(self.home / "missing-env.sh"),
                    "IDEA_CONFIG_DIR": str(self.config), "CDPATH": str(self.base)}
        self.write_project()

    def make_jdk(self, name):
        root = self.base / name
        (root / "bin").mkdir(parents=True)
        for executable, banner in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            path = root / "bin" / executable
            path.write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.marker)) + "\nprintf '%s\\n' " + shlex.quote(banner) + " >&2\n")
            path.chmod(0o755)
        for relative in ("jre/lib/rt.jar", "jre/lib/ext/sunec.jar", "lib/tools.jar", "src.zip"):
            archive = root / relative
            archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("fixture.txt", "fixture")
        return root

    def xml(self, path, root):
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    def write_project(self, sdk="old JDK's & name", jvm="alias 8", distribution="LOCAL"):
        root = ET.Element("project", version="4")
        ET.SubElement(root, "component", {"name": "ProjectRootManager", "version": "2", "languageLevel": "JDK_1_8",
                                         "project-jdk-name": sdk, "project-jdk-type": "JavaSDK"})
        ET.SubElement(root, "component", {"name": "KeepSetting", "value": "untouched"})
        self.xml(self.misc, root)
        root = ET.Element("project", version="4")
        component = ET.SubElement(root, "component", name="GradleSettings")
        linked = ET.SubElement(component, "option", name="linkedExternalProjectsSettings")
        for path, value in (("$PROJECT_DIR$", jvm), (str(self.base / "other project"), "other-sdk")):
            settings = ET.SubElement(linked, "GradleProjectSettings")
            for name, item in (("externalProjectPath", path), ("distributionType", distribution),
                               ("gradleHome", "$USER_HOME$/本地 Gradle's &"), ("gradleJvm", value), ("delegatedBuild", "true")):
                ET.SubElement(settings, "option", name=name, value=item)
        self.xml(self.gradle, root)

    def sdk_entry(self, component, name, home, version="1.8.0_432"):
        entry = ET.SubElement(component, "jdk", version="2")
        for tag, value in (("name", name), ("type", "JavaSDK"), ("version", 'java version "' + version + '"'), ("homePath", str(home))):
            ET.SubElement(entry, tag, value=value)
        roots = ET.SubElement(entry, "roots")
        for kind, relative in (("classPath", "jre/lib/rt.jar"), ("sourcePath", "src.zip"), ("javadocPath", "docs"), ("annotationsPath", "annotations")):
            group = ET.SubElement(roots, kind)
            composite = ET.SubElement(group, "root", type="composite")
            ET.SubElement(composite, "root", type="simple", url=f"jar://{home}/{relative}!/")
        ET.SubElement(entry, "additional", {"custom-keep": name})
        return entry

    def write_table(self, entries):
        root = ET.Element("application")
        ET.SubElement(root, "component", name="KeepComponent", value="untouched")
        component = ET.SubElement(root, "component", name="ProjectJdkTable")
        for name, home in entries:
            self.sdk_entry(component, name, home)
        self.xml(self.table, root)

    def module(self, relative="modules/子 模块's &.iml", name="alias 8", referenced=True):
        path = self.project / relative
        root = ET.Element("module", type="JAVA_MODULE", version="4")
        component = ET.SubElement(root, "component", name="NewModuleRootManager")
        ET.SubElement(component, "orderEntry", type="jdk", jdkName=name, jdkType="JavaSDK")
        ET.SubElement(component, "orderEntry", type="library", name="keep")
        self.xml(path, root)
        if referenced:
            root = ET.Element("project", version="4")
            component = ET.SubElement(root, "component", name="ProjectModuleManager")
            modules = ET.SubElement(component, "modules")
            ET.SubElement(modules, "module", fileurl="file://$PROJECT_DIR$/" + relative, filepath="$PROJECT_DIR$/" + relative)
            self.xml(self.project / ".idea/modules.xml", root)
        return path

    def run_script(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/config-idea-sdk.sh"),
                               "--project", str(self.project), *args], cwd=self.base,
                              env={**self.env, **(extra or {})}, capture_output=True, text=True, timeout=20)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for directory in (self.project, self.config)
                for p in directory.rglob("*") if p.is_file() and not p.is_symlink()}

    def test_dedupe_preserves_complete_roots_and_updates_project_and_modules(self):
        alias_path = self.base / "JDK alias"
        alias_path.symlink_to(self.jdk, target_is_directory=True)
        self.write_table([("old JDK's & name", self.jdk), ("alias 8", alias_path), ("other-sdk", self.base / "other JDK")])
        module = self.module()
        original_roots = ET.tostring(ET.parse(self.table).find("./component[@name='ProjectJdkTable']/jdk/roots"))
        self.assert_ok(self.run_script())
        entries = ET.parse(self.table).findall("./component[@name='ProjectJdkTable']/jdk")
        self.assertEqual([entry.find("name").get("value") for entry in entries], ["azul-1.8", "other-sdk"])
        self.assertEqual(ET.tostring(entries[0].find("roots")), original_roots)
        self.assertEqual(entries[0].find("additional").get("custom-keep"), "old JDK's & name")
        manager = ET.parse(self.misc).find("./component[@name='ProjectRootManager']")
        self.assertEqual(manager.get("project-jdk-name"), "azul-1.8")
        settings = ET.parse(self.gradle).findall("./component/option/GradleProjectSettings")
        self.assertEqual(settings[0].find("option[@name='gradleJvm']").get("value"), "azul-1.8")
        self.assertEqual(settings[0].find("option[@name='distributionType']").get("value"), "LOCAL")
        self.assertEqual(settings[0].find("option[@name='gradleHome']").get("value"), "$USER_HOME$/本地 Gradle's &")
        self.assertEqual(settings[1].find("option[@name='gradleJvm']").get("value"), "other-sdk")
        self.assertEqual(ET.parse(module).find("./component/orderEntry[@type='jdk']").get("jdkName"), "azul-1.8")
        for path in (self.table, self.misc, self.gradle, module):
            self.assertTrue(Path(str(path) + ".bak").exists())

    def test_new_sdk_contains_real_jdk8_class_and_source_roots(self):
        self.assert_ok(self.run_script())
        entry = ET.parse(self.table).find("./component[@name='ProjectJdkTable']/jdk")
        self.assertEqual(entry.find("name").get("value"), "azul-1.8")
        self.assertEqual(entry.find("homePath").get("value"), str(self.jdk))
        urls = [root.get("url") for root in entry.findall("./roots/classPath/root/root")]
        self.assertIn(f"jar://{self.jdk}/jre/lib/rt.jar!/", urls)
        self.assertIn(f"jar://{self.jdk}/lib/tools.jar!/", urls)
        self.assertIn(f"jar://{self.jdk}/jre/lib/ext/sunec.jar!/", urls)
        self.assertEqual(entry.find("./roots/sourcePath/root/root").get("url"), f"jar://{self.jdk}/src.zip!/")
        self.assertFalse(Path(str(self.table) + ".bak").exists())

    def test_existing_empty_table_gets_sdk_component_and_preserves_other_settings(self):
        root = ET.Element("application")
        ET.SubElement(root, "component", name="KeepComponent", value="untouched")
        self.xml(self.table, root)
        self.assert_ok(self.run_script())
        root = ET.parse(self.table).getroot()
        self.assertEqual(root.find("./component[@name='KeepComponent']").get("value"), "untouched")
        self.assertEqual(root.find("./component[@name='ProjectJdkTable']/jdk/name").get("value"), "azul-1.8")

    def test_missing_jdk_archives_fail_without_creating_backups(self):
        (self.jdk / "jre/lib/rt.jar").unlink()
        original = self.snapshot()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("roots", result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), original)

    def test_orphaned_old_project_sdk_module_reference_is_migrated(self):
        module = self.module(name="old JDK's & name")
        self.assert_ok(self.run_script())
        self.assertEqual(ET.parse(module).find("./component/orderEntry[@type='jdk']").get("jdkName"), "azul-1.8")

    def test_registered_other_home_project_sdk_does_not_migrate_module_sdk(self):
        other = self.make_jdk("保留独立 JDK")
        self.write_table([("other-sdk", other), ("alias 8", self.jdk)])
        self.write_project(sdk="other-sdk")
        module = self.module(name="other-sdk")
        self.assert_ok(self.run_script())
        self.assertEqual(ET.parse(self.misc).find("./component[@name='ProjectRootManager']").get("project-jdk-name"), "azul-1.8")
        self.assertEqual(ET.parse(module).find("./component/orderEntry[@type='jdk']").get("jdkName"), "other-sdk")

    def test_late_preflight_failure_preserves_every_file_and_existing_backup(self):
        self.write_table([("alias 8", self.jdk)])
        module = self.module()
        Path(str(self.table) + ".bak").write_bytes(b"original historical backup")
        Path(str(module) + ".bak").mkdir()
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_symlinked_config_or_project_ancestor_is_rejected(self):
        self.write_table([("alias 8", self.jdk)])
        original = self.snapshot()
        alias = self.base / "config alias"
        alias.symlink_to(self.config, target_is_directory=True)
        self.assertNotEqual(self.run_script(extra={"IDEA_CONFIG_DIR": str(alias)}).returncode, 0)
        self.assertEqual(self.snapshot(), original)
        alias = self.base / "project alias"
        alias.symlink_to(self.project, target_is_directory=True)
        result = subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/config-idea-sdk.sh"),
                                 "--project", str(alias)], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_second_run_preserves_bytes_mtime_and_original_backups(self):
        self.write_table([("alias 8", self.jdk)])
        self.module()
        self.assert_ok(self.run_script())
        snapshot = self.snapshot()
        self.assert_ok(self.run_script())
        self.assertEqual(self.snapshot(), snapshot)

    def test_canonical_name_supports_quotes_ampersand_and_chinese(self):
        name = "团队's \"SDK\" & JDK8"
        self.write_table([("alias 8", self.jdk)])
        self.assert_ok(self.run_script(extra={"IDEA_JDK_NAME": name}))
        self.assertEqual(ET.parse(self.table).find("./component[@name='ProjectJdkTable']/jdk/name").get("value"), name)
        self.assertEqual(ET.parse(self.misc).find("./component[@name='ProjectRootManager']").get("project-jdk-name"), name)

    def test_canonical_name_conflict_changes_no_file(self):
        other = self.make_jdk("another JDK")
        self.write_table([("alias 8", self.jdk), ("azul-1.8", other)])
        original = self.snapshot()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("冲突", result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), original)

    def test_malformed_or_duplicate_project_xml_is_rejected_without_writes(self):
        self.write_table([("alias 8", self.jdk)])
        for value in ("<project>", '<project><component name="ProjectRootManager"/><component name="ProjectRootManager"/></project>'):
            with self.subTest(value=value):
                self.misc.write_text(value)
                original = self.snapshot()
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertEqual(self.snapshot(), original)

    def test_unsafe_table_and_malformed_module_fail_entire_preflight(self):
        module = self.module()
        self.write_table([("alias 8", self.jdk)])
        module.write_text("<module>")
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)
        module.unlink()
        (self.project / ".idea/modules.xml").unlink()
        self.table.write_text('<!DOCTYPE application [<!ENTITY x SYSTEM "file:///etc/passwd">]><application>&x;</application>')
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_duplicate_gradle_association_fails_before_sdk_registration(self):
        root = ET.parse(self.gradle).getroot()
        linked = root.find("./component/option")
        linked.append(ET.fromstring(ET.tostring(linked[0])))
        self.xml(self.gradle, root)
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_dry_run_does_not_write_or_execute_jdk(self):
        self.write_table([("alias 8", self.jdk)])
        self.module()
        original = self.snapshot()
        result = self.run_script("--dry-run")
        self.assert_ok(result)
        self.assertIn("预演", result.stdout)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.marker.exists())

    def test_unimported_project_stays_pending_without_files(self):
        self.misc.unlink()
        self.gradle.unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("尚未", result.stdout)
        self.assertFalse(self.table.exists())
        self.assertFalse(self.marker.exists())

    def test_running_idea_or_symlinked_configuration_is_rejected(self):
        self.write_table([("alias 8", self.jdk)])
        original = self.snapshot()
        self.assertNotEqual(self.run_script(extra={"FIXTURE_IDEA_RUNNING": "1"}).returncode, 0)
        self.assertEqual(self.snapshot(), original)
        destination = self.base / "original misc.xml"
        shutil.move(self.misc, destination)
        self.misc.symlink_to(destination)
        original_bytes = destination.read_bytes()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(destination.read_bytes(), original_bytes)
        self.assertFalse(Path(str(self.table) + ".bak").exists())

    def test_publish_failure_restores_current_originals_instead_of_old_backups(self):
        self.write_table([("alias 8", self.jdk)])
        self.module()
        Path(str(self.table) + ".bak").write_bytes(b"historical table backup")
        Path(str(self.misc) + ".bak").write_bytes(b"historical misc backup")
        fail = self.fakebin / "mv"
        fail.write_text('#!/bin/bash\nfor last in "$@"; do :; done\ncase "$last" in */.idea/misc.xml) exit 41 ;; esac\nexec /bin/mv "$@"\n')
        fail.chmod(0o755)
        original = self.snapshot()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_publish_failure_removes_newly_registered_sdk_table(self):
        fail = self.fakebin / "mv"
        fail.write_text('#!/bin/bash\nfor last in "$@"; do :; done\ncase "$last" in */.idea/misc.xml) exit 41 ;; esac\nexec /bin/mv "$@"\n')
        fail.chmod(0o755)
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.table.exists())

    def test_publish_signal_restores_current_configuration_and_keeps_failure_status(self):
        self.write_table([("alias 8", self.jdk)])
        self.module()
        fail = self.fakebin / "mv"
        for signal, expected in (("TERM", 143), ("INT", 130)):
            with self.subTest(signal=signal):
                fail.write_text('#!/bin/bash\nfor last in "$@"; do :; done\ncase "$last" in */.idea/misc.xml) kill -' + signal + ' "$PPID"; exit 41 ;; esac\nexec /bin/mv "$@"\n')
                fail.chmod(0o755)
                original = self.snapshot()
                result = self.run_script()
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertEqual(self.snapshot(), original)

    def test_dry_run_uses_no_unverified_home_conflict_assertion(self):
        self.write_table([("azul-1.8", self.jdk)])
        other = self.make_jdk("当前 JAVA_HOME JDK21")
        (other / "bin/java").write_text('#!/bin/sh\nprintf \'openjdk version "21.0.1"\\n\' >&2\n')
        env_file = self.home / "可信 env.sh"
        env_file.write_text("export JAVA_HOME=" + shlex.quote(str(self.jdk)) + "\n")
        extra = {"JAVA_HOME": str(other), "ENV_FILE": str(env_file)}
        original = self.snapshot()
        result = self.run_script("--dry-run", extra=extra)
        self.assert_ok(result)
        self.assertIn("待", result.stdout)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.marker.exists())
        self.assert_ok(self.run_script(extra=extra))

    def test_dry_run_defers_same_physical_home_duplicate_name_to_formal_merge(self):
        alias = self.base / "JDK physical alias"
        alias.symlink_to(self.jdk, target_is_directory=True)
        self.write_table([("azul-1.8", self.jdk), ("azul-1.8", alias)])
        original = self.snapshot()
        self.assert_ok(self.run_script("--dry-run"))
        self.assertEqual(self.snapshot(), original)
        self.assertFalse(self.marker.exists())
        self.assert_ok(self.run_script())
        entries = ET.parse(self.table).findall("./component[@name='ProjectJdkTable']/jdk")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].find("name").get("value"), "azul-1.8")

    def test_dry_run_rejects_duplicate_name_with_different_home_or_sdk_type(self):
        other = self.make_jdk("different physical JDK")
        for kind in ("different-home", "different-type"):
            with self.subTest(kind=kind):
                self.write_table([("azul-1.8", self.jdk), ("azul-1.8", other if kind == "different-home" else self.jdk)])
                if kind == "different-type":
                    root = ET.parse(self.table).getroot()
                    root.findall("./component[@name='ProjectJdkTable']/jdk")[1].find("type").set("value", "PythonSDK")
                    self.xml(self.table, root)
                original = self.snapshot()
                self.assertNotEqual(self.run_script("--dry-run").returncode, 0)
                self.assertEqual(self.snapshot(), original)
                self.assertFalse(self.marker.exists())

    def test_module_scan_failure_prevents_alias_removal_and_all_writes(self):
        self.write_table([("alias 8", self.jdk)])
        self.module(referenced=False)
        fail = self.fakebin / "find"
        fail.write_text('#!/bin/sh\nexit 41\n')
        fail.chmod(0o755)
        original = self.snapshot()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), original)

    def test_external_module_alias_fails_before_any_write(self):
        self.write_table([("alias 8", self.jdk)])
        self.module("../external.iml")
        original = self.snapshot()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
