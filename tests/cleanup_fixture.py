"""Tiny, non-executable universal Mach-O fixture for distribution tests."""
import hashlib
import json
import struct


def cleanup_fixture(repo):
    folder = repo / "resources/cleanup"
    folder.mkdir(parents=True, exist_ok=True)
    cpus = (0x0100000C, 0x01000007)
    slices = [struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0) for cpu in cpus]
    binary = struct.pack(">II", 0xCAFEBABE, 2)
    for index, cpu in enumerate(cpus):
        binary += struct.pack(">5I", cpu, 0, 48 + index * 32, 32, 2)
    binary += b"".join(slices) + b"fixture\x00\r\n"
    (folder / "cleanup-macos-universal2").write_bytes(binary)
    source = (repo / "tools/uninstall_java_gradle.py").read_bytes()
    source = source.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    manifest = {"schema": 1, "sha256": hashlib.sha256(binary).hexdigest(),
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "architectures": ["arm64", "x86_64"]}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "THIRD_PARTY_NOTICES.txt").write_text("Fixture license\n", encoding="utf-8")
    return folder
