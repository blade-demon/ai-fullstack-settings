#!/usr/bin/env python3
"""Python 3.8+ server tools. The packaged installation client is macOS-only."""
import argparse
import dataclasses
import functools
import hashlib
import http.client
import http.server
import io
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import socket
import ssl
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

if __package__:
    from .lan import DiscoveryError, discover_ipv4_addresses
else:
    from lan import DiscoveryError, discover_ipv4_addresses

ROOT = Path(__file__).resolve().parents[1]
HEADER = "# id\tgroup\tversion\tarch\tpath\turl\tsha256"
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
SERVER = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._-]*|\[[A-Fa-f0-9:]+\])(?::[0-9]+)?\Z")
PUBLISHED = ("start.command", "start.zip", "team-dev-env.zip",
             "dev-env/team-dev-env.tar.gz", "dev-env/team-dev-env.tar.gz.sha256")
TEXT_SUFFIXES = {".sh", ".command", ".txt", ".yaml", ".yml", ".tsv", ".json", ".in", ".xsl"}
DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
DEVICES.update("%s%s" % (prefix, number) for prefix in ("COM", "LPT") for number in "123456789¹²³")


class UserError(Exception):
    pass


def absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def check_path(path, directory=False, required=False):
    """Reject symlinks, Windows junctions/reparse points, and special files."""
    path = absolute(path)
    for item in [path] + list(path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if item == path and required:
                raise UserError("缺少文件或目录：%s" % path)
            continue
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0)
                                        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise UserError("路径不能经过符号链接或目录联接：%s" % item)
        want_directory = directory if item == path else True
        if want_directory and not stat.S_ISDIR(info.st_mode):
            raise UserError("目录位置已有其他文件：%s" % item)
        if not want_directory and not stat.S_ISREG(info.st_mode):
            raise UserError("目标不是普通文件：%s" % item)
    return path


def relative_path(value, context="清单"):
    # Apply Windows path rules on all hosts before joining an untrusted relative path.
    parts = value.split("/")
    if (not value or PureWindowsPath(value).drive or value.startswith("/")
            or "\\" in value or re.search(r'[<>:"|?*\x00-\x1f\x7f]', value)
            or any(part in ("", ".", "..") or part.endswith((" ", "."))
                   or part.split(".", 1)[0].upper() in DEVICES for part in parts)):
        raise UserError("%s包含不安全或非跨平台相对路径：%s" % (context, value))
    return value


def http_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and not any(char.isspace() or ord(char) < 32 for char in value))
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise UserError("清单 URL 必须是有效的 HTTP(S) 地址：%s" % value)
    return value


@dataclasses.dataclass(frozen=True)
class Resource:
    id: str
    group: str
    version: str
    arch: str
    path: str
    url: str
    sha256: str

    def line(self):
        return "\t".join(dataclasses.astuple(self))


def read_catalog(path):
    check_path(path, required=True)
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != HEADER:
        raise UserError("清单首行必须为 # id、group、version、arch、path、url、sha256（制表符分隔）。")
    resources, ids, occupied = [], set(), set()
    for number, line in enumerate(lines[1:], 2):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7 or any(not field or re.search(r"[\x00-\x1f\x7f]", field) for field in fields):
            raise UserError("清单第 %s 行必须恰好包含 7 个非空字段。" % number)
        item = Resource(*fields)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item.id) or item.id in ids:
            raise UserError("清单资源 ID 无效或重复：%s" % item.id)
        if item.group not in ("runtime", "software", "plugins") or item.arch not in ("arm64", "x64", "any"):
            raise UserError("清单分组或架构无效：%s" % item.id)
        relative_path(item.path)
        http_url(item.url)
        if item.sha256 != "-" and not SHA256.fullmatch(item.sha256):
            raise UserError("清单 SHA-256 必须是 64 位十六进制或 -：%s" % item.id)
        names = (item.path.casefold(), (item.path + ".sha256").casefold())
        for name in names:
            if any(name == other or name.startswith(other + "/") or other.startswith(name + "/") for other in occupied):
                raise UserError("清单资源路径或校验文件冲突：%s" % item.path)
        occupied.update(names)
        ids.add(item.id)
        resources.append(dataclasses.replace(item, sha256=item.sha256.lower()))
    if not resources:
        raise UserError("清单没有资源条目。")
    return resources


def sha256_file(path):
    check_path(path, required=True)
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_path(path):
    return path.with_name(path.name + ".sha256")


def read_receipt(path):
    receipt = receipt_path(path)
    check_path(receipt, required=True)
    lines = receipt.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) != 1 or "  " not in lines[0]:
        raise UserError("本地校验记录格式无效：%s" % receipt)
    digest, name = lines[0].split("  ", 1)
    if not SHA256.fullmatch(digest) or name != path.name:
        raise UserError("本地校验记录摘要或文件名不匹配：%s" % receipt)
    return digest.lower()


def write_atomic(path, payload, mode=0o644):
    check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".part.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        os.chmod(temporary, mode)
        check_path(path)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_receipt(path, digest):
    receipt = receipt_path(path)
    check_path(receipt)
    content = (digest + "  " + path.name + "\n").encode("utf-8")
    if not receipt.is_file() or receipt.read_bytes() != content:
        write_atomic(receipt, content)


def publish_new(source, destination):
    """Publish a complete staged file without replacing an existing destination."""
    check_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(str(source), str(destination))
        source.unlink()
    except FileExistsError:
        raise UserError("发布期间目标文件已出现，原文件已保留：%s" % destination)
    except OSError:
        # Windows rename refuses existing targets and works on volumes without hard links.
        if os.name != "nt":
            raise
        os.rename(str(source), str(destination))


class HttpOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        http_url(url)
        return super().redirect_request(request, response, code, message, headers, url)


def download(url, target):
    opener = urllib.request.build_opener(HttpOnlyRedirect())
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "team-dev-env-resource/1"})
            with opener.open(request, timeout=30) as response, target.open("wb") as output:
                http_url(response.geturl())
                expected, received = response.headers.get("Content-Length"), 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                if expected is not None and received != int(expected):
                    raise http.client.IncompleteRead(b"", int(expected) - received)
            return
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                raise UserError("下载失败：HTTP %s，%s" % (error.code, url))
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, ConnectionError) as error:
            if isinstance(getattr(error, "reason", None), ssl.SSLCertVerificationError) or attempt == 2:
                raise UserError("下载失败：%s（%s）" % (url, error))
        print("连接中断，正在重试下载…", flush=True)
        time.sleep(1)


def verify_resource(item, storage):
    target = storage / item.path
    check_path(target, required=True)
    check_path(receipt_path(target))
    expected = item.sha256 if item.sha256 != "-" else read_receipt(target)
    actual = sha256_file(target)
    if actual != expected:
        raise UserError("资源 SHA-256 校验失败，原文件已保留：%s" % target)
    return dataclasses.replace(item, sha256=actual)


def prepare(args, settings):
    storage = option_path(args.output, settings, "resources_dir", ROOT / "resources")
    catalog = option_path(args.catalog, settings, "catalog", ROOT / "resources/catalog.tsv")
    resources = read_catalog(catalog)
    check_path(storage, directory=True)
    for item in resources:
        check_path(storage / item.path)
        check_path(receipt_path(storage / item.path))
    if args.id and not any(item.id == args.id for item in resources):
        raise UserError("未知资源 ID：%s" % args.id)
    selected = [item for item in resources if (not args.id or item.id == args.id)
                and (args.group == "all" or item.group == args.group)
                and (args.arch == "all" or item.arch == args.arch or item.arch == "any")]
    if not selected:
        raise UserError("没有符合分组、架构和资源 ID 条件的条目。")
    if args.dry_run:
        for item in selected:
            print("计划：%s [%s / %s / %s]\n  %s\n  → %s" %
                  (item.id, item.group, item.version, item.arch, item.url, storage / item.path))
        print("计划资源：%s；未写入文件或联网。" % len(selected))
        return
    downloaded = 0
    for item in selected:
        target = storage / item.path
        if target.exists():
            checked = verify_resource(item, storage)
            if not args.verify:
                write_receipt(target, checked.sha256)
            print("OK 已校验：%s" % target)
            continue
        if args.verify:
            raise UserError("缺少资源：%s" % target)
        check_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=target.name + ".part.", dir=str(target.parent))
        os.close(descriptor)
        temporary = Path(filename)
        try:
            print("下载：%s [%s]" % (item.id, item.version), flush=True)
            download(item.url, temporary)
            digest = sha256_file(temporary)
            if item.sha256 != "-" and digest != item.sha256:
                raise UserError("下载资源 SHA-256 与上游清单不符：%s" % item.id)
            if item.sha256 == "-":
                print("提示：%s 无上游 SHA-256，本地记录仅供之后检查文件是否变化。" % item.id)
            temporary.chmod(0o644)
            publish_new(temporary, target)
            write_receipt(target, digest)
            downloaded += 1
            print("OK 已保存：%s" % target)
        finally:
            if temporary.exists():
                temporary.unlink()
    print("资源完成：OK %s；下载 %s；复用/校验 %s。" % (len(selected), downloaded, len(selected) - downloaded))


def member_bytes(path):
    check_path(path, required=True)
    payload = path.read_bytes()
    if path.suffix in TEXT_SUFFIXES:
        return payload.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return payload


def archive_mode(name):
    return 0o755 if name.endswith((".sh", ".command")) else 0o644


def write_zip(path, files):
    with zipfile.ZipFile(str(path), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | archive_mode(name)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)


def write_tar(path, files):
    with tarfile.open(str(path), "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(payload), archive_mode(name)
            info.type, info.uid, info.gid = tarfile.REGTYPE, 0, 0
            archive.addfile(info, io.BytesIO(payload))


def package(args, settings, forced_server=None, catalog_path=None, announce=True):
    output = option_path(args.output, settings, "output", ROOT / "dist/server")
    storage = option_path(args.resources_dir, settings, "resources_dir", ROOT / "resources")
    server = forced_server or args.server or os.environ.get("SERVER_ADDR") or settings.get("server") or safe_env_default("SERVER_ADDR") or "127.0.0.1:8080"
    scheme = "http" if forced_server else (args.scheme or os.environ.get("SERVER_SCHEME") or settings.get("scheme") or safe_env_default("SERVER_SCHEME") or "http")
    if not isinstance(server, str) or not SERVER.fullmatch(server):
        raise UserError("服务器应为主机:端口，不能包含协议、路径、空格或引号。")
    if scheme not in ("http", "https"):
        raise UserError("协议仅支持 http 或 https。")
    allowlist = ROOT / "tools/package-files.txt"
    check_path(allowlist, required=True)
    members = [line.strip() for line in allowlist.read_text(encoding="utf-8-sig").splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    if not members or len(members) != len(set(members)):
        raise UserError("成员文件白名单为空或包含重复条目。")
    generated = {".support/config/team.sh", ".support/config/resources.tsv", ".support/scripts/prepare-resources.sh"}
    files = {}
    for name in members:
        relative_path(name, "白名单")
        if name in generated:
            raise UserError("白名单不能包含打包时生成的文件：%s" % name)
        files["team-dev-env/" + name] = member_bytes(ROOT / "dev-kit" / name)
    if "开始配置.command" not in members:
        raise UserError("白名单缺少成员入口。")
    files["team-dev-env/.support/scripts/prepare-resources.sh"] = member_bytes(ROOT / "tools/prepare-resources.sh")
    files["team-dev-env/.support/config/team.sh"] = (
        '# 打包时的团队服务器默认值；成员可用环境变量覆盖。\n'
        'SERVER_ADDR="${SERVER_ADDR:-%s}"\nSERVER_SCHEME="${SERVER_SCHEME:-%s}"\n' % (server, scheme)).encode("utf-8")
    resources = []
    catalog = catalog_path if catalog_path is not None else storage / "catalog.tsv"
    check_path(catalog)
    if catalog.exists():
        resources = [verify_resource(item, storage) for item in read_catalog(catalog)]
    elif args.with_resources:
        raise UserError("发布资源需要清单：%s" % catalog)
    files["team-dev-env/.support/config/resources.tsv"] = (
        HEADER + "\n" + "".join(item.line() + "\n" for item in resources)).encode("utf-8")
    launcher = member_bytes(ROOT / "tools/start.command.in").replace(b"@SERVER_ADDR@", server.encode("ascii"))
    launcher = launcher.replace(b"@SERVER_SCHEME@", scheme.encode("ascii"))
    check_path(output, directory=True)
    for name in PUBLISHED:
        check_path(output / name)
    if args.with_resources:
        check_path(output / "resources", directory=True)
        for item in resources:
            target = output / "resources" / item.path
            check_path(target)
            check_path(receipt_path(target))
            if target.exists() and sha256_file(target) != item.sha256:
                raise UserError("资源发布目标内容冲突，原文件已保留：%s" % target)
            if receipt_path(target).exists() and read_receipt(target) != item.sha256:
                raise UserError("资源发布目标校验记录冲突：%s" % receipt_path(target))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".package.", dir=str(output)) as temporary:
        staging = Path(temporary)
        (staging / "dev-env").mkdir()
        (staging / "start.command").write_bytes(launcher)
        (staging / "start.command").chmod(0o755)
        write_zip(staging / "start.zip", {"开始配置.command": launcher})
        write_zip(staging / "team-dev-env.zip", files)
        archive = staging / "dev-env/team-dev-env.tar.gz"
        write_tar(archive, files)
        write_receipt(archive, sha256_file(archive))
        additions = []
        if args.with_resources:
            for item in resources:
                target, staged = output / "resources" / item.path, staging / "resources" / item.path
                staged.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    source = check_path(storage / item.path, required=True)
                    shutil.copyfile(str(source), str(staged))
                    staged.chmod(0o644)
                    if sha256_file(staged) != item.sha256:
                        raise UserError("复制期间资源内容发生变化：%s" % item.path)
                    additions.append((staged, target))
                if not receipt_path(target).exists():
                    receipt_path(staged).write_bytes((item.sha256 + "  " + target.name + "\n").encode("utf-8"))
                    additions.append((receipt_path(staged), receipt_path(target)))
        for name in PUBLISHED:
            check_path(output / name)
        for source, target in additions:
            check_path(target)
            if target.exists():
                raise UserError("发布期间目标文件已出现，原文件已保留：%s" % target)
        for source, target in additions:
            publish_new(source, target)
        for name in PUBLISHED:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(staging / name), str(target))
    if announce:
        print("已生成：%s\n静态服务根目录：%s\n待部署下载地址：%s://%s/start.zip" % (output, output, scheme, server))
        print("打包不会启动服务器。Windows/macOS 可使用 server/manage.py serve。", flush=True)
    return output


def safe_env_default(name):
    path = ROOT / "dev-kit/.support/config/env.sh"
    check_path(path, required=True)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?" + name + r"\s*=\s*([\"']?)(.*?)\1\s*", line)
        if not match:
            continue
        value, prefix = match.group(2), "${" + name + ":-"
        if value.startswith(prefix) and value.endswith("}"):
            value = value[len(prefix):-1]
        if (name == "SERVER_ADDR" and SERVER.fullmatch(value)) or (name == "SERVER_SCHEME" and value in ("http", "https")):
            return value
    return None


def option_path(cli, settings, key, default):
    if cli is not None:
        return absolute(cli)
    value = settings.get(key)
    if value is None:
        return absolute(default)
    if not isinstance(value, str) or not value:
        raise UserError("配置路径必须为非空字符串：%s" % key)
    if os.name != "nt" and PureWindowsPath(value).drive:
        raise UserError("Windows 绝对路径只能在 Windows 上使用：%s" % value)
    path = Path(value.replace("\\", "/"))
    return absolute(path if path.is_absolute() else ROOT / path)


class DownloadHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        try:
            decoded = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if "\\" in decoded or "\x00" in decoded or ".." in decoded.split("/"):
                raise UserError("路径无效")
            target = Path(self.translate_path(self.path))
            relative = target.relative_to(absolute(self.directory))
            if str(relative) != ".":
                relative_path(relative.as_posix(), "下载路径")
            check_path(target, directory=target.is_dir())
            if target.is_dir():
                # SimpleHTTPRequestHandler resolves these after the requested directory.
                for name in ("index.html", "index.htm"):
                    check_path(target / name)
        except (UserError, ValueError, OSError):
            self.send_error(403, "Forbidden path")
            return None
        return super().send_head()

    def log_message(self, message, *args):
        print("%s - %s" % (self.address_string(), message % args), flush=True)


class DownloadServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def checked_port(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise UserError("端口必须为 1—65535 的整数。")
    return value


def select_lan_address():
    try:
        candidates = discover_ipv4_addresses()
    except DiscoveryError as error:
        raise UserError("%s 可用 start --server 主机地址 手动指定。" % error)
    if not candidates:
        raise UserError("未找到可用的内网 IPv4，请连接团队网络后重试，或用 start --server 主机地址 指定。")
    if len(candidates) == 1:
        return candidates[0]
    print("检测到多个网络地址，请选择成员能够访问的服务器内网地址：", flush=True)
    for number, address in enumerate(candidates, 1):
        print("  %s. %s" % (number, address), flush=True)
    if not sys.stdin.isatty():
        raise UserError("多个地址无法自动确定；请在终端选择，或用 start --server 主机地址 指定。")
    try:
        choice = int(input("请输入地址序号：").strip())
        if not 1 <= choice <= len(candidates):
            raise ValueError
    except (ValueError, EOFError):
        raise UserError("未选择有效地址，已停止；请重新启动并选择序号，或用 --server 指定。")
    return candidates[choice - 1]


def start_endpoint(args, settings):
    scheme = os.environ.get("SERVER_SCHEME") or settings.get("scheme") or "http"
    if scheme != "http":
        raise UserError("一键启动仅提供 HTTP；HTTPS 请使用 package --scheme https 并配置反向代理。")
    configured = args.server or os.environ.get("SERVER_ADDR") or settings.get("server")
    host, address_port = None, None
    if configured:
        if not isinstance(configured, str) or not SERVER.fullmatch(configured):
            raise UserError("--server 应为主机或主机:端口，不能包含协议、路径或空格。")
        try:
            parsed = urllib.parse.urlsplit("http://" + configured)
            host, address_port = parsed.hostname, parsed.port
            numeric = ipaddress.ip_address(host) if re.fullmatch(r"[0-9.]+|.*:.*", host) else None
        except ValueError:
            raise UserError("--server 的主机或端口无效。")
        # Older example configs defaulted to localhost; a one-click LAN start
        # must discover the actual address instead of publishing that default.
        if not args.server and (host == "localhost" or (numeric and numeric.is_loopback)):
            host, address_port = None, None
        elif numeric and (numeric.version != 4 or numeric.is_unspecified or numeric.is_multicast
                          or numeric.is_reserved or numeric.is_link_local):
            raise UserError("--server 需要可访问的 IPv4 或主机名；0.0.0.0 仅用于监听，不能用于下载。")
    if args.server and address_port is not None and args.port is not None and address_port != args.port:
        raise UserError("--server 中的端口与 --port 不一致，请使用同一端口。")
    port = checked_port(args.port if args.port is not None else (
        address_port if address_port is not None else settings.get("port", 8080)))
    host = host or select_lan_address()
    return "%s:%s" % (host, port), port


def start(args, settings):
    address, port = start_endpoint(args, settings)
    directory = option_path(args.output, settings, "output", ROOT / "dist/server")
    storage = option_path(args.resources_dir, settings, "resources_dir", ROOT / "resources")
    default_catalog = storage / "catalog.tsv"
    if not default_catalog.exists():
        default_catalog = ROOT / "resources/catalog.tsv"
    catalog = option_path(args.catalog, settings, "catalog", default_catalog)
    check_path(directory, directory=True)
    handler = functools.partial(DownloadHandler, directory=str(directory))
    try:
        server = DownloadServer(("0.0.0.0", port), handler)
    except OSError as error:
        raise UserError("端口已被占用或不可用：%s（%s）；未准备资源或改写发布文件。" % (port, error))
    # Keep the bound socket throughout preparation; never probe and release it.
    with server:
        print("服务器地址：http://%s\n[1/3] 正在校验资源，缺少的文件会自动下载…" % address, flush=True)
        prepare(argparse.Namespace(output=str(storage), catalog=str(catalog), group="all", arch="all",
                                   id=None, verify=False, dry_run=False), {})
        print("[2/3] 正在生成启动包和发布目录…", flush=True)
        package(argparse.Namespace(output=str(directory), resources_dir=str(storage), server=address,
                                   scheme="http", with_resources=True), {}, forced_server=address,
                catalog_path=catalog, announce=False)
        print("[3/3] 下载服务已就绪\n成员下载链接：http://%s/start.zip" % address, flush=True)
        print("监听：0.0.0.0:%s；托管目录：%s\n保持窗口运行，Ctrl+C 停止。" % (port, directory), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n下载服务已停止。", flush=True)


def serve(args, settings, preview=False):
    directory = (option_path(args.output, settings, "output", ROOT / "dist/server") if preview
                 else option_path(args.directory, settings, "directory",
                                  option_path(None, settings, "output", ROOT / "dist/server")))
    bind = "127.0.0.1" if preview else (args.bind or settings.get("bind", "127.0.0.1"))
    if bind not in ("127.0.0.1", "0.0.0.0"):
        raise UserError("--bind 仅支持 127.0.0.1 或显式的 0.0.0.0。")
    port = args.port if args.port is not None else (8081 if preview else settings.get("port", 8080))
    port = checked_port(port)
    if not preview:
        check_path(directory, directory=True, required=True)
        if not all((directory / name).is_file() for name in PUBLISHED):
            raise UserError("服务目录尚未打包完整，请先执行 package，并指定打包输出目录：%s" % directory)
        for name in PUBLISHED:
            check_path(directory / name, required=True)
    handler = functools.partial(DownloadHandler, directory=str(directory))
    try:
        server = DownloadServer((bind, port), handler)
    except OSError as error:
        raise UserError("端口已被占用或不可用：%s:%s（%s）；已有服务未改动。" % (bind, port, error))
    with server:
        if preview:
            args.with_resources = True
            package(args, settings, forced_server="127.0.0.1:%s" % port)
        print("%s：http://127.0.0.1:%s/start.zip" % ("本机预览已就绪" if preview else "下载服务已就绪", port), flush=True)
        print("监听：%s:%s；托管目录：%s\n客户端安装脚本仅适用于 macOS。保持窗口运行，Ctrl+C 停止。" % (bind, port, directory), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n下载服务已停止。", flush=True)


def read_settings(argv):
    argv, config, explicit = list(argv), ROOT / "server/config.json", False
    while "--config" in argv:
        index = argv.index("--config")
        if explicit or index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise UserError("--config 需要且只能指定一个 JSON 配置文件。")
        config = absolute(argv[index + 1])
        del argv[index:index + 2]
        explicit = True
    check_path(config)
    if not config.exists() and not explicit:
        return argv, {}
    check_path(config, required=True)
    settings = json.loads(config.read_text(encoding="utf-8-sig"))
    allowed = {"server", "scheme", "output", "resources_dir", "catalog", "directory", "bind", "port"}
    if not isinstance(settings, dict) or set(settings) - allowed:
        raise UserError("JSON 配置必须为对象，且只包含已支持的服务端选项。")
    return argv, settings


def make_parser():
    parser = argparse.ArgumentParser(description="跨平台资源下载、macOS 客户端打包与只读 HTTP 服务（Python 3.8+）。",
                                     epilog="可在任意位置添加 --config FILE；默认读取 server/config.json。配置相对目录基于项目根目录。")
    commands = parser.add_subparsers(dest="command", required=True)
    startup = commands.add_parser("start", help="自动选址、准备资源、打包并启动内网下载服务（默认操作）")
    startup.add_argument("--server", help="覆盖自动检测，指定成员可访问的主机或主机:端口")
    startup.add_argument("--port", type=int, help="下载服务端口，默认 8080")
    startup.add_argument("--output", help="发布目录，默认 dist/server")
    startup.add_argument("--resources-dir", help="本地资源库，默认 resources")
    startup.add_argument("--catalog", help="资源清单，默认优先使用资源库内的 catalog.tsv")
    preparation = commands.add_parser("prepare", help="下载/校验固定清单资源，不执行安装程序")
    preparation.add_argument("--output")
    preparation.add_argument("--catalog")
    preparation.add_argument("--group", choices=("all", "runtime", "software", "plugins"), default="all")
    preparation.add_argument("--arch", choices=("all", "arm64", "x64", "any"), default="all")
    preparation.add_argument("--id")
    modes = preparation.add_mutually_exclusive_group()
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    packaging = commands.add_parser("package", help="生成启动包与完整工具包，不启动服务")
    preview = commands.add_parser("preview", help="先占用本机端口，再打包并启动本机预览")
    for command in (packaging, preview):
        command.add_argument("--output")
        command.add_argument("--resources-dir")
    packaging.add_argument("--server")
    packaging.add_argument("--scheme", choices=("http", "https"))
    packaging.add_argument("--with-resources", action="store_true")
    preview.add_argument("--port", type=int)
    preview.set_defaults(server=None, scheme=None, with_resources=True)
    serving = commands.add_parser("serve", help="只读托管已打包目录，不修改发布文件")
    serving.add_argument("--directory")
    serving.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"))
    serving.add_argument("--port", type=int)
    return parser


def main(argv=None):
    if sys.version_info < (3, 8):
        print("需要 Python 3.8 或更新版本。", file=sys.stderr)
        return 1
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        arguments, settings = read_settings(sys.argv[1:] if argv is None else argv)
        args = make_parser().parse_args(arguments or ["start"])
        if args.command == "start":
            start(args, settings)
        elif args.command == "prepare":
            prepare(args, settings)
        elif args.command == "package":
            package(args, settings)
        else:
            serve(args, settings, preview=args.command == "preview")
        return 0
    except (UserError, OSError, ValueError, UnicodeError) as error:
        print("操作失败：%s" % error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n操作已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
