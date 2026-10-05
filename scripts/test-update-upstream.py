#!/usr/bin/env python3
"""Exercise release updates against a local upstream Git repository."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("update_upstream", Path(__file__).with_name("update-upstream.py"))
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.upstream = directory / "upstream"
        self.upstream.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        (self.upstream / "requirements.txt").write_text("pulsectl\n")
        (self.upstream / "setup.cfg").write_text("[metadata]\nversion = 2.2.0\n[options]\ninstall_requires = pulsectl\n")
        (self.upstream / "app.py").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Old release")
        self.old_commit = self.git("rev-parse", "HEAD")
        self.git("tag", "v2.2.0")
        # Non-dependency metadata changes must not block the update.
        (self.upstream / "setup.cfg").write_text("[metadata]\nversion = 2.3.0\n[options]\ninstall_requires = pulsectl\n")
        self.git("commit", "--quiet", "-am", "New release")
        self.new_commit = self.git("rev-parse", "HEAD")
        self.git("-c", "tag.gpgsign=false", "tag", "-a", "v2.3.0", "-m", "Annotated release")
        self.root = directory / "packaging"
        flatpak = self.root / "flatpak"
        (flatpak / "patches").mkdir(parents=True)
        self.manifest = flatpak / "eu.nosini.Pulsemeeter.yml"
        # Use the real manifest to also check that unrelated formatting survives.
        text = (updater.ROOT / "flatpak/eu.nosini.Pulsemeeter.yml").read_text()
        text = updater.SOURCE.sub(lambda match: f"{match[1]}v2.2.0{match[3]}{self.old_commit}", text)
        self.manifest.write_text(text)
        self.metadata = flatpak / "eu.nosini.Pulsemeeter.metainfo.xml"
        self.metadata.write_text('<component>\n  <releases>\n    <release version="2.2.0" date="2026-07-25"/>\n  </releases>\n</component>\n')
        self.before = self.manifest.read_text(), self.metadata.read_text()
        self.release = {
            "tag_name": "v2.3.0", "draft": False, "prerelease": False,
            "published_at": "2026-10-05T12:34:56Z",
        }
        self.override = patch.object(updater, "UPSTREAM", str(self.upstream))
        self.override.start()
        self.addCleanup(self.override.stop)

    def git(self, *args):
        return updater.git(self.upstream, *args)

    def assert_unchanged(self):
        self.assertEqual(self.before, (self.manifest.read_text(), self.metadata.read_text()))

    def add_patch(self, name, before, after):
        (self.root / "flatpak/patches" / name).write_text(
            f"diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-{before}\n+{after}\n"
        )

    def test_no_update_for_same_or_older_release(self):
        for tag in ("v2.2.0", "v2.1.9"):
            with self.subTest(tag=tag), patch.object(updater, "git", side_effect=AssertionError("No fetch needed")):
                self.assertEqual(updater.update(self.root, dict(self.release, tag_name=tag)), (False, "v2.2.0"))
                self.assert_unchanged()

    def test_annotated_tag_is_pinned_to_commit_and_history_is_preserved(self):
        self.add_patch("0001.patch", "original", "patched")
        self.assertEqual(updater.update(self.root, self.release), (True, "v2.3.0"))
        expected = self.before[0].replace("tag: v2.2.0", "tag: v2.3.0").replace(self.old_commit, self.new_commit)
        self.assertEqual(self.manifest.read_text(), expected)
        releases = ET.parse(self.metadata).findall("releases/release")
        self.assertEqual([release.get("version") for release in releases], ["2.3.0", "2.2.0"])
        self.assertEqual(releases[0].get("date"), "2026-10-05")
        # The second check must be a no-op, with no duplicate release entry.
        self.assertEqual(updater.update(self.root, self.release), (False, "v2.3.0"))

    def test_patches_are_checked_in_order(self):
        self.add_patch("0001.patch", "original", "first")
        self.add_patch("0002.patch", "first", "second")
        self.assertTrue(updater.update(self.root, self.release)[0])

    def test_dependency_changes_stop_without_editing_packaging(self):
        for filename, content in (
            ("requirements.txt", "pulsectl\nnew-dependency\n"),
            ("setup.cfg", "[options]\ninstall_requires = new-dependency\n"),
            ("pyproject.toml", '[build-system]\nrequires = ["new-backend"]\n'),
            ("setup.py", 'setup(install_requires=["new-dependency"])\n'),
        ):
            with self.subTest(filename=filename):
                (self.upstream / filename).write_text(content)
                self.git("add", ".")
                self.git("commit", "--quiet", "-m", "Change dependencies")
                self.git("tag", "--force", "v2.3.0")
                with self.assertRaisesRegex(ValueError, "declarations changed"):
                    updater.update(self.root, self.release)
                self.assert_unchanged()
                self.git("reset", "--hard", self.new_commit)
                self.git("clean", "-fd")

    def test_broken_patch_stops_without_editing_packaging(self):
        self.add_patch("0001.patch", "missing", "patched")
        with self.assertRaises(subprocess.CalledProcessError):
            updater.update(self.root, self.release)
        self.assert_unchanged()

    def test_drafts_prereleases_and_unsupported_tags_are_rejected(self):
        for change in ({"draft": True}, {"prerelease": True}, {"tag_name": "v2.3.0-rc1"}, {"tag_name": "v2.3.0\ninjected"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                updater.update(self.root, dict(self.release, **change))
            self.assert_unchanged()

    def test_invalid_release_date_stops_without_editing_packaging(self):
        with self.assertRaises(ValueError):
            updater.update(self.root, dict(self.release, published_at="invalid"))
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
