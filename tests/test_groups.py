"""Groups of lite users, and the narrowed state subscriptions that their open pages hold.

The cases come from two sets of panels in one home: a workshop's kiosks, which show
one dashboard, and a kitchen tablet, which shows another.
"""

from __future__ import annotations

import functools
from types import SimpleNamespace
import unittest

from support import load

_const = load("lite_resources.const", "const.py")
_groups = load("lite_resources.groups", "groups.py")

DEFAULT_DASHBOARD = _const.DEFAULT_DASHBOARD
Group = _groups.Group
LiveSubscriptions = _groups.LiveSubscriptions

WORKSHOP = Group(
    "g-workshop",
    "Workshop kiosks",
    {
        "users": ["u-w1", "u-w2"],
        "dashboards": ["dashboard-workshop"],
        "filter_states": True,
    },
)
KITCHEN = Group(
    "g-kitchen",
    "Kitchen tablet",
    {"users": ["u-k"], "dashboards": ["main-dashboard", DEFAULT_DASHBOARD]},
)
GROUPS = [WORKSHOP, KITCHEN]


class GroupLookupTest(unittest.TestCase):
    """Which group a user and a dashboard belong to."""

    def test_group_reads_its_options(self) -> None:
        self.assertEqual(WORKSHOP.users, ["u-w1", "u-w2"])
        self.assertEqual(WORKSHOP.dashboards, ["dashboard-workshop"])
        self.assertTrue(WORKSHOP.filter_states)
        self.assertFalse(KITCHEN.filter_states)

    def test_groups_come_from_group_subentries_only(self) -> None:
        subentries = {
            "a": SimpleNamespace(
                subentry_id="a",
                subentry_type="group",
                title="Workshop kiosks",
                data={"users": ["u-w1"]},
            ),
            "b": SimpleNamespace(
                subentry_id="b", subentry_type="other", title="Other", data={}
            ),
        }
        groups = _groups.groups_from_subentries(subentries)
        self.assertEqual(
            [(g.group_id, g.name) for g in groups], [("a", "Workshop kiosks")]
        )
        self.assertEqual(groups[0].users, ["u-w1"])

    def test_user_maps_to_its_group(self) -> None:
        self.assertIs(_groups.group_for_user(GROUPS, "u-w2"), WORKSHOP)
        self.assertIs(_groups.group_for_user(GROUPS, "u-k"), KITCHEN)
        self.assertIsNone(_groups.group_for_user(GROUPS, "u-phone"))
        self.assertIsNone(_groups.group_for_user(GROUPS, None))

    def test_dashboard_maps_to_each_group_that_shows_it(self) -> None:
        self.assertEqual(
            _groups.groups_with_dashboard(GROUPS, "dashboard-workshop"), [WORKSHOP]
        )
        self.assertEqual(
            _groups.groups_with_dashboard(GROUPS, "main-dashboard"), [KITCHEN]
        )
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, "dashboard-dev"), [])

    def test_lovelace_dashboard_counts_as_the_default_dashboard(self) -> None:
        # Home Assistant shows the dashboard "lovelace" as the default one when it exists.
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, "lovelace"), [KITCHEN])
        named = Group(
            "g-named", "Named", {"users": ["u-n"], "dashboards": ["lovelace"]}
        )
        self.assertEqual(
            _groups.groups_with_dashboard([*GROUPS, named], "lovelace"),
            [KITCHEN, named],
        )
        self.assertEqual(_groups.groups_with_dashboard([named], None), [])

    def test_user_in_two_groups_is_found(self) -> None:
        self.assertEqual(_groups.users_in_two_groups(GROUPS), set())
        second = Group(
            "g-second", "Second", {"users": ["u-w2", "u-x"], "dashboards": ["d"]}
        )
        self.assertEqual(_groups.users_in_two_groups([*GROUPS, second]), {"u-w2"})

    def test_group_has_a_hash(self) -> None:
        self.assertEqual(len({WORKSHOP, KITCHEN, WORKSHOP}), 2)

    def test_default_dashboard_has_no_url_path(self) -> None:
        self.assertEqual(_groups.dashboard_key(None), DEFAULT_DASHBOARD)
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, None), [KITCHEN])

    def test_user_of_another_group_is_reported(self) -> None:
        # A new group that takes a kiosk user and a new user.
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, None, ["u-w1", "u-new"]), {"u-w1"}
        )
        # A change to the workshop group keeps its own users.
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, "g-workshop", ["u-w1", "u-w2"]), set()
        )
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, "g-workshop", ["u-w1", "u-k"]),
            {"u-k"},
        )

    def test_single_group_options_become_group_data(self) -> None:
        options = {
            "users": ["u-w1"],
            "dashboards": ["dashboard-workshop"],
            "always_include": ["/local/a.js"],
            "filter_states": True,
            "unknown": 1,
        }
        self.assertEqual(
            _groups.legacy_group_data(options),
            {
                "users": ["u-w1"],
                "dashboards": ["dashboard-workshop"],
                "always_include": ["/local/a.js"],
                "filter_states": True,
            },
        )

    def test_single_group_options_without_users_give_no_group(self) -> None:
        self.assertIsNone(_groups.legacy_group_data({}))
        self.assertIsNone(_groups.legacy_group_data({"users": [], "dashboards": ["d"]}))


def _schema(msg: dict) -> dict:
    """The schema of subscribe_entities: it adds an empty "include" and "exclude"."""
    return {"include": {}, "exclude": {}, **msg}


def _page_msg(msg_id: int) -> dict:
    """A page's message, as Home Assistant gives it to a handler."""
    return _schema({"id": msg_id, "type": "subscribe_entities"})


class _Connection:
    """A websocket connection that records what it sends."""

    def __init__(self) -> None:
        self.user = SimpleNamespace(id="u-w1", name="Workshop Kiosk 1")
        self.subscriptions: dict = {}
        self.results: list = []
        self.messages: list = []

    def send_result(self, msg_id, result=None) -> None:
        self.results.append(msg_id)

    def send_message(self, message) -> None:
        self.messages.append(message)


class _Core:
    """Home Assistant's subscribe_entities handler, reduced to what the pages see."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        # True makes each call with an entity list fail. True in fail_all makes each call fail.
        self.fail_narrowed = False
        self.fail_all = False

    def subscribe(self, connection, msg) -> None:
        # Home Assistant's handler reads both keys with no default. Its schema adds
        # them, so a message that did not pass the schema raises KeyError here.
        msg["include"], msg["exclude"]
        call = {"entity_ids": msg.get("entity_ids"), "ended": False}
        self.calls.append(call)

        def end() -> None:
            call["ended"] = True

        connection.subscriptions[msg["id"]] = end
        if self.fail_all or (self.fail_narrowed and msg.get("entity_ids") is not None):
            # The failure comes after the listener is in place, which is the worst case.
            raise RuntimeError("the handler failed")
        connection.send_result(msg["id"])
        connection.send_message(
            {"id": msg["id"], "type": "event", "event": {"a": msg.get("entity_ids")}}
        )


class LiveSubscriptionsTest(unittest.TestCase):
    """An open page keeps its subscription ID while its entity set changes."""

    def setUp(self) -> None:
        self.core = _Core()
        self.live = LiveSubscriptions(self.core.subscribe)
        self.connection = _Connection()
        self.msg = _page_msg(5)
        self.live.start(self.connection, self.msg, {"sensor.b", "sensor.a"})

    def test_start_subscribes_to_the_set(self) -> None:
        self.assertEqual(self.core.calls[0]["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(self.connection.results, [5])
        self.assertEqual(len(self.live), 1)

    def test_same_set_changes_nothing(self) -> None:
        item = self.live.items()[0]
        self.assertFalse(self.live.update(item, ["sensor.a", "sensor.b"]))
        self.assertEqual(len(self.core.calls), 1)
        self.assertFalse(self.core.calls[0]["ended"])

    def test_new_set_replaces_the_listener(self) -> None:
        item = self.live.items()[0]
        self.assertTrue(self.live.update(item, {"sensor.a", "sensor.c"}))
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertEqual(self.core.calls[1]["entity_ids"], ["sensor.a", "sensor.c"])
        self.assertFalse(self.core.calls[1]["ended"])
        # The page has its subscription's result. It gets no second one.
        self.assertEqual(self.connection.results, [5])
        # The entity that left the set is removed from the page.
        self.assertEqual(
            self.connection.messages[-1],
            {"id": 5, "type": "event", "event": {"r": ["sensor.b"]}},
        )
        self.assertEqual(len(self.live), 1)
        self.assertEqual(self.live.items()[0].entities, {"sensor.a", "sensor.c"})

    def test_larger_set_sends_no_removal(self) -> None:
        item = self.live.items()[0]
        self.live.update(item, {"sensor.a", "sensor.b", "sensor.c"})
        self.assertEqual(
            self.connection.messages[-1]["event"],
            {"a": ["sensor.a", "sensor.b", "sensor.c"]},
        )

    def test_none_gives_all_states_and_stops_the_tracking(self) -> None:
        item = self.live.items()[0]
        self.assertTrue(self.live.update(item, None))
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertIsNone(self.core.calls[1]["entity_ids"])
        self.assertEqual(self.connection.results, [5])
        self.assertEqual(len(self.live), 0)

    def test_page_that_ends_its_subscription_is_forgotten(self) -> None:
        # Home Assistant calls this function for an unsubscribe and for a closed connection.
        self.connection.subscriptions.pop(5)()
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertEqual(len(self.live), 0)

    def test_stale_item_changes_nothing(self) -> None:
        stale = self.live.items()[0]
        self.live.update(stale, {"sensor.a"})
        self.assertFalse(self.live.update(stale, {"sensor.z"}))
        self.assertEqual(len(self.core.calls), 2)

    def test_subscription_that_is_gone_is_forgotten(self) -> None:
        item = self.live.items()[0]
        self.connection.subscriptions.clear()
        self.assertFalse(self.live.update(item, {"sensor.a"}))
        self.assertEqual(len(self.live), 0)
        self.assertEqual(len(self.core.calls), 1)

    def _assert_page_is_as_before(self) -> None:
        """The page keeps its first listener, its entity set and its place in the table."""
        self.assertFalse(self.core.calls[0]["ended"])
        self.assertEqual(len(self.live), 1)
        item = self.live.items()[0]
        self.assertEqual(item.entities, {"sensor.a", "sensor.b"})
        self.assertIn(5, self.connection.subscriptions)
        self.assertFalse(
            any("r" in message["event"] for message in self.connection.messages)
        )
        # The page can still end its subscription, and the table then forgets it.
        self.connection.subscriptions.pop(5)()
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertEqual(len(self.live), 0)

    def test_failed_change_of_the_set_keeps_the_earlier_listener(self) -> None:
        item = self.live.items()[0]
        self.core.fail_narrowed = True
        with self.assertLogs(_groups._LOGGER, level="ERROR"):
            self.assertFalse(self.live.update(item, {"sensor.a"}))
        # The handler failed after it made its listener. That listener ended.
        self.assertTrue(self.core.calls[1]["ended"])
        self.assertEqual(len(self.core.calls), 2)
        self._assert_page_is_as_before()

    def test_failed_return_to_all_states_keeps_the_earlier_listener(self) -> None:
        item = self.live.items()[0]
        self.core.fail_all = True
        with self.assertLogs(_groups._LOGGER, level="ERROR"):
            self.assertFalse(self.live.update(item, None))
        self.assertTrue(self.core.calls[1]["ended"])
        self._assert_page_is_as_before()

    def test_new_listener_starts_before_the_old_one_ends(self) -> None:
        order: list[str] = []
        first_end = self.connection.subscriptions[5].inner
        self.connection.subscriptions[5].inner = lambda: (
            order.append("old ended"),
            first_end(),
        )
        subscribe = self.core.subscribe

        def recording(connection, msg) -> None:
            order.append("new started")
            subscribe(connection, msg)

        self.live._subscribe = recording
        self.assertTrue(self.live.update(self.live.items()[0], {"sensor.a"}))
        self.assertEqual(order, ["new started", "old ended"])

    def test_two_pages_of_one_connection_are_kept_apart(self) -> None:
        self.live.start(self.connection, _page_msg(9), {"light.k"})
        self.assertEqual(len(self.live), 2)
        first = next(item for item in self.live.items() if item.msg["id"] == 5)
        self.live.update(first, {"sensor.a"})
        other = next(item for item in self.live.items() if item.msg["id"] == 9)
        self.assertEqual(other.entities, {"light.k"})
        self.assertFalse(self.core.calls[1]["ended"])


def _forward_entity_changes(
    send_message, entity_ids, entity_filter, user, message_id, event
):
    """Stand-in for Home Assistant's listener with the same name and arguments."""


# The search takes this function only from the Home Assistant module that defines it.
_forward_entity_changes.__module__ = _groups.CORE_FORWARD_MODULE


def _other_listener(event):
    """Another integration's listener."""


def _job(
    connection,
    msg_id,
    entity_ids=None,
    entity_filter=None,
    func=_forward_entity_changes,
):
    """One item in the listener list of the event bus, in Home Assistant's layout."""
    listener = functools.partial(
        func,
        connection.send_message,
        entity_ids,
        entity_filter,
        connection.user,
        str(msg_id).encode(),
    )
    return (SimpleNamespace(target=listener), None)


class UnfilteredSubscriptionsTest(unittest.TestCase):
    """The state subscriptions for all entities that the event bus holds."""

    def setUp(self) -> None:
        self.page = _Connection()
        self.page.subscriptions[5] = lambda: None

    def _found(self, *jobs):
        bus = SimpleNamespace(_listeners={"state_changed": list(jobs)})
        return _groups.unfiltered_state_subscriptions(bus)

    def test_subscription_for_all_entities_is_found(self) -> None:
        self.assertEqual(self._found(_job(self.page, 5)), [(self.page, 5)])

    def test_subscription_with_a_list_or_a_filter_is_left_out(self) -> None:
        self.assertEqual(self._found(_job(self.page, 5, entity_ids={"sensor.a"})), [])
        self.assertEqual(
            self._found(_job(self.page, 5, entity_filter=lambda e: True)), []
        )

    def test_other_listeners_are_left_out(self) -> None:
        plain = (SimpleNamespace(target=_other_listener), None)
        other = _job(self.page, 5, func=_other_listener)
        broken = ("not a job",)
        # An item that raises an error of another kind at the read.
        odd: dict = {}
        self.assertEqual(self._found(plain, other, broken, odd), [])

    def test_function_of_the_same_name_in_another_module_is_left_out(self) -> None:
        def _forward_entity_changes(
            send_message, entity_ids, entity_filter, user, message_id, event
        ):
            """A copy of Home Assistant's listener in another integration."""

        self.assertEqual(
            self._found(_job(self.page, 5, func=_forward_entity_changes)), []
        )

    def test_subscription_that_the_page_ended_is_left_out(self) -> None:
        self.assertEqual(self._found(_job(self.page, 9)), [])

    def test_missing_internals_are_reported(self) -> None:
        import sys
        import types

        name = _groups.CORE_FORWARD_MODULE
        saved = sys.modules.get(name)
        bus = SimpleNamespace(_listeners={})
        try:
            module = types.ModuleType(name)
            module._forward_entity_changes = _forward_entity_changes
            sys.modules[name] = module
            self.assertIsNone(_groups.adoption_fault(bus))
            self.assertIn("listener table", _groups.adoption_fault(SimpleNamespace()))
            del module._forward_entity_changes
            self.assertIn("_forward_entity_changes", _groups.adoption_fault(bus))
        finally:
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved

    def test_event_bus_of_another_layout_gives_nothing(self) -> None:
        self.assertEqual(_groups.unfiltered_state_subscriptions(SimpleNamespace()), [])
        self.assertEqual(
            _groups.unfiltered_state_subscriptions(SimpleNamespace(_listeners={})), []
        )


class AdoptTest(unittest.TestCase):
    """A subscription for all entities that Home Assistant's handler made."""

    def setUp(self) -> None:
        self.core = _Core()
        self.live = LiveSubscriptions(self.core.subscribe, _schema)
        self.connection = _Connection()
        # The page subscribed with Home Assistant's handler.
        self.core.subscribe(self.connection, _page_msg(5))

    def test_adopted_subscription_is_narrowed_in_place(self) -> None:
        held = ["sensor.a", "sensor.b", "sensor.other"]
        self.assertTrue(
            self.live.adopt(self.connection, 5, held, {"sensor.a", "sensor.b"})
        )
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertEqual(self.core.calls[1]["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(self.connection.results, [5])
        self.assertEqual(
            self.connection.messages[-1],
            {"id": 5, "type": "event", "event": {"r": ["sensor.other"]}},
        )
        self.assertEqual(len(self.live), 1)

    def test_adopted_subscription_is_narrowed_also_when_the_page_holds_no_other_entity(
        self,
    ) -> None:
        # Early in a start, the page can hold only the entities on its dashboards.
        self.assertTrue(
            self.live.adopt(self.connection, 5, ["sensor.a"], {"sensor.a", "sensor.b"})
        )
        self.assertTrue(self.core.calls[0]["ended"])
        self.assertEqual(self.core.calls[1]["entity_ids"], ["sensor.a", "sensor.b"])

    def test_adopted_subscription_follows_a_later_change(self) -> None:
        self.live.adopt(self.connection, 5, ["sensor.a", "sensor.x"], {"sensor.a"})
        item = self.live.items()[0]
        self.assertTrue(self.live.update(item, {"sensor.a", "sensor.c"}))
        self.assertEqual(self.core.calls[-1]["entity_ids"], ["sensor.a", "sensor.c"])

    def _assert_page_keeps_all_states(self) -> None:
        """The page keeps the listener for all entities that Home Assistant made."""
        self.assertFalse(self.core.calls[0]["ended"])
        self.assertIsNone(self.core.calls[0]["entity_ids"])
        self.assertIn(5, self.connection.subscriptions)
        self.assertEqual(len(self.live), 0)
        self.assertFalse(
            any("r" in message["event"] for message in self.connection.messages)
        )
        # The connection's function still ends that first listener.
        self.connection.subscriptions.pop(5)()
        self.assertTrue(self.core.calls[0]["ended"])

    def test_adopted_message_passes_the_schema_of_the_command(self) -> None:
        # Home Assistant's handler reads keys that only its schema adds.
        self.assertTrue(self.live.adopt(self.connection, 5, ["sensor.a"], {"sensor.a"}))
        item = self.live.items()[0]
        self.assertEqual(item.msg["include"], {})
        self.assertEqual(item.msg["exclude"], {})

    def test_adoption_with_no_schema_fails_and_changes_nothing(self) -> None:
        # A message that did not pass the schema makes the handler fail. That was the
        # fault in the first 0.3.4 code. The page must then keep its first listener.
        live = LiveSubscriptions(self.core.subscribe)
        with self.assertLogs(_groups._LOGGER, level="ERROR"):
            self.assertFalse(live.adopt(self.connection, 5, ["sensor.a"], {"sensor.a"}))
        self.assertEqual(len(self.core.calls), 1)
        self._assert_page_keeps_all_states()

    def test_schema_that_refuses_the_message_changes_nothing(self) -> None:
        def refuse(msg: dict) -> dict:
            raise ValueError("extra keys not allowed")

        live = LiveSubscriptions(self.core.subscribe, refuse)
        with self.assertLogs(_groups._LOGGER, level="ERROR"):
            self.assertFalse(live.adopt(self.connection, 5, ["sensor.a"], {"sensor.a"}))
        self.assertEqual(len(self.core.calls), 1)
        self._assert_page_keeps_all_states()

    def test_failed_adoption_keeps_the_subscription_for_all_entities(self) -> None:
        self.core.fail_narrowed = True
        with self.assertLogs(_groups._LOGGER, level="ERROR") as logs:
            self.assertFalse(
                self.live.adopt(
                    self.connection, 5, ["sensor.a", "sensor.x"], {"sensor.a"}
                )
            )
        self.assertEqual(len(logs.records), 1)
        # The handler failed after it made its listener. That listener ended.
        self.assertTrue(self.core.calls[1]["ended"])
        self._assert_page_keeps_all_states()

    def test_missing_subscription_is_not_adopted(self) -> None:
        self.assertFalse(
            self.live.adopt(self.connection, 9, ["sensor.a"], {"sensor.a"})
        )
        self.assertEqual(len(self.core.calls), 1)

    def test_subscription_of_this_object_is_not_adopted(self) -> None:
        other = _Connection()
        self.live.start(other, _page_msg(7), {"sensor.a"})
        self.assertFalse(
            self.live.adopt(other, 7, ["sensor.a", "sensor.b"], {"sensor.b"})
        )
        self.assertEqual(self.live.items()[0].entities, {"sensor.a"})
        self.assertIn(7, other.subscriptions)


if __name__ == "__main__":
    unittest.main()
