"""The README's instructions are complete.

An instruction that names an action also says where that action is. An earlier version's
reader found "select Add group" with no place.
"""

from __future__ import annotations

import json
import re
import unittest

from support import ROOT


class ReadmeTest(unittest.TestCase):
    """The README's configuration steps and pictures."""

    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_each_picture_of_the_readme_exists(self) -> None:
        pictures = re.findall(r'src="(docs/images/[^"]+)"', self.readme)
        self.assertIn("docs/images/integration-page.png", pictures)
        for picture in pictures:
            self.assertTrue((ROOT / picture).is_file(), picture)

    def test_add_group_has_its_two_places(self) -> None:
        step = next(
            line
            for line in self.readme.splitlines()
            if line.startswith("4. Select **Add group**")
        )
        self.assertIn("the button in the upper-right corner", step)
        self.assertIn("the three-dot menu", step)

    def test_each_action_on_a_group_has_its_place(self) -> None:
        section = self.readme.split("### Change, rename or delete a group")[1].split(
            "###"
        )[0]
        self.assertIn("the cog icon", section)
        self.assertIn("**Rename**", section)
        self.assertIn("**Delete**", section)
        self.assertEqual(section.count("at the right of its row"), 3)

    def test_button_is_not_given_as_a_replacement_of_the_steps(self) -> None:
        # A button opens one dialog. The steps after that dialog stay necessary.
        self.assertNotIn("Or do these steps", self.readme)
        steps = self.readme.split("\n## Configuration\n")[1].split("| Option |")[0]
        button = steps.index("config_flow_start")
        self.assertGreater(button, steps.index("1. Open the dialog"))
        self.assertLess(button, steps.index("2. The dialog has no settings"))

    def test_setup_names_the_page_of_the_integration(self) -> None:
        self.assertIn("**Settings → Devices & services → Lite Resources**", self.readme)
        self.assertIn("**Settings → Marketplace**", self.readme)

    def test_option_table_follows_the_group_form(self) -> None:
        """The table names each option of the form, by its label and in its order."""
        strings = json.loads(
            (ROOT / "custom_components" / "lite_resources" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        labels = strings["config_subentries"]["group"]["step"]["user"]["data"]
        table = self.readme.split("| Option | What to choose |")[1].split("\n\n")[0]
        rows = re.findall(r"^\| \*\*(.+?)\*\* \|", table, re.MULTILINE)
        self.assertEqual(
            rows, [label.removesuffix(" (optional)") for label in labels.values()]
        )


SECTION = "## What this fork changes"
FEATURES = "### Added features"
ISSUES = "### Corrections to the original"
# A word that names a test, a static check, the format or the release tooling.
_TOOLING = re.compile(r"\b(tests?|ruff|mypy|lint|format|workflow)\b", re.IGNORECASE)


class ForkDifferencesTest(unittest.TestCase):
    """The README states the difference between this fork and the original near its top."""

    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.section = self.readme.split(SECTION)[1].split("\n## ")[0]

    def _entries(self, heading: str) -> list[str]:
        """Return the list entries under one heading of the section."""
        part = self.section.split(heading)[1].split("\n### ")[0]
        return [line[2:] for line in part.splitlines() if line.startswith("- ")]

    def test_section_comes_directly_after_the_short_description(self) -> None:
        """Only the title, the badges and the short description come before it."""
        self.assertEqual(self.readme.count(SECTION), 1)
        before = self.readme.split(SECTION)[0]
        blocks = [block.strip() for block in before.split("\n\n") if block.strip()]
        self.assertEqual(len(blocks), 3, blocks)
        self.assertEqual(blocks[0], "# ha-lite-resources")
        self.assertTrue(blocks[1].startswith("[!["), blocks[1])
        self.assertTrue(blocks[2].startswith("**"), blocks[2])
        self.assertTrue(blocks[2].endswith("**"), blocks[2])

    def test_added_features_come_before_the_fixed_issues(self) -> None:
        """The section has these two lists, in this order, and each has entries."""
        self.assertEqual(
            re.findall(r"^### .*$", self.section, re.MULTILINE), [FEATURES, ISSUES]
        )
        self.assertTrue(self._entries(FEATURES))
        self.assertTrue(self._entries(ISSUES))

    def test_tests_and_style_are_one_short_entry_of_the_added_features(self) -> None:
        """The tooling has one entry, and the list of corrections holds none of it."""
        tooling = [entry for entry in self._entries(FEATURES) if _TOOLING.search(entry)]
        self.assertEqual(len(tooling), 1, tooling)
        self.assertLessEqual(len(tooling[0]), 250)
        self.assertEqual(
            [entry for entry in self._entries(ISSUES) if _TOOLING.search(entry)], []
        )

    def test_section_names_the_original_and_its_version(self) -> None:
        """A reader can find the code that the list of corrections speaks of."""
        intro = self.section.split(FEATURES)[0]
        self.assertIn("https://github.com/evski/ha-lite-resources", intro)
        self.assertIn("0.2.1", intro)
        self.assertIn("(CHANGELOG.md)", intro)

    def test_release_steps_keep_the_section_current(self) -> None:
        """The steps of a release name the section, so that each version updates it."""
        steps = self.readme.split("## Releasing")[1].split("## License")[0]
        self.assertIn("(#what-this-fork-changes)", steps)


if __name__ == "__main__":
    unittest.main()
