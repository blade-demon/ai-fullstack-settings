"""安装来源标记：仅新发布的 SDK 可供清理器认领，不标记复用的 SDK。"""
import hashlib
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest

import test_gradle_install as gradle_fixture
import test_gradle_versions as versions_fixture


MARKER = ".team-java-env-install.json"


class SDKOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.fixture = gradle_fixture.GradleInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_jdk(self, *args, extra=None):
        fixture = self.fixture
        return subprocess.run(["/bin/bash", str(fixture.support / "scripts/runtime/config-jdk.sh"), *args],
                              cwd=fixture.base, env={**fixture.env, **(extra or {})},
                              text=True, capture_output=True, timeout=20)

    def test_new_jdk_install_has_ownership_marker_at_published_root(self):
        fixture = self.fixture
        archive = fixture.web / "jdk8-fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(fixture.jdk, arcname="jdk8/Contents/Home")
        target = fixture.home / ".local/share/java-dev/jdk8"
        server = fixture.server()
        result = self.run_jdk(extra={"SERVER_ADDR": server["SERVER_ADDR"],
                                     "JDK_PACKAGE_PATH": archive.name,
                                     "JDK_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                     "JDK_INSTALL_DIR": str(target), "JAVA_HOME": ""})
        self.assert_ok(result)
        self.assertTrue((target / MARKER).is_file(), "新发布 JDK 缺少来源标记")
        self.assertEqual(json.loads((target / MARKER).read_text()),
                         {"schema": 1, "tool": "team-java-env", "kind": "jdk"})
        self.assertFalse((fixture.jdk / MARKER).exists())
        self.assertFalse((target / "jdk8/Contents/Home" / MARKER).exists())

    def test_new_gradle_install_has_ownership_marker(self):
        fixture = self.fixture
        result = fixture.run_script(extra=fixture.server())
        self.assert_ok(result)
        self.assertTrue((fixture.target / MARKER).is_file(), "新发布 Gradle 缺少来源标记")
        self.assertEqual(json.loads((fixture.target / MARKER).read_text()),
                         {"schema": 1, "tool": "team-java-env", "kind": "gradle"})
        self.assertFalse((fixture.jdk / MARKER).exists())

    def test_jdk_archive_cannot_redirect_marker_write_through_a_symlink(self):
        fixture = self.fixture
        external = fixture.base / "unrelated-user-file"
        external.write_text("preserve unrelated contents\n")
        archive = fixture.web / "jdk8-linked-marker.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(fixture.jdk, arcname="jdk8/Contents/Home")
            link = tarfile.TarInfo(MARKER)
            link.type = tarfile.SYMTYPE
            link.linkname = str(external)
            bundle.addfile(link)
        target = fixture.home / ".local/share/java-dev/jdk8"
        server = fixture.server()
        result = self.run_jdk(extra={"SERVER_ADDR": server["SERVER_ADDR"],
                                     "JDK_PACKAGE_PATH": archive.name,
                                     "JDK_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                     "JDK_INSTALL_DIR": str(target), "JAVA_HOME": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(external.read_text(), "preserve unrelated contents\n")
        self.assertFalse(target.exists())
        self.assertFalse(fixture.env_file.exists())

    def test_reusing_external_jdk_does_not_claim_it(self):
        fixture = self.fixture
        before = (fixture.jdk / "bin/java").read_bytes()
        self.assert_ok(self.run_jdk())
        self.assertFalse((fixture.jdk / MARKER).exists())
        self.assertEqual((fixture.jdk / "bin/java").read_bytes(), before)

    def test_reusing_unmarked_gradle_does_not_claim_it(self):
        fixture = self.fixture
        fixture.seed_install()
        self.assert_ok(fixture.run_script())
        self.assertFalse((fixture.target / MARKER).exists())
        self.assertFalse((fixture.jdk / MARKER).exists())

    def test_dry_runs_do_not_write_ownership_markers(self):
        fixture = self.fixture
        self.assert_ok(self.run_jdk("--dry-run"))
        self.assert_ok(fixture.run_script("--dry-run"))
        self.assertFalse(list(fixture.base.rglob(MARKER)))
        self.assertFalse(fixture.target.exists())
        self.assertFalse(fixture.env_file.exists())

    def test_uninstall_one_registered_gradle_preserves_actual_switch_function_jdk_and_default(self):
        fixture = versions_fixture.GradleVersionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        first, second = fixture.seed_version('4.5.1'), fixture.seed_version('6.8')
        for version, path in (('4.5.1', first), ('6.8', second)):
            (path / MARKER).write_text(json.dumps(dict(schema=1, tool='team-java-env', kind='gradle')))
            fixture.assert_ok(fixture.run_script(extra={'GRADLE_VERSION': version}))
        spec = importlib.util.spec_from_file_location('owned_component_cleanup', Path(__file__).resolve().parents[1] / 'tools/uninstall_java_gradle.py')
        tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = tool
        spec.loader.exec_module(tool)
        env = dict(HOME=str(fixture.home), ENV_FILE=str(fixture.env_file), PATH='/usr/bin:/bin')
        def cleaner(instances=None):
            return tool.Cleaner(fixture.home, components='gradle', instances=instances, environ=env,
                                system_jvms=fixture.base / 'system/java', process_reader=lambda: [])
        selected = next(item['id'] for item in cleaner().scan().instances if item['path'] == str(first))
        with contextlib.redirect_stdout(io.StringIO()):
            cleaner([selected]).scan().apply()
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(fixture.jdk.exists())
        self.assertEqual((fixture.env_file.parent / 'gradle-default').read_text(), '6.8\n')
        for shell in ('/bin/bash', '/bin/zsh'):
            result = subprocess.run([shell, '-f', '-c', 'source "$1"; gradle_use 6.8 >/dev/null || exit; printf "%s\\n" "$GRADLE_HOME" "$JAVA_HOME"', 'cleanup-check', str(fixture.env_file)], env=fixture.env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(second), str(fixture.jdk)])


if __name__ == "__main__":
    unittest.main()
