"""The texts of the forms agree with the forms.

Home Assistant shows the raw key of a field or of an error when no text exists for it.
"""

from __future__ import annotations

import json
import re
import unittest

from support import PACKAGE, load

_const = load("lite_resources.const", "const.py")


def _strings() -> dict:
    return json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))


class TranslationsTest(unittest.TestCase):
    """strings.json, its English copy, and the group form."""

    def setUp(self) -> None:
        self.flow = (PACKAGE / "config_flow.py").read_text(encoding="utf-8")
        self.group = _strings()["config_subentries"][_const.SUBENTRY_GROUP]

    def test_english_translation_equals_strings(self) -> None:
        english = json.loads(
            (PACKAGE / "translations" / "en.json").read_text(encoding="utf-8")
        )
        self.assertEqual(english, _strings())

    def test_each_field_of_the_group_form_has_a_label_and_a_description(self) -> None:
        names = re.findall(r"vol\.(?:Required|Optional)\(\s*(CONF_[A-Z_]+)", self.flow)
        fields = {getattr(_const, name) for name in names}
        self.assertEqual(len(fields), 8)
        for step in ("user", "reconfigure"):
            self.assertEqual(set(self.group["step"][step]["data"]), fields, step)
            self.assertEqual(
                set(self.group["step"][step]["data_description"]), fields, step
            )

    def test_each_error_of_the_group_form_has_a_text(self) -> None:
        errors = set(re.findall(r'return \{CONF_[A-Z_]+: "([a-z_]+)"\}', self.flow))
        self.assertEqual(len(errors), 4)
        self.assertEqual(set(self.group["error"]), errors)

    def test_group_has_the_labels_of_its_buttons(self) -> None:
        self.assertTrue(self.group["entry_type"])
        self.assertEqual(set(self.group["initiate_flow"]), {"user", "reconfigure"})

    def test_no_text_remains_for_the_options_form(self) -> None:
        # Versions up to 0.2.1 kept one group in an options form.
        self.assertNotIn("options", _strings())


if __name__ == "__main__":
    unittest.main()
