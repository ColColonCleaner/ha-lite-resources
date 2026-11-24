"""Checks for the release metadata and validation workflow."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "lite_resources"


class ReleaseMetadataTest(unittest.TestCase):
    """The commit a later GitHub release will point at."""

    def test_manifest_version_and_required_keys(self) -> None:
        """Manifest has a semantic version and keeps the HACS keys."""
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], "lite_resources")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["name"], "Lite Resources")
        for key in ("documentation", "issue_tracker", "codeowners"):
            self.assertTrue(manifest.get(key), key)
        self.assertEqual(
            manifest["documentation"],
            "https://github.com/ColColonCleaner/ha-lite-resources",
        )
        self.assertEqual(
            manifest["issue_tracker"],
            "https://github.com/ColColonCleaner/ha-lite-resources/issues",
        )

    def test_hacs_manifest_has_name(self) -> None:
        """hacs.json has the required name."""
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(hacs["name"], "Lite Resources")
        self.assertNotIn("country", hacs)

    def test_changelog_records_patch(self) -> None:
        """The changelog has an entry for the manifest version."""
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn(f"## {manifest['version']}", changelog)
        self.assertIn("11:39:18 GMT", changelog)

    def test_validation_workflow_has_no_ignored_checks(self) -> None:
        """Validate runs hassfest and HACS with no ignore list."""
        workflow = (ROOT / ".github" / "workflows" / "validate.yaml").read_text()
        self.assertIn("home-assistant/actions/hassfest@master", workflow)
        self.assertIn("hacs/action@main", workflow)
        self.assertIn("category: integration", workflow)
        self.assertNotIn("ignore:", workflow)
        self.assertNotIn("ignore ", workflow)

    def test_validation_workflow_runs_the_unit_tests(self) -> None:
        """A push that breaks a unit test fails the workflow."""
        workflow = (ROOT / ".github" / "workflows" / "validate.yaml").read_text()
        self.assertIn("-m unittest discover -s tests", workflow)

    def test_brand_icon_present(self) -> None:
        """The brands check looks for brand/icon.png."""
        icon = INTEGRATION / "brand" / "icon.png"
        self.assertTrue(icon.is_file())
        self.assertGreater(icon.stat().st_size, 0)

    def test_readme_gives_the_release_steps(self) -> None:
        """A release follows the local validation and the check of its tag."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        steps = readme.split("## Releasing")[1].split("## License")[0]
        validate = steps.index("python scripts/validate.py")
        check = steps.index("python scripts/release_notes.py")
        push = steps.index("git push origin v")
        self.assertLess(validate, check)
        self.assertLess(check, push)

    def _release_workflow(self) -> str:
        """Return the Release workflow without its comment lines.

        A comment that names a step must not count as that step.
        """
        text = (ROOT / ".github" / "workflows" / "release.yaml").read_text(
            encoding="utf-8"
        )
        return "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )

    def test_release_workflow_runs_the_script_for_a_pushed_tag(self) -> None:
        """The workflow makes a release only through the script that checks the tag."""
        workflow = self._release_workflow()
        self.assertRegex(workflow, r'push:\s*\n\s*tags:\s*\n\s*- "v\*"')
        self.assertRegex(workflow, r"permissions:\s*\n\s*contents: write\n")
        self.assertIn('python3 scripts/release_notes.py "$TAG" --publish', workflow)
        self.assertEqual(workflow.count("--publish"), 1)

    def test_release_workflow_takes_a_tag_for_a_manual_run(self) -> None:
        """A manual run names its tag, because its own ref is a branch."""
        workflow = self._release_workflow()
        self.assertRegex(
            workflow, r"workflow_dispatch:\s*\n\s*inputs:\s*\n\s*tag:\s*\n"
        )
        self.assertIn("required: true", workflow)
        self.assertIn("TAG: ${{ inputs.tag || github.ref_name }}", workflow)

    def test_release_workflow_stops_for_a_name_with_no_tag(self) -> None:
        """The request would make a tag for such a name, so the job stops before it."""
        workflow = self._release_workflow()
        checkout = workflow.index("ref: refs/tags/${{ env.TAG }}")
        guard = workflow.index(
            'test "$(git rev-parse HEAD)" = '
            '"$(git rev-parse --verify --quiet "refs/tags/$TAG^{commit}")"'
        )
        publish = workflow.index("--publish")
        self.assertLess(checkout, guard)
        self.assertLess(guard, publish)

    def test_release_workflow_limits_the_token(self) -> None:
        """One step reads the token, and no command holds an expression."""
        workflow = self._release_workflow()
        self.assertEqual(workflow.count("secrets."), 1)
        self.assertNotIn("github.token", workflow)
        publish = workflow.index("--publish")
        self.assertGreater(workflow.index("secrets.GITHUB_TOKEN"), publish)
        self.assertIn("persist-credentials: false", workflow)
        # The action of a job with a write token is named by a commit, never by a tag.
        actions = [line for line in workflow.splitlines() if "uses:" in line]
        self.assertEqual(len(actions), 1)
        self.assertRegex(actions[0], r"uses: actions/checkout@[0-9a-f]{40}$")
        commands = [line for line in workflow.splitlines() if "run:" in line]
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertNotIn("${{", command)

    def test_single_integration_package(self) -> None:
        """HACS manages one directory under custom_components."""
        packages = [
            path
            for path in (ROOT / "custom_components").iterdir()
            if path.is_dir() and not path.name.startswith("__")
        ]
        self.assertEqual([path.name for path in packages], ["lite_resources"])


if __name__ == "__main__":
    unittest.main()
