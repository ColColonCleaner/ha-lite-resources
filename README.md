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

One more need has no card type. A camera of the Advanced Camera Card with `live_provider: webrtc-card` needs the script of the WebRTC Camera integration. Lite Resources keeps that script when a dashboard holds this value.

Some cards name no entity, and find their entities by themselves. Lite Resources sends those entities too:

- The **area card** shows the camera, the sensors, the alerts and the controls of its area. Lite users get the entities of that area that the card can show.
- The **scheduler card** shows the schedules of the scheduler integration. Lite users get each schedule, and the entities that it controls.

For another card of this kind, add its entities under *Extra entities*.

Everyone else gets Home Assistant's normal behaviour. Remove the integration and everything is exactly as before.

## Groups

A group holds the users that one set of panels logs in as, and the dashboards that those panels show. Each group gets the resources and the states of its own dashboards. For example, the kiosks of a workshop are one group, and a kitchen tablet is a second group with another dashboard. A user can be in one group only.

You do not list the resources of a group. Lite Resources finds them from the dashboards of the group at each page load. It finds the entities at each connection of a panel.

### When a dashboard changes

Design the dashboards as a normal user, with every resource loaded. When you save a dashboard of a group, these things occur with no reload of the integration:

- Home Assistant sends the new dashboard to each open panel. This is its standard behaviour.
- Lite Resources finds the entities of the group again. Each open panel of the group gets the states of the new entities at once, and loses the entities that left the dashboards.
- A card type that is new on the dashboards loads on a panel at the next page load of that panel. The frontend loads its resources one time for each page load, so that card shows an error on the panel until then.

A change of a group, such as a new user or a new dashboard, reaches the open panels the same way.

## Install

Lite Resources needs Home Assistant 2026.11 or later.

### Marketplace (recommended)

The Marketplace is the successor of HACS in Home Assistant 2026.11.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ColColonCleaner&repository=ha-lite-resources&category=integration)

Or do these steps:

1. Open **Settings → Marketplace**.
2. Select **Add from link** in the upper-right corner.
3. Under **GitHub link**, enter `https://github.com/ColColonCleaner/ha-lite-resources`, and select **Add**. If the Marketplace asks you to connect GitHub, do that first.
4. Select **Lite Resources** in the list to open its page. Select **Install**, and **Install** again in the dialog.
5. Restart Home Assistant. A repair under **Settings → System → Repairs** asks for the restart and can do it.

If the Marketplace holds `evski/ha-lite-resources`, uninstall that repository first, because both repositories install the same integration folder. Open the page of that repository in the Marketplace. Select the three-dot menu (⋮) in the upper-right corner, then **Uninstall**, then **Delete and uninstall**. That also deletes its setup.

To update later, open the page of the repository in the Marketplace and install the new version, then restart Home Assistant.

### Manual

Copy `custom_components/lite_resources` into your `config/custom_components/` folder and restart Home Assistant.

## Set up

[![Open your Home Assistant instance and start setting up Lite Resources.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=lite_resources)

Or do these steps:

1. Open **Settings → Devices & services**, and select **Add integration**.
2. Search for **Lite Resources** and select it. The dialog has no settings, so select **Submit**.
3. Open the page of the integration: **Settings → Devices & services → Lite Resources**. The page shows the entry **Lite Resources**.
4. Select **Add group**. It is in two places on that page: the button in the upper-right corner, and the three-dot menu (⋮) at the right of the entry **Lite Resources**.
5. Fill in the form with the options of the table below, and select **Submit**. The group then shows as a row below the entry.
6. Do steps 4 and 5 again for each other set of panels.
7. Reload the browser or the app of each panel.

<p align="center">
  <img src="docs/images/integration-page.png" width="720" alt="The page of the integration. Add group is the button in the upper-right corner and an item of the three-dot menu of the entry. Each group is a row with a cog icon.">
  <br><em>The page of the integration with two groups. The three-dot menu of the entry is open.</em>
</p>

| Option | What to choose |
|---|---|
| **Group name** | A name for the set of panels, such as *Workshop kiosks*. |
| **Lite users** | The user(s) your panels log in as. Give each panel its own Home Assistant user if it doesn't have one. |
| **Their dashboards** | Every dashboard those users open. |
| **Always include** | Optional. Leave it empty, because the resources come from the dashboards. Add a resource only if a card fails to load (e.g. a mod your theme relies on). |
| **Always exclude** | Resources to never load, even if a card seems to need them. Use this for an integration script with a generic name, such as `/dreame_vacuum/frontend.js`, that these dashboards don't use. It wins over *Always include*. |
| **Include resources that can't be checked** | Resources served by integrations (e.g. `/browser_mod.js`, `/webrtc/...`) can't be read. On = load them (safe default). Off = skip them unless listed under *Always include*. A file whose name is a card these dashboards don't use, such as `dreame-vacuum-card.js`, is skipped either way. |
| **Only send states their dashboards show** | Turn on for the biggest speed-up on slow devices. |
| **Extra entities** | Entities to keep streaming even though they aren't on the dashboards. |

### Change, rename or delete a group

Each group is a row below the entry **Lite Resources** on the page of the integration.

- To change a group, select the cog icon (⚙) at the right of its row. The form of the group opens. Change the options, and select **Submit**.
- To rename a group, select the three-dot menu (⋮) at the right of its row, then **Rename**. The field **Group name** of the form does the same.
- To delete a group, select the three-dot menu (⋮) at the right of its row, then **Delete**. Its users then get the normal behaviour of Home Assistant.

A change reaches the open panels at once. No reload of the integration and no restart is necessary.

### Update from 0.2.x

The update moves the users and dashboards of a 0.2.x setup into one group named **Lite users**. On the page of the integration, select the cog icon (⚙) at the right of that group, and give it a name. Then add the other groups with **Add group**. 0.2.x does not read the new configuration, so a return to 0.2.x needs the integration removed and added again.

### Check what a panel gets

1. Open **Developer tools → Actions**.
2. Enter `lite_resources.preview` in the field **Action**.
3. Select **Perform action**. The response shows below the button.

The response lists each group with its users. For each group it shows the resources that its users get and skip, and any `custom:` card types with no local resource. With state filtering on, it also shows the entities that they receive.

## FAQ

**Why isn't this built into Home Assistant?**
Home Assistant's frontend is designed so any screen can show anything instantly - search, more-info dialogs and templates can reach every entity without asking first. That's the right default for phones and desktops. Lite Resources is an opt-in trade-off for screens that only ever show one dashboard.

**Does it filter per device or per user?**
Per user. If you log in as a lite user on your phone, you get the lite behaviour there too - so give panels their own user.

**Can two sets of panels have different dashboards?**
Yes. Add one group for each set. Each group gets the resources and the states of its own dashboards.

**Something shows "unavailable" or a card fails to load on the panel.**
With state filtering on, entities not on the panel's dashboards aren't sent - add them under *Extra entities*, or add the dashboard. For a card that fails to load, run `lite_resources.preview` and add its resource under *Always include*. To stop a resource the panel never uses, add it under *Always exclude*.

**Does it affect voice assistants, automations, history or the companion app's sensors?**
No. Only the dashboard's resource list and its live state subscription are changed, and only for lite users.

**What happens if something goes wrong?**
If working out the trimmed list fails for any reason, the full list is sent and an error is logged - a panel is never left without its cards.

## Contributing

Issues and pull requests are welcome. Please include your Home Assistant version and the output of `lite_resources.preview`.

## Releasing

Create the GitHub release after the Validate workflow on that commit has succeeded.

1. Set `version` in `custom_components/lite_resources/manifest.json` to the new version, and add that version to `CHANGELOG.md`.
2. Merge the change to `main`.
3. Wait until the Validate workflow on that commit succeeds. The hassfest job and the HACS job both have to pass. `.github/workflows/validate.yaml` does not set `ignore`.
4. Create a GitHub release of that commit. Name it `v` plus the manifest version (for example `v0.2.0`; the release history includes `v0.1.2`) and target `main`.

A submission to the HACS default repository asks for that release to be created after those actions have succeeded, and for links to the release and to the successful runs. v0.1.1 was published at 2026-11-07 11:39:18 GMT. Validate run [42369085242](https://github.com/evski/ha-lite-resources/actions/runs/42369085242) on the same commit finished hassfest at 11:39:40 GMT and HACS validation at 11:39:57 GMT.

## License

[MIT](LICENSE)
