"""Check a release tag against the repository, and print or publish the notes of its release.

    python scripts/release_notes.py v0.3.9
    python scripts/release_notes.py v0.3.9 --publish

Run the first form before the push of a tag: it shows what the release will say, or why the
tag is wrong. The script exits with 1, and names the reason, when:

- the tag is not "v" plus the version of the manifest at this commit,
- CHANGELOG.md has no entry for that version, or an entry with no text,
- the section "Unreleased" of CHANGELOG.md holds text. A release then would leave a change
  out of its notes, so each change of the commit belongs to the entry of its version.

The notes are the changelog entry of the version, without its heading.

The Release workflow runs the second form for a pushed tag. After the same checks, it
creates the GitHub release of the tag, with the tag as its name and the notes as its text,
and prints the address of the release. It reads three environment variables, which a
GitHub workflow provides: GITHUB_TOKEN, a token with write access to the repository's
contents, GITHUB_REPOSITORY, the owner and the name of the repository, and GITHUB_API_URL,
the root of the API. The script never prints the token.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("custom_components") / "lite_resources" / "manifest.json"
TAG_PREFIX = "v"
UNRELEASED = "Unreleased"
# The version of the GitHub REST API whose document for "Create a release" this script
# follows.
API_VERSION = "2026-03-10"
DEFAULT_API_URL = "https://api.github.com"
CREATED = 201


class ReleaseError(Exception):
    """The tag and the repository do not fit, and the text says why."""


def manifest_version(root: Path) -> str:
    """Return the version that the integration's manifest holds."""
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    return str(manifest["version"])


def section(changelog: str, name: str) -> str | None:
    """Return the text under the level 2 heading for this name, or None with no such heading.

    The heading is the name alone, or the name with " - " and a date after it. The text
    ends before the next level 2 heading, and keeps each deeper heading.
    """
    heading = re.compile(rf"^## {re.escape(name)}(?: - .*)?[ \t]*$", re.MULTILINE)
    found = heading.search(changelog)
    if found is None:
        return None
    rest = changelog[found.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return (rest[: following.start()] if following else rest).strip()


def notes_for(tag: str, root: Path) -> str:
    """Return the notes of the release for this tag, or raise ReleaseError."""
    version = manifest_version(root)
    if tag != f"{TAG_PREFIX}{version}":
        raise ReleaseError(
            f"The tag {tag} does not fit the manifest, whose version is {version}. "
            f"The tag of that version is {TAG_PREFIX}{version}."
        )
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if section(changelog, UNRELEASED):
        raise ReleaseError(
            f"The section {UNRELEASED} of CHANGELOG.md holds text. Move it into the "
            f"entry of version {version} before the release."
        )
    notes = section(changelog, version)
    if not notes:
        raise ReleaseError(
            f"CHANGELOG.md has no entry with text for version {version}."
        )
    return notes


def release_request(
    tag: str, notes: str, environment: Mapping[str, str]
) -> urllib.request.Request:
    """Return the request that creates the release of this tag, as the REST API asks.

    The request names no commit. GitHub uses the tag that exists, and the workflow checks
    the repository out at that tag before it runs this script, so a tag that does not
    exist stops the workflow before this request.
    """
    missing = [
        name
        for name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY")
        if not environment.get(name)
    ]
    if missing:
        raise ReleaseError(
            f"The environment lacks {' and '.join(missing)}, which a release needs."
        )
    root = (environment.get("GITHUB_API_URL") or DEFAULT_API_URL).rstrip("/")
    payload = {
        "tag_name": tag,
        "name": tag,
        "body": notes,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False,
    }
    return urllib.request.Request(
        f"{root}/repos/{environment['GITHUB_REPOSITORY']}/releases",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {environment['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": API_VERSION,
            # Without this header, urllib names the data a form.
            "Content-Type": "application/json",
        },
        method="POST",
    )


def publish(
    tag: str,
    notes: str,
    environment: Mapping[str, str],
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """Create the GitHub release of this tag, and return the address of its page.

    Each failure becomes a ReleaseError with the answer of GitHub, such as the status 422
    for a tag that has a release already. The text never holds the token.
    """
    request = release_request(tag, notes, environment)
    try:
        with opener(request, timeout=60) as response:
            status = response.status
            answer = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")[:500]
        raise ReleaseError(
            f"GitHub answered {err.code} to the creation of the release {tag}: {text}"
        ) from err
    except urllib.error.URLError as err:
        raise ReleaseError(f"GitHub did not answer: {err.reason}") from err
    if status != CREATED:
        raise ReleaseError(
            f"GitHub answered {status} to the creation of the release {tag}, "
            f"and {CREATED} means that the release exists: {answer[:500]}"
        )
    return str(json.loads(answer).get("html_url", ""))


def main(
    arguments: Sequence[str],
    environment: Mapping[str, str] = os.environ,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> int:
    """Print the notes for the tag, or create its release with --publish."""
    to_publish = "--publish" in arguments
    tags = [argument for argument in arguments if argument != "--publish"]
    if len(tags) != 1 or tags[0].startswith("-"):
        print(
            "Usage: python scripts/release_notes.py <tag> [--publish]", file=sys.stderr
        )
        return 2
    tag = tags[0]
    try:
        notes = notes_for(tag, ROOT)
        if to_publish:
            print(f"Release {tag}: {publish(tag, notes, environment, opener)}")
            return 0
    except ReleaseError as err:
        print(err, file=sys.stderr)
        return 1
    # The notes hold characters outside the code page of a Windows console.
    sys.stdout.buffer.write((notes + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
