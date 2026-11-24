# Changelog

## Unreleased

## 0.3.9 - 2026-11-24

A fourth independent review read the changes of 0.3.8 and the two commits with the static checks. It gave 22 findings: no critical one, no high one, 4 medium and 18 low. Each fault in behaviour needs a scan that fails, a scan that hangs or a YAML dashboard. The review found no fault on the path of a panel whose dashboards are stored in the UI and whose scan works. This version corrects each finding, and it states each limit that stays. It also adds a second type check, which reads the types of Home Assistant from the source of its core.

### Each validation runs before a commit

These changes came after the first commit of version 0.3.9. They add tooling and tests, and the integration's folder did not change.

- **hassfest never ran on this fork before.** It was a job of the Validate workflow only, and that workflow never ran on GitHub. So no version up to 0.3.9 had Home Assistant's own validation. Its first run on 0.3.9 found no error and no warning.
- **One script runs each validation: `python scripts/validate.py`.** It runs the unit tests, `ruff check`, the format check, both type checks and hassfest. It has no option that leaves a check out, and a check that cannot run is a failed check. A test compares the script's checks with the workflow's steps.
- **hassfest runs in the action's container image, with no network and no volume.** hassfest has no release as a package. The image is named by its digest, the integration's files reach the container as a tar stream, and the container holds no capability. The container can run on a host that the script reaches with `ssh`.
- **The script fails for a warning of hassfest.** hassfest exits with 0 for a warning, such as a discovery step with no unique ID.
- **Each plugin of hassfest that applies was proven with a fault.** A run for one integration loads 24 plugins, and each of the 24 ran. 11 of them read the files of a custom integration: `manifest`, `json`, `translations`, `services`, `config_flow`, `dependencies`, `requirements`, `config_schema`, `icons`, `triggers` and `conditions`. 17 copies of the integration with one fault each went through the same route, and hassfest named each fault. The other 13 plugins build index files of Home Assistant core, or check a core integration only.
- **A new test asks that each service has a name and a description.** hassfest asks this of a core integration only.
- **The script can refuse a working tree that holds more than the commit**, with the option `--tree-is-the-commit`, for use in a `pre-commit` hook. The checks read the working tree, so a file that the commit leaves out would make the result wrong.
- **A check gets none of git's hook variables, except the check of the working tree.** In a hook, git names its repository in variables such as `GIT_DIR`. With them, a unit test that makes a scratch repository acts on the clone in its place. The tests of the script run with such variables that name a decoy.
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

### The later tries after a failed scan

- **Each group has its own count of failed scans.** 0.3.8 held one count for all groups, and each page load of each group lowered it while one group had a fault. Six page loads of one group in 10 seconds used the tries of another group, which then got 1 try and not 6. Now a group's count changes only when a scan of that group fails or works.
- **A fault that lasts in one group no longer stops the tries of another group.** The one count of 0.3.8 started again only when no group had a fault. So a dashboard that stayed wrong left the count at 0. A scan of another group that failed one time then got no try, and its panel kept all states with no line in the log.
- **The count is of failed scans in a row.** Each scan of the group counts, also a scan that a new panel or a change starts. A try comes about 10 seconds after each failed scan, and a scan that works starts the count again.
- **The log says when the tries of a group end.** After 7 failed scans in a row, one warning names the group, and it says which events bring the next try.

### A scan that passes its time limit

- **A changed group gets a new scan at once.** 0.3.8 kept the open scan by the group's ID only. After you took a dashboard that hangs out of a group, each page load and each update of the group still waited 30 seconds for the old scan, and then gave all states. The integration now keeps the group's options beside the open scan, and a group with other options starts its own scan.
- **Nobody waits a second time for the same scan.** In 0.3.8 each later try waited up to 30 seconds for the scan that still ran, up to 6 times. It held the lock for the changes of all groups in that time, so a panel of another group that connected got no states for up to 30 seconds. Now a caller that finds such a scan gets no result at once.
- **A new scan has its own full time limit.** In 0.3.8 the wait for the old scan and the new scan shared one limit. A new scan that started late in that wait failed with the message `took longer than 30 seconds`, also when its load was normal.
- **The end of a late scan starts an update of its group.** In 0.3.8 nothing used that end. When a share returned after the last try, each panel of the group that held all states kept them until another event.
- **A scan is a background task.** 0.3.8 started it as a task that Home Assistant waits for at the end of its start and at its stop. A load that hangs then held both. Home Assistant does not wait for a background task, and it cancels each one at its stop.
- **The resource scan has the same time limit.** A request for `lovelace/resources` had no limit. A load that hangs left the panel with no answer, and such a panel loads no card. Now the panel gets the full list after 30 seconds.

### YAML dashboards

- **An open panel keeps its entities while a dashboard cannot be loaded.** 0.3.8 moved each open panel of the group to all states at the next update. So one typing error in one YAML file sent each kiosk of the group every state. A scan that failed in another way kept the entities, so the two faults had opposite results. Now both keep the entities. A panel that connects during the fault still gets all states.
- **A file that is put back after a fault reaches the open panels.** 0.3.8 compared a configuration with the last one that loaded with success. A file that failed and then came back as before counted as no change, when the first load after it was the preview action or a resource request. A panel that got all states during the fault then kept them. The integration now records a failed load, and the next good load of that dashboard counts as a change.
- **Each load is compared, and not only the load that fired the event.** A page load sends two requests at one time, and each loads the dashboard. When the load that did not find the changed file returned first, 0.3.8 stored the new configuration. The load that found the change then saw no difference, and the change reached no other open panel. Now each load compares its result with the last one, and the first load that sees a new configuration starts the update.
- **A save still gives each group one scan.** The update event of a save comes from another task, and it starts an update. The scans of that update load the new configuration, which is no second change. So the integration records each such event, and the first load after it starts no second update.
- **The comparison uses the configuration as text.** The YAML value `.nan` is not equal to itself. With that value in a file that fires its event at each load, 0.3.8 saw a change at each load, and the updates had no end. Two loads of one file give the same text.
- **A YAML dashboard whose file is gone is a dashboard that cannot be loaded.** Home Assistant raises an `OSError` for such a file after its first load. Before, that error ended the scan with a traceback at each page load.

### Other paths

- **A resource request that waits at a reload gets the reduced list.** 0.3.8 gave such a request the full list. Now the request goes to the handler that is registered at that time, as a state subscription does. After a reload, that is the new setup's handler.
- **A registry change starts no scan for a group that cannot be narrowed by design.** Such a group has a strategy, a card that finds its own entities, or a dashboard with no stored configuration, and no registry change alters that. 0.3.8 scanned the group again at each burst of registry events, which come each 10 seconds while Home Assistant starts. The integration now remembers such a group until a dashboard or a group changes.
- **One update scans a group one time.** Before, a group with a narrowed panel and a panel on all states got two scans in one update.
- **An update for one group leaves the other groups alone.** Before, the search for panels with all states ran a scan for each group.
- **A word that ends in `type` is no key.** 0.3.8 read `prototype: custom:x` and `subtype=custom:x` in a text as a card type. The pattern now asks for a boundary before `type`.
- **A card type with a dot inside a longer string is read whole.** Before, `custom:my.dotted-card` in a template gave the type `my`.
- **A warning belongs to one subject and holds its last value.** In 0.3.8 each reason had a key of its own, and only a good scan cleared the keys. An error in line 5, then in line 9, then in line 5 again gave two warnings and not three. Now the log gets a warning when the value for a subject changes. The warnings for a card type with no resource were never cleared before, and they now follow the same rule.
- **A reload forgets the warnings of the scan.** Before, `Dashboard X not found` came one time for each run of Home Assistant.

### Tests

- **The tests leave no state behind.** One test passed only at its first run in a process, because a warning record of the scan stayed from an earlier test. Each test class now clears the scan's records and its change listeners at its start. The suite passes two times in one process, in reverse order and in two shuffled orders.
- **The stand-in for a YAML dashboard has the cache rules of Home Assistant.** It keeps its cache when a load fails, and it fires its event when a cache existed before the read. The stand-in of 0.3.8 fired no event after a corrected error, so no test saw a file that returns to its old text.
- **The test for the end of the tries asks for the exact count.** In 0.3.8 it asked for an upper limit only, so it passed also when no try ran.
- **New tests cover the paths that the review named.**
  - The later tries: two groups, a group that changes during the scan of its old dashboards, and a late scan that ends in an error.
  - A YAML dashboard: a file that returns to its old text, two loads at one time, and a file with `.nan`.
  - A scan of two YAML dashboards of which one changed.
  - Each case of a YAML dashboard again for the default dashboard.
  - A stored dashboard: a save, a delete, and a page that connects after a save. Each test counts the scans.
  - A page that goes to another integration's handler at the unload.
  - A resource request at a reload, and a resource scan over the time limit.
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

- **The entry for 0.3.8 said four things that did not hold, and it is corrected.** The later tries were not always 6. One thread for a scan that hangs held only for the entity scan of one group. A warning did not come again when another reason came between. The format run changed the text of one comment: a comment in `resolver.py` that moved to its own line got a capital letter and a full stop.
- The README said `Two changes do not reach an open panel by themselves` and then named three. It now names three.
- The README says what a new panel and an open panel get for a dashboard that cannot be loaded, and for a scan that passes 30 seconds.
- The comments and the log messages that the review named are written anew with the code that they describe. The function that asks whether a load is the scan's own load now only answers. In 0.3.8 it also wrote a mark, which its name did not say.

### Limits that stay

- A load that never ends keeps its group's new panels on all states. That lasts until the load ends, the group changes, or Home Assistant restarts. Each open panel keeps its entities in that time.
- Each request for `lovelace/resources` and each call of the preview action starts a load of its own. While a load hangs, each of them holds one thread of the executor until the load ends.
- One lock serves the changes of all groups. So a slow scan of one group delays the first states of a new panel of another group, for up to 30 seconds.
- When the narrowed subscription fails after Home Assistant's handler sent its result, the panel gets a second result for the same message.
- A text in a dashboard that holds `type: custom:name`, or a quoted `'custom:name'`, names a card also when the text is a sentence for a person. The integration then sends one resource more, and never one less.
- A card type with a capital letter inside a longer string is not read. The name of a custom element holds no capital letter.
- The portable check `mypy` reads no type of Home Assistant. The full check needs a clone of the core source, and a library that the clone imports and that the environment lacks keeps the type `Any`.

## 0.3.8 - 2026-11-24

A third independent review read the changes of 0.3.6 and 0.3.7, and it gave 20 findings. None is critical. This version corrects each finding that holds. One finding did not hold, and the end of this entry names it. The review confirmed that 0.3.7 changed words only.

### A YAML dashboard whose file changes

- **A change that a scan of the integration finds first now reaches each open panel.** Home Assistant fires the update event of a YAML dashboard inside the load that finds the changed file. 0.3.6 dropped each such event that came while a scan of the integration loaded the dashboard. That scan could be the scan for one new panel, for a resource list or for the preview action. The other open panels then kept the old entities. Now the scan compares the configuration with the last one that it saw. When the two differ, each open panel of each group with that dashboard gets an update.
- **An event from the load of another task is no longer dropped.** 0.3.6 dropped each update event that came during a scan, also when the load of a browser fired it. The integration now drops only the event that its own load fires, and it knows that load by its task.
- **A file that fires at each load starts no update with no end.** Such a file gives the same configuration at each load, so the compare stops the chain. The rule of 0.3.6 was for this fault.
- **The time limit no longer cancels the load of a dashboard.** The limit of 0.3.6 cancelled the scan inside the load. Home Assistant then kept the new configuration and never fired the update event, for this integration and for each browser. Now the limit only ends the wait, and the scan runs to its end.

### Panels that kept all states

- **A dashboard that cannot be loaded stops the narrowing, and the log gives the real reason.** 0.3.6 left such a dashboard out of the entity scan, so the group stayed narrowed without its entities. When the file was correct again, no event came, and a panel that opened the dashboard had no state on it. Now the group gets all states, the log gives the error of the load, and the integration tries again. The resource list still leaves such a dashboard out.
- **The integration tries a failed scan again.** A panel that got all states after a scan error, a time limit or a load error kept them until another event. Now the integration tries the scan again, at most 6 times, with 10 seconds between the tries. One count served all groups, so a group could get fewer tries, which 0.3.9 corrects. When a try works, each open panel of the group is narrowed. When the scan for a new panel works after such a fault, the other panels of its group are narrowed also.
- **A registry change narrows a panel that holds all states.** Before, a registry change started no update while no panel was narrowed.
- **A page whose scan is open at a reload is narrowed by the new setup.** 0.3.6 gave such a page to the handler that the old setup held. The page got all states, and the new setup did not know it. Now the page goes to the handler that is registered at that time.
- **The entity scan of one group that hangs holds one thread.** While the entity scan of a group still runs after its time limit, the next entity scan of that group waits for its end. It starts no second load. A resource request and the preview action each start a load of their own.
- **A page that left during its wait gets no scan.** The task read the page's state only after its scan. A task that got its turn after an unload also ran a full scan and then dropped the result. Both checks now come before the scan.
- **A resource request that waits at an unload gets the full list.** The handler read the unload flag only before its scan.

### The scan

- **A strategy section in a sidebar, or inside another section, stops the narrowing.** The frontend makes a section for each item in `sidebar.sections` of a view, and for each item in `sections` of a section. 0.3.6 read the key `strategy` only in the sections of a view.
- **A quoted `custom:` type inside a longer string names a card again.** 0.3.6 took such a type only after the word `type`. A template that returns `'custom:name'` by itself named no card, and neither did YAML text with no quotes. The resource of such a card was not sent.
- **The last two of three joined pieces are no name for the guess.** The text `"my-" + "fancy-" + "thing"` gave the guess the name `fancy-thing`, which the file does not hold.
- **A warning comes again when its cause comes back after a good load.** The warning for a dashboard that cannot be loaded had a key with the dashboard's name only. So a later error of the same dashboard gave no warning. The key now holds the error text, and a good load clears it. The reasons why a group is not narrowed or not reduced are cleared in the same way.

### Tests and static checks

- **New tests run the real scan against a YAML dashboard that fires its event as Home Assistant does.** The test of 0.3.6 counted scans only, and its stand-in wrote the marker of the scan itself. The new tests ask that each open panel gets the new entities for each first loader: a new panel, the preview action, a resource request and a browser.
- New tests cover the time limit for a new panel and for an open panel, the later tries and their limit, a page whose scan is open at a reload, and a resource request at an unload.
- **Three stand-ins now behave as Home Assistant does.** The select field refuses a value that is no list. The administrator check raises `UnknownUser` for a user that does not exist, which is an `Unauthorized` error in Home Assistant. A closed connection records each send apart, because Home Assistant drops such a send.
- `tests/test_resolver.py` failed when it ran by itself, because its own stand-ins lacked one name. It now uses the shared stand-ins.
- **The repository has static checks.** `ruff.toml` sets up ruff with its default rule set, and the Validate workflow has a new job `lint` that runs `ruff check .` with ruff 0.17.5. The first run found no fault in behaviour. It found import blocks out of order, five broad `except` lines that are there on purpose and now say so, and some small points of style. All are corrected, and the import order of the tests now equals that of the integration.
- **The code has the format of `ruff format`**, which the development checklist of Home Assistant asks for. The run changed line breaks in 16 of the 18 Python files. The syntax tree of each file is the same before and after it. So is each comment, with one exception: a comment in `resolver.py` that moved to its own line got a capital letter and a full stop. The job `lint` checks the format also.
- **The integration has type checks.** `mypy.ini` sets up mypy 2.4.1 in its strict mode for the integration, and the job `lint` runs it. The checks run with no Home Assistant installation, so each name from Home Assistant has the type `Any`, and three strict checks that cannot pass with such names are off. The first run gave 18 findings. 15 came from those names. In two places, mypy held the unload flag for False after the first test, and so took the second test, which comes after a wait, for dead code. The code now reads the flag through a function. One was a variable with a type that was too wide in the resource scan. No finding was a fault in behaviour.

### Texts

- **A second wording pass.** 0.3.7 made sentences such as `Return each domain whose every entity one of the dashboard's cards shows`. A sentence must read well first. So a possessive now stays only for a short owner of a plain thing, such as `the group's dashboards`. Each other sentence of that kind is written anew, and some are longer. No possessive stands on a version or on a commit.
- The README says what a panel gets when a dashboard cannot be loaded, and when a scan passes 30 seconds. It says how a change to a YAML file reaches the panels, and when a file is sent for a guessed type. The warning for a guessed type says the same.
- The README gives the commands for the tests and for the static checks.

### Limits that stay

- The later tries stop after 6. A YAML dashboard that stays wrong keeps its group on all states until the next change or the next connection.
- The guess for a type with no provider reads only a file that holds `customElements.define(` before a name with no quotes. A card file that registers its element in another way needs *Always include*. The review built such files for its test, and it found no real card of that kind.
- Each new panel runs its own scan, and the scans run one after the other. Two panels of one group that connect together do not share a result.

### A finding that did not hold

- The review asked what a send on a closed connection does, because a page can close during its scan. In Home Assistant 2026.11.2, such a send writes one debug line and raises nothing.

## 0.3.7 - 2026-11-24

- **The fork's texts use the possessive form.** The README, this changelog from 0.3.0 on, the form texts, the log messages and the code comments now say `a group's dashboards` and not `the dashboards of a group`. The word `of` stays for a part, an amount, the contents, an action before its object, and an owner with a clause after it.
- No behaviour changed. Some log messages have new words, and two of them are now two sentences with no semicolon.
- The upstream author's paragraphs in the README, and the entries up to 0.2.1, keep their wording.

## 0.3.6 - 2026-11-23

A second independent review covered the whole code at 0.3.5. It gave 35 findings: no critical one, 1 high, 6 medium and 28 low. 24 of them are in code that 0.3.5 added. This version corrects each fault that the review confirmed, and it states each limit that stays. Three findings did not hold against the source of Home Assistant 2026.11.2, and the end of this entry names them.

### Rules of 0.3.5 that stopped the narrowing too often

- **A card feature with a like name no longer stops its group's narrowing. (high)** 0.3.5 took each `type` that starts with `energy-`, `water-`, `power-` or `gas-` as an energy settings card, in each mapping of a dashboard. A tile card's feature `water-heater-operation-modes` is none of these, and one such feature gave all states to each panel in the group. The rule now holds the frontend's exact card and badge types, and it reads no type inside a card's features.
- **The key `strategy` counts only where the frontend reads it.** 0.3.5 took that key in each mapping as a strategy, also as a custom card's option or in an action's data. It now counts at the dashboard, at a view and at a section.
- **A dashboard that cannot be loaded is left out.** 0.3.5 took each load error as a dashboard with no stored configuration, so one YAML dashboard with a syntax error stopped its group's narrowing. Only a dashboard with no stored configuration does that now. Another load error leaves the dashboard out, with one warning that gives the error.

### An open page's state stream

- **A task that still waits at the unload changes no page.** The unload returned each page to all states. The old setup's task that waited on a scan then narrowed the page again, into a table that nothing updated. After a removal the page stayed narrowed. After a reload the new setup did not find it. The unload now sets a flag, and that setup's tasks and handlers read it after each wait.
- **An unloaded setup's handler passes each message on.** When another integration keeps this integration's handler and calls it after the unload, the handler now gives the message to Home Assistant's handler.
- **An update event that the scan itself causes starts no new scan.** A YAML dashboard's load can fire that dashboard's update event. For a file that Home Assistant does not cache, such as an empty file or a file with a time in the future, each scan fired an event and each event started a scan, with no end. An event that comes while this integration's scan loads that dashboard is now left out.
- **Many events close together give one more update.** Each dashboard save started its own update, and 20 saves gave 20 scans. An update that runs now takes each later request with it.
- **A new page waits for an update that runs.** A page's first subscription ran apart from the updates of the open pages, so a page that started during a save could keep the older entity set.
- **One entity scan has a time limit of 30 seconds.** The changes to the open pages run one after the other. A dashboard load with no end, such as a YAML file on a dead share, held each later change.
- **A client that ends its subscription during the scan gets its command's result.** Before, that command got no answer.
- **An adoption's removal list holds only entities that the user can read.** It held each entity in Home Assistant, so a user with a narrow policy learned the names that the policy hides.
- **A page is in the open pages table before its removal message goes out.** If that message failed, it could leave a narrowed listener that the table did not know.
- **The log names each state listener that the adoption cannot read.** The check in 0.3.5 saw two layout changes only. The search now accepts only the exact five arguments that it knows, and it counts each listener that holds Home Assistant's function with another layout. The log holds one warning with that count.
- **The log names a page that keeps its narrowed states at the unload**, when the return to all states fails for it.

### The entities and the resources

- **A tile card for a device tracker gets each zone**, as a tile card for a person does.
- **`custom:` in plain text is no card.** 0.3.5 took each `custom:name` inside a longer string as a card on the dashboard, also in the text of a markdown card. It now needs the key `type` before it, as in a template that returns a card.
- **A key that ends in `type` is no registration.** The file scan took `layout_type:"grid-layout"` as a registration of `grid-layout`. That false provider was sent, and it stopped the search for the type's real file.
- **The guess for a type with no provider takes fewer files.** It took each file that names the type in quotes. It now takes only a file with a registration that the scan cannot read, such as the call inside a minified decorator. A file whose registrations all have a quoted name registers no other element.
- **That guess finds a name of two quoted pieces in a helper call.** 0.3.5 dropped such a pair outside a registration and an assignment, so a bundle that registers `"my"+"-card"` through a helper lost its card.
- **A name of three quoted pieces gives no wrong name.** The scan joined the first two pieces.
- **The preview lists each file with no element, whatever its name is.** 0.3.5 left out each file with a hyphen or with six or more characters in its name, so an icon set such as `custom-brand-icons.js` did not show. The list now holds also a card that the dashboards do not use and whose registration the scan cannot see.
- **The preview lists the names with no state.** A state subscription holds each name in the dashboards, also one with no state now. The preview showed only the entities with a state. The new key `state_entities_without_state` holds the rest.

### The form and the tests

- A stored user that is not active shows its name with `(not active)` in a group's form. 0.3.5 showed its ID with `(user not found)`.
- **The stand-ins in the tests take Home Assistant's order and defaults.** The unload callbacks run from the last one to the first, a task starts eagerly by default, and the stand-in for the administrator check refuses a user that is no administrator and passes the answer on. The stand-in for a select field refuses a value outside its options.
- New tests cover the group form's two steps, the resource handler's three paths that give the full list or a warning, a narrowed call that fails while the call for all states works, a subscription with a filter, and each correction in this version. The tests grow from 180 to 207.

### Findings that did not hold

- The preview action returns its answer through Home Assistant's administrator wrapper: `_async_admin_handler` returns the function's answer.
- A new group and a deleted group call the entry's update listener: `async_add_subentry` and `async_remove_subentry` both end in `_async_save_and_notify`.
- Home Assistant refuses an entry with a higher version than the flow knows before it calls the migration.

### Limits that stay

- **A group that the integration can no longer narrow gets all states on each open panel.** A dashboard save can add a strategy, a home-summary card or an energy card. Each open panel in the group then gets all states in one message, about 1.4 MB for 5,573 entities. Each panel also gets each state change after that. The log holds one warning with the reason. An unload and a reload send the same message one time.
- **A custom strategy that makes custom cards** names no card in the stored dashboard. Add each such card's resource under **Always include**.
- **When a file gives one short name more than one value, each value joins each template that uses that name.** A minified bundle can then seem to provide a card that it does not hold, and a panel loads it for nothing. No real bundle showed this.
- **Cost.** Each state subscription runs a scan of about 20 ms to 40 ms for 5,573 entities. Panels that connect together share no result. A change to one entity sends its whole set again to each open panel in the group.
- The three checks against the real package do not cover the handler for `subscribe_entities` as a whole. They also do not cover a user that is no administrator, a state change through a new listener, or an entry's setup. The test on a running Home Assistant covers those.

## 0.3.5 - 2026-11-23

An independent review of the whole code gave 51 findings: 1 critical, 1 high, 5 medium and 44 low. This version corrects each fault that it confirmed, and it states each limit that stays. Each point is in the list below.

A second review found faults in this version, and 0.3.6 corrects them. The largest one: three new rules stopped a group's narrowing too often, so install 0.3.6 and not this version.

### An open page's state stream

- **The adoption in 0.3.4 could leave each panel with no state stream after a restart.** The adoption made its own message for Home Assistant's handler, and that message did not pass the command's schema. The handler reads the keys `include` and `exclude`, which only the schema adds, so it failed with `KeyError`. The adoption ended the page's state listener before that call. The first 0.3.4 code then left the page with no listener, and its later correction sent the same message again and failed again. Each message that the integration makes now passes the schema first. The review found the fault before the first known install of 0.3.4.
- **A change to an open subscription starts the new listener before it ends the old one.** If the handler fails, the old listener goes back into its place, and the page keeps the entities that it had. Versions 0.3.0 to 0.3.4 ended the old listener first. This holds for a new entity set, for an adoption, and for the return to all states, which had no guard at all.
- **The integration's unload or removal gives each open page all states again.** Before, such a page kept its narrowed set until it connected again, against the README text that all is as before after a removal.
- **The integration's reload no longer loses the open pages.** Before, the new setup did not know the pages that the old setup narrowed. A saved dashboard, a changed group and a deleted group then changed nothing for them. The unload now returns each page to all states, and the new setup narrows it again.
- **A connection that closes during the entity scan gets no listener.** The scan can wait, such as at a dashboard's first load or for a YAML dashboard. A page that left in that time got a state listener and a place in the open pages table, and nothing ended them. The handler now puts a stand-in into the connection's subscriptions, which Home Assistant removes at a close.
- **Two changes at one time leave the newer entity set.** Two dashboard saves close together could leave a page with the older set. The changes to the open pages now run one after the other.
- **A new page gets all states, or an error message, when the handler fails.** Before, a failure inside a narrowed subscription's task sent the page no result and no error, and the page waited with no end. The page now gets the subscription for all states. If that fails too, the page gets the error message that Home Assistant sends for a failed handler.
- **A failed entity scan leaves each open page as it is, and a failure for one page no longer stops the update of the pages after it.** Before, an error for one page ended the update for each later page, and the adoption after a group change did not run.
- **The log says when Home Assistant has another layout than the adoption expects.** The search for early subscriptions reads the listener table of the event bus and the function `_forward_entity_changes`. On a version without them the search found nothing and the log held nothing. The setup now logs one warning. The search also catches each kind of error at the read, and it takes that function only from the Home Assistant module that defines it.
- **The update at the end of the start no longer depends on `hass.is_running`.** That property is true also while Home Assistant starts, so a setup in that time added no listener. The setup now uses `async_at_started`.
- **An unload keeps a handler that another integration registered after this one.** Before, the unload wrote Home Assistant's two handlers back, whatever the table held.
- **A change to the entity, device or area registry updates the open pages.** A new schedule, an entity that moves into an area card's area, and an entity that is no longer hidden now reach an open page. The registries change in bursts, so one update follows 10 seconds after the first change.

### A group's entities

- **A dashboard with no stored configuration no longer gives a page two entities. (high)** Home Assistant generates such a dashboard in the browser, such as the default dashboard before its first edit. The scan read it as an empty dashboard, so a panel got only `sun.sun` and `zone.home`, with no line in the log. Such a group's states are now not narrowed, and the log says why one time. The same holds when no dashboard in the group exists. A deleted dashboard beside a stored one is left out, with one warning.
- **A strategy stops its group's narrowing.** A dashboard, a view or a section with a strategy holds no card: the browser makes them. Such a page got no entity for those cards. The scan also read the area view strategy as an area card.
- **Core cards that find their entities by themselves.** The `home-summary` card and the energy, water, power and gas cards and badges take their entities from all states or from the energy settings, so a group with one of them is not narrowed. A `map` card with `show_all` gets each person, device tracker and zone, and with `geo_location_sources` each geo location entity. The `updates` card gets each update entity. A tile card for a person, and a visibility condition on the user's location, get each zone.
- **Each group user's person entity is sent.** The frontend finds the signed-in user's person by a search of all states, for a location condition and for the user's picture.
- **The scan reads a dashboard's values, and not its JSON text.** In JSON text, a line break or a tab inside a string is a backslash and a letter, which hid the entity ID after it. A value that JSON does not know, such as a date with no quotes in a YAML dashboard, made the scan fail, which turned the filter off for the group with an error at each page load.
- **An action's name is no entity.** A name such as `light.turn_on` with no state went into a state subscription's list. Each other name with no state stays, because its first state can come later.
- **The default dashboard is the dashboard `lovelace` when it exists.** Home Assistant 2026.11 takes that dashboard for a request with no URL path, before the dashboard with the key `None`. The scan and the update after a save now do the same.

### A group's resources

- **An element that a minified decorator registers keeps its file.** The file scan sees an element in `customElements.define` with a quoted name, in a `type:` entry, and through the file name. A bundle that registers a second element only through Lit's decorator, such as a layout in `layout-card.js`, lost that element, and its card showed `Custom element doesn't exist`. For a needed type that no file provides, each file that names the type in quotes is now sent, and the log names the type one time. A type with a provider never takes this way, so a file that only mentions another file's card stays out. A type that a resource under **Always exclude** provides takes no such file.
- **A card type inside a template is seen.** A template that returns `{type: 'custom:...'}` holds the type inside a longer string, and the scan read only a string that is the type as a whole.
- **A camera with the key `webrtc_card` keeps the WebRTC script.** The Advanced Camera Card takes the live provider `webrtc-card` by itself for such a camera, and 0.3.0 kept the script only for the written value `webrtc-card`.
- **A card type with no readable provider is in the log.** When one sent resource cannot be read, a type with no provider counts as not verified, and the log held nothing for it. The log now holds one warning for it.
- **Each warning is in the log one time.** `Dashboard ... not found` and `No local resource provides ...` came at each request from each page.
- **A file that cannot be read counts as not readable.** A cut or corrupt `.gz` copy, and a path with a null character, raised an error that failed the whole group's request. Each page load then sent the full list and wrote a traceback.
- **A resource URL with a host is no local file.** Another server's URL with a path that starts with `/local/` or `/hacsfiles/` was scanned as this server's file.
- **Always include and Always exclude compare the host and the path.** Before, an entry for one host's resource also took a resource with the same path on another host. The version in the query still does not count.
- **A name that a file binds more than one time.** A minified file gives one short name more than one value, and the scan kept only the last one, so a template such as `${p}-light-card` gave a wrong name. Each value now counts.
- **Two quoted pieces with a plus count only in a registration or in an assignment to a variable.** Before, each such pair in a file counted as an element that the file registers, such as a CSS class name.
- **A config folder path that is not in the system's normal form refused each local file.** The test that keeps a resource path inside the `www` folder compared a normal path with one that was not. Both now have the normal form.
- **The preview lists the files with no element.** A resource that works by a side effect, such as an icon set, provides no card type, so it is not sent. `lite_resources.preview` now lists each readable file with no element and no card's file name under `excluded_without_element`. Add such a file under **Always include** when a panel needs it.

### The form, the action and the checks

- **`lite_resources.preview` is for administrators.** Before, each signed-in user could call it, and it names each group, each user, each dashboard and each entity in the dashboards. The preview now also says why a group's states or resources are not narrowed.
- **A group's form keeps a stored value that is no option any more.** A select field refuses a value outside its options. A group with a deleted user, a deleted dashboard or an older version's resource URL could not be saved until that value was removed, and the error did not name it.
- **The form shows a stored group's state filter as it is.** For a group with no stored value the form showed the filter as on, and such a group does not filter. A plain submit then turned the filter on. The update from a single-group version now also writes the filter as off when that version did not hold the option.
- **A user in two groups is in the log.** Two forms that are open at one time can each add the same user. The first group in the list counts, and the log now says so.
- A group has a hash. Before, `hash(Group)` raised an error, because the options are a dict.
- A group's text `reconfigure_successful` is gone. Home Assistant shows its own text after a change to a group.
- **The stand-ins in the tests fail as Home Assistant does.** The stand-in for Home Assistant's handler accepted each message, so 18 adoption tests passed with the fault of 0.3.4. It now reads `include` and `exclude` with no default, and the stand-in for the filter does the same. The harness runs an eager task as Home Assistant does, and it can make the entity scan wait and close a connection. New tests cover the group form, the paths that give a panel the full list or all states, a resource URL's path test, a `.gz` copy and the file cache. The tests grow from 105 to 180.
- The check against the real package of Home Assistant 2026.11.2 now calls the handler exactly as the integration does. The earlier check passed each message through the schema itself, so it did not show the fault.
- The Validate workflow runs the unit tests.

### Limits that stay

- **Member lists.** A light group's new member, and a new entity that a schedule controls, reach an open page at its next load, at its dashboard's next save, or at a registry's next change.
- **Each client that signs in as a lite user is narrowed.** The integration knows a connection's user and not its program. A companion app or a script that signs in as a lite user and asks for all states gets only the entities on the dashboards.
- **Custom cards that select their entities in the browser.** `auto-entities` with a domain filter, the entity list in the scheduler card's editor, and a template that builds an entity ID from a variable name no entity in the dashboard. Add those entities under **Extra entities**.
- **An administrator who is a lite user** sees the reduced resource list also on the page **Settings**, **Dashboards**, **Resources**.
- **A YAML dashboard** fires no event when its file changes. Its open pages get the new entities when a page loads the dashboard again.
- **Cost.** A group's entity set is worked out again for each state subscription and each update. One run took 29 ms to 39 ms for 5,573 entities on a workstation. An adoption sends one removal message with each other entity, about 200 KB for that home.
- The Validate workflow's hassfest action and HACS action stay on a moving branch, `hassfest@master` and `hacs/action@main`, as the upstream project set them. Home Assistant's developer blog gives `hassfest@master`.
- The text `single_instance_allowed` stays. The review did not verify that Home Assistant never shows it.
- This fork's link to the issue tracker, its release badge and its Validate badge need issues, a release and workflow runs on GitHub. The README's section **Releasing** still describes the upstream project's releases.

## 0.3.4 - 2026-11-23

- **A panel stays a lite panel across a Home Assistant restart.** After a restart, a panel connects again within seconds, before Home Assistant sets a custom integration up. Home Assistant's handler then answered the panel's state subscription, with every entity. On one kiosk the page went from 95 entities to 5,573, and it fell more than 200 seconds behind for 10 minutes, until its connection broke. Lite Resources now finds such a subscription when its setup runs, and narrows it in place: the panel drops the entities that its dashboards do not show, and it keeps its connection.
- A user that joins a group gets the narrowed stream at once on each open page, in the same way.
- The search for those subscriptions reads internals of Home Assistant 2026.11: the listener list of the event bus. On a version with another layout it finds nothing, and a panel then gets its narrowed stream at its next connection, as before. The search takes the listener function only from the Home Assistant module that defines it.
- A second commit of this version, `57bf290`, tried to give a page the stream of all entities again when its narrowed subscription failed.
- **This version has a critical fault, and 0.3.5 replaces it. Do not install 0.3.4.** The adoption gave Home Assistant's handler a message that did not pass the command's schema, so the handler failed after the adoption ended the page's listener. Each adopted panel then had no state stream until it connected again. The return to all entities in `57bf290` sent the same message, so it failed in the same way. Two commits carry this version number: `ce1fba9` and `57bf290`.

## 0.3.3 - 2026-11-23

- **The instructions say where each action is.** The README gives each step of the install and of the setup. **Add group** is the button in the upper-right corner of the integration's page, and an item in the entry's three-dot menu. A group's cog icon changes it, and a group's three-dot menu renames or deletes it. A picture shows that page.
- The setup dialog and a group's dialog name the same places.
- The README no longer gives a button as a replacement for a list of steps. The setup button is a second way to do the first step only. The install section gives its steps with no button, because nobody checked that the button opens a repository that the catalog does not list.

## 0.3.2 - 2026-11-23

- **A page that connects while Home Assistant starts gets each of its entities.** Many entities get their first state some seconds after the start. A page that connected before that time never received them, and its cards showed no camera or no value until the page connected again. A lite user's state subscription now holds also each entity name with no state yet, so each one arrives with its first state. The registry gives such an entity's domain and device class.
- When Home Assistant's start is complete, each open page that belongs to a lite user gets its entity set again. A group entity names its members only after its integration loads.
- **The texts say lite users.** The word `light` now names only a lamp. The group that the update makes from a single-group setup has the name **Lite users**.

## 0.3.1 - 2026-11-23

- **The area card gets its area's entities.** An area card names an area and no entity. It finds its camera, its sensors, its alerts and its controls in the registries. Lite users now receive those entities, by the card's rules: the entity is in the area, it is not hidden, and it has no entity category. Before this version, such a card showed no light button, no temperature and no motion alert for a lite user.
- **The scheduler card gets its schedules.** Each schedule is a switch that the scheduler integration provides, and the card shows an empty row for a schedule with no state. Lite users now receive those switches, and the entities that each schedule controls.
- An entity with no area of its own has its device's area, and a child device with no area has its parent device's area. The area card follows that rule, so the search for its entities does too.
- An area can name one entity for its temperature and one for its humidity. An area card shows that entity also when it belongs to another area, so lite users receive it.
- An entity's device class comes from its state, which is the value that the area card filters on.

## 0.3.0 - 2026-11-23

- **Groups of lite users.** Each group has its own users, dashboards and options. So the panels in one room and a tablet in another room each get the resources and the states for their own dashboards. Add a group with **Add group** on the integration page, and change one with its reconfigure button. A user can be in one group only.
- The update moves a single-group setup's users and dashboards into one group named **Lite users**. Versions 0.3.0 and 0.3.1 gave it the name **Light users**. You enter nothing again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
- **A changed dashboard reaches the open panels at once.** When you save a dashboard in a group, each open page in that group gets each entity that is new on the dashboard, with its state. It loses the entities that left the dashboard. The integration needs no reload. A change to a group does the same.
- A card type that is new on a dashboard loads on a panel at that panel's next page load. The frontend loads its resources one time for each page load.
- **Always include** and **Always exclude** are optional overrides, and the form says so. A group's resources come from its dashboards.
- An Advanced Camera Card camera with `live_provider: webrtc-card` keeps the WebRTC Camera integration's script, `webrtc-camera.js`. No card type in the dashboard names that script.
- `lite_resources.preview` lists each group with its users, and the number of open pages with narrowed states.
- An update event that names no dashboard, such as a change to the resource list, updates no page. Such an event has no URL path, and the default dashboard has the URL path `None`, so the two are kept apart.
- The manifest and the README name this fork, `ColColonCleaner/ha-lite-resources`, for the documentation, the issue tracker and the install. The README says that the repository is a fork of `evski/ha-lite-resources`, and it gives the install through the Marketplace in Home Assistant 2026.11.
- The repository tracked one test's Python bytecode file, and each test run changed it. Git now ignores each `__pycache__` folder.
- Needs Home Assistant 2026.11 or later. The group checks ran on 2026.11.2.

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
