"""The script scripts/release_notes.py refuses a wrong tag, and gives the right notes.

A release with a wrong tag, or with notes that leave a change out, cannot be taken back
with no trace: Home Assistant shows the tag as the version.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Self
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "release_notes_script", ROOT / "scripts" / "release_notes.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_notes_script"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_release = _load()

CHANGELOG = """# Changelog

## Unreleased

## 1.2.3 - 2026-01-02

The first paragraph.

### A part

- One change.

## 1.2.2

- An older change.

## 1.2.10 - 2025-12-01

- A change of another version whose number starts with the same digits.
"""


class _Repository:
    """A scratch repository with a manifest and a changelog."""

    def __init__(self, version: str, changelog: str) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        manifest = self.root / "custom_components" / "lite_resources" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"version": version}), encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    def close(self) -> None:
        self._tmp.cleanup()


class SectionTest(unittest.TestCase):
    """The text of one changelog entry."""

    def test_entry_with_a_date_ends_before_the_next_version(self) -> None:
        self.assertEqual(
            _release.section(CHANGELOG, "1.2.3"),
            "The first paragraph.\n\n### A part\n\n- One change.",
        )

    def test_entry_with_no_date(self) -> None:
        self.assertEqual(_release.section(CHANGELOG, "1.2.2"), "- An older change.")

    def test_last_entry_runs_to_the_end_of_the_file(self) -> None:
        self.assertTrue(_release.section(CHANGELOG, "1.2.10").startswith("- A change"))

    def test_version_is_no_prefix_of_another_version(self) -> None:
        # "1.2.1" is the start of "1.2.10", and it has no entry.
        self.assertIsNone(_release.section(CHANGELOG, "1.2.1"))

    def test_empty_section_gives_an_empty_text(self) -> None:
        self.assertEqual(_release.section(CHANGELOG, "Unreleased"), "")
        self.assertIsNone(_release.section(CHANGELOG, "9.9.9"))


class NotesTest(unittest.TestCase):
    """The checks of a tag against the manifest and the changelog."""

    def _notes(self, tag: str, version: str = "1.2.3", changelog: str = CHANGELOG):
        repository = _Repository(version, changelog)
        self.addCleanup(repository.close)
        return _release.notes_for(tag, repository.root)

    def test_tag_of_the_manifest_version_gives_its_entry(self) -> None:
        self.assertTrue(self._notes("v1.2.3").startswith("The first paragraph."))

    def test_tag_of_another_version_is_refused(self) -> None:
        with self.assertRaisesRegex(_release.ReleaseError, "does not fit the manifest"):
            self._notes("v1.2.2")

    def test_tag_with_no_prefix_is_refused(self) -> None:
        with self.assertRaisesRegex(_release.ReleaseError, "is v1.2.3"):
            self._notes("1.2.3")

    def test_text_under_unreleased_is_refused(self) -> None:
        changelog = CHANGELOG.replace(
            "## Unreleased\n", "## Unreleased\n\n- A change with no version.\n"
        )
        with self.assertRaisesRegex(_release.ReleaseError, "Unreleased"):
            self._notes("v1.2.3", changelog=changelog)

    def test_version_with_no_entry_is_refused(self) -> None:
        with self.assertRaisesRegex(_release.ReleaseError, "no entry with text"):
            self._notes("v2.0.0", version="2.0.0")

    def test_changelog_with_no_unreleased_section_is_accepted(self) -> None:
        changelog = CHANGELOG.replace("## Unreleased\n\n", "")
        self.assertTrue(self._notes("v1.2.3", changelog=changelog))


class _Response:
    """Stand-in for the response of urllib.request.urlopen."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *error: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


# The values of a workflow run, with a text in the place of the token.
ENVIRONMENT = {
    "GITHUB_TOKEN": "text-in-the-place-of-the-token",
    "GITHUB_REPOSITORY": "owner/name",
    "GITHUB_API_URL": "https://api.example.test",
}


class PublishTest(unittest.TestCase):
    """The request that creates a release, and what the script does with the answer."""

    def setUp(self) -> None:
        self.requests: list = []
        self.answer: object = _Response(
            201, json.dumps({"html_url": "https://example.test/releases/v1.2.3"})
        )

    def _opener(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def _publish(self, environment=None) -> str:
        return _release.publish(
            "v1.2.3", "The notes.", environment or ENVIRONMENT, self._opener
        )

    def test_request_is_the_documented_call(self) -> None:
        self.assertEqual(self._publish(), "https://example.test/releases/v1.2.3")
        (request,) = self.requests
        self.assertEqual(
            request.full_url, "https://api.example.test/repos/owner/name/releases"
        )
        self.assertEqual(request.get_method(), "POST")
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(headers["accept"], "application/vnd.github+json")
        self.assertEqual(
            headers["authorization"], "Bearer text-in-the-place-of-the-token"
        )
        self.assertEqual(headers["x-github-api-version"], _release.API_VERSION)
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "tag_name": "v1.2.3",
                "name": "v1.2.3",
                "body": "The notes.",
                "draft": False,
                "prerelease": False,
                "generate_release_notes": False,
            },
        )

    def test_request_names_no_commit(self) -> None:
        # With a commit in the request, GitHub would make a tag that does not exist.
        self._publish()
        self.assertNotIn("target_commitish", json.loads(self.requests[0].data))

    def test_api_root_has_a_default(self) -> None:
        environment = {k: v for k, v in ENVIRONMENT.items() if k != "GITHUB_API_URL"}
        self._publish(environment)
        self.assertEqual(
            self.requests[0].full_url,
            "https://api.github.com/repos/owner/name/releases",
        )

    def test_missing_variable_is_named_and_no_request_goes_out(self) -> None:
        environment = {k: v for k, v in ENVIRONMENT.items() if k != "GITHUB_TOKEN"}
        with self.assertRaisesRegex(_release.ReleaseError, "GITHUB_TOKEN"):
            self._publish(environment)
        self.assertEqual(self.requests, [])

    def test_refusal_of_github_gives_its_answer_and_never_the_token(self) -> None:
        self.answer = urllib.error.HTTPError(
            "https://api.example.test/repos/owner/name/releases",
            422,
            "Unprocessable Entity",
            None,  # type: ignore[arg-type]
            io.BytesIO(b'{"message":"Validation Failed","errors":["already_exists"]}'),
        )
        with self.assertRaises(_release.ReleaseError) as raised:
            self._publish()
        text = str(raised.exception)
        self.assertIn("422", text)
        self.assertIn("already_exists", text)
        self.assertNotIn(ENVIRONMENT["GITHUB_TOKEN"], text)

    def test_answer_with_another_status_is_no_release(self) -> None:
        self.answer = _Response(200, "{}")
        with self.assertRaisesRegex(_release.ReleaseError, "answered 200"):
            self._publish()

    def test_no_answer_is_reported(self) -> None:
        self.answer = urllib.error.URLError("the name does not resolve")
        with self.assertRaisesRegex(_release.ReleaseError, "did not answer"):
            self._publish()


class PublishCommandTest(unittest.TestCase):
    """The command with --publish, against a scratch repository."""

    def setUp(self) -> None:
        self.repository = _Repository("1.2.3", CHANGELOG)
        self.addCleanup(self.repository.close)
        self._root = _release.ROOT
        _release.ROOT = self.repository.root
        self.addCleanup(setattr, _release, "ROOT", self._root)
        self.requests: list = []

    def _opener(self, request, timeout=None):
        self.requests.append(request)
        return _Response(201, json.dumps({"html_url": "https://example.test/r"}))

    def _main(self, *arguments: str) -> tuple[int, str, str]:
        out, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errors):
            code = _release.main(list(arguments), ENVIRONMENT, self._opener)
        return code, out.getvalue(), errors.getvalue()

    def test_publish_sends_the_notes_of_the_tag(self) -> None:
        code, out, _errors = self._main("v1.2.3", "--publish")
        self.assertEqual(code, 0)
        self.assertIn("https://example.test/r", out)
        (request,) = self.requests
        self.assertTrue(
            json.loads(request.data)["body"].startswith("The first paragraph.")
        )
        self.assertNotIn(ENVIRONMENT["GITHUB_TOKEN"], out)

    def test_wrong_tag_sends_no_request(self) -> None:
        code, _out, errors = self._main("v1.2.2", "--publish")
        self.assertEqual(code, 1)
        self.assertIn("does not fit the manifest", errors)
        self.assertEqual(self.requests, [])

    def test_publish_with_no_tag_sends_no_request(self) -> None:
        code, _out, _errors = self._main("--publish")
        self.assertEqual(code, 2)
        self.assertEqual(self.requests, [])


class MainTest(unittest.TestCase):
    """The command line of the script, against this repository."""

    def test_this_repository_has_an_entry_for_its_manifest_version(self) -> None:
        version = _release.manifest_version(ROOT)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertTrue(_release.section(changelog, version), version)

    def test_wrong_tag_gives_exit_code_1_and_the_reason(self) -> None:
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = _release.main(["v0.0.0"])
        self.assertEqual(code, 1)
        self.assertIn("does not fit the manifest", errors.getvalue())

    def test_no_tag_gives_exit_code_2(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(_release.main([]), 2)


if __name__ == "__main__":
    unittest.main()
