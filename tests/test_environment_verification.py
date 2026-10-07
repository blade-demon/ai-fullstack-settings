import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

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

    def test_startup_scan_recognizes_active_gradle68_and_its_alias(self):
        target = self.base / 'gradle-6.8'
        self.gradle.rename(target)
        (target / 'lib/gradle-launcher-4.5.1.jar').rename(target / 'lib/gradle-launcher-6.8.jar')
        result = subprocess.run(['/bin/bash', '-c',
                                 'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/managed-env.sh"; managed_env_write_gradle "$2"',
                                 'setup', str(self.support), str(target)],
                                env={**self.env, 'GRADLE_VERSION': '6.8'}, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_script('check-env.sh')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[已安装] 独立 Gradle 6.8', result.stdout)
        self.assertIn('[配置完整] GRADLE_6_8_HOME=', result.stdout)

    def idea_project(self, sdk='fixture-jdk-8', jvm='#PROJECT', home=None, distribution=None):
        self.project = self.base / "业务项目's"
        idea = self.project / '.idea'; idea.mkdir(parents=True)
        (self.project / 'build.gradle').write_text('// project fixture\n')
        (self.project / 'gradlew').write_text('#!/bin/sh\necho SHOULD_NOT_RUN_WRAPPER\nexit 97\n')
        wrapper = self.project / 'gradle/wrapper'; wrapper.mkdir(parents=True)
        (wrapper / 'gradle-wrapper.jar').write_bytes(b'fixture')
        (wrapper / 'gradle-wrapper.properties').write_text('distributionUrl=https\\://example.invalid/gradle-4.5.1-bin.zip\n')
        root = ET.Element('project')
        ET.SubElement(root, 'component', name='ProjectRootManager', **{'project-jdk-name': sdk, 'project-jdk-type': 'JavaSDK'})
        ET.ElementTree(root).write(idea / 'misc.xml', encoding='utf-8')
        root = ET.Element('project')
        settings = ET.SubElement(ET.SubElement(root, 'component', name='GradleSettings'), 'option', name='linkedExternalProjectsSettings')
        project_settings = ET.SubElement(settings, 'GradleProjectSettings')
        ET.SubElement(project_settings, 'option', name='externalProjectPath', value='$PROJECT_DIR$')
        ET.SubElement(project_settings, 'option', name='gradleJvm', value=jvm)
        if distribution:
            ET.SubElement(project_settings, 'option', name='distributionType', value=distribution)
        ET.ElementTree(root).write(idea / 'gradle.xml', encoding='utf-8')
        root = ET.Element('application')
        jdk = ET.SubElement(ET.SubElement(root, 'component', name='ProjectJdkTable'), 'jdk')
        ET.SubElement(jdk, 'name', value='fixture-jdk-8')
        ET.SubElement(jdk, 'type', value='JavaSDK')
        ET.SubElement(jdk, 'homePath', value=str(home or self.jdk))
        config = self.home / 'Library/Application Support/JetBrains/IdeaIC2024.3/options'
        config.mkdir(parents=True)
        ET.ElementTree(root).write(config / 'jdk.table.xml', encoding='utf-8')
        return idea

    def test_project_inherited_missing_sdk_is_pending_despite_valid_terminal_sdk(self):
        idea = self.idea_project(sdk='removed-sdk')
        before = {p: p.read_bytes() for p in idea.iterdir()}
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('IDEA 项目待配置', result.stdout)
        self.assertIn('#PROJECT', result.stdout)
        self.assertIn(str(self.jdk), result.stdout)
        self.assertNotIn('SHOULD_NOT_RUN_WRAPPER', result.stdout)
        self.assertEqual(before, {p: p.read_bytes() for p in idea.iterdir()})

    def test_registered_project_sdk_and_explicit_jvm_are_checked_without_running_wrapper(self):
        self.idea_project(jvm='fixture-jdk-8')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('IDEA 项目配置可解析', result.stdout)
        self.assertIn('fixture-jdk-8', result.stdout)
        self.assertIn('Wrapper', result.stdout)
        self.assertIn('同步', result.stdout)
        self.assertNotIn('SHOULD_NOT_RUN_WRAPPER', result.stdout)

    def test_registered_sdk_with_missing_installation_is_pending(self):
        self.idea_project(home=self.base / 'deleted-jdk')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('IDEA 项目待配置', result.stdout)

    def test_malformed_idea_configuration_is_not_reported_ready(self):
        idea = self.idea_project()
        (idea / 'gradle.xml').write_text('<project><broken>')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('IDEA 项目待配置', result.stdout)

    def test_idea_xml_external_entity_is_rejected_without_reading_its_content(self):
        idea = self.idea_project()
        secret = self.base / 'private'; secret.write_text('PRIVATE_ENTITY_CONTENT')
        (idea / 'misc.xml').write_text(f'<!DOCTYPE project [<!ENTITY leak SYSTEM "{secret.as_uri()}">]><project>&leak;</project>')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn('PRIVATE_ENTITY_CONTENT', result.stdout + result.stderr)

    def test_local_idea_distribution_requires_its_own_gradle_home(self):
        self.idea_project(distribution='LOCAL')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('Gradle', result.stdout)
        self.assertIn(str(self.gradle), result.stdout)

    def test_project_sdk_type_must_match_registered_java_sdk(self):
        idea = self.idea_project()
        xml = ET.parse(idea / 'misc.xml')
        xml.find('component').set('project-jdk-type', 'UnknownSDK')
        xml.write(idea / 'misc.xml', encoding='utf-8')
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('IDEA 项目待配置', result.stdout)

    def test_utf16_dtd_is_rejected_before_sdk_entity_expansion(self):
        idea = self.idea_project()
        content = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE project [<!ENTITY sdk "fixture-jdk-8">]><project><component name="ProjectRootManager" project-jdk-name="&sdk;" project-jdk-type="JavaSDK" /></project>'
        (idea / 'misc.xml').write_bytes(content.encode('utf-16'))
        result = self.run_script('check-env.sh', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('IDEA 项目待配置', result.stdout)

    def test_duplicate_distribution_settings_refuse_to_run_either_gradle(self):
        idea = self.idea_project()
        xml = ET.parse(idea / 'gradle.xml')
        settings = xml.find('.//GradleProjectSettings')
        ET.SubElement(settings, 'option', name='distributionType', value='DEFAULT_WRAPPED')
        ET.SubElement(settings, 'option', name='distributionType', value='LOCAL')
        xml.write(idea / 'gradle.xml', encoding='utf-8')
        calls = self.base / 'wrapper-calls'
        self.env['IDEA_ROUTE_RECORD'] = str(calls)
        wrapper = self.project / 'gradlew'
        wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$IDEA_ROUTE_RECORD"\nif [ "$1" = --version ]; then echo "Gradle 4.5.1"; else echo "BUILD SUCCESSFUL"; fi\n')
        wrapper.chmod(0o755)
        result = self.run_script('runtime/verify-gradle.sh', '--project', str(self.project))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(calls.exists())

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
