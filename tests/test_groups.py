"""Groups of lite users, and the narrowed state subscriptions of their open pages.

The cases come from two sets of panels in one home: the kiosks of a workshop, which show
one dashboard, and a kitchen tablet, which shows another.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from support import load

_const = load("lite_resources.const", "const.py")
_groups = load("lite_resources.groups", "groups.py")

DEFAULT_DASHBOARD = _const.DEFAULT_DASHBOARD
Group = _groups.Group
LiveSubscriptions = _groups.LiveSubscriptions

WORKSHOP = Group(
    "g-workshop",
    "Workshop kiosks",
    {"users": ["u-w1", "u-w2"], "dashboards": ["dashboard-workshop"], "filter_states": True},
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
        self.assertEqual([(g.group_id, g.name) for g in groups], [("a", "Workshop kiosks")])
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
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, "main-dashboard"), [KITCHEN])
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, "dashboard-dev"), [])

    def test_default_dashboard_has_no_url_path(self) -> None:
        self.assertEqual(_groups.dashboard_key(None), DEFAULT_DASHBOARD)
        self.assertEqual(_groups.groups_with_dashboard(GROUPS, None), [KITCHEN])

    def test_user_of_another_group_is_reported(self) -> None:
        # A new group that takes a kiosk user and a new user.
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, None, ["u-w1", "u-new"]), {"u-w1"}
        )
        # A change of the workshop group keeps its own users.
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, "g-workshop", ["u-w1", "u-w2"]), set()
        )
        self.assertEqual(
            _groups.users_in_other_groups(GROUPS, "g-workshop", ["u-w1", "u-k"]), {"u-k"}
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
    """The subscribe_entities handler of Home Assistant, reduced to what the pages see."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def subscribe(self, connection, msg) -> None:
        call = {"entity_ids": msg.get("entity_ids"), "ended": False}
        self.calls.append(call)

        def end() -> None:
            call["ended"] = True

        connection.subscriptions[msg["id"]] = end
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
        self.msg = {"id": 5, "type": "subscribe_entities"}
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
        # The page has the result of its subscription. It gets no second one.
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

    def test_two_pages_of_one_connection_are_kept_apart(self) -> None:
        self.live.start(self.connection, {"id": 9, "type": "subscribe_entities"}, {"light.k"})
        self.assertEqual(len(self.live), 2)
        first = next(item for item in self.live.items() if item.msg["id"] == 5)
        self.live.update(first, {"sensor.a"})
        other = next(item for item in self.live.items() if item.msg["id"] == 9)
        self.assertEqual(other.entities, {"light.k"})
        self.assertFalse(self.core.calls[1]["ended"])


if __name__ == "__main__":
    unittest.main()
