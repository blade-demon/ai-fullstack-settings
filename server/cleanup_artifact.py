"""Validate the prebuilt macOS cleanup runtime without executing host commands."""
import hashlib
import json
import re
import struct


CPU_NAMES = {0x0100000C: "arm64", 0x01000007: "x86_64"}
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")


def macho_architectures(payload):
    formats = {b"\xca\xfe\xba\xbe": (">", "5I"),
               b"\xbe\xba\xfe\xca": ("<", "5I"),
               b"\xca\xfe\xba\xbf": (">", "IIQQII"),
               b"\xbf\xba\xfe\xca": ("<", "IIQQII")}
    if len(payload) < 8 or payload[:4] not in formats:
        raise ValueError("卸载运行时不是 universal2 Mach-O 文件。")
    endian, layout = formats[payload[:4]]
    count = struct.unpack_from(endian + "I", payload, 4)[0]
    size = struct.calcsize(endian + layout)
    header_end = 8 + count * size
    if count != 2 or header_end > len(payload):
        raise ValueError("卸载运行时的 Mach-O 架构表无效。")
    architectures, occupied = set(), []
    for index in range(count):
        cpu, subtype, offset, length, alignment = struct.unpack_from(
            endian + layout, payload, 8 + index * size)[:5]
        name = CPU_NAMES.get(cpu)
        if (name is None or name in architectures or offset < header_end or length < 32
                or offset + length > len(payload) or alignment > 31
                or offset % (1 << alignment)
                or any(offset < end and start < offset + length for start, end in occupied)):
            raise ValueError("卸载运行时的 Mach-O 架构或分片范围无效。")
        magic = payload[offset:offset + 4]
        thin_endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(magic)
        if thin_endian is None or struct.unpack_from(thin_endian + "I", payload, offset + 4)[0] != cpu:
            raise ValueError("卸载运行时的 Mach-O 分片与架构表不一致。")
        occupied.append((offset, offset + length))
        architectures.add(name)
    return architectures


def validate_cleanup_artifact(binary, manifest_bytes, source_bytes):
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise ValueError("卸载运行时 manifest.json 格式无效。") from error
    if (not isinstance(manifest, dict) or type(manifest.get("schema")) is not int
            or manifest["schema"] != 1):
        raise ValueError("卸载运行时清单版本无效。")
    for key in ("sha256", "source_sha256"):
        if not isinstance(manifest.get(key), str) or not SHA256.fullmatch(manifest[key]):
            raise ValueError("卸载运行时清单缺少有效的 %s。" % key)
    architectures = manifest.get("architectures")
    if (not isinstance(architectures, list) or len(architectures) != 2
            or any(not isinstance(name, str) for name in architectures)
            or set(architectures) != {"arm64", "x86_64"}):
        raise ValueError("卸载运行时清单必须包含 arm64 和 x86_64。")
    if hashlib.sha256(binary).hexdigest() != manifest["sha256"].lower():
        raise ValueError("卸载运行时 SHA-256 校验失败。")
    # Git checkouts on Windows may use CRLF; builders use the same canonical source bytes.
    source = source_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if hashlib.sha256(source).hexdigest() != manifest["source_sha256"].lower():
        raise ValueError("卸载运行时已过期，与当前卸载源码不一致。")
    if macho_architectures(binary) != set(architectures):
        raise ValueError("卸载运行时实际架构与清单不一致。")
