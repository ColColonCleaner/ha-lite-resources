"""Lite Resources: make wall panels and other light devices do less work.

Light users are set up in groups (for example the logins of the wall panels of one room).
For the users of a group:
- Resources: Home Assistant's frontend fetches the full list of dashboard resources (custom
  cards and mods) with the "lovelace/resources" websocket command and loads all of them. This
  integration answers that command with only the resources the dashboards of the group use.
- States (optional): the frontend streams every entity's state with "subscribe_entities". This
  integration limits that stream to the entities the dashboards of the group show.
Both are worked out from the dashboards at each request. When a dashboard of a group changes,
the open pages of the group get the new entity list at once.
Everyone else gets Home Assistant's normal behaviour. Nothing is changed on disk.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol

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

from .const import (
    DOMAIN,
    EVENT_LOVELACE_UPDATED,
    SERVICE_PREVIEW,
    SUBENTRY_GROUP,
    WS_RESOURCES,
    WS_SUBSCRIBE_ENTITIES,
)
from .groups import (
    Group,
    LiveSubscriptions,
    group_for_user,
    groups_from_subentries,
    groups_with_dashboard,
    legacy_group_data,
)
from .resolver import FileCache, async_dashboard_entities, async_resolve

_LOGGER = logging.getLogger(__name__)

# The title of the group that the migration makes from the options of a single-group version.
MIGRATED_GROUP_TITLE = "Light users"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Move the users and dashboards of a single-group version into one group."""
    if entry.version == 1:
        data = legacy_group_data(entry.options)
        if data is not None and not groups_from_subentries(entry.subentries):
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
        _LOGGER.info("Migrated the configuration to groups of light users")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Take over the resources and states commands for the users of each group."""
    handlers = hass.data.get(websocket_api.DOMAIN, {})
    original = handlers.get(WS_RESOURCES)
    original_sub = handlers.get(WS_SUBSCRIBE_ENTITIES)
    if original is None or original_sub is None:
        raise ConfigEntryNotReady("Dashboards (lovelace) not set up yet")
    original_handler, original_schema = original
    sub_handler, sub_schema = original_sub
    cache = FileCache()

    def groups() -> list[Group]:
        # Read at each request, so a change of a group needs no reload.
        return groups_from_subentries(entry.subentries)

    def group_of(connection: websocket_api.ActiveConnection) -> Group | None:
        user = connection.user
        return group_for_user(groups(), user.id if user is not None else None)

    async def entities_of(group: Group) -> set[str]:
        """Return the entities of the dashboards of a group. Empty when that fails."""
        try:
            return await async_dashboard_entities(hass, dict(group.options))
        except Exception:
            _LOGGER.exception(
                "Working out the entities of group %s failed; sending all states",
                group.name,
            )
            return set()

    @websocket_api.websocket_command({vol.Required("type"): WS_RESOURCES})
    @websocket_api.async_response
    async def ws_resources(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        group = group_of(connection)
        if group is None:
            original_handler(hass, connection, msg)
            return
        try:
            result = await async_resolve(hass, dict(group.options), cache)
        except Exception:  # never leave a device without its cards
            _LOGGER.exception("Resolving resources failed; sending the full list")
            original_handler(hass, connection, msg)
            return
        if result.unresolved_types:
            _LOGGER.warning(
                "No local resource provides %s for %s (group %s); add it under "
                "'Always include' if those cards fail to load",
                ", ".join(result.unresolved_types),
                connection.user.name,
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
        lambda connection, msg: sub_handler(hass, connection, msg)
    )

    @callback
    def ws_subscribe_entities(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        # Only the frontend's unfiltered "all states" subscription is narrowed.
        group = group_of(connection)
        if (
            group is None
            or not group.filter_states
            or msg.get("entity_ids")
            or not _empty_filter(msg)
        ):
            sub_handler(hass, connection, msg)
            return

        async def narrowed() -> None:
            entities = await entities_of(group)
            if not entities:
                sub_handler(hass, connection, msg)
                return
            _LOGGER.debug(
                "%s (group %s) gets states for %d of %d entities",
                connection.user.name,
                group.name,
                len(entities),
                len(hass.states.async_entity_ids()),
            )
            live.start(connection, msg, entities)

        hass.async_create_task(narrowed(), eager_start=True)

    websocket_api.async_register_command(
        hass, WS_SUBSCRIBE_ENTITIES, ws_subscribe_entities, sub_schema
    )

    async def refresh_live(only: set[str] | None = None) -> None:
        """Give each open page of a light user the entity set of its group as it is now.

        `only` limits the work to the pages of the groups with these IDs.
        """
        current = groups()
        sets: dict[str, set[str]] = {}
        for item in live.items():
            user = item.connection.user
            group = group_for_user(current, user.id if user is not None else None)
            if group is None or not group.filter_states:
                # The user left its group, or the group no longer narrows the states.
                live.update(item, None)
                continue
            if only is not None and group.group_id not in only:
                continue
            if group.group_id not in sets:
                sets[group.group_id] = await entities_of(group)
            entities = sets[group.group_id]
            if not entities:
                continue
            if live.update(item, entities):
                _LOGGER.debug(
                    "%s (group %s) now gets states for %d entities",
                    user.name,
                    group.name,
                    len(entities),
                )

    @callback
    def dashboard_updated(event: Event) -> None:
        """A dashboard changed: update the open pages of the groups that show it."""
        if "url_path" not in event.data:
            # The event names no dashboard. None is the URL path of the default dashboard.
            return
        affected = groups_with_dashboard(groups(), event.data["url_path"])
        if affected and len(live):
            hass.async_create_task(refresh_live({group.group_id for group in affected}))

    async def groups_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """A group was added, changed or removed: update the open pages."""
        await refresh_live()

    async def preview(call: ServiceCall) -> ServiceResponse:
        response: list[dict[str, Any]] = []
        for group in groups():
            options = dict(group.options)
            result = await async_resolve(hass, options, cache)
            names = []
            for user_id in group.users:
                user = await hass.auth.async_get_user(user_id)
                names.append(user.name if user else user_id)
            item: dict[str, Any] = {
                "group": group.name,
                "users": names,
                **result.as_dict(),
            }
            if group.filter_states:
                entities = await async_dashboard_entities(hass, options)
                item["state_entities"] = sorted(entities)
                item["state_entities_count"] = (
                    f"{len(entities)} of {len(hass.states.async_entity_ids())}"
                )
            response.append(item)
        return {"groups": response, "open_pages_with_narrowed_states": len(live)}

    hass.services.async_register(
        DOMAIN, SERVICE_PREVIEW, preview, supports_response=SupportsResponse.ONLY
    )

    def restore() -> None:
        commands = hass.data[websocket_api.DOMAIN]
        commands[WS_RESOURCES] = (original_handler, original_schema)
        commands[WS_SUBSCRIBE_ENTITIES] = (sub_handler, sub_schema)
        hass.services.async_remove(DOMAIN, SERVICE_PREVIEW)

    entry.async_on_unload(restore)
    entry.async_on_unload(hass.bus.async_listen(EVENT_LOVELACE_UPDATED, dashboard_updated))
    entry.async_on_unload(entry.add_update_listener(groups_updated))
    return True


def _empty_filter(msg: dict[str, Any]) -> bool:
    """True if the subscription has no include/exclude filter (the schema adds empty ones)."""
    try:
        return convert_include_exclude_filter(msg).empty_filter
    except (KeyError, TypeError):
        return not any(msg.get(k) for k in ("include", "exclude"))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload: the on-unload callbacks restore the original commands."""
    return True
