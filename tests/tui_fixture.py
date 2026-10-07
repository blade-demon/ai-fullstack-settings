"""Tiny non-executable Mach-O fixtures; no real build or install runs in packaging tests."""
import hashlib
import json
import struct


def thin_fixture(arch, tail=b"fixture\x00\r\n"):
    cpu = {"arm64": 0x0100000C, "amd64": 0x01000007}[arch]
    return struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0) + tail


def tui_fixture(repo):
    source = repo / "tui"
    source.mkdir(exist_ok=True)
    if not (source / "go.mod").exists():
        (source / "go.mod").write_bytes(b"module fixture\n\ngo 1.25.0\n")
        (source / "go.sum").write_bytes(b"")
        (source / "main.go").write_bytes(b"package main\nfunc main() {}\n")
    digest = hashlib.sha256()
    for path in sorted((p for p in source.rglob("*")
                        if p.suffix == ".go" or p.name in ("go.mod", "go.sum")),
                       key=lambda p: p.relative_to(source).as_posix()):
        digest.update(path.relative_to(source).as_posix().encode() + b"\0")
        digest.update(path.read_text(encoding="utf-8-sig").encode() + b"\0")
    folder = repo / "resources/tui"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "source_sha256": digest.hexdigest(), "binaries": {}}
    for arch in ("arm64", "amd64"):
        name = "team-dev-env-" + arch
        payload = thin_fixture(arch)
        (folder / name).write_bytes(payload)
        manifest["binaries"][arch] = {"file": name, "sha256": hashlib.sha256(payload).hexdigest()}
    notices = b"Go and module fixture licenses\n"
    (folder / "THIRD_PARTY_NOTICES.txt").write_bytes(notices)
    manifest["notices_sha256"] = hashlib.sha256(notices).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder
