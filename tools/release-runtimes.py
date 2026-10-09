#!/usr/bin/env python3
"""Package verified local runtimes for a GitHub Release, without building or uploading."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.runtime_artifacts import FILES, validate_local_runtimes

ARCHIVE = "team-dev-env-runtimes.zip"
REPOSITORY = "blade-demon/ai-fullstack-settings"
BINARY_NAMES = {"team-dev-env-arm64", "team-dev-env-amd64", "cleanup-macos-universal2"}
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_archive(payloads):
    """Stable across host modes, timestamps, operating systems and zlib versions."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.create_system = 3
            mode = 0o755 if Path(name).name in BINARY_NAMES else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, payloads[name])
    return buffer.getvalue()


def release_notes(lock):
    lines = ["# 运行文件发布 %s" % lock["release"], "",
             "本发布包提供已构建的 macOS 双架构 Go TUI 与 universal2 卸载运行时。",
             "成员无需安装 Go；Windows 服务端可直接下载并校验这些文件，再分发给 macOS 成员使用。",
             "Windows 服务端不会执行 macOS 二进制。", "",
             "- 版本：`%s`" % lock["release"],
             "- ZIP SHA-256：`%s`" % lock["archive"]["sha256"],
             "- ZIP 字节数：%s" % lock["archive"]["size"],
             "- TUI 源码 SHA-256：`%s`" % lock["source_sha256"]["tui"],
             "- 卸载源码 SHA-256：`%s`" % lock["source_sha256"]["cleanup"], "",
             "源码摘要使用 UTF-8 去 BOM、LF 换行规范化，兼容 Windows Git 检出。",
             "ZIP 仅包含下列 7 个仓库相对路径；二进制权限为 755，清单及许可为 644。", "",
             "| 文件 | 字节数 | SHA-256 |", "| --- | ---: | --- |"]
    for name, entry in sorted(lock["files"].items()):
        lines.append("| `%s` | %s | `%s` |" % (name, entry["size"], entry["sha256"]))
    lines.extend(["", "下载地址：%s" % lock["archive"]["url"], "",
                  "发布包由仓库锁文件固定版本和摘要；生成工具只做本地打包，不会自动上传。", ""])
    return "\n".join(lines).encode("utf-8")


def _read_payloads(root):
    return {name: (root / name).read_bytes() for name in sorted(FILES)}


def _verify_unchanged(root, sources, payloads):
    current = validate_local_runtimes(root)
    if current["source_sha256"] != sources or _read_payloads(root) != payloads:
        raise ValueError("打包期间源码或运行文件已变化，请重新生成发布包。")


def _check_destination(path, directory=False):
    if path.is_symlink() or (path.exists() and
                            not (path.is_dir() if directory else path.is_file())):
        raise ValueError("发布目标必须是实际%s：%s" % ("目录" if directory else "文件", path))
    if path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise ValueError("发布目标不能是目录联接：%s" % path)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("运行文件锁存在重复字段：%s" % key)
        result[key] = value
    return result


def _publish(files, verify):
    """Stage every file before replacement; commit the lock last and roll back failures."""
    staged, backups, replaced, recovery = {}, {}, [], set()
    try:
        for target, payload in files.items():
            _check_destination(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".runtime-release-", dir=str(target.parent))
            staged[target] = Path(temporary)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged[target].chmod(0o644)
            if target.exists():
                descriptor, temporary = tempfile.mkstemp(prefix=".runtime-previous-", dir=str(target.parent))
                os.close(descriptor)
                backups[target] = Path(temporary)
                shutil.copy2(target, backups[target])
        verify()
        try:
            for target in files:
                os.replace(staged[target], target)
                replaced.append(target)
            verify()
        except BaseException as error:
            failures = []
            for target in reversed(replaced):
                try:
                    if target in backups:
                        os.replace(backups[target], target)
                    else:
                        target.unlink()
                except OSError as rollback_error:
                    if target in backups:
                        recovery.add(backups[target])
                    failures.append("%s: %s" % (target, rollback_error))
            if failures:
                raise OSError("发布失败且回滚未完成；备份保留在 %s；%s" % (
                    ", ".join(str(path) for path in sorted(recovery)), "; ".join(failures))) from error
            raise
    finally:
        for path in list(staged.values()) + list(backups.values()):
            if path not in recovery and path.exists():
                path.unlink()


def release_runtimes(root, output, lock_path, repository=REPOSITORY, verify_only=False):
    root, output, lock_path = Path(root), Path(output), Path(lock_path)
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository)
            or repository.split("/")[1] in (".", "..")):
        raise ValueError("仓库必须使用 owner/repo 格式。")
    validated = validate_local_runtimes(root)
    sources = validated["source_sha256"]
    payloads = _read_payloads(root)
    archive = build_archive(payloads)
    digest = hashlib.sha256(archive).hexdigest()
    release = "runtimes-" + digest[:16]
    lock = {
        "schema": 1, "release": release, "source_sha256": sources,
        "archive": {"url": "https://github.com/%s/releases/download/%s/%s" % (repository, release, ARCHIVE),
                    "sha256": digest, "size": len(archive)},
        "files": {name: {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
                  for name, payload in sorted(payloads.items())},
    }
    files = {output / ARCHIVE: archive}
    if lock_path in files:
        raise ValueError("锁文件路径不能与发布文件重叠。")
    files[lock_path] = (json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    def verify():
        _verify_unchanged(root, sources, payloads)

    verify()
    _check_destination(output, directory=True)
    for path in files:
        _check_destination(path)
    if verify_only:
        for path, expected in files.items():
            actual = path.read_bytes()
            if path == lock_path:
                try:
                    decoded = json.loads(actual.decode("utf-8-sig"), object_pairs_hook=_unique_object)
                    # JSON numeric types matter: True == 1 and 1.0 == 1 in Python.
                    canonical = (json.dumps(decoded, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
                    matches = canonical == expected
                except (ValueError, UnicodeError):
                    matches = False
            else:
                matches = actual == expected
            if not matches:
                raise ValueError("发布文件与本地产物或锁定内容不一致：%s" % path)
        verify()
    else:
        _publish(files, verify)
    return lock


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验并生成固定版本的 macOS 运行文件发布包（无需 Go，不上传）")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/runtime-release", help="运行文件 ZIP 输出目录")
    parser.add_argument("--lock", type=Path, default=ROOT / "resources/runtime-lock.json", help="仓库运行文件锁路径")
    parser.add_argument("--repository", default=REPOSITORY, help="GitHub 仓库 owner/repo")
    parser.add_argument("--verify-only", action="store_true", help="只校验现有发布包、锁和本地源码，不写入任何文件")
    args = parser.parse_args(argv)
    try:
        lock = release_runtimes(ROOT, args.output, args.lock, args.repository, args.verify_only)
    except (OSError, ValueError) as error:
        print("运行文件发布包%s失败：%s" % ("校验" if args.verify_only else "生成", error), file=sys.stderr)
        return 1
    print("%s：%s\n版本：%s\nZIP SHA-256：%s" % (
        "校验通过" if args.verify_only else "生成完成", args.output, lock["release"], lock["archive"]["sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
