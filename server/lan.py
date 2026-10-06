"""Discover local, active IPv4 addresses without network traffic (Python 3.8+)."""
import ipaddress
import json
import ntpath
import os
import platform
import re
import subprocess
from typing import List


class DiscoveryError(Exception):
    """Local network information could not be read reliably."""


def _run(command):
    try:
        result = subprocess.run(command, shell=False, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        raise DiscoveryError("自动检测 IPv4 失败：无法读取系统网卡信息，请手动指定内网 IPv4。") from error
    return result.stdout


def _address(value, mask):
    """Validate an address and discard values that cannot identify a unicast host."""
    if not isinstance(value, str):
        raise ValueError("IPv4 address must be text")
    address = ipaddress.IPv4Address(value)
    network = ipaddress.IPv4Network((address, mask), strict=False)
    if (address.is_loopback or address.is_unspecified or address.is_link_local
            or address.is_multicast or address.is_reserved
            or address in ipaddress.IPv4Network("0.0.0.0/8")):
        return None
    # /31 point-to-point links and /32 host routes have no broadcast host.
    if network.prefixlen < 31 and address in (network.network_address, network.broadcast_address):
        return None
    return str(address)


def _macos_addresses(output):
    interfaces = []
    current = None
    for line in output.splitlines():
        if not line.strip():
            continue
        header = re.match(r"^\S+:\s+flags=[0-9a-fA-F]+<([^>]*)>", line)
        if header:
            current = {"flags": set(header.group(1).split(",")), "lines": []}
            interfaces.append(current)
        elif current is None or not line[0].isspace():
            raise ValueError("unrecognized ifconfig output")
        else:
            current["lines"].append(line.strip())
    if not interfaces:
        raise ValueError("ifconfig did not return interfaces")

    addresses = []
    for interface in interfaces:
        flags, lines = interface["flags"], interface["lines"]
        statuses = [line.partition(":")[2].strip().lower()
                    for line in lines if line.startswith("status:")]
        if ("UP" not in flags or "LOOPBACK" in flags
                or (statuses and statuses != ["active"])
                or ("RUNNING" not in flags and statuses != ["active"])):
            continue
        for line in lines:
            fields = line.split()
            if fields[0] != "inet":
                continue
            if len(fields) < 4 or "netmask" not in fields:
                raise ValueError("missing IPv4 address or netmask")
            mask_position = fields.index("netmask") + 1
            if mask_position >= len(fields):
                raise ValueError("missing IPv4 netmask")
            mask = fields[mask_position]
            if mask.startswith("0x"):
                mask = str(ipaddress.IPv4Address(int(mask, 16)))
            address = _address(fields[1], mask)
            if address:
                addresses.append(address)
    return addresses


def _windows_addresses(output):
    data = json.loads(output.lstrip("\ufeff"))
    if (not isinstance(data, dict) or not isinstance(data.get("Adapters"), list)
            or not isinstance(data.get("Addresses"), list)):
        raise ValueError("unrecognized PowerShell network information")
    active = set()
    for adapter in data["Adapters"]:
        if (not isinstance(adapter, dict) or type(adapter.get("InterfaceIndex")) is not int
                or not isinstance(adapter.get("Status"), str)):
            raise ValueError("invalid adapter information")
        if adapter["Status"].lower() == "up":
            active.add(adapter["InterfaceIndex"])
    addresses = []
    for item in data["Addresses"]:
        if (not isinstance(item, dict) or type(item.get("InterfaceIndex")) is not int
                or not isinstance(item.get("AddressState"), str)
                or type(item.get("SkipAsSource")) is not bool
                or type(item.get("PrefixLength")) is not int
                or not 0 <= item["PrefixLength"] <= 32):
            raise ValueError("invalid IPv4 metadata")
        address = _address(item.get("IPAddress"), item["PrefixLength"])
        if (address and item["InterfaceIndex"] in active
                and item["AddressState"].lower() == "preferred" and not item["SkipAsSource"]):
            addresses.append(address)
    return addresses


def discover_ipv4_addresses() -> List[str]:
    """Return all active IPv4 hosts, numerically sorted and deduplicated.

    An empty list means the system reported no usable address. Command failures,
    malformed output, and unsupported systems raise DiscoveryError instead.
    Virtual adapters and VPNs are retained: the caller must select the LAN
    address when several networks are active. This does not test reachability.
    """
    system = platform.system()
    if system == "Darwin":
        output = _run(["/sbin/ifconfig"])
        parser = _macos_addresses
    elif system == "Windows":
        powershell = ntpath.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                 "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        # Arrays remain arrays for zero/one records. Convert enum values to text
        # explicitly because ConvertTo-Json otherwise serializes enum integers.
        script = (
            "$ErrorActionPreference = 'Stop'; "
            "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; "
            "$adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop | "
            "Select-Object InterfaceIndex,Status); "
            "$addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | "
            "Select-Object IPAddress,InterfaceIndex,PrefixLength,"
            "@{Name='AddressState';Expression={$_.AddressState.ToString()}},SkipAsSource); "
            "ConvertTo-Json -InputObject @{Adapters=$adapters;Addresses=$addresses} -Depth 4 -Compress"
        )
        output = _run([powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script])
        parser = _windows_addresses
    else:
        raise DiscoveryError("当前系统不支持自动检测 IPv4，请手动指定内网 IPv4。")
    try:
        return sorted(set(parser(output)), key=ipaddress.IPv4Address)
    except (ValueError, TypeError, KeyError) as error:
        raise DiscoveryError("自动检测 IPv4 失败：系统网卡信息格式无效，请手动指定内网 IPv4。") from error
