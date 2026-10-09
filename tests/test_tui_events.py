"""TUI阶段来自显式协议与退出码；普通命令行不输出协议。"""
import unittest
import test_repair as repair_fixtures
import test_frontend_env as frontend_fixtures


class RepairTuiEventsTests(unittest.TestCase):
    setUp = repair_fixtures.RepairTests.setUp
    run_script = repair_fixtures.RepairTests.run_script

    def test_stage_events_follow_actual_success_and_failure(self):
        result = self.run_script('--scope', 'jdk', extra={'TEAM_TUI_EVENTS': '1', 'FAIL_STAGE': 'jdk'})
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertIn('@@TEAM_TUI\tstage\tstep-1\trunning\tJDK', result.stdout)
        self.assertIn('@@TEAM_TUI\tstage\tstep-1\tfailed\tJDK', result.stdout)
        self.assertNotIn('@@TEAM_TUI\tstage\tstep-1\tsucceeded', result.stdout)

    def test_plain_output_keeps_existing_text_without_protocol(self):
        result = self.run_script('--scope', 'jdk')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('@@TEAM_TUI', result.stdout)


class FrontendTuiEventsTests(unittest.TestCase):
    setUp = frontend_fixtures.FrontendEnvironmentTests.setUp
    run_entry = frontend_fixtures.FrontendEnvironmentTests.run_entry

    def test_components_report_separate_statuses(self):
        result = self.run_entry(extra={'TEAM_TUI_EVENTS': '1', 'NODE_TEST_EXIT': '43'})
        self.assertEqual(result.returncode, 43, result.stdout + result.stderr)
        self.assertIn('@@TEAM_TUI\tstage\tfrontend-node\tfailed', result.stdout)
        self.assertIn('@@TEAM_TUI\tstage\tfrontend-iterm2\tsucceeded', result.stdout)
        self.assertIn('@@TEAM_TUI\tstage\tfrontend-zsh\tsucceeded', result.stdout)


if __name__ == '__main__':
    unittest.main()
