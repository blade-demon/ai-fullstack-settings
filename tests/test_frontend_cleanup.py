"""六组件卸载边界；仅操作临时 HOME，不执行安装的 SDK。"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest import mock
import test_terminal_tools as terminal_fixture
from test_uninstall_java_gradle import LEGACY_PATH_FIXTURE

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.team-frontend-env-install.json'


class ComponentCleanupTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('component_cleanup', ROOT / 'tools/uninstall_java_gradle.py')
        self.tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.tool
        spec.loader.exec_module(self.tool)
        self.temp = tempfile.TemporaryDirectory(prefix="component cleanup's ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / 'home'
        self.home.mkdir()
        self.env = {'HOME': str(self.home), 'PATH': '/usr/bin:/bin'}

    def write(self, path, body='fixture'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
        return path

    def mark(self, root, kind, **data):
        self.write(root / MARKER, json.dumps(dict(schema=1, tool='team-frontend-env', kind=kind,
                                               version='1', arch='any', archive='fixture.tar.gz', sha256='a' * 64, **data)))

    def sdk(self, name, kind):
        path = self.home / '.local/share/java-dev' / name
        self.write(path / ('bin/java' if kind == 'jdk' else 'bin/gradle'), 'must never execute')
        self.write(path / ('bin/javac' if kind == 'jdk' else 'lib/gradle-launcher-' + name[7:] + '.jar'))
        self.write(path / '.team-java-env-install.json', json.dumps(dict(schema=1, tool='team-java-env', kind=kind)))
        return path

    def cleaner(self, components, **kwargs):
        return self.tool.Cleaner(self.home, components=components, environ=self.env,
                                 system_jvms=self.home / 'system/java', system_apps=self.home / 'system/apps',
                                 process_reader=lambda: [], **kwargs)

    def apply(self, plan):
        with contextlib.redirect_stdout(io.StringIO()):
            plan.apply()

    def test_jdk_only_preserves_gradle_install_mapping_default_and_loading(self):
        jdk = self.sdk('jdk8', 'jdk')
        gradle = self.sdk('gradle-6.8', 'gradle')
        module = self.write(self.home / '.config/java-dev/gradle.sh', 'export GRADLE_HOME="{}"\n'.format(gradle))
        default = self.write(module.parent / 'gradle-default', '6.8\n')
        profile = self.write(self.home / '.zshrc', '# >>> team-java-env managed >>>\nexport JAVA_HOME="{}"\nexport GRADLE_HOME="{}"\nexport PATH="$JAVA_HOME/bin:$GRADLE_HOME/bin:$PATH"\n# <<< team-java-env managed <<<\n'.format(jdk, gradle))
        self.apply(self.cleaner('jdk').scan())
        self.assertFalse(jdk.exists())
        self.assertTrue(gradle.exists())
        self.assertIn('GRADLE_HOME', profile.read_text())
        self.assertNotIn('$JAVA_HOME/bin', profile.read_text())
        self.assertEqual(module.read_text(), 'export GRADLE_HOME="{}"\n'.format(gradle))
        self.assertEqual(default.read_text(), '6.8\n')

    def test_instance_white_list_removes_one_gradle_and_only_its_configuration(self):
        first = self.sdk('gradle-4.5.1', 'gradle')
        second = self.sdk('gradle-6.8', 'gradle')
        module = self.write(self.home / '.config/java-dev/gradle.sh', '# >>> team-java-env managed >>>\nexport GRADLE_4_5_1_HOME="{}"\nexport GRADLE_6_8_HOME="{}"\ngradle_use() {{ :; }}\n# <<< team-java-env managed <<<\n'.format(first, second))
        default = self.write(module.parent / 'gradle-default', '4.5.1\n')
        candidates = self.cleaner('gradle').scan().instances
        selected = next(item['id'] for item in candidates if item['path'] == str(first))
        self.apply(self.cleaner('gradle', instances=[selected]).scan())
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertNotIn('export GRADLE_4_5_1_HOME=', module.read_text())
        self.assertIn('export GRADLE_6_8_HOME=', module.read_text())
        self.assertIn('gradle_use()', module.read_text())
        self.assertFalse(default.exists())

    def test_last_gradle_removes_switch_code_but_keeps_user_and_jdk_settings_in_shared_block(self):
        gradle = self.sdk('gradle-6.8', 'gradle')
        module = self.write(self.home / '.config/java-dev/gradle.sh', '# >>> team-java-env managed >>>\nexport GRADLE_6_8_HOME="{}"\nexport GRADLE_DEFAULT_FILE="{}/gradle-default"\ngradle_use() {{\n  :\n}}\nexport USER_SETTING=keep\nexport JAVA_HOME=/external/jdk\n# <<< team-java-env managed <<<\n'.format(gradle, self.home / '.config/java-dev'))
        self.apply(self.cleaner('gradle').scan())
        self.assertFalse(gradle.exists())
        self.assertIn('export USER_SETTING=keep', module.read_text())
        self.assertIn('export JAVA_HOME=/external/jdk', module.read_text())
        self.assertNotIn('gradle_use()', module.read_text())
        self.assertNotIn('export GRADLE_6_8_HOME=', module.read_text())

    def test_gradle_default_path_is_read_statically_from_the_actual_module(self):
        first = self.sdk('gradle-4.5.1', 'gradle')
        second = self.sdk('gradle-6.8', 'gradle')
        default = self.write(self.home / 'custom config/gradle-default', '4.5.1\n')
        module = self.write(self.home / '.config/java-dev/gradle.sh', '# >>> team-java-env managed >>>\nexport GRADLE_4_5_1_HOME="{}"\nexport GRADLE_6_8_HOME="{}"\nexport GRADLE_DEFAULT_FILE="{}"\ngradle_use() {{ :; }}\n# <<< team-java-env managed <<<\n'.format(first, second, default))
        selected = next(item['id'] for item in self.cleaner('gradle').scan().instances if item['path'] == str(first))
        self.apply(self.cleaner('gradle', instances=[selected]).scan())
        self.assertFalse(default.exists())
        self.assertTrue(second.exists())
        self.assertIn(str(default), module.read_text())

    def test_unknown_or_other_component_instance_is_rejected_without_changes(self):
        jdk = self.sdk('jdk8', 'jdk')
        gradle = self.sdk('gradle-6.8', 'gradle')
        gid = next(item['id'] for item in self.cleaner('gradle').scan().instances if item['path'] == str(gradle))
        for selection in ([gid], ['jdk:unknown']):
            with self.subTest(selection=selection), self.assertRaises(self.tool.CleanupError):
                self.cleaner('jdk', instances=selection).scan()
        self.assertTrue(jdk.exists())
        self.assertTrue(gradle.exists())

    def test_frontend_only_scope_never_reads_unselected_sdk_configuration_paths(self):
        self.env.update(ENV_FILE='invalid relative Java config', ASDF_DATA_DIR='invalid relative asdf', SDKMAN_DIR='invalid relative sdkman')
        root = self.home / '.nvm'
        self.write(root / 'nvm.sh')
        self.snapshot_marker(root, 'nvm')
        self.apply(self.cleaner('nvm').scan())
        self.assertFalse(root.exists())

    def test_frontend_marker_cannot_authorize_a_broad_user_directory(self):
        root = self.home / 'Documents'
        self.env['NVM_DIR'] = str(root)
        self.write(root / 'nvm.sh')
        self.snapshot_marker(root, 'nvm')
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner('nvm').scan()
        self.assertTrue((root / 'nvm.sh').exists())

    def test_instance_scope_preserves_legacy_backup_outside_selected_instance(self):
        jdk = self.sdk('jdk8', 'jdk')
        backup = self.write(self.home / '.config/java-dev/env.sh.bak', '# 由 config-jdk.sh 管理；可重复 source。\nexport JAVA_HOME="/external/jdk"\n' + LEGACY_PATH_FIXTURE)
        selected = next(item['id'] for item in self.cleaner('jdk').scan().instances if item['path'] == str(jdk))
        self.apply(self.cleaner('jdk', instances=[selected]).scan())
        self.assertFalse(jdk.exists())
        self.assertTrue(backup.exists())

    def test_stale_instance_id_rejects_replaced_application_at_same_path(self):
        app = self.idea('selected.app', 'IdeaIC2024.3')
        selected = self.cleaner('idea').scan().instances[0]['id']
        (app / 'Contents/Resources/product-info.json').write_text(json.dumps(dict(dataDirectoryName='IdeaIC2026.1')))
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner('idea', instances=[selected]).scan()
        self.assertTrue(app.exists())

    def test_stale_idea_id_rejects_executable_replacement_with_unchanged_metadata_and_bytes(self):
        app = self.idea('selected.app', 'IdeaIC2024.3')
        selected = self.cleaner('idea').scan().instances[0]['id']
        executable = app / 'Contents/MacOS/idea'
        content = executable.read_bytes()
        old_inode = executable.stat().st_ino
        executable.rename(executable.with_name('old-idea'))
        executable.write_bytes(content)
        self.assertNotEqual(executable.stat().st_ino, old_inode)
        with self.assertRaises(self.tool.CleanupError):
            self.cleaner('idea', instances=[selected]).scan()
        self.assertTrue(app.exists())
        self.assertEqual(executable.read_bytes(), content)

    def node(self, root, version, owned=True):
        path = root / 'versions/node' / version
        self.write(path / 'bin/node', 'must never execute')
        self.write(path / 'bin/npm')
        if owned:
            self.mark(path, 'node')
        return path

    def test_owned_node_global_packages_removed_but_external_version_and_nvm_load_remain(self):
        root = self.home / '.nvm'
        self.write(root / 'nvm.sh', 'must never execute')
        profile = self.write(self.home / '.bash_profile', '# >>> team-frontend-env nvm >>>\nexport NVM_DIR="{}"\n. "$NVM_DIR/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(root))
        self.snapshot_marker(root, 'nvm', profile=str(profile))
        owned = self.node(root, 'v16.20.2')
        global_package = self.write(owned / 'lib/node_modules/team-cli/package.json')
        external = self.node(root, 'v22.0.0', False)
        default = self.write(root / 'alias/default', 'v16.20.2\n')
        plan = self.cleaner('nvm').scan()
        self.assertIn('全局包', plan.describe())
        self.apply(plan)
        self.assertFalse(global_package.exists())
        self.assertFalse(owned.exists())
        self.assertFalse(default.exists())
        self.assertTrue(external.exists())
        self.assertTrue((root / 'nvm.sh').exists())
        self.assertIn('team-frontend-env nvm', profile.read_text())

    def test_only_owned_node_selected_keeps_manager_and_valid_default(self):
        root = self.home / 'custom nvm'
        self.env['NVM_DIR'] = str(root)
        self.write(root / 'nvm.sh')
        profile = self.write(self.home / 'shell/startup', '# >>> team-frontend-env nvm >>>\n. "{}/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(root))
        self.mark(root, 'nvm', profile=str(profile))
        first = self.node(root, 'v14.21.3')
        second = self.node(root, 'v18.20.8')
        default = self.write(root / 'alias/default', 'v18.20.8\n')
        selected = next(item['id'] for item in self.cleaner('nvm').scan().instances if item['path'] == str(first))
        self.apply(self.cleaner('nvm', instances=[selected]).scan())
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(default.read_text(), 'v18.20.8\n')
        self.assertTrue((root / 'nvm.sh').exists())
        self.assertIn('team-frontend-env nvm', profile.read_text())

    def test_clean_owned_nvm_removes_only_recorded_profile_block(self):
        root = self.home / '.nvm'
        self.write(root / 'nvm.sh')
        block = '# >>> team-frontend-env nvm >>>\n. "{}/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(root)
        profile = self.write(self.home / 'shell/startup', 'export KEEP=yes\n' + block)
        other = self.write(self.home / '.zshrc', block)
        self.snapshot_marker(root, 'nvm', profile=str(profile))
        self.node(root, 'v10.24.1')
        self.apply(self.cleaner('nvm').scan())
        self.assertFalse(root.exists())
        self.assertEqual(profile.read_text(), 'export KEEP=yes\n')
        self.assertEqual(other.read_text(), block)

    def test_nvm_source_block_with_single_quote_path_and_default_alias_chain_is_cleaned(self):
        root = self.home / "custom nvm's"
        self.env['NVM_DIR'] = str(root)
        self.write(root / 'nvm.sh')
        quoted = "'" + str(root).replace("'", "'\\''") + "'"
        profile = self.write(self.home / '.bashrc', '# >>> team-frontend-env nvm >>>\nexport NVM_DIR={}\n. "$NVM_DIR/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(quoted))
        self.snapshot_marker(root, 'nvm', profile=str(profile))
        node = self.node(root, 'v18.20.8')
        self.write(root / 'alias/my-default', 'v18.20.8\n')
        default = self.write(root / 'alias/default', 'my-default\n')
        selected = next(item['id'] for item in self.cleaner('nvm').scan().instances if item['path'] == str(node))
        self.apply(self.cleaner('nvm', instances=[selected]).scan())
        self.assertFalse(node.exists())
        self.assertFalse(default.exists())
        self.assertTrue((root / 'alias/my-default').exists())
        # 别名用户内容保留，因此管理器和对应实际文件中的加载区块保留。
        self.assertIn('team-frontend-env nvm', profile.read_text())

    def test_nvm_recorded_profile_with_escaped_quote_is_removed_with_clean_manager(self):
        root = self.home / "custom nvm's"
        self.env['NVM_DIR'] = str(root)
        self.write(root / 'nvm.sh')
        quoted = "'" + str(root).replace("'", "'\\''") + "'"
        profile = self.write(self.home / '.bashrc', '# >>> team-frontend-env nvm >>>\nexport NVM_DIR={}\n. "$NVM_DIR/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(quoted))
        self.snapshot_marker(root, 'nvm', profile=str(profile))
        self.apply(self.cleaner('nvm').scan())
        self.assertFalse(root.exists())
        self.assertEqual(profile.read_text(), '')

    def test_custom_nvm_root_is_discovered_from_recorded_managed_shell_block(self):
        root = self.home / 'custom nvm'
        self.write(root / 'nvm.sh', 'must never execute')
        profile = self.write(self.home / '.bash_profile', '# >>> team-frontend-env nvm >>>\nexport NVM_DIR="{}"\n. "$NVM_DIR/nvm.sh"\n# <<< team-frontend-env nvm <<<\n'.format(root))
        self.snapshot_marker(root, 'nvm', profile=str(profile))
        self.apply(self.cleaner('nvm').scan())
        self.assertFalse(root.exists())
        self.assertEqual(profile.read_text(), '')

    def test_omz_user_theme_and_external_custom_plugins_keep_framework_and_load(self):
        root = self.home / '.oh-my-zsh'
        self.write(root / 'oh-my-zsh.sh')
        profile = self.write(self.home / '.zshrc', '# >>> team-frontend-env terminal-tools >>>\nsource "{}/oh-my-zsh.sh"\n# <<< team-frontend-env terminal-tools <<<\n'.format(root))
        self.mark(root, 'oh-my-zsh', profile=str(profile))
        theme = self.write(root / 'custom/themes/mine.zsh-theme', 'keep')
        custom = self.home / 'external custom'
        self.env['ZSH_CUSTOM'] = str(custom)
        plugin = custom / 'plugins/zsh-autosuggestions'
        self.write(plugin / 'zsh-autosuggestions.plugin.zsh')
        self.snapshot_marker(plugin, 'zsh-autosuggestions', profile=str(profile))
        keep = self.write(custom / 'plugins/mine/mine.plugin.zsh', 'keep')
        self.apply(self.cleaner('oh-my-zsh').scan())
        self.assertFalse(plugin.exists())
        self.assertEqual(theme.read_text(), 'keep')
        self.assertEqual(keep.read_text(), 'keep')
        self.assertTrue((root / 'oh-my-zsh.sh').exists())
        self.assertIn('terminal-tools', profile.read_text())

    def snapshot_marker(self, root, kind, **data):
        files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in root.rglob('*') if path.is_file() and not path.is_symlink() and path.name != MARKER}
        directories = [path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_dir() and not path.is_symlink()]
        self.mark(root, kind, files=files, links={}, directories=directories, **data)

    def test_omz_snapshot_with_builtin_themes_can_be_removed_but_added_theme_is_kept(self):
        root = self.home / '.oh-my-zsh'
        self.write(root / 'oh-my-zsh.sh')
        self.write(root / 'themes/builtin.zsh-theme')
        self.snapshot_marker(root, 'oh-my-zsh')
        plan = self.cleaner('oh-my-zsh').scan()
        self.assertIn(root, {item.path for item in plan.removals})
        user = self.write(root / 'themes/user.zsh-theme', 'keep')
        self.apply(self.cleaner('oh-my-zsh').scan())
        self.assertEqual(user.read_text(), 'keep')
        self.assertTrue((root / 'oh-my-zsh.sh').exists())

    def test_retained_omz_framework_still_loads_after_owned_plugin_removal(self):
        fixture = terminal_fixture.TerminalToolsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.assert_ok(fixture.run_script('install-zsh.sh'))
        self.write(fixture.home / '.oh-my-zsh/custom/themes/user.zsh-theme', 'keep')
        cleaner = self.tool.Cleaner(fixture.home, components='oh-my-zsh', environ=fixture.env, process_reader=lambda: [])
        self.apply(cleaner.scan())
        result = fixture.load_profile()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(fixture.record.read_text().splitlines(), ['framework', 'git', 'z'])

    def test_plugin_in_other_custom_root_does_not_keep_removed_active_plugin_reference(self):
        fixture = terminal_fixture.TerminalToolsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        active_custom = fixture.home / 'external-custom'
        fixture.env['ZSH_CUSTOM'] = str(active_custom)
        fixture.assert_ok(fixture.run_script('install-zsh.sh'))
        other_plugin = self.write(fixture.home / '.oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh', 'print -r -- other-root >> "$LOADED"\n')
        cleaner = self.tool.Cleaner(fixture.home, components='oh-my-zsh', environ=fixture.env, process_reader=lambda: [])
        self.apply(cleaner.scan())
        self.assertFalse((active_custom / 'plugins/zsh-autosuggestions').exists())
        self.assertTrue(other_plugin.exists())
        result = fixture.load_profile()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(fixture.record.read_text().splitlines(), ['framework', 'git', 'z'])

    def test_retained_plugin_in_active_custom_root_keeps_its_loading_reference(self):
        fixture = terminal_fixture.TerminalToolsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.assert_ok(fixture.run_script('install-zsh.sh'))
        active_custom = fixture.home / 'external-custom'
        fixture.env['ZSH_CUSTOM'] = str(active_custom)
        self.write(fixture.home / '.oh-my-zsh/custom/themes/user.zsh-theme', 'keep')
        active_plugin = self.write(active_custom / 'plugins/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh', 'print -r -- active-user-plugin >> "$LOADED"\n')
        cleaner = self.tool.Cleaner(fixture.home, components='oh-my-zsh', environ=fixture.env, process_reader=lambda: [])
        self.apply(cleaner.scan())
        self.assertFalse((fixture.home / '.oh-my-zsh/custom/plugins/zsh-autosuggestions').exists())
        self.assertTrue(active_plugin.exists())
        result = fixture.load_profile()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(fixture.record.read_text().splitlines(), ['framework', 'git', 'z', 'active-user-plugin'])

    def test_frontend_tree_change_after_preview_aborts_before_deleting_user_content(self):
        root = self.home / '.nvm'
        self.write(root / 'nvm.sh')
        self.write(root / 'existing/subdir/original.txt')
        self.snapshot_marker(root, 'nvm')
        plan = self.cleaner('nvm').scan()
        nested = self.write(root / 'existing/subdir/user.txt', 'keep')
        with self.assertRaises(self.tool.CleanupError):
            self.apply(plan)
        self.assertEqual(nested.read_text(), 'keep')

    def idea(self, name, selector):
        app = self.home / 'Applications' / name
        self.write(app / 'Contents/MacOS/idea')
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.jetbrains.intellij.ce', CFBundleExecutable='idea')))
        self.write(app / 'Contents/Resources/product-info.json', json.dumps(dict(dataDirectoryName=selector)))
        return app

    def test_idea_instance_does_not_remove_other_versions_or_shared_user_data(self):
        first = self.idea('first.app', 'IdeaIC2024.3')
        second = self.idea('second.app', 'IdeaIC2026.1')
        first_data = self.write(self.home / 'Library/Application Support/JetBrains/IdeaIC2024.3/options/editor.xml')
        other_data = self.write(self.home / 'Library/Application Support/JetBrains/IdeaIC2026.1/options/editor.xml', 'keep')
        selected = next(item['id'] for item in self.cleaner('idea').scan().instances if item['path'] == str(first))
        self.apply(self.cleaner('idea', include_idea=True, instances=[selected]).scan())
        self.assertFalse(first.exists())
        self.assertFalse(first_data.exists())
        self.assertTrue(second.exists())
        self.assertEqual(other_data.read_text(), 'keep')

    def test_retained_idea_without_selector_preserves_potentially_shared_plugins_and_data(self):
        first = self.idea('selected.app', 'IdeaIC2024.3')
        retained = self.idea('retained.app', 'unknown-selector')
        plugins = self.home / 'shared-plugins'
        shared_plugin = self.write(plugins / 'demo/lib/demo.jar', 'keep shared plugin')
        selected_data = self.write(self.home / 'Library/Application Support/JetBrains/IdeaIC2024.3/options/editor.xml', 'keep when association unknown')
        selected = next(item['id'] for item in self.cleaner('idea').scan().instances if item['path'] == str(first))
        plan = self.cleaner('idea', include_idea=True, extra_idea_plugins=[plugins], instances=[selected]).scan()
        self.apply(plan)
        self.assertFalse(first.exists())
        self.assertTrue(retained.exists())
        self.assertTrue(shared_plugin.exists(), '关联不明的保留 IDEA 可能共享此插件目录')
        self.assertTrue(selected_data.exists(), '无法排除被保留 IDEA 共享的用户数据')
        self.assertEqual(shared_plugin.read_text(), 'keep shared plugin')
        self.assertEqual(selected_data.read_text(), 'keep when association unknown')
        self.assertIn('关联不明', plan.describe())

    def iterm(self, legacy=False):
        app = self.home / 'Applications/iTerm.app'
        binary = self.write(app / 'Contents/MacOS/iTerm2')
        plist = app / 'Contents/Info.plist'
        plist.write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.googlecode.iterm2', CFBundleExecutable='iTerm2', CFBundleShortVersionString='3.7.3')))
        receipt = self.home / '.local/share/team-frontend-env/receipts/iterm2-fixture'
        data = {} if legacy else dict(app_path=str(app), bundle_identifier='com.googlecode.iterm2', bundle_version='3.7.3',
                                     code_identity='a' * 40, info_sha256=hashlib.sha256(plist.read_bytes()).hexdigest(),
                                     executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
        self.mark(receipt, 'iterm2', **data)
        return app, binary

    def test_old_iterm_receipt_and_replaced_app_are_preserved(self):
        app, binary = self.iterm(legacy=True)
        self.apply(self.cleaner('iterm2').scan())
        self.assertTrue(app.exists())
        app, binary = self.iterm()
        binary.write_text('replacement')
        self.apply(self.cleaner('iterm2').scan())
        self.assertTrue(app.exists())

    def test_iterm_host_is_never_quit_or_deleted(self):
        app, _ = self.iterm()
        self.env['TERM_PROGRAM'] = 'iTerm.app'
        plan = self.cleaner('iterm2').scan()
        with self.assertRaises(self.tool.CleanupError):
            self.apply(plan)
        self.assertTrue(app.exists())

    def test_iterm_code_identity_is_rechecked_after_confirmation(self):
        app, _ = self.iterm()
        plan = self.cleaner('iterm2').scan()
        def codesign(command, **kwargs):
            if command[1] == '--verify':
                return type('Result', (), dict(returncode=0, stdout='', stderr=''))()
            return type('Result', (), dict(returncode=0, stdout='', stderr='CDHash=' + 'b' * 40 + '\n'))()
        with mock.patch.object(self.tool.subprocess, 'run', side_effect=codesign):
            with self.assertRaises(self.tool.CleanupError):
                self.apply(plan)
        self.assertTrue(app.exists())

    def test_iterm_verified_application_removal_keeps_preferences(self):
        app, _ = self.iterm()
        preferences = self.write(self.home / 'Library/Preferences/com.googlecode.iterm2.plist', 'keep')
        plan = self.cleaner('iterm2').scan()
        def codesign(command, **kwargs):
            return type('Result', (), dict(returncode=0, stdout='', stderr='CDHash=' + 'a' * 40 + '\n'))()
        with mock.patch.object(self.tool.subprocess, 'run', side_effect=codesign):
            self.apply(plan)
        self.assertFalse(app.exists())
        self.assertEqual(preferences.read_text(), 'keep')

    def test_iterm_identity_check_does_not_stop_other_selected_components_after_app_removal(self):
        app, _ = self.iterm()
        jdk = self.sdk('jdk8', 'jdk')
        def codesign(command, **kwargs):
            if not app.exists():
                return type('Result', (), dict(returncode=1, stdout='', stderr='missing application'))()
            return type('Result', (), dict(returncode=0, stdout='', stderr='CDHash=' + 'a' * 40 + '\n'))()
        with mock.patch.object(self.tool.subprocess, 'run', side_effect=codesign):
            self.apply(self.cleaner('jdk,iterm2').scan())
        self.assertFalse(app.exists())
        self.assertFalse(jdk.exists())

    def test_plan_json_is_static_filtered_and_requires_explicit_non_tty_apply_scope(self):
        jdk = self.sdk('jdk8', 'jdk')
        self.sdk('gradle-6.8', 'gradle')
        def factory(_home, **kwargs):
            kwargs.update(environ=self.env, system_jvms=self.home / 'system/java', system_apps=self.home / 'system/apps', process_reader=lambda: [])
            return self.tool.Cleaner(self.home, **kwargs)
        with mock.patch.object(self.tool.sys, 'platform', 'darwin'), mock.patch.object(self.tool.os, 'geteuid', return_value=501), \
                mock.patch.object(self.tool.sys, 'stdin', io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.tool.main(['--plan-json', '--components', 'jdk'], cleaner_factory=factory), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan['schema'], 1)
        self.assertEqual({item['component'] for item in plan['instances']}, {'jdk'})
        self.assertTrue(jdk.exists())
        with mock.patch.object(self.tool.sys, 'stdin', io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                self.tool.main(['--apply', '--yes'], cleaner_factory=factory)
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
