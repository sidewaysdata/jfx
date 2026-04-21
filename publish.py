#!/usr/bin/env python3
"""
Publish the sidewaysdata JavaFX fork to repsy.

Each run publishes ONE platform classifier (linux, mac, or win) plus the
classifier-less jars for every javafx.* module. OpenJFX cannot cross-compile
native libraries, so Mac and Windows classifiers must be published from their
respective host machines.

Version scheme: 27.0.0-sd.<git-short-sha>. Each commit to the fork gets a
distinct immutable version; bump timer/build.gradle's jfxVersion in lockstep.

Usage:
    python3 publish.py                  # auto-detect host platform, version from HEAD sha
    python3 publish.py --platform linux
    python3 publish.py --version 27.0.0-sd.abc1234 --platform mac

Credentials: repsyUsername/repsyPassword Gradle props, or REPSY_USERNAME/
REPSY_PASSWORD env vars, or ~/.m2/settings.xml (id=repsy).

System deps (for COMPILE_MEDIA=true to build the media native libs):
  Linux:    apt install libglib2.0-dev libasound2-dev libavcodec-dev \\
                        libavformat-dev libavutil-dev libgtk-3-dev \\
                        libpango1.0-dev
  macOS:    xcode-select --install (ships required headers)
  Windows:  Visual Studio Build Tools + Windows SDK

Build JDK: requires JDK 24+ (jfx/build.properties sets jfx.build.jdk.version.min=24).
"""

import argparse
import base64
import os
import platform
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from xml.etree import ElementTree

JFX_DIR = Path(__file__).resolve().parent
GROUP = "org.openjfx"
REPSY_BASE = "https://repo.repsy.io/mvn/winrid/sidewaysdata"
MODULES = ["javafx-base", "javafx-graphics", "javafx-controls", "javafx-media", "javafx-fxml", "javafx-swing", "javafx-web"]
EXPECTED_CLASSIFIERS = ["linux", "mac", "win"]


def detect_host_platform() -> str:
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    if system == "darwin":
        return "mac"
    if system == "windows":
        return "win"
    sys.exit(f"Unsupported host OS: {platform.system()!r}")


def git_short_sha() -> str:
    result = subprocess.run(
        ["git", "-C", str(JFX_DIR), "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"git rev-parse failed: {result.stderr.strip()}")
    return result.stdout.strip()


def default_version() -> str:
    return f"27.0.0-sd.{git_short_sha()}"


def refuse_cross_compile(platform_arg: str) -> None:
    host = detect_host_platform()
    if platform_arg != host:
        sys.exit(
            f"Refusing to cross-compile. Requested platform {platform_arg!r} but host is "
            f"{host!r}. Run this script on a {platform_arg} machine to publish its native libs."
        )


def run_gradle_publish(version: str, platform_name: str) -> None:
    gradlew = JFX_DIR / ("gradlew.bat" if platform_name == "win" else "gradlew")
    cmd = [
        str(gradlew),
        "sdk",
        "publish",
        f"-PMAVEN_VERSION={version}",
        f"-PCOMPILE_TARGETS={platform_name}",
        "-PMAVEN_PUBLISH=true",
        "-PCOMPILE_MEDIA=true",
    ]
    print(f">>> {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(JFX_DIR))
    if result.returncode != 0:
        sys.exit(f"Gradle publish failed with exit code {result.returncode}")


def read_repsy_credentials() -> tuple[str | None, str | None]:
    """Return (username, password) from env, Gradle props, or ~/.m2/settings.xml."""
    user = os.environ.get("REPSY_USERNAME")
    password = os.environ.get("REPSY_PASSWORD")
    if user and password:
        return user, password

    settings = Path.home() / ".m2" / "settings.xml"
    if settings.exists():
        try:
            tree = ElementTree.parse(str(settings))
            ns = {"m": "http://maven.apache.org/SETTINGS/1.0.0"}
            for server in tree.getroot().findall(".//m:server", ns) or tree.getroot().findall(".//server"):
                sid = server.findtext("m:id", default="", namespaces=ns) or server.findtext("id", default="")
                if sid == "repsy":
                    u = server.findtext("m:username", namespaces=ns) or server.findtext("username")
                    p = server.findtext("m:password", namespaces=ns) or server.findtext("password")
                    return u, p
        except ElementTree.ParseError as exc:
            print(f"  warning: could not parse {settings}: {exc}", file=sys.stderr)
    return None, None


def _auth_request(url: str, method: str = "GET") -> urllib.request.Request:
    req = urllib.request.Request(url, method=method)
    user, password = read_repsy_credentials()
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    return req


def list_available_classifiers(artifact_id: str, version: str) -> list[str]:
    """Probe repsy for platform-classifier jars at the given version.

    Repsy's HEAD handling returns 200 for non-existent paths, so we issue a GET
    with Range: bytes=0-0 to get accurate status codes with minimal bandwidth.
    """
    found = []
    for classifier in EXPECTED_CLASSIFIERS:
        url = (
            f"{REPSY_BASE}/{GROUP.replace('.', '/')}/{artifact_id}/{version}/"
            f"{artifact_id}-{version}-{classifier}.jar"
        )
        try:
            req = _auth_request(url, method="GET")
            req.add_header("Range", "bytes=0-0")
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 206):
                    found.append(classifier)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            print(f"  warning: probe failed for {url}: HTTP {exc.code}", file=sys.stderr)
        except urllib.error.URLError as exc:
            print(f"  warning: probe failed for {url}: {exc}", file=sys.stderr)
    return found


def report_coordinates(version: str, published_platform: str) -> None:
    print()
    print("=" * 60)
    print(f"Published coordinates at {version}:")
    for mod in MODULES:
        print(f"  {GROUP}:{mod}:{version}")
        print(f"  {GROUP}:{mod}:{version}:{published_platform}")
    print("=" * 60)

    probe_artifact = "javafx-graphics"
    print(f"\nChecking {probe_artifact} classifiers at repsy...")
    available = list_available_classifiers(probe_artifact, version)
    if not available:
        print(
            f"  warning: could not confirm any classifiers at {REPSY_BASE}/.../javafx-graphics/{version}/."
            " repsy may not be indexed yet. try again in a minute."
        )
        return

    print(f"  present: {', '.join(available)}")
    missing = [c for c in EXPECTED_CLASSIFIERS if c not in available]
    if missing:
        print(
            f"  MISSING: {', '.join(missing)}. Users on those platforms will hit "
            f"UnsatisfiedLinkError until you run this script on a {'/'.join(missing)} box."
        )
    else:
        print("  all platforms present.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--version",
        help="Override the published version (default: 27.0.0-sd.<git-short-sha>)",
    )
    parser.add_argument(
        "--platform",
        choices=["linux", "mac", "win", "host"],
        default="host",
        help="Which platform's native libs to publish. Must match the host OS.",
    )
    args = parser.parse_args()

    platform_name = detect_host_platform() if args.platform == "host" else args.platform
    refuse_cross_compile(platform_name)

    version = args.version or default_version()
    print(f"Publishing {GROUP}:javafx-*:{version} (classifier: {platform_name}) to {REPSY_BASE}")

    run_gradle_publish(version, platform_name)
    report_coordinates(version, platform_name)


if __name__ == "__main__":
    main()
