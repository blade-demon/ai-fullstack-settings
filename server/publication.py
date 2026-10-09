"""Version information for the exact files a download server is publishing."""
import datetime
import hashlib
import json
import re

SHA256 = re.compile(r"[a-f0-9]{64}\Z")
LAUNCHER = "devtool-helper.sh"
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
    if set(artifacts) != {LAUNCHER, BUNDLE}:
        raise ValueError("发布文件集合无效")
    launcher = dict(path=LAUNCHER, **fingerprint(directory / LAUNCHER))
    bundle = dict(path=BUNDLE, **fingerprint(directory / BUNDLE))
    return {"schema": 2, "interface": "go-tui",
            "version": "go-tui-" + bundle["sha256"][:12],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "server": scheme + "://" + server, "runtime_sources": runtime_sources,
            "launcher": launcher, "bundle": bundle}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("发布信息包含重复字段：%s" % key)
        result[key] = value
    return result


def read_release(directory, artifacts):
    """The caller rejects symlinks/junctions for the directory and known files."""
    try:
        path = directory / "release.json"
        if path.stat().st_size > 64 * 1024:
            raise ValueError("发布信息过大")
        release = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
        fields = {"schema", "interface", "version", "created_at", "server", "runtime_sources", "launcher", "bundle"}
        if (not isinstance(release, dict) or set(release) != fields
                or type(release.get("schema")) is not int or release["schema"] != 2
                or release.get("interface") != "go-tui"):
            raise ValueError("缺少 schema 2 Go TUI 发布标识")
        sources = release.get("runtime_sources")
        if (not isinstance(sources, dict) or set(sources) != {"tui", "cleanup"}
                or any(not isinstance(value, str) or not SHA256.fullmatch(value) for value in sources.values())):
            raise ValueError("运行文件源码摘要无效")
        if set(artifacts) != {LAUNCHER, BUNDLE}:
            raise ValueError("发布文件集合无效")
        for key, name in (("launcher", LAUNCHER), ("bundle", BUNDLE)):
            entry = release.get(key)
            if (not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}
                    or entry["path"] != name or type(entry["size"]) is not int or entry["size"] <= 0
                    or not isinstance(entry["sha256"], str) or not SHA256.fullmatch(entry["sha256"])):
                raise ValueError("发布文件信息无效：%s" % name)
            if fingerprint(directory / name) != {"size": entry["size"], "sha256": entry["sha256"]}:
                raise ValueError("文件与发布版本不一致：%s" % name)
        if release.get("version") != "go-tui-" + release["bundle"]["sha256"][:12]:
            raise ValueError("发布版本与工具包摘要不一致")
        if not isinstance(release["created_at"], str) or not isinstance(release["server"], str):
            raise ValueError("发布元信息无效")
        return release
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise ValueError("发布信息无效，请使用 start 或 package 重新打包：%s" % error) from error
