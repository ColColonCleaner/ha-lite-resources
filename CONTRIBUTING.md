# Contributing to ha-lite-resources

Issues and pull requests are welcome. Please include your Home Assistant version and the output of `lite_resources.preview`.

The [README](README.md) holds what a user of the integration needs. This document holds the standards of the repository: the validation before a commit, the words of its texts, and the steps of a release.

## Validation

Before each commit, run the full validation with one command:

```bash
python scripts/validate.py
```

The script runs the unit tests, the static checks, two type checks and hassfest, and it has no option that skips a check. It exits with 1 when a check fails or cannot run. The comment at the top of [scripts/validate.py](scripts/validate.py) names the two environment variables that the script reads.

hassfest is the tool that the Home Assistant project uses to validate an integration's manifest, translations and services. The project does not release it as a package. So the script runs the container image of the GitHub action `home-assistant/actions/hassfest` with Docker, on your machine or on a host that the script reaches with `ssh`. The script names the image by its digest, and the container gets no network and no volume. The script also fails for a hassfest warning, which hassfest itself lets pass.

To make git refuse a commit that fails a check, add a `pre-commit` hook to your clone that runs `python scripts/validate.py --tree-is-the-commit`. With that option, the script first compares the working tree with the staged changes. This check fails when a tracked file holds a change that is not staged, or when a file is untracked. The other checks read the working tree, so they check the commit only when the two are the same.

The Validate workflow also runs the HACS action, with which the HACS project validates a custom repository. That action reads the repository on GitHub, so it cannot run locally. The unit tests cover the three files that it checks: the brand icon, `hacs.json` and the README.

These commands run the script's checks one at a time from the root of the repository, apart from hassfest and the second type check:

```bash
python -m unittest discover -s tests
ruff check .
ruff format --check .
mypy
```

The tests need Python 3.12 or later and the package `voluptuous`. They run against stand-ins, so they need no Home Assistant installation. The static checks and the format check need ruff 0.17.5, and the type checks need mypy 2.4.1. Those are the versions that the Validate workflow installs. `ruff.toml` and `mypy.ini` hold the settings. To format changed code, run `ruff format .`.

The command `mypy` does not read Home Assistant, so its result is the same on every machine. It checks the calls inside the integration, and each name from Home Assistant has the type `Any` there. A second type check reads the types of Home Assistant from the source of its core. It needs a clone of that source at the tag of your Home Assistant version, and it runs no code from that clone:

```bash
git clone --depth 1 --branch 2026.11.3 https://github.com/home-assistant/core ../home-assistant-core
MYPYPATH=../home-assistant-core mypy --config-file mypy-homeassistant.ini
```

On Windows, set `MYPYPATH` with your shell's syntax. The Validate workflow runs both type checks.

## One word for one thing

This repository uses one word for one thing in each of its texts: the README, this document, the changelog, the forms, the log and the comments. A second word for the same thing makes a reader ask if it is a second thing.

| The thing | Its word | Not for this thing |
|---|---|---|
| The hardware that shows a dashboard, such as a wall panel or a tablet | **device** | panel, screen, display |
| One browser tab or app window that shows Home Assistant, with its own connection | **page** | panel, device, client |
| A place in Home Assistant's settings, such as **Settings → Devices & services** | its path | page |
| A choice in a group's form | **option** | field |
| The name after `type:` in a card, such as `custom:mushroom-light-card` | **card type** | card name, element |
| An entity that holds other entities, such as a light group | **entity group** | group of entities |
| The browser loads the page again | **page reload** | refresh |
| Home Assistant loads the integration again | **reload of the integration** | restart |
| A user in a group | **lite user**, and a device **logs in** as that user | sign in |
| An entry of Home Assistant's list of dashboard resources | **resource**, and its file is the **resource file** | card file, script |
| The integration reads a group's dashboards to find the entities that they show | **entity scan** | scan alone |
| The integration reads a group's dashboards and resource files to find the resources that the dashboards use | **resource scan** | scan alone |
| The integration sends a page only the states of its group's entities | **entity filtering** | state filtering, narrow, limit |
| The integration sends a page only its group's resources | **resource filtering** | reduce, trim |
| The integration, in each of its versions, as the thing that acts | **this integration**, or `ha-lite-resources` | its display name, which stands only where a step names what Home Assistant shows |
| The version of the integration in this repository, where a text compares it with the original | **this fork** | this integration |
| A defect | **fault**, and a change **corrects** it | issue, bug |
| An entry of the issue list on GitHub | **issue** | |
| The version of the integration in the repository `evski/ha-lite-resources` | **the original** | upstream |
| Home Assistant sets the integration up | the integration's **setup** | start |
| What the user entered for the integration | **configuration** | setup |
| The checks before a commit | **validation**, with a **check** as one part of it | |

`scan` and `log` are nouns only. A word that does not explain itself gets a few words that say what it is, at its first use in a section.

## Releasing

Each version has a release on GitHub. Its tag is `v` plus the manifest's version, such as `v0.3.9`. Home Assistant shows that tag as the integration's version. For a repository with no release, Home Assistant shows a commit hash.

1. Set `version` in `custom_components/lite_resources/manifest.json` to the new version. Give `CHANGELOG.md` an entry for that version, and leave its section `Unreleased` empty. Add each new feature, and each correction to the original, to the README's section [What this fork changes](README.md#what-this-fork-changes).
2. Run `python scripts/validate.py`. When each check passes, commit, and push the commit to `main`.
3. Run `python scripts/release_notes.py` with the tag, such as `python scripts/release_notes.py v0.3.9`. It prints the notes of the release, or it says why the tag is wrong.
4. Make the tag on that commit, and push it:

```bash
git tag v0.3.9
git push origin v0.3.9
```

The workflow `Release` then runs `scripts/release_notes.py` on GitHub and makes the release, with the changelog entry of the version as its notes. A tag that the script refuses gets no release.

If a run fails for a cause in the workflow, correct the workflow on `main`. Then start the workflow `Release` by hand in the `Actions` tab, and give it the tag. For a cause in the tagged commit, make a new version. In your own fork of this repository, GitHub runs no workflow until you enable GitHub Actions in the `Actions` tab.

Never move a tag that has a release, because Home Assistant installs by the tag. For a correction, make a new version.
