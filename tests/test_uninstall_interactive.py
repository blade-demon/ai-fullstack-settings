"""清理交互只使用临时应用；进程列表及 macOS 退出请求均由 fixture 提供。"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class Terminal(io.StringIO):
    def __init__(self, tty=True):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


class UninstallInteractiveTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("interactive_cleanup_tool", ROOT / "tools/uninstall_java_gradle.py")
        self.tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.tool
        spec.loader.exec_module(self.tool)
        self.temp = tempfile.TemporaryDirectory(prefix="清理交互 SDK's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "用户 home"
        self.home.mkdir()
        self.system_apps = self.base / "系统 Applications"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        self.app = self.idea(self.home / "Applications/IntelliJ IDEA CE.app")
        self.sdk = self.home / ".local/share/java-dev/jdk8"
        self.write(self.sdk / "bin/java", "must not execute")
        self.write(self.sdk / "bin/javac", "must not execute")
        self.write(self.sdk / ".team-java-env-install.json", json.dumps({"schema": 1, "tool": "team-java-env", "kind": "jdk"}))
        self.config = self.write(self.home / "Library/Application Support/JetBrains/IdeaIC2024.3/options/jdk.table.xml",
                                 '<application><component name="ProjectJdkTable"><jdk><name value="1.8" />'
                                 '<homePath value="{}" /></jdk></component></application>'.format(self.sdk))
        self.settings = self.write(self.config.parent / "editor.xml", "keep editor settings")
        self.plugin = self.write(self.config.parent.parent / "plugins/demo/lib/demo.jar", "keep plugin")
        self.processes = [(111, self.app)]
        self.prompts = []
        self.quit_events = []

    def write(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def idea(self, path, identifier="com.jetbrains.intellij.ce"):
        self.write(path / "Contents/MacOS/idea", "must not execute")
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": identifier, "CFBundleExecutable": "idea", "CFBundleShortVersionString": "2024.3.7"}))
        return path

    def process_reader(self):
        if hasattr(self, "process_lines"):
            return list(self.process_lines)
        return ["{} {} --fixture".format(pid, app / "Contents/MacOS/idea") for pid, app in self.processes]

    def successful_quit(self, app, pid, executable=None):
        self.assertTrue(self.app.exists(), "正常退出前不能删除软件")
        self.assertTrue(self.sdk.exists(), "正常退出完成前不能清理其他 SDK")
        self.quit_events.append((app, pid))
        self.processes[:] = [(running_pid, running_app) for running_pid, running_app in self.processes if running_pid != pid]

    def run_main(self, args=(), answers=(), tty=True, quit_requester=None):
        real_cleaner = self.tool.Cleaner
        answers = iter(answers)
        output = Terminal(tty)
        errors = io.StringIO()

        def cleaner_factory(_home, **kwargs):
            kwargs.update(system_jvms=self.base / "系统 Java", system_apps=self.system_apps,
                          environ=self.env, process_reader=self.process_reader,
                          quit_requester=quit_requester or self.successful_quit, quit_timeout=0)
            return real_cleaner(self.home, **kwargs)

        def read_answer(prompt):
            self.prompts.append(prompt)
            self.assertTrue(self.app.exists(), "最终确认前不能删除 IDEA")
            self.assertTrue(self.sdk.exists(), "最终确认前不能删除 SDK")
            self.assertEqual(self.quit_events, [], "最终确认前不能退出应用")
            try:
                answer = next(answers)
                return answer(prompt) if callable(answer) else answer
            except StopIteration:
                raise EOFError()

        with mock.patch.object(self.tool, "Cleaner", side_effect=cleaner_factory), \
                mock.patch.object(self.tool.sys, "platform", "darwin"), \
                mock.patch.object(self.tool.os, "geteuid", return_value=501), \
                mock.patch.object(self.tool.sys, "stdin", Terminal(tty)), \
                mock.patch.dict(self.tool.os.environ, self.env, clear=True), \
                mock.patch("builtins.input", side_effect=read_answer), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                status = self.tool.main(list(args))
            except SystemExit as error:
                status = error.code
        return status, output.getvalue(), errors.getvalue()

    def assert_preserved(self):
        self.assertTrue(self.app.exists())
        self.assertTrue(self.sdk.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.settings.exists())
        self.assertTrue(self.plugin.exists())
        self.assertFalse((self.home / "Library/Logs/team-java-env/cleanup").exists())

    def test_terminal_default_deletes_idea_config_sdk_registration_and_plugins(self):
        cache = self.write(self.home / "Library/Caches/JetBrains/IdeaIC2024.3/LocalHistory/changes", "keep history")
        project = self.write(self.home / "业务项目/.idea/workspace.xml", "keep project")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.sdk.exists())
        self.assertFalse(self.config.parent.parent.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.settings.exists())
        self.assertFalse(self.plugin.exists())
        self.assertEqual(cache.read_text(), "keep history")
        self.assertEqual(project.read_text(), "keep project")
        self.assertEqual(self.quit_events, [(self.app, 111)])
        self.assertEqual(len(self.prompts), 3)
        self.assertIn("保留", self.prompts[1])
        self.assertIn("[y/N]", self.prompts[1])
        self.assertIn("DELETE", self.prompts[2])
        self.assertIn(str(self.app), output)
        self.assertIn(str(self.config.parent.parent), output)
        self.assertFalse(list(self.home.rglob("*.bak")))
        self.assertFalse(list((self.home / "Library/Logs/team-java-env/cleanup").glob("*/files")))

    def test_declining_to_preserve_settings_deletes_them(self):
        status, output, errors = self.run_main(answers=["y", "n", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.config.parent.parent.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.plugin.exists())

    def test_terminal_yes_confirms_then_quits_selected_app_and_explicitly_keeps_settings(self):
        registration = self.config.read_text()
        status, output, errors = self.run_main(answers=["y", "y", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.sdk.exists())
        self.assertEqual(self.config.read_text(), registration)
        self.assertEqual(self.settings.read_text(), "keep editor settings")
        self.assertEqual(self.plugin.read_text(), "keep plugin")
        self.assertEqual(self.quit_events, [(self.app, 111)])
        self.assertEqual(len(self.prompts), 3)
        self.assertIn(str(self.app), output)

    def test_unrecognized_preserve_answer_reprompts_instead_of_deleting_settings(self):
        status, output, errors = self.run_main(answers=["y", "DELETE", "yes", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.settings.exists())
        self.assertTrue(self.plugin.exists())
        self.assertEqual(len(self.prompts), 4)
        self.assertEqual(self.prompts[1], self.prompts[2])
        self.assertIn("DELETE", self.prompts[3])

    def test_terminal_no_keeps_idea_and_still_cleans_owned_sdk_after_delete(self):
        status, output, errors = self.run_main(answers=["n", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertTrue(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertFalse(self.sdk.exists())
        self.assertEqual(self.quit_events, [])
        self.assertIn("保留 IDEA", output)
        self.assertEqual(len(self.prompts), 2)

    def test_empty_scope_answer_defaults_to_preserving_idea(self):
        status, output, errors = self.run_main(answers=["", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertTrue(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertFalse(self.sdk.exists())
        self.assertEqual(self.quit_events, [])

    def test_no_discovered_app_does_not_infer_config_cleanup_scope(self):
        self.app = self.app.rename(self.home / "Toolbox IDEA.app")
        self.processes = [(111, self.app)]
        status, output, errors = self.run_main(answers=["DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertTrue(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertFalse(self.sdk.exists())
        self.assertEqual(self.quit_events, [])
        self.assertEqual(len(self.prompts), 1)

    def test_declining_delete_never_quits_or_mutates(self):
        status, output, errors = self.run_main(answers=["y", "", "NO"])
        self.assertNotEqual(status, 0)
        self.assertIn("取消", errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_eof_at_any_prompt_preserves_everything_without_quitting(self):
        for answers in ([], ["y"], ["y", ""], ["y", "unknown"]):
            with self.subTest(answers=answers):
                status, output, errors = self.run_main(answers=answers)
                self.assertEqual(status, 130, output + errors)
                self.assertEqual(self.quit_events, [])
                self.assert_preserved()

    def test_keyboard_interrupt_at_any_prompt_preserves_everything_without_quitting(self):
        def interrupt(_prompt):
            raise KeyboardInterrupt()
        for answers in ([interrupt], ["y", interrupt], ["y", "", interrupt], ["y", "unknown", interrupt]):
            with self.subTest(answers=answers):
                status, output, errors = self.run_main(answers=answers)
                self.assertEqual(status, 130, output + errors)
                self.assertEqual(self.quit_events, [])
                self.assert_preserved()

    def test_explicit_dry_run_has_no_prompt_or_quit_even_on_terminal(self):
        status, output, errors = self.run_main(["--dry-run", "--include-idea"])
        self.assertEqual(status, 0, output + errors)
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_non_terminal_without_apply_stays_preview_only(self):
        status, output, errors = self.run_main(tty=False)
        self.assertEqual(status, 0, output + errors)
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_explicit_noninteractive_app_scope_quits_then_deletes(self):
        status, output, errors = self.run_main(["--components", "jdk,gradle,idea", "--apply", "--yes", "--include-idea-apps"], tty=False)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.sdk.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertEqual(self.quit_events, [(self.app, 111)])
        self.assertEqual(self.prompts, [])

    def test_explicit_apply_yes_does_not_infer_idea_scope(self):
        status, output, errors = self.run_main(["--components", "jdk,gradle", "--apply", "--yes"], tty=False)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.sdk.exists())
        self.assertTrue(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertEqual(self.quit_events, [])

    def test_explicit_terminal_app_scope_keeps_settings_without_extra_scope_prompt(self):
        status, output, errors = self.run_main(["--include-idea-apps"], answers=["DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.plugin.exists())
        self.assertEqual(len(self.prompts), 1)

    def test_explicit_jdk_component_terminal_goes_directly_to_delete_without_idea_question(self):
        status, output, errors = self.run_main(["--components", "jdk"], answers=["DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.sdk.exists())
        self.assertTrue(self.app.exists())
        self.assertTrue(self.config.exists())
        self.assertEqual(len(self.prompts), 1)
        self.assertIn('DELETE', self.prompts[0])
        self.assertEqual(self.quit_events, [])

    def test_noninteractive_apply_yes_without_components_is_usage_error(self):
        status, output, errors = self.run_main(["--apply", "--yes"], tty=False)
        self.assertEqual(status, 2, output + errors)
        self.assert_preserved()

    def test_already_closed_app_is_deleted_without_sending_quit(self):
        self.processes = []
        status, output, errors = self.run_main(["--components", "jdk,gradle,idea", "--apply", "--yes", "--include-idea-apps"], tty=False)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertEqual(self.quit_events, [])

    def test_quit_permission_failure_preserves_all_cleanup_targets(self):
        def denied(_app, _pid, _executable=None):
            raise self.tool.CleanupError("Automation permission denied")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=denied)
        self.assertNotEqual(status, 0)
        self.assertIn("Automation", errors)
        self.assert_preserved()

    def test_save_dialog_or_quit_timeout_preserves_all_cleanup_targets(self):
        def pending(app, pid, executable=None):
            self.quit_events.append((app, pid))
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=pending)
        self.assertNotEqual(status, 0)
        self.assertEqual(self.quit_events, [(self.app, 111)])
        self.assertIn("正常退出", errors)
        self.assert_preserved()

    def test_system_scope_guard_runs_before_any_quit_request(self):
        system_app = self.idea(self.system_apps / "IntelliJ IDEA.app", "com.jetbrains.intellij")
        self.processes.append((222, system_app))
        status, output, errors = self.run_main(["--components", "jdk,gradle,idea", "--apply", "--yes", "--include-idea-apps"], tty=False)
        self.assertEqual(status, 1)
        self.assertIn("--include-system", errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()
        self.assertTrue(system_app.exists())

    def test_selected_pid_does_not_close_same_bundle_at_another_path(self):
        other = self.idea(self.home / "Toolbox/IntelliJ IDEA CE.app")
        self.processes.append((222, other))
        status, output, errors = self.run_main(answers=["y", "y", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertTrue(other.exists())
        self.assertEqual(self.quit_events, [(self.app, 111)])

    def test_default_config_cleanup_blocks_unselected_running_idea(self):
        other = self.idea(self.home / "Toolbox/IntelliJ IDEA CE.app")
        self.processes.append((222, other))
        status, output, errors = self.run_main(answers=["y", "", "DELETE"])
        self.assertEqual(status, 1, output + errors)
        self.assertIn("未选定", errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()
        self.assertTrue(other.exists())

    def test_default_config_cleanup_respects_system_scope_guard_before_quitting(self):
        system_app = self.idea(self.system_apps / "IntelliJ IDEA.app", "com.jetbrains.intellij")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"])
        self.assertEqual(status, 1, output + errors)
        self.assertIn("--include-system", errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()
        self.assertTrue(system_app.exists())

    def test_default_config_cleanup_blocks_directory_containing_project_files(self):
        project = self.write(self.config.parent.parent / ".idea/workspace.xml", "keep project")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"])
        self.assertEqual(status, 1, output + errors)
        self.assertIn("业务项目", errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()
        self.assertEqual(project.read_text(), "keep project")

    def test_full_scope_rescans_after_quit_changes_idea_settings(self):
        def saved_on_quit(app, pid, executable=None):
            self.successful_quit(app, pid)
            self.write(self.config.parent.parent / "new-settings.xml", "IDE wrote on normal exit")
        status, output, errors = self.run_main(["--components", "jdk,gradle,idea", "--apply", "--yes", "--include-idea"], tty=False,
                                              quit_requester=saved_on_quit)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.plugin.exists())
        self.assertFalse(self.sdk.exists())

    def test_default_scope_rescans_after_quit_changes_idea_settings(self):
        saved = self.config.parent.parent / "new-settings.xml"
        def saved_on_quit(app, pid, executable=None):
            self.successful_quit(app, pid)
            self.write(saved, "IDE wrote on normal exit")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=saved_on_quit)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.plugin.exists())
        self.assertFalse(saved.exists())

    def test_new_app_appearing_after_quit_does_not_expand_confirmed_deletion(self):
        new_app = self.home / "Applications/New IDEA.app"
        def new_on_quit(app, pid, executable=None):
            self.successful_quit(app, pid)
            self.idea(new_app)
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=new_on_quit)
        self.assertNotEqual(status, 0)
        self.assert_preserved()
        self.assertTrue(new_app.exists())

    def test_new_settings_directory_after_quit_does_not_expand_confirmed_deletion(self):
        new_settings = self.config.parent.parent.parent / "IdeaIC2025.1/options/editor.xml"
        def new_on_quit(app, pid, executable=None):
            self.successful_quit(app, pid)
            self.write(new_settings, "new version settings")
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=new_on_quit)
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.config.exists())
        self.assertTrue(new_settings.exists())
        self.assertEqual(new_settings.read_text(), "new version settings")

    def test_other_jetbrains_app_and_settings_are_preserved_in_default_scope(self):
        other = self.idea(self.home / "Applications/WebStorm.app", "com.jetbrains.WebStorm")
        settings = self.write(self.home / "Library/Application Support/JetBrains/WebStorm2026.1/options/editor.xml", "keep")
        status, output, errors = self.run_main(answers=["yes", "no", "DELETE"])
        self.assertEqual(status, 0, output + errors)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.config.exists())
        self.assertTrue(other.exists())
        self.assertEqual(settings.read_text(), "keep")

    def test_yes_without_explicit_apply_is_still_rejected(self):
        status, output, errors = self.run_main(["--yes"])
        self.assertNotEqual(status, 0)
        self.assertEqual(self.prompts, [])
        self.assert_preserved()

    def test_normal_quit_uses_exact_pid_and_safely_encoded_paths(self):
        requester = getattr(self.tool, "request_idea_quit", None)
        self.assertTrue(callable(requester), "尚未提供按 PID 正常退出 IDEA 的入口")
        app = self.home / r'工具/IDEA "quoted" \ $().app'
        self.idea(app)
        response = subprocess.CompletedProcess([], 0, "requested\n", "")
        with mock.patch.object(self.tool.subprocess, "run", return_value=response) as run:
            requester(app, 123)
        arguments = run.call_args[0][0]
        self.assertEqual(arguments[:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        script = arguments[-1]
        self.assertIn("runningApplicationWithProcessIdentifier(123)", script)
        self.assertIn(json.dumps(str(app.resolve())), script)
        self.assertIn(json.dumps(str((app / "Contents/MacOS/idea").resolve())), script)
        self.assertNotIn("forceTerminate", script)
        self.assertNotIn("tell application", script)

    def test_process_reader_requests_untruncated_paths(self):
        line = "111 /very long/IntelliJ IDEA CE.app/Contents/MacOS/idea --fixture"
        result = subprocess.CompletedProcess([], 0, line + "\n", "")
        with mock.patch.object(self.tool.subprocess, "run", return_value=result) as run:
            self.assertEqual(self.tool.Cleaner.read_processes(), [line])
        self.assertIn("-ww", run.call_args[0][0])

    def test_target_changed_while_confirming_stops_before_quit(self):
        def changed_before_confirmation(_prompt):
            self.write(self.app / "changed-during-preview.txt", "changed")
            return "DELETE"
        status, output, errors = self.run_main(answers=["y", "", changed_before_confirmation])
        self.assertEqual(status, 1)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_app_identifier_changed_while_confirming_stops_before_quit(self):
        def changed_before_confirmation(_prompt):
            (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "com.jetbrains.WebStorm", "CFBundleExecutable": "idea"}))
            return "DELETE"
        status, output, errors = self.run_main(answers=["y", "", changed_before_confirmation])
        self.assertEqual(status, 1)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_selected_embedded_jbr_process_is_not_mistaken_for_a_closed_app(self):
        executable = self.write(self.app / "Contents/jbr/Contents/Home/bin/java", "must not execute")
        self.process_lines = ["111 {} -Didea.paths.selector=IdeaIC2024.3".format(
            executable)]
        def stopped_on_quit(app, pid, actual_executable=None):
            self.assertEqual(actual_executable, executable)
            self.quit_events.append((app, pid))
            self.process_lines = []
        status, output, errors = self.run_main(answers=["y", "", "DELETE"], quit_requester=stopped_on_quit)
        self.assertEqual(status, 0, output + errors)
        self.assertEqual(self.quit_events, [(self.app, 111)])
        self.assertFalse(self.app.exists())

    def test_unidentified_idea_jvm_blocks_app_scope_without_mutations(self):
        self.process_lines = ["111 /external/jdk/bin/java -Didea.paths.selector=IdeaIC2024.3"]
        status, output, errors = self.run_main(answers=["y", "y", "DELETE"])
        self.assertEqual(status, 1, output + errors)
        self.assertEqual(self.quit_events, [])
        self.assert_preserved()

    def test_normal_quit_validates_actual_embedded_jbr_executable_path(self):
        executable = self.write(self.app / "Contents/jbr/Contents/Home/bin/java", "must not execute")
        requester = self.tool.request_idea_quit
        result = subprocess.CompletedProcess([], 0, "requested\n", "")
        with mock.patch.object(self.tool.subprocess, "run", return_value=result) as run:
            requester(self.app, 111, executable)
        self.assertIn(json.dumps(str(executable)), run.call_args[0][0][-1])


if __name__ == "__main__":
    unittest.main()
