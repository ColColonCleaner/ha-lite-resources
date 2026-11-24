"""Lite Resources: make wall panels and other low-powered devices do less work.

Lite users are set up in groups (for example the logins of the wall panels in one room).
For the users in a group:
- Resources: Home Assistant's frontend fetches the full list of dashboard resources (custom
  cards and mods) with the "lovelace/resources" websocket command and loads all of them. This
  integration answers that command with only the resources that the group's dashboards use.
- States (optional): the frontend streams every entity's state with "subscribe_entities".
  This integration limits that stream to the entities that the group's dashboards show.
Both are worked out from the dashboards at each request. When a dashboard in a group
changes, the open pages in that group get the new entity list at once.
Everyone else gets Home Assistant's normal behaviour. Nothing is changed on disk.
"""

from __future__ import annotations

import asyncio
import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entityfilter import convert_include_exclude_filter
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_FILTER_STATES,
    DOMAIN,
    EVENT_LOVELACE_UPDATED,
    REGISTRY_EVENTS,
    REGISTRY_REFRESH_DELAY,
    SCAN_TIMEOUT,
    SERVICE_PREVIEW,
    SUBENTRY_GROUP,
    UPDATE_RETRIES,
    WS_RESOURCES,
    WS_SUBSCRIBE_ENTITIES,
)
from .groups import (
    Group,
    LiveSubscriptions,
    adoption_fault,
    group_for_user,
    groups_from_subentries,
    groups_with_dashboard,
    legacy_group_data,
    search_state_subscriptions,
    users_in_two_groups,
)
from .resolver import (
    CannotNarrow,
    FileCache,
    async_dashboard_entities,
    async_listen_changes,
    async_resolve,
    own_load_fired,
)

_LOGGER = logging.getLogger(__name__)

# The title of the group that the migration makes from the options of a single-group version.
MIGRATED_GROUP_TITLE = "Lite users"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Move the users and the dashboards of a single-group version into one group."""
    if entry.version == 1:
        data = legacy_group_data(entry.options)
        if data is not None and not groups_from_subentries(entry.subentries):
            # A single-group version with no such option did not narrow the states. A
            # group's form shows a missing option as on, so the group states it.
            data.setdefault(CONF_FILTER_STATES, False)
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(data),
                    subentry_type=SUBENTRY_GROUP,
                    title=MIGRATED_GROUP_TITLE,
                    unique_id=None,
                ),
            )
        hass.config_entries.async_update_entry(entry, options={}, version=2)
        _LOGGER.info("Migrated the configuration to groups of lite users")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Take over the resources command and the states command for the users in each group."""
    handlers = hass.data.get(websocket_api.DOMAIN, {})
    original = handlers.get(WS_RESOURCES)
    original_sub = handlers.get(WS_SUBSCRIBE_ENTITIES)
    if original is None or original_sub is None:
        raise ConfigEntryNotReady("Dashboards (lovelace) not set up yet")
    original_handler, original_schema = original
    sub_handler, sub_schema = original_sub
    cache = FileCache()
    # The keys of the warnings that the log already holds. A warning that repeats at each
    # request from each page hides a new one.
    warned: set[Any] = set()

    def warn_once(key: Any, message: str, *args: Any) -> None:
        if key not in warned:
            warned.add(key)
            _LOGGER.warning(message, *args)

    # "unloaded" is True after this setup's unload. A task from this setup that still
    # waits at that time must change no page, and the handlers from this setup pass each
    # message on.
    setup_state = {"unloaded": False}
    # The IDs of the groups whose last scan failed or could not load a dashboard. A later
    # update tries those scans again, at most UPDATE_RETRIES times in a row.
    trouble: set[str] = set()
    retries = {"left": UPDATE_RETRIES}
    # The scan that runs for each group, by the group ID. A scan that passed its time
    # limit stays here until it ends. The next scan of that group starts only then, so a
    # load that hangs holds one thread of the executor, and not one more for each try.
    open_scans: dict[str, asyncio.Task[set[str]]] = {}

    def groups() -> list[Group]:
        # Read at each request, so a change to a group needs no reload.
        return groups_from_subentries(entry.subentries)

    def check_groups() -> None:
        twice = users_in_two_groups(groups())
        if twice:
            warn_once(
                ("two groups", tuple(sorted(twice))),
                "%d user(s) are in more than one group of lite users. The first group "
                "in the list counts for each of them: %s",
                len(twice),
                ", ".join(sorted(twice)),
            )

    def group_of(connection: websocket_api.ActiveConnection) -> Group | None:
        user = connection.user
        return group_for_user(groups(), user.id if user is not None else None)

    async def entities_of(group: Group) -> set[str] | None:
        """Return the entities for a group's state subscription.

        None means that the group's dashboards do not say which entities a page needs, so
        the group's states are not narrowed. The set holds also each name with no state
        now, so that a page gets an entity whose first state comes after the page
        connected. A scan error is raised, and so is a scan that takes longer than
        SCAN_TIMEOUT seconds, such as the load of a YAML dashboard from a dead share.

        A group whose scan failed, or whose dashboard could not be loaded, goes into
        `trouble`, so that a later update tries its scan again.
        """
        # The scan runs as a task of its own, and the time limit only stops the wait for
        # it. A cancel would stop the load of a YAML dashboard inside Home Assistant
        # before that load fires the update event of the dashboard.
        deadline = hass.loop.time() + SCAN_TIMEOUT
        scan = open_scans.get(group.group_id)
        if scan is not None and not scan.done():
            # An earlier scan of this group still runs after its time limit. Its result
            # can be older than the last change to a dashboard, so it is not used.
            await asyncio.wait({scan}, timeout=SCAN_TIMEOUT)
        if scan is None or scan.done():
            scan = hass.async_create_task(
                async_dashboard_entities(hass, dict(group.options), include_missing=True),
                name=f"{DOMAIN} entity scan",
            )
            open_scans[group.group_id] = scan
            if not scan.done():
                await asyncio.wait(
                    {scan}, timeout=max(deadline - hass.loop.time(), 0)
                )
        if not scan.done():
            scan.add_done_callback(_drop_result)
            trouble.add(group.group_id)
            raise TimeoutError(
                f"the entity scan of group {group.name} took longer than "
                f"{SCAN_TIMEOUT} seconds"
            )
        del open_scans[group.group_id]
        try:
            entities = scan.result()
        except CannotNarrow as err:
            warn_once(
                ("states", group.group_id, str(err)),
                "The states of group %s are not narrowed: %s",
                group.name,
                err,
            )
            if err.retry:
                trouble.add(group.group_id)
            else:
                trouble.discard(group.group_id)
            return None
        except Exception:
            trouble.add(group.group_id)
            raise
        trouble.discard(group.group_id)
        # A reason that comes back later is new, so the log must hold it again.
        for key in [k for k in warned if k[:2] == ("states", group.group_id)]:
            warned.discard(key)
        return entities

    @websocket_api.websocket_command({vol.Required("type"): WS_RESOURCES})
    @websocket_api.async_response
    async def ws_resources(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        group = None if setup_state["unloaded"] else group_of(connection)
        if group is None:
            original_handler(hass, connection, msg)
            return
        try:
            result = await async_resolve(hass, dict(group.options), cache)
        except CannotNarrow as err:
            warn_once(
                ("resources", group.group_id, str(err)),
                "The resources of group %s are not reduced: %s",
                group.name,
                err,
            )
            original_handler(hass, connection, msg)
            return
        except Exception:  # never leave a device without its cards
            _LOGGER.exception("Resolving resources failed; sending the full list")
            original_handler(hass, connection, msg)
            return
        if setup_state["unloaded"]:
            # The unload came during the scan: the full list, as with no integration.
            original_handler(hass, connection, msg)
            return
        # A reason that comes back later is new, so the log must hold it again.
        for key in [k for k in warned if k[:2] == ("resources", group.group_id)]:
            warned.discard(key)
        if result.unresolved_types:
            warn_once(
                ("unresolved", group.group_id, tuple(result.unresolved_types)),
                "No local resource provides %s for group %s; add it under "
                "'Always include' if those cards fail to load",
                ", ".join(result.unresolved_types),
                group.name,
            )
        if result.guessed_types:
            warn_once(
                ("guessed", group.group_id, tuple(result.guessed_types)),
                "No resource registers %s for group %s in a way that the scan sees. Each "
                "resource that names it, and that holds a registration that the scan "
                "cannot read, is sent. If those cards fail to load, add their resource "
                "under 'Always include'",
                ", ".join(result.guessed_types),
                group.name,
            )
        if result.unverified_types:
            warn_once(
                ("unverified", group.group_id, tuple(result.unverified_types)),
                "No resource that the scan can read provides %s for group %s. A resource "
                "that it cannot read may provide it. If those cards fail to load, add "
                "their resource under 'Always include'",
                ", ".join(result.unverified_types),
                group.name,
            )
        _LOGGER.debug(
            "%s (group %s) gets %d of %d resources",
            connection.user.name,
            group.name,
            len(result.included),
            len(result.included) + len(result.excluded),
        )
        connection.send_result(msg["id"], result.included)

    websocket_api.async_register_command(hass, ws_resources)

    live = LiveSubscriptions(
        lambda connection, msg: sub_handler(hass, connection, msg),
        # The handler reads keys that only its schema adds to a message.
        sub_schema if callable(sub_schema) else None,
    )
    # One change to the open pages at a time. Two changes that overlap can leave a page
    # with the older of two entity sets.
    change_lock = asyncio.Lock()

    @callback
    def ws_subscribe_entities(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        # Only the frontend's unfiltered "all states" subscription is narrowed. After the
        # unload, another integration can still call this handler: it then changes nothing.
        group = None if setup_state["unloaded"] else group_of(connection)
        if (
            group is None
            or not group.filter_states
            or msg.get("entity_ids")
            or not _empty_filter(msg)
        ):
            sub_handler(hass, connection, msg)
            return

        msg_id = msg["id"]

        def waiting() -> None:
            """Stand in for the subscription while the entity scan runs."""

        # Home Assistant removes this entry when the page ends the subscription and when
        # the connection closes. So its absence after the scan says that nobody waits.
        connection.subscriptions[msg_id] = waiting

        async def narrowed() -> None:
            try:
                # Under the change lock. A page that starts during an update of the open
                # pages then gets the entity set from after that update.
                async with change_lock:
                    entities = None
                    # A page that left during the wait for the lock, and a setup that is
                    # unloaded, need no scan.
                    if (
                        connection.subscriptions.get(msg_id) is waiting
                        and not setup_state["unloaded"]
                    ):
                        had_trouble = group.group_id in trouble
                        try:
                            entities = await entities_of(group)
                        except Exception:  # the page gets all states for now
                            _LOGGER.exception(
                                "Working out the entities of group %s failed; sending "
                                "all states",
                                group.name,
                            )
                        if had_trouble and group.group_id not in trouble:
                            # The scan of this group works again. Its other pages can
                            # hold all states from the time of the fault.
                            request_update({group.group_id})
                        # A page that gets all states after a failed scan is narrowed by
                        # a later update, when the scan works again.
                        plan_retry()
                    if connection.subscriptions.get(msg_id) is not waiting:
                        # The connection closed, or the client ended the subscription
                        # during the wait. A client that still listens gets the result of
                        # its command. A closed connection only writes a debug line.
                        connection.send_result(msg_id)
                        return
                    del connection.subscriptions[msg_id]
                    if setup_state["unloaded"]:
                        # The unload came during the wait. The page goes to the handler
                        # that is registered now. After a reload that is the new setup's
                        # handler, which narrows the page.
                        handler_now()(hass, connection, msg)
                        return
                    if entities:
                        try:
                            live.start(connection, msg, entities)
                        except Exception:  # the page gets all states
                            _LOGGER.exception(
                                "The narrowed state subscription of %s failed; sending "
                                "all states",
                                connection.user.name,
                            )
                            # The handler can fail after it put its listener on the event bus.
                            half_made = connection.subscriptions.pop(msg_id, None)
                            if half_made is not None:
                                half_made()
                        else:
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug(
                                    "%s (group %s) gets states for %d of %d entities",
                                    connection.user.name,
                                    group.name,
                                    len(entities),
                                    len(hass.states.async_entity_ids()),
                                )
                            return
                    sub_handler(hass, connection, msg)
            # The page gets an error message, as it does from a handler of Home Assistant.
            except Exception as err:  # noqa: BLE001
                connection.async_handle_exception(msg, err)

        hass.async_create_task(narrowed(), eager_start=True)

    websocket_api.async_register_command(
        hass, WS_SUBSCRIBE_ENTITIES, ws_subscribe_entities, sub_schema
    )

    def handler_now() -> Any:
        """Return the handler that is registered for subscribe_entities now.

        This setup's own handler gives the handler that it replaced. So the result never
        calls this setup again.
        """
        pair = hass.data.get(websocket_api.DOMAIN, {}).get(WS_SUBSCRIBE_ENTITIES)
        handler = pair[0] if pair else sub_handler
        return sub_handler if handler is ws_subscribe_entities else handler

    async def group_sets(
        sets: dict[str, set[str] | None],
        failed: set[str],
        group: Group,
        tried: set[str] | None,
    ) -> bool:
        """Put the entity set of a group into `sets`. False when its scan failed.

        `tried` gets the ID of each group that got a scan.
        """
        if tried is not None:
            tried.add(group.group_id)
        if group.group_id in failed:
            return False
        if group.group_id not in sets:
            try:
                sets[group.group_id] = await entities_of(group)
            except Exception:  # the group's pages keep what they have
                _LOGGER.exception(
                    "Working out the entities of group %s failed; its open pages "
                    "keep their entities",
                    group.name,
                )
                failed.add(group.group_id)
                return False
        return True

    def readable_entity_ids(user: Any) -> list[str]:
        """Return each entity that the user can read, as Home Assistant's handler does.

        A page holds only those entities, so only they go into the removal list of an
        adoption. A list of all entities would give a user with a narrow policy the
        names that the policy hides.
        """
        entity_ids = hass.states.async_entity_ids()
        permissions = user.permissions
        if user.is_admin or permissions.access_all_entities(POLICY_READ):
            return entity_ids
        return [
            entity_id
            for entity_id in entity_ids
            if permissions.check_entity(entity_id, POLICY_READ)
        ]

    async def refresh_live(
        only: set[str] | None = None, tried: set[str] | None = None
    ) -> None:
        """Give each open narrowed page the entity set that its group has now.

        `only` limits the work to the pages of the groups with these IDs. `tried` gets
        the ID of each group that got a scan.
        """
        async with change_lock:
            if setup_state["unloaded"]:
                return
            current = groups()
            sets: dict[str, set[str] | None] = {}
            failed: set[str] = set()
            for item in live.items():
                try:
                    user = item.connection.user
                    group = group_for_user(current, user.id if user is not None else None)
                    if group is None or not group.filter_states:
                        # The user left its group, or the group no longer narrows the states.
                        live.update(item, None)
                        continue
                    if only is not None and group.group_id not in only:
                        continue
                    scanned = await group_sets(sets, failed, group, tried)
                    if setup_state["unloaded"]:
                        # The unload came during the scan. It gave each page all states.
                        return
                    if not scanned:
                        continue
                    entities = sets[group.group_id]
                    if not entities:
                        # The dashboards no longer say which entities the page needs.
                        live.update(item, None)
                        continue
                    if live.update(item, entities):
                        _LOGGER.debug(
                            "%s (group %s) now gets states for %d entities",
                            user.name,
                            group.name,
                            len(entities),
                        )
                except Exception:  # the other pages still get their update
                    _LOGGER.exception("The update of an open page of a lite user failed")

    async def adopt_unfiltered(tried: set[str] | None = None) -> None:
        """Narrow each subscription to all states that a page of a lite user holds.

        After a Home Assistant restart, a page connects again before this setup runs.
        Home Assistant's handler then answers its state subscription, with every
        entity. A user that joins a group holds such a subscription too. `tried` gets
        the ID of each group that got a scan.
        """
        async with change_lock:
            if setup_state["unloaded"]:
                return
            current = groups()
            sets: dict[str, set[str] | None] = {}
            failed: set[str] = set()
            found, unreadable = search_state_subscriptions(hass.bus)
            _LOGGER.debug("%d open state subscription(s) hold all entities", len(found))
            if unreadable:
                warn_once(
                    "unreadable listeners",
                    "%d of Home Assistant's state listeners have another layout than this "
                    "integration expects. A panel that connects before this setup, such "
                    "as after a restart, can keep all states until it connects again",
                    unreadable,
                )
            for connection, msg_id in found:
                try:
                    user = connection.user
                    group = group_for_user(current, user.id if user is not None else None)
                    if group is None or not group.filter_states:
                        continue
                    scanned = await group_sets(sets, failed, group, tried)
                    if setup_state["unloaded"]:
                        return
                    if not scanned:
                        continue
                    entities = sets[group.group_id]
                    if not entities:
                        continue
                    if live.adopt(connection, msg_id, readable_entity_ids(user), entities):
                        _LOGGER.debug(
                            "%s (group %s) had a subscription to all states; it now "
                            "gets %d entities",
                            user.name,
                            group.name,
                            len(entities),
                        )
                except Exception:  # the other pages still get their change
                    _LOGGER.exception("The narrowing of an open page of a lite user failed")

    async def update_pages(only: set[str] | None = None) -> None:
        """Bring each open page that belongs to a lite user in step with its group and its dashboards."""
        tried: set[str] = set()
        await refresh_live(only, tried)
        # A page that got all states, because its dashboards did not say what it needs,
        # is narrowed again when they do.
        await adopt_unfiltered(tried)
        # A group that got no scan in this update has no open page, so it has nothing
        # to try again.
        for group_id in [g for g in trouble if g not in tried]:
            if only is None or group_id in only:
                trouble.discard(group_id)
        plan_retry()

    # The updates that wait for the one that runs: the IDs of their groups, or "all" for
    # an update of each group. Many events close together then give one more update, and
    # not one update for each event.
    wanted_updates: dict[str, Any] = {"all": False, "groups": set(), "task": None}

    async def run_updates() -> None:
        while wanted_updates["all"] or wanted_updates["groups"]:
            only = None if wanted_updates["all"] else set(wanted_updates["groups"])
            wanted_updates["all"] = False
            wanted_updates["groups"] = set()
            await update_pages(only)

    @callback
    def request_update(only: set[str] | None = None) -> None:
        """Ask for an update of the open pages in these groups, or in each group for None."""
        if setup_state["unloaded"]:
            return
        if only is None:
            wanted_updates["all"] = True
        else:
            wanted_updates["groups"] |= only
        task = wanted_updates["task"]
        if task is None or task.done():
            wanted_updates["task"] = hass.async_create_task(run_updates())

    @callback
    def dashboard_changed(url_path: str | None) -> None:
        """Update the open pages of the groups that show the dashboard with this URL path."""
        affected = groups_with_dashboard(groups(), url_path)
        if affected:
            request_update({group.group_id for group in affected})

    @callback
    def dashboard_updated(event: Event) -> None:
        """A dashboard changed: update the open pages of the groups that show it."""
        if "url_path" not in event.data:
            # The event names no dashboard. None is the URL path of the default dashboard.
            return
        url_path = event.data["url_path"]
        if own_load_fired(url_path):
            # The load of this dashboard by a scan in this task fired the event: a YAML
            # dashboard whose file changed. That scan calls `dashboard_changed` when the
            # configuration differs from the last one. An update for each such event
            # would have no end for a file that fires at each load.
            return
        dashboard_changed(url_path)

    # An update that waits for its time: the handle of its timer, and the groups that it
    # is for, or "all" for each group. The requests of that time join into one update.
    later: dict[str, Any] = {"handle": None, "all": False, "groups": set()}

    @callback
    def run_later_update() -> None:
        only = None if later["all"] else set(later["groups"])
        later.update(handle=None, all=False, groups=set())
        request_update(only)

    @callback
    def request_later_update(only: set[str] | None = None) -> None:
        """Ask for an update REGISTRY_REFRESH_DELAY seconds from the first such request."""
        if setup_state["unloaded"]:
            return
        if only is None:
            later["all"] = True
        else:
            later["groups"] |= only
        if later["handle"] is None:
            later["handle"] = hass.loop.call_later(
                REGISTRY_REFRESH_DELAY, run_later_update
            )

    def plan_retry() -> None:
        """Ask for one more update when the last scan of a group failed.

        A dashboard load that fails now can work some seconds later. The tries stop after
        UPDATE_RETRIES in a row. The count starts again when no group has such a scan.
        """
        if not trouble:
            retries["left"] = UPDATE_RETRIES
        elif retries["left"] > 0:
            retries["left"] -= 1
            request_later_update(set(trouble))

    @callback
    def registry_updated(event: Event) -> None:
        """A registry changed: a card that finds its entities there can show other ones.

        The registries change in bursts, so one update follows all changes of
        REGISTRY_REFRESH_DELAY seconds.
        """
        request_later_update()

    async def groups_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """A group was added, changed or removed: update the open pages."""
        check_groups()
        await update_pages()

    async def started(hass: HomeAssistant) -> None:
        """Home Assistant's start is complete: update the pages that connected before.

        Each integration had its chance to load, so a group entity now names its members.
        """
        await update_pages()

    async def preview(call: ServiceCall) -> ServiceResponse:
        response: list[dict[str, Any]] = []
        for group in groups():
            options = dict(group.options)
            names = []
            for user_id in group.users:
                user = await hass.auth.async_get_user(user_id)
                names.append(user.name if user else user_id)
            item: dict[str, Any] = {"group": group.name, "users": names}
            try:
                item.update((await async_resolve(hass, options, cache)).as_dict())
            except CannotNarrow as err:
                item["resources_not_reduced"] = str(err)
            if group.filter_states:
                try:
                    entities = await async_dashboard_entities(hass, options)
                    subscribed = await async_dashboard_entities(
                        hass, options, include_missing=True
                    )
                except CannotNarrow as err:
                    item["states_not_narrowed"] = str(err)
                else:
                    item["state_entities"] = sorted(entities)
                    item["state_entities_count"] = (
                        f"{len(entities)} of {len(hass.states.async_entity_ids())}"
                    )
                    # A state subscription holds these names too. Each one has no state
                    # now: an entity whose first state comes later, or a name with an error.
                    item["state_entities_without_state"] = sorted(subscribed - entities)
            response.append(item)
        return {"groups": response, "open_pages_with_narrowed_states": len(live)}

    # The answer names each user and each entity in the dashboards, so only an
    # administrator can call the action.
    async_register_admin_service(
        hass, DOMAIN, SERVICE_PREVIEW, preview, supports_response=SupportsResponse.ONLY
    )

    def restore() -> None:
        # From here on, a task from this setup that still waits changes no page. A handler
        # from this setup that another integration still calls passes each message on.
        setup_state["unloaded"] = True
        commands = hass.data[websocket_api.DOMAIN]
        for command, own, original_pair in (
            (WS_RESOURCES, ws_resources, (original_handler, original_schema)),
            (WS_SUBSCRIBE_ENTITIES, ws_subscribe_entities, (sub_handler, sub_schema)),
        ):
            if commands.get(command, (None, None))[0] is own:
                commands[command] = original_pair
            else:
                _LOGGER.warning(
                    "Another integration replaced the handler of %s after this one. "
                    "That handler stays in place. A call that it passes to this "
                    "integration goes on to Home Assistant's handler",
                    command,
                )
        hass.services.async_remove(DOMAIN, SERVICE_PREVIEW)
        if later["handle"] is not None:
            later["handle"].cancel()
            later["handle"] = None
        # Each open page gets all states again, as without this integration. After a
        # reload, the new setup narrows it again.
        for item in live.items():
            try:
                returned = live.update(item, None)
            except Exception:  # the other pages still get all states
                _LOGGER.exception("The return of an open page to all states failed")
                returned = False
            # A page that ended its subscription in the meantime needs nothing.
            if not returned and item.msg["id"] in item.connection.subscriptions:
                user = item.connection.user
                _LOGGER.error(
                    "An open page of %s keeps its narrowed states until it connects again",
                    user.name if user is not None else "an unknown user",
                )

    entry.async_on_unload(restore)
    entry.async_on_unload(hass.bus.async_listen(EVENT_LOVELACE_UPDATED, dashboard_updated))
    entry.async_on_unload(async_listen_changes(dashboard_changed))
    for event_type in REGISTRY_EVENTS:
        entry.async_on_unload(hass.bus.async_listen(event_type, registry_updated))
    entry.async_on_unload(entry.add_update_listener(groups_updated))
    # At once when the start is complete already, and otherwise at its end.
    entry.async_on_unload(async_at_started(hass, started))

    check_groups()
    fault = adoption_fault(hass.bus)
    if fault:
        _LOGGER.warning(
            "This Home Assistant version differs from the one that this integration "
            "expects: %s. A panel that connects before this setup, such as after a "
            "restart, keeps all states until it connects again",
            fault,
        )
    # The pages that connected before this setup hold a subscription to all states.
    hass.async_create_task(adopt_unfiltered())
    return True


def _drop_result(scan: asyncio.Task[Any]) -> None:
    """Read the result of a scan that ended after its time limit, so that no error stays unread."""
    if not scan.cancelled():
        scan.exception()


def _empty_filter(msg: dict[str, Any]) -> bool:
    """True if the subscription has no include/exclude filter (the schema adds empty ones)."""
    try:
        return convert_include_exclude_filter(msg).empty_filter
    except (KeyError, TypeError):
        return not any(msg.get(k) for k in ("include", "exclude"))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload: the on-unload callbacks restore the original commands."""
    return True
