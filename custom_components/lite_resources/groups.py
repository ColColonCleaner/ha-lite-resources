"""Groups of lite users, and the live state subscriptions that their open pages hold.

A group has a name, its users, its dashboards and its options. A user belongs to at most
one group. This module imports nothing from Home Assistant, so that its logic runs in a
plain unit test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import functools
import logging
import sys
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
    LOVELACE_DASHBOARD,
    SUBENTRY_GROUP,
    WS_SUBSCRIBE_ENTITIES,
)

# The keys in a group's data. The group name is its subentry's title.
GROUP_KEYS = (
    CONF_USERS,
    CONF_DASHBOARDS,
    CONF_ALWAYS_INCLUDE,
    CONF_ALWAYS_EXCLUDE,
    CONF_INCLUDE_UNSCANNABLE,
    CONF_FILTER_STATES,
    CONF_EXTRA_ENTITIES,
)

# The key for the removal list in an entity event of a state subscription, as
# homeassistant.components.websocket_api.messages.ENTITY_EVENT_REMOVE defines it.
ENTITY_EVENT_REMOVE = "r"

# The state change event, as homeassistant.const.EVENT_STATE_CHANGED defines it.
EVENT_STATE_CHANGED = "state_changed"

# The function that forwards the state changes of a subscribe_entities subscription to
# its page, and the Home Assistant module that defines it.
CORE_FORWARD_FUNCTION = "_forward_entity_changes"
CORE_FORWARD_MODULE = "homeassistant.components.websocket_api.commands"

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Group:
    """One group of lite users."""

    group_id: str
    name: str
    # The options are a dict, which has no hash. A group's hash comes from its ID and its
    # name.
    options: Mapping[str, Any] = field(hash=False)

    @property
    def users(self) -> list[str]:
        """The group's user IDs."""
        return list(self.options.get(CONF_USERS, []))

    @property
    def dashboards(self) -> list[str]:
        """The group's dashboard keys, with DEFAULT_DASHBOARD for the default one."""
        return list(self.options.get(CONF_DASHBOARDS, []))

    @property
    def filter_states(self) -> bool:
        """True when state filtering is on for the group."""
        return bool(self.options.get(CONF_FILTER_STATES))


def groups_from_subentries(subentries: Mapping[str, Any]) -> list[Group]:
    """Return each group subentry in a config entry as a Group, in the stored order."""
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
    """Return the groups whose dashboards include the dashboard with this URL path.

    Home Assistant shows the dashboard with the URL path LOVELACE_DASHBOARD as the default
    dashboard when it exists. So a group with the default dashboard also follows that one.
    """
    keys = {dashboard_key(url_path)}
    if url_path == LOVELACE_DASHBOARD:
        keys.add(DEFAULT_DASHBOARD)
    return [group for group in groups if keys.intersection(group.dashboards)]


def users_in_two_groups(groups: Iterable[Group]) -> set[str]:
    """Return each user that more than one group holds. The first group counts for it."""
    seen: set[str] = set()
    twice: set[str] = set()
    for group in groups:
        users = set(group.users)
        twice |= seen & users
        seen |= users
    return twice


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
    """Return the data for one group, taken from the options of a single-group version.

    Versions up to 0.2.1 kept the users and the dashboards of one group in the config
    entry's options. None means that those options name no user, so no group results.
    """
    if not options.get(CONF_USERS):
        return None
    return {key: options[key] for key in GROUP_KEYS if key in options}


def unfiltered_state_subscriptions(bus: Any) -> list[tuple[Any, int]]:
    """Return each subscription to all states, as (connection, subscription ID).

    Home Assistant keeps no list of its websocket connections. Its subscribe_entities
    handler puts a listener for state changes on the event bus: a partial of the function
    CORE_FORWARD_FUNCTION with the arguments (send_message, entity_ids, entity_filter,
    user, message ID as bytes). `send_message` is a method of the connection, and
    `entity_ids` and `entity_filter` are None for a subscription to all states.

    This reads internals of Home Assistant: the listener list of the event bus, and that
    partial. An item with another layout is left out, so a later Home Assistant version
    with another layout gives an empty list. The read catches each exception, because
    the layout of an internal can change in any way.
    """
    return search_state_subscriptions(bus)[0]


def search_state_subscriptions(bus: Any) -> tuple[list[tuple[Any, int]], int]:
    """Return the subscriptions to all states, and a count of unreadable listeners.

    The first value is that of unfiltered_state_subscriptions. The second value counts the
    listeners of the function CORE_FORWARD_FUNCTION whose arguments do not have the layout
    that this search knows. A count above zero means that Home Assistant passes that
    function in another way, so the search can miss a subscription.
    """
    found: list[tuple[Any, int]] = []
    unreadable = 0
    try:
        listeners = list(bus._listeners.get(EVENT_STATE_CHANGED, ()))
    # An event bus with another layout can raise any error.
    except Exception:  # noqa: BLE001
        return found, unreadable
    for item in listeners:
        try:
            target = item[0].target
            func = getattr(target, "func", target)
            if (
                getattr(func, "__name__", None) != CORE_FORWARD_FUNCTION
                or getattr(func, "__module__", None) != CORE_FORWARD_MODULE
            ):
                continue
        # A listener with another layout does not hold that function, and it is no fault.
        except Exception:  # noqa: BLE001, S112
            continue
        try:
            if not isinstance(target, functools.partial) or target.keywords:
                raise TypeError("the listener is no partial with positional arguments")
            # Exactly these five arguments. One more or one less shifts their places.
            send_message, entity_ids, entity_filter, _user, message_id = target.args
            connection = send_message.__self__
            if not isinstance(message_id, bytes) or not isinstance(
                entity_ids, (set, frozenset, type(None))
            ):
                raise TypeError("an argument has another type")
            msg_id = int(message_id)
            subscriptions = connection.subscriptions
        # The function is there, and its arguments are not as expected.
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        if entity_ids is None and entity_filter is None and msg_id in subscriptions:
            found.append((connection, msg_id))
    return found, unreadable


def adoption_fault(bus: Any) -> str | None:
    """Return why the search for early subscriptions cannot work here, or None when it can.

    The search reads two internals of Home Assistant: the listener table of the event bus,
    and the function CORE_FORWARD_FUNCTION in the module CORE_FORWARD_MODULE. On a version
    that lacks one of them, the search finds nothing and reports nothing by itself.
    """
    if not isinstance(getattr(bus, "_listeners", None), Mapping):
        return "the event bus has no listener table"
    module = sys.modules.get(CORE_FORWARD_MODULE)
    if module is None or not callable(getattr(module, CORE_FORWARD_FUNCTION, None)):
        return f"{CORE_FORWARD_MODULE} has no function {CORE_FORWARD_FUNCTION}"
    return None


class _QuietConnection:
    """A connection whose `send_result` does nothing, and that forwards everything else.

    Home Assistant's subscribe_entities handler answers each call with a result message and
    then with the states. A page already holds its subscription's result, so a second call
    for the same subscription goes through this wrapper.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def send_result(self, msg_id: Any, result: Any | None = None) -> None:
        """Send no second result for a subscription that already has one."""


@dataclass
class _Live:
    """One filtered state subscription that an open page holds."""

    connection: Any
    msg: dict[str, Any]
    entities: frozenset[str]


class LiveSubscriptions:
    """The filtered state subscriptions of the pages that are open now.

    `subscribe(connection, msg)` runs Home Assistant's subscribe_entities handler. That
    handler stores the function that ends its state listener in
    `connection.subscriptions[msg["id"]]`, and sends the states of the entities in
    `msg["entity_ids"]`, or of all entities without that key.

    `validate(msg)` is that command's schema. The handler reads keys that only the schema
    adds, so each message that this object makes passes through it first. A message from a
    page passed through it before the integration's handler got it.
    """

    def __init__(
        self,
        subscribe: Callable[[Any, dict[str, Any]], None],
        validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._subscribe = subscribe
        self._validate = validate
        self._live: dict[tuple[int, Any], _Live] = {}

    def __len__(self) -> int:
        return len(self._live)

    def items(self) -> list[_Live]:
        """Return the live subscriptions, as a list that stays valid during changes."""
        return list(self._live.values())

    def start(
        self, connection: Any, msg: dict[str, Any], entities: Iterable[str]
    ) -> None:
        """Make a page's subscription for these entities, and keep track of it."""
        wanted = frozenset(entities)
        self._subscribe(connection, {**msg, "entity_ids": sorted(wanted)})
        self._track(_Live(connection, dict(msg), wanted))

    def update(self, live: _Live, entities: Iterable[str] | None) -> bool:
        """Give a live subscription a new entity set. None stands for all states.

        The page keeps its subscription ID. It gets the states of the new set, and a
        removal for each entity that left the set. Returns False when the set is unchanged,
        and when the handler fails. After a failure the page keeps its earlier set.
        """
        wanted = None if entities is None else frozenset(entities)
        if wanted == live.entities:
            return False
        msg_id = live.msg["id"]
        key = (id(live.connection), msg_id)
        if self._live.get(key) is not live:
            return False
        if msg_id not in live.connection.subscriptions:
            # The page ended the subscription between the two steps.
            self._live.pop(key, None)
            return False
        if not self._replace(live.connection, live.msg, wanted):
            return False
        self._live.pop(key, None)
        if wanted is None:
            return True
        # The page is in the table before the removal goes out, so a failure of that
        # message leaves no filtered listener that the table does not know.
        self._track(_Live(live.connection, live.msg, wanted))
        removed = live.entities - wanted
        if removed:
            live.connection.send_message(
                {
                    "id": msg_id,
                    "type": "event",
                    "event": {ENTITY_EVENT_REMOVE: sorted(removed)},
                }
            )
        return True

    def adopt(
        self,
        connection: Any,
        msg_id: Any,
        held: Iterable[str],
        entities: Iterable[str],
    ) -> bool:
        """Filter a subscription to all states that this object did not make.

        A page makes such a subscription when Home Assistant's handler answers it, before
        this integration's setup. `held` is each entity that the page can hold now. The
        page keeps its subscription ID. It gets the states of `entities`, and a
        removal for each other entity in `held`. Returns False when the page has no
        subscription with this ID, and when the handler fails. After a failure the page
        keeps its subscription to all states.
        """
        key = (id(connection), msg_id)
        if key in self._live or msg_id not in connection.subscriptions:
            return False
        wanted = frozenset(entities)
        msg: dict[str, Any] = {"id": msg_id, "type": WS_SUBSCRIBE_ENTITIES}
        if self._validate is not None:
            try:
                # The schema adds the keys "include" and "exclude", which the handler reads.
                msg = dict(self._validate(msg))
            except Exception:  # the page keeps its subscription to all states
                _LOGGER.exception(
                    "The schema of %s refused an adoption's message. The page keeps "
                    "all states",
                    WS_SUBSCRIBE_ENTITIES,
                )
                return False
        if not self._replace(connection, msg, wanted):
            return False
        self._track(_Live(connection, msg, wanted))
        removed = frozenset(held) - wanted
        if removed:
            connection.send_message(
                {
                    "id": msg_id,
                    "type": "event",
                    "event": {ENTITY_EVENT_REMOVE: sorted(removed)},
                }
            )
        return True

    def _replace(
        self, connection: Any, msg: dict[str, Any], wanted: frozenset[str] | None
    ) -> bool:
        """Put a new state listener in the place of a subscription's listener.

        `wanted` is the new listener's entity set, and None stands for all states. The
        new listener starts before the old one ends, and no state change can occur
        between the two steps, because nothing here waits. So the page loses no state
        change, and the handler's failure leaves the old listener in its place. Returns
        False then.
        """
        msg_id = msg["id"]
        old = connection.subscriptions.get(msg_id)
        if old is None:
            return False
        new_msg = dict(msg)
        new_msg.pop("entity_ids", None)
        if wanted is not None:
            new_msg["entity_ids"] = sorted(wanted)
        try:
            self._subscribe(_QuietConnection(connection), new_msg)
        except Exception:  # the page keeps the listener that it had
            _LOGGER.exception(
                "The change to an open state subscription failed. The page keeps "
                "the entities that it had"
            )
            # The handler can fail after it put its own listener in the place of the old one.
            half_made = connection.subscriptions.get(msg_id)
            if half_made is not None and half_made is not old:
                try:
                    half_made()
                except Exception:  # the old listener still goes back in its place
                    _LOGGER.exception("The end of a half-made state listener failed")
            connection.subscriptions[msg_id] = old
            return False
        # The handler put the function that ends the new listener in the place of `old`.
        # A listener that _track wrapped ends through its inner function, so that the
        # page's tracking changes only in the caller.
        getattr(old, "inner", old)()
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
