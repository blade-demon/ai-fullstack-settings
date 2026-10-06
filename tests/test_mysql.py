"""Run the real Bash entry point; replace only the external Docker command."""

import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1] / "dev-kit/.support"


class MySQLScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mysql script ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        self.root.mkdir()
        for relative in ("scripts/services/mysql.sh", "config/mysql.compose.yaml", "config/env.sh"):
            source = REPO_ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.copy2(source, destination)
        self.script = self.root / "scripts/services/mysql.sh"
        self.cwd = Path(self.temp.name) / "unrelated working directory"
        self.cwd.mkdir()
        self.bin_dir = Path(self.temp.name) / "bin"
        self.bin_dir.mkdir()
        self.call_log = Path(self.temp.name) / "docker-calls.jsonl"
        docker = self.bin_dir / "docker"
        docker.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "keys = ('MYSQL_IMAGE', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_PLATFORM')\n"
            "record = {'args': args, 'cwd': os.getcwd(), "
            "'env': {k: os.environ.get(k) for k in keys}, "
            "'has_password': bool(os.environ.get('MYSQL_ROOT_PASSWORD'))}\n"
            "with open(os.environ['DOCKER_CALL_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(record) + '\\n')\n"
            "if args == ['compose', 'version']:\n"
            "    sys.exit(int(os.environ.get('DOCKER_VERSION_EXIT', '0')))\n"
            "sys.exit(int(os.environ.get('DOCKER_ACTION_EXIT', '0')))\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("MYSQL_", "COMPOSE_", "DOCKER_"))
        }
        self.env.update(
            PATH=str(self.bin_dir) + os.pathsep + "/usr/bin:/bin",
            DOCKER_CALL_LOG=str(self.call_log),
        )

    def run_script(self, *args, env=None):
        run_env = dict(self.env)
        run_env.update(env or {})
        return subprocess.run(
            ["/bin/bash", str(self.script), *args],
            cwd=self.cwd,
            env=run_env,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self):
        if not self.call_log.exists():
            return []
        return [json.loads(line) for line in self.call_log.read_text().splitlines()]

    def expected_prefix(self, project="ai-fullstack-mysql"):
        return [
            "compose", "--project-name", project,
            "--project-directory", str(self.root),
            "--env-file", "/dev/null",
            "--file", str(self.root / "config/mysql.compose.yaml"),
        ]

    def test_up_uses_stable_project_and_absolute_paths_from_other_directory(self):
        result = self.run_script("up", env={"MYSQL_ROOT_PASSWORD": "secret $ value"})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls[0]["args"], ["compose", "version"])
        self.assertEqual(calls[1]["args"], self.expected_prefix() + ["up", "--detach", "mysql"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["env"]["MYSQL_IMAGE"], "mysql:8.0")
        self.assertEqual(calls[1]["env"]["MYSQL_PORT"], "3306")
        self.assertEqual(calls[1]["env"]["MYSQL_DATABASE"], "app_dev")
        self.assertEqual(calls[1]["env"]["MYSQL_PLATFORM"], "")
        self.assertTrue(calls[1]["has_password"])
        self.assertNotIn("secret $ value", result.stdout + result.stderr)
        self.assertNotIn("secret $ value", str(calls[1]["args"]))

    def test_real_up_rejects_missing_or_empty_password_before_docker(self):
        for env in ({}, {"MYSQL_ROOT_PASSWORD": ""}):
            with self.subTest(env=env):
                result = self.run_script("up", env=env)
                self.assertEqual(result.returncode, 2)
                self.assertIn("MYSQL_ROOT_PASSWORD", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_dry_run_up_needs_no_password_and_has_no_side_effects(self):
        before = sorted(str(path) for path in Path(self.temp.name).rglob("*"))
        result = self.run_script("--dry-run", "up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MYSQL_ROOT_PASSWORD", result.stdout)
        displayed = result.stdout.split("将执行：", 1)[1].strip()
        self.assertEqual(shlex.split(displayed)[-3:], ["up", "--detach", "mysql"])
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, sorted(str(path) for path in Path(self.temp.name).rglob("*")))

    def test_dry_run_never_prints_password_or_checks_docker(self):
        result = self.run_script("up", "--dry-run", env={
            "MYSQL_ROOT_PASSWORD": "never-print-this-$ecret",
            "DOCKER_VERSION_EXIT": "99",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("never-print-this-$ecret", result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_dry_run_chinese_and_quote_paths_are_readable_and_round_trip(self):
        relocated = self.root.with_name("中文项目 with 'quotes' and $literal")
        self.root.rename(relocated)
        self.root = relocated
        self.script = self.root / "scripts/services/mysql.sh"
        try:
            result = self.run_script("up", "--dry-run", env={"LC_ALL": "C.UTF-8"})
        except UnicodeDecodeError as error:
            self.fail("预演输出不是有效的 UTF-8：" + str(error))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("中文项目", result.stdout)
        displayed = result.stdout.split("将执行：", 1)[1].strip()
        self.assertEqual(
            shlex.split(displayed),
            ["docker"] + self.expected_prefix() + ["up", "--detach", "mysql"],
        )
        self.assertEqual(self.calls(), [])

    def test_help_and_default_invocation_do_not_require_docker(self):
        for args in ((), ("help",), ("--help",), ("-h",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("MYSQL_PLATFORM", result.stdout)
                self.assertEqual(self.calls(), [])

    def test_non_start_commands_work_without_password_and_keep_volumes(self):
        for action, suffix in (
            ("down", ["down"]),
            ("status", ["ps", "--all"]),
            ("logs", ["logs", "--follow", "--tail", "100", "mysql"]),
        ):
            with self.subTest(action=action):
                result = self.run_script(action)
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.calls()[-1]
                self.assertEqual(call["args"], self.expected_prefix() + suffix)
                self.assertFalse(call["has_password"])
                self.assertNotIn("--volumes", call["args"])
                self.assertNotIn("-v", call["args"])

    def test_environment_overrides_are_forwarded_without_shell_evaluation(self):
        result = self.run_script("up", env={
            "MYSQL_ROOT_PASSWORD": "custom-secret",
            "MYSQL_IMAGE": "mysql:5.7",
            "MYSQL_PORT": "13306",
            "MYSQL_DATABASE": "custom_db",
            "MYSQL_PLATFORM": "linux/amd64",
            "MYSQL_PROJECT_NAME": "separate-mysql",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.calls()[-1]
        self.assertEqual(call["args"], self.expected_prefix("separate-mysql") + ["up", "--detach", "mysql"])
        self.assertEqual(call["env"], {
            "MYSQL_IMAGE": "mysql:5.7", "MYSQL_PORT": "13306",
            "MYSQL_DATABASE": "custom_db", "MYSQL_PLATFORM": "linux/amd64",
        })

    def test_invalid_command_and_extra_arguments_do_not_invoke_docker(self):
        for args in (("destroy",), ("up", "down"), ("down", "--volumes")):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.calls(), [])

    def test_invalid_port_or_project_is_rejected_before_docker(self):
        for env in (
            {"MYSQL_PORT": "0"}, {"MYSQL_PORT": "65536"},
            {"MYSQL_PORT": "3306;touch bad"}, {"MYSQL_PORT": "999999999999999999999"},
            {"MYSQL_PROJECT_NAME": "../unsafe"}, {"MYSQL_PROJECT_NAME": "Uppercase"},
        ):
            with self.subTest(env=env):
                result = self.run_script("up", "--dry-run", env=env)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.calls(), [])

    def test_operation_exit_code_is_preserved(self):
        result = self.run_script("status", env={"DOCKER_ACTION_EXIT": "42"})
        self.assertEqual(result.returncode, 42)
        self.assertEqual(len(self.calls()), 2)

    def test_missing_compose_reports_error_and_does_not_attempt_operation(self):
        result = self.run_script("status", env={"DOCKER_VERSION_EXIT": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Docker Compose", result.stderr)
        self.assertEqual([call["args"] for call in self.calls()], [["compose", "version"]])


if __name__ == "__main__":
    unittest.main()
