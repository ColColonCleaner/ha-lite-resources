# Changelog

## Unreleased

- **The README names this fork where it compares the fork with the original.** `This integration` names `ha-lite-resources` in each of its versions, and the original and this fork are two versions of it.
- **The README's list of added features has one entry for the automatic selection of resources,** in the second place. It holds three cases that had an entry each. They are a card in a minified file, a card that only a template names, and the WebRTC resource for the Advanced Camera Card.

## 0.3.10 - 2026-11-25

This version changes the wording of the texts, and it gives new names to three keys of the preview action. The integration's behaviour does not change.

- **Three keys of `lite_resources.preview` have new names.** `states_not_narrowed` is now `states_not_filtered`, `resources_not_reduced` is now `resources_not_filtered`, and `open_pages_with_narrowed_states` is now `open_pages_with_filtered_states`. An automation or a script that reads one of these keys needs the new name.
- **Each text uses one word for one thing.** The README, this changelog, the forms, the log messages and the comments now say `device` for the hardware, and `page` for one browser tab or app window that shows Home Assistant. They say `state filtering` and `resource filtering` for the two kinds of filtering. The README's section `One word for one thing` lists the words.
- **The texts call the integration `ha-lite-resources`, or this integration.** Its display name in Home Assistant stays `Lite Resources`.
- **One option of a group has a new label.** `Include resources that can't be checked` is now `Include resources that the integration cannot read`. The option's description already said `read` for the same thing.
- **The descriptions of two options say more.** The description of `Include resources that the integration cannot read` now says what the off position does. The description of `Only send states their dashboards show` now names the entities under `Extra entities`.
- **Log messages have new wording.** A search or a filter on the log's text needs the new text, such as `State filtering is off for group`.
- **The README says near its top what this fork changes:** the added features first, and then the corrections to the original.
- **The README answers more of a new reader's questions:** what a strategy is, why to edit a dashboard as a normal user, which install keeps a 0.2.x configuration, and what to do when state filtering fails after a restart on a later Home Assistant version.
- **The README gives the path to the actions tool in Home Assistant 2026.11,** which is `Settings → Tools → Actions`.
- **New tests check the README.** They fail when the section on the fork moves from the top, or when a text holds a replaced word.

## 0.3.9 - 2026-11-24

A fourth independent review read the changes of 0.3.8 and the two commits with the static checks. It gave 22 findings: none critical, none high, 4 medium and 18 low. The entity scan reads a group's dashboards to find their entities, and the resource scan reads them to find their resources. Each fault in behaviour needs a YAML dashboard, or an entity scan or a resource scan that fails or hangs. The review found no fault for a page whose dashboards are stored in the UI, when its entity scan and its resource scan work. This version corrects each finding, and it states each limit that stays. It also adds a second type check, which reads the types of Home Assistant from the source of its core.

### Each validation runs before a commit

These changes came after the first commit of version 0.3.9. They add tooling and tests, and the integration's folder did not change.

- **hassfest, the tool with which the Home Assistant project validates an integration, now runs on this fork.** Before, hassfest was a job of the Validate workflow only, and that workflow never ran on GitHub. So no version up to 0.3.9 had that validation. Its first run on 0.3.9 found no error and no warning.
- **One script runs each validation: `python scripts/validate.py`.** It runs the unit tests, `ruff check`, the format check, both type checks and hassfest. It has no option that leaves a check out, and a check that cannot run is a failed check. A test compares the script's checks with the workflow's steps.
- **hassfest runs before a commit, in a container with no network and no volume.** hassfest has no release as a package. The script runs it in the container image of the hassfest action. The script names the image by its digest, the integration's files reach the container as a tar stream, and the container holds no capability. The container can run on a host that the script reaches with `ssh`.
- **A warning of hassfest fails the validation.** hassfest exits with 0 for a warning, such as a discovery step with no unique ID.
- **The hassfest run finds each of 17 planted faults.** A run for one integration loads 24 plugins, and each of the 24 ran. 11 of them read the files of a custom integration: `manifest`, `json`, `translations`, `services`, `config_flow`, `dependencies`, `requirements`, `config_schema`, `icons`, `triggers` and `conditions`. 17 copies of the integration with one fault each went through the same route, and hassfest named each fault. The other 13 plugins build index files of Home Assistant core, or check a core integration only.
- **A new test asks that each service has a name and a description.** hassfest asks this of a core integration only.
- **The script can refuse a working tree that holds more than the commit**, with the option `--tree-is-the-commit`, for use in a `pre-commit` hook. The checks read the working tree, so a file that the commit leaves out would make the result wrong.
- **The validation gives the same result inside a git hook.** In a hook, git names its repository in variables such as `GIT_DIR`. With them, a unit test that makes a scratch repository acts on the clone instead. So a check gets none of those variables, except the check of the working tree. The script's tests run with such variables set to a decoy repository.
- The HACS action reads the repository on GitHub, so it has no local run. Three unit tests cover its checks of files.
- **The full type check reads the core source at the tag `2026.11.3`.** The workflow, the README and `mypy-homeassistant.ini` named `2026.11.2`. The check passes against the new tag with no change to the code. A new test asks that the three places name one tag.

### Each version has a release on GitHub

These changes also came after the first commit of version 0.3.9, and the integration's folder did not change.

- **Home Assistant showed a commit hash as the version of this fork**, because the fork had no release. HACS takes the version from the tag of the latest release, and a tag with no release does not count.
- **The tag of a version is `v` plus the manifest's version**, such as `v0.3.9`.
- **A new script, `scripts/release_notes.py`, checks a tag and prints the notes of its release.** It refuses a tag that does not fit the manifest's version, a changelog with no entry for the version, and a changelog with text under `Unreleased`. The notes are the changelog entry of the version.
- **A new workflow, `Release`, runs the script for each pushed tag `v*` and makes the release.** With the option `--publish`, the script sends the request `Create a release` of the GitHub REST API. The request names no commit, so GitHub uses the tag that exists.
- **The workflow stops for a name with no tag.** For such a name, GitHub makes a new tag on the default branch. So the workflow checks the repository out at the tag ref, and it compares the checked out commit with the tag's commit, before the request.
- **Only the step that makes the release gets the token.** The token has write access to the contents and no other permission. The workflow names the checkout action by a commit, and the checkout keeps no token.
- **A manual run of the workflow takes a tag as its input.** It makes the release of a tag whose run failed.
- The workflow file has no local run. The unit tests cover the script, and they check the text of the workflow file. The first run on GitHub is the first proof of that file.
- The README's section `Releasing` gives the steps of a release.

### The retries after a failed entity scan

- **One group's failed entity scans no longer use up the retries of another group.** Each group now has its own count of failed entity scans. 0.3.8 held one count for all groups, and each page reload of each group lowered it while one group had a fault. Six page reloads of one group in 10 seconds used the retries of another group, which then got 1 retry and not 6. Now a group's count changes only when an entity scan of that group fails or works.
- **A fault that lasts in one group no longer stops the retries of another group.** The one count of 0.3.8 started again only when no group had a fault. So a dashboard that stayed wrong left the count at 0. An entity scan of another group that failed once then got no retry. That group's page kept all states, with no line in the log.
- **The retry count is the number of failed entity scans in a row.** Each entity scan of the group counts, including one that a new page or a change starts. A retry comes about 10 seconds after each failed entity scan, and an entity scan that works starts the count again.
- **The log says when the retries of a group end.** After 7 failed entity scans in a row, one warning names the group, and it says which events bring the next retry.

### An entity scan or a resource scan that passes its timeout

- **A change to a group takes effect immediately, even while an old entity scan hangs.** 0.3.8 kept the open entity scan by the group's ID only. After you removed a dashboard that hangs from a group, each page reload and each update of the group still waited 30 seconds for the old entity scan. Each of them then sent all states. The integration now keeps the group's options beside the open entity scan, and a group with other options starts its own entity scan.
- **The integration waits only once for an entity scan that hangs.** In 0.3.8 each retry waited up to 30 seconds for the entity scan that still ran, up to 6 times. Each retry held the lock for the changes of all groups in that time, so a page of another group that connected got no states for up to 30 seconds. Now a caller that finds such an entity scan does not wait, and it gets no result.
- **A new entity scan has its own full timeout.** In 0.3.8 the wait for the old entity scan and the new entity scan shared one timeout. A new entity scan that started late in that wait failed with the message `took longer than 30 seconds`, even when its load was normal.
- **When an entity scan ends after its timeout, the pages of its group get an update.** In 0.3.8 nothing used that end. When a share returned after the last retry, each page of the group that held all states kept them until another event.
- **An entity scan that hangs no longer holds up the start or the stop of Home Assistant.** The entity scan is now a background task. 0.3.8 started it as a task that Home Assistant waits for at the end of its start and at its stop. A load that hangs then held both. Home Assistant does not wait for a background task, and it cancels each one at its stop.
- **The resource scan has the same timeout of 30 seconds.** A request for `lovelace/resources` had no timeout. A load that hangs left the page with no answer, and such a page loads no card. Now the page gets the full resource list after 30 seconds.

### YAML dashboards

- **An open page keeps its entities while Home Assistant cannot load a dashboard.** 0.3.8 moved each open page of the group to all states at the next update. So one typing error in one YAML file sent every state to each open page of the group. An entity scan that failed in another way kept the entities, so the two faults had opposite results. Now both keep the entities. A page that connects during the fault still gets all states.
- **A corrected YAML file reaches the open pages, even when it returns to its old text.** 0.3.8 compared a dashboard's configuration with the last one that loaded successfully. A file that failed and then came back as before counted as no change, when the first load after it was the preview action or a resource request. A page that got all states during the fault then kept them. The integration now records a failed load, and the next good load of that dashboard counts as a change.
- **A change to a YAML file reaches the open pages even when two loads run together.** A page reload sends two requests at the same time, and each loads the dashboard. When the load that did not find the changed file returned first, 0.3.8 stored the new configuration. The load that found the change then saw no difference, and the change reached no other open page. Now each load compares its result with the last one, and the first load that sees a new configuration starts the update.
- **A dashboard save still starts only one entity scan for each group.** The update event of a save comes from another task, and it starts an update. The entity scans of that update load the dashboard's new configuration, which is no second change. So the integration records each such event, and the first load after it starts no second update.
- **A YAML file with the value `.nan` no longer starts updates with no end.** The YAML value `.nan` is not equal to itself. With that value in a file that fires its event at each load, 0.3.8 saw a change at each load, and the updates had no end. The comparison now uses the dashboard's configuration as text, and two loads of one file give the same text.
- **A YAML dashboard with a missing file no longer breaks the entity scan and the resource scan.** Home Assistant raises an `OSError` for such a file after its first load. Before, that error ended the entity scan and the resource scan, with a traceback at each page reload. Now such a dashboard counts as a dashboard that Home Assistant cannot load.

### Other paths

- **A page that asks for its resources during a reload of the integration gets the filtered resource list.** 0.3.8 answered such a request with the full resource list. Now the request goes to the handler that is registered at that time, as a state subscription does. After a reload of the integration, that is the new setup's handler.
- **A registry change starts no entity scan for a group whose state filtering is off by design.** State filtering is off for a group with a strategy, a card that finds its own entities, or a dashboard with no stored configuration, and no registry change alters that. 0.3.8 ran an entity scan of the group again at each burst of registry events, which come each 10 seconds while Home Assistant starts. The integration now remembers such a group until a dashboard or a group changes.
- **One update runs one entity scan for a group.** Before, a group with a filtered page and a page on all states got two entity scans in one update.
- **An update for one group leaves the other groups alone.** Before, the search for pages with all states ran an entity scan for each group.
- **A word that only ends in `type`, such as `prototype`, no longer names a card type.** 0.3.8 read `prototype: custom:x` and `subtype=custom:x` in a text as a card type. The pattern now asks for a boundary before `type`.
- **A card type with a dot inside a longer string is no longer cut at the dot.** Before, `custom:my.dotted-card` in a template gave the type `my`.
- **The log gets a warning each time a reason changes, even back to an earlier reason.** In 0.3.8 each reason had a key of its own, and only a good entity scan or a good resource scan cleared the keys. An error in line 5, then in line 9, then in line 5 again gave two warnings and not three. Now a warning belongs to one subject, and the log gets a warning when the value for that subject changes. The warnings for a card type with no resource were never cleared before, and they now follow the same rule.
- **After a reload of the integration, the log gets each warning of the entity scan and of the resource scan again.** Before, `Dashboard X not found` came once for each run of Home Assistant.

### Tests

- **The tests leave no state behind.** One test passed only at its first run in a process, because a warning record stayed from an earlier test. Each test class now clears the records and the change listeners that the entity scan and the resource scan share, at its start. The suite passes two times in one process, in reverse order and in two shuffled orders.
- **The stand-in for a YAML dashboard has the cache rules of Home Assistant.** It keeps its cache when a load fails, and it fires its event when a cache existed before the read. The stand-in of 0.3.8 fired no event after a corrected error, so no test saw a file that returns to its old text.
- **The test for the end of the retries asks for the exact count.** In 0.3.8 it asked for an upper limit only, so it passed even when no retry ran.
- **New tests cover the paths that the review named.**
  - The retries: two groups, a group that changes during the entity scan of its old dashboards, and a late entity scan that ends in an error.
  - A YAML dashboard: a file that returns to its old text, two loads at the same time, and a file with `.nan`.
  - An entity scan of two YAML dashboards of which one changed.
  - Each case of a YAML dashboard again for the default dashboard.
  - A stored dashboard: a save, a delete, and a page that connects after a save. Each test counts the entity scans.
  - A page that goes to another integration's handler at the unload.
  - A resource request at a reload of the integration, and a resource scan over the timeout.
  - A registry change for a group with a strategy, and a reason that comes back.
- A check on a scratch copy made six changes to the code, one at a time. Each change breaks the subject of one new test. That test failed with its change, and it passes with the code as it is.
- The suite has 260 tests. 0.3.8 had 229.

### Type checks and the workflow

- **`mypy` gives the same result on each machine.** With the settings of 0.3.8, mypy read the real types on a machine that holds Home Assistant. A `type: ignore` in the config flow was then unused, which the strict mode reports. `mypy.ini` now skips each import from Home Assistant, and it names Python 3.14, on which Home Assistant 2026.11 runs.
- **A second type check reads the types of Home Assistant.** With no such types, mypy checks no call of a function under `@callback`, and it knows the type of 77.54% of the expressions. `mypy-homeassistant.ini` runs the full strict mode, and mypy reads the types from a clone of the core source that `MYPYPATH` names. Nothing of that source runs. mypy then knows the type of 89.57% of the expressions. The Validate workflow runs both checks, and the README gives both commands.
- **The first run of the full check gave 3 findings, and none was a fault at run time.** The YAML resource collection of Home Assistant has no load function. The call was never reached for it, and the code now asks for the function by name. The `type: ignore` in the config flow was unused, and it is gone. The list in the preview action's answer had a type that did not fit the answer type of an action.
- **Both jobs install the same voluptuous version.** The job `tests` installed the newest version, and the job `lint` installed 0.16.0.
- The import in `tests/support.py` that keeps a ruff finding on purpose now has its reason on the line before it, as `ruff.toml` asks.

### Texts

- **The entry for 0.3.8 said four things that did not hold, and it is corrected.** The retries were not always 6. One thread for an entity scan or a resource scan that hangs held only for the entity scan of one group. A warning did not come again when another reason came in between. The format run changed the text of one comment: a comment in `resolver.py` that moved to its own line got a capital letter and a full stop.
- The README said `Two changes do not reach an open panel by themselves` and then named three. It now names three.
- The README names two cases: Home Assistant cannot load a dashboard, or an entity scan passes 30 seconds. It says what a new page and an open page get in each case.
- The comments and the log messages that the review named are written anew with the code that they describe. The function that asks whether the integration started a load now only answers. In 0.3.8 it also wrote a mark, which its name did not say.

### Limits that stay

- A load that never ends keeps its group's new pages on all states. That lasts until the load ends, the group changes, or Home Assistant restarts. Each open page keeps its entities in that time.
- Each request for `lovelace/resources` and each call of the preview action starts a load of its own. While a load hangs, each of them holds one thread of the executor until the load ends.
- One lock serves the changes of all groups. So a slow entity scan of one group delays the first states of a new page of another group, for up to 30 seconds.
- When the filtered state subscription fails after Home Assistant's handler sent its result, the page gets a second result for the same message.
- A text in a dashboard that holds `type: custom:name`, or a quoted `'custom:name'`, names a card even when the text is a sentence for a person. The integration then sends one resource more, and never one less.
- A card type with a capital letter inside a longer string is not read. The browser accepts no capital letter in such a name, so no card type holds one.
- The portable check `mypy` reads no type of Home Assistant. The full check needs a clone of the core source, and a library that the clone imports and that the environment lacks keeps the type `Any`.

## 0.3.8 - 2026-11-24

A third independent review read the changes of 0.3.6 and 0.3.7, and it gave 20 findings. None is critical. This version corrects each finding that holds. One finding did not hold, and the end of this entry names it. The review confirmed that 0.3.7 changed words only.

### A YAML dashboard whose file changes

- **A changed YAML file now reaches each open page, even when this integration finds the change first.** The entity scan loads a group's dashboards to find their entities, and the resource scan loads them to find their resources. Home Assistant fires the update event of a YAML dashboard inside the load that finds the changed file. 0.3.6 dropped each such event that came while an entity scan or a resource scan loaded the dashboard. That load could be for one new page, for a resource list or for the preview action. The other open pages then kept the old entities. Now each such load compares the dashboard's configuration with the last one that the integration saw. When the two differ, each open page of each group with that dashboard gets an update.
- **A change that a browser finds while an entity scan or a resource scan runs is no longer lost.** 0.3.6 dropped each update event that came during an entity scan or a resource scan, even when a browser's load fired it. The integration now drops only an event from a load that it started, and it knows that load by its task.
- **A YAML file that fires an update event at each load starts no chain of updates.** Such a file gives the same configuration at each load, so the comparison stops the chain. The rule of 0.3.6 was for this fault.
- **The timeout no longer cancels the load of a dashboard.** The timeout of 0.3.6 cancelled the entity scan inside the load. Home Assistant then kept the new configuration and never fired the update event, for this integration and for each browser. Now the timeout only ends the wait, and the entity scan runs to its end.

### Pages that kept all states

- **A dashboard that Home Assistant cannot load turns state filtering off, and the log gives the real reason.** 0.3.6 left such a dashboard out of the entity scan, so the pages of the group stayed filtered, without that dashboard's entities. When the file was correct again, no event came, and a page that opened the dashboard had no state on it. Now the pages of the group get all states, the log gives the error of the load, and the integration retries the entity scan. The resource list still leaves such a dashboard out.
- **The integration retries a failed entity scan.** A page that got all states after an error of the entity scan, a timeout or a load error kept them until another event. Now the integration retries the entity scan, at most 6 times, with 10 seconds between the retries. One count served all groups, so a group could get fewer retries, which 0.3.9 corrects. When a retry works, the integration filters the state subscription of each open page of the group. When the entity scan for a new page works after such a fault, the integration filters the other pages of its group also.
- **A registry change turns state filtering on for a page that holds all states.** Before, a registry change started no update while no filtered page was open.
- **State filtering holds for a page that connects during a reload of the integration.** 0.3.6 passed a page whose entity scan was open at the reload to the handler that the old setup held. The page got all states, and the new setup did not know it. Now the page goes to the handler that is registered at that time.
- **A hanging entity scan of one group holds only one thread.** While the entity scan of a group still runs after its timeout, the next entity scan of that group waits for its end. It starts no second load. A resource request and the preview action each start a load of their own.
- **The integration runs no entity scan for a page that already left.** The task read the page's state only after its entity scan. A task that got its turn after an unload also ran a full entity scan and then dropped the result. Both checks now come before the entity scan.
- **A page that asks for its resources during an unload of the integration gets the full resource list.** The handler read the unload flag only before its resource scan.

### The entity scan and the resource scan

- **A strategy section in a sidebar, or inside another section, turns state filtering off.** The frontend makes a section for each item in `sidebar.sections` of a view, and for each item in `sections` of a section. 0.3.6 read the key `strategy` only in the sections of a view.
- **A custom card that a template names by a quoted `custom:` type loads again.** 0.3.6 took such a type inside a longer string only after the word `type`. A template that returns `'custom:name'` by itself named no card, and neither did YAML text with no quotes. The integration did not send the resource of such a card.
- **A name of three joined pieces in a resource file no longer gives a wrong card type.** The text `"my-" + "fancy-" + "thing"` gave the guess the name `fancy-thing`, which the file does not hold.
- **A warning comes again when its cause comes back after a good load.** The warning for a dashboard that cannot be loaded had a key with the dashboard's name only. So a later error of the same dashboard gave no warning. The key now holds the error text, and a good load clears it. The integration clears the reasons why state filtering or resource filtering is off for a group in the same way.

### Tests and static checks

- **New tests run the real entity scan and the real resource scan against a YAML dashboard that fires its event as Home Assistant does.** The test of 0.3.6 counted entity scans only, and its stand-in wrote the marker in place of the entity scan. The new tests ask that each open page gets the new entities for each first loader: a new page, the preview action, a resource request and a browser.
- New tests cover the timeout for a new page and for an open page, and the retries with their limit. They also cover a page whose entity scan is open at a reload of the integration, and a resource request at an unload.
- **Three stand-ins now behave as Home Assistant does.** The select selector refuses a value that is no list. The administrator check raises `UnknownUser` for a user that does not exist, which is an `Unauthorized` error in Home Assistant. A closed connection records each send apart, because Home Assistant drops such a send.
- `tests/test_resolver.py` failed when it ran by itself, because its own stand-ins lacked one name. It now uses the shared stand-ins.
- **The repository has static checks.** `ruff.toml` sets up ruff with its default rule set, and the Validate workflow has a new job `lint` that runs `ruff check .` with ruff 0.17.5. The first run found no fault in behaviour. It found import blocks out of order, five broad `except` lines that are there on purpose and now say so, and some small points of style. All are corrected, and the import order of the tests now equals that of the integration.
- **The code has the format of `ruff format`**, which the development checklist of Home Assistant asks for. The run changed line breaks in 16 of the 18 Python files. The syntax tree of each file is the same before and after it. So is each comment, with one exception: a comment in `resolver.py` that moved to its own line got a capital letter and a full stop. The job `lint` checks the format also.
- **The integration has type checks.** `mypy.ini` sets up mypy 2.4.1 in its strict mode for the integration, and the job `lint` runs it. The checks run with no Home Assistant installation, so each name from Home Assistant has the type `Any`, and three strict checks that cannot pass with such names are off. The first run gave 18 findings. 15 came from those names. In two places, mypy held the unload flag for False after the first test, and so took the second test, which comes after a wait, for dead code. The code now reads the flag through a function. One was a variable with a type that was too wide in the resource scan. No finding was a fault in behaviour.

### Texts

- **A second wording pass.** 0.3.7 made sentences such as `Return each domain whose every entity one of the dashboard's cards shows`. A sentence must read well first. So a possessive now stays only for a short owner of a plain thing, such as `the group's dashboards`. Each other sentence of that kind is written anew, and some are longer. No possessive stands on a version or on a commit.
- The README says what a page gets when Home Assistant cannot load a dashboard, and when an entity scan passes 30 seconds. It says how a change to a YAML file reaches the open pages, and when the integration sends a resource file for a guessed type. The warning for a guessed type says the same.
- The README gives the commands for the tests and for the static checks.

### Limits that stay

- The retries stop after 6. A YAML dashboard that stays wrong keeps the pages of its group on all states until the next change or the next connection.
- The guess for a type with no provider reads only a file that holds `customElements.define(` before a name with no quotes. A resource file that registers its card type in another way needs **Always include**. The review built such files for its test, and it found no real card of that kind.
- Each new page runs its own entity scan, and the entity scans run one after the other. Two pages of one group that connect together do not share a result.

### A finding that did not hold

- The review asked what a send on a closed connection does, because a page can close during its entity scan. In Home Assistant 2026.11.2, such a send writes one debug line and raises nothing.

## 0.3.7 - 2026-11-24

- **The fork's texts use the possessive form.** The README, this changelog from 0.3.0 on, the form texts, the log messages and the code comments now say `a group's dashboards` and not `the dashboards of a group`. The word `of` stays for a part, an amount, the contents, an action before its object, and an owner with a clause after it.
- No behaviour changed. Some log messages have new words, and two of them are now two sentences with no semicolon.
- The paragraphs of the original's author in the README, and the entries up to 0.2.1, keep their wording.

## 0.3.6 - 2026-11-23

A second independent review covered the whole code at 0.3.5. It gave 35 findings: none critical, 1 high, 6 medium and 28 low. 24 of them are in code that 0.3.5 added. This version corrects each fault that the review confirmed, and it states each limit that stays. Three findings did not hold against the source of Home Assistant 2026.11.2, and the end of this entry names them.

### Rules of 0.3.5 that turned state filtering off too often

- **A card feature with a name like an energy card's no longer turns state filtering off. (high)** 0.3.5 took each `type` that starts with `energy-`, `water-`, `power-` or `gas-` as an energy settings card, in each mapping of a dashboard. A tile card's feature `water-heater-operation-modes` is none of these, and one such feature sent all states to each page in the group. The rule now holds the frontend's exact card and badge types, and it reads no type inside a card's features.
- **A key `strategy` in a card's options no longer turns state filtering off.** 0.3.5 took that key in each mapping as a strategy, even as a custom card's option or in an action's data. The key now counts only where the frontend reads it: at the dashboard, at a view and at a section.
- **One dashboard that Home Assistant cannot load no longer turns state filtering off.** 0.3.5 took each load error as a dashboard with no stored configuration, so one YAML dashboard with a syntax error turned state filtering off for its group. Only a dashboard with no stored configuration does that now. Another load error leaves the dashboard out, with one warning that gives the error.

### An open page's state subscription

- **An unload of the integration returns each page to all states, including a page whose entity scan still runs.** A task can wait on the entity scan, which reads a group's dashboards to find their entities. The unload returned each page to all states. The old setup's task that waited on an entity scan then filtered the page again, into a table that nothing updated. After a removal the page stayed filtered. After a reload of the integration the new setup did not find it. The unload now sets a flag, and that setup's tasks and handlers read it after each wait.
- **After its unload, the integration filters nothing, even when another integration still calls its handler.** When another integration keeps this integration's handler and calls it after the unload, the handler now passes the message to Home Assistant's handler.
- **A YAML dashboard that Home Assistant does not cache no longer starts entity scans with no end.** A YAML dashboard's load can fire that dashboard's update event. For a file that Home Assistant does not cache, such as an empty file or a file with a time in the future, each entity scan fired an event and each event started an entity scan, with no end. The integration now leaves out an event that comes while its entity scan or its resource scan loads that dashboard.
- **Many dashboard saves close together no longer start one entity scan each.** Each dashboard save started its own update, and 20 saves started 20 entity scans. An update that runs now takes each later request with it.
- **A page that connects during a dashboard save gets the new entities.** A page's first state subscription ran apart from the updates of the open pages, so a page that started during a save could keep the older entity set. A new page now waits for an update that runs.
- **An entity scan has a timeout of 30 seconds.** The changes to the open pages run one after the other. A dashboard load with no end, such as a YAML file on a dead share, held each later change.
- **A page that ends its state subscription during the entity scan gets its command's result.** Before, that command got no answer.
- **A lite user no longer learns the entity IDs that its permissions hide.** An adoption filters a page's open subscription to all states in place, and it sends the page one message that removes the other entities. That message held each entity in Home Assistant, so a user with a restricted policy learned the entity IDs that the policy hides. The message now holds only entities that the user can read.
- **A failed adoption no longer leaves a filtered state listener that the integration does not know.** A page is now in the open pages table before its removal message goes out. If that message failed, it could leave a filtered listener that the table did not know.
- **The log says how many state listeners the adoption cannot read.** The check in 0.3.5 saw two layout changes only. The search now accepts only the exact five arguments that it knows, and it counts each listener that holds Home Assistant's function with another layout. The log holds one warning with that count.
- **The log names a page that stays filtered at the unload**, when the return to all states fails for it.

### The entities and the resources

- **A tile card for a device tracker gets each zone**, as a tile card for a person does.
- **The text `custom:` in a markdown card no longer counts as a card.** 0.3.5 took each `custom:name` inside a longer string as a card on the dashboard, even in the text of a markdown card. It now needs the key `type` before it, as in a template that returns a card.
- **A key such as `layout_type` in a resource file no longer hides a card's real file.** The resource scan reads each resource file to find the card types that the file registers. It took `layout_type:"grid-layout"` as a registration of `grid-layout`. The integration sent that false provider, and the provider stopped the search for the type's real file.
- **The integration sends fewer files for a card type whose registration it cannot find.** The guess for such a type took each file that names the type in quotes. It now takes only a file with a registration that the resource scan cannot read, such as the call inside a minified decorator. A file whose registrations all have a quoted name registers no other card type.
- **A card whose resource file joins its name from two pieces in a helper call loads again.** 0.3.5 dropped such a pair outside a registration and an assignment, so a resource file that registers `"my"+"-card"` through a helper lost its card. The guess now finds that name.
- **A name of three quoted pieces gives no wrong name.** The resource scan joined the first two pieces.
- **The preview lists each file with no card type, whatever its name is.** 0.3.5 left out each file with a hyphen or with six or more characters in its name, so an icon set such as `custom-brand-icons.js` did not show. The list now also holds a card that the dashboards do not use and whose registration the resource scan cannot see.
- **The preview lists the entity IDs with no state.** A state subscription holds each entity ID in the dashboards, including one with no state now. The preview showed only the entities with a state. The new key `state_entities_without_state` holds the rest.

### The form and the tests

- A stored user that is not active shows its name with `(not active)` in a group's form. 0.3.5 showed its ID with `(user not found)`.
- **The stand-ins in the tests take Home Assistant's order and defaults.** The unload callbacks run from the last one to the first, a task starts eagerly by default, and the stand-in for the administrator check refuses a user that is no administrator and passes the answer on. The stand-in for a select selector refuses a value outside its choices.
- New tests cover the group form's two steps. They cover the resource handler's three paths that send the full resource list or write a warning to the log. They cover a filtered call that fails while the call for all states works, and a state subscription with a filter. They also cover each correction in this version. The tests grow from 180 to 207.

### Findings that did not hold

- The preview action returns its answer through Home Assistant's administrator wrapper: `_async_admin_handler` returns the function's answer.
- A new group and a deleted group call the entry's update listener: `async_add_subentry` and `async_remove_subentry` both end in `_async_save_and_notify`.
- Home Assistant refuses an entry with a higher version than the flow knows before it calls the migration.

### Limits that stay

- **When a dashboard save turns state filtering off for a group, each open page of the group gets all states.** A dashboard save can add a strategy, a home-summary card or an energy card. Each open page in the group then gets all states in one message, about 1.4 MB for 5,573 entities. Each page also gets each state change after that. The log holds one warning with the reason. An unload and a reload of the integration send the same message once.
- **A custom strategy that makes custom cards** names no card in the stored dashboard. Add each such card's resource under **Always include**.
- **When a file gives one short name more than one value, each value joins each template that uses that name.** A minified resource file can then seem to provide a card that it does not hold, and a page loads it for nothing. No real resource file showed this.
- **Each state subscription runs an entity scan of about 20 ms to 40 ms for 5,573 entities.** Pages that connect together share no result. A change to one entity sends its whole set again to each open page in the group.
- The three checks against the real package do not cover the handler for `subscribe_entities` as a whole. They also do not cover a user that is no administrator, a state change through a new listener, or an entry's setup. The test on a running Home Assistant covers those.

## 0.3.5 - 2026-11-23

An independent review of the whole code gave 51 findings: 1 critical, 1 high, 5 medium and 44 low. This version corrects each fault that it confirmed, and it states each limit that stays. Each point is in the list below.

A second review found faults in this version, and 0.3.6 corrects them. The largest one: three new rules turned state filtering off too often, so install 0.3.6 and not this version.

### An open page's state subscription

- **A restart of Home Assistant no longer leaves a page with no states.** The adoption of 0.3.4 filters in place a subscription to all states that a page started before the integration's setup. The adoption made its own message for Home Assistant's handler, and that message did not pass the command's schema. The handler reads the keys `include` and `exclude`, which only the schema adds, so it failed with `KeyError`. The adoption ended the page's state listener before that call. The first 0.3.4 code then left the page with no listener, and its later correction sent the same message again and failed again. Each message that the integration makes now passes the schema first. The review found the fault before the first known install of 0.3.4.
- **A page keeps its states when a change to its state subscription fails.** A change to an open state subscription now starts the new listener before it ends the old one. If the handler fails, the old listener goes back into its place, and the page keeps the entities that it had. Versions 0.3.0 to 0.3.4 ended the old listener first. This holds for a new entity set, for an adoption, and for the return to all states, which had no guard at all.
- **An unload or a removal of the integration sends each open page all states again.** Before, such a page stayed filtered until it reconnected, although the README said that all is as before after a removal.
- **A reload of the integration no longer loses the open pages.** Before, the new setup did not know the pages that the old setup filtered. A saved dashboard, a changed group and a deleted group then changed nothing for them. The unload now returns each page to all states, and the new setup filters it again.
- **A page that closes during the entity scan no longer leaves a state listener behind.** The entity scan reads a group's dashboards to find their entities. It can wait, such as at a dashboard's first load or for a YAML dashboard. A page that left in that time got a state listener and a place in the open pages table, and nothing ended them. The handler now puts a stand-in into the page's subscriptions, which Home Assistant removes when the page closes.
- **Two dashboard saves close together leave each page with the newer entities.** Two such saves could leave a page with the older entity set. The changes to the open pages now run one after the other.
- **A new page no longer waits with no end when state filtering fails.** Before, a failure inside the task of a filtered state subscription sent the page no result and no error, and the page waited with no end. The page now gets the subscription to all states. If that fails too, the page gets the error message that Home Assistant sends for a failed handler.
- **A failure for one page no longer stops the update of the other pages.** A failed entity scan now leaves each open page as it is. Before, an error for one page ended the update for each later page, and the adoption after a group change did not run.
- **The log says when this Home Assistant version has internals that the adoption cannot read.** The search for early state subscriptions reads the listener table of the event bus and the function `_forward_entity_changes`. On a version without them the search found nothing and the log held nothing. The setup now writes one warning to the log. The search also catches each kind of error at the read, and it takes that function only from the Home Assistant module that defines it.
- **A setup of the integration during Home Assistant's start still updates the pages at the end of the start.** The update at the end of the start depended on `hass.is_running`. That property is also true while Home Assistant starts, so a setup in that time added no listener. The setup now uses `async_at_started`.
- **An unload keeps a handler that another integration registered after this one.** Before, the unload wrote Home Assistant's two handlers back, whatever the table held.
- **A change to the entity registry, the device registry or the area registry updates the open pages.** A new schedule, an entity that moves into an area card's area, and an entity that is no longer hidden now reach an open page. The registries change in bursts, so one update follows 10 seconds after the first change.

### A group's entities

- **A dashboard with no stored configuration no longer leaves a page with only two entities. (high)** Home Assistant generates such a dashboard in the browser, such as the default dashboard before its first edit. The entity scan read it as an empty dashboard, so a page got only `sun.sun` and `zone.home`, with no line in the log. State filtering is now off for such a group, and the log says why once. The same holds when no dashboard in the group exists. A deleted dashboard beside a stored one is left out, with one warning.
- **A strategy turns state filtering off for its group.** A dashboard, a view or a section with a strategy holds no card: the browser makes them. A page that showed such a dashboard got no entity for those cards. The entity scan also read the area view strategy as an area card.
- **Core cards that find their entities by themselves now show them.** The `home-summary` card and the energy, water, power and gas cards and badges take their entities from all states or from the energy settings, so state filtering is off for a group with one of them. A `map` card with `show_all` gets each person, device tracker and zone, and with `geo_location_sources` each geo location entity. The `updates` card gets each update entity. A tile card for a person, and a visibility condition on the user's location, get each zone.
- **The integration sends the person entity of each user in a group.** The frontend finds the logged-in user's person by a search of all states, for a location condition and for the user's picture.
- **The entity scan finds an entity ID directly after a line break or a tab.** The entity scan now reads a dashboard's values, and not its JSON text. In JSON text, a line break or a tab inside a string is a backslash and a letter, which hid the entity ID after it. A value that JSON does not know, such as a date with no quotes in a YAML dashboard, made the entity scan fail. That failure turned state filtering off for the group, with an error at each page reload.
- **An action's name, such as `light.turn_on`, no longer counts as an entity.** Such a name with no state went into a state subscription's list. Each other entity ID with no state stays, because its first state can come later.
- **The default dashboard is the dashboard `lovelace` when it exists.** Home Assistant 2026.11 takes that dashboard for a request with no URL path, before the dashboard with the key `None`. The entity scan, the resource scan and the update after a save now do the same.

### A group's resources

- **A card that a minified file registers through a decorator still loads.** The resource scan reads each resource file. It sees a card type in `customElements.define` with a quoted name, in a `type:` entry, and through the file name. A resource file that registers a second card type only through Lit's decorator, such as a layout in `layout-card.js`, lost that card type, and its card showed `Custom element doesn't exist`. For a needed type that no file provides, the integration now sends each file that names the type in quotes, and the log names the type once. A type with a provider never takes this route, so a file that only mentions another file's card stays out. A type that a resource under **Always exclude** provides takes no such file.
- **The resource scan sees a card type inside a template.** A template that returns `{type: 'custom:...'}` holds the type inside a longer string, and the resource scan read only a string that is the type as a whole.
- **A camera with the key `webrtc_card` keeps the WebRTC Camera integration's resource.** The Advanced Camera Card takes the live provider `webrtc-card` by itself for such a camera, and 0.3.0 kept that resource only for the written value `webrtc-card`.
- **The log names a card type whose resource the integration cannot verify.** When one sent resource cannot be read, a type with no provider counts as not verified, and the log held nothing for it. The log now holds one warning for it.
- **Each warning is in the log once.** `Dashboard ... not found` and `No local resource provides ...` came at each request from each page.
- **One unreadable resource file no longer turns resource filtering off.** A cut or corrupt `.gz` copy, and a path with a null character, raised an error that failed the whole group's request. The integration then sent the full resource list at each page reload, and it wrote a traceback to the log. Such a file now counts as not readable.
- **A resource on another server no longer counts as a local file.** The resource scan read another server's URL with a path that starts with `/local/` or `/hacsfiles/` as this server's file.
- **Always include and Always exclude compare the host and the path.** Before, an entry for one host's resource also took a resource with the same path on another host. The version in the query still does not count.
- **A short name with more than one value in a minified file no longer gives a wrong card type.** A minified file gives one short name more than one value, and the resource scan kept only the last one, so a template such as `${p}-light-card` gave a wrong name. Each value now counts.
- **Two joined pieces of text in a resource file no longer count as a card by themselves.** Two quoted pieces with a plus now count only in a registration or in an assignment to a variable. Before, each such pair in a file counted as a card type that the file registers, such as a CSS class name.
- **A config folder path in an unusual form no longer refuses each local file.** The test that keeps a resource path inside the `www` folder compared a normal path with one that was not. Both now have the normal form.
- **The preview lists the files with no card type.** A resource that works by a side effect, such as an icon set, provides no card type, so it is not sent. `lite_resources.preview` now lists each readable file with no card type and no card's file name under `excluded_without_element`. When a page needs such a file, add it under **Always include**.

### The form, the action and the checks

- **Only administrators can call `lite_resources.preview`.** Before, each logged-in user could call it, and it names each group, each user, each dashboard and each entity in the dashboards. The preview now also says why state filtering or resource filtering is off for a group.
- **You can save a group's form after you delete one of its users or dashboards.** Home Assistant refuses a form value that is not among an option's choices. A group with a deleted user, a deleted dashboard or an older version's resource URL could not be saved until that value was removed, and the error did not name it. The form now keeps such a stored value.
- **The form shows a stored group's state filtering as it is.** For a group with no stored value the form showed state filtering as on, but it is off for such a group. A plain submit then turned it on. The update from a single-group version now also writes state filtering as off when that version did not hold the option.
- **The log names a user that is in two groups.** Two forms that are open at the same time can each add the same user. The first group in the list counts, and the log now says so.
- A group has a hash. Before, `hash(Group)` raised an error, because the options are a dict.
- A group's text `reconfigure_successful` is gone. Home Assistant shows its own text after a change to a group.
- **The stand-ins in the tests fail as Home Assistant does.** The stand-in for Home Assistant's handler accepted each message, so 18 adoption tests passed with the fault of 0.3.4. It now reads `include` and `exclude` with no default, and the stand-in for the filter does the same. The harness runs an eager task as Home Assistant does, and it can make the entity scan wait and close a connection. New tests cover the group form, the paths that send a page the full resource list or all states, a resource URL's path test, a `.gz` copy and the file cache. The tests grow from 105 to 180.
- The check against the real package of Home Assistant 2026.11.2 now calls the handler exactly as the integration does. The earlier check passed each message through the schema itself, so it did not show the fault.
- The Validate workflow runs the unit tests.

### Limits that stay

- **A new member of a light group or of a schedule reaches an open page only later.** A light group's new member, and a new entity that a schedule controls, reach an open page at its next page reload, at its dashboard's next save, or at a registry's next change.
- **State filtering holds for each program that logs in as a lite user.** The integration knows a connection's user and not its program. A companion app or a script that logs in as a lite user and asks for all states gets only the entities on the dashboards.
- **The integration cannot find the entities of a custom card that selects them in the browser.** `auto-entities` with a domain filter, the entity list in the scheduler card's editor, and a template that builds an entity ID from a variable name no entity in the dashboard. Add those entities under **Extra entities**.
- **An administrator who is a lite user** also sees the filtered resource list under **Settings**, **Dashboards**, **Resources**.
- **A YAML dashboard** fires no event when its file changes. Its open pages get the new entities when a page loads the dashboard again.
- **The entity scan of a group runs again for each state subscription and each update.** One entity scan took 29 ms to 39 ms for 5,573 entities on a workstation. An adoption sends one removal message with each other entity, about 200 KB for that home.
- The Validate workflow's hassfest action and HACS action stay on a moving branch, `hassfest@master` and `hacs/action@main`, as the original set them. Home Assistant's developer blog gives `hassfest@master`.
- The text `single_instance_allowed` stays. The review did not verify that Home Assistant never shows it.
- This fork's link to the issue tracker, its release badge and its Validate badge need issues, a release and workflow runs on GitHub. The README's section **Releasing** still describes the original's releases.

## 0.3.4 - 2026-11-23

- **State filtering survives a Home Assistant restart.** After a restart, a page reconnects within seconds, before Home Assistant sets a custom integration up. Home Assistant's handler then answered the page's state subscription, with every entity. On one device the page went from 95 entities to 5,573, and it fell more than 200 seconds behind for 10 minutes, until its connection broke. The integration now finds such a state subscription when its setup runs, and it filters the subscription in place. The page drops the entities that its dashboards do not show, and it keeps its connection.
- Each open page of a user that joins a group becomes a filtered page immediately, in the same way.
- The search for those state subscriptions reads internals of Home Assistant 2026.11: the listener list of the event bus. On a version with another layout it finds nothing, and a page then gets its filtered state subscription at its next connection, as before. The search takes the listener function only from the Home Assistant module that defines it.
- A second commit of this version, `57bf290`, tried to return a page to all states when its filtered state subscription failed.
- **This version has a critical fault, and 0.3.5 replaces it. Do not install 0.3.4.** The filtering in place has the name adoption. The adoption sent Home Assistant's handler a message that did not pass the command's schema, so the handler failed after the adoption ended the page's listener. Each adopted page then had no state subscription until it reconnected. The return to all states in `57bf290` sent the same message, so it failed in the same way. Two commits carry this version number: `ce1fba9` and `57bf290`.

## 0.3.3 - 2026-11-23

- **The instructions say where each action is.** The README gives each step of the install and of the configuration. **Add group** is the button in the upper-right corner under **Settings → Devices & services → Lite Resources**, and an item in the entry's three-dot menu. A group's cog icon changes it, and a group's three-dot menu renames or deletes it. A picture shows that place.
- The dialog that adds the integration and a group's dialog name the same places.
- The README no longer gives a button as a replacement for a list of steps. The button for the dialog that adds the integration is a second way to do the first step only. The install section gives its steps with no button, because nobody checked that the button opens a repository that the catalog does not list.

## 0.3.2 - 2026-11-23

- **A page that connects while Home Assistant starts gets each of its entities.** Many entities get their first state some seconds after the start. A page that connected before that time never got them, and its cards showed no camera or no value until the page reconnected. A lite user's state subscription now also holds each entity ID with no state yet, so each one arrives with its first state. The registry gives such an entity's domain and device class.
- When Home Assistant's start is complete, each open page that belongs to a lite user gets its entity set again. A group entity names its members only after the setup of its integration.
- **The texts say lite users.** The word `light` now names only a lamp. The group that the update makes from a single-group configuration has the name **Lite users**.

## 0.3.1 - 2026-11-23

- **The area card gets its area's entities.** An area card names an area and no entity. It finds its camera, its sensors, its alerts and its controls in the registries. The page of a lite user now gets those entities, by the card's rules: the entity is in the area, it is not hidden, and it has no entity category. Before this version, such a card showed no light button, no temperature and no motion alert for a lite user.
- **The scheduler card gets its schedules.** Each schedule is a switch that the scheduler integration provides, and the card shows an empty row for a schedule with no state. The page of a lite user now gets those switches, and the entities that each schedule controls.
- An entity with no area of its own has the area of its device in the device registry. A child device in that registry with no area has the area of its parent device. The area card follows that rule, so the entity scan follows it too.
- An area can name one entity for its temperature and one for its humidity. An area card shows that entity even when it belongs to another area, so the page of a lite user gets it.
- An entity's device class comes from its state, and the area card selects its entities by that value.

## 0.3.0 - 2026-11-23

- **Groups of lite users.** Each group has its own users, dashboards and options. So the devices in one room and a tablet in another room each get the resources and the states for their own dashboards. Add a group with **Add group** under **Settings → Devices & services → Lite Resources**, and change one with its reconfigure button. A user can be in one group only.
- The update moves the users and the dashboards of a single-group configuration into one group named **Lite users**. Versions 0.3.0 and 0.3.1 gave it the name **Light users**. You do not need to enter anything again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
- **A saved dashboard reaches the open pages immediately.** When you save a dashboard in a group, each open page in that group gets each entity that is new on the dashboard, with its state. It loses the entities that left the dashboard. The integration needs no reload. A change to a group does the same.
- A page loads a card type that is new on a dashboard at its next page reload. The frontend loads its resources once for each page reload.
- **Always include** and **Always exclude** are optional overrides, and the form says so. A group's resources come from its dashboards.
- An Advanced Camera Card camera with `live_provider: webrtc-card` keeps the WebRTC Camera integration's resource, `webrtc-camera.js`. No card type in the dashboard names that resource.
- `lite_resources.preview` lists each group with its users, and the number of open pages with filtered states.
- An update event that names no dashboard, such as a change to the resource list, updates no page. Such an event has no URL path, and the default dashboard has the URL path `None`, so the two are kept apart.
- The manifest and the README name this fork, `ColColonCleaner/ha-lite-resources`, for the documentation, the issue tracker and the install. The README says that the repository is a fork of `evski/ha-lite-resources`, and it gives the install through the Marketplace in Home Assistant 2026.11.
- The repository tracked one test's Python bytecode file, and each test run changed it. Git now ignores each `__pycache__` folder.
- This version needs Home Assistant 2026.11 or later. The group checks ran on 2026.11.2.

## 0.2.1 - 2026-11-16

- Card names built in JavaScript are recognised. Mushroom's `mushroom.js` is loaded for `custom:mushroom-*-card` on the selected dashboards, including cards nested in stacks, sections, conditional cards and pop-ups.
- A resource is matched by its whole file name. `dreame-vacuum-card.js` is not sent for a Mushroom vacuum card, and `lock-manager.js` is not sent for a Mushroom lock card. Mentioning another card's name inside a file does not load that file.
- A file named after a card the selected dashboards don't use is no longer sent just because its contents could not be read. Scripts with a generic name, such as `/browser_mod.js`, are unchanged.
- Every dashboard selected in the integration is scanned, including one that nothing links to.
- New option **Always exclude**: resources lite users never load, including an integration script whose file name is not the card name. It wins over **Always include**.

## 0.2.0
- New option **Only send states their dashboards show**: lite users' live state subscription is narrowed to entities on their dashboards (cards, pop-ups, conditions, actions), group members and **Extra entities**. On a Sonoff NSPanel Pro this cut 2,955 streamed entities to 89.
- `lite_resources.preview` also lists the entities lite users receive.
- README rewritten: who it's for (wall panels, View Assist / VACA, the F-Droid Home Assistant app), screenshots, install buttons, FAQ. Issue templates.

## 0.1.2

Records the release order for this patch. Resource filtering is unchanged.

Publish the GitHub release for 0.1.2 after the Validate workflow on this commit succeeds. v0.1.1 was published at 2026-11-07 11:39:18 GMT, before hassfest (11:39:40 GMT) and HACS validation (11:39:57 GMT) finished on that commit.

## 0.1.1

Adds the integration icon used by the HACS brands check.

## 0.1.0

First release. Chosen users receive the dashboard resources their dashboards use. "Always include" matches resources by path, ignoring the version query string.
