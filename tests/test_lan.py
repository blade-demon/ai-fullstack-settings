"""Local IPv4 discovery, with operating-system commands replaced at the boundary."""
import json
import subprocess
import unittest
from unittest import mock

from server import lan


class DiscoveryTests(unittest.TestCase):
    def discover(self, system, output):
        result = subprocess.CompletedProcess([], 0, output, "")
        with mock.patch.object(lan.platform, "system", return_value=system):
            with mock.patch.object(lan.subprocess, "run", return_value=result) as run:
                addresses = lan.discover_ipv4_addresses()
        command, = run.call_args.args
        self.assertIsInstance(command, list)
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertGreater(run.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 30)
        return addresses

    def test_macos_collects_all_active_interfaces_and_sorts_and_deduplicates(self):
        output = """en0: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
    inet 192.168.1.10 netmask 0xffffff00 broadcast 192.168.1.255
    inet 192.168.1.2 netmask 0xffffff00 broadcast 192.168.1.255
    status: active
en1: flags=8863<UP,BROADCAST> mtu 1500
    inet 10.0.0.3 netmask 0xffffff00 broadcast 10.0.0.255
    status: active
utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1500
    inet 172.16.0.2 --> 172.16.0.1 netmask 0xffffffff
en2: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
    inet 192.168.1.2 netmask 0xffffff00 broadcast 192.168.1.255
"""
        self.assertEqual(self.discover("Darwin", output),
                         ["10.0.0.3", "172.16.0.2", "192.168.1.2", "192.168.1.10"])

    def test_macos_excludes_inactive_down_and_nonrunning_interfaces(self):
        output = """en0: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
    inet 192.168.1.2 netmask 0xffffff00
    status: inactive
en1: flags=8863<BROADCAST,RUNNING> mtu 1500
    inet 192.168.1.3 netmask 0xffffff00
    status: active
en2: flags=8863<UP,BROADCAST> mtu 1500
    inet 192.168.1.4 netmask 0xffffff00
"""
        self.assertEqual(self.discover("Darwin", output), [])

    def test_macos_filters_nonshareable_and_directed_broadcast_addresses(self):
        output = "en0: flags=8863<UP,BROADCAST,RUNNING> mtu 1500\n"
        for address in ("127.0.0.1", "0.0.0.0", "169.254.1.2", "224.0.0.1",
                        "240.0.0.1", "255.255.255.255", "192.168.1.255",
                        "192.168.1.0", "10.0.0.2"):
            output += "    inet %s netmask 0xffffff00\n" % address
        self.assertEqual(self.discover("Darwin", output), ["10.0.0.2"])

    def test_macos_preserves_hosts_on_point_to_point_and_host_routes(self):
        output = """utun0: flags=8051<UP,POINTOPOINT,RUNNING> mtu 1500
    inet 10.0.0.0 --> 10.0.0.1 netmask 0xfffffffe
    inet 10.0.0.1 --> 10.0.0.0 netmask 0xfffffffe
    inet 10.0.0.2 --> 10.0.0.2 netmask 0xffffffff
"""
        self.assertEqual(self.discover("Darwin", output),
                         ["10.0.0.0", "10.0.0.1", "10.0.0.2"])

    def test_macos_without_ipv4_returns_empty_list(self):
        self.assertEqual(self.discover("Darwin", """lo0: flags=8049<UP,LOOPBACK,RUNNING> mtu 16384
    inet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
    inet6 fe80::1%en0 prefixlen 64 scopeid 0x4
    status: active
"""), [])

    def test_macos_rejects_unparseable_output_and_invalid_ipv4_records(self):
        invalid_outputs = ["", "unrecognized command output", "{\"Addresses\": []}",
                           "en0: flags=8863<UP,RUNNING> mtu 1500\n    inet garbage netmask 0xffffff00",
                           "en0: flags=8863<UP,RUNNING> mtu 1500\n    inet 10.0.0.2",
                           "en0: flags=8863<UP,RUNNING> mtu 1500\n    inet 10.0.0.2 netmask 0xff00ff00"]
        for output in invalid_outputs:
            with self.subTest(output=output), self.assertRaises(lan.DiscoveryError):
                self.discover("Darwin", output)

    def windows_output(self, addresses=None, adapters=None):
        if adapters is None:
            adapters = [{"InterfaceIndex": 4, "Status": "Up"},
                        {"InterfaceIndex": 8, "Status": "Disconnected"},
                        {"InterfaceIndex": 12, "Status": "Up"}]
        return json.dumps({"Adapters": adapters, "Addresses": addresses or []})

    def windows_address(self, address, index=4, state="Preferred", skip=False, prefix=24):
        return {"IPAddress": address, "InterfaceIndex": index, "AddressState": state,
                "SkipAsSource": skip, "PrefixLength": prefix}

    def test_windows_collects_all_active_preferred_source_addresses(self):
        output = self.windows_output([
            self.windows_address("192.168.1.10"),
            self.windows_address("192.168.1.2"),
            self.windows_address("10.0.0.3", index=12),
            self.windows_address("192.168.1.2", index=12),
            self.windows_address("10.0.0.4", index=8),
            self.windows_address("10.0.0.5", index=999),
            self.windows_address("10.0.0.6", state="Tentative"),
            self.windows_address("10.0.0.7", state="Deprecated"),
            self.windows_address("10.0.0.8", skip=True),
        ])
        self.assertEqual(self.discover("Windows", output),
                         ["10.0.0.3", "192.168.1.2", "192.168.1.10"])

    def test_windows_filters_nonshareable_addresses_and_subnet_broadcast(self):
        addresses = [self.windows_address(address) for address in
                     ("127.0.0.1", "0.0.0.0", "169.254.1.2", "224.0.0.1",
                      "240.0.0.1", "255.255.255.255", "192.168.1.255", "10.0.0.2")]
        self.assertEqual(self.discover("Windows", self.windows_output(addresses)),
                         ["10.0.0.2"])

    def test_windows_without_ipv4_or_adapters_returns_empty_list(self):
        self.assertEqual(self.discover("Windows", self.windows_output()), [])
        self.assertEqual(self.discover("Windows", self.windows_output(adapters=[])), [])

    def test_windows_rejects_invalid_json_shapes_and_missing_fields(self):
        outputs = ["", "not JSON", "null", "[]", "{}",
                   '{"Adapters": [], "Addresses": null}',
                   self.windows_output(adapters=[{"Status": "Up"}]),
                   self.windows_output(addresses=[{"IPAddress": "10.0.0.2"}])]
        for output in outputs:
            with self.subTest(output=output), self.assertRaises(lan.DiscoveryError):
                self.discover("Windows", output)

    def test_windows_rejects_invalid_address_prefix_and_status_types(self):
        invalid_addresses = [self.windows_address("not-an-ip"),
                             self.windows_address("10.0.0.2", prefix=33),
                             self.windows_address("10.0.0.2", prefix="24"),
                             self.windows_address("10.0.0.2", skip="False"),
                             self.windows_address("10.0.0.2", state=4)]
        for address in invalid_addresses:
            with self.subTest(address=address), self.assertRaises(lan.DiscoveryError):
                self.discover("Windows", self.windows_output([address]))

    def test_windows_accepts_utf8_bom_from_powershell(self):
        output = "\ufeff" + self.windows_output([self.windows_address("10.0.0.2")])
        self.assertEqual(self.discover("Windows", output), ["10.0.0.2"])

    def test_command_failure_has_actionable_chinese_error(self):
        failures = [FileNotFoundError("not installed"), PermissionError("denied"),
                    subprocess.TimeoutExpired(["ifconfig"], 10),
                    subprocess.CalledProcessError(1, ["ifconfig"], stderr="unavailable")]
        for system in ("Darwin", "Windows"):
            for failure in failures:
                with self.subTest(system=system, failure=failure):
                    with mock.patch.object(lan.platform, "system", return_value=system):
                        with mock.patch.object(lan.subprocess, "run", side_effect=failure):
                            with self.assertRaisesRegex(lan.DiscoveryError, "IPv4"):
                                lan.discover_ipv4_addresses()

    def test_unknown_platform_reports_manual_selection_is_needed(self):
        with mock.patch.object(lan.platform, "system", return_value="UnknownOS"):
            with self.assertRaisesRegex(lan.DiscoveryError, "手动"):
                lan.discover_ipv4_addresses()


if __name__ == "__main__":
    unittest.main()
