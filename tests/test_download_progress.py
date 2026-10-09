import functools
import http.server
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DownloadProgressTests(unittest.TestCase):
    def test_real_download_reports_bytes_without_changing_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            payload = b'content\n' * 4096
            (root / 'resource').write_bytes(payload)
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(['/bin/bash', '-c', 'source "$1"; team_download "$2" "$3"', 'download',
                    str(ROOT / 'dev-kit/.support/scripts/lib/download-progress.sh'), str(root / 'output'),
                    f'http://127.0.0.1:{server.server_port}/resource'],
                    env={**os.environ, 'TEAM_TUI_EVENTS':'1', 'TEAM_TUI_COMPONENT':'nvm'},
                    text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'output').read_bytes(), payload)
                lines = [line.split('\t') for line in result.stdout.splitlines() if line.startswith('@@TEAM_TUI\tprogress\t')]
                self.assertTrue(lines, result.stdout)
                self.assertEqual(lines[-1][2], 'nvm')
                self.assertEqual(lines[-1][-2:], [str(len(payload)), str(len(payload))])
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
