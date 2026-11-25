"""ha-lite-resources: make wall panels and other low-powered devices do less work.

Lite users are set up in groups (for example the logins of the wall panels in one room).
For the users in a group:
- Resources: Home Assistant's frontend fetches the full list of dashboard resources (custom
  cards and mods) with the "lovelace/resources" websocket command and loads all of them. This
  integration answers that command with only the resources that the group's dashboards use.
- States (optional): the frontend subscribes to every entity's state with
  "subscribe_entities". This integration filters that state subscription to the entities
  that the group's dashboards show.
Both are worked out from the dashboards at each request. When a dashboard in a group
changes, the open pages in that group get the new entity list immediately.
Everyone else gets Home Assistant's normal behaviour. Nothing is changed on disk.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from types import MappingProxyType
from typing import Any

# Home Assistant gives this name to its validation library Probatio.
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
from homeassistant.util.json import JsonValueType

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
    forget_warnings,
    is_own_load,
    note_event,
)

_LOGGER = logging.getLogger(__name__)

# The title of the group that the migration makes from the options of a single-group version.
MIGRATED_GROUP_TITLE = "Lite users"
# Stands for "no warning yet" in the table of the last warnings.
_NO_WARNING = object()


class ScanTrouble(Exception):
    """The entity scan of a group gave no result that a caller can use.

    The log holds the reason, and a later update retries the group's entity scan.
    """


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Move the users and the dashboards of a single-group version into one group."""
    if entry.version == 1:
        data = legacy_group_data(entry.options)
        if data is not None and not groups_from_subentries(entry.subentries):
            # A single-group version with no such option had no entity filtering. A
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
    # A warning of an entity scan or of a resource scan from before this setup is new
    # for this setup.
    forget_warnings()
    # The value of the last warning for each subject, such as the reason why state
    # filtering is off for one group. A warning at each request from each page hides a
    # new one, so the log gets a warning only when its value changes.
    warnings: dict[tuple[Any, ...], Any] = {}

    def warn_change(key: tuple[Any, ...], value: Any, message: str, *args: Any) -> None:
        """Write the warning to the log when the value for this subject is new."""
        if warnings.get(key, _NO_WARNING) != value:
            warnings[key] = value
            _LOGGER.warning(message, *args)

    def forget_warning(key: tuple[Any, ...]) -> None:
        """The cause is gone. The same cause is new when it comes back."""
        warnings.pop(key, None)

    # "unloaded" is True after this setup's unload. A task from this setup that still
    # waits at that time must change no page, and the handlers from this setup pass each
    # message on.
    setup_state = {"unloaded": False}

    def unloaded() -> bool:
        """True after this setup's unload. The value can change during each wait."""
        return setup_state["unloaded"]

    # The count of entity scans in a row that failed, for each group ID. An entity scan
    # that works takes the group out. Each group has its own count, so the pages of one
    # group never use the retries of another group.
    failures: dict[str, int] = {}
    # The IDs of the groups whose dashboards do not say which entities a page needs, such
    # as a group with a strategy dashboard. Only a change to a dashboard or to a group can
    # change that, so an update after a registry change leaves these groups out.
    unscoped: set[str] = set()
    # The entity scan that runs for each group ID, with the group as it was at the start
    # of that entity scan. An entity scan that passed its timeout stays here until it
    # ends.
    open_scans: dict[str, tuple[asyncio.Task[set[str]], Group]] = {}

    def groups() -> list[Group]:
        # Read at each request, so a change to a group needs no reload of the
        # integration.
        return groups_from_subentries(entry.subentries)

    def check_groups() -> None:
        twice = users_in_two_groups(groups())
        if twice:
            warn_change(
                ("two groups",),
                tuple(sorted(twice)),
                "%d user(s) are in more than one group of lite users. The first group "
                "in the list counts for each of them: %s",
                len(twice),
                ", ".join(sorted(twice)),
            )
        else:
            forget_warning(("two groups",))

    def group_of(connection: websocket_api.ActiveConnection) -> Group | None:
        user = connection.user
        return group_for_user(groups(), user.id if user is not None else None)

    async def entities_of(group: Group) -> set[str] | None:
        """Return the entities for a group's state subscription.

        None means that the group's dashboards do not say which entities a page needs, so
        entity filtering is off for the group. The set holds also each entity ID with no
        state now, so that a page gets an entity whose first state comes after the page
        connected.

        ScanTrouble is raised when the entity scan gave no result that a caller can use.
        The entity scan failed, or a dashboard could not be loaded, or the entity scan
        runs longer than SCAN_TIMEOUT seconds, such as the load of a YAML dashboard from
        a dead share. The log then holds the reason, and a later update retries the
        entity scan. So a caller does nothing more: a new page gets all states for that
        time, and an open page keeps its entities.
        """
        group_id = group.group_id
        key = ("states", group_id)
        running, scanned = open_scans.get(group_id, (None, None))
        if running is not None and not running.done() and scanned == group:
            # This entity scan passed its timeout before. Its end starts an update of
            # the group, so nobody waits for it a second time.
            raise ScanTrouble(f"the entity scan of group {group.name} still runs")
        # The entity scan runs as a task of its own, and the timeout only stops the
        # wait for it. A cancel would stop the load of a YAML dashboard inside Home
        # Assistant before that load fires the update event of the dashboard. A
        # background task holds neither the start nor the stop of Home Assistant. It is
        # a task of Home Assistant and not of the config entry, because an unload
        # cancels each background task of its entry. An entity scan of this group that
        # still runs for other dashboards, from before a change to the group, is left
        # alone, and its result is not used.
        scan = hass.async_create_background_task(
            async_dashboard_entities(hass, dict(group.options), include_missing=True),
            name=f"{DOMAIN} entity scan",
        )
        open_scans[group_id] = (scan, group)
        if not scan.done():
            await asyncio.wait({scan}, timeout=SCAN_TIMEOUT)
        if not scan.done():
            scan.add_done_callback(functools.partial(late_scan_done, group_id))
            warn_change(
                key,
                "time limit",
                "The entity scan of group %s runs longer than %s seconds. A new page "
                "gets all states, and an open page keeps its entities. The pages of "
                "the group get an update when the entity scan ends",
                group.name,
                SCAN_TIMEOUT,
            )
            raise ScanTrouble(
                f"the entity scan of group {group.name} passed its timeout"
            )
        if open_scans.get(group_id, (None, None))[0] is scan:
            del open_scans[group_id]
        try:
            entities = scan.result()
        except CannotNarrow as err:
            if err.retry:
                # Such as a dashboard that cannot be loaded now.
                warn_change(
                    key,
                    str(err),
                    "The entity scan of group %s cannot run: %s. A new page gets all "
                    "states, and an open page keeps its entities",
                    group.name,
                    err,
                )
                scan_failed(group)
                raise ScanTrouble(str(err)) from err
            warn_change(
                key,
                str(err),
                "Entity filtering is off for group %s: %s",
                group.name,
                err,
            )
            failures.pop(group_id, None)
            unscoped.add(group_id)
            return None
        except Exception as err:
            # The traceback goes into the log once for each new error text.
            if warnings.get(key, _NO_WARNING) != repr(err):
                warnings[key] = repr(err)
                _LOGGER.exception(
                    "The entity scan of group %s failed. A new page gets all states, "
                    "and an open page keeps its entities",
                    group.name,
                )
            scan_failed(group)
            raise ScanTrouble(repr(err)) from err
        failures.pop(group_id, None)
        unscoped.discard(group_id)
        forget_warning(key)
        return entities

    @callback
    def scan_failed(group: Group) -> None:
        """Count a group's failed entity scan, and ask for a retry of that entity scan.

        Each entity scan of the group counts, also one that a new page or a change
        starts. The retries stop when the count passes UPDATE_RETRIES, and an entity
        scan that works starts the count again.
        """
        count = failures.get(group.group_id, 0) + 1
        failures[group.group_id] = count
        if count <= UPDATE_RETRIES:
            request_later_update({group.group_id})
        elif count == UPDATE_RETRIES + 1:
            _LOGGER.warning(
                "The entity scan of group %s failed %d times in a row. The next retry "
                "comes with the next change to a dashboard or to the group, or when a "
                "page of the group connects",
                group.name,
                count,
            )

    def late_scan_done(group_id: str, scan: asyncio.Task[set[str]]) -> None:
        """An entity scan ended after its timeout: ask for an update of its group.

        The update runs a new entity scan, which ends in time when the load works again.
        The result of the late entity scan is not used, because a dashboard can be newer
        than that result.
        """
        if open_scans.get(group_id, (None, None))[0] is scan:
            del open_scans[group_id]
        if scan.cancelled():
            return
        # Read the error, so that Python reports no error that nobody read.
        scan.exception()
        request_update({group_id})

    @websocket_api.websocket_command({vol.Required("type"): WS_RESOURCES})
    @websocket_api.async_response
    async def ws_resources(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        group = None if unloaded() else group_of(connection)
        if group is None:
            original_handler(hass, connection, msg)
            return
        key = ("resources", group.group_id)
        # The resource scan runs as a task of its own, as the entity scan does. The
        # timeout ends the wait, and not the load of a dashboard. A page with no answer
        # to this command loads no card at all, so a resource scan with no end gets the
        # full resource list.
        scan = hass.async_create_background_task(
            async_resolve(hass, dict(group.options), cache),
            name=f"{DOMAIN} resource scan",
        )
        if not scan.done():
            await asyncio.wait({scan}, timeout=SCAN_TIMEOUT)
        result = None
        if not scan.done():
            scan.add_done_callback(_drop_result)
            warn_change(
                key,
                "time limit",
                "The resource scan of group %s runs longer than %s seconds. The page "
                "gets the full resource list",
                group.name,
                SCAN_TIMEOUT,
            )
        else:
            try:
                result = scan.result()
            except CannotNarrow as err:
                warn_change(
                    key,
                    str(err),
                    "Resource filtering is off for group %s: %s",
                    group.name,
                    err,
                )
            except Exception:  # never leave a device without its cards
                _LOGGER.exception("The resource scan failed; sending the full list")
        if unloaded():
            # The unload came during the resource scan. After a reload of the
            # integration, the handler of the new setup answers, so the page still gets
            # its filtered resource list.
            answer = resources_handler_now()(hass, connection, msg)
            if inspect.isawaitable(answer):
                await answer
            return
        if result is None:
            original_handler(hass, connection, msg)
            return
        forget_warning(key)
        for kind, types, message in (
            (
                "unresolved",
                result.unresolved_types,
                (
                    "No local resource provides %s for group %s; add it under "
                    "'Always include' if those cards fail to load"
                ),
            ),
            (
                "guessed",
                result.guessed_types,
                (
                    "No resource registers %s for group %s in a way that the resource "
                    "scan can read. The page gets each resource that names it, and "
                    "that holds a registration that the resource scan cannot read. "
                    "If those cards fail to load, add their resource under "
                    "'Always include'"
                ),
            ),
            (
                "unverified",
                result.unverified_types,
                (
                    "No resource that the resource scan can read provides %s for group "
                    "%s. A resource that the resource scan cannot read may provide it. "
                    "If those cards fail to load, add their resource under "
                    "'Always include'"
                ),
            ),
        ):
            if types:
                warn_change(
                    (kind, group.group_id),
                    tuple(types),
                    message,
                    ", ".join(types),
                    group.name,
                )
            else:
                forget_warning((kind, group.group_id))
        _LOGGER.debug(
            "%s (group %s) gets %d of %d resources",
            connection.user.name,
            group.name,
            len(result.included),
            len(result.included) + len(result.excluded),
        )
        connection.send_result(msg["id"], result.included)

    websocket_api.async_register_command(hass, ws_resources)

    def resources_handler_now() -> Any:
        """Return the handler for lovelace/resources that a waiting request goes to.

        That is the handler in the table now, which is the handler of the new setup
        after a reload of the integration. While the table still holds the handler of
        this setup, it is the handler that this setup replaced, so this setup is not
        called a second time.
        """
        pair = hass.data.get(websocket_api.DOMAIN, {}).get(WS_RESOURCES)
        handler = pair[0] if pair else original_handler
        return original_handler if handler is ws_resources else handler

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
        # Entity filtering applies only to the frontend's subscription to all states,
        # which has no entity list and no include or exclude filter. After the
        # unload, another integration can still call this handler: it then changes
        # nothing.
        group = None if unloaded() else group_of(connection)
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
        # the connection closes. So its absence after the entity scan says that nobody
        # waits.
        connection.subscriptions[msg_id] = waiting

        async def narrowed() -> None:
            try:
                # Under the change lock. A page that starts during an update of the open
                # pages then gets the entity set from after that update.
                async with change_lock:
                    entities = None
                    # A page that left during the wait for the lock, and a setup that is
                    # unloaded, need no entity scan.
                    if (
                        connection.subscriptions.get(msg_id) is waiting
                        and not unloaded()
                    ):
                        had_failures = group.group_id in failures
                        try:
                            entities = await entities_of(group)
                        except ScanTrouble:
                            # The page gets all states for now. The log holds the
                            # reason, and a later update of the group filters the page.
                            entities = None
                        else:
                            if had_failures:
                                # The entity scan of this group works again. Its other
                                # pages can hold all states from the time of the fault.
                                request_update({group.group_id})
                    if connection.subscriptions.get(msg_id) is not waiting:
                        # The connection closed, or the page ended the subscription
                        # during the wait. A page that still listens gets the result of
                        # its command. A closed connection only writes a debug line.
                        connection.send_result(msg_id)
                        return
                    del connection.subscriptions[msg_id]
                    if unloaded():
                        # The unload came during the wait. The page goes to the handler
                        # that is registered now. After a reload of the integration,
                        # that is the new setup's handler, which filters the page.
                        handler_now()(hass, connection, msg)
                        return
                    if entities:
                        try:
                            live.start(connection, msg, entities)
                        except Exception:  # the page gets all states
                            _LOGGER.exception(
                                "The filtered state subscription of %s failed. The "
                                "page gets all states",
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
        """Return the handler for subscribe_entities that a waiting page goes to.

        That is the handler in the table now, which is the handler of the new setup
        after a reload of the integration. While the table still holds the handler of
        this setup, it is the handler that this setup replaced, so this function never
        returns the handler of this setup.
        """
        pair = hass.data.get(websocket_api.DOMAIN, {}).get(WS_SUBSCRIBE_ENTITIES)
        handler = pair[0] if pair else sub_handler
        return sub_handler if handler is ws_subscribe_entities else handler

    async def group_sets(
        sets: dict[str, set[str] | None], failed: set[str], group: Group
    ) -> bool:
        """Put the entity set of a group into `sets`.

        The result is False when the group's entity scan gave no result. `sets` and
        `failed` hold the results of one update, so that each group gets one entity scan
        in that update.
        """
        if group.group_id in failed:
            return False
        if group.group_id not in sets:
            try:
                sets[group.group_id] = await entities_of(group)
            except ScanTrouble:
                # The pages of the group keep what they have. The log holds the reason.
                failed.add(group.group_id)
                return False
        return True

    def readable_entity_ids(user: Any) -> list[str]:
        """Return each entity that the user can read, as Home Assistant's handler does.

        A page holds only those entities, so only they go into the removal list of an
        adoption. A list of all entities would show a user with a restrictive policy the
        entity IDs that the policy hides.
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
        only: set[str] | None, sets: dict[str, set[str] | None], failed: set[str]
    ) -> None:
        """Update each open filtered page with the entity set that its group has now.

        `only` limits the entity scans to the groups with these IDs. `sets` and `failed`
        are those of `group_sets`.
        """
        async with change_lock:
            if unloaded():
                return
            current = groups()
            for item in live.items():
                try:
                    user = item.connection.user
                    group = group_for_user(
                        current, user.id if user is not None else None
                    )
                    if group is None or not group.filter_states:
                        # The user left its group, or entity filtering is off for the
                        # group now.
                        live.update(item, None)
                        continue
                    if only is not None and group.group_id not in only:
                        continue
                    scanned = await group_sets(sets, failed, group)
                    if unloaded():
                        # The unload came during the entity scan. It sent each page all
                        # states.
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
                    _LOGGER.exception(
                        "The update of an open page of a lite user failed"
                    )

    async def adopt_unfiltered(
        only: set[str] | None, sets: dict[str, set[str] | None], failed: set[str]
    ) -> None:
        """Filter each subscription to all states that a page of a lite user holds.

        After a Home Assistant restart, a page reconnects before this setup runs.
        Home Assistant's handler then answers its state subscription, with every
        entity. A user that joins a group holds such a subscription too. A page that
        got all states after an entity scan with no result holds one also. `only`,
        `sets` and `failed` are those of `refresh_live`.
        """
        async with change_lock:
            if unloaded():
                return
            current = groups()
            found, unreadable = search_state_subscriptions(hass.bus)
            _LOGGER.debug("%d open state subscription(s) hold all states", len(found))
            if unreadable:
                warn_change(
                    ("unreadable listeners",),
                    True,
                    "%d of Home Assistant's state listeners have another layout than this "
                    "integration expects. A page that connects before this setup, such "
                    "as after a restart, can keep all states until it reconnects",
                    unreadable,
                )
            for connection, msg_id in found:
                try:
                    user = connection.user
                    group = group_for_user(
                        current, user.id if user is not None else None
                    )
                    if group is None or not group.filter_states:
                        continue
                    if only is not None and group.group_id not in only:
                        continue
                    scanned = await group_sets(sets, failed, group)
                    if unloaded():
                        return
                    if not scanned:
                        continue
                    entities = sets[group.group_id]
                    if not entities:
                        continue
                    if live.adopt(
                        connection, msg_id, readable_entity_ids(user), entities
                    ):
                        _LOGGER.debug(
                            "%s (group %s) had a subscription to all states. It now "
                            "gets %d entities",
                            user.name,
                            group.name,
                            len(entities),
                        )
                except Exception:  # the other pages still get their change
                    _LOGGER.exception(
                        "The entity filtering of an open page of a lite user failed"
                    )

    async def update_pages(only: set[str] | None = None) -> None:
        """Bring each open page that belongs to a lite user in step with its group and its dashboards."""
        sets: dict[str, set[str] | None] = {}
        failed: set[str] = set()
        await refresh_live(only, sets, failed)
        # A page that holds all states is filtered when its group has an entity set: a
        # page from before the setup, and a page from the time of an entity scan with no
        # result.
        await adopt_unfiltered(only, sets, failed)

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
        if unloaded():
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
        if is_own_load(url_path):
            # An entity scan or a resource scan of this integration loads this dashboard
            # now, in this task, and that load fired the event: a YAML dashboard whose
            # file changed. After each load, the integration compares the configuration
            # with the last one, and calls `dashboard_changed` when the two differ. An
            # update for each such event would have no end for a file that fires at each
            # load.
            return
        # The event comes from another task: a save, or the load of a browser. The
        # entity scans of the update below load what the event announced, which is no
        # second change.
        note_event(url_path)
        dashboard_changed(url_path)

    # An update that waits for its time: the handle of its timer, the groups that it is
    # for, and "registry" when a registry changed. The requests of that time join into
    # one update.
    later: dict[str, Any] = {"handle": None, "registry": False, "groups": set()}

    @callback
    def run_later_update() -> None:
        only = set(later["groups"])
        if later["registry"]:
            # A registry change cannot give a group in `unscoped` an entity set.
            only |= {g.group_id for g in groups() if g.group_id not in unscoped}
        later.update(handle=None, registry=False, groups=set())
        if only:
            request_update(only)

    @callback
    def request_later_update(only: set[str] | None = None) -> None:
        """Ask for an update REGISTRY_REFRESH_DELAY seconds from the first such request.

        `only` names the groups of the update. None stands for a registry change.
        """
        if unloaded():
            return
        if only is None:
            later["registry"] = True
        else:
            later["groups"] |= only
        if later["handle"] is None:
            later["handle"] = hass.loop.call_later(
                REGISTRY_REFRESH_DELAY, run_later_update
            )

    @callback
    def registry_updated(event: Event) -> None:
        """A registry changed: a card that finds its entities there can show other ones.

        The registries change in bursts, so one update follows the changes of
        REGISTRY_REFRESH_DELAY seconds.
        """
        request_later_update()

    async def groups_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """A group was added, changed or removed: update the open pages."""
        check_groups()
        await update_pages()

    async def started(hass: HomeAssistant) -> None:
        """Home Assistant's start is complete: update the pages that connected before.

        The setup of each integration is over, so a group entity now names its members.
        """
        await update_pages()

    async def preview(call: ServiceCall) -> ServiceResponse:
        response: list[JsonValueType] = []
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
                item["resources_not_filtered"] = str(err)
            if group.filter_states:
                try:
                    entities = await async_dashboard_entities(hass, options)
                    subscribed = await async_dashboard_entities(
                        hass, options, include_missing=True
                    )
                except CannotNarrow as err:
                    item["entities_not_filtered"] = str(err)
                else:
                    item["state_entities"] = sorted(entities)
                    item["state_entities_count"] = (
                        f"{len(entities)} of {len(hass.states.async_entity_ids())}"
                    )
                    # A state subscription holds these entity IDs too. Each one has no
                    # state now: an entity whose first state comes later, or an entity
                    # ID with an error.
                    item["state_entities_without_state"] = sorted(subscribed - entities)
            response.append(item)
        return {"groups": response, "open_pages_with_filtered_entities": len(live)}

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
        # reload of the integration, the new setup filters it again.
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
                    "An open page of %s keeps entity filtering until it reconnects",
                    user.name if user is not None else "an unknown user",
                )

    entry.async_on_unload(restore)
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_LOVELACE_UPDATED, dashboard_updated)
    )
    entry.async_on_unload(async_listen_changes(dashboard_changed))
    for event_type in REGISTRY_EVENTS:
        entry.async_on_unload(hass.bus.async_listen(event_type, registry_updated))
    entry.async_on_unload(entry.add_update_listener(groups_updated))
    # Immediately when the start is complete already, and otherwise at its end.
    entry.async_on_unload(async_at_started(hass, started))

    check_groups()
    fault = adoption_fault(hass.bus)
    if fault:
        _LOGGER.warning(
            "This Home Assistant version differs from the one that this integration "
            "expects: %s. A page that connects before this setup, such as after a "
            "restart, keeps all states until it reconnects",
            fault,
        )
    # The pages that connected before this setup hold a subscription to all states.
    hass.async_create_task(adopt_unfiltered(None, {}, set()))
    return True


def _drop_result(scan: asyncio.Task[Any]) -> None:
    """Read the result of a resource scan that ended after its timeout.

    No error then stays unread.
    """
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
