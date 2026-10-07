"""Exercise recoverable network failures without weakening archive verification."""
import contextlib
import hashlib
import http.client
import http.server
import io
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request


MODULE = Path(__file__).resolve().parents[1] / "server/network_download.py"
BODY = b"complete archive contents\n"


@contextlib.contextmanager
def serve(respond, tls_context=None):
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            respond(self, len(requests))

        do_CONNECT = do_GET

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if tls_context is not None:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield "%s://127.0.0.1:%d/file" % ("https" if tls_context else "http", server.server_port), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def reply(handler, body=BODY, status=200, headers=None):
    handler.send_response(status)
    for key, value in (headers if headers is not None else {"Content-Length": str(len(body))}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


class CurlProcess:
    """The curl process boundary; file transfer/validation stays in production."""
    def __init__(self, argv, *, body=BODY, status=200, headers=None, code=0, **kwargs):
        values = headers if headers is not None else {"Content-Length": str(len(body))}
        dump = Path(argv[argv.index("--dump-header") + 1])
        dump.write_bytes(("HTTP/1.1 200 Connection established\r\n\r\n"
                          "HTTP/1.1 100 Continue\r\n\r\n"
                          "HTTP/1.1 %s Result\r\n" % status
                          + "".join("%s: %s\r\n" % item for item in values.items())
                          + "\r\n").encode("ascii"))
        self.stdout = io.BytesIO(body)
        self.returncode = None
        self.code = code
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.code = -9

    def wait(self, timeout=None):
        self.waited = True
        self.returncode = self.code
        return self.code


class NetworkDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.is_file():
            from server import network_download
            cls.module = network_download

    def setUp(self):
        self.assertTrue(MODULE.is_file(), "缺少能够恢复 TLS EOF 的共享下载模块")
        self.temp = tempfile.TemporaryDirectory(prefix="下载 ' 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "payload.tmp"
        self.logs = []
        self.sleep = mock.patch("time.sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def download(self, url="https://download.invalid/archive", **kwargs):
        values = dict(expected_sha256=hashlib.sha256(BODY).hexdigest(),
                      expected_size=len(BODY), report=self.logs.append)
        values.update(kwargs)
        return self.module.download_file(url, self.target, **values)

    def test_urllib_reopens_after_wrapped_tls_eof_and_downloads_complete_body(self):
        original = urllib.request.OpenerDirector.open
        attempts = []

        def flaky(opener, *args, **kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise urllib.error.URLError(ssl.SSLEOFError(8, "UNEXPECTED_EOF_WHILE_READING"))
            return original(opener, *args, **kwargs)

        with serve(lambda h, n: reply(h)) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open", flaky), \
                mock.patch("shutil.which", side_effect=AssertionError("no curl needed")):
            self.download(url)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(requests, ["/file"])

    def test_half_response_is_discarded_before_retry(self):
        def respond(handler, number):
            reply(handler, BODY[:7] if number == 1 else BODY,
                  headers={"Content-Length": str(len(BODY))})

        with serve(respond) as (url, requests):
            self.download(url)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(requests, ["/file", "/file"])

    def test_short_sdk_response_without_lock_size_also_retries(self):
        def respond(handler, number):
            reply(handler, BODY[:7] if number == 1 else BODY,
                  headers={"Content-Length": str(len(BODY))})

        with serve(respond) as (url, requests):
            self.download(url, expected_size=None, expected_sha256=None)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(len(requests), 2)

    def test_certificate_failures_never_retry_or_invoke_curl(self):
        cert = ssl.SSLCertVerificationError(1, "secret proxy password")
        for error in (cert, urllib.error.URLError(cert),
                      urllib.error.URLError(urllib.error.URLError(cert))):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=error) as opened, \
                    mock.patch("shutil.which", side_effect=AssertionError("unsafe fallback")):
                with self.assertRaisesRegex(self.module.DownloadError, "证书") as raised:
                    self.download()
                self.assertNotIn("secret", str(raised.exception))
                self.assertEqual(opened.call_count, 1)
                self.assertFalse(self.target.exists())

    def test_fixed_size_header_mismatch_and_full_hash_mismatch_fail_without_retry(self):
        for body, headers, expected in (
                (BODY, {"Content-Length": "100"}, "大小"),
                (b"x" * len(BODY), None, "SHA-256"),
                (BODY + b"extra", {}, "大小")):
            with self.subTest(expected=expected), \
                    serve(lambda h, n: reply(h, body, headers=headers)) as (url, requests), \
                    mock.patch("shutil.which", side_effect=AssertionError("no fallback")):
                with self.assertRaisesRegex(self.module.DownloadError, expected):
                    self.download(url)
                self.assertEqual(len(requests), 1)
                self.assertFalse(self.target.exists())

    def test_transient_http_statuses_retry_but_404_is_terminal(self):
        for status in (408, 429, 500, 502, 503, 504, 404):
            with self.subTest(status=status), \
                    serve(lambda h, n: reply(h, status=status if n == 1 else 200)) as (url, requests):
                if status == 404:
                    with self.assertRaisesRegex(self.module.DownloadError, "404"):
                        self.download(url)
                    self.assertFalse(self.target.exists())
                    self.assertEqual(len(requests), 1)
                else:
                    self.download(url)
                    self.assertEqual(self.target.read_bytes(), BODY)
                    self.assertEqual(len(requests), 2)

    def test_http_error_responses_are_closed_before_retry_or_failure(self):
        for status in (404, 503):
            response = io.BytesIO(b"sensitive server error")
            error = urllib.error.HTTPError("https://download.invalid", status, "Error", {}, response)
            with self.subTest(status=status), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=error), \
                    mock.patch("shutil.which", return_value=None):
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assertTrue(response.closed)
            error.close()

    def test_invalid_initial_urls_are_rejected_before_open(self):
        for url in ("file:///etc/passwd", "https://user:secret@host/file", "https://a/\nfile",
                    "https://a/\x7ffile", "http://", "https://a:bad/file"):
            with self.subTest(url=url), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=AssertionError("opened")):
                with self.assertRaises(self.module.DownloadError):
                    self.download(url)

    def test_redirect_is_checked_before_downgraded_request(self):
        def https_open(handler, request):
            headers = http.client.HTTPMessage()
            headers["Location"] = "http://insecure.invalid/file"
            response = io.BytesIO(b"")
            return handler.parent.error("https", request, response, 302, "Found", headers)

        with mock.patch.object(urllib.request.HTTPSHandler, "https_open", https_open), \
                mock.patch.object(urllib.request.HTTPHandler, "http_open", side_effect=AssertionError("downgrade")):
            with self.assertRaisesRegex(self.module.DownloadError, "重定向"):
                self.download()

    def test_redirect_count_is_bounded(self):
        with serve(lambda h, n: reply(h, b"", 302, {"Location": "/file?n=%d" % n})) as (url, requests):
            with self.assertRaisesRegex(self.module.DownloadError, "重定向"):
                self.download(url)
        self.assertEqual(len(requests), 11)

    def test_recoverable_errors_use_curl_only_after_three_urllib_attempts(self):
        for error in (ssl.SSLEOFError(8, "eof"), socket.timeout("timeout"),
                      ConnectionResetError("reset"), ConnectionRefusedError("refused"),
                      http.client.IncompleteRead(b"partial", len(BODY))):
            calls = []

            def process(argv, **kwargs):
                calls.append((argv, kwargs))
                return CurlProcess(argv, **kwargs)

            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=urllib.error.URLError(error)) as opened, \
                    mock.patch("shutil.which", return_value="/usr/bin/curl"), \
                    mock.patch("subprocess.Popen", side_effect=process):
                self.download()
            self.assertEqual(self.target.read_bytes(), BODY)
            self.assertEqual(opened.call_count, 3)
            self.assertEqual(len(calls), 1)
            argv, kwargs = calls[0]
            self.assertEqual(argv[:2], ["/usr/bin/curl", "-q"])
            self.assertNotIn("--location", argv)
            self.assertNotIn("-k", argv)
            self.assertNotIn("--insecure", argv)
            self.assertNotIn("--ssl-no-revoke", argv)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertFalse(kwargs.get("shell", False))

    def test_no_curl_reports_action_and_never_leaks_proxy_credentials(self):
        error = urllib.error.URLError(ssl.SSLEOFError(8, "https://user:password@proxy.invalid"))
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=error), \
                mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(self.module.DownloadError, "代理.*内网镜像") as raised:
                self.download()
        self.assertNotIn("password", str(raised.exception) + " ".join(self.logs))
        self.assertFalse(self.target.exists())

    def test_real_curl_recovers_a_download_after_persistent_urllib_eof(self):
        if not shutil.which("curl"):
            self.skipTest("system curl is unavailable")
        with serve(lambda h, n: reply(h)) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open",
                                  side_effect=urllib.error.URLError(ssl.SSLEOFError(8, "eof"))):
            self.download(url)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(requests, ["/file"])

    def test_real_curl_retries_partial_transfer_and_discards_previous_bytes(self):
        if not shutil.which("curl"):
            self.skipTest("system curl is unavailable")

        def respond(handler, number):
            reply(handler, BODY[:7] if number == 1 else BODY,
                  headers={"Content-Length": str(len(BODY))})

        with serve(respond) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()):
            self.download(url)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(requests, ["/file", "/file"])
        self.assertTrue(any("18" in message for message in self.logs))

    def test_real_curl_treats_url_braces_literally_as_urllib_does(self):
        if not shutil.which("curl"):
            self.skipTest("system curl is unavailable")
        with serve(lambda h, n: reply(h)) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()):
            self.download(url + "?artifact={a,b}")
        self.assertEqual(requests, ["/file?artifact={a,b}"])
        self.assertEqual(self.target.read_bytes(), BODY)

    def test_real_curl_follows_valid_redirect_and_rejects_chunked_oversize(self):
        if not shutil.which("curl"):
            self.skipTest("system curl is unavailable")

        def respond(handler, number):
            if number == 1:
                reply(handler, b"redirect body", 302, {"Location": "/final"})
            else:
                reply(handler, BODY)

        with serve(respond) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()):
            self.download(url)
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(requests, ["/file", "/final"])

        def oversized(handler, number):
            payload = BODY + b"extra"
            reply(handler, ("%x\r\n" % len(payload)).encode("ascii") + payload + b"\r\n0\r\n\r\n",
                  headers={"Transfer-Encoding": "chunked"})

        with serve(oversized) as (url, requests), \
                mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()):
            with self.assertRaisesRegex(self.module.DownloadError, "大小"):
                self.download(url)
        self.assertFalse(self.target.exists())

    def test_urllib_trickle_cannot_exceed_total_deadline(self):
        def respond(handler, number):
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(BODY)))
            handler.end_headers()
            for byte in BODY:
                try:
                    handler.wfile.write(bytes([byte]))
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                threading.Event().wait(.05)

        started = time.monotonic()
        with serve(respond) as (url, requests):
            with self.assertRaisesRegex(self.module.DownloadError, "超时"):
                self.download(url, total_timeout=.15)
        self.assertLess(time.monotonic() - started, 1)
        self.assertFalse(self.target.exists())

    def test_urllib_slow_status_and_headers_are_interrupted_at_total_deadline(self):
        for phase in ("status", "headers", "redirect"):
            stopped = threading.Event()

            def respond(handler, number):
                if phase == "redirect" and number == 1:
                    reply(handler, b"", 302, {"Location": "/slow"})
                    return
                if phase == "status":
                    chunks = [bytes([byte]) for byte in b"HTTP/1.1 200 OK\r\n"]
                else:
                    chunks = [b"HTTP/1.1 200 OK\r\n"] + [b"X-Slow: value\r\n"] * 12
                try:
                    for chunk in chunks:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
                        if stopped.wait(.04):
                            return
                    handler.wfile.write(("Content-Length: %d\r\n\r\n" % len(BODY)).encode("ascii") + BODY)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            with self.subTest(phase=phase), serve(respond) as (url, requests):
                baseline = set(threading.enumerate())
                start = time.monotonic()
                try:
                    with self.assertRaisesRegex(self.module.DownloadError, "超时"):
                        self.download(url, total_timeout=.15)
                    self.assertLess(time.monotonic() - start, .35)
                    self.assertFalse(self.target.exists())
                    self.assertEqual(len(requests), 2 if phase == "redirect" else 1)
                    # HTTP server request threads may still unwind; download
                    # deadline workers must already be cancelled and joined.
                    self.assertEqual([thread.name for thread in threading.enumerate()
                                      if thread not in baseline and not "process_request_thread" in thread.name], [])
                finally:
                    stopped.set()

    def test_urllib_slow_chunk_size_and_trailers_cannot_extend_total_deadline(self):
        for phase in ("size", "trailers"):
            stopped = threading.Event()

            def respond(handler, number):
                try:
                    handler.wfile.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
                    if phase == "size":
                        chunks = [bytes([byte]) for byte in b"0000000000000000000000001a\r\n"]
                        end = BODY + b"\r\n0\r\n\r\n"
                    else:
                        handler.wfile.write(b"1a\r\n" + BODY + b"\r\n0\r\n")
                        chunks = [b"X-Trailer: value\r\n"] * 15
                        end = b"\r\n"
                    for chunk in chunks:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
                        if stopped.wait(.04):
                            return
                    handler.wfile.write(end)
                except OSError:
                    pass

            with self.subTest(phase=phase), serve(respond) as (url, requests):
                baseline = set(threading.enumerate())
                started = time.monotonic()
                try:
                    with self.assertRaisesRegex(self.module.DownloadError, "超时"):
                        self.download(url, total_timeout=.15)
                    self.assertLess(time.monotonic() - started, .35)
                    self.assertFalse(self.target.exists())
                    self.assertEqual([thread.name for thread in threading.enumerate()
                                      if thread not in baseline and not "process_request_thread" in thread.name], [])
                finally:
                    stopped.set()

    def test_urllib_success_cancels_deadline_worker_and_sdk_has_no_total_limit(self):
        def respond(handler, number):
            handler.wfile.write(b"HTTP/1.1 200 OK\r\n")
            for index in range(4):
                handler.wfile.write(b"X-Slow: value\r\n")
                handler.wfile.flush()
                threading.Event().wait(.05)
            handler.wfile.write(("Content-Length: %d\r\n\r\n" % len(BODY)).encode("ascii") + BODY)

        for total in (None, 3):
            with self.subTest(total=total), serve(respond) as (url, requests):
                baseline = set(threading.enumerate())
                self.download(url, total_timeout=total)
                self.assertEqual(self.target.read_bytes(), BODY)
                self.assertEqual([thread.name for thread in threading.enumerate()
                                  if thread not in baseline and not "process_request_thread" in thread.name], [])

    def test_urllib_slow_https_and_connect_headers_use_same_total_deadline(self):
        openssl = shutil.which("openssl")
        if not openssl:
            self.skipTest("openssl is needed to create a local TLS test certificate")
        cert, key = Path(self.temp.name) / "cert.pem", Path(self.temp.name) / "key.pem"
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(cert), str(key))
        trusted = ssl.create_default_context(cafile=str(cert))
        untrusted = ssl.create_default_context()

        for phase in ("https", "connect", "untrusted"):
            stopped = threading.Event()

            def respond(handler, number):
                try:
                    handler.wfile.write(b"HTTP/1.1 200 OK\r\n")
                    for index in range(15):
                        handler.wfile.write(b"X-Slow: value\r\n")
                        handler.wfile.flush()
                        if stopped.wait(.04):
                            return
                    handler.wfile.write(b"\r\n")
                except (OSError, ssl.SSLError):
                    pass

            with self.subTest(phase=phase), \
                    serve(respond, tls_context=None if phase == "connect" else server_context) as (url, requests), \
                    mock.patch("ssl._create_default_https_context", return_value=untrusted if phase == "untrusted" else trusted), \
                    mock.patch("urllib.request.getproxies", return_value={"https": url} if phase == "connect" else {}), \
                    mock.patch("urllib.request.proxy_bypass", return_value=False), \
                    mock.patch("shutil.which", side_effect=AssertionError("no curl for deadlines or certificates")):
                baseline = set(threading.enumerate())
                start = time.monotonic()
                try:
                    with self.assertRaisesRegex(self.module.DownloadError, "证书" if phase == "untrusted" else "超时"):
                        self.download("https://upstream.invalid/file" if phase == "connect" else url,
                                      total_timeout=.15)
                    self.assertLess(time.monotonic() - start, .35)
                    self.assertFalse(self.target.exists())
                    self.assertEqual([thread.name for thread in threading.enumerate()
                                      if thread not in baseline and not "process_request_thread" in thread.name], [])
                finally:
                    stopped.set()

    def test_curl_failure_is_waited_and_does_not_leave_body(self):
        for code in (60, 77, 35, 18, 7):
            children = []

            def process(argv, **kwargs):
                child = CurlProcess(argv, code=code, **kwargs)
                children.append(child)
                return child

            with self.subTest(code=code), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                    mock.patch("shutil.which", return_value="curl"), \
                    mock.patch("subprocess.Popen", side_effect=process):
                with self.assertRaises(self.module.DownloadError) as raised:
                    self.download()
                if code in (60, 77):
                    self.assertIn("证书", str(raised.exception))
                self.assertTrue(children[0].waited)
                self.assertFalse(self.target.exists())

    def test_curl_network_error_retries_from_original_url_for_a_fresh_redirect(self):
        requested, children = [], []

        def process(argv, **kwargs):
            requested.append(argv[argv.index("--url") + 1])
            if len(requested) in (1, 3):
                signed = "https://assets.invalid/archive?signature=" + ("first" if len(requested) == 1 else "fresh")
                child = CurlProcess(argv, body=b"", status=302, headers={"Location": signed}, **kwargs)
            elif len(requested) == 2:
                child = CurlProcess(argv, body=BODY[:7], headers={}, code=56, **kwargs)
            else:
                child = CurlProcess(argv, **kwargs)
            children.append(child)
            return child

        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process):
            self.download()
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(requested, ["https://download.invalid/archive", "https://assets.invalid/archive?signature=first",
                                     "https://download.invalid/archive", "https://assets.invalid/archive?signature=fresh"])
        self.assertTrue(all(child.waited for child in children))

    def test_curl_retryable_exit_codes_are_bounded_and_terminal_codes_never_retry(self):
        for code in (5, 6, 7, 18, 28, 35, 52, 55, 56, 92, 60, 77, 23, 3):
            children = []

            def process(argv, **kwargs):
                child = CurlProcess(argv, body=b"", code=code, **kwargs)
                children.append(child)
                return child

            with self.subTest(code=code), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                    mock.patch("shutil.which", return_value="curl"), \
                    mock.patch("subprocess.Popen", side_effect=process):
                with self.assertRaises(self.module.DownloadError) as raised:
                    self.download()
            self.assertEqual(len(children), 1 if code in (60, 77, 23, 3) else 3)
            self.assertTrue(all(child.waited for child in children))
            self.assertFalse(self.target.exists())
            if code in (60, 77):
                self.assertIn("证书", str(raised.exception))
            else:
                self.assertIn(str(code), str(raised.exception))

    def test_curl_short_read_and_selected_http_statuses_recover_without_retrying_integrity_errors(self):
        cases = [(b"short", 200, {}, True)]
        cases += [(b"error", status, {}, status != 404) for status in (408, 429, 500, 502, 503, 504, 404)]
        cases += [(BODY + b"extra", 200, {}, False), (b"x" * len(BODY), 200, {}, False),
                  (BODY, 200, {"Content-Length": "999"}, False), (BODY, 200, {"Content-Length": "invalid"}, False)]
        for payload, status, headers, recover in cases:
            children = []

            def process(argv, **kwargs):
                child = (CurlProcess(argv, body=payload, status=status, headers=headers, **kwargs)
                         if not children else CurlProcess(argv, **kwargs))
                children.append(child)
                return child

            with self.subTest(status=status, payload=payload, headers=headers), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                    mock.patch("shutil.which", return_value="curl"), \
                    mock.patch("subprocess.Popen", side_effect=process):
                if recover:
                    self.download()
                    self.assertEqual(self.target.read_bytes(), BODY)
                    self.assertEqual(len(children), 2)
                else:
                    with self.assertRaises(self.module.DownloadError):
                        self.download()
                    self.assertEqual(len(children), 1)
                    self.assertFalse(self.target.exists())
            self.assertTrue(all(child.waited for child in children))

    def test_curl_checks_stream_size_and_hash_and_reaps_on_oversize(self):
        for body, headers in ((BODY + b"extra", {}), (b"x" * len(BODY), None),
                              (BODY, {"Content-Length": "999"}), (BODY[:3], {})):
            children = []

            def process(argv, **kwargs):
                child = CurlProcess(argv, body=body, headers=headers, **kwargs)
                children.append(child)
                return child

            with self.subTest(body=body, headers=headers), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                    mock.patch("shutil.which", return_value="curl"), \
                    mock.patch("subprocess.Popen", side_effect=process):
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assertTrue(children[0].waited)
                self.assertFalse(self.target.exists())

    def test_curl_redirect_recomputes_registry_proxy_and_bypass_for_each_host(self):
        calls = []

        def process(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                return CurlProcess(argv, body=b"redirect", status=302,
                                   headers={"Location": "https://internal.invalid/archive"}, **kwargs)
            return CurlProcess(argv, **kwargs)

        proxies = {"https": "http://user:secret@registry-proxy:8080", "http": "http://wrong:8888"}
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process), \
                mock.patch("urllib.request.getproxies", return_value=proxies), \
                mock.patch("urllib.request.proxy_bypass", side_effect=lambda host: host == "internal.invalid"), \
                mock.patch.dict(os.environ, {"ALL_PROXY": "http://wrong:8080", "all_proxy": "http://wrong:8080",
                                             "HTTP_PROXY": "http://wrong:8080", "NO_PROXY": "*",
                                             "SSL_CERT_FILE": "/custom/trust.pem"}):
            self.download()
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertEqual(len(calls), 2)
        for argv, kwargs in calls:
            self.assertNotIn("secret", " ".join(argv))
            self.assertEqual(kwargs["env"]["SSL_CERT_FILE"], "/custom/trust.pem")
            self.assertNotIn("ALL_PROXY", list(kwargs["env"]))
            self.assertNotIn("all_proxy", list(kwargs["env"]))
            self.assertNotIn("HTTP_PROXY", list(kwargs["env"]))
            self.assertNotIn("NO_PROXY", list(kwargs["env"]))
        self.assertEqual(calls[0][1]["env"].get("https_proxy"), proxies["https"])
        self.assertNotIn("https_proxy", list(calls[1][1]["env"]))

    def test_curl_redirect_to_http_is_rejected_before_second_process(self):
        calls = []

        def process(argv, **kwargs):
            calls.append(argv)
            return CurlProcess(argv, body=b"", status=302,
                               headers={"Location": "http://insecure.invalid/file"}, **kwargs)

        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process):
            with self.assertRaisesRegex(self.module.DownloadError, "重定向"):
                self.download()
        self.assertEqual(len(calls), 1)

    def test_curl_proxy_bypass_preserves_port_specific_no_proxy(self):
        calls = []

        def process(argv, **kwargs):
            calls.append(kwargs["env"])
            return CurlProcess(argv, **kwargs)

        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process), \
                mock.patch("urllib.request.getproxies", return_value={"https": "http://proxy:8080"}), \
                mock.patch("urllib.request.proxy_bypass", side_effect=lambda host: host == "internal.invalid:8443"):
            self.download("https://internal.invalid:8443/archive")
        self.assertNotIn("https_proxy", list(calls[0]))

    def test_curl_uses_all_proxy_unless_protocol_proxy_or_bypass_takes_precedence(self):
        cases = (
            ({"all": "socks5h://127.0.0.1:7890"}, False, "socks5h://127.0.0.1:7890"),
            ({"all": "socks5h://127.0.0.1:7890", "https": "http://protocol-proxy:8080"},
             False, "http://protocol-proxy:8080"),
            ({"all": "socks5h://127.0.0.1:7890"}, True, None),
        )
        for proxies, bypass, expected in cases:
            captured = []

            def process(argv, **kwargs):
                captured.append(kwargs["env"].get("https_proxy"))
                return CurlProcess(argv, **kwargs)

            with self.subTest(bypass=bypass, expected=expected), \
                    mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                    mock.patch("shutil.which", return_value="curl"), \
                    mock.patch("subprocess.Popen", side_effect=process), \
                    mock.patch("urllib.request.getproxies", return_value=proxies), \
                    mock.patch("urllib.request.proxy_bypass", return_value=bypass):
                self.download()
            self.assertEqual(captured, [expected])
            self.assertEqual(self.target.read_bytes(), BODY)

    def test_curl_stderr_and_launch_errors_never_reveal_credentials(self):
        real_popen = subprocess.Popen
        children = []

        def process(argv, **kwargs):
            child = real_popen([sys.executable, "-c",
                               "import sys; sys.stderr.write('https://user:password@proxy'); sys.exit(7)"], **kwargs)
            children.append(child)
            return child

        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process):
            with self.assertRaises(self.module.DownloadError) as raised:
                self.download()
        self.assertNotIn("password", str(raised.exception) + " ".join(self.logs))
        self.assertIsNotNone(children[0].poll())
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=OSError("https://user:password@proxy")):
            with self.assertRaises(self.module.DownloadError) as raised:
                self.download()
        self.assertNotIn("password", str(raised.exception) + " ".join(self.logs))

    def test_hung_curl_is_killed_and_waited_at_total_deadline(self):
        original_popen = subprocess.Popen
        children = []

        def process(argv, **kwargs):
            child = original_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child

        start = time.monotonic()
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process):
            with self.assertRaisesRegex(self.module.DownloadError, "超时"):
                self.download(total_timeout=.3)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertFalse(self.target.exists())

    def test_curl_terminal_http_error_stops_without_waiting_for_slow_body(self):
        real_popen = subprocess.Popen
        children = []

        def process(argv, **kwargs):
            script = ("import pathlib,sys,time; "
                      "pathlib.Path(sys.argv[1]).write_bytes(b'HTTP/1.1 404 Not Found\\r\\n\\r\\n'); "
                      "sys.stdout.buffer.write(b'error'); sys.stdout.flush(); time.sleep(30)")
            child = real_popen([sys.executable, "-c", script,
                                argv[argv.index("--dump-header") + 1]], **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()), \
                mock.patch("shutil.which", return_value="curl"), \
                mock.patch("subprocess.Popen", side_effect=process):
            with self.assertRaisesRegex(self.module.DownloadError, "404"):
                self.download(timeout=1)
        self.assertLess(time.monotonic() - started, .8)
        self.assertIsNotNone(children[0].poll())


if __name__ == "__main__":
    unittest.main()
