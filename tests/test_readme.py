"""The README's instructions are complete.

An instruction that names an action also says where that action is. An earlier version's
reader found "select Add group" with no place.
"""

from __future__ import annotations

import re
import unittest

from support import ROOT


class ReadmeTest(unittest.TestCase):
    """The README's setup instructions and pictures."""

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

    def test_button_is_not_given_as_a_replacement_of_the_steps(self) -> None:
        # A button opens one dialog. The steps after that dialog stay necessary.
        self.assertNotIn("Or do these steps", self.readme)
        setup = self.readme.split("## Set up")[1].split("| Option |")[0]
        button = setup.index("config_flow_start")
        self.assertGreater(button, setup.index("1. Open the dialog"))
        self.assertLess(button, setup.index("2. The dialog has no settings"))

    def test_setup_names_the_page_of_the_integration(self) -> None:
        self.assertIn("**Settings → Devices & services → Lite Resources**", self.readme)
        self.assertIn("**Settings → Marketplace**", self.readme)


if __name__ == "__main__":
    unittest.main()
