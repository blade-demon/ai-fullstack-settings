#!/usr/bin/env python3
"""Build both macOS Go TUI binaries with an existing, isolated Go toolchain."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tui"
sys.path.insert(0, str(ROOT))
from server import tui_artifact

BINARIES = tui_artifact.BINARIES
FILES = tui_artifact.FILES


class BuildError(Exception):
    pass


def verify_bundle(output, source=None):
    try:
        return tui_artifact.verify_bundle(output, SOURCE if source is None else source)
    except (OSError, ValueError) as error:
        raise BuildError(str(error)) from error


def build_environment(work):
    """Ignore user Go settings and keep downloaded modules, caches and HOME temporary."""
    work = Path(work)
    environment = dict(os.environ)
    for name in ("GOROOT", "GOOS", "GOARCH", "GOAMD64", "GOARM64", "GOEXPERIMENT", "GOTOOLDIR", "GOCACHEPROG"):
        environment.pop(name, None)
    environment.update(CGO_ENABLED="0", GOENV="off", GOTOOLCHAIN="local", GOWORK="off",
                       GOFLAGS="-mod=readonly", GO111MODULE="on", GOTELEMETRY="off")
    for key, name in (("HOME", "home"), ("GOPATH", "gopath"), ("GOMODCACHE", "modules"),
                      ("GOCACHE", "cache"), ("GOTMPDIR", "tmp"), ("TMPDIR", "tmp"),
                      ("XDG_CACHE_HOME", "xdg-cache"), ("XDG_CONFIG_HOME", "xdg-config")):
        path = work / name
        path.mkdir(parents=True, exist_ok=True)
        environment[key] = str(path)
    return environment


def license_files(directory):
    return sorted((path for path in Path(directory).rglob("*")
                   if path.is_file() and re.match(r"^(?:licen[cs]e|copying|notice|copyright|patents)(?:[._-]|$)",
                                                 path.name, re.IGNORECASE)),
                  key=lambda path: path.relative_to(directory).as_posix())


def collect_notices(goroot, version, modules):
    goroot = Path(goroot)
    go_license = goroot / "LICENSE"
    if not go_license.is_file() or not go_license.read_bytes().strip():
        raise BuildError("Go 工具链缺少完整 LICENSE 许可文件。")
    sections = ["Team development environment TUI — Third-party notices\n"
                "This distribution contains Go executables built with CGO_ENABLED=0.\n"
                "License texts below are copied from the named, versioned toolchain and module sources.\n",
                "Go %s\nSource: https://go.dev/dl/%s.src.tar.gz\nFile: LICENSE\n\n%s" % (
                    version, version, go_license.read_text(encoding="utf-8-sig"))]
    vendor = goroot / "src/vendor"
    if vendor.is_dir():
        for path in license_files(vendor):
            sections.append("Go %s bundled sources\nSource: https://go.dev/dl/%s.src.tar.gz\n"
                            "File: %s\n\n%s" % (version, version, path.relative_to(goroot).as_posix(),
                                                  path.read_text(encoding="utf-8-sig")))
    for module in sorted(modules, key=lambda item: item["Path"]):
        name, module_version = module["Path"], module.get("Version")
        if not module_version or module.get("Replace") or not module.get("Dir"):
            raise BuildError("依赖必须是有固定版本、无 replace 的已下载模块：%s" % name)
        directory = Path(module["Dir"])
        paths = license_files(directory)
        if not paths:
            raise BuildError("依赖 %s@%s 缺少完整许可文件。" % (name, module_version))
        for path in paths:
            content = path.read_text(encoding="utf-8-sig")
            if not content.strip():
                raise BuildError("第三方许可文件为空：%s" % path)
            sections.append("%s %s\nSource: https://pkg.go.dev/%s@%s\nFile: %s\n\n%s" % (
                name, module_version, name, module_version, path.relative_to(directory).as_posix(), content))
    return ("\n" + "=" * 78 + "\n\n").join(sections).rstrip() + "\n"


def publish_bundle(output, executables, source, expected_source_hash, metadata, notices):
    if tui_artifact.source_sha256(source) != expected_source_hash:
        raise BuildError("构建期间源码已变化；未发布产物，请重新构建。")
    output = Path(output)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise BuildError("TUI 输出路径必须是实际目录。")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tui-publish-", dir=str(output.parent)))
    preserve_recovery = False
    try:
        entries = {}
        for architecture, filename in BINARIES.items():
            shutil.copyfile(executables[architecture], stage / filename)
            (stage / filename).chmod(0o755)
            entries[architecture] = {"file": filename,
                                     "sha256": hashlib.sha256((stage / filename).read_bytes()).hexdigest()}
        notice_bytes = notices.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        (stage / "THIRD_PARTY_NOTICES.txt").write_bytes(notice_bytes)
        (stage / "THIRD_PARTY_NOTICES.txt").chmod(0o644)
        manifest = dict(metadata, schema=1, source_sha256=expected_source_hash, binaries=entries,
                        notices_sha256=hashlib.sha256(notice_bytes).hexdigest())
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
        (stage / "manifest.json").chmod(0o644)
        verify_bundle(stage, source)
        output.mkdir(exist_ok=True)
        previous = stage / "previous"
        previous.mkdir()
        existing = set()
        for name in FILES:
            target = output / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise BuildError("现有 TUI 产物不是常规文件，未发布：%s" % name)
            if target.exists():
                shutil.copy2(target, previous / name)
                existing.add(name)
        replaced = []
        try:
            # The manifest changes last, so readers reject mixed generations.
            for name in FILES:
                os.replace(stage / name, output / name)
                replaced.append(name)
        except BaseException as publish_error:
            failures = []
            for name in reversed(replaced):
                try:
                    if name in existing:
                        os.replace(previous / name, output / name)
                    else:
                        (output / name).unlink()
                except OSError as error:
                    failures.append("%s: %s" % (name, error))
            if failures:
                preserve_recovery = True
                raise BuildError("发布失败且回滚未完成；恢复文件已保留在 %s：%s" % (
                    previous, "; ".join(failures))) from publish_error
            raise
    finally:
        if not preserve_recovery:
            shutil.rmtree(stage)
    return manifest


def decode_json_stream(text):
    decoder, objects, remainder = json.JSONDecoder(), [], text.strip()
    while remainder:
        value, end = decoder.raw_decode(remainder)
        objects.append(value)
        remainder = remainder[end:].lstrip()
    return objects


def build(output, go=None):
    selected = str(go) if go else shutil.which("go")
    if not selected or not Path(selected).is_file():
        raise BuildError("找不到 Go；请通过 --go /path/to/go 指定已有工具链，本工具不会安装 Go。")
    executable = str(Path(selected).resolve())
    expected_hash = tui_artifact.source_sha256(SOURCE)
    with tempfile.TemporaryDirectory(prefix="team-dev-env-tui-build-") as temporary:
        work = Path(temporary)
        environment = build_environment(work)
        snapshot = work / "source"
        snapshot.mkdir()
        for path in tui_artifact.source_files(SOURCE):
            target = snapshot / path.relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_text(encoding="utf-8-sig").encode("utf-8"))
        if tui_artifact.source_sha256(snapshot) != expected_hash:
            raise BuildError("复制期间源码发生变化，请重新构建。")

        def run(arguments, env=None):
            return subprocess.run([executable] + arguments, cwd=str(snapshot),
                                  env=env or environment, check=True, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

        details = json.loads(run(["env", "-json", "GOROOT", "GOVERSION"]))
        print("使用 %s；模块与缓存保存在临时目录。" % details["GOVERSION"], flush=True)
        module_file = json.loads(run(["mod", "edit", "-json"]))
        if module_file.get("Replace"):
            raise BuildError("可发布的 TUI 依赖必须固定版本，不能使用 go.mod replace。")
        # `all` also expands unrelated packages' dependencies and rewrites go.sum.
        # With no module arguments Go downloads only this go.mod's selected modules.
        modules = decode_json_stream(run(["mod", "download", "-json"]))
        selected = {(item["Path"], item["Version"]) for item in module_file.get("Require", [])}
        if {(item["Path"], item["Version"]) for item in modules} != selected:
            raise BuildError("下载模块与 go.mod 的固定版本列表不一致。")
        if tui_artifact.source_sha256(snapshot) != expected_hash:
            raise BuildError("Go 修改了依赖锁定文件；请先更新并检查 go.mod/go.sum，再重新构建。")
        notices = collect_notices(details["GOROOT"], details["GOVERSION"], modules)
        executables = {}
        for architecture, filename in BINARIES.items():
            target = work / filename
            print("正在构建 darwin/%s …" % architecture, flush=True)
            run(["build", "-trimpath", "-buildvcs=false", "-mod=readonly", "-ldflags=-s -w -buildid=",
                 "-o", str(target), "."], dict(environment, GOOS="darwin", GOARCH=architecture))
            tui_artifact.validate_macho(target.read_bytes(), architecture)
            executables[architecture] = target
        if tui_artifact.source_sha256(snapshot) != expected_hash:
            raise BuildError("Go 修改了依赖锁定文件；请先更新并检查 go.mod/go.sum，再重新构建。")
        # macOS-only smoke checks never call an installation action.
        host_arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}.get(platform.machine())
        if sys.platform == "darwin" and host_arch in executables:
            for option in ("--help", "--version"):
                subprocess.run([str(executables[host_arch]), option], env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=True, timeout=30)
        metadata = {"go_version": details["GOVERSION"], "cgo_enabled": False, "goos": "darwin",
                    "source_normalization": "relative UTF-8 path + NUL + UTF-8 without BOM, LF content + NUL; sorted paths",
                    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "modules": [{"path": item["Path"], "version": item["Version"]} for item in modules]}
        return publish_bundle(output, executables, SOURCE, expected_hash, metadata, notices)


def main(argv=None):
    parser = argparse.ArgumentParser(description="用已有 Go 工具链隔离构建双架构 macOS TUI（不会安装工具链）")
    parser.add_argument("--go", type=Path, help="已有 Go 可执行文件路径；默认使用 PATH 中的 Go")
    parser.add_argument("--output", type=Path, default=ROOT / "resources/tui", help="构建产物目录")
    parser.add_argument("--verify-only", action="store_true", help="只核验双架构产物、源码和许可；无需 Go，支持 Windows/Linux")
    args = parser.parse_args(argv)
    try:
        manifest = verify_bundle(args.output) if args.verify_only else build(args.output, args.go)
    except (BuildError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("TUI 构建/校验失败：%s" % error, file=sys.stderr)
        details = getattr(error, "stderr", None)
        if details:
            print(details.decode("utf-8", errors="replace") if isinstance(details, bytes) else details,
                  file=sys.stderr)
        return 1
    print("%s：%s\n源码 SHA-256: %s" % (
        "校验通过" if args.verify_only else "构建完成", args.output, manifest["source_sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
