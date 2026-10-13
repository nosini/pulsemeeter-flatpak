#!/usr/bin/env python3
"""Exercise the workflow's tag classification and release commands offline."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/flatpak.yml").read_text())


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        self.env = dict(os.environ, APP_NAME="Example", TAG="v1.2.3")

    def run_step(self, job, name, **env):
        step = next(step for step in WORKFLOW["jobs"][job]["steps"]
                    if step.get("name") == name)
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=self.directory, env=dict(self.env, **env),
            capture_output=True, text=True,
        )

    def test_tag_classification(self):
        for tag, stable in (
            ("v1.32.16", True), ("v1.32.16-1", True),
            ("v1.32.16-12", True), ("v1.32.17-rc1", False),
            ("v1.32.17-beta.2", False), ("v1.32.17rc1", False),
            ("v1.32.16-", False), ("v1.32.16-1rc1", False),
        ):
            with self.subTest(tag=tag):
                output = self.directory / "output"
                result = self.run_step(
                    "setup", "Classify the release tag",
                    TAG=tag, GITHUB_OUTPUT=str(output),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(), f"stable={str(stable).lower()}\n")
                output.unlink()

    def release_commands(self, *, stable="true", exists="false", fail="false"):
        bundles = self.directory / "bundles"
        bundles.mkdir()
        for name in ("example-x86_64.flatpak", "example-aarch64.flatpak"):
            (bundles / name).touch()
        binary = self.directory / "gh"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "if args[:2] == ['release', 'view']:\n"
            "    sys.exit(0 if os.environ['RELEASE_EXISTS'] == 'true' else 1)\n"
            "with open(os.environ['GH_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(args) + '\\n')\n"
            "sys.exit(1 if os.environ['RELEASE_FAIL'] == 'true' else 0)\n"
        )
        binary.chmod(0o755)
        log = self.directory / "gh.jsonl"
        result = self.run_step(
            "release", "Create the release and upload the tested bundles",
            PATH=f"{self.directory}:{os.environ['PATH']}", STABLE=stable,
            RELEASE_EXISTS=exists, RELEASE_FAIL=fail, GH_LOG=str(log),
        )
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        return result, commands

    def test_stable_release_includes_both_bundles_and_verifies_tag(self):
        result, commands = self.release_commands()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 1)
        args = commands[0]
        self.assertEqual(args[:3], ["release", "create", "v1.2.3"])
        self.assertIn("--verify-tag", args)
        self.assertIn("--generate-notes", args)
        self.assertIn("bundles/example-x86_64.flatpak", args)
        self.assertIn("bundles/example-aarch64.flatpak", args)
        self.assertNotIn("--prerelease", args)

    def test_prerelease_cannot_become_latest(self):
        result, commands = self.release_commands(stable="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prerelease", commands[0])
        self.assertIn("--latest=false", commands[0])

    def test_retry_uploads_to_existing_release(self):
        result, commands = self.release_commands(exists="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:3], ["release", "upload", "v1.2.3"])
        self.assertIn("--clobber", commands[0])

    def test_creation_failure_fails_the_step(self):
        result, _ = self.release_commands(fail="true")
        self.assertNotEqual(result.returncode, 0)

    def test_retry_keeps_existing_prerelease_out_of_latest(self):
        result, commands = self.release_commands(stable="false", exists="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands[0], ["release", "edit", "v1.2.3",
                                      "--prerelease", "--latest=false"])
        self.assertEqual(commands[1][:3], ["release", "upload", "v1.2.3"])
        self.assertIn("--clobber", commands[1])

    def test_upload_failure_fails_the_step(self):
        result, _ = self.release_commands(exists="true", fail="true")
        self.assertNotEqual(result.returncode, 0)

    def evaluate(self, expression, **context):
        expression = expression.strip().removeprefix("${{").removesuffix("}}")
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = expression.replace("!", " not ")
        return bool(eval("(" + expression + ")", {"__builtins__": {}},
                         dict(context, startsWith=lambda value, prefix: value.startswith(prefix))))

    def test_release_requires_validation_and_required_deployment(self):
        expression = WORKFLOW["jobs"]["release"]["if"]
        for publish, setup, build, signing, deploy, cancelled, ref, expected in (
            ("true", "success", "success", "success", "success", False, "refs/tags/v2.2.0", True),
            ("false", "success", "success", "skipped", "skipped", False, "refs/tags/v2.3.0-rc1", True),
            ("true", "success", "failure", "skipped", "skipped", False, "refs/tags/v2.2.0", False),
            ("true", "success", "success", "failure", "skipped", False, "refs/tags/v2.2.0", False),
            ("true", "success", "success", "success", "failure", False, "refs/tags/v2.2.0", False),
            ("true", "success", "success", "success", "skipped", False, "refs/tags/v2.2.0", False),
            ("false", "failure", "skipped", "skipped", "skipped", False, "refs/tags/v2.2.0", False),
            ("false", "success", "success", "skipped", "skipped", True, "refs/tags/v2.3.0-rc1", False),
            ("true", "success", "success", "success", "success", False, "refs/heads/main", False),
        ):
            for cache_only in (False, True):
                with self.subTest(publish=publish, setup=setup, build=build, signing=signing,
                                  deploy=deploy, cancelled=cancelled, ref=ref,
                                  cache_only=cache_only):
                    needs = SimpleNamespace(
                        setup=SimpleNamespace(result=setup, outputs=SimpleNamespace(publish=publish)),
                        build=SimpleNamespace(result=build), publish=SimpleNamespace(result=signing),
                        deploy=SimpleNamespace(result=deploy),
                    )
                    self.assertEqual(self.evaluate(expression, needs=needs,
                                                   github=SimpleNamespace(ref=ref),
                                                   inputs=SimpleNamespace(cache_only=cache_only),
                                                   cancelled=lambda: cancelled),
                                     expected and not cache_only)

    def test_stable_publication_is_limited_to_stable_tags_and_manual_main(self):
        expression = next(step["env"]["PUBLISH"] for step in WORKFLOW["jobs"]["setup"]["steps"]
                          if step.get("id") == "arches")
        for event, ref, stable, enabled, expected in (
            ("push", "refs/tags/v2.2.0", "true", "true", True),
            ("push", "refs/tags/v2.2.0-1", "true", "true", True),
            ("push", "refs/tags/v2.3.0-rc1", "false", "true", False),
            ("push", "refs/tags/v2.2.0", "true", "false", False),
            ("push", "refs/heads/main", "", "true", False),
            ("pull_request", "refs/pull/1/merge", "", "true", False),
            ("workflow_dispatch", "refs/heads/main", "", "true", True),
            ("workflow_dispatch", "refs/heads/update/upstream", "", "true", False),
            ("workflow_dispatch", "refs/tags/v2.2.0", "true", "true", True),
            ("workflow_dispatch", "refs/tags/v2.3.0-rc1", "false", "true", False),
        ):
            for cache_only in (False, True):
                with self.subTest(event=event, ref=ref, enabled=enabled,
                                  cache_only=cache_only):
                    self.assertEqual(self.evaluate(expression,
                        vars=SimpleNamespace(PUBLISH_FLATPAK=enabled),
                        github=SimpleNamespace(ref=ref, event_name=event),
                        inputs=SimpleNamespace(cache_only=cache_only),
                        steps=SimpleNamespace(release=SimpleNamespace(outputs=SimpleNamespace(stable=stable))),
                    ), expected and not cache_only)


if __name__ == "__main__":
    unittest.main()
