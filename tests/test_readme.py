"""The instructions of the README are complete.

An instruction that names an action also says where that action is. A reader of an
earlier version found "select Add group" with no place.
"""

from __future__ import annotations

import re
import unittest

from support import ROOT


class ReadmeTest(unittest.TestCase):
    """The setup instructions and the pictures of the README."""

    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_each_picture_of_the_readme_exists(self) -> None:
        pictures = re.findall(r'src="(docs/images/[^"]+)"', self.readme)
        self.assertIn("docs/images/integration-page.png", pictures)
        for picture in pictures:
            self.assertTrue((ROOT / picture).is_file(), picture)

    def test_add_group_has_its_two_places(self) -> None:
        step = next(
            line for line in self.readme.splitlines() if line.startswith("4. Select **Add group**")
        )
        self.assertIn("the button in the upper-right corner", step)
        self.assertIn("the three-dot menu", step)

    def test_each_action_on_a_group_has_its_place(self) -> None:
        section = self.readme.split("### Change, rename or delete a group")[1].split("###")[0]
        self.assertIn("the cog icon", section)
        self.assertIn("**Rename**", section)
        self.assertIn("**Delete**", section)
        self.assertEqual(section.count("at the right of its row"), 3)

    def test_setup_names_the_page_of_the_integration(self) -> None:
        self.assertIn("**Settings → Devices & services → Lite Resources**", self.readme)
        self.assertIn("**Settings → Marketplace**", self.readme)


if __name__ == "__main__":
    unittest.main()
