#!/usr/bin/env python3
"""Update the Flatpak source pin and AppStream entry for a stable release."""

import configparser
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "https://github.com/theRealCarneiro/pulsemeeter.git"
RELEASE_API = "https://api.github.com/repos/theRealCarneiro/pulsemeeter/releases/latest"
SOURCE = re.compile(
    r"(        url: https://github\.com/theRealCarneiro/pulsemeeter\.git\n"
    r"        tag: )(?P<tag>v\d+\.\d+\.\d+)(\n        commit: )(?P<commit>[0-9a-f]{40})(?=\n)"
)


def latest_release():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "pulsemeeter-flatpak"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(RELEASE_API, headers=headers), timeout=30) as response:
        return json.load(response)


def version(tag):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"Unsupported stable release tag: {tag!r}")
    return tuple(int(part) for part in tag[1:].split("."))


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()


def dependency_config(checkout, commit):
    """Stop unattended updates when upstream changes its dependency declarations."""
    files = set(git(checkout, "ls-tree", "--name-only", commit).splitlines())
    result = {}
    for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
        text = git(checkout, "show", f"{commit}:{name}") if name in files else ""
        if name == "setup.cfg":
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(text)
            result[name] = {
                key: config.get("options", key, fallback="")
                for key in ("install_requires", "setup_requires", "python_requires")
            }
            result["extras"] = dict(config.items("options.extras_require")) if config.has_section("options.extras_require") else {}
        else:
            result[name] = text
    return result


def update(root, release):
    manifest = root / "flatpak/eu.nosini.Pulsemeeter.yml"
    metadata = root / "flatpak/eu.nosini.Pulsemeeter.metainfo.xml"
    original = manifest.read_text()
    sources = list(SOURCE.finditer(original))
    if len(sources) != 1:
        raise ValueError("Expected exactly one pinned Pulsemeeter git source")
    source = sources[0]
    tag = release["tag_name"]
    if release["draft"] or release["prerelease"]:
        raise ValueError("Only published stable releases can be packaged")
    if version(tag) <= version(source["tag"]):
        print(f"Already packaged {source['tag']}; no newer stable release.")
        return False, source["tag"]
    date = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).date().isoformat()

    with tempfile.TemporaryDirectory(prefix="pulsemeeter-upstream-") as directory:
        checkout = Path(directory)
        git(checkout, "init", "--quiet")
        git(checkout, "remote", "add", "origin", UPSTREAM)
        git(checkout, "fetch", "--quiet", "--depth=1", "origin", source["commit"])
        git(checkout, "fetch", "--quiet", "--depth=1", "origin", f"refs/tags/{tag}")
        commit = git(checkout, "rev-parse", "FETCH_HEAD^{commit}")
        if dependency_config(checkout, source["commit"]) != dependency_config(checkout, commit):
            raise ValueError("Upstream dependency/build declarations changed; review them and update the pinned wheels manually")
        git(checkout, "checkout", "--quiet", "--detach", commit)
        for patch in sorted((root / "flatpak/patches").glob("*.patch")):
            git(checkout, "apply", "--check", str(patch.resolve()))
            git(checkout, "apply", str(patch.resolve()))

    xml = metadata.read_text()
    releases = ET.fromstring(xml).find("releases")
    if releases is None or xml.count("  <releases>\n") != 1:
        raise ValueError("Expected an AppStream releases section")
    if not any(entry.get("version") == tag[1:] for entry in releases):
        xml = xml.replace("  <releases>\n", f'  <releases>\n    <release version="{tag[1:]}" date="{date}"/>\n', 1)
    replacement = f"{source[1]}{tag}{source[3]}{commit}"
    manifest.write_text(original[:source.start()] + replacement + original[source.end():])
    metadata.write_text(xml)
    print(f"Updated Pulsemeeter to {tag} ({commit}).")
    return True, tag


def main():
    changed, tag = update(ROOT, latest_release())
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            stream.write(f"changed={str(changed).lower()}\ntag={tag}\n")


if __name__ == "__main__":
    main()
