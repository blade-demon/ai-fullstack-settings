"""Go artifact validation and rollback contracts; no real installer is executed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from server import tui_artifact

try:
    from .tui_fixture import tui_fixture, thin_fixture
except ImportError:
    from tui_fixture import tui_fixture, thin_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build-tui.py"


class TuiBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.is_file():
            spec = importlib.util.spec_from_file_location("tui_build", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "缺少 Go TUI 构建入口")
        self.temp = tempfile.TemporaryDirectory(prefix="tui build ' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = tui_fixture(self.base)
        self.source = self.base / "tui"
        self.manifest = json.loads((self.output / "manifest.json").read_text())

    def test_source_hash_canonicalizes_lf_bom_and_includes_paths_and_tests(self):
        files = {"go.mod": b"module fixture\n\ngo 1.25.0\n", "go.sum": b"",
                 "main.go": b"package main\nfunc main() {}\n"}
        expected = hashlib.sha256(b"".join(name.encode() + b"\0" + files[name] + b"\0"
                                           for name in ("go.mod", "go.sum", "main.go"))).hexdigest()
        self.assertEqual(tui_artifact.source_sha256(self.source), expected)
        for path in self.source.iterdir():
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(tui_artifact.source_sha256(self.source), expected)
        test = self.source / "nested/runner_test.go"
        test.parent.mkdir()
        test.write_text("package nested\n")
        self.assertNotEqual(tui_artifact.source_sha256(self.source), expected)
        first = tui_artifact.source_sha256(self.source)
        test.rename(test.with_name("new_test.go"))
        self.assertNotEqual(tui_artifact.source_sha256(self.source), first)

    def test_valid_bundle_does_not_execute_a_binary_or_toolchain(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("must not execute")):
            self.assertEqual(self.module.verify_bundle(self.output, self.source), self.manifest)

    def test_rejects_fat_wrong_cpu_wrong_type_and_truncated_command_table(self):
        binary = self.output / "team-dev-env-arm64"
        fixtures = [b"\xca\xfe\xba\xbe" + b"\0" * 36,
                    thin_fixture("amd64"),
                    struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 6, 0, 0, 0, 0),
                    struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 1, 500, 0, 0)]
        for payload in fixtures:
            with self.subTest(payload=payload):
                binary.write_bytes(payload)
                self.manifest["binaries"]["arm64"]["sha256"] = hashlib.sha256(payload).hexdigest()
                (self.output / "manifest.json").write_text(json.dumps(self.manifest))
                with self.assertRaisesRegex(self.module.BuildError, "Mach-O"):
                    self.module.verify_bundle(self.output, self.source)

    def test_source_symlink_is_rejected(self):
        outside = self.base / "external.go"
        outside.write_text("package outside\n")
        (self.source / "linked.go").symlink_to(outside)
        with self.assertRaisesRegex(self.module.BuildError, "符号链接"):
            self.module.verify_bundle(self.output, self.source)

    def candidates(self):
        paths = {}
        for arch in ("arm64", "amd64"):
            paths[arch] = self.base / ("new-" + arch)
            paths[arch].write_bytes(thin_fixture(arch, b"new release"))
        return paths

    def test_publish_rolls_back_each_partial_failure_preserving_unknown_files_and_modes(self):
        unknown = self.output / "user-data/note.txt"
        unknown.parent.mkdir()
        unknown.write_text("keep")
        for name in tui_artifact.FILES:
            (self.output / name).chmod(0o640)
        before = {p.relative_to(self.output): (p.read_bytes(), p.stat().st_mode)
                  for p in self.output.rglob("*") if p.is_file()}
        candidates = self.candidates()
        for fail_at in (2, 3, 4):
            with self.subTest(fail_at=fail_at):
                replace, calls = self.module.os.replace, 0

                def fail_once(source, destination):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("injected publication failure")
                    return replace(source, destination)

                with mock.patch.object(self.module.os, "replace", side_effect=fail_once):
                    with self.assertRaisesRegex(OSError, "injected publication failure"):
                        self.module.publish_bundle(self.output, candidates, self.source,
                                                   self.manifest["source_sha256"], {}, "new notices\n")
                self.assertEqual({p.relative_to(self.output): (p.read_bytes(), p.stat().st_mode)
                                  for p in self.output.rglob("*") if p.is_file()}, before)
                self.module.verify_bundle(self.output, self.source)

    def test_failed_rollback_keeps_full_previous_bundle_for_recovery(self):
        replace, calls = self.module.os.replace, 0

        def fail_from_second(source, destination):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise OSError("persistent write failure")
            return replace(source, destination)

        with mock.patch.object(self.module.os, "replace", side_effect=fail_from_second):
            with self.assertRaisesRegex(self.module.BuildError, "回滚.*保留"):
                self.module.publish_bundle(self.output, self.candidates(), self.source,
                                           self.manifest["source_sha256"], {}, "new notices\n")
        recovery = list(self.output.parent.glob(".tui-publish-*/previous"))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(self.module.verify_bundle(recovery[0], self.source), self.manifest)

    def test_source_change_before_publish_preserves_old_bundle(self):
        before = (self.output / "manifest.json").read_bytes()
        (self.source / "main.go").write_text("package main\n// concurrent edit\n")
        with self.assertRaisesRegex(self.module.BuildError, "源码"):
            self.module.publish_bundle(self.output, self.candidates(), self.source,
                                       self.manifest["source_sha256"], {}, "notice\n")
        self.assertEqual((self.output / "manifest.json").read_bytes(), before)

    def test_publish_sets_archive_modes_and_keeps_unmanaged_content(self):
        (self.output / "notes.txt").write_text("keep")
        self.module.publish_bundle(self.output, self.candidates(), self.source,
                                   self.manifest["source_sha256"], {}, "license text\n")
        self.module.verify_bundle(self.output, self.source)
        for name in tui_artifact.FILES:
            self.assertEqual((self.output / name).stat().st_mode & 0o777,
                             0o755 if name.startswith("team-dev-env-") else 0o644)
        self.assertEqual((self.output / "notes.txt").read_text(), "keep")

    def test_notices_include_full_go_and_module_licenses_with_sources(self):
        goroot = self.base / "go"
        goroot.mkdir()
        (goroot / "LICENSE").write_text("GO COMPLETE LICENSE\n")
        module = self.base / "modules/example"
        (module / "subdir").mkdir(parents=True)
        (module / "LICENSE").write_text("MODULE COMPLETE LICENSE\n")
        (module / "subdir/LICENSE-MIT").write_text("EMBEDDED COMPLETE LICENSE\n")
        modules = [{"Path": "example.org/library/v2", "Version": "v2.3.4", "Dir": str(module)}]
        notices = self.module.collect_notices(goroot, "go1.27.1", modules)
        for text in ("GO COMPLETE LICENSE", "MODULE COMPLETE LICENSE", "EMBEDDED COMPLETE LICENSE",
                     "go1.27.1", "example.org/library/v2", "v2.3.4", "subdir/LICENSE-MIT", "Source:"):
            self.assertIn(text, notices)

    def test_missing_module_license_prevents_publication(self):
        goroot = self.base / "go"
        goroot.mkdir()
        (goroot / "LICENSE").write_text("Go license\n")
        dependency = self.base / "dependency"
        dependency.mkdir()
        with self.assertRaisesRegex(self.module.BuildError, "许可"):
            self.module.collect_notices(goroot, "go1.27.1", [
                {"Path": "example.org/module", "Version": "v1.0.0", "Dir": str(dependency)}])

    def test_isolated_build_environment_disables_cgo_auto_toolchains_and_user_go_config(self):
        with mock.patch.dict(self.module.os.environ, {"GOFLAGS": "-race", "GOROOT": "/untrusted",
                                                      "GOTOOLCHAIN": "auto", "GOWORK": "/user/work",
                                                      "GO111MODULE": "off", "GOCACHEPROG": "/user/cache"}):
            env = self.module.build_environment(self.base)
        self.assertEqual(env["CGO_ENABLED"], "0")
        self.assertEqual(env["GOTOOLCHAIN"], "local")
        self.assertEqual(env["GOENV"], "off")
        self.assertEqual(env["GOWORK"], "off")
        self.assertEqual(env["GO111MODULE"], "on")
        self.assertNotIn("GOCACHEPROG", env)
        self.assertNotIn("GOROOT", env)
        self.assertNotIn("-race", env["GOFLAGS"])
        for key in ("GOPATH", "GOMODCACHE", "GOCACHE", "HOME", "GOTMPDIR"):
            self.assertIn(self.base, Path(env[key]).parents, key)

    def test_cli_help_and_verify_only_do_not_need_go(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--go", result.stdout)
        with mock.patch.object(self.module, "SOURCE", self.source):
            self.assertEqual(self.module.main(["--output", str(self.output), "--verify-only"]), 0)

    def test_missing_go_fails_without_modifying_output(self):
        before = (self.output / "manifest.json").read_bytes()
        self.assertEqual(self.module.main(["--go", str(self.base / "not-installed"), "--output", str(self.output)]), 1)
        self.assertEqual((self.output / "manifest.json").read_bytes(), before)

    def test_build_uses_locked_modules_without_expanding_unrelated_dependency_graph(self):
        toolchain = self.base / "go-toolchain"
        toolchain.mkdir()
        go = toolchain / "go"
        go.touch()
        (toolchain / "LICENSE").write_text("complete Go license\n")
        dependency = self.base / "dependency"
        dependency.mkdir()
        (dependency / "LICENSE").write_text("complete locked module license\n")
        module = {"Path": "example.org/locked", "Version": "v1.0.0", "Dir": str(dependency)}

        def compiler(command, **kwargs):
            arguments = command[1:]
            source = Path(kwargs["cwd"])
            if arguments == ["env", "-json", "GOROOT", "GOVERSION"]:
                output = json.dumps({"GOROOT": str(toolchain), "GOVERSION": "go1.27.1"})
            elif arguments == ["mod", "download", "all"]:
                # Mirrors Go expanding unrelated packages' checksums under `all`.
                (source / "go.sum").write_text("unrelated graph checksum\n")
                output = ""
            elif arguments == ["mod", "download", "-json"]:
                output = json.dumps(module)
            elif arguments == ["list", "-m", "-json", "all"]:
                output = json.dumps(module)
            elif arguments == ["mod", "edit", "-json"]:
                output = json.dumps({"Require": [{"Path": module["Path"], "Version": module["Version"]}]})
            elif arguments[0] == "build":
                target = Path(arguments[arguments.index("-o") + 1])
                target.write_bytes(thin_fixture(kwargs["env"]["GOARCH"]))
                output = ""
            else:
                raise AssertionError("Unexpected compiler command: %r" % arguments)
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

        with mock.patch.object(self.module, "SOURCE", self.source), \
                mock.patch.object(self.module.subprocess, "run", side_effect=compiler), \
                mock.patch.object(self.module.platform, "machine", return_value="no-execution"):
            self.module.build(self.output, go)
        self.module.verify_bundle(self.output, self.source)
        self.assertIn("complete locked module license", (self.output / "THIRD_PARTY_NOTICES.txt").read_text())


if __name__ == "__main__":
    unittest.main()
