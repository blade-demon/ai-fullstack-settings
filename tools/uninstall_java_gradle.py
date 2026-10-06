#!/usr/bin/env python3
"""维护者用 macOS JDK/Gradle 清理；静态预检后才执行明确的删除计划。"""
import argparse
from dataclasses import dataclass, field
import datetime
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


START = "# >>> team-java-env managed >>>"
END = "# <<< team-java-env managed <<<"
VARIABLE = r"(?:JAVA_HOME|JAVA_[A-Za-z0-9_]+_HOME|JDK_HOME|JDK_[A-Za-z0-9_]+_HOME|JRE_HOME|GRADLE_HOME|GRADLE_[A-Za-z0-9_]+_HOME|GRADLE_USER_HOME)"
REFERENCE = re.compile(r"\b" + VARIABLE + r"\b")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(" + VARIABLE + r")=(.*)$")
PATH_ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?PATH=)(.*)$")
FORMULA = re.compile(r"(?:openjdk|gradle|graalvm)(?:@[^/\s]+)?$")
CASK = re.compile(r"(?:temurin|adoptopenjdk|zulu|corretto|liberica-jdk|liberica-jdk-full|liberica-jdk-lite|microsoft-openjdk|oracle-jdk|sapmachine-jdk|graalvm-jdk|graalvm-community-jdk|graalvm-ce-java|semeru-jdk|semeru-jdk-open|dragonwell|openjdk)(?:[0-9][A-Za-z0-9.-]*|[@-][^/\s]+)?$")
CACHE_ENTRIES = {"caches", "daemon", "native", "notifications", "jdks", "wrapper", "workers", ".tmp", "build-scan-data", "develocity", "enterprise", "kotlin", "init.d", "init.gradle", "init.gradle.kts", "gradle.properties", ".DS_Store"}


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
            return directory.name.endswith(".jdk") or {child.name for child in directory.iterdir()} <= {"Contents", ".DS_Store"}
        relative = home.relative_to(directory)
        next_directory = directory / relative.parts[0]
        if {child.name for child in directory.iterdir()} - {next_directory.name, ".DS_Store"}:
            return False
        directory = next_directory
    return True


@dataclass
class Removal:
    path: Path
    kind: str
    stamp: tuple
    system: bool = False


@dataclass
class Edit:
    path: Path
    before: bytes
    after: bytes
    stamp: tuple


@dataclass
class Plan:
    home: Path
    environ: dict
    include_system: bool
    removals: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    edits: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    cache_configs: list = field(default_factory=list)

    def describe(self):
        lines = ["JDK / Gradle 所有版本清理计划（macOS）"]
        for command, system in self.commands:
            lines.append("[卸载{}] {}".format("，需 --include-system" if system and not self.include_system else "", shlex.join(command)))
        for item in self.removals:
            action = "删除链接" if item.path.is_symlink() else "删除 " + item.kind
            lines.append("[{}{}] {}".format(action, "，需 --include-system" if item.system and not self.include_system else "", item.path))
        lines.extend("[备份并清理配置] {}".format(edit.path) for edit in self.edits)
        lines.extend("[说明] " + note for note in self.notes)
        lines.extend("[需先处理] " + blocker for blocker in self.blockers)
        lines.append("安装目录删除后无法通过配置备份恢复；请保存工作并退出 Java/Gradle/IDE 进程。")
        return "\n".join(lines)

    def preflight(self):
        if self.blockers:
            raise CleanupError("存在无法安全处理的项目，尚未执行任何修改：\n" + "\n".join(self.blockers))
        if not self.include_system and (any(item.system for item in self.removals) or any(system for _, system in self.commands)):
            raise CleanupError("发现系统安装；重新预览并加 --include-system 才能执行，尚未修改。")
        for edit in self.edits:
            check_parents(edit.path)
            if edit.path.is_symlink() or not edit.path.is_file() or identity(edit.path) != edit.stamp or edit.path.read_bytes() != edit.before:
                raise CleanupError("配置在预览后发生变化，请重新预览：{}".format(edit.path))
            if not os.access(str(edit.path.parent), os.W_OK):
                raise CleanupError("配置目录不可写，已保留：{}".format(edit.path))
        for item in self.removals:
            check_parents(item.path)
            if not present(item.path) or identity(item.path) != item.stamp:
                raise CleanupError("删除目标在预览后发生变化，请重新预览：{}".format(item.path))
            if not item.system and not os.access(str(item.path.parent), os.W_OK):
                raise CleanupError("安装目录不可写，已保留：{}".format(item.path))

    def apply(self):
        self.preflight()
        if not (self.commands or self.removals or self.edits):
            print("扫描范围内没有需要清理的内容。")
            return
        log_root = self.home / "Library/Logs/team-java-env/cleanup"
        check_parents(log_root / "placeholder")
        log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=str(log_root)))
        report = backup / "report.txt"
        report.write_text(self.describe() + "\n", encoding="utf-8")
        report.chmod(0o600)
        print("配置备份和记录：{}".format(backup))

        def save(path):
            check_parents(path)
            if path.is_symlink():
                raise CleanupError("配置备份遇到符号链接，已保留：{}".format(path))
            target = backup / "files" / str(path).lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.is_dir():
                shutil.copytree(str(path), str(target), symlinks=True)
            else:
                shutil.copy2(str(path), str(target))

        try:
            # 所有配置先备份；备份失败不会开始卸载或修改配置。
            for edit in self.edits:
                save(edit.path)
            for path in self.cache_configs:
                if not (backup / "files" / str(path).lstrip("/")).exists() or path.is_dir():
                    target = backup / "files" / str(path).lstrip("/")
                    if path.is_dir() and target.exists():
                        # 上面已备份其中的单个配置时，补齐同一目录的其他配置。
                        check_parents(path)
                        if path.is_symlink():
                            raise CleanupError("缓存配置是符号链接，已保留：{}".format(path))
                        shutil.copytree(str(path), str(target), symlinks=True, dirs_exist_ok=True)
                    else:
                        save(path)
            self.preflight()
            for command, _ in self.commands:
                print("执行：{}".format(shlex.join(command)))
                result = subprocess.run(command, env=self.environ)
                if result.returncode:
                    raise CleanupError("卸载失败（退出码 {}）：{}".format(result.returncode, shlex.join(command)))
            for item in self.removals:
                if not present(item.path):
                    continue  # Homebrew 可能已删除同一个目录或登记链接。
                check_parents(item.path)
                if identity(item.path) != item.stamp:
                    raise CleanupError("删除目标发生变化，停止：{}".format(item.path))
                if item.system and not os.access(str(item.path.parent), os.W_OK):
                    result = subprocess.run(["/usr/bin/sudo", "/bin/rm", "-rf", "--", str(item.path)])
                    if result.returncode:
                        raise CleanupError("系统目录删除失败：{}".format(item.path))
                elif item.path.is_symlink():
                    item.path.unlink()
                else:
                    shutil.rmtree(str(item.path))
                if present(item.path):
                    raise CleanupError("删除后目标仍存在：{}".format(item.path))
                print("已删除：{}".format(item.path))
            for edit in self.edits:
                if any(item.path in edit.path.parents for item in self.removals):
                    continue  # 配置已备份，随已明确选择的用户缓存一起删除。
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
        except (OSError, CleanupError) as error:
            with report.open("a", encoding="utf-8") as output:
                output.write("\n失败，可能已有部分变更：{}\n".format(error))
            raise CleanupError("{}；详细记录：{}".format(error, report)) from error
        with report.open("a", encoding="utf-8") as output:
            output.write("\n计划内操作完成。\n")
        print("计划内清理完成；新开终端后重新扫描，任意自定义目录不属于全盘自动搜索范围。")


class Cleaner:
    def __init__(self, home, system_jvms=Path("/Library/Java/JavaVirtualMachines"), brews=(),
                 environ=None, include_system=False, remove_caches=False,
                 extra_jdks=(), extra_gradles=(), extra_profiles=()):
        self.home = Path(home).resolve()
        if self.home == Path("/"):
            raise CleanupError("HOME 不能是根目录。")
        self.system_jvms = Path(system_jvms)
        self.environ = dict(os.environ if environ is None else environ)
        self.environ.update({"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1", "HOMEBREW_NO_AUTOREMOVE": "1"})
        self.brews = tuple(brews)
        self.remove_caches = remove_caches
        self.extra_jdks = extra_jdks
        self.extra_gradles = extra_gradles
        self.extra_profiles = extra_profiles
        self.plan = Plan(self.home, self.environ, include_system)
        self.bin_paths = set()
        self.cache_paths = {self.home / ".gradle"}
        self.brew_roots = set()

    def path(self, value):
        value = str(value).replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
        if value == "~" or value.startswith("~/"):
            value = str(self.home) + value[1:]
        if not value.startswith("/") or "$" in value or "\x00" in value:
            raise CleanupError("只接受明确的绝对路径：{}".format(value))
        return Path(os.path.abspath(value))

    def safe_root(self, path):
        protected = {self.home, *self.home.parents, Path("/Library"), Path("/Library/Java"),
                     self.system_jvms, Path("/opt"), Path("/opt/homebrew"), Path("/usr"), Path("/usr/local")}
        protected.update(self.home / name for name in (".local", ".local/share", ".local/share/java-dev", ".sdkman", ".sdkman/candidates", ".asdf", ".asdf/installs", ".local/share/mise", ".local/share/mise/installs", ".gradle", ".jdks", ".config", "Library", "Library/Java", "Library/Java/JavaVirtualMachines", "Library/Caches", "Library/Logs", "Applications", "Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music", "Public"))
        if path in protected or any(part.endswith(".app") for part in path.parts) or str(path).startswith(("/System/", "/usr/bin/")):
            raise CleanupError("拒绝删除宽泛目录、系统组件或应用内置运行时：{}".format(path))
        if any((path / name).exists() for name in (".git", "build.gradle", "build.gradle.kts", "pom.xml", "settings.gradle", "settings.gradle.kts")):
            raise CleanupError("目录包含项目文件，拒绝作为 SDK 删除：{}".format(path))
        check_parents(path)

    def add_sdk(self, path, kind, system=False, explicit=False):
        path = self.path(path)
        if not present(path):
            return
        resolved = path.resolve()
        brew_managed = any(part in ("Cellar", "Caskroom") for part in resolved.parts + path.parts) or str(path).startswith(("/opt/homebrew/opt/", "/usr/local/opt/"))
        if brew_managed:
            if not any(root == resolved or root in resolved.parents or root == path or root in path.parents for root in self.brew_roots):
                self.plan.blockers.append("Homebrew 安装未匹配到卸载登记，需先核对包名：{}".format(path))
            elif path.is_symlink() and self.system_jvms in path.parents:
                # 手工登记的系统链接不一定由 formula 卸载步骤删除。
                self.plan.removals.append(Removal(path, kind, identity(path), True))
                self.bin_paths.add(str(path / "Contents/Home/bin"))
            self.bin_paths.update(str(path / name) for name in ("bin", "Contents/Home/bin", "jre/bin"))
            return
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
                self.plan.removals.append(Removal(path, kind, identity(path), system))
            self.bin_paths.add(str(path / "bin"))
            self.bin_paths.update(str(home / name) for home in homes for name in ("bin", "jre/bin"))
        except CleanupError as error:
            if explicit:
                raise
            self.plan.blockers.append(str(error))

    def container(self, path, kind, pattern="*", system=False):
        if not present(path):
            return
        try:
            check_parents(path / "placeholder")
            for child in sorted(path.glob(pattern)):
                if child.name == ".DS_Store":
                    continue
                self.add_sdk(child, kind, system)
        except (OSError, CleanupError) as error:
            self.plan.blockers.append(str(error))

    def brew_inventory(self):
        for brew in self.brews:
            prefix_result = subprocess.run([str(brew), "--prefix"], env=self.environ, text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if prefix_result.returncode:
                raise CleanupError("无法读取 Homebrew 安装前缀：{}\n{}".format(brew, prefix_result.stderr.strip()))
            prefix = self.path(prefix_result.stdout.strip()).resolve()
            for kind, matcher in (("formula", FORMULA), ("cask", CASK)):
                result = subprocess.run([str(brew), "list", "--" + kind, "-1"], env=self.environ,
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                if result.returncode:
                    raise CleanupError("Homebrew 清单读取失败：{}\n{}".format(brew, result.stderr.strip()))
                packages = [name.strip() for name in result.stdout.splitlines() if matcher.fullmatch(name.strip().rsplit("/", 1)[-1])]
                for name in result.stdout.splitlines():
                    short_name = name.strip().rsplit("/", 1)[-1]
                    if re.search(r"(?:jdk|graalvm)", short_name) and name.strip() not in packages:
                        self.plan.blockers.append("未识别的 Homebrew Java 包，需按其卸载说明处理：{}".format(name.strip()))
                packages.sort(key=lambda name: not name.rsplit("/", 1)[-1].startswith("gradle"))
                for package in packages:
                    command = [str(brew), "uninstall", "--" + kind]
                    if kind == "formula":
                        command.append("--force")
                    command.append(package)
                    self.plan.commands.append((command, kind == "cask"))
                    token = package.rsplit("/", 1)[-1]
                    self.bin_paths.add(str(prefix / "opt" / token / "bin"))
                    self.brew_roots.update(prefix / folder / token for folder in ("Cellar", "Caskroom", "opt"))

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
            return
        expanded = values[0].replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
        if "$" in expanded or "`" in expanded:
            return
        candidate = self.path(expanded)
        if name == "GRADLE_USER_HOME":
            self.cache_paths.add(candidate)
        elif name != "JRE_HOME":
            if candidate.parts[-2:] == ("Contents", "Home"):
                candidate = candidate.parent.parent
            self.add_sdk(candidate, "Gradle" if name.startswith("GRADLE") else "JDK", system=self.system_jvms in candidate.parents)

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
        env_files.update(self.path(self.environ[key]) for key in ("ENV_FILE", "JDK_ENV_FILE", "GRADLE_ENV_FILE") if self.environ.get(key))
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
            if managed:
                assignment = ASSIGNMENT.match(line.rstrip("\r\n"))
                if assignment:
                    self.discover_assignment(*assignment.groups(), path)
                continue
            if not stripped or stripped.startswith("#"):
                result.append(line)
                continue
            related = bool(REFERENCE.search(line)) or any(str(env_file) in line for env_file in env_files)
            if re.search(r"(^|\s)(if|for|while|case|function|select)\b|\(\)\s*\{|<<|\\\s*$", line):
                complex_context = True
            if related and (complex_context or re.search(r"[;&|]", line)):
                raise CleanupError("Java/Gradle 配置包含复杂 Shell 逻辑，请先手工整理：{}".format(path))
            assignment = ASSIGNMENT.match(line.rstrip("\r\n"))
            if assignment:
                self.discover_assignment(*assignment.groups(), path)
                continue
            path_line = PATH_ASSIGNMENT.match(line.rstrip("\r\n"))
            if path_line:
                prefix, value = path_line.groups()
                quote = value[0] if value and value[0] in "\"'" else ""
                if quote and value.endswith(quote):
                    value = value[1:-1]
                elif quote or re.search(r"\s|[;`()]|\\|[&|]", value):
                    if related or any(binary in line for binary in self.bin_paths):
                        raise CleanupError("PATH 配置无法安全拆分，请先手工整理：{}".format(path))
                    result.append(line)
                    continue
                if re.search(r"[`()\\]|\$\(|[;&|]", value) or (quote and quote in value):
                    if related or any(binary in line for binary in self.bin_paths):
                        raise CleanupError("PATH 包含命令替换或复杂引号，请先手工整理：{}".format(path))
                    result.append(line)
                    continue
                entries = value.split(":")
                kept = []
                for entry in entries:
                    expanded = entry.replace("${HOME}", str(self.home)).replace("$HOME", str(self.home))
                    if REFERENCE.search(entry) or expanded in self.bin_paths:
                        continue
                    kept.append(entry)
                if kept != entries:
                    if complex_context:
                        raise CleanupError("PATH 位于复杂 Shell 逻辑中，请先手工整理：{}".format(path))
                    if kept:
                        result.append(prefix + quote + ":".join(kept) + quote + ("\n" if line.endswith("\n") else ""))
                    continue
            if stripped.startswith((". ", "source ")):
                source_is_environment = False
                try:
                    tokens = shlex.split(stripped, comments=True)
                    source_is_environment = len(tokens) == 2 and self.path(tokens[1]) in env_files
                except ValueError:
                    pass
                except CleanupError:
                    if related:
                        raise
                if source_is_environment:
                    if complex_context:
                        raise CleanupError("加载环境文件位于复杂逻辑中：{}".format(path))
                    continue
            if related:
                raise CleanupError("存在无法自动清理的 Java/Gradle 配置，请先手工整理：{}".format(path))
            result.append(line)
        if managed:
            raise CleanupError("受管区块没有结束标记：{}".format(path))
        after = "".join(result).encode("utf-8")
        if after != before:
            self.plan.edits.append(Edit(path, before, after, identity(path)))

    def scan(self):
        self.brew_inventory()
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
        # 第一遍静态发现自定义 SDK；第二遍才能清理排在赋值之前的具体 PATH。
        for _ in range(2):
            self.plan.edits = []
            for path in sorted(profiles):
                if present(path):
                    try:
                        self.clean_config(path)
                    except (OSError, UnicodeError, CleanupError) as error:
                        self.plan.blockers.append(str(error))
        self.manager_configs()
        if self.environ.get("GRADLE_USER_HOME"):
            self.cache_paths.add(self.path(self.environ["GRADLE_USER_HOME"]))
        if self.remove_caches:
            for path in sorted(self.cache_paths):
                if not present(path):
                    continue
                try:
                    if path != self.home / ".gradle":
                        self.safe_root(path)
                        if not any((path / name).exists() for name in ("caches", "wrapper/dists", "gradle.properties", "daemon", "init.d")):
                            raise CleanupError("无法确认 Gradle 用户缓存目录：{}".format(path))
                    check_parents(path)
                    if path.is_symlink():
                        raise CleanupError("Gradle 用户缓存是链接，需明确实际目录：{}".format(path))
                    if not path.is_dir():
                        raise CleanupError("Gradle 用户缓存不是目录：{}".format(path))
                    unknown = {entry.name for entry in path.iterdir()} - CACHE_ENTRIES
                    if unknown:
                        raise CleanupError("Gradle 缓存目录含未识别资料，拒绝整体删除：{}（{}）".format(path, ", ".join(sorted(unknown))))
                    self.plan.removals.append(Removal(path, "Gradle 用户配置与缓存", identity(path)))
                    for name in ("gradle.properties", "init.gradle", "init.gradle.kts", "init.d"):
                        if present(path / name):
                            self.plan.cache_configs.append(path / name)
                except CleanupError as error:
                    self.plan.blockers.append(str(error))
        else:
            self.plan.notes.append("保留 Gradle 用户配置与缓存（含 Wrapper 分发）；完整重装测试加 --remove-caches。")
        # 父目录一旦在计划中，内部子目录不再单独删除。
        unique = []
        for item in sorted(self.plan.removals, key=lambda item: (len(item.path.parts), str(item.path))):
            if not any(parent.path == item.path or parent.path in item.path.parents for parent in unique):
                unique.append(item)
        self.plan.removals = unique
        self.plan.blockers = list(dict.fromkeys(self.plan.blockers))
        self.plan.notes = list(dict.fromkeys(self.plan.notes))
        self.plan.notes.append("保留业务项目、IDEA 内置 JBR、系统 Java 占位程序、其他 SDKMAN 工具及 SDK 下载压缩包。")
        self.plan.notes.append("/etc 全局配置、launchctl 环境、安装器收据及未列出的自定义位置需另行核对。")
        return self.plan

    def manager_configs(self):
        asdf = self.home / ".tool-versions"
        mise = self.path(self.environ.get("MISE_CONFIG_DIR", str(self.home / ".config/mise"))) / "config.toml"
        for path in (asdf, mise):
            if not present(path):
                continue
            try:
                check_parents(path)
                if path.is_symlink() or not path.is_file():
                    raise CleanupError("版本管理配置不是普通文件，已保留：{}".format(path))
                before = path.read_bytes()
                result = []
                section = ""
                for line in before.decode("utf-8").splitlines(keepends=True):
                    stripped = line.strip()
                    if path == asdf:
                        if re.match(r"^(?:java|gradle)\s+", stripped):
                            continue
                    else:
                        if stripped.startswith("["):
                            section = stripped.split("#", 1)[0].strip()
                        if section == "[tools]" and re.match(r"^(?:java|gradle)\s*=", stripped):
                            if not re.fullmatch(r'(?:java|gradle)\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\')\s*(?:#.*)?', stripped):
                                raise CleanupError("mise Java/Gradle 配置复杂，请先手工整理：{}".format(path))
                            continue
                        if re.search(r"\b(?:java|gradle)\b", stripped) and not stripped.startswith("#"):
                            raise CleanupError("mise Java/Gradle 配置无法安全拆分：{}".format(path))
                    result.append(line)
                after = "".join(result).encode("utf-8")
                if before != after:
                    self.plan.edits.append(Edit(path, before, after, identity(path)))
            except (OSError, UnicodeError, CleanupError) as error:
                self.plan.blockers.append(str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description="macOS 维护者测试工具：清理扫描范围内全部版本 JDK/Gradle；默认只预览。")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="执行计划，需输入 DELETE")
    mode.add_argument("--dry-run", action="store_true", help="只预览（默认）")
    parser.add_argument("--yes", action="store_true", help="仅配合 --apply 跳过输入确认")
    parser.add_argument("--include-system", action="store_true", help="包含系统 JDK 目录及 Homebrew JDK cask，必要时逐项 sudo")
    parser.add_argument("--remove-caches", action="store_true", help="额外删除 Gradle 用户配置、缓存及 Wrapper 分发，先备份配置")
    parser.add_argument("--no-homebrew", action="store_true", help="明确跳过 Homebrew，保留其登记安装")
    parser.add_argument("--jdk-dir", action="append", default=[], metavar="绝对路径", help="额外 JDK 安装目录，可重复")
    parser.add_argument("--gradle-dir", action="append", default=[], metavar="绝对路径", help="额外 Gradle 安装目录，可重复")
    parser.add_argument("--profile", action="append", default=[], metavar="绝对路径", help="额外 Shell 配置文件，可重复")
    args = parser.parse_args(argv)
    if args.yes and not args.apply:
        parser.error("--yes 必须与 --apply 一起使用")
    try:
        if sys.platform != "darwin":
            raise CleanupError("本工具面向 macOS；不在 Windows/Linux 上执行清理。")
        if os.geteuid() == 0:
            raise CleanupError("请以目标用户运行，不要对整个脚本使用 sudo。")
        brews = []
        if not args.no_homebrew:
            for value in (shutil.which("brew"), "/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
                if value and Path(value).is_file() and os.access(value, os.X_OK) and str(Path(value).resolve()) not in [str(path.resolve()) for path in brews]:
                    brews.append(Path(value))
        cleaner = Cleaner(Path.home(), brews=brews, include_system=args.include_system,
                          remove_caches=args.remove_caches, extra_jdks=args.jdk_dir,
                          extra_gradles=args.gradle_dir, extra_profiles=args.profile)
        plan = cleaner.scan()
        if args.no_homebrew:
            plan.notes.append("已指定 --no-homebrew：Homebrew 安装未纳入本次清理。")
        print(plan.describe())
        if not args.apply:
            print("仅预览，未修改文件。执行需加 --apply；完整重装测试加 --include-system --remove-caches。")
            return 0
        plan.preflight()
        if not args.yes:
            if not sys.stdin.isatty():
                raise CleanupError("非交互输入不执行删除；自动测试须明确指定 --apply --yes。")
            if input("确认按上述计划永久删除 SDK？输入 DELETE：").strip() != "DELETE":
                raise CleanupError("已取消，未执行清理。")
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
