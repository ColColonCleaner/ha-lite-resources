# Changelog

## Unreleased

## 0.3.0 - 2026-11-23

- **Groups of light users.** Each group has its own users, dashboards and options. So the panels of one room and a tablet of another room each get the resources and the states of their own dashboards. Add a group with **Add group** on the integration page, and change one with its reconfigure button. A user can be in one group only.
- The update moves the users and dashboards of a single-group setup into one group named **Light users**. You enter nothing again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
- **A changed dashboard reaches the open panels at once.** When you save a dashboard of a group, each open page of the group gets the states of the entities that are new on the dashboard. It loses the entities that left the dashboard. No reload of the integration is necessary. A change of a group does the same.
- A card type that is new on a dashboard loads on a panel at the next page load of that panel. The frontend loads its resources one time for each page load.
- **Always include** and **Always exclude** are optional overrides, and the form says so. The resources of a group come from its dashboards.
- A camera of the Advanced Camera Card with `live_provider: webrtc-card` keeps the script of the WebRTC Camera integration, `webrtc-camera.js`. No card type in the dashboard names that script.
- `lite_resources.preview` lists each group with its users, and the number of open pages with narrowed states.
- Needs Home Assistant 2026.11 or later. The checks of the groups ran on 2026.11.2.

## 0.2.1 - 2026-11-16

- Card names built in JavaScript are recognised. Mushroom's `mushroom.js` is loaded for `custom:mushroom-*-card` on the selected dashboards, including cards nested in stacks, sections, conditional cards and pop-ups.
- A resource is matched by its whole file name. `dreame-vacuum-card.js` is not sent for a Mushroom vacuum card, and `lock-manager.js` is not sent for a Mushroom lock card. Mentioning another card's name inside a file does not load that file.
- A file named after a card the selected dashboards don't use is no longer sent just because its contents could not be read. Scripts with a generic name, such as `/browser_mod.js`, are unchanged.
- Every dashboard selected in the integration is scanned, including one that nothing links to.
- New option **Always exclude**: resources light users never load, including an integration script whose file name is not the card name. It wins over **Always include**.

## 0.2.0
- New option **Only send states their dashboards show**: light users' live state subscription is narrowed to entities on their dashboards (cards, pop-ups, conditions, actions), group members and **Extra entities**. On a Sonoff NSPanel Pro this cut 2,955 streamed entities to 89.
- `lite_resources.preview` also lists the entities light users receive.
- README rewritten: who it's for (wall panels, View Assist / VACA, the F-Droid Home Assistant app), screenshots, install buttons, FAQ. Issue templates.

## 0.1.2

Records the release order for this patch. Resource filtering is unchanged.

Publish the GitHub release for 0.1.2 after the Validate workflow on this commit succeeds. v0.1.1 was published at 2026-11-07 11:39:18 GMT, before hassfest (11:39:40 GMT) and HACS validation (11:39:57 GMT) finished on that commit.

## 0.1.1

Adds the integration icon used by the HACS brands check.

## 0.1.0

First release. Chosen users receive the dashboard resources their dashboards use. "Always include" matches resources by path, ignoring the version query string.
