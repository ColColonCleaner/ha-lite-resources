# Changelog

## Unreleased

## 0.3.7 - 2026-11-24

- **The fork's texts use the possessive form.** The README, this changelog from 0.3.0 on, the form texts, the log messages and the code comments now say `a group's dashboards` and not `the dashboards of a group`. The word `of` stays for a part, an amount, the contents, an action before its object, and an owner with a clause after it.
- No behaviour changed. Some log messages have new words, and two of them are now two sentences with no semicolon.
- The upstream author's paragraphs in the README, and the entries up to 0.2.1, keep their wording.

## 0.3.6 - 2026-11-23

A second independent review covered the whole code at 0.3.5. It gave 35 findings: no critical one, 1 high, 6 medium and 28 low. 24 of them are in code that 0.3.5 added. This version corrects each fault that the review confirmed, and it states each limit that stays. Three findings did not hold against Home Assistant 2026.11.2's source, and the end of this entry names them.

### 0.3.5's rules that stopped the narrowing too often

- **A card feature with a like name no longer stops its group's narrowing. (high)** 0.3.5 took each `type` that starts with `energy-`, `water-`, `power-` or `gas-` as an energy settings card, in each mapping of a dashboard. A tile card's feature `water-heater-operation-modes` is none of these, and one such feature gave all states to each panel in the group. The rule now holds the frontend's exact card and badge types, and it reads no type inside a card's features.
- **The key `strategy` counts only where the frontend reads it.** 0.3.5 took that key in each mapping as a strategy, also as a custom card's option or in an action's data. It now counts at the dashboard, at a view and at a section.
- **A dashboard that cannot be loaded is left out.** 0.3.5 took each load error as a dashboard with no stored configuration, so one YAML dashboard with a syntax error stopped its group's narrowing. Only a dashboard with no stored configuration does that now. Another load error leaves the dashboard out, with one warning that gives the error.

### An open page's state stream

- **A task that still waits at the unload changes no page.** The unload returned each page to all states. The old setup's task that waited on a scan then narrowed the page again, into a table that nothing updated. After a removal the page stayed narrowed. After a reload the new setup did not find it. The unload now sets a flag, and that setup's tasks and handlers read it after each wait.
- **An unloaded setup's handler passes each message on.** When another integration keeps this integration's handler and calls it after the unload, the handler now gives the message to Home Assistant's handler.
- **An update event that the scan itself causes starts no new scan.** A YAML dashboard's load can fire that dashboard's update event. For a file that Home Assistant does not cache, such as an empty file or a file with a time in the future, each scan fired an event and each event started a scan, with no end. An event that comes while this integration's scan loads that dashboard is now left out.
- **Many events close together give one more update.** Each dashboard save started its own update, and 20 saves gave 20 scans. An update that runs now takes each later request with it.
- **A new page waits for an update that runs.** A page's first subscription ran apart from the open pages' updates, so a page that started during a save could keep the older entity set.
- **One entity scan has a time limit of 30 seconds.** The open pages' changes run one after the other. A dashboard load with no end, such as a YAML file on a dead share, held each later change.
- **A client that ends its subscription during the scan gets its command's result.** Before, that command got no answer.
- **An adoption's removal list holds only entities that the user can read.** It held each entity in Home Assistant, so a user with a narrow policy learned the names that the policy hides.
- **A page is in the open pages table before its removal message goes out.** If that message failed, it could leave a narrowed listener that the table did not know.
- **The log names each state listener that the adoption cannot read.** 0.3.5's check saw two layout changes only. The search now accepts only the exact five arguments that it knows, and it counts each listener that holds Home Assistant's function with another layout. The log holds one warning with that count.
- **The log names a page that keeps its narrowed states at the unload**, when the return to all states fails for it.

### The entities and the resources

- **A device tracker's tile card gets each zone**, as a person's tile card does.
- **`custom:` in plain text is no card.** 0.3.5 took each `custom:name` inside a longer string as one of the dashboard's cards, also in a markdown card's text. It now needs the key `type` before it, as in a template that returns a card.
- **A key that ends in `type` is no registration.** The file scan took `layout_type:"grid-layout"` as a registration of `grid-layout`. That false provider was sent, and it stopped the search for the type's real file.
- **The guess for a type with no provider takes fewer files.** It took each file that names the type in quotes. It now takes only a file with a registration that the scan cannot read, such as the call inside a minified decorator. A file whose registrations all have a quoted name registers no other element.
- **That guess finds a name of two quoted pieces in a helper call.** 0.3.5 dropped such a pair outside a registration and an assignment, so a bundle that registers `"my"+"-card"` through a helper lost its card.
- **A name of three quoted pieces gives no wrong name.** The scan joined the first two pieces.
- **The preview lists each file with no element, whatever its name is.** 0.3.5 left out each file with a hyphen or with six or more characters in its name, so an icon set such as `custom-brand-icons.js` did not show. The list now holds also a card that the dashboards do not use and whose registration the scan cannot see.
- **The preview lists the names with no state.** A state subscription holds each name in the dashboards, also one with no state now. The preview showed only the entities with a state. The new key `state_entities_without_state` holds the rest.

### The form and the tests

- A stored user that is not active shows its name with `(not active)` in a group's form. 0.3.5 showed its ID with `(user not found)`.
- **The tests' stand-ins take Home Assistant's order and defaults.** The unload callbacks run from the last one to the first, a task starts eagerly by default, and the stand-in for the administrator check refuses a user that is no administrator and passes the answer on. The stand-in for a select field refuses a value outside its options.
- New tests cover the group form's two steps, the resource handler's three paths that give the full list or a warning, a narrowed call that fails while the call for all states works, a subscription with a filter, and each correction in this version. The tests grow from 180 to 207.

### Findings that did not hold

- The preview action returns its answer through Home Assistant's administrator wrapper: `_async_admin_handler` returns the function's answer.
- A new group and a deleted group call the entry's update listener: `async_add_subentry` and `async_remove_subentry` both end in `_async_save_and_notify`.
- Home Assistant refuses an entry with a higher version than the flow knows before it calls the migration.

### Limits that stay

- **A group that the integration can no longer narrow gets all states on each open panel.** A dashboard save can add a strategy, a home-summary card or an energy card. Each of the group's open panels then gets all states in one message, about 1.4 MB for 5,573 entities. Each panel also gets each state change after that. The log holds one warning with the reason. An unload and a reload send the same message one time.
- **A custom strategy that makes custom cards** names no card in the stored dashboard. Add each such card's resource under **Always include**.
- **Each of a short name's values joins each template with that name.** A minified bundle can then seem to provide a card that it does not hold, and a panel loads it for nothing. No real bundle showed this.
- **Cost.** Each state subscription runs a scan of about 20 ms to 40 ms for 5,573 entities. Panels that connect together share no result. A change to one entity sends its whole set again to each of the group's open panels.
- The three checks against the real package do not cover the handler for `subscribe_entities` as a whole. They also do not cover a user that is no administrator, a state change through a new listener, or an entry's setup. The test on a running Home Assistant covers those.

## 0.3.5 - 2026-11-23

An independent review of the whole code gave 51 findings: 1 critical, 1 high, 5 medium and 44 low. This version corrects each fault that it confirmed, and it states each limit that stays. Each point is in the list below.

A second review found faults in this version, and 0.3.6 corrects them. The largest one: three new rules stopped a group's narrowing too often, so install 0.3.6 and not this version.

### An open page's state stream

- **0.3.4's adoption could leave each panel with no state stream after a restart.** The adoption made its own message for Home Assistant's handler, and that message did not pass the command's schema. The handler reads the keys `include` and `exclude`, which only the schema adds, so it failed with `KeyError`. The adoption ended the page's state listener before that call. 0.3.4's first code then left the page with no listener, and its later correction sent the same message again and failed again. Each message that the integration makes now passes the schema first. The review found the fault before 0.3.4's first known install.
- **A change to an open subscription starts the new listener before it ends the old one.** If the handler fails, the old listener goes back into its place, and the page keeps the entities that it had. Versions 0.3.0 to 0.3.4 ended the old listener first. This holds for a new entity set, for an adoption, and for the return to all states, which had no guard at all.
- **The integration's unload or removal gives each open page all states again.** Before, such a page kept its narrowed set until it connected again, against the README text that all is as before after a removal.
- **The integration's reload no longer loses the open pages.** Before, the new setup did not know the pages that the old setup narrowed. A saved dashboard, a changed group and a deleted group then changed nothing for them. The unload now returns each page to all states, and the new setup narrows it again.
- **A connection that closes during the entity scan gets no listener.** The scan can wait, such as at a dashboard's first load or for a YAML dashboard. A page that left in that time got a state listener and a place in the open pages table, and nothing ended them. The handler now puts a stand-in into the connection's subscriptions, which Home Assistant removes at a close.
- **Two changes at one time leave the newer entity set.** Two dashboard saves close together could leave a page with the older set. The open pages' changes now run one after the other.
- **A new page gets all states, or an error message, when the handler fails.** Before, a failure inside a narrowed subscription's task sent the page no result and no error, and the page waited with no end. The page now gets the subscription for all states. If that fails too, the page gets the error message that Home Assistant sends for a failed handler.
- **A failed entity scan leaves each open page as it is, and a failure for one page no longer stops the next pages' update.** Before, an error for one page ended each later page's update, and the adoption after a group change did not run.
- **The log says when Home Assistant has another layout than the adoption expects.** The search for early subscriptions reads the event bus's listener table and the function `_forward_entity_changes`. On a version without them the search found nothing and the log held nothing. The setup now logs one warning. The search also catches each kind of error at the read, and it takes that function only from the Home Assistant module that defines it.
- **The update at the end of the start no longer depends on `hass.is_running`.** That property is true also while Home Assistant starts, so a setup in that time added no listener. The setup now uses `async_at_started`.
- **An unload keeps a handler that another integration registered after this one.** Before, the unload wrote Home Assistant's two handlers back, whatever the table held.
- **A change to the entity, device or area registry updates the open pages.** A new schedule, an entity that moves into an area card's area, and an entity that is no longer hidden now reach an open page. The registries change in bursts, so one update follows 10 seconds after the first change.

### A group's entities

- **A dashboard with no stored configuration no longer gives a page two entities. (high)** Home Assistant generates such a dashboard in the browser, such as the default dashboard before its first edit. The scan read it as an empty dashboard, so a panel got only `sun.sun` and `zone.home`, with no line in the log. Such a group's states are now not narrowed, and the log says why one time. The same holds when none of the group's dashboards exists. A deleted dashboard beside a stored one is left out, with one warning.
- **A strategy stops its group's narrowing.** A dashboard, a view or a section with a strategy holds no card: the browser makes them. Such a page got no entity for those cards. The scan also read the area view strategy as an area card.
- **Core cards that find their entities by themselves.** The `home-summary` card and the energy, water, power and gas cards and badges take their entities from all states or from the energy settings, so a group with one of them is not narrowed. A `map` card with `show_all` gets each person, device tracker and zone, and with `geo_location_sources` each geo location entity. The `updates` card gets each update entity. A person's tile card, and a visibility condition on the user's location, get each zone.
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
- **Two quoted pieces with a plus count only in a registration or in an assignment to a variable.** Before, each such pair in a file counted as one of the file's elements, such as a CSS class name.
- **A config folder path that is not in the system's normal form refused each local file.** The test that keeps a resource path inside the `www` folder compared a normal path with one that was not. Both now have the normal form.
- **The preview lists the files with no element.** A resource that works by a side effect, such as an icon set, provides no card type, so it is not sent. `lite_resources.preview` now lists each readable file with no element and no card's file name under `excluded_without_element`. Add such a file under **Always include** when a panel needs it.

### The form, the action and the checks

- **`lite_resources.preview` is for administrators.** Before, each signed-in user could call it, and it names each group, each user, each dashboard and each entity in the dashboards. The preview now also says why a group's states or resources are not narrowed.
- **A group's form keeps a stored value that is no option any more.** A select field refuses a value outside its options. A group with a deleted user, a deleted dashboard or an older version's resource URL could not be saved until that value was removed, and the error did not name it.
- **The form shows a stored group's state filter as it is.** For a group with no stored value the form showed the filter as on, and such a group does not filter. A plain submit then turned the filter on. The update from a single-group version now also writes the filter as off when that version did not hold the option.
- **A user in two groups is in the log.** Two forms that are open at one time can each add the same user. The first group in the list counts, and the log now says so.
- A group has a hash. Before, `hash(Group)` raised an error, because the options are a dict.
- A group's text `reconfigure_successful` is gone. Home Assistant shows its own text after a change to a group.
- **The tests' stand-ins fail as Home Assistant does.** The stand-in for Home Assistant's handler accepted each message, so 18 adoption tests passed with 0.3.4's fault. It now reads `include` and `exclude` with no default, and the stand-in for the filter does the same. The harness runs an eager task as Home Assistant does, and it can make the entity scan wait and close a connection. New tests cover the group form, the paths that give a panel the full list or all states, a resource URL's path test, a `.gz` copy and the file cache. The tests grow from 105 to 180.
- The check against Home Assistant 2026.11.2's real package now calls the handler exactly as the integration does. The earlier check passed each message through the schema itself, so it did not show the fault.
- The Validate workflow runs the unit tests.

### Limits that stay

- **Member lists.** A light group's new member, and a new entity that a schedule controls, reach an open page at its next load, at its dashboard's next save, or at a registry's next change.
- **Each of a lite user's clients is narrowed.** The integration knows a connection's user and not its program. A companion app or a script that signs in as a lite user and asks for all states gets the dashboards' entities only.
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
- The search for those subscriptions reads Home Assistant 2026.11's internals: the event bus's listener list. On a version with another layout it finds nothing, and a panel then gets its narrowed stream at its next connection, as before. The search takes the listener function only from the Home Assistant module that defines it.
- A second commit of this version, `57bf290`, tried to give a page the stream of all entities again when its narrowed subscription failed.
- **This version has a critical fault, and 0.3.5 replaces it. Do not install 0.3.4.** The adoption gave Home Assistant's handler a message that did not pass the command's schema, so the handler failed after the adoption ended the page's listener. Each adopted panel then had no state stream until it connected again. `57bf290`'s return to all entities sent the same message, so it failed in the same way. Two commits carry this version number: `ce1fba9` and `57bf290`.

## 0.3.3 - 2026-11-23

- **The instructions say where each action is.** The README gives each step of the install and of the setup. **Add group** is the button in the upper-right corner of the integration's page, and an item in the entry's three-dot menu. A group's cog icon changes it, and a group's three-dot menu renames or deletes it. A picture shows that page.
- The setup dialog and a group's dialog name the same places.
- The README no longer gives a button as a replacement for a list of steps. The setup button is a second way to do the first step only. The install section gives its steps with no button, because nobody checked that the button opens a repository that the catalog does not list.

## 0.3.2 - 2026-11-23

- **A page that connects while Home Assistant starts gets each of its entities.** Many entities get their first state some seconds after the start. A page that connected before that time never received them, and its cards showed no camera or no value until the page connected again. A lite user's state subscription now holds also each entity name with no state yet, so each one arrives with its first state. The registry gives such an entity's domain and device class.
- When Home Assistant's start is complete, each of a lite user's open pages gets its entity set again. A group entity names its members only after its integration loads.
- **The texts say lite users.** The word `light` now names only a lamp. The group that the update makes from a single-group setup has the name **Lite users**.

## 0.3.1 - 2026-11-23

- **The area card gets its area's entities.** An area card names an area and no entity. It finds its camera, its sensors, its alerts and its controls in the registries. Lite users now receive those entities, by the card's rules: the entity is in the area, it is not hidden, and it has no entity category. Before this version, such a card showed no light button, no temperature and no motion alert for a lite user.
- **The scheduler card gets its schedules.** Each schedule is one of the scheduler integration's switches, and the card shows an empty row for a schedule with no state. Lite users now receive those switches, and the entities that each schedule controls.
- An entity with no area of its own has its device's area, and a child device with no area has its parent device's area. The area card follows that rule, so the search for its entities does too.
- An area can name one entity for its temperature and one for its humidity. An area card shows that entity also when it belongs to another area, so lite users receive it.
- An entity's device class comes from its state, which is the value that the area card filters on.

## 0.3.0 - 2026-11-23

- **Groups of lite users.** Each group has its own users, dashboards and options. So one room's panels and another room's tablet each get their own dashboards' resources and states. Add a group with **Add group** on the integration page, and change one with its reconfigure button. A user can be in one group only.
- The update moves a single-group setup's users and dashboards into one group named **Lite users**. Versions 0.3.0 and 0.3.1 gave it the name **Light users**. You enter nothing again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
- **A changed dashboard reaches the open panels at once.** When you save one of a group's dashboards, each of the group's open pages gets each entity that is new on the dashboard, with its state. It loses the entities that left the dashboard. The integration needs no reload. A change to a group does the same.
- A card type that is new on a dashboard loads on a panel at that panel's next page load. The frontend loads its resources one time for each page load.
- **Always include** and **Always exclude** are optional overrides, and the form says so. A group's resources come from its dashboards.
- An Advanced Camera Card camera with `live_provider: webrtc-card` keeps the WebRTC Camera integration's script, `webrtc-camera.js`. No card type in the dashboard names that script.
- `lite_resources.preview` lists each group with its users, and the number of open pages with narrowed states.
- An update event that names no dashboard, such as a change to the resource list, updates no page. Such an event has no URL path, and the default dashboard has the URL path `None`, so the two are kept apart.
- The manifest and the README name this fork, `ColColonCleaner/ha-lite-resources`, for the documentation, the issue tracker and the install. The README says that the repository is a fork of `evski/ha-lite-resources`, and it gives the install through Home Assistant 2026.11's Marketplace.
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
