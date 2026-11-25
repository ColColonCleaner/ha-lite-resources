"""The texts keep to the words of the README's section "One word for one thing".

A reader who meets two words for one thing asks if the second word is a second thing. Each
pattern below is a word or a construction that an earlier version held, and that the texts
no longer use. A code span is a quotation, such as a key or a log message of an older
version, so the checks leave each code span out.
"""

from __future__ import annotations

import json
import re
import unittest

from support import ROOT

INTEGRATION = ROOT / "custom_components" / "lite_resources"
WORD_TABLE = "### One word for one thing"
FIRST_ORIGINAL_ENTRY = "## 0.2.1"

PATTERNS = {
    "a possessive before own": r"\b\w+'s own\b",
    "two possessives in a row": r"\b\w+'s \w+'s\b",
    "narrow, for state filtering": r"\bnarrow(?:s|ed|ing)?\b",
    "time limit, for a timeout": r"\btime limits?\b",
    "later tries, for retries": r"\blater tr(?:y|ies)\b",
    # The singular only: "a page loads" is a page and a verb.
    "page load, for a page reload": r"\bpage load\b",
    "connects again, for reconnects": r"\bconnects? again\b",
    "at once, for immediately": r"\bat once\b",
    "one time, for once": r"\bone time\b",
    "upstream, for the original": r"\bupstream\b",
    # "scans" is also the plural of the noun, so only these two forms are sure verbs.
    "scan as a verb": r"\bscann(?:ed|ing)\b",
    # The singular only: "a card names an area" is a card and a verb.
    "card name or element, for a card type": r"\bcard name\b|\belements?\b",
    "group of entities, for an entity group": r"\bgroups? of entities\b",
    "field, for an option": r"\bfields?\b",
    # A place in Home Assistant's settings takes its path. "page" is a browser tab.
    "page, for a place in the settings": r"\b(?:integration|repository)'s page\b",
    # The original and this fork are two versions of the integration. A sentence that
    # compares them names this fork.
    "this integration, for this fork beside the original": (
        r"[^.\n]*\bthe original\b[^.\n]*\bthis integration\b"
        r"|[^.\n]*\bthis integration\b[^.\n]*\bthe original\b"
    ),
    # The name of an option is bold. A single asterisk on each side is italics.
    "an option name in italics": (
        r"(?<!\*)\*(?:Always include|Always exclude|Extra entities)\*(?!\*)"
    ),
}


def _without_code(text: str) -> str:
    """Return the text with each fenced block and each code span left out."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def _readme() -> str:
    """Return the README without its word table, which names the words to avoid."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    before, _, rest = text.partition(WORD_TABLE)
    _, _, after = rest.partition("\n## ")
    return _without_code(before + after)


def _changelog() -> str:
    """Return the entries of the changelog that are newer than the original's."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return _without_code(text.split(FIRST_ORIGINAL_ENTRY)[0])


def _form_texts() -> str:
    """Return each text of the forms, one on a line."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, str):
            found.append(node)

    walk(json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8")))
    return "\n".join(found)


class WordingTest(unittest.TestCase):
    """No text holds a word or a construction that the word table replaced."""

    def _check(self, name: str, text: str) -> None:
        for label, pattern in PATTERNS.items():
            with self.subTest(text=name, pattern=label):
                found = re.findall(pattern, text, flags=re.IGNORECASE)
                self.assertEqual(found, [], f"{name} holds {label}")

    def test_readme(self) -> None:
        self._check("README.md", _readme())

    def test_changelog_entries_of_this_fork(self) -> None:
        self._check("CHANGELOG.md", _changelog())

    def test_form_texts(self) -> None:
        self._check("strings.json", _form_texts())

    def test_word_table_is_in_the_readme(self) -> None:
        """The checks leave the table out, so the table must be there to leave out."""
        self.assertEqual(
            (ROOT / "README.md").read_text(encoding="utf-8").count(WORD_TABLE), 1
        )


if __name__ == "__main__":
    unittest.main()
