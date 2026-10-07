"""Node/nvm 安装与共享前端配置：隔离 HOME、小型固定哈希归档，不联网。"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NVM = r'''nvm() {
  case "$1" in
    --version) echo 0.40.8 ;;
    use)
      shift; [ "${1-}" != --silent ] || shift
      local version="$1"
      [ "$version" != default ] || version="$(cat "$NVM_DIR/alias/default")"
      [ -x "$NVM_DIR/versions/node/$version/bin/node" ] || return 3
      export PATH="$NVM_DIR/versions/node/$version/bin:$PATH" ;;
    ls) [ -x "$NVM_DIR/versions/node/$2/bin/node" ] || return 3; echo "$2" ;;
    alias) mkdir -p "$NVM_DIR/alias"; printf '%s\n' "$3" > "$NVM_DIR/alias/$2" ;;
    *) return 12 ;;
  esac
}
if [ "${1-}" != --no-use ] && [ -f "$NVM_DIR/alias/default" ]; then nvm use --silent default; fi
'''


class NodeInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Node 安装's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        shutil.copy2(ROOT / "tools/prepare-resources.sh", self.support / "scripts/prepare-resources.sh")
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.web = self.base / "web/resources"
        self.web.mkdir(parents=True)
        self.catalog = self.support / "config/resources.tsv"
        self.rows = []
        self.calls = self.base / "calls"
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "LC_ALL": "C.UTF-8", "SERVER_ADDR": "team.invalid:8080", "WEB": str(self.base / "web"),
                    "CALLS": str(self.calls), "MACHINE": "x86_64", "ROSETTA": "true"}
        self.executable(self.bin / "uname", '#!/bin/sh\nif [ "$1" = -m ]; then echo "$MACHINE"; else echo Darwin; fi\n')
        self.executable(self.bin / "sysctl", '#!/bin/sh\n[ "$MACHINE" = arm64 ] && echo 1 || echo 0\n')
        self.executable(self.bin / "arch", '#!/bin/sh\necho rosetta >> "$CALLS"\n[ "$ROSETTA" = true ]\n')
        self.executable(self.bin / "curl", r'''#!/bin/bash
printf '%s\n' "$*" >> "$CALLS"
while [ "$#" -gt 0 ]; do
  case "$1" in --output) output="$2"; shift 2 ;; http://*) url="$1"; shift ;; *) shift ;; esac
done
relative="${url#*://}"; relative="${relative#*/}"
cp "$WEB/$relative" "$output"
''')
        self.add_archive("nvm", "0.40.8", "any", "frontend/nvm/nvm.tar.gz",
                         [("nvm-0.40.8/nvm.sh", NVM, 0o644),
                          ("nvm-0.40.8/nvm-exec", "#!/bin/sh\nexec \"$@\"\n", 0o755),
                          ("nvm-0.40.8/bash_completion", "# completion\n", 0o644)])
        for version, arches in (("14.21.3", ("x64",)), ("16.20.2", ("x64", "arm64")), ("18.20.8", ("x64", "arm64"))):
            for arch in arches:
                self.node_archive(version, arch)
        self.write_catalog()

    @staticmethod
    def executable(path, body):
        path.write_text(body)
        path.chmod(0o755)

    def add_archive(self, identifier, version, arch, relative, entries, symlink=None):
        archive = self.web / relative
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as tar:
            for name, body, mode in entries:
                data = body.encode()
                info = tarfile.TarInfo(name)
                info.mode, info.size = mode, len(data)
                tar.addfile(info, io.BytesIO(data))
            if symlink:
                info = tarfile.TarInfo(symlink[0])
                info.type, info.linkname = tarfile.SYMTYPE, symlink[1]
                tar.addfile(info)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.rows = [row for row in self.rows if row[0] != identifier]
        self.rows.append([identifier, "runtime", version, arch, relative,
                          "https://never-public.invalid/archive", digest])

    def node_archive(self, version, arch, actual=None, unsafe=False):
        prefix = f"node-v{version}-darwin-{arch}"
        actual = actual or version
        self.add_archive(f"node{version.split('.')[0]}-macos-{arch}", version, arch,
                         f"frontend/node/{prefix}.tar.gz",
                         [(f"{prefix}/bin/node", f'#!/bin/sh\necho node-{version}-{arch} >> "$CALLS"\necho v{actual}\n', 0o755),
                          (f"{prefix}/lib/node_modules/npm/bin/npm-cli.js", "#!/bin/sh\necho 9.0.0\n", 0o755)],
                         (f"{prefix}/bin/npm", "../../../../outside" if unsafe else "../lib/node_modules/npm/bin/npm-cli.js"))

    def write_catalog(self):
        self.catalog.write_text("\n".join("\t".join(row) for row in self.rows) + "\n")

    def run_script(self, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/install-node.sh"), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=25)

    def helper(self, command, *args, extra=None):
        return subprocess.run(["/bin/bash", "-euc", 'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/frontend.sh"; shift; ' + command,
                               "helper", str(self.support), *args], cwd=self.base,
                              env={**self.env, **(extra or {})}, text=True, capture_output=True, timeout=25)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dry_run_reports_native_and_rosetta_plan_without_any_write_or_sdk(self):
        result = self.run_script("--dry-run", extra={"MACHINE": "arm64"})
        self.assert_ok(result)
        self.assertIn("node-v14.21.3-darwin-x64", result.stdout)
        self.assertIn("node-v16.20.2-darwin-arm64", result.stdout)
        self.assertIn("Rosetta", result.stdout)
        self.assertFalse(self.calls.exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_dry_run_does_not_load_existing_nvm_or_node(self):
        target = self.home / ".nvm"
        target.mkdir()
        (target / "nvm.sh").write_text('echo loaded >> "$CALLS"\nexit 91\n')
        self.assert_ok(self.run_script("--version", "18", "--dry-run"))
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_cached_resource_is_rechecked_and_bad_bytes_are_preserved(self):
        first = self.helper('frontend_fetch_resource nvm; printf "FILE:%s\\n" "$FR_FILE"')
        self.assert_ok(first)
        cached = self.home / "Library/Caches/team-frontend-env/resources/frontend/nvm/nvm.tar.gz"
        cached.write_bytes(b"changed archive")
        result = self.helper('frontend_fetch_resource nvm')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)
        self.assertEqual(cached.read_bytes(), b"changed archive")

    def test_fresh_all_installs_versions_default18_and_keeps_java_profile(self):
        profile = self.home / ".zshrc"
        original = "export JAVA_HOME='/a/jdk'\n# >>> team-java-env managed >>>\nexport JAVA_8_HOME='/a/jdk'\n# <<< team-java-env managed <<<\n"
        profile.write_text(original)
        self.assert_ok(self.run_script())
        self.assertIn(original, profile.read_text())
        self.assertEqual((self.home / ".nvm/alias/default").read_text().strip(), "v18.20.8")
        for version in ("14.21.3", "16.20.2", "18.20.8"):
            root = self.home / f".nvm/versions/node/v{version}"
            self.assertTrue((root / "bin/node").is_file())
            self.assertEqual(json.loads((root / ".team-frontend-env-install.json").read_text())["tool"], "team-frontend-env")
        self.assertFalse(list(self.home.rglob(".team-java-env-install.json")))
        for shell in ("/bin/bash", "/bin/zsh"):
            if not Path(shell).exists():
                continue
            result = subprocess.run([shell, "-f", "-c", '. "$HOME/.zshrc"; node --version; printf "%s\\n" "$JAVA_HOME"'],
                                    env=self.env, capture_output=True, text=True)
            self.assert_ok(result)
            self.assertEqual(result.stdout.splitlines(), ["v18.20.8", "/a/jdk"])
        before = profile.stat().st_mtime_ns
        self.assert_ok(self.run_script())
        self.assertEqual(before, profile.stat().st_mtime_ns)
        self.assertTrue(any(self.home.glob(".zshrc*.bak*")))

    def test_arm_all_checks_rosetta_before_install_and_uses_native_16_18(self):
        result = self.run_script(extra={"MACHINE": "arm64", "ROSETTA": "false"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Rosetta", result.stderr)
        self.assertFalse((self.home / ".nvm").exists())
        self.assertEqual(self.calls.read_text(), "rosetta\n")
        self.assert_ok(self.run_script(extra={"MACHINE": "arm64"}))
        logs = self.calls.read_text()
        for expected in ("node-14.21.3-x64", "node-16.20.2-arm64", "node-18.20.8-arm64"):
            self.assertIn(expected, logs)

    def test_single_native18_does_not_require_rosetta(self):
        self.assert_ok(self.run_script("--version", "18", extra={"MACHINE": "arm64", "ROSETTA": "false"}))
        self.assertNotIn("rosetta", self.calls.read_text())
        self.assertFalse((self.home / ".nvm/versions/node/v14.21.3").exists())

    def test_bad_hash_prevents_every_install_and_profile_write(self):
        self.rows[-1][-1] = "0" * 64
        self.write_catalog()
        result = self.run_script(extra={"MACHINE": "arm64"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)
        self.assertFalse((self.home / ".nvm").exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_wrong_node_version_prevents_publish(self):
        self.node_archive("18.20.8", "x64", actual="20.0.0")
        self.write_catalog()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("版本", result.stderr)
        self.assertFalse((self.home / ".nvm").exists())

    def test_unknown_existing_nvm_is_preserved(self):
        root = self.home / ".nvm"
        root.mkdir()
        (root / "keep").write_text("mine")
        result = self.run_script("--version", "18")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((root / "keep").read_text(), "mine")
        self.assertFalse((root / "nvm.sh").exists())
        self.assertFalse(self.calls.exists())

    def test_external_nvm_and_default_are_reused_without_claiming_ownership(self):
        root = self.home / ".nvm"
        (root / "alias").mkdir(parents=True)
        (root / "nvm.sh").write_text(NVM.replace("0.40.8", "0.39.7"))
        (root / "alias/default").write_text("system\n")
        before = (root / "nvm.sh").read_bytes()
        self.assert_ok(self.run_script())
        self.assertEqual(before, (root / "nvm.sh").read_bytes())
        self.assertEqual((root / "alias/default").read_text(), "system\n")
        self.assertFalse((root / ".team-frontend-env-install.json").exists())
        self.assert_ok(self.run_script("--version", "16"))
        self.assertEqual((root / "alias/default").read_text().strip(), "v16.20.2")

    def test_existing_wrong_version_and_symlink_directory_are_preserved(self):
        self.assert_ok(self.run_script("--version", "18"))
        target = self.home / ".nvm/versions/node/v18.20.8"
        self.executable(target / "bin/node", '#!/bin/sh\necho v18.0.0\n')
        result = self.run_script("--version", "18")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("v18.0.0", (target / "bin/node").read_text())
        shutil.rmtree(target)
        outside = self.base / "outside"
        outside.mkdir()
        target.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_script("--version", "18").returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unsafe_archive_link_cannot_escape_target(self):
        self.node_archive("18.20.8", "x64", unsafe=True)
        self.write_catalog()
        result = self.run_script("--version", "18")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".nvm").exists())

    def test_missing_or_unpinned_catalog_entry_refuses_network(self):
        self.rows = [row for row in self.rows if row[0] != "node18-macos-x64"]
        self.write_catalog()
        result = self.run_script("--version", "18")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())
        self.node_archive("18.20.8", "x64")
        self.rows[-1][-1] = "-"
        self.write_catalog()
        self.assertNotEqual(self.run_script("--version", "18").returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_help_bad_arguments_and_install_lock(self):
        self.assert_ok(self.run_script("--help"))
        for args in (("--version",), ("--version", "20"), ("--version", "--dry-run"), ("--wat",)):
            self.assertNotEqual(self.run_script(*args).returncode, 0)
        lock = self.home / ".nvm.team-frontend.lock"
        lock.mkdir()
        self.assertNotEqual(self.run_script("--version", "18").returncode, 0)
        self.assertTrue(lock.is_dir())
        self.assertFalse(self.calls.exists())

    def test_shared_resource_reader_supports_all_groups_and_rejects_duplicate_id(self):
        for group in ("runtime", "software", "plugins"):
            self.rows[0][1] = group
            self.write_catalog()
            result = self.helper('frontend_read_resource nvm; printf "VALUE:%s|%s|%s\\n" "$FR_ID" "$FR_VERSION" "$FR_URL"')
            self.assert_ok(result)
            self.assertIn("VALUE:nvm|0.40.8|http://team.invalid:8080/resources/frontend/nvm/nvm.tar.gz", result.stdout)
        self.rows.append(self.rows[0][:])
        self.write_catalog()
        self.assertNotEqual(self.helper('frontend_read_resource nvm').returncode, 0)

    def test_profile_helper_keeps_other_blocks_and_refuses_malformed_or_symlink(self):
        profile = self.home / ".zshrc"
        initial = "# >>> team-java-env managed >>>\nexport JAVA_HOME=/keep\n# <<< team-java-env managed <<<\n"
        profile.write_text(initial)
        self.assert_ok(self.helper('frontend_update_zsh_block nvm "$1"', "export NVM_DIR='/a b'"))
        self.assert_ok(self.helper('frontend_update_zsh_block terminal "$1"', "export ZSH='/another'"))
        self.assertIn(initial, profile.read_text())
        before = profile.read_bytes(), profile.stat().st_mtime_ns
        self.assert_ok(self.helper('frontend_update_zsh_block nvm "$1"', "export NVM_DIR='/a b'"))
        self.assertEqual(before, (profile.read_bytes(), profile.stat().st_mtime_ns))
        profile.write_text(profile.read_text() + "# >>> team-frontend-env nvm >>>\n")
        broken = profile.read_bytes()
        self.assertNotEqual(self.helper('frontend_update_zsh_block nvm hi').returncode, 0)
        self.assertEqual(profile.read_bytes(), broken)
        profile.unlink()
        outside = self.base / "outside-profile"
        outside.write_text("keep")
        profile.symlink_to(outside)
        self.assertNotEqual(self.helper('frontend_update_zsh_block nvm hi').returncode, 0)
        self.assertEqual(outside.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
