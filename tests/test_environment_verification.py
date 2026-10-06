import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="完整验证's ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.support = self.base / '.support'
        shutil.copytree(ROOT / 'dev-kit/.support', self.support)
        self.home = self.base / 'home'; self.home.mkdir()
        self.jdk = self.base / 'jdk8'
        (self.jdk/'bin').mkdir(parents=True); (self.jdk/'jre').mkdir()
        for name, text in [('java','openjdk version "1.8.0_432"'),('javac','javac 1.8.0_432')]:
            executable=self.jdk/'bin'/name
            executable.write_text("#!/bin/sh\nprintf '%s\\n' '"+text+"' >&2\n"); executable.chmod(0o755)
        self.gradle=self.base/'gradle-4.5.1'
        (self.gradle/'bin').mkdir(parents=True); (self.gradle/'lib').mkdir()
        (self.gradle/'lib/gradle-launcher-4.5.1.jar').write_bytes(b'fixture')
        (self.gradle/'bin/gradle').write_text('#!/bin/sh\necho "Gradle 4.5.1"\n')
        (self.gradle/'bin/gradle').chmod(0o755)
        self.app=self.home/'Applications/IntelliJ IDEA CE.app'
        (self.app/'Contents/MacOS').mkdir(parents=True)
        with (self.app/'Contents/Info.plist').open('wb') as f:
            plistlib.dump({'CFBundleIdentifier':'com.jetbrains.intellij.ce','CFBundleVersion':'IC-243.28141.41',
                          'CFBundleShortVersionString':'2024.3.7.1','CFBundleExecutable':'idea'},f)
        (self.app/'Contents/MacOS/idea').write_text('#!/bin/sh\nexit 89\n'); (self.app/'Contents/MacOS/idea').chmod(0o755)
        jbr=self.app/'Contents/jbr/Contents/Home/bin/java'; jbr.parent.mkdir(parents=True)
        jbr.write_text('#!/bin/sh\necho "runtime 21"\n'); jbr.chmod(0o755)
        self.bin=self.base/'bin'; self.bin.mkdir()
        self.codesign=self.bin/'codesign'; self.codesign.write_text('#!/bin/sh\nexit 0\n'); self.codesign.chmod(0o755)
        self.env={'HOME':str(self.home),'PATH':f'{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin','SHELL':'/bin/zsh',
                  'LC_ALL':'C.UTF-8','JDK_AUTO_DETECT':'false','JDK_INSTALL_DIR':str(self.jdk),'IDEA_APP':str(self.app)}
        result=subprocess.run(['/bin/bash','-c','source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/managed-env.sh"; managed_env_write_jdk "$2"; managed_env_write_gradle "$3"',
                               'setup',str(self.support),str(self.jdk),str(self.gradle)],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def run_script(self, script, *args):
        return subprocess.run(['/bin/bash',str(self.support/'scripts'/script),*args],env=self.env,text=True,capture_output=True,timeout=15)

    def test_full_scan_lists_all_variables_and_idea_without_running_ide(self):
        result=self.run_script('check-env.sh')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in ['JAVA_HOME=','JAVA_8_HOME=','JRE_HOME=','GRADLE_HOME=','GRADLE_4_5_1_HOME=','GRADLE_USER_HOME=','IDEA 2024.3.7.1']:
            self.assertIn(name,result.stdout)
        self.assertIn('未选择项目',result.stdout)

    def test_incomplete_environment_is_repairable_not_ready(self):
        (self.home/'.config/java-dev/jdk.sh').write_text("export JAVA_HOME='"+str(self.jdk)+"'\n")
        result=self.run_script('check-env.sh')
        self.assertEqual(result.returncode,1)
        self.assertIn('一键修复',result.stdout)
        self.assertIn('[待修复] JAVA_HOME',result.stdout)

    def test_gradle_runtime_version_failure_overrides_static_structure(self):
        self.assertEqual(self.run_script('verify-environment.sh','--scope','gradle').returncode,0)
        (self.gradle/'bin/gradle').write_text('#!/bin/sh\necho "Gradle 8.0"\n')
        result=self.run_script('verify-environment.sh','--scope','gradle')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('版本错误',result.stderr)

    def test_idea_requires_signature_and_runtime_checks(self):
        self.assertEqual(self.run_script('verify-environment.sh','--scope','idea').returncode,0)
        self.codesign.write_text('#!/bin/sh\nexit 17\n')
        result=self.run_script('verify-environment.sh','--scope','idea')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('签名验证失败',result.stderr)

    def test_profile_override_after_source_is_not_reported_ready(self):
        with (self.home / '.zshrc').open('a') as stream:
            stream.write('\nexport JAVA_HOME=/wrong-jdk\nexport PATH=/usr/bin:/bin\n')
        result = self.run_script('verify-environment.sh', '--scope', 'gradle')
        self.assertNotEqual(result.returncode, 0)

    def test_profile_return_before_managed_block_fails_actual_shell_verification(self):
        profile = self.home / '.zshrc'
        profile.write_text('return 0\n' + profile.read_text())
        result = self.run_script('verify-environment.sh', '--scope', 'gradle')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Shell', result.stderr)

    def test_profile_output_is_not_copied_to_verification_logs(self):
        profile = self.home / '.zshrc'
        profile.write_text('echo PRIVATE_CONFIG_VALUE\necho PRIVATE_CONFIG_ERROR >&2\n' + profile.read_text())
        result = self.run_script('verify-environment.sh', '--scope', 'gradle')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('PRIVATE_CONFIG', result.stdout + result.stderr)

    def test_profile_execution_is_bounded(self):
        profile = self.home / '.zshrc'
        profile.write_text('/bin/sleep 30\n' + profile.read_text())
        started = time.monotonic()
        result = self.run_script('verify-environment.sh', '--scope', 'gradle')
        self.assertLess(time.monotonic() - started, 9)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Shell', result.stderr)


if __name__=='__main__': unittest.main()
