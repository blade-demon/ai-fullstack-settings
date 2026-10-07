"""Bounded HTTP downloads with verified retries and an optional system curl.

The destination belongs to this operation (normally a temporary archive). Each
attempt replaces it, and failure removes it. Downloaded bytes are never run.
"""
import errno
import hashlib
import http.client
import io
import math
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


CHUNK_SIZE = 64 * 1024
MAX_REDIRECTS = 10
MAX_HEADERS = 128 * 1024
MAX_REDIRECT_BODY = 64 * 1024
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
CURL_RETRY_CODES = {5, 6, 7, 18, 28, 35, 52, 55, 56, 92}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
NETWORK_HELP = "下载失败；请检查网络和代理配置，或使用内网镜像。"
HEADERS = {"User-Agent": "team-dev-env-download/1", "Accept-Encoding": "identity"}


class DownloadError(ValueError):
    """A download failed without exposing proxy credentials or server output."""


class _ShortRead(Exception):
    pass


class _CurlRetryable(DownloadError):
    """A native transport failure that permits a fresh, bounded retry."""


class _Budget:
    def __init__(self, timeout, total_timeout):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise DownloadError("下载超时参数无效。")
        if total_timeout is not None and (not isinstance(total_timeout, (int, float))
                                         or not math.isfinite(total_timeout) or total_timeout <= 0):
            raise DownloadError("下载总超时参数无效。")
        self.timeout = timeout
        self.deadline = None if total_timeout is None else time.monotonic() + total_timeout

    def remaining(self):
        if self.deadline is None:
            return None
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DownloadError("下载超时；请检查网络和代理配置，或使用内网镜像。")
        return remaining

    def io_timeout(self):
        remaining = self.remaining()
        return self.timeout if remaining is None else min(self.timeout, remaining)


def _valid_url(url):
    if (not isinstance(url, str) or not url or "\\" in url
            or any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in url)):
        raise DownloadError("下载 URL 必须是有效的 HTTP 或 HTTPS 地址。")
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname
                 and "@" not in parsed.netloc)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise DownloadError("下载 URL 必须是无凭据的 HTTP 或 HTTPS 地址。")
    return url


def _redirect_url(url, location):
    if (not isinstance(location, str) or not location or "\\" in location
            or any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in location)):
        raise DownloadError("下载重定向 URL 无效。")
    try:
        target = _valid_url(urllib.parse.urljoin(url, location))
    except (ValueError, DownloadError):
        raise DownloadError("下载重定向 URL 无效。") from None
    if (urllib.parse.urlsplit(url).scheme == "https"
            and urllib.parse.urlsplit(target).scheme != "https"):
        raise DownloadError("下载重定向不能从 HTTPS 降级到 HTTP。")
    return target


def _single_header(headers, name):
    values = headers.get_all(name, [])
    if len(values) > 1:
        raise DownloadError("下载响应头存在冲突。")
    return values[0] if values else None


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, budget):
        self.budget = budget
        self.count = 0

    def http_error_302(self, req, fp, code, msg, headers):
        # Closing first avoids the standard handler's unbounded redirect-body
        # read. Validate the destination before issuing any redirected request.
        fp.close()
        self.count += 1
        if self.count > MAX_REDIRECTS:
            raise DownloadError("下载重定向超过 10 次。")
        target = _redirect_url(req.full_url, _single_header(headers, "Location"))
        request = urllib.request.Request(target, headers=HEADERS)
        return self.parent.open(request, timeout=self.budget.io_timeout())

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


class _ConnectionDeadline:
    """Interrupt a connected socket, including slow HTTP framing reads."""
    def __init__(self, budget):
        self.budget = budget
        self.connection = None
        self.socket = None
        self.timer = None

    def start(self, sock):
        self.socket = sock
        sock.settimeout(self.budget.io_timeout())
        self.timer = threading.Timer(self.budget.remaining(), self._interrupt)
        self.timer.daemon = True
        self.timer.start()

    def _interrupt(self):
        # HTTPS replaces its initial socket after the TLS handshake. Look up
        # the current socket at expiry so both HTTPS and proxy CONNECT headers
        # are covered, without changing certificate validation or SSL contexts.
        sock = getattr(self.connection, "sock", None) or self.socket
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def cancel(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer.join()


class _DeadlineHandler:
    def __init__(self, budget):
        self.budget = budget
        super().__init__()

    def do_open(self, http_class, req, **kwargs):
        deadline = _ConnectionDeadline(self.budget)

        def connection_factory(*args, **connection_kwargs):
            connection = http_class(*args, **connection_kwargs)
            deadline.connection = connection
            create_connection = connection._create_connection

            def connect(*connect_args, **connect_kwargs):
                # http.client exposes this per-instance connection hook. The
                # timer starts once TCP has connected, before proxy CONNECT or
                # response headers; platform DNS lookup is not interruptible.
                sock = create_connection(*connect_args, **connect_kwargs)
                try:
                    deadline.start(sock)
                except BaseException:
                    sock.close()
                    raise
                return sock

            connection._create_connection = connect
            return connection

        try:
            return super().do_open(connection_factory, req, **kwargs)
        finally:
            deadline.cancel()


class _DeadlineHTTPHandler(_DeadlineHandler, urllib.request.HTTPHandler):
    pass


class _DeadlineHTTPSHandler(_DeadlineHandler, urllib.request.HTTPSHandler):
    pass


class _Body:
    def __init__(self, expected_size, expected_sha256, headers):
        length = _single_header(headers, "Content-Length")
        if length is not None:
            if not re.fullmatch(r"[0-9]{1,20}", length):
                raise DownloadError("下载响应大小无效。")
            length = int(length)
        if expected_size is not None and length is not None and length != expected_size:
            raise DownloadError("下载大小与预期大小不一致。")
        self.limit = expected_size if expected_size is not None else length
        self.expected_sha256 = expected_sha256
        self.size = 0
        self.digest = hashlib.sha256()

    def read_size(self):
        return CHUNK_SIZE if self.limit is None else min(CHUNK_SIZE, self.limit - self.size + 1)

    def write(self, output, chunk):
        self.size += len(chunk)
        if self.limit is not None and self.size > self.limit:
            raise DownloadError("下载超过预期大小。")
        self.digest.update(chunk)
        output.write(chunk)

    def finish(self):
        if self.limit is not None and self.size < self.limit:
            raise _ShortRead()
        if self.expected_sha256 is not None and self.digest.hexdigest() != self.expected_sha256:
            raise DownloadError("下载文件 SHA-256 校验失败。")


def _urllib_download(url, target, expected_size, expected_sha256, budget):
    handlers = [_SafeRedirectHandler(budget)]
    if budget.deadline is not None:
        handlers.extend([_DeadlineHTTPHandler(budget), _DeadlineHTTPSHandler(budget)])
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers=HEADERS)
    deadline = _ConnectionDeadline(budget)
    try:
        with opener.open(request, timeout=budget.io_timeout()) as response, target.open("wb") as output:
            raw = getattr(getattr(response, "fp", None), "raw", None)
            sock = getattr(raw, "_sock", None)
            if sock is not None and budget.deadline is not None:
                # read1 can itself wait for chunk sizes/trailers one byte at a
                # time. Retain the same deadline during all body framing.
                deadline.start(sock)
            if response.status != 200:
                raise DownloadError("下载服务返回 HTTP %s。" % response.status)
            body = _Body(expected_size, expected_sha256, response.headers)
            read = getattr(response, "read1", response.read)
            while True:
                io_timeout = budget.io_timeout()
                raw = getattr(getattr(response, "fp", None), "raw", None)
                sock = getattr(raw, "_sock", None)
                if sock is not None:
                    sock.settimeout(io_timeout)
                chunk = read(body.read_size())
                budget.remaining()
                if not chunk:
                    break
                body.write(output, chunk)
            body.finish()
    finally:
        deadline.cancel()


def _error_chain(error):
    seen, pending = set(), [error]
    while pending:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        pending.extend([getattr(item, "reason", None), item.__cause__, item.__context__])


def _certificate_error(error):
    return any(isinstance(item, ssl.SSLCertVerificationError)
               or isinstance(item, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(item).upper()
               for item in _error_chain(error))


def _recoverable(error):
    for item in _error_chain(error):
        if isinstance(item, urllib.error.HTTPError):
            return item.code in RETRY_STATUSES
        if isinstance(item, (ssl.SSLEOFError, socket.timeout, TimeoutError,
                             ConnectionResetError, ConnectionRefusedError,
                             http.client.IncompleteRead, _ShortRead)):
            return True
        if isinstance(item, OSError) and item.errno in (errno.ECONNRESET, errno.ECONNREFUSED, errno.ETIMEDOUT):
            return True
    return False


def _curl_environment(url):
    # Preserve Windows registry/environment proxy selection for this hop, with
    # curl's ALL_PROXY fallback (including SOCKS). Credentials stay in the
    # child's environment, never argv or diagnostics.
    env = {key: value for key, value in os.environ.items()
           if key.lower() not in ("http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy")}
    parsed = urllib.parse.urlsplit(url)
    proxies = urllib.request.getproxies()
    if not urllib.request.proxy_bypass(parsed.netloc):
        proxy = proxies.get(parsed.scheme) or proxies.get("all")
        if proxy:
            env[parsed.scheme + "_proxy"] = proxy
    return env


def _curl_headers(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_HEADERS + 1)
    if len(data) > MAX_HEADERS:
        raise DownloadError("下载响应头超过大小上限。")
    result = None
    # CONNECT and informational responses may precede the actual HTTP result.
    for block in re.split(br"\r?\n\r?\n", data)[:-1]:
        line, separator, rest = block.partition(b"\n")
        match = re.fullmatch(br"HTTP/\S+ ([0-9]{3})(?:[^\r\n]*)\r?", line)
        if not match:
            raise DownloadError("curl 下载响应头无效。")
        status = int(match.group(1))
        if status >= 200:
            result = (status, http.client.parse_headers(io.BytesIO(rest + b"\r\n\r\n")))
    if result is None:
        raise DownloadError("curl 未返回完整下载响应。")
    return result


def _read_pipe(stream, messages, stopped):
    def send(value):
        while not stopped.is_set():
            try:
                messages.put(value, timeout=.1)
                return
            except queue.Full:
                continue

    try:
        read = getattr(stream, "read1", stream.read)
        while not stopped.is_set():
            data = read(CHUNK_SIZE)
            send(data)
            if not data:
                return
    except (OSError, ValueError):
        send(None)


def _curl_hop(curl, url, target, expected_size, expected_sha256, budget):
    with tempfile.TemporaryDirectory(prefix="team-dev-env-curl-") as temporary:
        header_path = Path(temporary) / "headers"
        header_path.touch(mode=0o600)
        argv = [curl, "-q", "--silent", "--globoff", "--no-buffer", "--proto", "=http,https", "--request", "GET",
                "--header", "Accept-Encoding: identity", "--user-agent", HEADERS["User-Agent"],
                "--connect-timeout", str(budget.io_timeout()),
                "--speed-time", str(max(1, int(math.ceil(budget.timeout)))), "--speed-limit", "1",
                "--dump-header", str(header_path), "--output", "-"]
        remaining = budget.remaining()
        if remaining is not None:
            argv.extend(["--max-time", str(remaining)])
        argv.extend(["--url", url])
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=_curl_environment(url), shell=False)
        messages, stopped = queue.Queue(maxsize=2), threading.Event()
        reader = threading.Thread(target=_read_pipe, args=(process.stdout, messages, stopped), daemon=True)
        reader.start()
        status, headers, body, discarded = None, None, None, 0
        last_data = time.monotonic()
        try:
            with target.open("wb") as output:
                while True:
                    remaining = budget.remaining()
                    idle_remaining = budget.timeout - (time.monotonic() - last_data)
                    if idle_remaining <= 0:
                        raise _CurlRetryable("curl 下载超时；请检查网络和代理配置，或使用内网镜像。")
                    wait = idle_remaining if remaining is None else min(idle_remaining, remaining)
                    try:
                        chunk = messages.get(timeout=wait)
                    except queue.Empty:
                        raise _CurlRetryable("curl 下载超时；请检查网络和代理配置，或使用内网镜像。") from None
                    if chunk is None:
                        raise DownloadError(NETWORK_HELP)
                    if status is None and chunk:
                        status, headers = _curl_headers(header_path)
                        if status == 200:
                            body = _Body(expected_size, expected_sha256, headers)
                        elif status in REDIRECT_STATUSES:
                            _redirect_url(url, _single_header(headers, "Location"))
                        else:
                            error_class = _CurlRetryable if status in RETRY_STATUSES else DownloadError
                            raise error_class("curl 下载服务返回 HTTP %s。" % status)
                    if not chunk:
                        break
                    last_data = time.monotonic()
                    if status == 200:
                        body.write(output, chunk)
                    else:
                        discarded += len(chunk)
                        if discarded > MAX_REDIRECT_BODY:
                            raise DownloadError("下载重定向或错误响应正文超过大小上限。")
                try:
                    code = process.wait(timeout=budget.io_timeout())
                except subprocess.TimeoutExpired:
                    raise _CurlRetryable("curl 下载超时；请检查网络和代理配置，或使用内网镜像。") from None
                budget.remaining()
                if code in (51, 58, 60, 77, 82, 83, 90, 91):
                    raise DownloadError("curl 下载证书验证失败（退出码 %s）；请检查系统信任证书和代理配置。" % code)
                if code != 0:
                    error_class = _CurlRetryable if code in CURL_RETRY_CODES else DownloadError
                    raise error_class("curl 下载失败（退出码 %s）；请检查网络和代理配置，或使用内网镜像。" % code)
                if status is None:
                    status, headers = _curl_headers(header_path)
                    if status == 200:
                        body = _Body(expected_size, expected_sha256, headers)
                if status in REDIRECT_STATUSES:
                    return _redirect_url(url, _single_header(headers, "Location"))
                if status != 200:
                    error_class = _CurlRetryable if status in RETRY_STATUSES else DownloadError
                    raise error_class("curl 下载服务返回 HTTP %s。" % status)
                body.finish()
                return None
        finally:
            stopped.set()
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=1)
            process.stdout.close()


def _curl_download(curl, url, target, expected_size, expected_sha256, budget):
    for number in range(MAX_REDIRECTS + 1):
        redirect = _curl_hop(curl, url, target, expected_size, expected_sha256, budget)
        if redirect is None:
            return
        if number == MAX_REDIRECTS:
            raise DownloadError("curl 下载重定向超过 10 次。")
        url = redirect


def download_file(url, target, *, expected_sha256=None, expected_size=None,
                  timeout=30, total_timeout=None, report=print):
    """Download HTTP(S) from scratch, retrying only recoverable transport errors.

    ``timeout`` bounds connection/read inactivity; optional ``total_timeout``
    shares a deadline across attempts and redirects, interrupting connected
    urllib sockets and curl at expiry. Platform DNS resolution before urllib's
    socket exists cannot be interrupted. Supply the pinned size and hash when
    available. Callers with separate verification may leave them unset.
    """
    target = Path(target)
    try:
        _valid_url(url)
        if expected_size is not None and (type(expected_size) is not int or expected_size < 0):
            raise DownloadError("下载预期大小无效。")
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
                raise DownloadError("下载预期 SHA-256 无效。")
            expected_sha256 = expected_sha256.lower()
        budget = _Budget(timeout, total_timeout)
        for attempt in range(3):
            try:
                _urllib_download(url, target, expected_size, expected_sha256, budget)
                return
            except (OSError, ValueError, http.client.HTTPException, _ShortRead) as error:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                if _certificate_error(error):
                    raise DownloadError("下载证书验证失败；请检查系统信任证书和代理配置。") from None
                budget.remaining()
                if isinstance(error, DownloadError):
                    raise error from None
                if not _recoverable(error):
                    if isinstance(error, urllib.error.HTTPError):
                        raise DownloadError("下载服务返回 HTTP %s。" % error.code) from None
                    raise DownloadError(NETWORK_HELP) from None
                if attempt < 2:
                    report("下载连接中断，将重新下载（%s/3）。" % (attempt + 2))
                    remaining = budget.remaining()
                    time.sleep(attempt + 1 if remaining is None else min(attempt + 1, remaining))
        curl = shutil.which("curl")
        if curl is None:
            raise DownloadError(NETWORK_HELP)
        report("下载连接仍不稳定，正在使用系统 curl 恢复下载。")
        for attempt in range(3):
            try:
                # Restart at the original URL to obtain fresh signed redirects.
                _curl_download(curl, url, target, expected_size, expected_sha256, budget)
                return
            except (_CurlRetryable, _ShortRead) as error:
                budget.remaining()
                message = ("curl 下载正文不完整；请检查网络和代理配置，或使用内网镜像。"
                           if isinstance(error, _ShortRead) else str(error))
                if attempt == 2:
                    raise DownloadError(message) from None
                report("%s 正在重新下载（%s/3）。" % (message, attempt + 2))
                remaining = budget.remaining()
                time.sleep(attempt + 1 if remaining is None else min(attempt + 1, remaining))
    except BaseException as error:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        if isinstance(error, DownloadError):
            raise
        if isinstance(error, (OSError, ValueError, http.client.HTTPException, _ShortRead)):
            raise DownloadError(NETWORK_HELP) from None
        raise
