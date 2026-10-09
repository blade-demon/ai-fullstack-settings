"""成员统一入口及维护者命令行；仅隔离目录内执行。"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MemberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="成员使用 test ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.kit = self.base / "工具's 目录"
        shutil.copytree(ROOT / "dev-kit", self.kit)
        self.support = self.kit / ".support"
        self.home = self.base / "home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.picker_record = self.base / "picker-called"
        self.repair_record = self.base / "repair-arguments"
        picker = self.bin / "osascript"
        picker.write_text('#!/bin/sh\nprintf "called\\n" >> "$PICKER_RECORD"\nexit 1\n')
        picker.chmod(0o755)
        self.jdk = self.home / "existing jdk8"
        (self.jdk / "bin").mkdir(parents=True)
        (self.jdk / "jre").mkdir()
        for name, output in (("java", 'openjdk version "1.8.0_432"'), ("javac", "javac 1.8.0_432")):
            file = self.jdk / "bin" / name
            file.write_text("#!/bin/sh\nprintf '%s\\n' '" + output + "'\n")
            file.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "SHELL": "/bin/zsh", "LC_ALL": "C.UTF-8", "JDK_INSTALL_DIR": str(self.jdk),
                    "JDK_AUTO_DETECT": "false", "PICKER_RECORD": str(self.picker_record),
                    "REPAIR_RECORD": str(self.repair_record)}

    def stub_repair(self):
        # 菜单本身仍真实执行，替身只隔离完整SDK/IDE安装与构建的子进程边界。
        # 真正修复、安装、构建与历史由独立 runtime/repair 测试覆盖。
        (self.support / "scripts/repair-env.sh").write_text(
            '#!/bin/bash\nprintf "%s\\0" "$@" > "$REPAIR_RECORD"\n'
            'printf "repair fixture exit=%s\\n" "${REPAIR_EXIT:-0}"\nexit "${REPAIR_EXIT:-0}"\n')

    def repair_arguments(self):
        return self.repair_record.read_bytes().decode().split("\0")[:-1]

    def project(self, name="Java 项目's dir"):
        path = self.base / name
        path.mkdir()
        (path / "build.gradle").write_text("// fixture project; no Wrapper required\n")
        return path

    def run_entry(self, *args, input_text="", menu=False, extra=None):
        path = self.support / "scripts/run-tool.sh"
        args=("install", *args)
        return subprocess.run(["/bin/bash", str(path), *args], cwd=self.base, input=input_text,
                              env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=20)

    def test_no_terminal_shows_usage_without_installing(self):
        result = self.run_entry()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--components", result.stderr)
        self.assertFalse((self.home / ".zshrc").exists())


    def test_entry_dry_run_uses_packaged_server_without_writing(self):
        (self.support / "config/team.sh").write_text('SERVER_ADDR="${SERVER_ADDR:-team.example:9090}"\n')
        result = self.run_entry("--components", "jdk", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://team.example:9090/", result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / "Library/Logs/team-java-env/history").exists())

    def test_jdk_component_configures_existing_sdk_and_records_result(self):
        result=self.run_entry('--components','jdk')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((self.home/'.zshrc').exists())
        self.assertTrue((self.home/'.config/java-dev/jdk.sh').exists())
        records=list(self.home.glob('Library/Logs/team-java-env/components/*/result.tsv'))
        self.assertEqual(len(records),1)
        self.assertIn('SUCCEEDED',records[0].read_text())

    def run_maintenance(self,*args):
        return subprocess.run(['/bin/bash',str(self.support/'install_env.sh'),*args],cwd=self.base,env=self.env,text=True,capture_output=True,timeout=20)

    def test_gradle_version_cli_sets_package_before_derived_defaults(self):
        result = self.run_maintenance("--scope", "gradle", "--gradle-version", "6.8", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gradle-6.8-bin.zip", result.stdout)
        for version in ("", "--dry-run", "9.0"):
            result = self.run_maintenance("--scope", "gradle", "--gradle-version", version, "--dry-run")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.home / ".zshrc").exists())

    def test_command_line_still_forwards_project_to_repair(self):
        project = self.project()
        self.stub_repair()
        result = self.run_maintenance("--project", str(project), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.repair_arguments(), ["--project", str(project), "--dry-run"])

    def test_command_line_check_does_not_modify_project_or_run_wrapper(self):
        project = self.project("只检查项目")
        wrapper = project / "gradle/wrapper"
        wrapper.mkdir(parents=True)
        (wrapper / "gradle-wrapper.jar").write_bytes(b"fixture")
        props = wrapper / "gradle-wrapper.properties"
        original = "distributionUrl=https\\://example.invalid/gradle-4.5.1-bin.zip\n"
        props.write_text(original)
        launcher = project / "gradlew"
        launcher.write_text('#!/bin/sh\ntouch "$WRAPPER_AUDIT"\nexit 99\n')
        launcher.chmod(0o644)
        marker = self.base / "wrapper-was-run"
        result = subprocess.run(["/bin/bash", str(self.support / "scripts/check-env.sh"),
                                 "--project", str(project)],
                                env={**self.env, "WRAPPER_AUDIT": str(marker)},
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[待构建验证]", result.stdout)
        self.assertEqual(props.read_text(), original)
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o644)
        self.assertFalse(Path(str(props) + ".bak").exists())
        self.assertFalse(marker.exists())
        self.assertFalse((self.home / ".zshrc").exists())



    def test_existing_java_home_is_reused_without_download(self):
        # 不可达地址确保没有意外进入 JDK 下载；后一次从保存配置复用。
        for extra in ({"JAVA_HOME": str(self.jdk)}, {}):
            result = subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/config-jdk.sh")],
                                    env={**self.env, "JDK_INSTALL_DIR": str(self.home / "managed"),
                                         "JDK_AUTO_DETECT": "true", "SERVER_ADDR": "127.0.0.1:1", **extra},
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("复用", result.stdout)
            self.assertIn(str(self.jdk), result.stdout)
            self.assertFalse((self.home / "managed").exists())


if __name__ == "__main__":
    unittest.main()
