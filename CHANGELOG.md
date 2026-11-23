# Changelog

## Unreleased

## 0.3.6 - 2026-11-23

A second independent review, of the whole code at 0.3.5, gave 35 findings: no critical one, 1 high, 6 medium and 28 low. 24 of them are in code that 0.3.5 added. This version corrects each fault that the review confirmed, and it states each limit that stays. Three findings did not hold against the source of Home Assistant 2026.11.2, and they are named at the end.

### Rules of 0.3.5 that stopped the narrowing too often

- **A card feature with a like name no longer stops the narrowing of its group. (high)** 0.3.5 took each `type` that starts with `energy-`, `water-`, `power-` or `gas-` as a card of the energy settings, in each mapping of a dashboard. The feature `water-heater-operation-modes` of a tile card is none of these, and one such feature gave each panel of the group all states. The rule now holds the exact card and badge types of the frontend, and it reads no type inside the features of a card.
- **The key `strategy` counts only where the frontend reads it.** 0.3.5 took that key in each mapping as a strategy, also as the option of a custom card or in the data of an action. It now counts at the dashboard, at a view and at a section.
- **A dashboard that cannot be loaded is left out.** 0.3.5 took each load error as a dashboard with no stored configuration, so one YAML dashboard with a syntax error stopped the narrowing of its group. Only a dashboard with no stored configuration does that now. Another load error leaves the dashboard out, with one warning that gives the error.

### The state stream of an open page

- **A task that still waits at the unload changes no page.** The unload returned each page to all states, and a task of the old setup that waited on a scan then narrowed the page again, into a table that nothing updated. After a removal the page stayed narrowed. After a reload the new setup did not find it. The unload now sets a flag, and each task and each handler of that setup reads it after each wait.
- **A handler of an unloaded setup passes each message on.** When another integration keeps the handler of this one and calls it after the unload, the handler now gives the message to the handler of Home Assistant.
- **An update event that the scan itself causes starts no new scan.** The load of a YAML dashboard can fire the update event of that dashboard. For a file that Home Assistant does not cache, such as an empty file or a file with a time in the future, each scan fired an event and each event started a scan, with no end. An event that comes while a scan of this integration loads that dashboard is now left out.
- **Many events close together give one more update.** Each save of a dashboard started its own update, and 20 saves gave 20 scans. An update that runs now takes each later request with it.
- **A new page waits for an update that runs.** The first subscription of a page ran apart from the updates of the open pages, so a page that started during a save could keep the older entity set.
- **One entity scan has a time limit of 30 seconds.** The changes of the open pages run one after the other. A dashboard load with no end, such as a YAML file on a dead share, held each later change.
- **A client that ends its subscription during the scan gets the result of its command.** Before, that command got no answer.
- **The removal list of an adoption holds only entities that the user can read.** It held each entity of Home Assistant, so a user with a narrow policy learned the name of each entity that the policy hides.
- **A page is in the table of open pages before its removal message goes out.** A failure of that message could leave a narrowed listener that the table did not know.
- **The log names each state listener that the adoption cannot read.** The check of 0.3.5 saw two layout changes only. The search now accepts only the exact five arguments that it knows, and it counts each listener of the function of Home Assistant with another layout. The log holds one warning with that count.
- **The log names a page that keeps its narrowed states at the unload**, when the return to all states fails for it.

### The entities and the resources

- **A tile card of a device tracker gets each zone**, as a tile card of a person does.
- **`custom:` in plain text is no card.** 0.3.5 took each `custom:name` inside a longer string as a card of the dashboard, also in the text of a markdown card. It now needs the key `type` before it, as in a template that returns a card.
- **A key that ends in `type` is no registration.** The scan of a file took `layout_type:"grid-layout"` as a registration of `grid-layout`. That false provider was sent, and it stopped the search for the real file of a type.
- **The guess for a type with no provider takes fewer files.** It took each file that names the type in quotes. It now takes only a file with a registration that the scan cannot read, such as the call inside a minified decorator. A file whose registrations all have a quoted name registers no other element.
- **A name of two quoted pieces in a helper call is found by that guess.** 0.3.5 dropped such a pair outside a registration and an assignment, so a bundle that registers `"my"+"-card"` through a helper lost its card.
- **A name of three quoted pieces gives no wrong name.** The scan joined the first two pieces.
- **The preview lists each file with no element, whatever its name is.** 0.3.5 left out each file with a hyphen or with six or more characters in its name, so an icon set such as `custom-brand-icons.js` did not show. The list now holds also a card that the dashboards do not use and whose registration the scan cannot see.
- **The preview lists the names with no state.** A state subscription holds each name of the dashboards, also one with no state now. The preview showed only the entities with a state. The new key `state_entities_without_state` holds the rest.

### The form and the tests

- A stored user that is not active shows its name with `(not active)` in the form of a group. 0.3.5 showed its ID with `(user not found)`.
- **The stand-ins of the tests take the order and the defaults of Home Assistant.** The unload callbacks run from the last one to the first, a task starts eagerly by default, and the stand-in for the administrator check refuses a user that is no administrator and passes the answer on. The stand-in for a select field refuses a value outside its options.
- New tests cover the two steps of the group form, the three paths of the resource handler that give the full list or a warning, a narrowed call that fails while the call for all states works, a subscription with a filter, and each correction of this version. The tests grow from 180 to 207.

### Findings that did not hold

- The preview action returns its answer through the administrator wrapper of Home Assistant: `_async_admin_handler` returns the answer of the function.
- A new group and a deleted group call the update listener of the entry: `async_add_subentry` and `async_remove_subentry` both end in `_async_save_and_notify`.
- Home Assistant refuses an entry with a higher version than the flow knows before it calls the migration.

### Limits that stay

- **A group that can no longer be narrowed gets all states on each open panel.** A save that adds a strategy, a home-summary card or an energy card to a dashboard gives each open panel of the group all states in one message, about 1.4 MB for 5,573 entities, and each state change after that. The log holds one warning with the reason. An unload and a reload send the same message one time.
- **A custom strategy that makes custom cards** names no card in the stored dashboard. Add the resource of each such card under **Always include**.
- **Each value of a short name joins each template with that name.** A minified bundle can then seem to provide a card that it does not hold, and it is sent for nothing. No real bundle showed this.
- **Cost.** Each state subscription runs a scan of about 20 ms to 40 ms for 5,573 entities, and no result is shared between panels that connect together. A change of one entity sends each open panel of the group its whole set again.
- The three checks against the real package do not cover the handler for `subscribe_entities` as a whole, a user that is no administrator, a state change through a new listener, or the setup of an entry. The test on a running Home Assistant covers those.

## 0.3.5 - 2026-11-23

An independent review of the whole code gave 51 findings: 1 critical, 1 high, 5 medium and 44 low. This version corrects each fault that it confirmed, and it states each limit that stays. Each point is in the list below.

A second review found faults in this version, and 0.3.6 corrects them. The largest one: three new rules stopped the narrowing of a group too often, so install 0.3.6 and not this version.

### The state stream of an open page

- **The adoption of 0.3.4 could leave each panel with no state stream after a restart.** The adoption made its own message for the handler of Home Assistant, and that message did not pass the schema of the command. The handler reads the keys `include` and `exclude`, which only the schema adds, so it failed with `KeyError`. The adoption ended the state listener of the page before that call. The first code of 0.3.4 then left the page with no listener, and its later correction sent the same message again and failed again. Each message that the integration makes now passes the schema first. The review found the fault before the first known install of 0.3.4.
- **A change of an open subscription starts the new listener before it ends the old one.** If the handler fails, the old listener goes back into its place, and the page keeps the entities that it had. Versions 0.3.0 to 0.3.4 ended the old listener first. This holds for a new entity set, for an adoption, and for the return to all states, which had no guard at all.
- **An unload or a removal of the integration gives each open page all states again.** Before, such a page kept its narrowed set until it connected again, against the README text that all is as before after a removal.
- **A reload of the integration no longer loses the open pages.** Before, the new setup did not know the pages that the old setup narrowed. A saved dashboard, a changed group and a deleted group then changed nothing for them. The unload now returns each page to all states, and the new setup narrows it again.
- **A connection that closes during the entity scan gets no listener.** The scan can wait, such as at the first load of a dashboard or for a YAML dashboard. A page that left in that time got a state listener and a place in the table of open pages, and nothing ended them. The handler now puts a stand-in into the subscriptions of the connection, which Home Assistant removes at a close.
- **Two changes at one time leave the newer entity set.** Two saves of a dashboard close together could leave a page with the older set. The changes of the open pages now run one after the other.
- **A new page gets all states, or an error message, when the handler fails.** Before, a failure inside the task of a narrowed subscription sent the page no result and no error, and the page waited with no end. The page now gets the subscription for all states. If that fails too, the page gets the error message that Home Assistant sends for a failed handler.
- **A failed entity scan leaves each open page as it is, and a failure for one page no longer stops the update of the next pages.** Before, an error for one page ended the update of all later pages, and the adoption after a group change did not run.
- **The log says when Home Assistant has another layout than the adoption expects.** The search for early subscriptions reads the listener table of the event bus and the function `_forward_entity_changes`. On a version without them the search found nothing and the log held nothing. The setup now logs one warning. The search also catches each kind of error at the read, and it takes that function only from the module of Home Assistant that defines it.
- **The update at the end of the start no longer depends on `hass.is_running`.** That property is true also while Home Assistant starts, so a setup in that time added no listener. The setup now uses `async_at_started`.
- **An unload keeps a handler that another integration registered after this one.** Before, the unload wrote the two handlers of Home Assistant back, whatever the table held.
- **A change of the entity, device or area registry updates the open pages.** A new schedule, an entity that moves into the area of an area card, and an entity that is no longer hidden now reach an open page. The registries change in bursts, so one update follows 10 seconds after the first change.

### The entities of a group

- **A dashboard with no stored configuration no longer gives a page two entities. (high)** Home Assistant generates such a dashboard in the browser, such as the default dashboard before its first edit. The scan read it as an empty dashboard, so a panel got only `sun.sun` and `zone.home`, with no line in the log. The states of such a group are now not narrowed, and the log says why one time. The same holds when no dashboard of the group exists. A deleted dashboard beside a stored one is left out, with one warning.
- **A strategy stops the narrowing of its group.** A dashboard, a view or a section with a strategy holds no card: the browser makes them. Such a page got no entity for those cards. The scan also read the area view strategy as an area card.
- **Core cards that find their entities by themselves.** The `home-summary` card and the energy, water, power and gas cards and badges take their entities from all states or from the energy settings, so a group with one of them is not narrowed. A `map` card with `show_all` gets each person, device tracker and zone, and with `geo_location_sources` each geo location entity. The `updates` card gets each update entity. A tile card of a person, and a visibility condition on the location of the user, get each zone.
- **The person entity of each user of the group is sent.** The frontend finds the person of the signed-in user by a search of all states, for a location condition and for the picture of the user.
- **The scan reads the values of a dashboard, and not its JSON text.** In JSON text, a line break or a tab inside a string is a backslash and a letter, which hid the entity ID after it. A value that JSON does not know, such as a date with no quotes in a YAML dashboard, made the scan fail, which turned the filter off for the group with an error at each page load.
- **The name of an action is no entity.** A name such as `light.turn_on` with no state went into the list of a state subscription. Each other name with no state stays, because its first state can come later.
- **The default dashboard is the dashboard `lovelace` when it exists.** Home Assistant 2026.11 takes that dashboard for a request with no URL path, before the dashboard with the key `None`. The scan and the update after a save now do the same.

### The resources of a group

- **An element that a minified decorator registers keeps its file.** The scan of a file sees an element in `customElements.define` with a quoted name, in a `type:` entry, and through the file name. A bundle that registers a second element only through the decorator of Lit, such as a layout of `layout-card.js`, lost that element, and its card showed `Custom element doesn't exist`. For a needed type that no file provides, each file that names the type in quotes is now sent, and the log names the type one time. A type with a provider never takes this way, so a file that only mentions a card of another file stays out. A type of a resource under **Always exclude** takes no such file.
- **A card type inside a template is seen.** A template that returns `{type: 'custom:...'}` holds the type inside a longer string, and the scan read only a string that is the type as a whole.
- **A camera with the key `webrtc_card` keeps the WebRTC script.** The Advanced Camera Card takes the live provider `webrtc-card` by itself for such a camera, and 0.3.0 kept the script only for the written value `webrtc-card`.
- **A card type with no readable provider is in the log.** When one sent resource cannot be read, a type with no provider counts as not verified, and the log held nothing for it. The log now holds one warning for it.
- **Each warning is in the log one time.** `Dashboard ... not found` and `No local resource provides ...` came at each request of each page.
- **A file that cannot be read counts as not readable.** A cut or corrupt `.gz` copy, and a path with a null character, raised an error that failed the request of the whole group. Each page load then sent the full list and wrote a traceback.
- **A resource URL with a host is no local file.** A URL of another server with a path that starts with `/local/` or `/hacsfiles/` was scanned as a file of this server.
- **Always include and Always exclude compare the host and the path.** Before, an entry for a resource of one host also took a resource with the same path on another host. The version in the query still does not count.
- **A name that a file binds more than one time.** A minified file gives one short name more than one value, and the scan kept only the last one, so a template such as `${p}-light-card` gave a wrong name. Each value now counts.
- **Two quoted pieces with a plus count only in a registration or in an assignment to a variable.** Before, each such pair in a file counted as an element of the file, such as a CSS class name.
- **A config folder path that is not in the normal form of the system refused each local file.** The test that keeps a resource path inside the `www` folder compared a normal path with one that was not. Both now have the normal form.
- **The preview lists the files with no element.** A resource that works by a side effect, such as an icon set, provides no card type, so it is not sent. `lite_resources.preview` now lists each readable file with no element and no file name of a card under `excluded_without_element`. Add such a file under **Always include** when a panel needs it.

### The form, the action and the checks

- **`lite_resources.preview` is for administrators.** Before, each signed-in user could call it, and it names each group, each user, each dashboard and each entity of the dashboards. The preview now also says why the states or the resources of a group are not narrowed.
- **The form of a group keeps a stored value that is no option any more.** A select field refuses a value outside its options. A group with a deleted user, a deleted dashboard or a resource URL of an older version could not be saved until that value was removed, and the error did not name it.
- **The form shows the state filter of a stored group as it is.** For a group with no stored value the form showed the filter as on, and such a group does not filter. A plain submit then turned the filter on. The update from a single-group version now also writes the filter as off when that version did not hold the option.
- **A user in two groups is in the log.** Two forms that are open at one time can each add the same user. The first group in the list counts, and the log now says so.
- A group has a hash. Before, `hash(Group)` raised an error, because the options are a dict.
- The text `reconfigure_successful` of a group is gone. Home Assistant shows its own text after a change of a group.
- **The stand-ins of the tests fail as Home Assistant does.** The stand-in for the handler of Home Assistant accepted each message, so 18 tests of the adoption passed with the fault of 0.3.4. It now reads `include` and `exclude` with no default, and the stand-in for the filter does the same. The harness runs an eager task as Home Assistant does, and it can make the entity scan wait and close a connection. New tests cover the group form, the paths that give a panel the full list or all states, the path test of a resource URL, a `.gz` copy and the file cache. The tests grow from 105 to 180.
- The check against the real package of Home Assistant 2026.11.2 now calls the handler exactly as the integration does. The earlier check passed each message through the schema itself, so it did not show the fault.
- The Validate workflow runs the unit tests.

### Limits that stay

- **Member lists.** A new member of a light group, and a new entity that a schedule controls, reach an open page at its next load, at the next save of its dashboard, or at the next change of a registry.
- **Each client of a lite user is narrowed.** The integration knows the user of a connection and not its program. A companion app or a script that signs in as a lite user and asks for all states gets the entities of the dashboards only.
- **Custom cards that select their entities in the browser.** `auto-entities` with a domain filter, the entity list in the editor of the scheduler card, and a template that builds an entity ID from a variable name no entity in the dashboard. Add those entities under **Extra entities**.
- **An administrator who is a lite user** sees the reduced resource list also on the page **Settings**, **Dashboards**, **Resources**.
- **A YAML dashboard** fires no event when its file changes. Its open pages get the new entities when a page loads the dashboard again.
- **Cost.** The entity set of a group is worked out again for each state subscription and each update. One run took 29 ms to 39 ms for 5,573 entities on a workstation. An adoption sends one removal message with each other entity, about 200 KB for that home.
- The hassfest action and the HACS action of the Validate workflow stay on a moving branch, `hassfest@master` and `hacs/action@main`, as the upstream project set them. The developer blog of Home Assistant gives `hassfest@master`.
- The text `single_instance_allowed` stays. The review did not verify that Home Assistant never shows it.
- The links to the issue tracker, the release badge and the Validate badge of this fork need issues, a release and workflow runs on GitHub. The section **Releasing** of the README still describes the releases of the upstream project.

## 0.3.4 - 2026-11-23

- **A panel stays a lite panel across a restart of Home Assistant.** After a restart, a panel connects again within seconds, before Home Assistant sets a custom integration up. The handler of Home Assistant then answered the state subscription of the panel, with every entity. On one kiosk the page went from 95 entities to 5,573, and it fell more than 200 seconds behind for 10 minutes, until its connection broke. Lite Resources now finds such a subscription when its setup runs, and narrows it in place: the panel drops the entities that its dashboards do not show, and it keeps its connection.
- A user that joins a group gets the narrowed stream at once on each open page, in the same way.
- The search for those subscriptions reads internals of Home Assistant 2026.11: the listener list of the event bus. On a version with another layout it finds nothing, and a panel then gets its narrowed stream at its next connection, as before. The search takes the listener function only from the module of Home Assistant that defines it.
- A second commit of this version, `57bf290`, tried to give a page the stream of all entities again when its narrowed subscription failed.
- **This version has a critical fault, and 0.3.5 replaces it. Do not install 0.3.4.** The adoption gave the handler of Home Assistant a message that did not pass the schema of the command, so the handler failed after the adoption ended the listener of the page. Each adopted panel then had no state stream until it connected again. The return to all entities of `57bf290` sent the same message, so it failed in the same way. Two commits carry this version number: `ce1fba9` and `57bf290`.

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
- An entity with no area of its own has the area of its device, and a child device with no area has the area of its parent device. The area card follows that rule, so the search for its entities does too.
- An area can name one entity for its temperature and one for its humidity. An area card shows that entity also when it belongs to another area, so lite users receive it.
- The device class of an entity comes from its state, which is the value that the area card filters on.

## 0.3.0 - 2026-11-23

- **Groups of lite users.** Each group has its own users, dashboards and options. So the panels of one room and a tablet of another room each get the resources and the states of their own dashboards. Add a group with **Add group** on the integration page, and change one with its reconfigure button. A user can be in one group only.
- The update moves the users and dashboards of a single-group setup into one group named **Lite users**. Versions 0.3.0 and 0.3.1 gave it the name **Light users**. You enter nothing again. 0.2.x does not read the new configuration. So a return to 0.2.x after the update needs the integration removed and added again.
- **A changed dashboard reaches the open panels at once.** When you save a dashboard of a group, each open page of the group gets the states of the entities that are new on the dashboard. It loses the entities that left the dashboard. No reload of the integration is necessary. A change of a group does the same.
- A card type that is new on a dashboard loads on a panel at the next page load of that panel. The frontend loads its resources one time for each page load.
- **Always include** and **Always exclude** are optional overrides, and the form says so. The resources of a group come from its dashboards.
- A camera of the Advanced Camera Card with `live_provider: webrtc-card` keeps the script of the WebRTC Camera integration, `webrtc-camera.js`. No card type in the dashboard names that script.
- `lite_resources.preview` lists each group with its users, and the number of open pages with narrowed states.
- An update event that names no dashboard, such as a change of the resource list, updates no page. Such an event has no URL path, and the default dashboard has the URL path `None`, so the two are kept apart.
- The manifest and the README name this fork, `ColColonCleaner/ha-lite-resources`, for the documentation, the issue tracker and the install. The README says that the repository is a fork of `evski/ha-lite-resources`, and it gives the install through the Marketplace of Home Assistant 2026.11.
- The repository tracked one Python bytecode file of a test, and each test run changed it. Git now ignores each `__pycache__` folder.
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
