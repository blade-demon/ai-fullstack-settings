"""Version information for the exact files a download server is publishing."""
import datetime
import hashlib
import json
import re


SHA256 = re.compile(r"[a-f0-9]{64}\Z")
BUNDLE = "dev-env/team-dev-env.tar.gz"


def fingerprint(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def make_release(directory, artifacts, runtime_sources, server, scheme):
    """The caller supplies a private staging directory containing validated files."""
    entries = {name: fingerprint(directory / name) for name in artifacts}
    return {
        "schema": 1,
        "interface": "go-tui",
        "version": "go-tui-" + entries[BUNDLE]["sha256"][:12],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "server": scheme + "://" + server,
        "runtime_sources": runtime_sources,
        "artifacts": entries,
    }


def read_release(directory, artifacts):
    """The caller rejects symlinks/junctions for the directory and all known files."""
    try:
        path = directory / "release.json"
        if path.stat().st_size > 64 * 1024:
            raise ValueError("发布信息过大")
        release = json.loads(path.read_text(encoding="utf-8-sig"))
        if (not isinstance(release, dict) or type(release.get("schema")) is not int
                or release["schema"] != 1 or release.get("interface") != "go-tui"):
            raise ValueError("缺少 Go TUI 发布标识")
        sources = release.get("runtime_sources")
        if (not isinstance(sources, dict) or set(sources) != {"tui", "cleanup"}
                or any(not isinstance(value, str) or not SHA256.fullmatch(value)
                       for value in sources.values())):
            raise ValueError("运行文件源码摘要无效")
        entries = release.get("artifacts")
        if not isinstance(entries, dict) or set(entries) != set(artifacts):
            raise ValueError("发布文件清单不完整")
        for name in artifacts:
            entry = entries[name]
            if (not isinstance(entry, dict) or type(entry.get("size")) is not int
                    or entry["size"] < 0 or not isinstance(entry.get("sha256"), str)
                    or not SHA256.fullmatch(entry["sha256"])):
                raise ValueError("发布文件信息无效：%s" % name)
            if fingerprint(directory / name) != entry:
                raise ValueError("文件与发布版本不一致：%s" % name)
        if release.get("version") != "go-tui-" + entries[BUNDLE]["sha256"][:12]:
            raise ValueError("发布版本与工具包摘要不一致")
        return release
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise ValueError("发布信息无效，请使用 start 或 package 重新打包：%s" % error) from error
