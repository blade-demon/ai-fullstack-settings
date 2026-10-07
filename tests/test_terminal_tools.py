"""终端工具集成：只操作临时 HOME、小型归档和签名/下载命令替身。"""
import hashlib
import io
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OMZ_VERSION = "60c9a7a839b790cd905d0fd4419435124fd1bdc0"


class TerminalToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="终端 tools' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / "工具/.support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        shutil.copy2(ROOT / "tools/prepare-resources.sh", self.support / "scripts/prepare-resources.sh")
        self.home = self.base / "Users/用户's home"
        self.home.mkdir(parents=True)
        self.web = self.base / "web"
        self.web.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.record = self.base / "loaded"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin:/usr/sbin:/sbin",
                    "SHELL": "/bin/zsh", "SERVER_ADDR": "fixture.invalid:8080", "SERVER_SCHEME": "http",
                    "FIXTURE_WEB": str(self.web), "LOADED": str(self.record), "LC_ALL": "C.UTF-8",
                    "USER": "other-login", "LOGNAME": "other-login"}
        self.stub("uname", '#!/bin/sh\ncase "$1" in -m) echo arm64;; *) echo Darwin;; esac\n')
        self.stub("sw_vers", '#!/bin/sh\necho "${MACOS_VERSION:-14.0}"\n')
        self.stub("codesign", '#!/bin/sh\nexit "${SIGNATURE_STATUS:-0}"\n')
        self.stub("git", '#!/bin/sh\n[ "${1-}" = --version ] || exit 91\nprintf "git version 2.48.0\\n"\n')
        self.stub("curl", r'''#!/bin/bash
output=''
while [ "$#" -gt 0 ]; do
  case "$1" in --output|-o) output="$2"; shift 2;; http*) url="$1"; shift;; *) shift;; esac
done
[ -n "$output" ] || exit 90
cp "$FIXTURE_WEB/${url##*/}" "$output"
''')
        self.rows = []
        self.iterm()
        self.framework()
        self.plugin("zsh-autosuggestions", "0.7.1")
        self.plugin("zsh-syntax-highlighting", "0.8.0")
        self.catalog()

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def register(self, resource, version, filename, arch="any"):
        archive = self.web / filename
        self.rows = [row for row in self.rows if row[0] != resource]
        relative = "frontend/iterm2/" + filename if resource == "iterm2" else "frontend/zsh/" + filename
        group = "software" if resource in ("iterm2", "oh-my-zsh") else "plugins"
        self.rows.append((resource, group, version, arch, relative,
                          "https://official.invalid/" + filename, hashlib.sha256(archive.read_bytes()).hexdigest()))

    def catalog(self):
        (self.support / "config/resources.tsv").write_text(
            "# id\tgroup\tversion\tarch\tpath\turl\tsha256\n" +
            "".join("\t".join(row) + "\n" for row in self.rows))

    def iterm(self, version="3.7.3", extra=None):
        plist = plistlib.dumps({"CFBundleIdentifier": "com.googlecode.iterm2",
                               "CFBundleShortVersionString": version, "CFBundleVersion": version,
                               "CFBundleExecutable": "iTerm2"})
        with zipfile.ZipFile(self.web / "iTerm2.zip", "w") as archive:
            for name, data, mode in [("iTerm.app/Contents/Info.plist", plist, 0o100644),
                                     ("iTerm.app/Contents/MacOS/iTerm2", b"#!/bin/sh\nexit 0\n", 0o100755)] + (extra or []):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
        self.register("iterm2", "3.7.3", "iTerm2.zip", "any")

    def tar(self, filename, root, files):
        with tarfile.open(self.web / filename, "w:gz") as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(root + "/" + name)
                encoded = data.encode()
                info.size = len(encoded)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(encoded))

    def framework(self):
        self.tar("oh-my-zsh.tar.gz", "ohmyzsh-" + OMZ_VERSION, {
            "oh-my-zsh.sh": '''omz() { :; }
print -r -- framework >> "$LOADED"
for p in $plugins; do
  if [[ -f "${ZSH_CUSTOM:-$ZSH/custom}/plugins/$p/$p.plugin.zsh" ]]; then
    source "${ZSH_CUSTOM:-$ZSH/custom}/plugins/$p/$p.plugin.zsh"
  elif [[ -f "$ZSH/plugins/$p/$p.plugin.zsh" ]]; then
    source "$ZSH/plugins/$p/$p.plugin.zsh"
  fi
done
''',
            "lib/completion.zsh": "# fixture\n",
            "plugins/git/git.plugin.zsh": 'print -r -- git >> "$LOADED"\n',
            "plugins/z/z.plugin.zsh": 'print -r -- z >> "$LOADED"\n',
            "tools/install.sh": 'echo MUST_NOT_RUN > "$HOME/official-installer-ran"\n'})
        self.register("oh-my-zsh", OMZ_VERSION, "oh-my-zsh.tar.gz")

    def plugin(self, name, version):
        self.tar(name + ".tar.gz", name + "-" + version,
                 {name + ".plugin.zsh": 'print -r -- ' + name + ' >> "$LOADED"\n',
                  name + ".zsh": "# fixture\n"})
        self.register(name, version, name + ".tar.gz")

    def run_script(self, name, *args, extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/software" / name), *args],
                              env={**self.env, **(extra or {})}, cwd=self.base,
                              text=True, errors="backslashreplace", capture_output=True, timeout=30)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def load_profile(self, extra=None):
        return subprocess.run(["/bin/zsh", "-dfc", 'source "$HOME/.zshrc"; print -r -- "$ZSH_THEME"'],
                              env={**self.env, **(extra or {})}, cwd=self.base,
                              text=True, capture_output=True, timeout=10)

    def test_iterm_installs_and_reuses_without_launching_or_overwriting(self):
        unexpected = self.base / "external-applications"
        self.assert_ok(self.run_script("install-iterm2.sh", extra={"USER_APPLICATIONS_DIR": str(unexpected)}))
        binary = self.home / "Applications/iTerm.app/Contents/MacOS/iTerm2"
        self.assertTrue(os.access(binary, os.X_OK))
        self.assertFalse((self.home / "Users").exists())
        self.assertFalse((self.base / "Users/other-login").exists())
        self.assertFalse(unexpected.exists())
        before = binary.stat().st_mtime_ns
        self.assert_ok(self.run_script("install-iterm2.sh"))
        self.assertEqual(binary.stat().st_mtime_ns, before)
        info = binary.parents[1] / "Info.plist"
        data = plistlib.loads(info.read_bytes())
        data["CFBundleShortVersionString"] = "3.6.0"
        info.write_bytes(plistlib.dumps(data))
        self.assertNotEqual(self.run_script("install-iterm2.sh").returncode, 0)
        self.assertEqual(plistlib.loads(info.read_bytes())["CFBundleShortVersionString"], "3.6.0")

    def test_iterm_help_shows_expanded_install_destination_without_writing(self):
        result = self.run_script("install-iterm2.sh", "--help")
        self.assert_ok(result)
        self.assertIn(str(self.home / "Applications/iTerm.app"), result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_iterm_rejects_old_macos_and_invalid_signature(self):
        for extra in ({"MACOS_VERSION": "12.7"}, {"SIGNATURE_STATUS": "1"}):
            with self.subTest(extra=extra):
                self.assertNotEqual(self.run_script("install-iterm2.sh", extra=extra).returncode, 0)
                self.assertFalse((self.home / "Applications/iTerm.app").exists())

    def test_iterm_rejects_archive_escape_before_extraction(self):
        self.iterm(extra=[("../escaped", b"unsafe", 0o100644)])
        self.catalog()
        result = self.run_script("install-iterm2.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "Applications/iTerm.app").exists())
        self.assertFalse(any(self.home.rglob("escaped")))

    def test_iterm_rejects_symlink_destination(self):
        external = self.base / "external"
        external.mkdir()
        (self.home / "Applications").symlink_to(external)
        self.assertNotEqual(self.run_script("install-iterm2.sh").returncode, 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_iterm_does_not_add_unsealed_files_to_signed_bundle(self):
        self.assert_ok(self.run_script("install-iterm2.sh"))
        app = self.home / "Applications/iTerm.app"
        self.assertEqual({p.name for p in app.iterdir()}, {"Contents"})
        records = list((self.home / ".local/share/team-frontend-env/receipts").rglob(".team-frontend-env-install.json"))
        self.assertEqual(len(records), 1)
        self.assertIn('"kind":"iterm2"', records[0].read_text())

    def test_dry_runs_do_not_create_cache_or_shell_configuration(self):
        for script in ("install-iterm2.sh", "install-zsh.sh"):
            self.assert_ok(self.run_script(script, "--dry-run"))
        self.assertEqual(list(self.home.iterdir()), [])

    def test_framework_and_plugins_without_clt_do_not_invoke_system_git_or_change_home(self):
        (self.bin / "git").unlink()
        (self.bin / "git").symlink_to("/usr/bin/git")
        self.stub("xcode-select", '#!/bin/sh\nexit 2\n')
        called = self.base / "system-git-called"
        guard = self.base / "guard.sh"
        guard.write_text('set -T\ntrap \'case "$BASH_COMMAND" in *--version*) printf blocked > "$GIT_CALL_GUARD"; exit 91;; esac\' DEBUG\n')
        for arguments in ([], ["--without-plugins"]):
            with self.subTest(arguments=arguments):
                result = self.run_script("install-zsh.sh", *arguments, extra={"BASH_ENV": str(guard), "GIT_CALL_GUARD": str(called)})
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Git", result.stderr)
                self.assertIn("CLT", result.stderr)
                self.assertFalse(called.exists(), "system Git must not be executed when CLT is unavailable")
                self.assertEqual(list(self.home.iterdir()), [])

    def test_dry_run_reports_git_dependency_without_executing_it(self):
        self.stub("git", '#!/bin/sh\nprintf called > "$HOME/git-called"\nexit 1\n')
        self.stub("xcode-select", '#!/bin/sh\nexit 2\n')
        for arguments in ([], ["--without-plugins"]):
            with self.subTest(arguments=arguments):
                result = self.run_script("install-zsh.sh", "--dry-run", *arguments)
                self.assert_ok(result)
                self.assertIn("Git", result.stdout)
                self.assertEqual(list(self.home.iterdir()), [])

    def test_recommended_plugins_reject_nonfunctional_custom_git_before_writes(self):
        self.stub("git", '#!/bin/sh\necho not-git\nexit 0\n')
        result = self.run_script("install-zsh.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_zsh_preserves_profile_and_loads_four_plugins_in_order_idempotently(self):
        profile = self.home / ".zshrc"
        original = 'export JAVA_HOME=/fixture/jdk\nZSH_THEME="user-theme"\nplugins=(custom)\n'
        profile.write_text(original)
        self.assert_ok(self.run_script("install-zsh.sh"))
        first = profile.read_bytes()
        self.assertTrue(first.decode().startswith(original))
        self.assertTrue(any(p.read_text() == original for p in self.home.glob(".zshrc*")) )
        self.assert_ok(self.run_script("install-zsh.sh"))
        self.assertEqual(profile.read_bytes(), first)
        result = self.load_profile()
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip(), "user-theme")
        self.assertEqual(self.record.read_text().splitlines(),
                         ["framework", "git", "z", "zsh-autosuggestions", "zsh-syntax-highlighting"])
        self.assertFalse((self.home / "official-installer-ran").exists())

    def test_existing_omz_preserves_custom_and_does_not_load_framework_twice(self):
        self.assert_ok(self.run_script("install-zsh.sh", "--without-plugins"))
        custom = self.home / ".oh-my-zsh/custom/keep.zsh"
        custom.write_text("# preserved\n")
        profile = self.home / ".zshrc"
        profile.write_text('ZSH="$HOME/.oh-my-zsh"\nZSH_THEME=mine\nplugins=(git)\nsource "$ZSH/oh-my-zsh.sh"\n')
        self.assert_ok(self.run_script("install-zsh.sh"))
        self.assertEqual(custom.read_text(), "# preserved\n")
        result = self.load_profile()
        self.assert_ok(result)
        self.assertEqual(self.record.read_text().splitlines(),
                         ["framework", "git", "z", "zsh-autosuggestions", "zsh-syntax-highlighting"])

    def test_existing_highlighter_is_not_loaded_twice_when_adding_plugins(self):
        self.assert_ok(self.run_script("install-zsh.sh"))
        (self.home / ".zshrc").write_text('ZSH="$HOME/.oh-my-zsh"\nplugins=(zsh-syntax-highlighting)\nsource "$ZSH/oh-my-zsh.sh"\n')
        self.assert_ok(self.run_script("install-zsh.sh"))
        self.assert_ok(self.load_profile())
        self.assertEqual(self.record.read_text().splitlines(),
                         ["framework", "zsh-syntax-highlighting", "git", "z", "zsh-autosuggestions"])

    def test_zsh_without_plugins_installs_only_framework(self):
        self.assert_ok(self.run_script("install-zsh.sh", "--without-plugins"))
        self.assertTrue((self.home / ".oh-my-zsh/oh-my-zsh.sh").is_file())
        self.assertFalse((self.home / ".oh-my-zsh/custom/plugins/zsh-autosuggestions").exists())
        self.assert_ok(self.load_profile())
        self.assertEqual(self.record.read_text().splitlines(), ["framework"])

    def test_existing_unowned_framework_keeps_user_update_policy(self):
        self.assert_ok(self.run_script("install-zsh.sh", "--without-plugins"))
        (self.home / ".oh-my-zsh/.team-frontend-env-install.json").unlink()
        profile = self.home / ".zshrc"
        profile.write_text("zstyle ':omz:update' mode auto\n")
        self.assert_ok(self.run_script("install-zsh.sh", "--without-plugins"))
        result = subprocess.run(["/bin/zsh", "-dfc", 'source "$HOME/.zshrc"; zstyle -s ":omz:update" mode result; print -r -- "$result"'],
                                env=self.env, cwd=self.base, text=True, capture_output=True, timeout=10)
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip(), "auto")

    def test_zsh_profile_custom_plugin_directory_does_not_hide_installed_plugins(self):
        custom = self.home / "user-custom"
        custom.mkdir()
        (self.home / ".zshrc").write_text('ZSH_CUSTOM="$HOME/user-custom"\nplugins=(git zsh-autosuggestions)\n')
        self.assert_ok(self.run_script("install-zsh.sh"))
        self.assert_ok(self.load_profile())
        self.assertEqual(self.record.read_text().splitlines(),
                         ["framework", "git", "z", "zsh-autosuggestions", "zsh-syntax-highlighting"])
        self.assertEqual(list(custom.iterdir()), [])

    def test_zsh_refuses_unknown_existing_framework_and_symlink_profile(self):
        root = self.home / ".oh-my-zsh"
        root.mkdir()
        (root / "keep.txt").write_text("keep")
        self.assertNotEqual(self.run_script("install-zsh.sh").returncode, 0)
        self.assertEqual((root / "keep.txt").read_text(), "keep")
        shutil.rmtree(root)
        external = self.base / "profile"
        external.write_text("keep\n")
        (self.home / ".zshrc").symlink_to(external)
        self.assertNotEqual(self.run_script("install-zsh.sh").returncode, 0)
        self.assertEqual(external.read_text(), "keep\n")

    def test_zsh_rejects_plugin_archive_symlink_escape_and_hash_mismatch(self):
        archive = self.web / "zsh-autosuggestions.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            member = tarfile.TarInfo("zsh-autosuggestions-0.7.1/evil")
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp"
            output.addfile(member)
        self.register("zsh-autosuggestions", "0.7.1", archive.name)
        self.catalog()
        self.assertNotEqual(self.run_script("install-zsh.sh").returncode, 0)
        self.assertFalse((self.home / ".zshrc").exists())
        self.plugin("zsh-autosuggestions", "0.7.1")
        self.catalog()
        archive.write_bytes(b"corrupt")
        self.assertNotEqual(self.run_script("install-zsh.sh").returncode, 0)
        self.assertFalse((self.home / ".zshrc").exists())

    def test_zsh_accepts_in_root_documentation_links_and_rejects_link_ancestor_escape(self):
        name = "zsh-syntax-highlighting"
        archive = self.web / (name + ".tar.gz")
        self.tar(archive.name, name + "-0.8.0", {
            name + ".plugin.zsh": 'print -r -- zsh-syntax-highlighting >> "$LOADED"\n',
            "docs/highlighters/main.md": "documentation\n"})
        # Append using an uncompressed intermediate only inside the test temporary directory.
        with tarfile.open(archive, "r:gz") as source:
            members = [(member, source.extractfile(member).read()) for member in source.getmembers()]
        with tarfile.open(archive, "w:gz") as output:
            for member, data in members:
                output.addfile(member, io.BytesIO(data))
            link = tarfile.TarInfo(name + "-0.8.0/highlighters/main/README.md")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../docs/highlighters/main.md"
            output.addfile(link)
        self.register(name, "0.8.0", archive.name)
        self.catalog()
        self.assert_ok(self.run_script("install-zsh.sh"))
        target = self.home / ".oh-my-zsh/custom/plugins" / name
        self.assertEqual((target / "highlighters/main/README.md").read_text(), "documentation\n")
        shutil.rmtree(target)
        shutil.rmtree(self.home / "Library/Caches/team-frontend-env")
        with tarfile.open(archive, "w:gz") as output:
            for path, destination in (("a", "."), ("b", "a/../escaped")):
                link = tarfile.TarInfo(name + "-0.8.0/" + path)
                link.type = tarfile.SYMTYPE
                link.linkname = destination
                output.addfile(link)
        self.register(name, "0.8.0", archive.name)
        self.catalog()
        self.assertNotEqual(self.run_script("install-zsh.sh").returncode, 0)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
