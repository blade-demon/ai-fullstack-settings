"""Check that a double-click terminal keeps actionable failures visible."""
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(sys.platform == "darwin", "macOS command entry")
class StartEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        python = self.base / "python3"
        python.write_text("#!/bin/bash\nprintf 'fixture failed\\n'\nexit 23\n")
        python.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.base) + ":/usr/bin:/bin"}
        self.entry = Path(__file__).resolve().parents[1] / "server/start-server.command"

    def test_no_argument_terminal_failure_waits_for_enter_and_preserves_status(self):
        import pty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        process = subprocess.Popen(["/bin/bash", str(self.entry)], env=self.env,
                                   stdin=slave, stdout=slave, stderr=slave)
        def stop():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.addCleanup(stop)
        data = b""
        deadline = time.monotonic() + 3
        while "按回车" not in data.decode("utf-8", errors="replace") and time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                data += os.read(master, 4096)
            elif process.poll() is not None:
                break
        self.assertIn("按回车", data.decode("utf-8", errors="replace"))
        self.assertIsNone(process.poll())
        os.write(master, b"\n")
        self.assertEqual(process.wait(timeout=3), 23)

    def test_explicit_command_failure_returns_without_pause(self):
        result = subprocess.run(["/bin/bash", str(self.entry), "--help"], env=self.env,
                                input="", text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 23)
        self.assertNotIn("按回车", result.stdout)


if __name__ == "__main__":
    unittest.main()
