"""The integration set up with two groups of lite users.

The workshop kiosks show one dashboard and the kitchen tablet shows another. Each user gets
the resources and the states of the dashboards of its own group, and an open page follows a
change of its dashboard and of its group. The resolver has its own tests, so here two
stand-ins answer for it from a table.
"""

from __future__ import annotations

import asyncio
import functools
import unittest
from types import SimpleNamespace

from support import ConfigSubentry, Event, install_homeassistant_stubs, load

install_homeassistant_stubs()

load("lite_resources.const", "const.py")
load("lite_resources.groups", "groups.py")
load("lite_resources.resolver", "resolver.py")
_entry = load("lite_resources.entry_module", "__init__.py")

# The 5000 entities of the home. The dashboards of the groups show four of them.
ALL_ENTITIES = [f"sensor.other_{number}" for number in range(4996)] + [
    "sensor.a",
    "sensor.b",
    "light.k",
    "sensor.c",
]

USERS = {
    "u-w1": "Workshop Kiosk 1",
    "u-w2": "Workshop Kiosk 2",
    "u-k": "Kitchen Tablet",
    "u-phone": "Phone",
}


async def _dashboard_entities(hass, options, include_missing=False) -> set[str]:
    """Stand-in for resolver.async_dashboard_entities."""
    hass.include_missing.append(include_missing)
    found = set(options.get("extra_entities", []))
    for key in options["dashboards"]:
        found |= hass.dashboard_entities[key]
    return found


async def _resolve(hass, options, cache) -> SimpleNamespace:
    """Stand-in for resolver.async_resolve: one resource for each dashboard."""
    included = [{"url": f"/local/{key}.js"} for key in options["dashboards"]]
    return SimpleNamespace(
        included=included,
        excluded=[{"url": "/local/unused.js"}],
        unresolved_types=[],
        as_dict=lambda: {"included": [item["url"] for item in included]},
    )


def _core_resources(hass, connection, msg) -> None:
    """The lovelace/resources handler of Home Assistant: every resource."""
    connection.send_result(msg["id"], "every resource")


def _forward_entity_changes(send_message, entity_ids, entity_filter, user, message_id, event):
    """Stand-in for the listener of Home Assistant with the same name and arguments."""


def _core_subscribe(hass, connection, msg) -> None:
    """The subscribe_entities handler of Home Assistant, reduced to what the pages see.

    As in Home Assistant, the listener is a partial of _forward_entity_changes in the
    listener list of the event bus, and the connection keeps the function that removes it.
    """
    call = {"user": connection.user.id, "entity_ids": msg.get("entity_ids"), "ended": False}
    hass.core_subscriptions.append(call)
    listener = functools.partial(
        _forward_entity_changes,
        connection.send_message,
        set(msg["entity_ids"]) if msg.get("entity_ids") else None,
        None,
        connection.user,
        str(msg["id"]).encode(),
    )
    job = (SimpleNamespace(target=listener), None)
    listeners = hass.bus._listeners.setdefault("state_changed", [])
    listeners.append(job)

    def end() -> None:
        call["ended"] = True
        listeners.remove(job)

    connection.subscriptions[msg["id"]] = end
    connection.send_result(msg["id"])
    connection.send_message(
        {"id": msg["id"], "type": "event", "event": {"a": msg.get("entity_ids")}}
    )


class _Connection:
    """A websocket connection that records what it sends."""

    def __init__(self, user_id: str) -> None:
        self.user = SimpleNamespace(id=user_id, name=USERS[user_id])
        self.subscriptions: dict = {}
        self.results: list = []
        self.messages: list = []

    def send_result(self, msg_id, result=None) -> None:
        self.results.append((msg_id, result))

    def send_message(self, message) -> None:
        self.messages.append(message)


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        # The listener list of the event bus of Home Assistant, for the state listeners.
        self._listeners: dict[str, list] = {}

    def async_listen(self, event_type, listener):
        self.listeners.setdefault(event_type, []).append(listener)
        return lambda: self.listeners[event_type].remove(listener)

    def async_listen_once(self, event_type, listener):
        """The listener leaves the bus before it runs, as in Home Assistant."""

        def once(event) -> None:
            self.listeners[event_type].remove(once)
            listener(event)

        self.listeners.setdefault(event_type, []).append(once)
        return lambda: self.listeners[event_type].remove(once)

    def fire(self, event_type, data) -> None:
        for listener in list(self.listeners.get(event_type, [])):
            listener(Event(data))


class _Services:
    def __init__(self) -> None:
        self.registered: dict = {}

    def async_register(self, domain, name, func, supports_response=None) -> None:
        self.registered[(domain, name)] = func

    def async_remove(self, domain, name) -> None:
        self.registered.pop((domain, name), None)


class _ConfigEntries:
    def async_add_subentry(self, entry, subentry) -> bool:
        entry.subentries = {**entry.subentries, subentry.subentry_id: subentry}
        return True

    def async_update_entry(self, entry, **changes) -> bool:
        for name, value in changes.items():
            setattr(entry, name, value)
        return True


class _Auth:
    async def async_get_user(self, user_id):
        name = USERS.get(user_id)
        return SimpleNamespace(id=user_id, name=name) if name else None


class _Hass:
    def __init__(self, is_running: bool = True) -> None:
        self.is_running = is_running
        self.include_missing: list[bool] = []
        self.data = {
            "websocket_api": {
                "lovelace/resources": (_core_resources, "resources schema"),
                "subscribe_entities": (_core_subscribe, "states schema"),
            }
        }
        self.bus = _Bus()
        self.services = _Services()
        self.config_entries = _ConfigEntries()
        self.auth = _Auth()
        self.states = SimpleNamespace(async_entity_ids=lambda: list(ALL_ENTITIES))
        self.dashboard_entities = {
            "dashboard-workshop": {"sensor.a", "sensor.b"},
            "main-dashboard": {"light.k", "sensor.b"},
        }
        self.core_subscriptions: list[dict] = []
        self.tasks: list = []

    def async_create_task(self, coro, name=None, eager_start=False):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task

    async def drain(self) -> None:
        """Wait for each task that a handler or a listener started."""
        while self.tasks:
            await self.tasks.pop(0)


class _Entry:
    def __init__(self, version=2, options=None, subentries=()) -> None:
        self.version = version
        self.options = options or {}
        self.subentries = {sub.subentry_id: sub for sub in subentries}
        self.unload: list = []
        self.update_listeners: list = []

    def async_on_unload(self, func) -> None:
        self.unload.append(func)

    def add_update_listener(self, listener):
        self.update_listeners.append(listener)
        return lambda: self.update_listeners.remove(listener)


def _group(title, users, dashboards, **more) -> ConfigSubentry:
    data = {"users": users, "dashboards": dashboards, "filter_states": True, **more}
    return ConfigSubentry(data=data, subentry_type="group", title=title, unique_id=None)


class SetupEntryTest(unittest.IsolatedAsyncioTestCase):
    """Two groups, each with its own users and dashboards."""

    async def asyncSetUp(self) -> None:
        self._saved = (_entry.async_dashboard_entities, _entry.async_resolve)
        _entry.async_dashboard_entities = _dashboard_entities
        _entry.async_resolve = _resolve
        self.hass = _Hass()
        self.workshop = _group(
            "Workshop kiosks", ["u-w1", "u-w2"], ["dashboard-workshop"]
        )
        self.kitchen = _group("Kitchen tablet", ["u-k"], ["main-dashboard"])
        self.entry = _Entry(subentries=[self.workshop, self.kitchen])
        self.assertTrue(await _entry.async_setup_entry(self.hass, self.entry))
        self.commands = self.hass.data["websocket_api"]

    async def asyncTearDown(self) -> None:
        _entry.async_dashboard_entities, _entry.async_resolve = self._saved

    async def _resources(self, user_id: str):
        connection = _Connection(user_id)
        handler, _schema = self.commands["lovelace/resources"]
        await handler(self.hass, connection, {"id": 1, "type": "lovelace/resources"})
        return connection.results[-1][1]

    async def _open_page(self, user_id: str, msg_id: int = 5, **more) -> _Connection:
        connection = _Connection(user_id)
        handler, _schema = self.commands["subscribe_entities"]
        handler(
            self.hass, connection, {"id": msg_id, "type": "subscribe_entities", **more}
        )
        await self.hass.drain()
        return connection

    def _calls(self, user_id: str) -> list[dict]:
        return [c for c in self.hass.core_subscriptions if c["user"] == user_id]

    async def test_resources_follow_the_group_of_the_user(self) -> None:
        self.assertEqual(
            await self._resources("u-w2"), [{"url": "/local/dashboard-workshop.js"}]
        )
        self.assertEqual(
            await self._resources("u-k"), [{"url": "/local/main-dashboard.js"}]
        )

    async def test_user_in_no_group_gets_every_resource(self) -> None:
        self.assertEqual(await self._resources("u-phone"), "every resource")

    async def test_states_follow_the_group_of_the_user(self) -> None:
        await self._open_page("u-w1")
        await self._open_page("u-k")
        self.assertEqual(self._calls("u-w1")[0]["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(self._calls("u-k")[0]["entity_ids"], ["light.k", "sensor.b"])

    async def test_user_in_no_group_gets_every_state(self) -> None:
        await self._open_page("u-phone")
        self.assertIsNone(self._calls("u-phone")[0]["entity_ids"])

    async def test_request_with_its_own_entities_is_not_changed(self) -> None:
        await self._open_page("u-w1", entity_ids=["sensor.z"])
        self.assertEqual(self._calls("u-w1")[0]["entity_ids"], ["sensor.z"])

    async def test_group_with_the_state_filter_off_gets_every_state(self) -> None:
        off = _group("Hall panel", ["u-phone"], ["main-dashboard"])
        off.data["filter_states"] = False
        self.entry.subentries = {**self.entry.subentries, off.subentry_id: off}
        await self._open_page("u-phone")
        self.assertIsNone(self._calls("u-phone")[0]["entity_ids"])
        self.assertEqual(
            await self._resources("u-phone"), [{"url": "/local/main-dashboard.js"}]
        )

    async def test_changed_dashboard_updates_the_open_pages_of_its_group(self) -> None:
        kiosk = await self._open_page("u-w1")
        tablet = await self._open_page("u-k", msg_id=7)
        # The design user replaces a card: sensor.b leaves the dashboard, sensor.c enters.
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.a", "sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()

        first, second = self._calls("u-w1")
        self.assertTrue(first["ended"])
        self.assertEqual(second["entity_ids"], ["sensor.a", "sensor.c"])
        self.assertFalse(second["ended"])
        self.assertEqual(kiosk.results, [(5, None)])
        self.assertEqual(
            kiosk.messages[-1], {"id": 5, "type": "event", "event": {"r": ["sensor.b"]}}
        )
        # The kitchen tablet shows another dashboard. Its page stays as it was.
        self.assertEqual(len(self._calls("u-k")), 1)
        self.assertFalse(self._calls("u-k")[0]["ended"])
        self.assertEqual(len(tablet.messages), 1)

    async def test_changed_dashboard_of_no_group_changes_nothing(self) -> None:
        await self._open_page("u-w1")
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-dev"})
        await self.hass.drain()
        self.assertEqual(len(self.hass.core_subscriptions), 1)

    async def test_event_that_names_no_dashboard_changes_nothing(self) -> None:
        # The default dashboard has the URL path None. An event with no URL path is not it.
        default = _group("Hall panel", ["u-phone"], ["__default__"])
        self.entry.subentries = {**self.entry.subentries, default.subentry_id: default}
        self.hass.dashboard_entities["__default__"] = {"sensor.a"}
        await self._open_page("u-phone")
        self.hass.dashboard_entities["__default__"] = {"sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"resource_type": "resources"})
        await self.hass.drain()
        self.assertEqual(len(self._calls("u-phone")), 1)
        self.hass.bus.fire("lovelace_updated", {"url_path": None})
        await self.hass.drain()
        self.assertEqual(self._calls("u-phone")[-1]["entity_ids"], ["sensor.c"])

    async def test_changed_dashboard_reaches_a_page_opened_later(self) -> None:
        self.hass.dashboard_entities["main-dashboard"] = {"light.k", "lock.front"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "main-dashboard"})
        await self.hass.drain()
        await self._open_page("u-k")
        self.assertEqual(self._calls("u-k")[0]["entity_ids"], ["light.k", "lock.front"])

    async def test_closed_page_is_not_updated(self) -> None:
        kiosk = await self._open_page("u-w1")
        kiosk.subscriptions.pop(5)()
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        self.assertEqual(len(self._calls("u-w1")), 1)

    async def test_changed_group_updates_its_open_pages(self) -> None:
        kiosk = await self._open_page("u-w1")
        changed = _group(
            "Workshop kiosks",
            ["u-w1", "u-w2"],
            ["dashboard-workshop"],
            extra_entities=["sensor.extra"],
        )
        self.entry.subentries = {
            self.workshop.subentry_id: changed,
            self.kitchen.subentry_id: self.kitchen,
        }
        for listener in self.entry.update_listeners:
            await listener(self.hass, self.entry)
        self.assertEqual(
            self._calls("u-w1")[-1]["entity_ids"],
            ["sensor.a", "sensor.b", "sensor.extra"],
        )
        self.assertEqual(kiosk.results, [(5, None)])

    async def test_user_that_leaves_its_group_gets_every_state(self) -> None:
        kiosk = await self._open_page("u-w1")
        self.entry.subentries = {self.kitchen.subentry_id: self.kitchen}
        for listener in self.entry.update_listeners:
            await listener(self.hass, self.entry)
        first, second = self._calls("u-w1")
        self.assertTrue(first["ended"])
        self.assertIsNone(second["entity_ids"])
        self.assertEqual(kiosk.results, [(5, None)])
        self.assertEqual(await self._resources("u-w1"), "every resource")

    async def test_preview_lists_each_group(self) -> None:
        await self._open_page("u-w1")
        preview = self.hass.services.registered[("lite_resources", "preview")]
        response = await preview(None)
        self.assertEqual(response["open_pages_with_narrowed_states"], 1)
        workshop, kitchen = response["groups"]
        self.assertEqual(workshop["group"], "Workshop kiosks")
        self.assertEqual(workshop["users"], ["Workshop Kiosk 1", "Workshop Kiosk 2"])
        self.assertEqual(workshop["included"], ["/local/dashboard-workshop.js"])
        self.assertEqual(workshop["state_entities"], ["sensor.a", "sensor.b"])
        self.assertEqual(workshop["state_entities_count"], "2 of 5000")
        self.assertEqual(kitchen["group"], "Kitchen tablet")
        self.assertEqual(kitchen["state_entities"], ["light.k", "sensor.b"])

    async def test_unload_restores_the_handlers_of_home_assistant(self) -> None:
        for func in self.entry.unload:
            func()
        self.assertEqual(
            self.commands["lovelace/resources"], (_core_resources, "resources schema")
        )
        self.assertEqual(
            self.commands["subscribe_entities"], (_core_subscribe, "states schema")
        )
        self.assertEqual(self.hass.services.registered, {})
        self.assertEqual(self.hass.bus.listeners["lovelace_updated"], [])
        self.assertEqual(self.entry.update_listeners, [])


class EarlyPageTest(unittest.IsolatedAsyncioTestCase):
    """A page that connected before Home Assistant set the integration up.

    After a restart, a kiosk page connects again within seconds. Home Assistant sets a
    custom integration up later, so the handler of Home Assistant answers the first state
    subscription of that page, with every entity. One kiosk went from 95 entities to
    5573 that way, and its page fell 200 seconds behind.
    """

    async def asyncSetUp(self) -> None:
        self._saved = (_entry.async_dashboard_entities, _entry.async_resolve)
        _entry.async_dashboard_entities = _dashboard_entities
        _entry.async_resolve = _resolve
        self.hass = _Hass()
        self.entry = _Entry(
            subentries=[_group("Workshop kiosks", ["u-w1", "u-w2"], ["dashboard-workshop"])]
        )

    async def asyncTearDown(self) -> None:
        _entry.async_dashboard_entities, _entry.async_resolve = self._saved

    def _early_page(self, user_id: str, **more) -> _Connection:
        """A page subscribes before the setup, so the handler of Home Assistant answers."""
        connection = _Connection(user_id)
        _core_subscribe(self.hass, connection, {"id": 5, "type": "subscribe_entities", **more})
        return connection

    async def _setup(self) -> None:
        await _entry.async_setup_entry(self.hass, self.entry)
        await self.hass.drain()

    def _calls(self, user_id: str) -> list[dict]:
        return [c for c in self.hass.core_subscriptions if c["user"] == user_id]

    async def test_early_page_of_a_lite_user_is_narrowed_at_the_setup(self) -> None:
        kiosk = self._early_page("u-w1")
        await self._setup()
        first, second = self._calls("u-w1")
        self.assertTrue(first["ended"])
        self.assertEqual(second["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertFalse(second["ended"])
        # The page has the result of its subscription. It gets no second one.
        self.assertEqual(kiosk.results, [(5, None)])
        # The page drops each entity that it holds and that its dashboards do not show.
        removed = kiosk.messages[-1]["event"]["r"]
        self.assertEqual(len(removed), 4998)
        self.assertIn("sensor.other_0", removed)
        self.assertIn("light.k", removed)
        self.assertNotIn("sensor.a", removed)
        # The narrowed subscription follows a changed dashboard like any other.
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.a", "sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        self.assertEqual(self._calls("u-w1")[-1]["entity_ids"], ["sensor.a", "sensor.c"])

    async def test_early_page_of_another_user_keeps_every_state(self) -> None:
        phone = self._early_page("u-phone")
        await self._setup()
        (call,) = self._calls("u-phone")
        self.assertFalse(call["ended"])
        self.assertEqual(len(phone.messages), 1)

    async def test_early_subscription_with_its_own_entities_is_not_changed(self) -> None:
        self._early_page("u-w1", entity_ids=["sensor.c"])
        await self._setup()
        (call,) = self._calls("u-w1")
        self.assertFalse(call["ended"])

    async def test_event_bus_of_another_layout_changes_nothing(self) -> None:
        self._early_page("u-w1")
        del self.hass.bus._listeners
        await self._setup()
        (call,) = self._calls("u-w1")
        self.assertFalse(call["ended"])

    async def test_user_that_joins_a_group_is_narrowed_at_once(self) -> None:
        await self._setup()
        handler, _schema = self.hass.data["websocket_api"]["subscribe_entities"]
        tablet = _Connection("u-k")
        handler(self.hass, tablet, {"id": 7, "type": "subscribe_entities"})
        await self.hass.drain()
        self.assertIsNone(self._calls("u-k")[0]["entity_ids"])
        kitchen = _group("Kitchen tablet", ["u-k"], ["main-dashboard"])
        self.entry.subentries = {**self.entry.subentries, kitchen.subentry_id: kitchen}
        for listener in self.entry.update_listeners:
            await listener(self.hass, self.entry)
        await self.hass.drain()
        first, second = self._calls("u-k")
        self.assertTrue(first["ended"])
        self.assertEqual(second["entity_ids"], ["light.k", "sensor.b"])
        self.assertEqual(tablet.results, [(7, None)])


class StartupTest(unittest.IsolatedAsyncioTestCase):
    """A page that connects while Home Assistant starts gets its full set after the start."""

    async def asyncSetUp(self) -> None:
        self._saved = (_entry.async_dashboard_entities, _entry.async_resolve)
        _entry.async_dashboard_entities = _dashboard_entities
        _entry.async_resolve = _resolve

    async def asyncTearDown(self) -> None:
        _entry.async_dashboard_entities, _entry.async_resolve = self._saved

    async def _setup(self, is_running: bool):
        hass = _Hass(is_running=is_running)
        entry = _Entry(subentries=[_group("Kitchen tablet", ["u-k"], ["main-dashboard"])])
        await _entry.async_setup_entry(hass, entry)
        return hass, entry

    async def test_page_is_updated_when_the_start_is_complete(self) -> None:
        hass, entry = await self._setup(is_running=False)
        connection = _Connection("u-k")
        handler, _schema = hass.data["websocket_api"]["subscribe_entities"]
        handler(hass, connection, {"id": 5, "type": "subscribe_entities"})
        await hass.drain()
        # A group entity got its state after the page connected, so it has a member now.
        hass.dashboard_entities["main-dashboard"] = {"light.k", "sensor.b", "light.k_member"}
        hass.bus.fire("homeassistant_started", {})
        await hass.drain()
        calls = [c for c in hass.core_subscriptions if c["user"] == "u-k"]
        self.assertEqual(calls[-1]["entity_ids"], ["light.k", "light.k_member", "sensor.b"])
        self.assertEqual(connection.results, [(5, None)])
        # The listener ran once. The unload does not remove it a second time.
        self.assertEqual(hass.bus.listeners["homeassistant_started"], [])
        for func in entry.unload:
            func()

    async def test_unload_before_the_start_removes_the_listener(self) -> None:
        hass, entry = await self._setup(is_running=False)
        self.assertEqual(len(hass.bus.listeners["homeassistant_started"]), 1)
        for func in entry.unload:
            func()
        self.assertEqual(hass.bus.listeners["homeassistant_started"], [])

    async def test_running_home_assistant_needs_no_listener(self) -> None:
        hass, _unused = await self._setup(is_running=True)
        self.assertNotIn("homeassistant_started", hass.bus.listeners)

    async def test_subscription_asks_for_the_entities_with_no_state_yet(self) -> None:
        hass, _unused = await self._setup(is_running=True)
        handler, _schema = hass.data["websocket_api"]["subscribe_entities"]
        handler(hass, _Connection("u-k"), {"id": 5, "type": "subscribe_entities"})
        await hass.drain()
        self.assertEqual(hass.include_missing, [True])
        # The preview lists the entities that have a state.
        await hass.services.registered[("lite_resources", "preview")](None)
        self.assertEqual(hass.include_missing, [True, False])


class SetupWithoutLovelaceTest(unittest.IsolatedAsyncioTestCase):
    """Home Assistant tries the setup again when the dashboards are not set up yet."""

    async def test_setup_waits_for_the_dashboards(self) -> None:
        hass = _Hass()
        hass.data = {"websocket_api": {}}
        with self.assertRaises(_entry.ConfigEntryNotReady):
            await _entry.async_setup_entry(hass, _Entry())


class MigrationTest(unittest.IsolatedAsyncioTestCase):
    """The settings of a single-group version become the first group."""

    async def test_single_group_options_become_one_group(self) -> None:
        options = {
            "users": ["u-w1", "u-w2"],
            "dashboards": ["dashboard-workshop"],
            "always_include": ["/local/a.js"],
            "always_exclude": [],
            "include_unscannable": True,
            "filter_states": True,
            "extra_entities": [],
        }
        entry = _Entry(version=1, options=dict(options))
        self.assertTrue(await _entry.async_migrate_entry(_Hass(), entry))
        self.assertEqual(entry.version, 2)
        self.assertEqual(entry.options, {})
        (group,) = entry.subentries.values()
        self.assertEqual(group.subentry_type, "group")
        self.assertEqual(group.title, "Lite users")
        self.assertEqual(dict(group.data), options)

    async def test_setup_without_users_gets_no_group(self) -> None:
        entry = _Entry(version=1, options={"users": [], "dashboards": []})
        self.assertTrue(await _entry.async_migrate_entry(_Hass(), entry))
        self.assertEqual(entry.version, 2)
        self.assertEqual(entry.subentries, {})

    async def test_current_version_is_left_alone(self) -> None:
        group = _group("Workshop kiosks", ["u-w1"], ["dashboard-workshop"])
        entry = _Entry(version=2, subentries=[group])
        self.assertTrue(await _entry.async_migrate_entry(_Hass(), entry))
        self.assertEqual(list(entry.subentries.values()), [group])


if __name__ == "__main__":
    unittest.main()
