# Lite Resources

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Release](https://img.shields.io/github/v/release/ColColonCleaner/ha-lite-resources)](https://github.com/ColColonCleaner/ha-lite-resources/releases)
[![Validate](https://github.com/ColColonCleaner/ha-lite-resources/actions/workflows/validate.yaml/badge.svg)](https://github.com/ColColonCleaner/ha-lite-resources/actions/workflows/validate.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This repository is a fork of [evski/ha-lite-resources](https://github.com/evski/ha-lite-resources). It adds [groups](#groups) of lite users, each with its own dashboards.

**Make Home Assistant dashboards fast on wall panels, old tablets and other low-powered screens - without changing anything for your phones and computers.**

Home Assistant sends every screen the same thing: *every* custom card you've ever installed, and a live update for *every* entity in your home, whether or not that screen shows it. A phone shrugs that off. A wall panel with a slow chip spends its life downloading JavaScript it never runs and processing updates for sensors it never displays - and you feel it as a laggy, stuttering dashboard.

Lite Resources fixes that for the users your panels log in as:

| | Without | With Lite Resources |
|---|---|---|
| Custom card files loaded at start-up | all of them (25 files, ~9 MB here) | only the ones the panel's dashboard uses (2 here) |
| Entities streamed live | every entity (2,955 here, ~28 updates a second) | only those on the panel's dashboard (89 here) |
| Your phone, tablet, desktop | unchanged | unchanged |

<p align="center">
  <img src="docs/images/panel-landing.png" width="240" alt="Landing panel: lights and lighting modes">
  <img src="docs/images/panel-heating.png" width="240" alt="Heating tab">
  <img src="docs/images/panel-cameras.png" width="240" alt="Cameras tab">
  <br><em>A Sonoff NSPanel Pro (480×480, Rockchip PX30) running a full Home Assistant dashboard with Lite Resources.</em>
</p>

## Who is it for?

Anyone running a Home Assistant dashboard on hardware that struggles with it. For example:

- **Sonoff NSPanel Pro** (Gen 1 / Gen 2) and other Android in-wall switch panels (Tuya, Moes, Shelly Wall Display, "86-box" panels)
- **Amazon Fire tablets** (Fire 7 / HD 8 / HD 10) used as wall dashboards
- **Old iPads and Android tablets** given a second life on the wall
- **Raspberry Pi touchscreens** running a Chromium kiosk (Pi 3, Pi Zero 2 W, older Pi 4s)
- **Echo Show / Lenovo smart displays** running a browser or Fully Kiosk
- **Old phones** used as room remotes
- The **Home Assistant app from F-Droid** (the "minimal" Companion build without Google services), common on de-Googled and budget Android panels
- Anything shown through **Fully Kiosk Browser, WallPanel, View Assist / VACA, or the Home Assistant Companion app** on a modest device

The more custom cards you have installed and the more entities your home has, the bigger the difference.

### Running View Assist / VACA?

If you use [View Assist](https://github.com/dinki/View-Assist) with the **View Assist Companion App (VACA)** on a wall tablet or panel, this is for you. VACA's screen is a Home Assistant dashboard running on the same modest hardware that's also doing wake-word detection and audio - every bit of CPU the dashboard doesn't waste is CPU the voice side gets. Point Lite Resources at the user your VACA device logs in as and its View Assist dashboard(s). Voice, timers and VACA's device controls are unaffected: they don't use the dashboard's connection.

## How it works

Nothing is changed on disk and nothing is patched in the frontend. Lite Resources answers two of the frontend's own requests differently for the users you choose:

1. **Resources** - the frontend asks once per page load for the list of dashboard resources (`lovelace/resources`). Lite users get only the resources their dashboards use. Lite Resources reads every dashboard you select (including one nothing links to), collects every `custom:` card type in that config (stacks, sections, conditional cards, pop-ups and features), and finds which resource files register them. A bundle that builds its element names in code is recognised too (`mushroom.js` provides `custom:mushroom-*-card`). A file is matched by its whole name, so `dreame-vacuum-card.js` is not treated as the Mushroom vacuum card and `lock-manager.js` is not treated as the Mushroom lock card. Mods with no card type are detected from dashboard keys (`card_mod` → card-mod, `kiosk_mode` → kiosk-mode).
2. **States** (optional) - the frontend subscribes to every entity's state (`subscribe_entities`). Lite users' subscription is narrowed to the entities that appear anywhere in their dashboards (cards, pop-ups, conditions, actions), plus members of any groups, plus anything you add yourself.

One more need has no card type. An Advanced Camera Card camera with `live_provider: webrtc-card`, or with the key `webrtc_card` and no live provider, needs the WebRTC Camera integration's script. Lite Resources keeps that script when a dashboard holds one of them.

Some cards name no entity, and find their entities by themselves. Lite Resources sends those entities too:

- The **area card** shows its area's camera, sensors, alerts and controls. Lite users get that area's entities that the card can show.
- The **scheduler card** shows the scheduler integration's schedules. Lite users get each schedule, and the entities that it controls.
- A **map card** with `show_all` gets each person, device tracker and zone. With `geo_location_sources` it gets each geo location entity.
- The **updates card** gets each update entity.
- A **tile card for a person** or a **tile card for a device tracker**, and a visibility condition on the user's **location**, get each zone.
- Each lite user gets its own person entity, which the frontend reads for that condition and for the user's picture.

For another card of this kind, add its entities under *Extra entities*. Custom cards that select entities in the browser are of this kind: `auto-entities` with a domain filter, the entity list in the scheduler card's editor, and a template that builds an entity ID from a variable.

### When a group's states are not narrowed

Some dashboards do not say which entities a panel needs. A group with such a dashboard gets all states, as without this integration, and the log says why one time. `lite_resources.preview` says it too. The group's resources are still reduced.

- A dashboard with no stored configuration. Home Assistant generates such a dashboard in the browser, such as the default dashboard before its first edit.
- A dashboard, a view or a section with a **strategy**. The browser makes its cards. This holds also for a section in the sidebar of a view, and for a section inside another section.
- The **home-summary** card, the **energy**, **water** and **power** cards, and the badges **power-total**, **gas-total** and **water-total**. They take their entities from all states or from the energy settings.

On a slow panel, all states are the load that this integration exists to remove. When you save such a card to a dashboard in a group, each open panel in that group gets all states at once. So look at the log, or at the preview, after you change a dashboard in a group.

A custom strategy that makes custom cards names no card in the stored dashboard. Add each such card's resource under *Always include*.

Two faults give all states only to a panel that connects during the fault, because no scan says which entities that panel needs. A panel that is open at that time keeps the entities that it has. The log gives each new reason one time.

- A dashboard that Home Assistant cannot load, such as a YAML dashboard with a syntax error. Lite Resources tries the scan again by itself, about 10 seconds after each failed scan. After 7 failed scans in a row, the log says so. The next try then comes at the next change that the section *When a dashboard changes* names, or when one of the group's panels connects.
- A scan that takes longer than 30 seconds, such as the load of a YAML dashboard from a share that does not answer. While that scan runs, Lite Resources starts no second scan of the group, unless you change the group. When the scan ends, the group gets a new scan.

When a scan works again, each open panel of the group is narrowed, and each gets the group's entities of that time.

Everyone else gets Home Assistant's normal behaviour. Remove the integration and everything is exactly as before: each open panel gets all states again at once.

## Groups

A group holds the users that one set of panels logs in as, and the dashboards that those panels show. Each group gets the resources and the states for its own dashboards. For example, a workshop's kiosks are one group, and a kitchen tablet is a second group with another dashboard. A user can be in one group only.

You do not list a group's resources. Lite Resources finds them from the group's dashboards at each page load. It finds the entities at each panel connection.

### When a dashboard changes

Design the dashboards as a normal user, with every resource loaded. When you save a dashboard in a group, these things occur, and the integration needs no reload:

- Home Assistant sends the new dashboard to each open panel. This is its standard behaviour.
- Lite Resources finds the group's entities again. Each open panel in the group gets the states of the new entities at once, and loses the entities that left the dashboards.
- A card type that is new on the dashboards loads on a panel at that panel's next page load. The frontend loads its resources one time for each page load, so that card shows an error on the panel until then.

A change to a group, such as a new user or a new dashboard, reaches the open panels the same way. So does a change to the entity, device or area registry, about 10 seconds after it: a new schedule, or an entity that moves into an area card's area.

Three changes do not reach an open panel by themselves. The first is a change to the file of a YAML dashboard. Home Assistant reads that file again only when something loads the dashboard. So the change reaches the open panels at the next such load. That load comes when a panel or a browser opens the dashboard, or at the next change above. Each open panel of each group with that dashboard then gets the new entities.

The second is a new member of a light group. The third is a new entity that a schedule controls. Each of the two reaches a panel at its next page load or at the next change above.

### After a Home Assistant restart

A panel connects again within seconds of a restart. Home Assistant sets a custom integration up some seconds later, so the panel's first state subscription is for every entity. When the Lite Resources setup runs, it finds that subscription and narrows it. The panel then drops the entities that its dashboards do not show, and it keeps its connection. The search for that subscription reads internals of Home Assistant 2026.11. On a version with another layout, the log holds a warning, and such a panel keeps all states until it connects again.

One fault stays, and it is not in this integration. After a restart, a card with a camera can show no camera until the page loads again. In one home, a panel asked for its cameras 9 seconds after the start, and Home Assistant answered `Camera not found`, because the camera integration was not ready. So let each panel load its page again some minutes after a restart, for example with its kiosk browser's reload timer.

## Install

Lite Resources needs Home Assistant 2026.11 or later.

### Marketplace (recommended)

The Marketplace replaced HACS in Home Assistant 2026.11.

Do each of these steps:

1. Open **Settings → Marketplace**.
2. Select **Add from link** in the upper-right corner.
3. Under **GitHub link**, enter `https://github.com/ColColonCleaner/ha-lite-resources`, and select **Add**. If the Marketplace asks you to connect GitHub, do that first.
4. Select **Lite Resources** in the list to open its page. Select **Install**, and **Install** again in the dialog.
5. Restart Home Assistant. A repair under **Settings → System → Repairs** asks for the restart and can do it.

If the Marketplace holds `evski/ha-lite-resources`, uninstall that repository first, because both repositories install the same integration folder. Open that repository's page in the Marketplace. Select the three-dot menu (⋮) in the upper-right corner, then **Uninstall**, then **Delete and uninstall**. That also deletes its setup.

To update later, open the repository's page in the Marketplace and install the new version, then restart Home Assistant.

### Manual

Copy `custom_components/lite_resources` into your `config/custom_components/` folder and restart Home Assistant.

## Set up

Do each of these steps. The button is only a second way to do step 1.

1. Open the dialog that adds the integration, in one of two ways:
   - Open **Settings → Devices & services**, select **Add integration**, search for **Lite Resources**, and select it.
   - Select this button: [![Open your Home Assistant instance and start setting up Lite Resources.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=lite_resources)
2. The dialog has no settings, so select **Submit**. The dialog names the next step, and it does not show this list's steps.
3. Open the integration's page: **Settings → Devices & services → Lite Resources**. The page shows the entry **Lite Resources**.
4. Select **Add group**. It is in two places on that page: the button in the upper-right corner, and the three-dot menu (⋮) at the right of the entry **Lite Resources**.
5. Fill in the form with the options in the table below, and select **Submit**. The group then shows as a row below the entry.
6. Do steps 4 and 5 again for each other set of panels.
7. Reload each panel's browser or app.

<p align="center">
  <img src="docs/images/integration-page.png" width="720" alt="The integration's page. Add group is the button in the upper-right corner and an item in the entry's three-dot menu. Each group is a row with a cog icon.">
  <br><em>The integration's page with two groups. The entry's three-dot menu is open.</em>
</p>

| Option | What to choose |
|---|---|
| **Group name** | A name for the set of panels, such as *Workshop kiosks*. |
| **Lite users** | The user(s) your panels log in as. Give each panel its own Home Assistant user if it doesn't have one. |
| **Their dashboards** | Every dashboard those users open. |
| **Always include** | Optional. Leave it empty, because the resources come from the dashboards. Add a resource only if a card fails to load (e.g. a mod your theme relies on). |
| **Always exclude** | Resources to never load, even if a card seems to need them. Use this for an integration script with a generic name, such as `/dreame_vacuum/frontend.js`, that these dashboards don't use. It wins over *Always include*. |
| **Include resources that can't be checked** | Resources served by integrations (e.g. `/browser_mod.js`, `/webrtc/...`) can't be read. On = load them (safe default). Off = skip them unless listed under *Always include*. A file whose name is a card these dashboards don't use, such as `dreame-vacuum-card.js`, is skipped either way. |
| **Only send states their dashboards show** | On for a new group. It gives the biggest speed-up on slow devices. Turn it off when a panel must show entities that its dashboards do not name. |
| **Extra entities** | Entities to keep streaming even though they aren't on the dashboards. |

### Change, rename or delete a group

Each group is a row below the entry **Lite Resources** on the integration's page.

- To change a group, select the cog icon (⚙) at the right of its row. The group's form opens. Change the options, and select **Submit**.
- To rename a group, select the three-dot menu (⋮) at the right of its row, then **Rename**. The form's field **Group name** does the same.
- To delete a group, select the three-dot menu (⋮) at the right of its row, then **Delete**. Its users then get Home Assistant's normal behaviour.

A change reaches the open panels at once. The integration needs no reload, and Home Assistant needs no restart.

### Update from 0.2.x

The update moves the users and the dashboards of a 0.2.x setup into one group named **Lite users**. On the integration's page, select the cog icon (⚙) at the right of that group, and give it a name. Then add the other groups with **Add group**. 0.2.x does not read the new configuration, so a return to 0.2.x needs the integration removed and added again.

### Check what a panel gets

1. Open **Developer tools → Actions**.
2. Enter `lite_resources.preview` in the field **Action**.
3. Select **Perform action**. The response shows below the button.

Only an administrator can perform this action, because the response names each user and each entity in the dashboards.

The response lists each group with its users. For each group it shows the resources that its users get and skip, and any `custom:` card types with no local resource. With state filtering on, it also shows the entities that they receive. More keys say what to look at:

- `states_not_narrowed` and `resources_not_reduced` give the reason when a group gets all states or the full resource list.
- `guessed_types` holds each card type that no file registers in a way that the scan sees. For such a type, a file is sent when it meets two conditions: it names the type in quotes, and it holds a registration that the scan cannot read. If the card still fails to load, add its resource under *Always include*.
- `excluded_without_element` holds each readable file in which the scan sees no element. Such a file is not sent. It is a file that works by a side effect, such as an icon set, or a card that the dashboards do not use. Add it under *Always include* when a panel needs it.
- `state_entities_without_state` holds each name in the dashboards that has no state now. A state subscription holds those names too: an entity whose first state comes later, or a name with an error in a card.

## FAQ

**Why isn't this built into Home Assistant?**
Home Assistant's frontend is designed so any screen can show anything instantly - search, more-info dialogs and templates can reach every entity without asking first. That's the right default for phones and desktops. Lite Resources is an opt-in trade-off for screens that only ever show one dashboard.

**Does it filter per device or per user?**
Per user. If you log in as a lite user on your phone, you get the lite behaviour there too - so give panels their own user.

**Can two sets of panels have different dashboards?**
Yes. Add one group for each set. Each group gets the resources and the states for its own dashboards.

**Something shows "unavailable" or a card fails to load on the panel.**
With state filtering on, entities not on the panel's dashboards aren't sent - add them under *Extra entities*, or add the dashboard. For a card that fails to load, run `lite_resources.preview` and add its resource under *Always include*. To stop a resource the panel never uses, add it under *Always exclude*.

**Does it affect voice assistants, automations, history or the companion app's sensors?**
No. Only the dashboard's resource list and the live state subscription are changed, and only for lite users. The integration knows a connection's user and not its program. So each program that signs in as a lite user and asks for all states gets only the entities on the dashboards. Give each panel a user of its own, and use that user for nothing else.

**An administrator is a lite user. What changes?**
The page **Settings → Dashboards → Resources** reads the same resource list, so it shows only the group's resources. Use another user to manage the resources.

**What happens if something goes wrong?**
If the work on the trimmed list fails with an error, or takes longer than 30 seconds, Lite Resources sends the full list and logs the reason. If the entity scan fails, a panel that connects gets all states, and an open panel keeps its entities. The section *When a group's states are not narrowed* says what comes next.

Some gaps give no error. A card type that no file seems to provide is in the log one time, and `lite_resources.preview` shows it. A resource can work by a side effect, such as an icon set or a mod that only a theme uses. Lite Resources does not send such a resource until you add it under *Always include*.

## Contributing

Issues and pull requests are welcome. Please include your Home Assistant version and the output of `lite_resources.preview`.

Before each commit, run each validation with one command:

```bash
python scripts/validate.py
```

The script runs the unit tests, the static checks, both type checks and hassfest, and it has no option that leaves a check out. It exits with 1 when a check fails or cannot run. The comment at the top of [scripts/validate.py](scripts/validate.py) names the two environment variables that it reads.

hassfest is Home Assistant's own validation of an integration's manifest, translations and services. It has no release as a package, so the script runs the container image of the GitHub action `home-assistant/actions/hassfest`, on this machine or on a host that it reaches with `ssh`. The image is named by its digest, and the container gets no network and no volume. The script also fails for a warning of hassfest, which hassfest itself lets pass.

To make git refuse a commit that fails a check, add a `pre-commit` hook to your clone that runs `python scripts/validate.py --tree-is-the-commit`. With that option, the script first refuses a working tree that holds more than the commit.

The HACS action reads the repository on GitHub, so it has no local run. The unit tests cover its three checks of files: the brand icon, `hacs.json` and this README.

These are the checks of the script apart from hassfest, as single commands from the root of the repository:

```bash
python -m unittest discover -s tests
ruff check .
ruff format --check .
mypy
```

The tests need Python 3.12 or later and the package `voluptuous`. They run against stand-ins, so they need no Home Assistant installation. The static checks and the format check need ruff 0.17.5, and the type checks need mypy 2.4.1. Those are the versions that the Validate workflow installs. `ruff.toml` and `mypy.ini` hold the settings. To give changed code the format, run `ruff format .`.

The command `mypy` reads no Home Assistant, so its result is the same on each machine. It checks the calls inside the integration, and each name from Home Assistant has the type `Any` there. A second type check reads the types of Home Assistant from the source of its core. It needs a clone of that source at the tag of your Home Assistant version, and it runs nothing of it:

```bash
git clone --depth 1 --branch 2026.11.2 https://github.com/home-assistant/core ../home-assistant-core
MYPYPATH=../home-assistant-core mypy --config-file mypy-homeassistant.ini
```

On Windows, set `MYPYPATH` with your shell's syntax. The Validate workflow runs both type checks.

## Releasing

Create the GitHub release after the Validate workflow on that commit has succeeded.

1. Set `version` in `custom_components/lite_resources/manifest.json` to the new version, and add that version to `CHANGELOG.md`.
2. Merge the change to `main`.
3. Wait until the Validate workflow on that commit succeeds. The hassfest job and the HACS job both have to pass. `.github/workflows/validate.yaml` does not set `ignore`.
4. Create a GitHub release of that commit. Name it `v` plus the manifest version (for example `v0.2.0`; the release history includes `v0.1.2`) and target `main`.

A submission to the HACS default repository asks for that release to be created after those actions have succeeded, and for links to the release and to the successful runs. v0.1.1 was published at 2026-11-07 11:39:18 GMT. Validate run [42369085242](https://github.com/evski/ha-lite-resources/actions/runs/42369085242) on the same commit finished hassfest at 11:39:40 GMT and HACS validation at 11:39:57 GMT.

## License

[MIT](LICENSE)
