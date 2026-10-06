"""成员菜单集成：真实入口/扫描/JDK修复；完整修复用进程替身记录调用边界。"""
from pathlib import Path
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
        self.set_picker(cancel=True)
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

    def set_picker(self, *, cancel=False, error=False, cancel_after_first=False):
        picker = self.bin / "osascript"
        if error:
            body = "echo 'AppleEvent timed out. (-1712)' >&2\nexit 1\n"
        elif cancel:
            body = "echo 'User canceled. (-128)' >&2\nexit 1\n"
        else:
            body = 'printf "%s\\n" "$PICKED_PROJECT"\n'
        condition = ('if [ -f "$PICKER_RECORD" ]; then echo "User canceled. (-128)" >&2; exit 1; fi\n'
                     if cancel_after_first else "")
        picker.write_text('#!/bin/sh\n' + condition + 'printf "called\\n" >> "$PICKER_RECORD"\n' + body)
        picker.chmod(0o755)

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
        path = self.support / "menu.sh" if menu else self.kit / "开始配置.command"
        return subprocess.run(["/bin/bash", str(path), *args], cwd=self.base, input=input_text,
                              env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=20)

    def test_no_terminal_shows_usage_without_installing(self):
        result = self.run_entry()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())

    def test_menu_checks_jdk_and_gradle_before_first_choice_without_installing(self):
        result = self.run_entry(menu=True, input_text="0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index("环境预检"), result.stdout.index("输入编号"))
        self.assertIn(str(self.jdk), result.stdout)
        self.assertIn("Gradle", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [self.jdk])

    def test_entry_dry_run_uses_packaged_server_without_writing(self):
        (self.support / "config/team.sh").write_text('SERVER_ADDR="${SERVER_ADDR:-team.example:9090}"\n')
        result = self.run_entry("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://team.example:9090/", result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertFalse((self.home / "Library/Logs/team-java-env/history").exists())

    def test_jdk_menu_repairs_complete_environment_and_records_history(self):
        result = self.run_entry(menu=True, input_text="2\n3\n0\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / ".zshrc").exists())
        self.assertTrue((self.home / ".config/java-dev/jdk.sh").exists())
        self.assertIn("JAVA_8_HOME", result.stdout)
        self.assertIn("JRE_HOME", result.stdout)
        logs = list((self.home / "Library/Logs/team-java-env").glob("*.log"))
        self.assertTrue(logs)
        records = list((self.home / "Library/Logs/team-java-env/history").iterdir())
        self.assertEqual(len(records), 1)
        self.assertIn("COMPONENT_VERIFIED", (records[0] / "result.tsv").read_text())
        self.assertTrue((records[0] / "report.md").exists())

    def test_all_repair_without_project_does_not_open_picker(self):
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="1\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.repair_arguments(), ["--scope", "all"])
        self.assertFalse(self.picker_record.exists())
        self.assertIn("未选择项目", result.stdout)

    def test_cancel_check_picker_returns_to_menu_without_installing(self):
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="3\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("未更换项目", result.stdout)
        self.assertFalse(self.repair_record.exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_folder_picker_error_preserves_diagnostic(self):
        self.set_picker(error=True)
        result = self.run_entry(menu=True, input_text="3\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-1712", result.stdout)
        self.assertNotIn("已取消选择", result.stdout)
        logs = list((self.home / "Library/Logs/team-java-env").glob("*.log"))
        self.assertTrue(any("-1712" in log.read_text() for log in logs))

    def test_menu_three_selects_project_and_menu_one_forwards_it_to_repair(self):
        project = self.project()
        self.set_picker()
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="3\n1\n0\n", extra={"PICKED_PROJECT": str(project)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.repair_arguments(), ["--scope", "all", "--project", str(project)])
        self.assertEqual(self.picker_record.read_text().splitlines(), ["called"])
        self.assertFalse((project / "gradlew").exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_gradle_menu_forwards_selected_build_project_to_repair(self):
        project = self.project("独立 Gradle 项目's")
        self.set_picker()
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="7\n0\n", extra={"PICKED_PROJECT": str(project)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.repair_arguments(), ["--scope", "gradle", "--project", str(project)])
        self.assertFalse((project / "gradlew").exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_gradle_menu_initial_cancel_still_repairs_sdk_without_project(self):
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="7\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("未选择新项目", result.stdout)
        self.assertEqual(self.repair_arguments(), ["--scope", "gradle"])

    def test_gradle_picker_cancel_preserves_previously_selected_project(self):
        project = self.project()
        self.set_picker(cancel_after_first=True)
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="3\n7\n0\n", extra={"PICKED_PROJECT": str(project)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.repair_arguments(), ["--scope", "gradle", "--project", str(project)])
        self.assertIn("未选择新项目", result.stdout)

    def test_check_menu_does_not_modify_project_or_run_wrapper(self):
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
        self.set_picker()
        result = self.run_entry(menu=True, input_text="3\n0\n", extra={
            "PICKED_PROJECT": str(project), "WRAPPER_AUDIT": str(marker)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[待构建验证]", result.stdout)
        self.assertEqual(props.read_text(), original)
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o644)
        self.assertFalse(Path(str(props) + ".bak").exists())
        self.assertFalse(marker.exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_failed_check_returns_to_menu_and_eof_exits(self):
        result = self.run_entry(menu=True, input_text="3\n", extra={"JDK_INSTALL_DIR": str(self.home / "missing")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("日志", result.stdout)
        self.assertFalse((self.home / ".zshrc").exists())

    def test_failed_repair_stays_in_menu_and_preserves_exit_code(self):
        self.stub_repair()
        result = self.run_entry(menu=True, input_text="1\n0\n", extra={"REPAIR_EXIT": "43"})
        self.assertEqual(result.returncode, 43, result.stdout + result.stderr)
        self.assertIn("本次操作未完成", result.stdout)
        self.assertGreaterEqual(result.stdout.count("输入编号"), 2)

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
