"""Validate or fetch the pinned macOS runtimes, without executing downloaded code.

The repository lock pins an archive and every member. Only the seven managed
files can be installed; unknown resource files are never part of publication.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import urllib.parse
import zipfile
import zlib

try:
    from . import cleanup_artifact, tui_artifact
    from .network_download import download_file
except ImportError:
    import cleanup_artifact
    import tui_artifact
    from network_download import download_file


FILES = (
    "resources/tui/team-dev-env-arm64",
    "resources/tui/team-dev-env-amd64",
    "resources/tui/manifest.json",
    "resources/tui/THIRD_PARTY_NOTICES.txt",
    "resources/cleanup/cleanup-macos-universal2",
    "resources/cleanup/manifest.json",
    "resources/cleanup/THIRD_PARTY_NOTICES.txt",
)
ARCHIVE_NAME = "team-dev-env-runtimes.zip"
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
MAX_FILE_SIZE = 256 * 1024 * 1024
MAX_LOCK_SIZE = 128 * 1024
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_DEADLINE = 300
CHUNK_SIZE = 1024 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class RuntimeArtifactError(ValueError):
    """A runtime cannot be validated or safely installed."""


def _safe_path(path, directory=False, required=False):
    """Check every ancestor, including Windows junctions on any test host."""
    path = Path(os.path.abspath(os.fspath(path)))
    for item in (path,) + tuple(path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if item == path and required:
                raise RuntimeArtifactError("缺少运行文件或目录：%s" % path)
            continue
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise RuntimeArtifactError("运行文件路径不能经过符号链接或目录联接：%s" % item)
        want_directory = directory if item == path else True
        if not (stat.S_ISDIR(info.st_mode) if want_directory else stat.S_ISREG(info.st_mode)):
            raise RuntimeArtifactError("运行文件路径不是%s：%s" % (
                "普通目录" if want_directory else "普通文件", item))
    return path


def _read_file(path, limit=MAX_FILE_SIZE):
    path = _safe_path(path, required=True)
    if path.stat().st_size > limit:
        raise RuntimeArtifactError("运行文件超过大小上限：%s" % path)
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise RuntimeArtifactError("运行文件超过大小上限：%s" % path)
    return data


def _source_state(root):
    source = _read_file(root / "tools/uninstall_java_gradle.py")
    normalized = source.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    _safe_path(root / "tui", directory=True, required=True)
    return {"tui": tui_artifact.source_sha256(root / "tui"),
            "cleanup": hashlib.sha256(normalized).hexdigest()}, source


def _validate_payloads(payloads, source_hashes, cleanup_source):
    tui = tui_artifact.validate_tui_artifact(
        {arch: payloads["resources/tui/" + name] for arch, name in tui_artifact.BINARIES.items()},
        payloads["resources/tui/manifest.json"], source_hashes["tui"],
        payloads["resources/tui/THIRD_PARTY_NOTICES.txt"])
    cleanup_bytes = payloads["resources/cleanup/manifest.json"]
    cleanup_artifact.validate_cleanup_artifact(
        payloads["resources/cleanup/cleanup-macos-universal2"], cleanup_bytes, cleanup_source)
    cleanup = json.loads(cleanup_bytes.decode("utf-8-sig"))
    notices = payloads["resources/cleanup/THIRD_PARTY_NOTICES.txt"]
    digest = cleanup.get("notices_sha256")
    # Older cleanup schema-1 manifests did not record a notices digest. Their
    # notices must be nonempty; downloads also pin them in runtime-lock.json.
    if (not notices.strip() or "notices_sha256" in cleanup and (
            not isinstance(digest, str) or not SHA256.fullmatch(digest.lower())
            or hashlib.sha256(notices).hexdigest() != digest.lower())):
        raise RuntimeArtifactError("卸载运行时第三方许可 THIRD_PARTY_NOTICES.txt 摘要不匹配或为空。")
    return {"source_sha256": source_hashes, "tui_manifest": tui,
            "cleanup_manifest": cleanup, "release": "local", "downloaded": False}


def validate_local_runtimes(root):
    """Validate both artifacts against current sources, independently of the lock."""
    try:
        root = _safe_path(root, directory=True, required=True)
        source_hashes, source = _source_state(root)
        payloads = {name: _read_file(root / name) for name in FILES}
        return _validate_payloads(payloads, source_hashes, source)
    except (OSError, ValueError) as error:
        if isinstance(error, RuntimeArtifactError):
            raise
        raise RuntimeArtifactError(str(error)) from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeArtifactError("runtime-lock.json 存在重复字段：%s" % key)
        result[key] = value
    return result


def _valid_digest(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _valid_entry(entry, limit):
    return (isinstance(entry, dict) and _valid_digest(entry.get("sha256"))
            and type(entry.get("size")) is int and 0 < entry["size"] <= limit)


def _read_lock(root, source_hashes):
    try:
        lock = json.loads(_read_file(root / "resources/runtime-lock.json", MAX_LOCK_SIZE)
                          .decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as error:
        raise RuntimeArtifactError("无法读取 runtime-lock.json：%s" % error) from error
    if not isinstance(lock, dict) or type(lock.get("schema")) is not int or lock["schema"] != 1:
        raise RuntimeArtifactError("runtime-lock.json schema 必须为 1。")
    archive = lock.get("archive")
    if not _valid_entry(archive, MAX_ARCHIVE_SIZE):
        raise RuntimeArtifactError("runtime-lock.json 归档 SHA-256 或大小无效。")
    release = "runtimes-" + archive["sha256"][:16]
    url = archive.get("url")
    # Keep owner/repo rules aligned with tools/release-runtimes.py. Matching
    # the full URL also excludes credentials, ports, query strings and fragments.
    url_match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)/releases/download/"
        + re.escape(release) + "/" + re.escape(ARCHIVE_NAME), url) if isinstance(url, str) else None
    if lock.get("release") != release or not url_match or url_match.group(2) in (".", ".."):
        raise RuntimeArtifactError("runtime-lock.json 必须固定 GitHub release URL 与归档版本。")
    hashes = lock.get("source_sha256")
    if (not isinstance(hashes, dict) or set(hashes) != {"tui", "cleanup"}
            or not all(_valid_digest(value) for value in hashes.values())):
        raise RuntimeArtifactError("runtime-lock.json 源码摘要无效。")
    if hashes != source_hashes:
        raise RuntimeArtifactError("运行文件锁已过期，与当前源码不一致；请更新匹配源码的 runtime-lock.json。")
    entries = lock.get("files")
    if (not isinstance(entries, dict) or set(entries) != set(FILES)
            or not all(_valid_entry(entry, MAX_FILE_SIZE) for entry in entries.values())
            or sum(entry["size"] for entry in entries.values()) > MAX_ARCHIVE_SIZE):
        raise RuntimeArtifactError("runtime-lock.json 必须精确固定 7 个运行文件及其有效大小和 SHA-256。")
    return lock


def _download_url(lock, base_url):
    if base_url is None:
        return lock["archive"]["url"]
    if not isinstance(base_url, str) or any(ord(character) < 32 for character in base_url):
        raise RuntimeArtifactError("运行文件镜像 URL 无效。")
    try:
        parsed = urllib.parse.urlsplit(base_url)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeArtifactError("运行文件镜像必须是有效的 HTTP 或 HTTPS 地址。")
    return base_url.rstrip("/") + "/" + ARCHIVE_NAME


def _download(url, destination, expected, report=print):
    download_file(url, destination, expected_sha256=expected["sha256"],
                  expected_size=expected["size"], timeout=DOWNLOAD_TIMEOUT,
                  total_timeout=DOWNLOAD_DEADLINE, report=report)


def _unpack(archive_path, candidate, entries):
    """Copy only allowlisted members; ZipFile.extract is intentionally unused."""
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(FILES) or set(names) != set(FILES):
            raise RuntimeArtifactError("运行文件 ZIP 必须精确包含 7 个文件，不能包含额外、重复或缺失成员。")
        for info in infos:
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            expected = entries[info.filename]
            if (info.is_dir() or info.orig_filename != info.filename or file_type not in (0, stat.S_IFREG)
                    or info.external_attr & 0x10 or info.flag_bits & 1
                    or info.file_size != expected["size"]
                    or info.compress_size < 0 or info.compress_size > MAX_ARCHIVE_SIZE):
                raise RuntimeArtifactError("运行文件 ZIP 成员类型或大小无效：%s" % info.filename)
        for info in infos:
            expected = entries[info.filename]
            target = candidate / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with archive.open(info) as source, target.open("wb") as output:
                while True:
                    chunk = source.read(min(CHUNK_SIZE, expected["size"] - size + 1))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > expected["size"]:
                        raise RuntimeArtifactError("运行文件 ZIP 成员超过锁定大小：%s" % info.filename)
                    digest.update(chunk)
                    output.write(chunk)
            if size != expected["size"] or digest.hexdigest() != expected["sha256"]:
                raise RuntimeArtifactError("运行文件 ZIP 成员 SHA-256 或大小校验失败：%s" % info.filename)
            target.chmod(0o755 if target.name.startswith(("team-dev-env-", "cleanup-macos-")) else 0o644)


def _publish(root, work, candidate, expected_hashes):
    previous, rollback = work / "previous", work / "rollback"
    existing, replaced, created = set(), [], []
    for name in FILES:
        target = _safe_path(root / name)
        if target.exists():
            backup = previous / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            existing.add(name)
    if _source_state(root)[0] != expected_hashes:
        raise RuntimeArtifactError("下载期间源码已变化；未发布运行文件，请重试。")
    try:
        for relative in ("resources", "resources/tui", "resources/cleanup"):
            directory = _safe_path(root / relative, directory=True)
            if not directory.exists():
                directory.mkdir()
                created.append(directory)
        # Publish manifests last so validators reject any mixed generation.
        order = [name for name in FILES if not name.endswith("/manifest.json")]
        order += [name for name in FILES if name.endswith("/manifest.json")]
        for name in order:
            target = _safe_path(root / name)
            os.replace(candidate / name, target)
            replaced.append(name)
    except BaseException as error:
        failures = []
        for name in reversed(replaced):
            try:
                target = _safe_path(root / name)
                if name in existing:
                    restore = rollback / name
                    restore.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(previous / name, restore)
                    os.replace(restore, target)
                else:
                    target.unlink()
            except (OSError, ValueError) as failure:
                failures.append("%s: %s" % (name, failure))
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError as failure:
                failures.append("%s: %s" % (directory, failure))
        if failures:
            # ensure_runtimes preserves this directory for manual recovery.
            (work / "KEEP_RECOVERY").touch()
            raise RuntimeArtifactError("发布失败且回滚未完成；原文件已保留在 %s：%s" % (
                previous, "; ".join(failures))) from error
        raise


def ensure_runtimes(root, base_url=None, offline=False, report=print):
    """Reuse valid local artifacts or download and transactionally install a pin."""
    work = None
    try:
        root = _safe_path(root, directory=True, required=True)
        try:
            local = validate_local_runtimes(root)
        except RuntimeArtifactError as error:
            if offline:
                raise RuntimeArtifactError("离线模式下运行文件缺失、损坏或过期；请联网补齐后重试。%s" % error) from error
        else:
            return {"release": "local", "downloaded": False, "source_sha256": local["source_sha256"]}
        # Reject unsafe destinations before touching the network or staging files.
        for name in FILES:
            _safe_path(root / name)
        source_hashes, cleanup_source = _source_state(root)
        lock = _read_lock(root, source_hashes)
        url = _download_url(lock, base_url)
        report("正在获取匹配当前源码的运行文件：%s" % lock["release"])
        work = Path(tempfile.mkdtemp(prefix=".runtime-stage-", dir=str(root)))
        archive, candidate = work / ARCHIVE_NAME, work / "candidate"
        _download(url, archive, lock["archive"], report=report)
        _unpack(archive, candidate, lock["files"])
        _validate_payloads({name: _read_file(candidate / name) for name in FILES}, source_hashes, cleanup_source)
        _publish(root, work, candidate, source_hashes)
        return {"release": lock["release"], "downloaded": True, "source_sha256": source_hashes}
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError,
            http.client.HTTPException, zlib.error) as error:
        if isinstance(error, RuntimeArtifactError):
            raise
        raise RuntimeArtifactError("无法补齐运行文件：%s" % error) from error
    finally:
        if work is not None and not (work / "KEEP_RECOVERY").exists():
            shutil.rmtree(work)
