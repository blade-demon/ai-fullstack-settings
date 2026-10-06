import functools
import hashlib
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class MemberResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="组员资源 test ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.support = self.base / ".support"
        shutil.copytree(ROOT / "dev-kit/.support", self.support)
        shutil.copy2(ROOT / "tools/prepare-resources.sh", self.support / "scripts/prepare-resources.sh")
        self.home = self.base / "用户's home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        uname = self.bin / "uname"
        uname.write_text('#!/bin/sh\nif [ "$1" = -m ]; then echo arm64; else echo Darwin; fi\n')
        uname.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
        self.payload = b"offline plugin fixture"
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.catalog = self.support / "config/resources.tsv"
        self.catalog.write_text(
            f"plugin\tplugins\t1.0\tany\tplugins/demo.zip\thttps://must-not-connect.invalid/demo.zip\t{self.digest}\n"
            f"idea-arm\tsoftware\t2024\tarm64\tsoftware/arm.dmg\thttps://must-not-connect.invalid/a\t{self.digest}\n"
            f"idea-intel\tsoftware\t2024\tx64\tsoftware/intel.dmg\thttps://must-not-connect.invalid/b\t{self.digest}\n")

    def run_script(self, *args, input_text="", extra=None):
        return subprocess.run(["/bin/bash", str(self.support / "scripts/download-tools.sh"), *args],
                              cwd=self.base, env={**self.env, **(extra or {})}, input=input_text,
                              text=True, capture_output=True, timeout=15)

    def test_listing_filters_architecture_and_does_not_write(self):
        result = self.run_script("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("idea-arm", result.stdout)
        self.assertIn("plugin", result.stdout)
        self.assertNotIn("idea-intel", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_dry_run_always_uses_intranet_and_does_not_write(self):
        result = self.run_script("--id", "plugin", "--dry-run", extra={"SERVER_ADDR": "team.example:8080"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://team.example:8080/resources/plugins/demo.zip", result.stdout)
        self.assertNotIn("must-not-connect", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_idea_install_preview_uses_native_arch_and_personal_applications(self):
        result = self.run_script("--install-idea", "--dry-run", extra={"SERVER_ADDR": "team.example:8080"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://team.example:8080/resources/software/arm.dmg", result.stdout)
        self.assertIn(str(self.home / "Applications/IntelliJ IDEA CE.app"), result.stdout)
        self.assertNotIn("intel.dmg", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_idea_install_mode_rejects_non_idea_resource(self):
        result = self.run_script("--install-idea", "--id", "plugin", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_download_uses_intranet_and_validates_bytes(self):
        resource = self.base / "web/resources/plugins/demo.zip"
        resource.parent.mkdir(parents=True)
        resource.write_bytes(self.payload)
        handler = functools.partial(QuietHandler, directory=str(self.base / "web"))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        result = self.run_script("--id", "plugin", extra={"SERVER_ADDR": f"127.0.0.1:{server.server_port}"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        downloaded = self.home / "Downloads/team-java-env/plugins/demo.zip"
        self.assertEqual(downloaded.read_bytes(), self.payload)
        self.assertIn("Install Plugin from Disk", result.stdout)

    def test_cancel_and_unavailable_id_do_not_write(self):
        result = self.run_script(input_text="0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_script("--id", "idea-intel")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_empty_resource_id_is_not_interactive(self):
        result = self.run_script("--id", "", input_text="0\n")
        self.assertNotEqual(result.returncode, 0)

    def test_gradle_uses_pinned_member_catalog_hash(self):
        project = self.base / "Java 项目"
        wrapper = project / "gradle/wrapper"
        wrapper.mkdir(parents=True)
        (project / "gradlew").write_text("#!/bin/sh\nexit 99\n")
        (wrapper / "gradle-wrapper.jar").write_bytes(b"fixture")
        properties = wrapper / "gradle-wrapper.properties"
        properties.write_text("distributionUrl=https\\://old.example/gradle.zip\n")
        with self.catalog.open("a") as file:
            file.write(f"gradle\truntime\t4.5.1\tany\truntime/gradle/gradle-4.5.1-bin.zip\thttps://unused.example\t{self.digest}\n")
        resource = self.base / "web/resources/runtime/gradle/gradle-4.5.1-bin.zip"
        resource.parent.mkdir(parents=True)
        resource.write_bytes(self.payload)
        handler = functools.partial(QuietHandler, directory=str(self.base / "web"))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        result = subprocess.run(["/bin/bash", str(self.support / "scripts/runtime/config-gradle.sh"),
                                 "--project", str(project)],
                                env={**self.env, "SERVER_ADDR": f"127.0.0.1:{server.server_port}"},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("distributionSha256Sum=" + self.digest, properties.read_text())


if __name__ == "__main__":
    unittest.main()
