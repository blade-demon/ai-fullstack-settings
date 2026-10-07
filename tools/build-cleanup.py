#!/usr/bin/env python3
"""在 macOS 的独立 universal2 Python 环境构建成员卸载程序；从不安装依赖。"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/uninstall_java_gradle.py"
NAME = "cleanup-macos-universal2"
PYINSTALLER_VERSION = "6.22.3"
PYTHON_VERSION = "3.14.6"
ARCHITECTURES = ["arm64", "x86_64"]
LICENSE_FILES = (
    "expat-python-3.14.6.txt", "hacl-python-3.14.6.txt",
    "openssl-3.5.7.txt", "xz-5.2.3.txt", "zstd-1.5.7.txt",
)


class BuildError(Exception):
    pass


def normalized_source(path):
    # Text mode also normalizes bare CR. Identical to the Windows packager.
    return path.read_text(encoding="utf-8-sig").encode("utf-8")


def source_sha256(path):
    return hashlib.sha256(normalized_source(path)).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def macho_architectures(path):
    """无需 macOS 命令即可验证 fat 表及真实 64 位可执行 slice。"""
    formats = {b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
               b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True)}
    cpu_names = {0x0100000C: "arm64", 0x01000007: "x86_64"}
    length = path.stat().st_size
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8 or prefix[:4] not in formats:
            raise BuildError("需要 universal2 Mach-O 可执行文件：{}".format(path.name))
        endian, wide = formats[prefix[:4]]
        if struct.unpack(endian + "I", prefix[4:])[0] != 2:
            raise BuildError("Mach-O 必须且只能包含 arm64 / x86_64 两种架构")
        entry_size = 32 if wide else 20
        table = handle.read(2 * entry_size)
        if len(table) != 2 * entry_size:
            raise BuildError("Mach-O 架构表不完整")
        found, ranges = [], []
        for index in range(2):
            entry = struct.unpack_from(endian + ("IIQQII" if wide else "IIIII"),
                                       table, index * entry_size)
            cpu, _, offset, size, alignment = entry[:5]
            if cpu not in cpu_names or cpu_names[cpu] in found:
                raise BuildError("Mach-O 架构不匹配或重复")
            if (alignment > 31 or offset % (1 << alignment) or size < 32
                    or offset < 8 + 2 * entry_size or offset + size > length
                    or any(offset < end and offset + size > start for start, end in ranges)):
                raise BuildError("Mach-O slice 越界、重叠或对齐错误")
            handle.seek(offset)
            header = handle.read(32)
            thin_endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(header[:4])
            if not thin_endian:
                raise BuildError("Mach-O slice 不是 64 位可执行文件")
            fields = struct.unpack(thin_endian + "IIIIIIII", header)
            if fields[1] != cpu or fields[3] != 2:
                raise BuildError("Mach-O slice 实际架构或文件类型不匹配")
            found.append(cpu_names[cpu])
            ranges.append((offset, offset + size))
    return sorted(found)


def verify_bundle(output, source=SOURCE):
    output, source = Path(output), Path(source)
    paths = {name: output / name for name in (NAME, "manifest.json", "THIRD_PARTY_NOTICES.txt")}
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise BuildError("产物缺失、为空或为符号链接：{}".format(name))
    try:
        manifest = json.loads(paths["manifest.json"].read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise BuildError("manifest.json 不是有效 JSON") from error
    if not isinstance(manifest, dict) or type(manifest.get("schema")) is not int or manifest["schema"] != 1:
        raise BuildError("manifest schema 必须为 1")
    if manifest.get("architectures") != ARCHITECTURES:
        raise BuildError("manifest 架构必须为 arm64 / x86_64")
    for key in ("python_version", "pyinstaller_version"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise BuildError("manifest 缺少版本：{}".format(key))
    for key in ("sha256", "source_sha256", "notices_sha256"):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest[key]):
            raise BuildError("manifest 缺少有效 SHA-256：{}".format(key))
    if file_sha256(paths[NAME]) != manifest["sha256"]:
        raise BuildError("可执行文件 SHA-256 不匹配，请重新构建")
    if source_sha256(source) != manifest["source_sha256"]:
        raise BuildError("源码已变化，卸载产物已过期，请在 macOS 重新构建")
    if file_sha256(paths["THIRD_PARTY_NOTICES.txt"]) != manifest["notices_sha256"]:
        raise BuildError("第三方许可 THIRD_PARTY_NOTICES.txt 摘要不匹配")
    if macho_architectures(paths[NAME]) != ARCHITECTURES:
        raise BuildError("可执行文件不是 arm64 / x86_64 universal2")
    return manifest


def collect_notices():
    documentation = (Path(sys.base_prefix) / "Resources/English.lproj/Documentation"
                     / "_sources/license.rst.txt")
    if not documentation.is_file():
        raise BuildError("缺少 Python 完整许可文档；请使用包含文档的 python.org macOS 安装包")
    distribution = importlib.metadata.distribution("pyinstaller")
    copying = [path for path in (distribution.files or []) if str(path).endswith("/COPYING.txt")]
    if len(copying) != 1:
        raise BuildError("PyInstaller 安装缺少完整 COPYING.txt 许可")
    sections = [
        "Member cleanup runtime — Third-party notices\n"
        "Built from the unmodified CPython runtime and PyInstaller bootloader.\n"
        "No Python installation is required on the member machine.\n"
        "Build-only packages are listed in manifest.json; they are not runtime dependencies.\n",
        "CPython {} and incorporated software\n"
        "Source: https://www.python.org/ftp/python/{}/Python-{}.tar.xz\n\n{}".format(
            PYTHON_VERSION, PYTHON_VERSION, PYTHON_VERSION, documentation.read_text(encoding="utf-8")),
        "PyInstaller {} (bootloader exception and Apache-2.0 runtime hooks)\n"
        "Source: https://github.com/pyinstaller/pyinstaller/tree/v{}\n\n{}".format(
            PYINSTALLER_VERSION, PYINSTALLER_VERSION,
            distribution.locate_file(copying[0]).read_text(encoding="utf-8")),
    ]
    for name in LICENSE_FILES:
        path = ROOT / "tools/cleanup-licenses" / name
        if not path.is_file() or not path.stat().st_size:
            raise BuildError("缺少第三方许可数据：{}".format(name))
        sections.append(path.read_text(encoding="utf-8"))
    return ("\n" + "=" * 78 + "\n\n").join(sections).rstrip() + "\n"


def publish_bundle(output, executable, source, expected_source_hash, metadata, notices):
    # Stage and check first, then preserve only the three managed files for rollback.
    if source_sha256(source) != expected_source_hash:
        raise BuildError("构建期间源码已变化；未发布产物，请重新构建")
    output = Path(output)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise BuildError("输出路径必须是实际目录")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".cleanup-publish-", dir=str(output.parent)))
    preserve_recovery = False
    try:
        shutil.copyfile(executable, stage / NAME)
        (stage / NAME).chmod(0o755)
        (stage / "THIRD_PARTY_NOTICES.txt").write_text(notices, encoding="utf-8")
        manifest = dict(metadata, schema=1, architectures=ARCHITECTURES,
                        sha256=file_sha256(stage / NAME), source_sha256=expected_source_hash,
                        notices_sha256=file_sha256(stage / "THIRD_PARTY_NOTICES.txt"))
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
        verify_bundle(stage, source)
        output.mkdir(exist_ok=True)
        names = (NAME, "THIRD_PARTY_NOTICES.txt", "manifest.json")
        previous = stage / "previous"
        previous.mkdir()
        existing = set()
        for name in names:
            target = output / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise BuildError("现有产物不是常规文件，未发布：{}".format(name))
            if target.exists():
                shutil.copy2(target, previous / name)
                existing.add(name)
        replaced = []
        try:
            # Readers reject intermediate generations because the manifest switches last.
            for name in names:
                os.replace(stage / name, output / name)
                replaced.append(name)
        except BaseException as publish_error:
            rollback_errors = []
            for name in reversed(replaced):
                try:
                    if name in existing:
                        os.replace(previous / name, output / name)
                    else:
                        (output / name).unlink()
                except OSError as error:
                    rollback_errors.append("{}: {}".format(name, error))
            if rollback_errors:
                preserve_recovery = True
                raise BuildError("发布失败且回滚未完成；恢复文件已保留在 {}：{}".format(
                    previous, "; ".join(rollback_errors))) from publish_error
            raise
    finally:
        if not preserve_recovery:
            shutil.rmtree(stage)
    return manifest


def build(output):
    if sys.platform != "darwin":
        raise BuildError("只能在 macOS 构建 universal2；Windows/Linux 可使用 --verify-only")
    # Licenses for the incorporated C libraries are vetted for this python.org release.
    if platform.python_version() != PYTHON_VERSION:
        raise BuildError("请使用 python.org universal2 Python {}；更新运行时需同步审查许可数据".format(PYTHON_VERSION))
    if sys.prefix == sys.base_prefix:
        raise BuildError("请在临时 venv 中构建，避免依赖全局 Python 包")
    try:
        installed = importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError as error:
        raise BuildError("当前 Python 缺少 PyInstaller；请先在该 venv 安装 pyinstaller=={}".format(PYINSTALLER_VERSION)) from error
    if installed != PYINSTALLER_VERSION:
        raise BuildError("需要固定版本 pyinstaller=={}，当前为 {}".format(PYINSTALLER_VERSION, installed))
    macho_architectures(Path(sys.executable).resolve())
    notices = collect_notices()
    snapshot = normalized_source(SOURCE)
    expected_hash = hashlib.sha256(snapshot).hexdigest()
    metadata = {
        "source": "tools/uninstall_java_gradle.py",
        "source_normalization": "UTF-8 without BOM; LF newlines",
        "python_version": platform.python_version(),
        "pyinstaller_version": installed,
        "build_script_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "macos_deployment_target": sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET"),
        "codesign": "ad-hoc; not notarized",
        "build_dependencies": {name: importlib.metadata.version(name) for name in (
            "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "macholib", "packaging", "setuptools")},
    }
    with tempfile.TemporaryDirectory(prefix="member-cleanup-build-") as directory:
        work = Path(directory)
        source = work / SOURCE.name
        source.write_bytes(snapshot)
        command = [sys.executable, "-I", "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile",
                   "--console", "--target-arch", "universal2", "--noupx", "--name", NAME,
                   "--distpath", str(work / "dist"), "--workpath", str(work / "work"),
                   "--specpath", str(work / "spec"), str(source)]
        environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "cache"),
                           PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(command, cwd=str(work), env=environment, check=True)
        executable = work / "dist" / NAME
        macho_architectures(executable)
        # Only --help is run automatically. The cleanup implementation is never invoked with --apply.
        home = work / "empty-home"
        home.mkdir()
        safe_environment = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "en_US.UTF-8",
                            "TMPDIR": str(work)}
        subprocess.run([str(executable), "--help"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=safe_environment, check=True, timeout=60)
        return publish_bundle(output, executable, SOURCE, expected_hash, metadata, notices)


def main(argv=None):
    parser = argparse.ArgumentParser(description="用隔离的 universal2 Python 构建自包含成员卸载程序（不自动安装依赖）")
    parser.add_argument("--output", type=Path, default=ROOT / "resources/cleanup", help="构建产物目录")
    parser.add_argument("--verify-only", action="store_true", help="只核验已有产物、架构、许可与源码摘要；支持 Windows/Linux")
    args = parser.parse_args(argv)
    try:
        manifest = verify_bundle(args.output) if args.verify_only else build(args.output)
    except (BuildError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        print("卸载工具构建/校验失败：{}".format(error), file=sys.stderr)
        details = getattr(error, "stderr", None)
        if details:
            print(details.decode("utf-8", errors="replace") if isinstance(details, bytes) else details,
                  file=sys.stderr)
        return 1
    print("{}：{}\nSHA-256: {}".format("校验通过" if args.verify_only else "构建完成", args.output, manifest["sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
