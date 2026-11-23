"""Groups of lite users, and the live state subscriptions of their open pages.

A group has a name, its users, its dashboards and its options. A user belongs to at most
one group. This module imports nothing from Home Assistant, so that its logic runs in a
plain unit test.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_ALWAYS_EXCLUDE,
    CONF_ALWAYS_INCLUDE,
    CONF_DASHBOARDS,
    CONF_EXTRA_ENTITIES,
    CONF_FILTER_STATES,
    CONF_INCLUDE_UNSCANNABLE,
    CONF_USERS,
    DEFAULT_DASHBOARD,
    SUBENTRY_GROUP,
    WS_SUBSCRIBE_ENTITIES,
)

# The keys of the data of a group. The group name is the title of its subentry.
GROUP_KEYS = (
    CONF_USERS,
    CONF_DASHBOARDS,
    CONF_ALWAYS_INCLUDE,
    CONF_ALWAYS_EXCLUDE,
    CONF_INCLUDE_UNSCANNABLE,
    CONF_FILTER_STATES,
    CONF_EXTRA_ENTITIES,
)

# The key of the removal list in an entity event of the subscribe_entities stream, as
# homeassistant.components.websocket_api.messages.ENTITY_EVENT_REMOVE defines it.
ENTITY_EVENT_REMOVE = "r"

# The event of a state change, as homeassistant.const.EVENT_STATE_CHANGED defines it.
EVENT_STATE_CHANGED = "state_changed"

# The function of homeassistant.components.websocket_api.commands that forwards the state
# changes of a subscribe_entities subscription to its page.
CORE_FORWARD_FUNCTION = "_forward_entity_changes"


@dataclass(frozen=True)
class Group:
    """One group of lite users."""

    group_id: str
    name: str
    options: Mapping[str, Any]

    @property
    def users(self) -> list[str]:
        """The user IDs of the group."""
        return list(self.options.get(CONF_USERS, []))

    @property
    def dashboards(self) -> list[str]:
        """The dashboard keys of the group, with DEFAULT_DASHBOARD for the default one."""
        return list(self.options.get(CONF_DASHBOARDS, []))

    @property
    def filter_states(self) -> bool:
        """True when the state stream of the group is narrowed to its dashboards."""
        return bool(self.options.get(CONF_FILTER_STATES))


def groups_from_subentries(subentries: Mapping[str, Any]) -> list[Group]:
    """Return each group subentry of a config entry as a Group, in the stored order."""
    return [
        Group(sub.subentry_id, sub.title, dict(sub.data))
        for sub in subentries.values()
        if sub.subentry_type == SUBENTRY_GROUP
    ]


def group_for_user(groups: Iterable[Group], user_id: str | None) -> Group | None:
    """Return the first group that holds the user, or None for a user in no group."""
    if user_id is None:
        return None
    for group in groups:
        if user_id in group.users:
            return group
    return None


def dashboard_key(url_path: str | None) -> str:
    """Return the key that a group stores for a dashboard URL path."""
    return DEFAULT_DASHBOARD if url_path is None else url_path


def groups_with_dashboard(groups: Iterable[Group], url_path: str | None) -> list[Group]:
    """Return the groups whose dashboards include the dashboard with this URL path."""
    key = dashboard_key(url_path)
    return [group for group in groups if key in group.dashboards]


def users_in_other_groups(
    groups: Iterable[Group], group_id: str | None, users: Iterable[str]
) -> set[str]:
    """Return those of `users` that a group other than `group_id` already holds."""
    wanted = set(users)
    taken: set[str] = set()
    for group in groups:
        if group.group_id != group_id:
            taken |= wanted.intersection(group.users)
    return taken


def legacy_group_data(options: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the data of one group from the options of a single-group version.

    Versions up to 0.2.1 kept one set of users and dashboards in the options of the config
    entry. None means that those options name no user, so no group results.
    """
    if not options.get(CONF_USERS):
        return None
    return {key: options[key] for key in GROUP_KEYS if key in options}


def unfiltered_state_subscriptions(bus: Any) -> list[tuple[Any, int]]:
    """Return each state subscription for all entities, as (connection, subscription ID).

    Home Assistant keeps no list of its websocket connections. Its subscribe_entities
    handler puts a listener for state changes on the event bus: a partial of the function
    CORE_FORWARD_FUNCTION with the arguments (send_message, entity_ids, entity_filter,
    user, message ID as bytes). `send_message` is a method of the connection, and
    `entity_ids` and `entity_filter` are None for a subscription to all entities.

    This reads internals of Home Assistant: the listener list of the event bus and that
    partial. An item of another layout is left out, so a later version of Home Assistant
    with another layout gives an empty list.
    """
    found: list[tuple[Any, int]] = []
    try:
        listeners = list(bus._listeners.get(EVENT_STATE_CHANGED, ()))
    except AttributeError:
        return found
    for item in listeners:
        try:
            target = item[0].target
            if (
                not isinstance(target, functools.partial)
                or getattr(target.func, "__name__", None) != CORE_FORWARD_FUNCTION
            ):
                continue
            send_message, entity_ids, entity_filter, _user, message_id = target.args[:5]
            if entity_ids is not None or entity_filter is not None:
                continue
            connection = send_message.__self__
            msg_id = int(message_id)
            if msg_id in connection.subscriptions:
                found.append((connection, msg_id))
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
    return found


class _QuietConnection:
    """A connection whose `send_result` does nothing, and that forwards everything else.

    The subscribe_entities handler of Home Assistant answers each call with a result message
    and then with the states. A page already holds the result of its subscription, so a
    second call for the same subscription goes through this wrapper.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def send_result(self, msg_id: Any, result: Any | None = None) -> None:
        """Send no second result for a subscription that already has one."""


@dataclass
class _Live:
    """One narrowed subscribe_entities subscription of an open page."""

    connection: Any
    msg: dict[str, Any]
    entities: frozenset[str]


class LiveSubscriptions:
    """The narrowed state subscriptions of the pages that are open now.

    `subscribe(connection, msg)` runs the subscribe_entities handler of Home Assistant. That
    handler stores the function that ends its state listener in
    `connection.subscriptions[msg["id"]]`, and sends the states of the entities in
    `msg["entity_ids"]`, or of all entities without that key.
    """

    def __init__(self, subscribe: Callable[[Any, dict[str, Any]], None]) -> None:
        self._subscribe = subscribe
        self._live: dict[tuple[int, Any], _Live] = {}

    def __len__(self) -> int:
        return len(self._live)

    def items(self) -> list[_Live]:
        """Return the live subscriptions, as a list that stays valid during changes."""
        return list(self._live.values())

    def start(self, connection: Any, msg: dict[str, Any], entities: Iterable[str]) -> None:
        """Make the subscription of a page for these entities, and keep track of it."""
        wanted = frozenset(entities)
        self._subscribe(connection, {**msg, "entity_ids": sorted(wanted)})
        self._track(_Live(connection, dict(msg), wanted))

    def update(self, live: _Live, entities: Iterable[str] | None) -> bool:
        """Give a live subscription a new entity set. None gives the page all entities.

        The page keeps its subscription ID. It receives the states of the new set, and a
        removal for each entity that left the set. Returns False when the set is unchanged.
        """
        wanted = None if entities is None else frozenset(entities)
        if wanted == live.entities:
            return False
        msg_id = live.msg["id"]
        key = (id(live.connection), msg_id)
        if self._live.get(key) is not live:
            return False
        ended = live.connection.subscriptions.pop(msg_id, None)
        if ended is None:
            # The page ended the subscription between the two steps.
            self._live.pop(key, None)
            return False
        self._live.pop(key, None)
        getattr(ended, "inner", ended)()
        quiet = _QuietConnection(live.connection)
        if wanted is None:
            self._subscribe(quiet, dict(live.msg))
            return True
        self._subscribe(quiet, {**live.msg, "entity_ids": sorted(wanted)})
        removed = live.entities - wanted
        if removed:
            live.connection.send_message(
                {
                    "id": msg_id,
                    "type": "event",
                    "event": {ENTITY_EVENT_REMOVE: sorted(removed)},
                }
            )
        self._track(_Live(live.connection, live.msg, wanted))
        return True

    def adopt(
        self,
        connection: Any,
        msg_id: Any,
        held: Iterable[str],
        entities: Iterable[str],
    ) -> bool:
        """Narrow a subscription for all entities that this object did not make.

        A page makes such a subscription when the handler of Home Assistant answers it,
        before this integration is set up. `held` is each entity that the page can hold
        now. The page keeps its subscription ID. It receives the states of `entities`, and
        a removal for each other entity of `held`. Returns False when the page has no
        subscription with this ID.
        """
        key = (id(connection), msg_id)
        ended = connection.subscriptions.pop(msg_id, None)
        if ended is None or key in self._live:
            if ended is not None:
                connection.subscriptions[msg_id] = ended
            return False
        ended()
        wanted = frozenset(entities)
        msg = {"id": msg_id, "type": WS_SUBSCRIBE_ENTITIES}
        self._subscribe(
            _QuietConnection(connection), {**msg, "entity_ids": sorted(wanted)}
        )
        removed = frozenset(held) - wanted
        if removed:
            connection.send_message(
                {
                    "id": msg_id,
                    "type": "event",
                    "event": {ENTITY_EVENT_REMOVE: sorted(removed)},
                }
            )
        self._track(_Live(connection, msg, wanted))
        return True

    def _track(self, live: _Live) -> None:
        """Remember a subscription until the page or the connection ends it."""
        msg_id = live.msg["id"]
        key = (id(live.connection), msg_id)
        inner = live.connection.subscriptions.get(msg_id)
        if inner is None:
            return

        def ended() -> None:
            self._live.pop(key, None)
            inner()

        ended.inner = inner  # type: ignore[attr-defined]
        live.connection.subscriptions[msg_id] = ended
        self._live[key] = live
