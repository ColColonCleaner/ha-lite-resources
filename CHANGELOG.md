# Changelog

## Unreleased

## 0.3.3 - 2026-11-23

- **The instructions say where each action is.** The README gives each step of the install and of the setup. **Add group** is the button in the upper-right corner of the page of the integration, and an item of the three-dot menu of the entry. The cog icon of a group changes it, and the three-dot menu of a group renames or deletes it. A picture shows that page.
- The setup dialog and the dialog of a group name the same places.
- The README no longer gives a button as a replacement of a list of steps. The setup button is a second way to do the first step only. The install section gives its steps with no button, because nobody checked that the button opens a repository that the catalog does not list.

## 0.3.2 - 2026-11-23

- **A page that connects while Home Assistant starts gets each of its entities.** Many entities get their first state some seconds after the start. A page that connected before that time never received them, and its cards showed no camera or no value until the page connected again. The state subscription of a lite user now holds also the names of entities with no state yet, so each one arrives with its first state. The registry gives the domain and the device class of such an entity.
- When the start of Home Assistant is complete, each open page of a lite user gets its entity set again. A group entity names its members only after its integration loads.
- **The texts say lite users.** The word `light` now names only a lamp. The group that the update makes from a single-group setup has the name **Lite users**.

## 0.3.1 - 2026-11-23

- **The area card gets the entities of its area.** An area card names an area and no entity. It finds its camera, its sensors, its alerts and its controls in the registries. Lite users now receive those entities, by the rules of the card: the entity is in the area, it is not hidden, and it has no entity category. Before this version, such a card showed no light button, no temperature and no motion alert for a lite user.
- **The scheduler card gets its schedules.** Each schedule is a switch of the scheduler integration, and the card shows an empty row for a schedule with no state. Lite users now receive those switches, and the entities that each schedule controls.

## 0.3.0 - 2026-11-23

- **Groups of lite users.** Each group has its own users, dashboards and options. So the panels of one room and a tablet of another room each get the resources and the states of their own dashboards. Add a group with **Add group** on the integration page, and change one with its reconfigure button. A user can be in one group only.
- The update moves the users and dashboards of a single-group setup into one group named **Lite users**. Versions 0.3.0 and 0.3.1 gave it the name **Light users**. You enter nothing again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
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
