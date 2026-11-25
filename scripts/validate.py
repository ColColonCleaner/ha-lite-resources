"""Run the full validation of this repository with one command.

    python scripts/validate.py

Run it from any folder, before each commit, with a Python that holds the packages of the
checks. CONTRIBUTING.md names them with their versions. The script runs the unit tests, the
static checks and the format check of ruff, both type checks of mypy, and hassfest. It
prints the result of each check. It exits with 1 when a check fails or cannot run, and
no option leaves a check out.

Two checks read a value from the environment:

MYPYPATH
    The path of a clone of Home Assistant core, at the tag of the Home Assistant version
    that runs the integration. mypy-homeassistant.ini says how to make the clone.
LITE_RESOURCES_HASSFEST_SSH
    Optional. The arguments of ssh for a host that runs Docker: its options, then the
    destination, such as "-o ConnectTimeout=20 builder@buildhost". hassfest then runs in
    a container on that host. With no value, the script calls docker on this machine.

hassfest is the validation of Home Assistant for an integration's manifest, translations,
services and other files. It has no release as a package, so the script runs the container
image that the GitHub action home-assistant/actions/hassfest runs. The image is named by
its digest, and the container gets no network and no volume: the files of
custom_components reach it as a tar stream on its standard input. Pull the image once
on the Docker host before the first run:

    docker pull <the value of HASSFEST_IMAGE below>

With --tree-is-the-commit, the script first refuses a working tree that holds more than
the commit: a tracked file with a change that the commit leaves out, or an untracked file.
The checks read the working tree, so only then do they check the commit. A pre-commit hook
passes this option.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]

# The arguments after the Python executable, for each check that is a Python module. The
# Validate workflow runs the same commands, and tests/test_validate.py compares the two.
PYTHON_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("unit tests", ("-m", "unittest", "discover", "-s", "tests")),
    ("ruff check", ("-m", "ruff", "check", ".")),
    ("ruff format", ("-m", "ruff", "format", "--check", ".")),
    ("mypy", ("-m", "mypy")),
    (
        "mypy with the types of Home Assistant",
        ("-m", "mypy", "--config-file", "mypy-homeassistant.ini"),
    ),
)
# The check that needs MYPYPATH.
FULL_TYPE_CHECK = "mypy with the types of Home Assistant"

# The image of the hassfest action, by its digest. A tag can move to another image, and a
# digest cannot. To take a newer image, pull the tag "latest" on the Docker host, and put
# the digest that docker prints here.
HASSFEST_IMAGE = (
    "ghcr.io/home-assistant/hassfest"
    "@sha256:d5269221a05a4b744f2bf88d22af9449f8c490bbc54c9097a9c53cd9cfc76bfe"
)
# The command inside the container. It unpacks the tar stream from the standard input
# into the folder that the image's entry point reads, and then starts that entry point,
# which finds each manifest.json under custom_components and runs hassfest on its folder.
# The tar option -o keeps the files' owner out, because the container holds no capability
# to change an owner.
HASSFEST_IN_CONTAINER = (
    "tar -x -o -f - -C /github/workspace"
    " && exec /usr/src/homeassistant/script/hassfest/docker/entrypoint.sh"
)
# --pull never: a run never fetches an image. A host with no copy of the image fails.
# --network none, and no volume: the container reaches no host and no file of the host.
# --cap-drop ALL and no-new-privileges: the processes in the container hold no capability.
# The three limits keep a run small beside the other work of the host.
HASSFEST_DOCKER: tuple[str, ...] = (
    "docker",
    "run",
    "--rm",
    "-i",
    "--pull",
    "never",
    "--network",
    "none",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--memory",
    "2g",
    "--pids-limit",
    "512",
    "--cpus",
    "2",
    "--entrypoint",
    "sh",
    HASSFEST_IMAGE,
    "-c",
    HASSFEST_IN_CONTAINER,
)
# The last line of a hassfest run that found no error.
HASSFEST_PASS = "Invalid integrations: 0"
# hassfest marks each finding with one of these. It exits with 0 for a warning, and this
# script fails for both.
HASSFEST_FINDINGS = ("[ERROR]", "[WARNING]")

type Result = tuple[bool, str]
type Check = tuple[str, Callable[[], Result]]


def without_git(environment: Mapping[str, str]) -> dict[str, str]:
    """Return the environment with no variable of git.

    In a hook, git sets variables such as GIT_DIR and GIT_INDEX_FILE, which name this
    repository. A check that starts git in another folder would then act on this
    repository: a unit test that made a scratch repository changed the settings of the
    clone that way. So only the check of the working tree gets these variables.
    """
    return {
        name: value
        for name, value in environment.items()
        if not name.upper().startswith("GIT_")
    }


def python_check(arguments: Sequence[str], environment: Mapping[str, str]) -> Result:
    """Run one Python module in the root of the repository, with the Python of this run."""
    done = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=without_git(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.returncode == 0, done.stdout + done.stderr


def full_type_check(environment: Mapping[str, str]) -> Result:
    """Run the type check that reads the source of Home Assistant core."""
    if not environment.get("MYPYPATH"):
        return False, (
            "MYPYPATH is not set. It names a clone of Home Assistant core, and "
            "mypy-homeassistant.ini says how to make the clone."
        )
    arguments = dict(PYTHON_CHECKS)[FULL_TYPE_CHECK]
    return python_check(arguments, environment)


def integration_tar() -> bytes:
    """Return the folder custom_components as a tar stream, with no bytecode cache."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        archive.add(
            ROOT / "custom_components",
            arcname="custom_components",
            filter=lambda member: None if "__pycache__" in member.name else member,
        )
    return stream.getvalue()


def hassfest_command(ssh_arguments: str | None) -> list[str]:
    """Return the command that runs hassfest: docker here, or docker on a host over ssh.

    BatchMode makes ssh fail where it would ask for a password or for a host key.
    """
    if not ssh_arguments:
        return list(HASSFEST_DOCKER)
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        *shlex.split(ssh_arguments),
        shlex.join(HASSFEST_DOCKER),
    ]


def hassfest_verdict(returncode: int, output: str) -> bool:
    """True when hassfest ran to its end with no error and no warning.

    The exit code alone is not enough: it is 0 for a warning, and a run that printed no
    result at all, such as one with no integration, must not count as a pass.
    """
    return (
        returncode == 0
        and HASSFEST_PASS in output
        and not any(mark in output for mark in HASSFEST_FINDINGS)
    )


def hassfest_check(environment: Mapping[str, str]) -> Result:
    """Run hassfest on the integration in a container, and return its verdict."""
    command = hassfest_command(environment.get("LITE_RESOURCES_HASSFEST_SSH"))
    try:
        done = subprocess.run(
            command,
            input=integration_tar(),
            env=without_git(environment),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return False, f"The program {command[0]} is not on this machine."
    output = (done.stdout + done.stderr).decode("utf-8", errors="replace")
    return hassfest_verdict(done.returncode, output), output


def tree_check(environment: Mapping[str, str]) -> Result:
    """Fail when the working tree holds more than the commit that git prepares.

    `git status --porcelain` gives two letters for each path: the state in the index, and
    the state in the working tree against the index. A letter in the second place is a
    change that the commit leaves out, and "??" is an untracked file. In a pre-commit
    hook, git gives the index of the commit also for a commit that names its paths. The
    document of the hooks does not say so, and a test in tests/test_validate.py holds it.
    This check keeps the variables of git, because they name that index.
    """
    done = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if done.returncode != 0:
        return False, done.stdout + done.stderr
    left_out = [line for line in done.stdout.splitlines() if line[1:2] != " "]
    if not left_out:
        return True, ""
    return False, (
        "The checks read the working tree, and these paths are not as in the commit. "
        "Commit them, or move them away, and run again:\n" + "\n".join(left_out)
    )


def checks(environment: Mapping[str, str], tree_is_the_commit: bool) -> list[Check]:
    """Return each check with its name, in the order of the run."""
    found: list[Check] = []
    if tree_is_the_commit:
        found.append(
            ("the working tree is the commit", lambda: tree_check(environment))
        )
    for name, arguments in PYTHON_CHECKS:
        if name == FULL_TYPE_CHECK:
            found.append((name, lambda: full_type_check(environment)))
        else:
            found.append(
                (name, lambda arguments=arguments: python_check(arguments, environment))
            )
    found.append(("hassfest", lambda: hassfest_check(environment)))
    return found


def run(to_run: Sequence[Check], show: Callable[[str], None] = print) -> int:
    """Run each check, also after a failed one, and return the exit code."""
    failed: list[str] = []
    for name, check in to_run:
        passed, output = check()
        show(f"{'PASS' if passed else 'FAIL'}  {name}")
        if not passed:
            failed.append(name)
            for line in output.rstrip().splitlines():
                show(f"      {line}")
    if failed:
        show(f"{len(failed)} of {len(to_run)} checks failed: {', '.join(failed)}")
        return 1
    show(f"Each of the {len(to_run)} checks passed.")
    return 0


def main(arguments: Sequence[str]) -> int:
    """Run the checks. The one option is --tree-is-the-commit."""
    unknown = [item for item in arguments if item != "--tree-is-the-commit"]
    if unknown:
        print(f"Unknown argument: {' '.join(unknown)}", file=sys.stderr)
        return 2
    return run(checks(os.environ, "--tree-is-the-commit" in arguments))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
