"""Inert runtime release fixtures; no Go, Python bundle or installer is executed."""
import hashlib
import io
import json
import zipfile

try:
    from .cleanup_fixture import cleanup_fixture
    from .tui_fixture import tui_fixture
except ImportError:
    from cleanup_fixture import cleanup_fixture
    from tui_fixture import tui_fixture


FILES = (
    "resources/tui/team-dev-env-arm64",
    "resources/tui/team-dev-env-amd64",
    "resources/tui/manifest.json",
    "resources/tui/THIRD_PARTY_NOTICES.txt",
    "resources/cleanup/cleanup-macos-universal2",
    "resources/cleanup/manifest.json",
    "resources/cleanup/THIRD_PARTY_NOTICES.txt",
)


def runtime_fixture(repo):
    source = repo / "tools/uninstall_java_gradle.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_bytes(b"print('inert cleanup fixture')\n")
    tui_fixture(repo)
    cleanup = cleanup_fixture(repo)
    manifest = json.loads((cleanup / "manifest.json").read_text(encoding="utf-8"))
    manifest["notices_sha256"] = hashlib.sha256((cleanup / "THIRD_PARTY_NOTICES.txt").read_bytes()).hexdigest()
    (cleanup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return {name: (repo / name).read_bytes() for name in FILES}


def archive_fixture(payloads, extra=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in list(payloads.items()) + list(extra):
            archive.writestr(name, data)
    return buffer.getvalue()


def lock_fixture(payloads, archive=None):
    archive = archive_fixture(payloads) if archive is None else archive
    digest = hashlib.sha256(archive).hexdigest()
    release = "runtimes-" + digest[:16]
    return {
        "schema": 1,
        "release": release,
        "source_sha256": {name: json.loads(payloads["resources/%s/manifest.json" % name])["source_sha256"]
                          for name in ("tui", "cleanup")},
        "archive": {
            "url": "https://github.com/blade-demon/ai-fullstack-settings/releases/download/"
                   + release + "/team-dev-env-runtimes.zip",
            "sha256": digest,
            "size": len(archive),
        },
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                  for name, data in payloads.items()},
    }
