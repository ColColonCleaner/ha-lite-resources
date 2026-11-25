"""The script scripts/validate.py runs each check of the validation.

It lets no check pass by default.

The checks of the script and of the Validate workflow must stay the same. hassfest must
run with no network and no volume, from an image that is named by its digest.
"""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "validate_script", ROOT / "scripts" / "validate.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_script"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_validate = _load()

_PASS_OUTPUT = (
    "Validating manifest... done in 0.00s\n\nIntegrations: 1\nInvalid integrations: 0\n"
)


def _scratch_environment(**more: str) -> dict[str, str]:
    """Return the environment for git in a scratch repository.

    These tests also run inside a git hook of this repository. git gives a hook variables
    such as GIT_DIR, and with them a git command in another folder acts on this
    repository. So a scratch repository gets none of them.
    """
    return {**_validate.without_git(os.environ), **more}


def _git(folder: Path, *arguments: str, **environment: str) -> str:
    """Run git in a scratch repository, with an identity and with no signature."""
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        cwd=folder,
        env=_scratch_environment(**environment),
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


class ChecksTest(unittest.TestCase):
    """Which checks the script runs."""

    def test_each_python_check_of_the_workflow_is_a_check_of_the_script(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yaml").read_text(
            encoding="utf-8"
        )
        # Each step that runs a module, with no step that installs a package.
        steps = re.findall(r"\.venv/bin/python (-m (?!pip |venv ).+)", workflow)
        in_script = {
            " ".join(arguments) for _name, arguments in _validate.PYTHON_CHECKS
        }
        self.assertEqual(set(steps), in_script)
        self.assertEqual(len(steps), len(_validate.PYTHON_CHECKS))

    def test_workflow_runs_the_hassfest_action_whose_image_the_script_runs(
        self,
    ) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("home-assistant/actions/hassfest@master", workflow)
        self.assertTrue(
            _validate.HASSFEST_IMAGE.startswith("ghcr.io/home-assistant/hassfest@")
        )

    def test_each_place_names_one_tag_of_the_core_source(self) -> None:
        # The workflow, the README and the settings of the full type check each give the
        # command that clones Home Assistant core. One tag serves all three.
        tags = []
        for name in (
            ".github/workflows/validate.yaml",
            "README.md",
            "mypy-homeassistant.ini",
        ):
            text = (ROOT / name).read_text(encoding="utf-8")
            found = re.findall(
                r"--branch (\S+) https://github\.com/home-assistant/core", text
            )
            self.assertEqual(len(found), 1, name)
            tags.extend(found)
        self.assertEqual(len(set(tags)), 1, tags)
        self.assertRegex(tags[0], r"^\d{4}\.\d{1,2}\.\d+$")

    def test_run_holds_each_check_one_time_and_hassfest_last(self) -> None:
        names = [name for name, _check in _validate.checks({}, False)]
        self.assertEqual(
            names, [*(name for name, _a in _validate.PYTHON_CHECKS), "hassfest"]
        )
        with_tree = [name for name, _check in _validate.checks({}, True)]
        self.assertEqual(with_tree, ["the working tree is the commit", *names])

    def test_no_argument_leaves_a_check_out(self) -> None:
        self.assertEqual(_validate.main(["--skip-hassfest"]), 2)

    def test_failed_check_gives_exit_code_1_and_the_later_checks_still_run(
        self,
    ) -> None:
        ran: list[str] = []

        def check(name: str, passed: bool):
            def run() -> tuple[bool, str]:
                ran.append(name)
                return passed, f"output of {name}"

            return name, run

        shown: list[str] = []
        code = _validate.run(
            [check("a", True), check("b", False), check("c", True)], shown.append
        )
        self.assertEqual(code, 1)
        self.assertEqual(ran, ["a", "b", "c"])
        self.assertIn("FAIL  b", shown)
        self.assertIn("      output of b", shown)
        self.assertNotIn("      output of a", shown)
        self.assertEqual(_validate.run([check("a", True)], shown.append), 0)

    def test_full_type_check_fails_with_no_path_of_the_core_source(self) -> None:
        passed, output = _validate.full_type_check({})
        self.assertFalse(passed)
        self.assertIn("MYPYPATH is not set", output)


class HassfestTest(unittest.TestCase):
    """How the script runs hassfest, and how it reads the result."""

    def test_image_is_named_by_its_digest(self) -> None:
        self.assertRegex(
            _validate.HASSFEST_IMAGE,
            r"^ghcr\.io/home-assistant/hassfest@sha256:[0-9a-f]{64}$",
        )

    def test_container_gets_no_network_no_volume_and_no_pull(self) -> None:
        command = _validate.hassfest_command(None)
        self.assertEqual(command[:2], ["docker", "run"])
        for option, value in (("--network", "none"), ("--pull", "never")):
            self.assertEqual(command[command.index(option) + 1], value)
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
        self.assertIn("--rm", command)
        for option in ("-v", "--volume", "--mount", "--privileged", "--volumes-from"):
            self.assertNotIn(option, command)

    def test_ssh_arguments_send_the_same_docker_command_to_the_host(self) -> None:
        command = _validate.hassfest_command("-o ConnectTimeout=20 builder@buildhost")
        self.assertEqual(command[:3], ["ssh", "-o", "BatchMode=yes"])
        self.assertEqual(command[3:6], ["-o", "ConnectTimeout=20", "builder@buildhost"])
        # The host's shell gets one string, which splits into the docker command again.
        self.assertEqual(shlex.split(command[6]), _validate.hassfest_command(None))
        self.assertEqual(len(command), 7)

    def test_tar_stream_holds_the_integration_and_no_cache(self) -> None:
        with tarfile.open(fileobj=io.BytesIO(_validate.integration_tar())) as archive:
            names = archive.getnames()
        self.assertIn("custom_components/lite_resources/manifest.json", names)
        self.assertIn("custom_components/lite_resources/translations/en.json", names)
        self.assertEqual([name for name in names if "__pycache__" in name], [])
        self.assertTrue(all(name.startswith("custom_components") for name in names))

    def test_pass_needs_the_result_line_and_no_finding(self) -> None:
        verdict = _validate.hassfest_verdict
        self.assertTrue(verdict(0, _PASS_OUTPUT))
        # hassfest exits with 0 for a warning.
        warning = _PASS_OUTPUT + "* [WARNING] [CONFIG_SCHEMA] a text\n"
        self.assertFalse(verdict(0, warning))
        self.assertFalse(
            verdict(1, "Invalid integrations: 1\n* [ERROR] [MANIFEST] x\n")
        )
        # A run with no result line, such as a docker error, is no pass.
        self.assertFalse(verdict(0, ""))
        self.assertFalse(verdict(125, _PASS_OUTPUT))

    def test_missing_program_is_a_failed_check_and_no_crash(self) -> None:
        saved = _validate.HASSFEST_DOCKER
        _validate.HASSFEST_DOCKER = ("no-such-program-of-this-test", "run")
        try:
            passed, output = _validate.hassfest_check({"PATH": ""})
        finally:
            _validate.HASSFEST_DOCKER = saved
        self.assertFalse(passed)
        self.assertIn("is not on this machine", output)


class TreeTest(unittest.TestCase):
    """The check that the working tree holds no more than the commit.

    Each test runs with the variables that git gives a hook, which name a decoy
    repository here. In a real hook they name this repository, and a scratch repository
    that took them changed the settings of the clone.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.decoy = Path(self._tmp.name) / "decoy.git"
        self.decoy.mkdir()
        hook_variables = mock.patch.dict(
            os.environ,
            {"GIT_DIR": str(self.decoy), "GIT_INDEX_FILE": str(self.decoy / "index")},
        )
        hook_variables.start()
        self.addCleanup(hook_variables.stop)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "core.hooksPath", ".git/hooks")
        for name in ("a.txt", "b.txt"):
            (self.repo / name).write_text("one\n", encoding="utf-8")
        _git(self.repo, "add", "a.txt", "b.txt")
        _git(self.repo, "commit", "-q", "-m", "first")
        self._root = _validate.ROOT
        _validate.ROOT = self.repo

    def tearDown(self) -> None:
        _validate.ROOT = self._root
        self._tmp.cleanup()

    def _tree_check(self) -> tuple[bool, str]:
        return _validate.tree_check(_scratch_environment())

    def test_scratch_repository_takes_no_variable_of_a_hook(self) -> None:
        # The scratch repository has its own folder, and the decoy got no file.
        self.assertTrue((self.repo / ".git" / "HEAD").is_file())
        self.assertEqual(list(self.decoy.iterdir()), [])
        self.assertEqual(_git(self.repo, "log", "--format=%s").split(), ["first"])

    def test_checks_that_are_python_modules_get_no_variable_of_git(self) -> None:
        program = "import os, sys; sys.exit(any(n.upper().startswith('GIT_') for n in os.environ))"
        passed, _output = _validate.python_check(("-c", program), os.environ)
        self.assertTrue(passed)

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(self._tree_check(), (True, ""))

    def test_untracked_file_fails(self) -> None:
        (self.repo / "new.txt").write_text("x\n", encoding="utf-8")
        passed, output = self._tree_check()
        self.assertFalse(passed)
        self.assertIn("?? new.txt", output)

    def test_staged_change_passes_and_a_change_left_out_fails(self) -> None:
        (self.repo / "a.txt").write_text("two\n", encoding="utf-8")
        _git(self.repo, "add", "a.txt")
        self.assertEqual(self._tree_check(), (True, ""))
        (self.repo / "b.txt").write_text("two\n", encoding="utf-8")
        passed, output = self._tree_check()
        self.assertFalse(passed)
        self.assertIn(" M b.txt", output)
        self.assertNotIn("a.txt", output)

    def test_hook_of_a_commit_that_names_its_paths_sees_the_index_of_that_commit(
        self,
    ) -> None:
        # The document of the git hooks does not state this, and the check rests on it.
        seen = self.repo / "seen-by-the-hook.txt"
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(
            '#!/bin/sh\ngit status --porcelain > "$HOOK_OUT"\n',
            encoding="utf-8",
            newline="\n",
        )
        hook.chmod(0o755)
        for name in ("a.txt", "b.txt"):
            (self.repo / name).write_text("two\n", encoding="utf-8")
        # Nothing is staged. The commit names one of the two changed files.
        _git(
            self.repo,
            "commit",
            "-q",
            "-m",
            "second",
            "--",
            "a.txt",
            HOOK_OUT=seen.as_posix(),
        )
        lines = seen.read_text(encoding="utf-8").splitlines()
        self.assertIn("M  a.txt", lines)
        self.assertIn(" M b.txt", lines)


if __name__ == "__main__":
    unittest.main()
