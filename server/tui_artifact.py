"""Cross-platform, non-executing validation for the prebuilt macOS Go TUI."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct


BINARIES = {"arm64": "team-dev-env-arm64", "amd64": "team-dev-env-amd64"}
FILES = tuple(BINARIES.values()) + ("THIRD_PARTY_NOTICES.txt", "manifest.json")
CPU_TYPES = {"arm64": 0x0100000C, "amd64": 0x01000007}
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")


def regular_path(path, directory=False):
    path = Path(path)
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ValueError("TUI 路径不能是符号链接或目录联接：%s" % path)
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("TUI 路径类型无效：%s" % path)
    return path


def source_files(directory):
    directory = regular_path(directory, directory=True)
    files = []
    for current, directories, names in os.walk(str(directory), followlinks=False):
        for name in directories:
            regular_path(Path(current) / name, directory=True)
        for name in names:
            path = Path(current) / name
            if path.suffix == ".go" or name in ("go.mod", "go.sum"):
                regular_path(path)
                files.append(path)
    if not {"go.mod", "go.sum"}.issubset({p.relative_to(directory).as_posix() for p in files}):
        raise ValueError("TUI 源码缺少 go.mod 或 go.sum。")
    if not any(path.suffix == ".go" for path in files):
        raise ValueError("TUI 源码缺少 Go 文件。")
    return sorted(files, key=lambda path: path.relative_to(directory).as_posix())


def source_sha256(directory):
    directory = Path(directory)
    digest = hashlib.sha256()
    for path in source_files(directory):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8") + b"\0")
        content = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        digest.update(content.encode("utf-8") + b"\0")
    return digest.hexdigest()


def validate_macho(binary, architecture):
    endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(binary[:4])
    if len(binary) < 32 or endian is None:
        raise ValueError("TUI %s 不是完整的 thin 64 位 Mach-O。" % architecture)
    fields = struct.unpack_from(endian + "8I", binary)
    if fields[1] != CPU_TYPES[architecture] or fields[3] != 2:
        raise ValueError("TUI %s 的 Mach-O 架构或 MH_EXECUTE 文件类型不匹配。" % architecture)
    if fields[5] > len(binary) - 32 or fields[4] > fields[5] // 8:
        raise ValueError("TUI %s 的 Mach-O 命令表被截断。" % architecture)


def validate_tui_artifact(binaries, manifest_bytes, source_hash, notices):
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise ValueError("TUI manifest.json 格式无效。") from error
    if (not isinstance(manifest, dict) or type(manifest.get("schema")) is not int
            or manifest["schema"] != 1):
        raise ValueError("TUI 清单 schema 必须为 1。")
    for key in ("source_sha256", "notices_sha256"):
        if not isinstance(manifest.get(key), str) or not SHA256.fullmatch(manifest[key]):
            raise ValueError("TUI 清单缺少有效的 %s。" % key)
    if source_hash != manifest["source_sha256"].lower():
        raise ValueError("TUI 产物已过期，与当前源码不一致。")
    if not notices.strip() or hashlib.sha256(notices).hexdigest() != manifest["notices_sha256"].lower():
        raise ValueError("TUI 第三方许可 THIRD_PARTY_NOTICES.txt 摘要不匹配或为空。")
    entries = manifest.get("binaries")
    if not isinstance(entries, dict) or set(entries) != set(BINARIES):
        raise ValueError("TUI 清单必须包含 arm64 和 amd64。")
    for architecture, filename in BINARIES.items():
        entry = entries[architecture]
        if (not isinstance(entry, dict) or entry.get("file") != filename
                or not isinstance(entry.get("sha256"), str) or not SHA256.fullmatch(entry["sha256"])):
            raise ValueError("TUI %s 清单文件名或 SHA-256 无效。" % architecture)
        payload = binaries[architecture]
        if hashlib.sha256(payload).hexdigest() != entry["sha256"].lower():
            raise ValueError("TUI %s 可执行文件 SHA-256 校验失败。" % architecture)
        validate_macho(payload, architecture)
    return manifest


def verify_bundle(output, source):
    output = regular_path(output, directory=True)
    payloads = {name: regular_path(output / name).read_bytes() for name in FILES}
    return validate_tui_artifact({arch: payloads[name] for arch, name in BINARIES.items()},
                                 payloads["manifest.json"], source_sha256(source),
                                 payloads["THIRD_PARTY_NOTICES.txt"])
