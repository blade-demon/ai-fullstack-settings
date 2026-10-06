#!/usr/bin/env python3
"""维护者用 macOS 环境清理；预检后直接删除，不生成软件或配置备份。"""
import argparse
from dataclasses import dataclass, field
import datetime
import errno
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from xml.parsers.expat import ExpatError


START = "# >>> team-java-env managed >>>"
END = "# <<< team-java-env managed <<<"
VARIABLE = r"(?:JAVA_HOME|JAVA_[A-Za-z0-9_]+_HOME|JDK_HOME|JDK_[A-Za-z0-9_]+_HOME|JRE_HOME|GRADLE_HOME|GRADLE_[A-Za-z0-9_]+_HOME|GRADLE_USER_HOME)"
REFERENCE = re.compile(r"\b" + VARIABLE + r"\b")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(" + VARIABLE + r")=(.*)$")
PATH_ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?PATH=)(.*)$")
OWNERSHIP_FILE = ".team-java-env-install.json"
IDEA_PRODUCT = re.compile(r"(?:IdeaIC|IntelliJIdea|IntelliJ)[0-9]{1,4}(?:\.[0-9]+)*(?:[-.]?(?:EAP|Beta|RC)[0-9]*)?$")
IDEA_IDS = {"com.jetbrains.intellij", "com.jetbrains.intellij.ce"}
LEGACY_JDK_PATH = '''_java_dev_prefer_jdk() {
    local remaining="${PATH-}" entry cleaned='' separator='' more
    while :; do
        case "$remaining" in
            *:*) entry="${remaining%%:*}"; remaining="${remaining#*:}"; more=1 ;;
            *) entry="$remaining"; more=0 ;;
        esac
        if [ "$entry" != "$JAVA_HOME/bin" ]; then
            cleaned="${cleaned}${separator}${entry}"
            separator=':'
        fi
        [ "$more" -eq 1 ] || break
    done
    export PATH="$JAVA_HOME/bin${separator}${cleaned}"
}
_java_dev_prefer_jdk
unset -f _java_dev_prefer_jdk'''


class CleanupError(Exception):
    pass


def identity(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size, info.st_mode)


def present(path):
    return path.exists() or path.is_symlink()


def check_parents(path):
    for parent in path.parents:
        if parent.is_symlink():
            raise CleanupError("父目录是符号链接，需使用实际路径重新预览：{}".format(path))


def jdk_homes(path):
    """最多检查四层，不跟随内部目录链接，也不运行 SDK。"""
    found = []
    for directory, children, _ in os.walk(str(path), followlinks=False):
        directory = Path(directory)
        children[:] = [name for name in children if name != ".git" and not (directory / name).is_symlink()]
        if (directory / "bin/java").is_file() and (directory / "bin/javac").is_file():
            found.append(directory)
            children[:] = []
        elif len(directory.relative_to(path).parts) >= 4:
            children[:] = []
    return found


def is_gradle(path):
    return (path / "bin/gradle").is_file() and any((path / "lib").glob("gradle-launcher-*.jar"))


def dedicated_jdk(root, home):
    """支持安装包的单一外层目录，拒绝把混合资料目录当安装根。"""
    directory = root
    while directory != home:
        if home == directory / "Contents/Home":
            return directory.name.endswith(".jdk") or {child.name for child in directory.iterdir()} <= {"Contents", ".DS_Store", OWNERSHIP_FILE}
        relative = home.relative_to(directory)
        next_directory = directory / relative.parts[0]
        if {child.name for child in directory.iterdir()} - {next_directory.name, ".DS_Store", OWNERSHIP_FILE}:
            return False
        directory = next_directory
    return True


def request_idea_quit(app_path, pid, executable_path=None):
    """向已经存在且路径匹配的 PID 发正常退出请求；不启动应用或强制终止。"""
    if type(pid) is not int or pid <= 0:
        raise CleanupError("无法确定 IDEA 实例的 PID，请保存工作并正常退出后重试。")
    app_path = Path(app_path).resolve()
    executable_path = Path(executable_path or app_path / "Contents/MacOS/idea").resolve()
    try:
        relative = executable_path.relative_to(app_path).as_posix()
    except ValueError:
        raise CleanupError("IDEA 运行可执行文件不在所选应用内，未发送退出请求；请正常退出后重试。")
    if not re.fullmatch(r"Contents/(?:MacOS/idea|(?:jbr|jdk)/(?:Contents/Home/)?bin/java)", relative):
        raise CleanupError("无法确认 IDEA 运行可执行路径，未发送退出请求；请正常退出后重试。")
    script = '''ObjC.import("AppKit");
function run() {
    var running = $.NSRunningApplication.runningApplicationWithProcessIdentifier(%s);
    if (running.isNil()) throw new Error("无法定位此 PID 的运行应用，未发送退出请求");
    var bundlePath = ObjC.unwrap(running.bundleURL.path.stringByResolvingSymlinksInPath);
    var executablePath = ObjC.unwrap(running.executableURL.path.stringByResolvingSymlinksInPath);
    if (bundlePath !== %s || executablePath !== %s) {
        throw new Error("IDEA PID 的应用或可执行路径已变化，未发送退出请求");
    }
    if (!running.terminate) throw new Error("macOS 拒绝正常退出请求");
    return "requested";
}''' % (pid, json.dumps(str(app_path)), json.dumps(str(executable_path)))
    try:
        result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CleanupError("无法发送 IDEA 正常退出请求；请保存工作并正常退出后重试：{}".format(error)) from error
    if result.returncode:
        raise CleanupError("IDEA 正常退出请求失败（可能未获 Automation 权限）；请保存工作并正常退出后重试：{}".format(result.stderr.strip()))


@dataclass
class Removal:
    path: Path
    kind: str
    stamp: tuple
    system: bool = False
    ownership: tuple = ()
    content: bytes = None
    app_files: tuple = ()


@dataclass
class EmptyDirectory:
    path: Path
    node: tuple


@dataclass
class Edit:
    path: Path
    before: bytes
    after: bytes
    stamp: tuple


@dataclass
class Plan:
    home: Path
    include_system: bool
    removals: list = field(default_factory=list)
    edits: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    empty_dirs: list = field(default_factory=list)

    @staticmethod
    def verify_removal(item):
        for path, stamp, content in item.app_files:
            if not path.is_file() or identity(path) != stamp or (content is not None and path.read_bytes() != content):
                raise CleanupError("IDEA 应用标识或可执行文件在预览后发生变化，已保留：{}".format(item.path))
        if item.content is not None:
            if item.path.is_symlink() or not item.path.is_file() or item.path.read_bytes() != item.content:
                raise CleanupError("待清理的旧配置备份已变化，停止清理：{}".format(item.path))
        if not item.ownership:
            return
        marker, stamp, content = item.ownership
        if marker.is_symlink() or not marker.is_file() or identity(marker) != stamp or marker.read_bytes() != content:
            raise CleanupError("安装来源标记在预览后发生变化，停止清理：{}".format(item.path))

    @staticmethod
    def verify_empty_directory(item):
        check_parents(item.path)
        if not present(item.path):
            return False
        if item.path.is_symlink() or not item.path.is_dir() or identity(item.path)[:2] != item.node:
            raise CleanupError("工具目录在预览后发生变化，已保留：{}".format(item.path))
        return True

    def describe(self):
        lines = ["本工具安装的 JDK / Gradle 及所选 IDEA 清理计划（macOS，无备份）"]
        for item in self.removals:
            action = "删除链接" if item.path.is_symlink() else "删除 " + item.kind
            lines.append("[{}{}] {}".format(action, "，需 --include-system" if item.system and not self.include_system else "", item.path))
        lines.extend("[直接清理配置，无备份] {}".format(edit.path) for edit in self.edits)
        lines.extend("[清理后为空才删除目录] {}".format(item.path) for item in self.empty_dirs)
        lines.extend("[说明] " + note for note in self.notes)
        lines.extend("[需先处理] " + blocker for blocker in self.blockers)
        lines.append("安装、插件及配置直接删除，不生成备份，不自动回滚；请保存工作并退出相关程序。")
        return "\n".join(lines)

    def preflight(self, check_processes=True):
        if check_processes:
            for check in self.checks:
                check()
        if self.blockers:
            raise CleanupError("存在无法安全处理的项目，尚未执行任何修改：\n" + "\n".join(self.blockers))
        if not self.include_system and any(item.system for item in self.removals):
            raise CleanupError("发现系统安装；重新预览并加 --include-system 才能执行，尚未修改。")
        for edit in self.edits:
            check_parents(edit.path)
            if edit.path.is_symlink() or not edit.path.is_file() or identity(edit.path) != edit.stamp or edit.path.read_bytes() != edit.before:
                raise CleanupError("配置在预览后发生变化，请重新预览：{}".format(edit.path))
            if not os.access(str(edit.path.parent), os.W_OK):
                raise CleanupError("配置目录不可写，已保留：{}".format(edit.path))
        for item in self.removals:
            check_parents(item.path)
            self.verify_removal(item)
            if not present(item.path) or identity(item.path) != item.stamp:
                raise CleanupError("删除目标在预览后发生变化，请重新预览：{}".format(item.path))
            if not item.system and not os.access(str(item.path.parent), os.W_OK):
                raise CleanupError("安装目录不可写，已保留：{}".format(item.path))
        for item in self.empty_dirs:
            self.verify_empty_directory(item)

    def apply(self):
        self.preflight()
        if not (self.removals or self.edits or self.empty_dirs):
            print("扫描范围内没有需要清理的内容。")
            return
        log_root = self.home / "Library/Logs/team-java-env/cleanup"
        check_parents(log_root / "placeholder")
        log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        record = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=str(log_root)))
        report = record / "report.txt"
        report.write_text(self.describe() + "\n", encoding="utf-8")
        report.chmod(0o600)
        print("清理记录（不含配置副本）：{}".format(report))

        try:
            self.preflight()
            for item in self.removals:
                for check in self.checks:
                    check()
                if not present(item.path):
                    continue  # 目标可能随同一批计划中的父目录一起删除。
                check_parents(item.path)
                self.verify_removal(item)
                if identity(item.path) != item.stamp:
                    raise CleanupError("删除目标发生变化，停止：{}".format(item.path))
                if item.system and not os.access(str(item.path.parent), os.W_OK):
                    result = subprocess.run(["/usr/bin/sudo", "/bin/rm", "-rf", "--", str(item.path)])
                    if result.returncode:
                        raise CleanupError("系统目录删除失败：{}".format(item.path))
                elif item.path.is_symlink() or item.path.is_file():
                    item.path.unlink()
                else:
                    shutil.rmtree(str(item.path))
                if present(item.path):
                    raise CleanupError("删除后目标仍存在：{}".format(item.path))
                print("已删除：{}".format(item.path))
            for edit in self.edits:
                if any(item.path in edit.path.parents for item in self.removals):
                    continue  # 随已明确选择的安装或用户缓存一起直接删除。
                check_parents(edit.path)
                if edit.path.is_symlink() or identity(edit.path) != edit.stamp or edit.path.read_bytes() != edit.before:
                    raise CleanupError("配置在卸载期间发生变化，停止：{}".format(edit.path))
                fd, temporary = tempfile.mkstemp(prefix=edit.path.name + ".cleanup.", dir=str(edit.path.parent))
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(edit.after)
                    shutil.copymode(str(edit.path), temporary)
                    os.replace(temporary, str(edit.path))
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                print("已清理配置：{}".format(edit.path))
            for item in self.empty_dirs:
                if not self.verify_empty_directory(item):
                    continue
                try:
                    item.path.rmdir()
                    print("已删除空工具目录：{}".format(item.path))
                except OSError as error:
                    if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                        raise
                    print("目录仍有内容，已保留：{}".format(item.path))
        except (OSError, CleanupError) as error:
            with report.open("a", encoding="utf-8") as output:
                output.write("\n失败，可能已有部分变更：{}\n".format(error))
            raise CleanupError("{}；详细记录：{}".format(error, report)) from error
        with report.open("a", encoding="utf-8") as output:
            output.write("\n计划内操作完成。\n")
        print("计划内清理完成；新开终端后重新扫描，任意自定义目录不属于全盘自动搜索范围。")


class Cleaner:
    def __init__(self, home, system_jvms=Path("/Library/Java/JavaVirtualMachines"),
                 environ=None, include_system=False, remove_caches=False,
                 extra_jdks=(), extra_gradles=(), extra_profiles=(), include_idea=False,
                 extra_idea_apps=(), extra_idea_plugins=(), system_apps=Path("/Applications"),
                 process_reader=None, include_idea_apps=False, quit_requester=None, quit_timeout=30):
        self.home = Path(home).resolve()
        if self.home == Path("/"):
            raise CleanupError("HOME 不能是根目录。")
        self.system_jvms = Path(system_jvms)
        self.environ = dict(os.environ if environ is None else environ)
        self.remove_caches = remove_caches
        self.extra_jdks = extra_jdks
        self.extra_gradles = extra_gradles
        self.extra_profiles = extra_profiles
        self.plan = Plan(self.home, include_system)
        self.bin_paths = set()
        self.include_idea = include_idea
        self.include_idea_apps = include_idea_apps or include_idea
        self.extra_idea_apps = extra_idea_apps
        self.extra_idea_plugins = extra_idea_plugins
        self.system_apps = Path(system_apps)
        self.process_reader = process_reader or self.read_processes
        self.quit_requester = quit_requester or request_idea_quit
        self.quit_timeout = quit_timeout
        if extra_idea_apps and not self.include_idea_apps:
            raise CleanupError("自定义 IDEA 应用须同时使用 --include-idea-apps 或 --include-idea。")
        if extra_idea_plugins and not include_idea:
            raise CleanupError("自定义 IDEA 插件目录须同时使用 --include-idea。")

    def path(self, value):
        value = str(value).replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
        if value == "~" or value.startswith("~/"):
            value = str(self.home) + value[1:]
        if not value.startswith("/") or "$" in value or "\x00" in value:
            raise CleanupError("只接受明确的绝对路径：{}".format(value))
        return Path(os.path.abspath(value))

    def safe_root(self, path):
        protected = {self.home, *self.home.parents, Path("/Library"), Path("/Library/Java"),
                     self.system_jvms, Path("/opt"), Path("/usr"), Path("/usr/local")}
        protected.update(self.home / name for name in (".local", ".local/share", ".local/share/java-dev", ".sdkman", ".sdkman/candidates", ".asdf", ".asdf/installs", ".local/share/mise", ".local/share/mise/installs", ".gradle", ".jdks", ".config", "Library", "Library/Java", "Library/Java/JavaVirtualMachines", "Library/Caches", "Library/Logs", "Applications", "Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music", "Public"))
        if path in protected or any(part.endswith(".app") for part in path.parts) or str(path).startswith(("/System/", "/usr/bin/")):
            raise CleanupError("拒绝删除宽泛目录、系统组件或应用内置运行时：{}".format(path))
        if any((path / name).exists() for name in (".git", "build.gradle", "build.gradle.kts", "pom.xml", "settings.gradle", "settings.gradle.kts")):
            raise CleanupError("目录包含项目文件，拒绝作为 SDK 删除：{}".format(path))
        check_parents(path)

    def add_sdk(self, path, kind, system=False, explicit=False):
        path = self.path(path)
        if any(item.kind == "IDEA 应用" and item.path in path.parents for item in self.plan.removals):
            self.bin_paths.add(str(path / "bin"))
            return True  # IDEA 自带 JBR 随确认过的应用一起删除。
        root = self.owned_sdk_root(path, kind)
        if root is None:
            if present(path):
                self.plan.notes.append("保留非本工具安装或来源未确认的 {}：{}".format(kind, path))
            return False
        path = root
        system = self.system_jvms in path.parents
        try:
            self.safe_root(path)
            if path.is_symlink():
                self.plan.notes.append("只删除链接，不跟随外部目标：{} -> {}".format(path, os.readlink(str(path))))
                homes = []
            elif kind == "JDK":
                homes = jdk_homes(path)
                if len(homes) != 1:
                    raise CleanupError("无法确认唯一 JDK 的目录，已保留：{}".format(path))
                if not dedicated_jdk(path, homes[0]):
                    raise CleanupError("JDK 外层目录含其他资料，拒绝整体删除：{}".format(path))
            else:
                homes = []
                if not is_gradle(path):
                    raise CleanupError("无法确认 Gradle 安装的目录，已保留：{}".format(path))
            if not any(item.path == path for item in self.plan.removals):
                marker = path / OWNERSHIP_FILE
                self.plan.removals.append(Removal(path, kind, identity(path), system,
                                                  (marker, identity(marker), marker.read_bytes())))
            self.bin_paths.add(str(path / "bin"))
            self.bin_paths.update(str(home / name) for home in homes for name in ("bin", "jre/bin"))
            return True
        except CleanupError as error:
            if explicit:
                raise
            self.plan.blockers.append(str(error))
        return False

    def owned_sdk_root(self, path, kind):
        """只有有效来源标记才能认领；不沿目录链接认领其外部目标。"""
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            return None
        for root in (path, *path.parents):
            marker = root / OWNERSHIP_FILE
            if not marker.is_file() or marker.is_symlink():
                continue
            try:
                if marker.stat().st_size > 4096:
                    continue
                data = json.loads(marker.read_text(encoding="utf-8"))
                if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 1 and data.get("tool") == "team-java-env" and data.get("kind") == kind.lower():
                    return root
            except (OSError, ValueError, UnicodeError):
                continue
        return None

    @staticmethod
    def idea_jdk_metadata(path):
        if not (path.name.startswith(".") and path.name.endswith(".intellij") and path.is_file() and not path.is_symlink()):
            return False
        try:
            if path.stat().st_size > 65536:
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            return (isinstance(data, dict) and isinstance(data.get("jdk_version"), str)
                    and str(data.get("jdk_version_major", "")).isdigit()
                    and isinstance(data.get("packages"), list) and "product" in data and "vendor" in data)
        except (OSError, ValueError, UnicodeError):
            return False

    def container(self, path, kind, pattern="*", system=False):
        if not present(path):
            return
        try:
            check_parents(path / "placeholder")
            for child in sorted(path.glob(pattern)):
                if child.name == ".DS_Store":
                    continue
                if kind == "JDK" and self.idea_jdk_metadata(child):
                    self.plan.notes.append("保留 IDEA JDK 辅助 JSON 文件：{}".format(child))
                    continue
                self.add_sdk(child, kind, system)
        except (OSError, CleanupError) as error:
            self.plan.blockers.append(str(error))

    def discover_assignment(self, name, value, path):
        # 不求值命令替换，只解析独立赋值中的绝对路径或 HOME 引用。
        try:
            values = shlex.split(value, comments=True)
        except ValueError as error:
            raise CleanupError("变量赋值无法安全解析：{}".format(path)) from error
        command_substitution = re.fullmatch(r"\$\([^()\n]+\)|\"\$\([^()\n]+\)\"", value.strip())
        if len(values) != 1 and not command_substitution:
            raise CleanupError("Java/Gradle 赋值与其他命令或变量在同一行，请先拆分：{}".format(path))
        if len(values) != 1 or not values[0] or command_substitution:
            return False
        expanded = values[0].replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
        if "$" in expanded or "`" in expanded:
            return False
        candidate = self.path(expanded)
        if name == "GRADLE_USER_HOME":
            return False  # 用户缓存可能被其他 Gradle 版本共用。
        return self.add_sdk(candidate, "Gradle" if name.startswith("GRADLE") else "JDK")

    def strip_legacy_jdk_path(self, text, path, discover=True):
        lines = text.splitlines(keepends=True)
        expected = [line.strip() for line in LEGACY_JDK_PATH.splitlines()]
        index = 1
        while index + len(expected) <= len(lines):
            if [line.strip() for line in lines[index:index + len(expected)]] == expected:
                assignment = ASSIGNMENT.fullmatch(lines[index - 1].rstrip("\r\n"))
                if assignment and assignment.group(1) == "JAVA_HOME":
                    try:
                        lexer = shlex.shlex(assignment.group(2), posix=True, punctuation_chars=";&|<>()")
                        lexer.whitespace_split = True
                        lexer.commenters = ""
                        values = list(lexer)
                    except ValueError:
                        values = []
                    if (len(values) != 1
                            or not values[0].startswith(("/", "$HOME/", "${HOME}/", "~/"))
                            or "$" in values[0].replace("${HOME}", "").replace("$HOME", "") or "`" in values[0]):
                        index += 1
                        continue
                    if discover:
                        self.discover_assignment(*assignment.groups(), path)
                    start = index - 1
                    if start > 0 and lines[start - 1].strip() == "# 由 config-jdk.sh 管理；可重复 source。":
                        start -= 1
                    del lines[start:index + len(expected)]
                    if discover:
                        self.plan.notes.append("识别并清理旧版 JDK PATH 配置：{}".format(path))
                    index = max(1, start)
                    continue
            index += 1
        return "".join(lines)

    def clean_config(self, path):
        check_parents(path)
        if path.is_symlink() or not path.is_file():
            raise CleanupError("配置不是普通文件，已保留：{}".format(path))
        before = path.read_bytes()
        text = before.decode("utf-8")
        result = []
        managed = False
        complex_context = False
        env_files = {self.home / ".config/java-dev" / name for name in ("env.sh", "jdk.sh", "gradle.sh")}
        env_root = self.path(self.environ.get("ENV_FILE", str(self.home / ".config/java-dev/env.sh"))).parent
        env_files.update(env_root / name for name in ("env.sh", "jdk.sh", "gradle.sh"))
        env_files.update(self.path(self.environ[key]) for key in ("ENV_FILE", "JDK_ENV_FILE", "GRADLE_ENV_FILE") if self.environ.get(key))
        env_files.update(item.path for item in self.plan.removals if item.kind == "旧版工具配置备份")
        shared_profile = path.name in (".zshenv", ".zprofile", ".zshrc", ".zlogin", ".bash_profile", ".bash_login", ".bashrc", ".profile")
        shared_profile = shared_profile or path in {self.path(value) for value in self.extra_profiles}
        if self.environ.get("SHELL_PROFILE"):
            shared_profile = shared_profile or path == self.path(self.environ["SHELL_PROFILE"])
        dedicated_environment = path in env_files and not shared_profile
        if dedicated_environment:
            text = self.strip_legacy_jdk_path(text, path)
            if re.search(r"(?m)^\s*_java_dev_prefer_jdk\(\)\s*\{", text):
                raise CleanupError("旧版 PATH 函数已改写或结构不完整，原文件保留：{}".format(path))
        removed_variables = set()
        preserved_variables = set()
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped == START:
                if managed:
                    raise CleanupError("受管区块嵌套：{}".format(path))
                managed = True
                continue
            if stripped == END:
                if not managed:
                    raise CleanupError("受管区块标记不完整：{}".format(path))
                managed = False
                continue
            if managed and dedicated_environment:
                assignment = ASSIGNMENT.match(line.rstrip("\r\n"))
                if assignment:
                    self.discover_assignment(*assignment.groups(), path)
                continue
            if not stripped or stripped.startswith("#"):
                result.append(line)
                continue
            cleanup_context = managed
            references = set(REFERENCE.findall(line))
            related = bool(references) or any(str(env_file) in line for env_file in env_files)
            assignment = ASSIGNMENT.match(line.rstrip("\r\n"))
            if assignment:
                try:
                    owned = self.discover_assignment(*assignment.groups(), path)
                except CleanupError:
                    if cleanup_context or any(str(item.path) in line for item in self.plan.removals):
                        raise
                    owned = False
                if not cleanup_context and not owned:
                    removed_variables.discard(assignment.group(1))
                    preserved_variables.add(assignment.group(1))
                    result.append(line)
                    continue
                if complex_context or re.search(r"[;&|]", line):
                    raise CleanupError("Java/Gradle 配置包含复杂 Shell 逻辑，请先手工整理：{}".format(path))
                if assignment.group(1) not in preserved_variables:
                    removed_variables.add(assignment.group(1))
                continue
            path_line = PATH_ASSIGNMENT.match(line.rstrip("\r\n"))
            if path_line:
                prefix, value = path_line.groups()
                path_related = bool(references if cleanup_context else references & removed_variables) or any(binary in line for binary in self.bin_paths)
                quote = value[0] if value and value[0] in "\"'" else ""
                if quote and value.endswith(quote):
                    value = value[1:-1]
                elif quote or re.search(r"\s|[;`()]|\\|[&|]", value):
                    if path_related:
                        raise CleanupError("PATH 配置无法安全拆分，请先手工整理：{}".format(path))
                    result.append(line)
                    continue
                if re.search(r"[`()\\]|\$\(|[;&|]", value) or (quote and quote in value):
                    if path_related:
                        raise CleanupError("PATH 包含命令替换或复杂引号，请先手工整理：{}".format(path))
                    result.append(line)
                    continue
                entries = value.split(":")
                kept = []
                for entry in entries:
                    expanded = entry.replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
                    entry_references = set(REFERENCE.findall(entry))
                    if (entry_references if cleanup_context else entry_references & removed_variables) or expanded in self.bin_paths:
                        continue
                    kept.append(entry)
                if kept != entries:
                    if complex_context:
                        raise CleanupError("PATH 位于复杂 Shell 逻辑中，请先手工整理：{}".format(path))
                    if kept:
                        result.append(prefix + quote + ":".join(kept) + quote + ("\n" if line.endswith("\n") else ""))
                    continue
                result.append(line)
                continue
            if re.search(r"(^|\s)(if|for|while|case|function|select)\b|\(\)\s*\{|<<|\\\s*$", line):
                complex_context = True
            if stripped.startswith((". ", "source ")):
                source_is_environment = False
                source_path = None
                try:
                    tokens = shlex.split(stripped, comments=True)
                    if len(tokens) == 2:
                        source_path = self.path(tokens[1])
                        source_is_environment = source_path in env_files
                except ValueError:
                    pass
                except CleanupError:
                    if related:
                        raise
                if source_is_environment:
                    target_removed = any(item.path == source_path or item.path in source_path.parents for item in self.plan.removals)
                    if present(source_path) and not target_removed:
                        # 留存用户设置的环境/共享文件仍需通过原入口加载。
                        result.append(line)
                        continue
                    if complex_context:
                        raise CleanupError("加载环境文件位于复杂逻辑中：{}".format(path))
                    continue
            if related and (cleanup_context or references & removed_variables or any(str(item.path) in line for item in self.plan.removals)):
                raise CleanupError("存在无法自动清理的 Java/Gradle 配置，请先手工整理：{}".format(path))
            result.append(line)
        if managed:
            raise CleanupError("受管区块没有结束标记：{}".format(path))
        # 旧入口标题在配置清空后可能单独留在文件尾；有后续内容时原样保留。
        index = len(result) - 1
        while index >= 0:
            if not result[index].strip():
                index -= 1
                continue
            if result[index].strip() != "# Java 开发环境":
                break
            del result[index]
            index -= 1
        after = "".join(result).encode("utf-8")
        if after != before:
            if dedicated_environment and not after.strip():
                self.plan.removals.append(Removal(path, "Java/Gradle 专属环境配置", identity(path)))
            else:
                self.plan.edits.append(Edit(path, before, after, identity(path)))

    def scan(self):
        self.scan_legacy_backup()
        if self.include_idea_apps:
            self.scan_idea()
        team = self.home / ".local/share/java-dev"
        self.container(team, "JDK", "jdk*")
        self.container(team, "Gradle", "gradle*")
        self.container(self.home / "Library/Java/JavaVirtualMachines", "JDK")
        self.container(self.system_jvms, "JDK", system=True)
        self.container(self.home / ".jdks", "JDK")
        managers = [(self.environ.get("SDKMAN_DIR", str(self.home / ".sdkman")), "candidates"),
                    (self.environ.get("ASDF_DATA_DIR", str(self.home / ".asdf")), "installs"),
                    (self.environ.get("MISE_DATA_DIR", str(self.home / ".local/share/mise")), "installs")]
        for manager, directory in managers:
            for name, kind in (("java", "JDK"), ("gradle", "Gradle")):
                self.container(self.path(manager) / directory / name, kind)
        for key, kind in (("JDK_INSTALL_DIR", "JDK"), ("JAVA_HOME", "JDK"), ("GRADLE_INSTALL_DIR", "Gradle"), ("GRADLE_HOME", "Gradle")):
            if self.environ.get(key):
                candidate = self.path(self.environ[key])
                if candidate.parts[-2:] == ("Contents", "Home"):
                    candidate = candidate.parent.parent
                self.add_sdk(candidate, kind, system=self.system_jvms in candidate.parents)
        for paths, kind in ((self.extra_jdks, "JDK"), (self.extra_gradles, "Gradle")):
            for path in paths:
                path = self.path(path)
                self.safe_root(path)
                self.add_sdk(path, kind, system=self.system_jvms in path.parents, explicit=True)
        config_root = self.path(self.environ.get("ENV_FILE", str(self.home / ".config/java-dev/env.sh"))).parent
        profiles = {config_root / name for name in ("env.sh", "jdk.sh", "gradle.sh")}
        profiles.update(self.home / name for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin", ".bash_profile", ".bash_login", ".bashrc", ".profile"))
        if self.environ.get("ZDOTDIR"):
            profiles.update(self.path(self.environ["ZDOTDIR"]) / name for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin"))
        profiles.update(self.path(self.environ[key]) for key in ("ENV_FILE", "JDK_ENV_FILE", "GRADLE_ENV_FILE", "SHELL_PROFILE") if self.environ.get(key))
        profiles.update(self.path(path) for path in self.extra_profiles)
        # 静态收敛 SDK 路径与加载关系，避免排序靠前的入口引用稍后被删的模块。
        previous_state = None
        for _ in range(len(profiles) + 2):
            self.plan.edits = []
            for path in sorted(profiles):
                if present(path):
                    try:
                        self.clean_config(path)
                    except (OSError, UnicodeError, CleanupError) as error:
                        self.plan.blockers.append(str(error))
            state = (frozenset(item.path for item in self.plan.removals),
                     tuple((edit.path, edit.after) for edit in self.plan.edits),
                     frozenset(self.bin_paths))
            if state == previous_state:
                break
            previous_state = state
        self.plan.notes.append("保留 Gradle 共享用户配置、缓存和 Wrapper 分发，以及版本管理器的原有选择配置。")
        # 父目录一旦在计划中，内部子目录不再单独删除。
        unique = []
        for item in sorted(self.plan.removals, key=lambda item: (len(item.path.parts), str(item.path))):
            if not any(parent.path == item.path or parent.path in item.path.parents for parent in unique):
                unique.append(item)
        self.plan.removals = unique
        self.plan_empty_tool_directories()
        self.plan.blockers = list(dict.fromkeys(self.plan.blockers))
        self.plan.notes = list(dict.fromkeys(self.plan.notes))
        self.plan.notes.append("保留业务项目、系统 Java 占位程序、其他 SDKMAN 工具及 SDK 下载压缩包。")
        if self.include_idea_apps and not self.include_idea:
            self.plan.notes.append("仅删除所选 IDEA 软件；保留 IDEA 用户配置、SDK 登记、用户插件、缓存及 Local History。")
        elif not self.include_idea:
            self.plan.notes.append("保留 IDEA 与其内置 JBR；清理 IDEA 应用、配置和插件须加 --include-idea。")
        self.plan.notes.append("/etc 全局配置、launchctl 环境、安装器收据及未列出的自定义位置需另行核对。")
        return self.plan

    def scan_legacy_backup(self):
        path = self.home / ".config/java-dev/env.sh.bak"
        if not path.is_file() or path.is_symlink():
            return
        try:
            check_parents(path)
            if path.stat().st_size > 65536:
                return
            before = path.read_bytes()
            text = before.decode("utf-8")
            if not text.lstrip().startswith("# 由 config-jdk.sh 管理；可重复 source。"):
                return
            if self.strip_legacy_jdk_path(text, path, discover=False).strip():
                return
            self.plan.removals.append(Removal(path, "旧版工具配置备份", identity(path), content=before))
        except (OSError, UnicodeError, CleanupError):
            self.plan.notes.append("旧配置备份无法完整确认，已保留：{}".format(path))

    def plan_empty_tool_directories(self):
        removals = {item.path for item in self.plan.removals}
        for path in (self.home / ".config/java-dev", self.home / ".local/share/java-dev"):
            if not present(path):
                continue
            try:
                check_parents(path)
                if path.is_symlink() or not path.is_dir():
                    self.plan.notes.append("工具目录不是普通目录，已保留：{}".format(path))
                    continue
                if any(child not in removals for child in path.iterdir()):
                    self.plan.notes.append("工具目录内仍有保留内容，目录将保留：{}".format(path))
                    continue
                self.plan.empty_dirs.append(EmptyDirectory(path, identity(path)[:2]))
            except (OSError, CleanupError):
                self.plan.notes.append("工具目录无法安全检查，已保留：{}".format(path))

    @staticmethod
    def read_processes():
        result = subprocess.run(["/bin/ps", "-ax", "-ww", "-o", "pid=", "-o", "command="], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if result.returncode:
            raise CleanupError("无法检查 IDEA 进程，停止清理：" + result.stderr.strip())
        return result.stdout.splitlines()

    def running_idea_instances(self):
        instances = []
        for line in self.process_reader():
            parsed = re.match(r"^\s*([0-9]+)\s+(.*)$", line)
            pid, command = (int(parsed.group(1)), parsed.group(2)) if parsed else (None, line.strip())
            selector = re.search(r"-Didea\.paths\.selector=(?:IdeaIC|IntelliJIdea|IntelliJ)[0-9]", command)
            app = re.match(r"^((/.*?\.app)/Contents/(MacOS/idea|(?:jbr|jdk)/(?:Contents/Home/)?bin/java))(?:\s|$)", command)
            if app and (app.group(3) == "MacOS/idea" or selector):
                path = Path(app.group(2)).resolve()
                executable = Path(app.group(1)).resolve()
                # 其他 JetBrains 应用即使可执行文件同名，也不属于 IDEA 范围。
                try:
                    with (path / "Contents/Info.plist").open("rb") as source:
                        metadata = plistlib.load(source)
                    if isinstance(metadata, dict) and metadata.get("CFBundleIdentifier") not in IDEA_IDS:
                        continue
                except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
                    pass  # 无法识别的运行实例保守阻止完整 IDEA 配置清理。
                instances.append((path, pid, executable))
            elif selector:
                instances.append((None, pid, None))
        return instances

    def selected_idea_apps(self):
        return {item.path.resolve() for item in self.plan.removals
                if item.kind == "IDEA 应用" and not item.path.is_symlink()}

    def ensure_idea_stopped(self):
        selected = self.selected_idea_apps()
        if any(self.include_idea or app is None or app in selected for app, _, _ in self.running_idea_instances()):
            raise CleanupError("所选 IDEA 仍在运行，请保存工作并正常退出后重试；尚未执行清理。")

    def quit_selected_idea(self):
        """只在最终确认后调用；任一实例未退出则不执行任何清理。"""
        if not self.include_idea_apps:
            return False
        selected = self.selected_idea_apps()
        instances = self.running_idea_instances()
        if any(app is None or (self.include_idea and app not in selected) for app, _, _ in instances):
            raise CleanupError("另有未选定或无法定位的 IDEA 正在使用配置；请保存工作并正常退出后重试，尚未执行清理。")
        running = [(app, pid, executable) for app, pid, executable in instances if app in selected]
        if any(pid is None for _, pid, _ in running):
            raise CleanupError("无法精确确定所选 IDEA 的 PID；请保存工作并正常退出后重试，尚未执行清理。")
        for app, pid, executable in running:
            print("请求 IDEA 正常退出：{}（PID {}）；若出现保存对话框，请处理后退出。".format(app, pid))
            try:
                self.quit_requester(app, pid, executable)
            except (CleanupError, OSError, subprocess.TimeoutExpired) as error:
                raise CleanupError("IDEA 未能正常退出，软件和清理目标均保留；请保存工作并正常退出后重试：{}".format(error)) from error
        deadline = time.monotonic() + self.quit_timeout
        while running:
            if not any(app is None or app in selected for app, _, _ in self.running_idea_instances()):
                break
            if time.monotonic() >= deadline:
                raise CleanupError("IDEA 正常退出超时或已取消（可能仍有保存对话框）；软件和清理目标均保留，请正常退出后重试。")
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        self.ensure_idea_stopped()
        return bool(running)

    def idea_path_guard(self, path):
        protected = {self.home, *self.home.parents, self.system_apps, Path("/Library"),
                     self.home / "Applications"}
        protected.update(self.home / name for name in ("Desktop", "Documents", "Downloads", ".config", ".config/JetBrains", ".local", ".local/share", ".gradle", ".sdkman", ".asdf", ".jdks", "Library", "Library/Application Support", "Library/Application Support/JetBrains", "Library/Application Support/JetBrains/Toolbox", "Library/Preferences", "Library/Caches", "Library/Caches/JetBrains", "Library/Logs", "Library/Logs/JetBrains", "Library/Saved Application State", "Library/Containers", "Library/Group Containers"))
        if path in protected or any(parent.suffix == ".app" for parent in path.parents) or str(path).startswith(("/System/", "/usr/")):
            raise CleanupError("拒绝把宽泛目录、系统组件或应用内部目录作为 IDEA 清理目标：{}".format(path))
        check_parents(path)
        if any((path / name).exists() for name in (".git", ".idea", "build.gradle", "pom.xml")):
            raise CleanupError("IDEA 清理目录含业务项目文件，已保留：{}".format(path))

    def add_idea_data(self, path, kind, explicit=False):
        path = self.path(path)
        self.idea_path_guard(path)
        if not present(path):
            return
        if path.is_symlink():
            raise CleanupError("IDEA 配置或插件路径是符号链接，需核对实际专属目录：{}".format(path))
        if explicit:
            if not path.is_dir():
                raise CleanupError("IDEA 插件位置不是目录：{}".format(path))
            for child in path.iterdir():
                if child.name == ".DS_Store" or child.is_symlink():
                    continue
                if child.is_file() and child.suffix == ".jar":
                    continue
                if child.is_dir() and (any((child / "lib").glob("*.jar")) or (child / "META-INF/plugin.xml").is_file()):
                    continue
                raise CleanupError("自定义 IDEA 插件目录含未识别资料，拒绝整体删除：{}".format(child))
        self.plan.removals.append(Removal(path, kind, identity(path), self.system_apps in path.parents or str(path).startswith("/Library/")))

    def add_idea_app(self, path, explicit=False):
        path = self.path(path)
        self.idea_path_guard(path)
        if not present(path):
            return
        if path.suffix != ".app" or not path.is_dir():
            raise CleanupError("不是可识别的 IDEA 应用包：{}".format(path))
        plist = path / "Contents/Info.plist"
        if plist.is_symlink():
            raise CleanupError("IDEA 应用标识是符号链接，已保留：{}".format(plist))
        try:
            content = plist.read_bytes()
            metadata = plistlib.loads(content)
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as error:
            raise CleanupError("无法识别 IDEA 应用标识：{}".format(path)) from error
        if not isinstance(metadata, dict) or metadata.get("CFBundleIdentifier") not in IDEA_IDS:
            if explicit:
                raise CleanupError("应用标识不属于 IntelliJ IDEA，已保留：{}".format(path))
            return
        if metadata.get("CFBundleExecutable") != "idea" or not (path / "Contents/MacOS/idea").is_file():
            raise CleanupError("IDEA 应用包不完整，已保留：{}".format(path))
        resolved = path.resolve()
        if path.is_symlink():
            self.plan.notes.append("IDEA 应用只删除链接，不跟随外部目标：{} -> {}".format(path, resolved))
        executable = path / "Contents/MacOS/idea"
        self.plan.removals.append(Removal(path, "IDEA 应用", identity(path), self.system_apps in path.parents,
                                          app_files=((plist, identity(plist), content), (executable, identity(executable), None))))

    def scan_idea_apps(self):
        for root in (self.home / "Applications", self.system_apps):
            if not present(root):
                continue
            try:
                check_parents(root / "placeholder")
                for path in sorted(root.glob("*.app")):
                    try:
                        self.add_idea_app(path)
                    except CleanupError as error:
                        if "intellij" in path.name.lower() or "idea" in path.name.lower():
                            self.plan.blockers.append(str(error))
            except (OSError, CleanupError) as error:
                self.plan.blockers.append(str(error))
        apps = list(self.extra_idea_apps)
        if self.environ.get("IDEA_APP"):
            apps.append(self.environ["IDEA_APP"])
        for path in apps:
            self.add_idea_app(path, explicit=True)

    def scan_idea(self):
        self.plan.checks.append(self.ensure_idea_stopped)
        self.scan_idea_apps()
        if not self.include_idea:
            return
        roots = [(self.home / "Library/Application Support/JetBrains", "IDEA 用户配置与插件"),
                 (self.home / "Library/Application Support", "IDEA 旧版插件"),
                 (self.home / "Library/Preferences", "IDEA 旧版用户配置")]
        if self.remove_caches:
            roots.extend((self.home / folder / suffix, "IDEA 缓存、日志与本地历史")
                         for folder in ("Library/Caches", "Library/Logs") for suffix in ("JetBrains", ""))
        else:
            self.plan.notes.append("保留 IDEA 缓存、日志及 Local History；需要直接删除时加 --remove-caches。")
        for root, kind in roots:
            if not present(root):
                continue
            try:
                check_parents(root / "placeholder")
                for path in sorted(root.iterdir()):
                    if IDEA_PRODUCT.fullmatch(path.name):
                        self.add_idea_data(path, kind)
            except (OSError, CleanupError) as error:
                self.plan.blockers.append(str(error))
        for identifier in IDEA_IDS:
            path = self.home / "Library/Preferences" / (identifier + ".plist")
            if present(path):
                try:
                    self.add_idea_data(path, "IDEA 专属偏好配置")
                except CleanupError as error:
                    self.plan.blockers.append(str(error))
        for root in self.home.iterdir():
            if root.name.startswith(".") and IDEA_PRODUCT.fullmatch(root.name[1:]):
                for name, kind in (("config", "IDEA 旧版用户配置与插件"), ("plugins", "IDEA 旧版插件")):
                    try:
                        self.add_idea_data(root / name, kind)
                    except CleanupError as error:
                        self.plan.blockers.append(str(error))
                if self.remove_caches:
                    try:
                        self.add_idea_data(root / "system", "IDEA 旧版缓存与本地历史")
                    except CleanupError as error:
                        self.plan.blockers.append(str(error))
        plugins = list(self.extra_idea_plugins)
        if self.environ.get("IDEA_PLUGINS_DIR"):
            plugins.append(self.environ["IDEA_PLUGINS_DIR"])
        for path in plugins:
            self.add_idea_data(path, "IDEA 自定义插件", explicit=True)



def verify_confirmed_scope(approved, refreshed):
    """IDEA 退出可能写配置；允许内容变化，不扩大已经确认的操作路径。"""
    previous = {(item.path, item.kind, item.system): item for item in approved.removals}
    for item in refreshed.removals:
        old = previous.get((item.path, item.kind, item.system))
        if old is None or old.stamp[:2] != item.stamp[:2] or old.ownership != item.ownership or old.app_files != item.app_files:
            raise CleanupError("IDEA 退出后清理目标发生变化；尚未执行清理，请重新运行并确认计划：{}".format(item.path))
    if not {edit.path for edit in refreshed.edits}.issubset({edit.path for edit in approved.edits}):
        raise CleanupError("IDEA 退出后出现新的配置清理目标；尚未执行清理，请重新确认计划。")
    if not {item.path for item in refreshed.empty_dirs}.issubset({item.path for item in approved.empty_dirs}):
        raise CleanupError("IDEA 退出后出现新的空目录清理目标；尚未执行清理，请重新确认计划。")


def main(argv=None, cleaner_factory=None, input_reader=None):
    parser = argparse.ArgumentParser(description="macOS 维护者测试工具：交互终端引导选择并确认；非交互默认仅预览，无备份。")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="执行计划，需输入 DELETE")
    mode.add_argument("--dry-run", action="store_true", help="只预览，不提问、不退出应用")
    parser.add_argument("--yes", action="store_true", help="仅配合 --apply 跳过输入确认")
    parser.add_argument("--include-system", action="store_true", help="包含系统 JDK 与系统 Applications 中的 IDEA，必要时逐项 sudo")
    parser.add_argument("--include-idea", action="store_true", help="直接删除 IDEA 全版本应用、配置及插件，不备份")
    parser.add_argument("--include-idea-apps", action="store_true", help="只删除 IDEA 应用，保留用户配置、SDK 登记及插件")
    parser.add_argument("--idea-app", action="append", default=[], metavar="绝对路径", help="额外 IDEA .app，可重复，须 --include-idea-apps 或 --include-idea")
    parser.add_argument("--idea-plugins-dir", action="append", default=[], metavar="绝对路径", help="额外 IDEA 专属插件目录，可重复，须 --include-idea")
    parser.add_argument("--remove-caches", action="store_true", help="包含 IDEA 时删除其缓存、日志和本地历史；Gradle 共享缓存始终保留")
    parser.add_argument("--jdk-dir", action="append", default=[], metavar="绝对路径", help="额外 JDK 查找目录，仍须有本工具来源标记，可重复")
    parser.add_argument("--gradle-dir", action="append", default=[], metavar="绝对路径", help="额外 Gradle 查找目录，仍须有本工具来源标记，可重复")
    parser.add_argument("--profile", action="append", default=[], metavar="绝对路径", help="额外 Shell 配置文件，可重复")
    args = parser.parse_args(argv)
    if args.yes and not args.apply:
        parser.error("--yes 必须与 --apply 一起使用")
    try:
        if sys.platform != "darwin":
            raise CleanupError("本工具面向 macOS；不在 Windows/Linux 上执行清理。")
        if os.geteuid() == 0:
            raise CleanupError("请以目标用户运行，不要对整个脚本使用 sudo。")
        factory = cleaner_factory or Cleaner
        read_answer = input_reader or input
        terminal = sys.stdin.isatty() and sys.stdout.isatty()
        guided = terminal and not args.dry_run and not args.yes

        def make_cleaner(include_apps=None):
            return factory(Path.home(), include_system=args.include_system,
                           remove_caches=args.remove_caches, extra_jdks=args.jdk_dir,
                           extra_gradles=args.gradle_dir, extra_profiles=args.profile,
                           include_idea=args.include_idea, extra_idea_apps=args.idea_app,
                           extra_idea_plugins=args.idea_plugins_dir,
                           include_idea_apps=args.include_idea_apps if include_apps is None else include_apps)

        if guided and not (args.include_idea or args.include_idea_apps):
            discovery = make_cleaner(True)
            discovery.scan_idea_apps()
            apps = [item.path for item in discovery.plan.removals if item.kind == "IDEA 应用"]
            if apps:
                print("检测到以下 IDEA 软件：\n" + "\n".join("  " + str(path) for path in apps))
                print("选择删除时仅包含这些应用；保留 IDEA 用户配置、SDK 登记和用户插件。")
                args.include_idea_apps = read_answer("是否删除上述 IDEA 软件？[y/N]：").strip().lower() in ("y", "yes")
            else:
                print("未在当前扫描范围发现可识别的 IDEA 软件。")
            if not args.include_idea_apps:
                print("本次保留 IDEA 软件、配置和插件；继续核对本工具 SDK 与环境配置清理计划。")
        cleaner = make_cleaner()
        plan = cleaner.scan()
        print(plan.describe())
        if not args.apply and not guided:
            print("仅预览，未修改文件。执行需加 --apply；完整重装测试加 --include-idea --include-system --remove-caches。")
            return 0
        # 系统目录、来源标记与文件保护先核对；最终确认前不退出应用。
        plan.preflight(check_processes=False)
        if not args.yes:
            if not terminal:
                raise CleanupError("非交互输入不执行删除；自动测试须明确指定 --apply --yes。")
            if read_answer("确认按上述计划永久清理软件、插件和配置（无备份）？输入 DELETE：").strip() != "DELETE":
                raise CleanupError("已取消，未执行清理。")
        plan.preflight(check_processes=False)
        if cleaner.quit_selected_idea():
            refreshed_cleaner = make_cleaner()
            refreshed = refreshed_cleaner.scan()
            verify_confirmed_scope(plan, refreshed)
            refreshed.preflight()
            print("IDEA 已正常退出；重新核对后的清理计划：\n" + refreshed.describe())
            plan = refreshed
        plan.apply()
        return 0
    except (CleanupError, OSError, subprocess.TimeoutExpired) as error:
        print("清理未完成：{}".format(error), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
