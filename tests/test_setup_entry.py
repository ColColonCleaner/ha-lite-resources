"""The integration set up with two groups of lite users.

The workshop kiosks show one dashboard and the kitchen tablet shows another. Each user gets
the resources and the states for the dashboards in its own group, and an open page follows
a change to its dashboard and to its group. The resolver has its own tests, so here two stand-ins answer
for it from a table.
"""

from __future__ import annotations

import asyncio
import functools
import sys
import types
from types import SimpleNamespace
import unittest

from support import (
    ConfigSubentry,
    Event,
    Unauthorized as _Unauthorized,
    empty_filter_part,
    install_homeassistant_stubs,
    load,
)

install_homeassistant_stubs()

load("lite_resources.const", "const.py")
load("lite_resources.groups", "groups.py")
_resolver = load("lite_resources.resolver", "resolver.py")
_entry = load("lite_resources.entry_module", "__init__.py")

# The home's 5000 entities. The groups' dashboards show four of them.
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
    "u-admin": "Administrator",
}


async def _dashboard_entities(hass, options, include_missing=False) -> set[str]:
    """Stand-in for resolver.async_dashboard_entities.

    `hass.scan_suspends` makes the scan wait that number of event loop turns, as the
    first load of a dashboard does. `hass.scan_seconds` makes it wait that time, as a
    load from a slow share does. `hass.scan_error` makes it raise that error.
    """
    hass.include_missing.append(include_missing)
    for _turn in range(hass.scan_suspends):
        await asyncio.sleep(0)
    if hass.scan_seconds:
        await asyncio.sleep(hass.scan_seconds)
    if hass.scan_error is not None:
        raise hass.scan_error
    found = set(options.get("extra_entities", []))
    for key in options["dashboards"]:
        found |= hass.dashboard_entities[key]
    return found


async def _resolve(hass, options, cache) -> SimpleNamespace:
    """Stand-in for resolver.async_resolve: one resource for each dashboard.

    `hass.resolve_error` makes it raise that error, and `hass.resolve_gaps` gives it these
    card types with no provider. `hass.resolve_suspends` makes it wait that number of
    event loop turns, as the read of the resource files does.
    """
    for _turn in range(hass.resolve_suspends):
        await asyncio.sleep(0)
    if hass.resolve_error is not None:
        raise hass.resolve_error
    gaps = dict(hass.resolve_gaps)
    included = [{"url": f"/local/{key}.js"} for key in options["dashboards"]]
    if gaps:
        return SimpleNamespace(
            included=included,
            excluded=[],
            unresolved_types=gaps.get("unresolved", []),
            unverified_types=gaps.get("unverified", []),
            guessed_types=gaps.get("guessed", []),
            as_dict=lambda: {"included": [item["url"] for item in included]},
        )
    return SimpleNamespace(
        included=included,
        excluded=[{"url": "/local/unused.js"}],
        unresolved_types=[],
        unverified_types=[],
        guessed_types=[],
        as_dict=lambda: {"included": [item["url"] for item in included]},
    )


def _core_resources(hass, connection, msg) -> None:
    """Home Assistant's lovelace/resources handler: every resource."""
    connection.send_result(msg["id"], "every resource")


def _forward_entity_changes(
    send_message, entity_ids, entity_filter, user, message_id, event
):
    """Stand-in for Home Assistant's listener with the same name and arguments."""


# The search takes this function only from the Home Assistant module that defines it.
_COMMANDS = "homeassistant.components.websocket_api.commands"
_forward_entity_changes.__module__ = _COMMANDS
_commands = sys.modules.setdefault(_COMMANDS, types.ModuleType(_COMMANDS))
_commands._forward_entity_changes = _forward_entity_changes


def _states_schema(msg: dict) -> dict:
    """The schema of subscribe_entities: it adds an empty "include" and "exclude"."""
    return {"include": empty_filter_part(), "exclude": empty_filter_part(), **msg}


def _core_subscribe(hass, connection, msg) -> None:
    """Home Assistant's subscribe_entities handler, reduced to what the pages see.

    As in Home Assistant, the listener is a partial of _forward_entity_changes in the
    listener list of the event bus, and the connection keeps the function that removes it.
    The handler reads "include" and "exclude" with no default, as the real one does. So a
    message that did not pass the schema raises KeyError before a listener exists.
    """
    if hass.handler_error is not None:
        raise hass.handler_error
    if hass.narrowed_handler_error is not None and msg.get("entity_ids"):
        raise hass.narrowed_handler_error
    msg["include"], msg["exclude"]
    call = {
        "user": connection.user.id,
        "entity_ids": msg.get("entity_ids"),
        "ended": False,
    }
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
        self.user = SimpleNamespace(
            id=user_id, name=USERS[user_id], is_admin=True, permissions=None
        )
        self.subscriptions: dict = {}
        self.results: list = []
        self.messages: list = []
        self.errors: list = []
        self.closed = False
        # Each send after the close. Home Assistant writes a debug line for such a send,
        # and the page gets nothing.
        self.after_close: list = []

    def send_result(self, msg_id, result=None) -> None:
        if self.closed:
            self.after_close.append((msg_id, result))
        else:
            self.results.append((msg_id, result))

    def send_message(self, message) -> None:
        if self.closed:
            self.after_close.append(message)
        else:
            self.messages.append(message)

    def async_handle_exception(self, msg, err) -> None:
        """Home Assistant answers the message with an error."""
        self.errors.append((msg["id"], err))

    def close(self) -> None:
        """The connection closes.

        As async_handle_close of Home Assistant does, it ends each subscription, forgets
        it, and replaces the send function.
        """
        for end in list(self.subscriptions.values()):
            end()
        self.subscriptions.clear()
        self.closed = True


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        # The listener list of Home Assistant's event bus, for the state listeners.
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
        if not name:
            return None
        return SimpleNamespace(id=user_id, name=name, is_admin=user_id == "u-admin")


class _Hass:
    def __init__(self, started: bool = True) -> None:
        # False while Home Assistant starts. Its property is_running is true in that time
        # also, so the stand-in has no such attribute.
        self.started = started
        self.include_missing: list[bool] = []
        self.scan_suspends = 0
        self.scan_seconds = 0.0
        self.scan_error: Exception | None = None
        self.handler_error: Exception | None = None
        self.narrowed_handler_error: Exception | None = None
        self.resolve_error: Exception | None = None
        self.resolve_suspends = 0
        self.resolve_gaps: dict[str, list[str]] = {}
        self.data = {
            "websocket_api": {
                "lovelace/resources": (_core_resources, "resources schema"),
                "subscribe_entities": (_core_subscribe, _states_schema),
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

    @property
    def loop(self):
        return asyncio.get_running_loop()

    def async_create_task(self, coro, name=None, eager_start=True):
        """As in Home Assistant, a task is eager by default: it runs at once up to its first wait."""
        task = asyncio.Task(coro, loop=self.loop, name=name, eager_start=eager_start)
        self.tasks.append(task)
        return task

    async def drain(self) -> None:
        """Wait for each task that a handler or a listener started.

        The error of an entity scan goes to the code that waits for the scan, so it is
        not raised here. Each other error fails the test.
        """
        while self.tasks:
            task = self.tasks.pop(0)
            if task.get_name().endswith("entity scan"):
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task


def _run_unload(entry) -> None:
    """Run the unload callbacks as Home Assistant does: the last one first."""
    while entry.unload:
        entry.unload.pop()()


def _call(user_id: str | None = None) -> SimpleNamespace:
    """A call of an action. No user in the context means a call by Home Assistant."""
    return SimpleNamespace(context=SimpleNamespace(user_id=user_id))


def _subscribe(hass, connection, msg_id: int = 5, **more) -> None:
    """A page sends subscribe_entities. Home Assistant gives the handler schema(msg)."""
    handler, schema = hass.data["websocket_api"]["subscribe_entities"]
    handler(
        hass, connection, schema({"id": msg_id, "type": "subscribe_entities", **more})
    )


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
        _subscribe(self.hass, connection, msg_id, **more)
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
        response = await preview(_call())
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
        _run_unload(self.entry)
        self.assertEqual(
            self.commands["lovelace/resources"], (_core_resources, "resources schema")
        )
        self.assertEqual(
            self.commands["subscribe_entities"], (_core_subscribe, _states_schema)
        )
        self.assertEqual(self.hass.services.registered, {})
        self.assertEqual(self.hass.bus.listeners["lovelace_updated"], [])
        self.assertEqual(self.entry.update_listeners, [])


class EarlyPageTest(unittest.IsolatedAsyncioTestCase):
    """A page that connected before Home Assistant set the integration up.

    After a restart, a kiosk page connects again within seconds. Home Assistant sets a
    custom integration up later, so Home Assistant's handler answers that page's first
    state subscription, with every entity. One kiosk went from 95 entities to
    5573 that way, and its page fell 200 seconds behind.
    """

    async def asyncSetUp(self) -> None:
        self._saved = (_entry.async_dashboard_entities, _entry.async_resolve)
        _entry.async_dashboard_entities = _dashboard_entities
        _entry.async_resolve = _resolve
        self.hass = _Hass()
        self.entry = _Entry(
            subentries=[
                _group("Workshop kiosks", ["u-w1", "u-w2"], ["dashboard-workshop"])
            ]
        )

    async def asyncTearDown(self) -> None:
        _entry.async_dashboard_entities, _entry.async_resolve = self._saved

    def _early_page(self, user_id: str, **more) -> _Connection:
        """A page subscribes before the setup, so Home Assistant's handler answers."""
        connection = _Connection(user_id)
        _core_subscribe(
            self.hass,
            connection,
            _states_schema({"id": 5, "type": "subscribe_entities", **more}),
        )
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
        # The page has its subscription's result. It gets no second one.
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
        self.assertEqual(
            self._calls("u-w1")[-1]["entity_ids"], ["sensor.a", "sensor.c"]
        )

    async def test_early_page_of_another_user_keeps_every_state(self) -> None:
        phone = self._early_page("u-phone")
        await self._setup()
        (call,) = self._calls("u-phone")
        self.assertFalse(call["ended"])
        self.assertEqual(len(phone.messages), 1)

    async def test_early_subscription_with_its_own_entities_is_not_changed(
        self,
    ) -> None:
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
        tablet = _Connection("u-k")
        _subscribe(self.hass, tablet, 7)
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

    async def _setup(self, started: bool):
        hass = _Hass(started=started)
        entry = _Entry(
            subentries=[_group("Kitchen tablet", ["u-k"], ["main-dashboard"])]
        )
        await _entry.async_setup_entry(hass, entry)
        # The setup's tasks run before a page connects.
        await hass.drain()
        return hass, entry

    async def test_page_is_updated_when_the_start_is_complete(self) -> None:
        hass, entry = await self._setup(started=False)
        connection = _Connection("u-k")
        _subscribe(hass, connection)
        await hass.drain()
        # A group entity got its state after the page connected, so it has a member now.
        hass.dashboard_entities["main-dashboard"] = {
            "light.k",
            "sensor.b",
            "light.k_member",
        }
        hass.bus.fire("homeassistant_started", {})
        await hass.drain()
        calls = [c for c in hass.core_subscriptions if c["user"] == "u-k"]
        self.assertEqual(
            calls[-1]["entity_ids"], ["light.k", "light.k_member", "sensor.b"]
        )
        self.assertEqual(connection.results, [(5, None)])
        # The listener ran once. The unload does not remove it a second time.
        self.assertEqual(hass.bus.listeners["homeassistant_started"], [])
        _run_unload(entry)

    async def test_unload_before_the_start_removes_the_listener(self) -> None:
        hass, entry = await self._setup(started=False)
        self.assertEqual(len(hass.bus.listeners["homeassistant_started"]), 1)
        _run_unload(entry)
        self.assertEqual(hass.bus.listeners["homeassistant_started"], [])

    async def test_running_home_assistant_needs_no_listener(self) -> None:
        hass, _unused = await self._setup(started=True)
        self.assertNotIn("homeassistant_started", hass.bus.listeners)

    async def test_subscription_asks_for_the_entities_with_no_state_yet(self) -> None:
        hass, _unused = await self._setup(started=True)
        _subscribe(hass, _Connection("u-k"))
        await hass.drain()
        self.assertEqual(hass.include_missing, [True])
        # The preview lists the entities that have a state. Apart from them, it lists the
        # names in a state subscription that have none.
        answer = await hass.services.registered[("lite_resources", "preview")](_call())
        self.assertEqual(hass.include_missing, [True, False, True])
        self.assertEqual(answer["groups"][0]["state_entities_without_state"], [])


class OpenPageSafetyTest(unittest.IsolatedAsyncioTestCase):
    """An open page keeps a state stream through each failure and each change to the setup."""

    async def asyncSetUp(self) -> None:
        self._saved = (_entry.async_dashboard_entities, _entry.async_resolve)
        _entry.async_dashboard_entities = _dashboard_entities
        _entry.async_resolve = _resolve
        self.hass = _Hass()
        self.entry = _Entry(
            subentries=[
                _group("Workshop kiosks", ["u-w1", "u-w2"], ["dashboard-workshop"])
            ]
        )
        await _entry.async_setup_entry(self.hass, self.entry)
        await self.hass.drain()

    async def asyncTearDown(self) -> None:
        _entry.async_dashboard_entities, _entry.async_resolve = self._saved

    def _calls(self, user_id: str) -> list[dict]:
        return [c for c in self.hass.core_subscriptions if c["user"] == user_id]

    def _live(self, user_id: str) -> list[dict]:
        return [c for c in self._calls(user_id) if not c["ended"]]

    async def _open_page(self, user_id: str, msg_id: int = 5) -> _Connection:
        connection = _Connection(user_id)
        _subscribe(self.hass, connection, msg_id)
        await self.hass.drain()
        return connection

    async def _unload(self) -> None:
        _run_unload(self.entry)
        await self.hass.drain()

    async def test_unload_gives_each_open_page_all_states_again(self) -> None:
        kiosk = await self._open_page("u-w1")
        await self._unload()
        (live,) = self._live("u-w1")
        self.assertIsNone(live["entity_ids"])
        # The page has its subscription's result. It gets no second one.
        self.assertEqual(kiosk.results, [(5, None)])

    async def test_reload_narrows_the_open_pages_again(self) -> None:
        kiosk = await self._open_page("u-w1")
        await self._unload()
        entry = _Entry(subentries=list(self.entry.subentries.values()))
        await _entry.async_setup_entry(self.hass, entry)
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])
        # The new setup follows a changed dashboard for that page.
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.a", "sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.c"])
        self.assertEqual(kiosk.results, [(5, None)])

    async def test_connection_that_closes_during_the_scan_gets_no_listener(
        self,
    ) -> None:
        self.hass.scan_suspends = 1
        kiosk = _Connection("u-w1")
        _subscribe(self.hass, kiosk)
        # The scan waits. The page leaves before the scan ends.
        kiosk.close()
        await self.hass.drain()
        self.assertEqual(self._calls("u-w1"), [])
        self.assertEqual(kiosk.subscriptions, {})
        # The result goes to a closed connection, where Home Assistant drops it.
        self.assertEqual(kiosk.results, [])
        self.assertEqual(kiosk.after_close, [(5, None)])
        self.assertEqual(self.hass.bus._listeners.get("state_changed", []), [])
        preview = self.hass.services.registered[("lite_resources", "preview")]
        self.assertEqual((await preview(_call()))["open_pages_with_narrowed_states"], 0)

    async def test_page_that_waits_for_the_scan_is_narrowed(self) -> None:
        self.hass.scan_suspends = 2
        kiosk = _Connection("u-w1")
        _subscribe(self.hass, kiosk)
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(kiosk.results, [(5, None)])

    async def test_two_changes_at_one_time_leave_the_newer_set(self) -> None:
        await self._open_page("u-w1")
        self.hass.scan_suspends = 3
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.a", "sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        # The second save comes while the scan for the first one waits.
        await asyncio.sleep(0)
        self.hass.dashboard_entities["dashboard-workshop"] = {
            "sensor.a",
            "sensor.c",
            "light.k",
        }
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["light.k", "sensor.a", "sensor.c"])

    async def test_scan_that_fails_gives_a_new_page_all_states(self) -> None:
        self.hass.scan_error = RuntimeError("the scan failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            kiosk = await self._open_page("u-w1")
        (live,) = self._live("u-w1")
        self.assertIsNone(live["entity_ids"])
        self.assertEqual(kiosk.results, [(5, None)])
        self.assertEqual(kiosk.errors, [])

    async def test_scan_that_fails_leaves_an_open_page_as_it_is(self) -> None:
        await self._open_page("u-w1")
        self.hass.scan_error = RuntimeError("the scan failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
            await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])

    async def test_handler_that_fails_gives_the_page_an_error_message(self) -> None:
        self.hass.handler_error = RuntimeError("the handler failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            kiosk = await self._open_page("u-w1")
        # The narrowed call failed, and the call for all states failed too. The page gets
        # the error, as it does from one of Home Assistant's handlers.
        self.assertEqual([msg_id for msg_id, _err in kiosk.errors], [5])
        self.assertEqual(kiosk.subscriptions, {})

    async def test_dashboard_that_cannot_be_narrowed_gives_all_states(self) -> None:
        self.hass.scan_error = _entry.CannotNarrow("the dashboard holds a strategy")
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            await self._open_page("u-w1")
            await self._open_page("u-w2", msg_id=6)
        # The reason is in the log one time, and not one time for each page.
        self.assertEqual(len(logs.records), 1)
        self.assertIn("strategy", logs.records[0].getMessage())
        self.assertIsNone(self._live("u-w1")[0]["entity_ids"])
        # When the dashboard names its entities again, the open pages are narrowed.
        self.hass.scan_error = None
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        self.assertEqual(self._live("u-w1")[0]["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(self._live("u-w2")[0]["entity_ids"], ["sensor.a", "sensor.b"])

    async def test_open_page_gets_all_states_when_its_dashboard_cannot_be_narrowed(
        self,
    ) -> None:
        await self._open_page("u-w1")
        self.hass.scan_error = _entry.CannotNarrow("the dashboard holds a strategy")
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
            await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertIsNone(live["entity_ids"])

    async def test_registry_change_updates_the_open_pages_one_time(self) -> None:
        await self._open_page("u-w1")
        saved = _entry.REGISTRY_REFRESH_DELAY
        _entry.REGISTRY_REFRESH_DELAY = 0
        try:
            # A new entity enters an area card's area: the registry fires a burst.
            self.hass.dashboard_entities["dashboard-workshop"] = {
                "sensor.a",
                "sensor.b",
                "light.k",
            }
            scans = len(self.hass.include_missing)
            for _event in range(5):
                self.hass.bus.fire("entity_registry_updated", {"action": "update"})
            self.hass.bus.fire("device_registry_updated", {"action": "update"})
            await asyncio.sleep(0.01)
            await self.hass.drain()
        finally:
            _entry.REGISTRY_REFRESH_DELAY = saved
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["light.k", "sensor.a", "sensor.b"])
        self.assertEqual(len(self.hass.include_missing), scans + 1)

    async def test_registry_change_with_no_open_page_starts_no_scan(self) -> None:
        saved = _entry.REGISTRY_REFRESH_DELAY
        _entry.REGISTRY_REFRESH_DELAY = 0
        try:
            scans = len(self.hass.include_missing)
            self.hass.bus.fire("area_registry_updated", {"action": "update"})
            await asyncio.sleep(0.01)
            await self.hass.drain()
        finally:
            _entry.REGISTRY_REFRESH_DELAY = saved
        self.assertEqual(len(self.hass.include_missing), scans)

    async def test_registry_change_narrows_a_page_that_holds_all_states(self) -> None:
        # The dashboard of the page names its entities again, and no dashboard event came.
        self.hass.scan_error = _entry.CannotNarrow("the dashboard holds a strategy")
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            await self._open_page("u-w1")
        self.assertIsNone(self._live("u-w1")[0]["entity_ids"])
        self.hass.scan_error = None
        saved = _entry.REGISTRY_REFRESH_DELAY
        _entry.REGISTRY_REFRESH_DELAY = 0
        try:
            self.hass.bus.fire("entity_registry_updated", {"action": "update"})
            await asyncio.sleep(0.01)
            await self.hass.drain()
        finally:
            _entry.REGISTRY_REFRESH_DELAY = saved
        self.assertEqual(self._live("u-w1")[0]["entity_ids"], ["sensor.a", "sensor.b"])

    async def test_preview_is_for_administrators_only(self) -> None:
        preview = self.hass.services.registered[("lite_resources", "preview")]
        # A kiosk user is no administrator: Home Assistant refuses its call.
        with self.assertRaises(_Unauthorized):
            await preview(_call("u-w1"))
        # A user that does not exist is refused too.
        with self.assertRaises(_Unauthorized):
            await preview(_call("u-deleted"))
        # An administrator gets the answer, through Home Assistant's wrapper.
        answer = await preview(_call("u-admin"))
        self.assertEqual(answer["groups"][0]["group"], "Workshop kiosks")

    async def test_preview_says_why_a_group_is_not_narrowed(self) -> None:
        self.hass.scan_error = _entry.CannotNarrow("the dashboard holds a strategy")
        preview = self.hass.services.registered[("lite_resources", "preview")]
        (group,) = (await preview(_call()))["groups"]
        self.assertEqual(group["states_not_narrowed"], "the dashboard holds a strategy")
        self.assertNotIn("state_entities", group)

    async def test_unload_keeps_the_handler_of_another_integration(self) -> None:
        commands = self.hass.data["websocket_api"]

        def other_handler(hass, connection, msg) -> None:
            """A handler that another integration registered after this one."""

        commands["subscribe_entities"] = (other_handler, _states_schema)
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            await self._unload()
        self.assertIs(commands["subscribe_entities"][0], other_handler)
        self.assertIs(commands["lovelace/resources"][0], _core_resources)

    async def test_user_in_two_groups_is_reported(self) -> None:
        second = _group("Hall panel", ["u-w1"], ["main-dashboard"])
        self.entry.subentries = {**self.entry.subentries, second.subentry_id: second}
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            for listener in self.entry.update_listeners:
                await listener(self.hass, self.entry)
        self.assertIn("more than one group", logs.records[0].getMessage())

    async def test_task_that_waits_at_the_unload_changes_no_page(self) -> None:
        await self._open_page("u-w1")
        # A dashboard save starts an update, and its scan waits.
        self.hass.scan_suspends = 2
        self.hass.dashboard_entities["dashboard-workshop"] = {"sensor.a", "sensor.c"}
        self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        # A second page subscribes in that time, and waits behind that update.
        late = _Connection("u-w2")
        _subscribe(self.hass, late, 6)
        _run_unload(self.entry)
        await self.hass.drain()
        # The unload is the last word on each page: all states, as without the integration.
        (live,) = self._live("u-w1")
        self.assertIsNone(live["entity_ids"])
        (live,) = self._live("u-w2")
        self.assertIsNone(live["entity_ids"])
        self.assertEqual(late.results, [(6, None)])

    async def test_handler_of_an_unloaded_setup_passes_each_message_on(self) -> None:
        # Another integration can keep this setup's handler and call it later.
        handler, schema = self.hass.data["websocket_api"]["subscribe_entities"]
        await self._unload()
        late = _Connection("u-w1")
        handler(self.hass, late, schema({"id": 5, "type": "subscribe_entities"}))
        await self.hass.drain()
        (call,) = self._calls("u-w1")
        self.assertIsNone(call["entity_ids"])

    async def test_client_that_unsubscribes_during_the_scan_gets_its_result(
        self,
    ) -> None:
        self.hass.scan_suspends = 1
        client = _Connection("u-w1")
        _subscribe(self.hass, client)
        # As Home Assistant's unsubscribe command: it takes the entry out and calls it.
        client.subscriptions.pop(5)()
        await self.hass.drain()
        self.assertEqual(client.results, [(5, None)])
        self.assertEqual(self._calls("u-w1"), [])

    async def test_page_whose_scan_is_open_at_a_reload_is_narrowed_by_the_new_setup(
        self,
    ) -> None:
        self.hass.scan_suspends = 3
        kiosk = _Connection("u-w1")
        _subscribe(self.hass, kiosk)
        # The scan waits. The operator reloads the integration in that time.
        _run_unload(self.entry)
        entry = _Entry(subentries=list(self.entry.subentries.values()))
        await _entry.async_setup_entry(self.hass, entry)
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(kiosk.results, [(5, None)])
        # The new setup holds the page, so it follows a changed dashboard.
        preview = self.hass.services.registered[("lite_resources", "preview")]
        self.assertEqual((await preview(_call()))["open_pages_with_narrowed_states"], 1)

    async def test_resources_request_that_waits_at_the_unload_gets_the_full_list(
        self,
    ) -> None:
        self.hass.resolve_suspends = 2
        connection = _Connection("u-w1")
        handler, _schema = self.hass.data["websocket_api"]["lovelace/resources"]
        request = asyncio.ensure_future(
            handler(self.hass, connection, {"id": 1, "type": "lovelace/resources"})
        )
        await asyncio.sleep(0)
        _run_unload(self.entry)
        await request
        self.assertEqual(connection.results, [(1, "every resource")])
        # A call of the old handler after the unload gets the full list also.
        self.assertEqual(await self._resources_from(handler, "u-w1"), "every resource")

    async def _resources_from(self, handler, user_id: str):
        connection = _Connection(user_id)
        await handler(self.hass, connection, {"id": 1, "type": "lovelace/resources"})
        return connection.results[-1][1]

    async def test_scan_over_the_time_limit_gives_a_new_page_all_states_and_a_later_try(
        self,
    ) -> None:
        saved = (_entry.SCAN_TIMEOUT, _entry.REGISTRY_REFRESH_DELAY)
        _entry.SCAN_TIMEOUT, _entry.REGISTRY_REFRESH_DELAY = 0.05, 0.05
        try:
            # As the load of a YAML dashboard from a slow share.
            self.hass.scan_seconds = 0.3
            kiosk = _Connection("u-w1")
            with self.assertLogs(_entry._LOGGER, level="ERROR"):
                _subscribe(self.hass, kiosk)
                await asyncio.sleep(0.15)
            (live,) = self._live("u-w1")
            self.assertIsNone(live["entity_ids"])
            # The share answers again. No event comes, and a later try narrows the page.
            self.hass.scan_seconds = 0
            with self.assertLogs(_entry._LOGGER, level="ERROR"):
                await asyncio.sleep(0.6)
                await self.hass.drain()
        finally:
            _entry.SCAN_TIMEOUT, _entry.REGISTRY_REFRESH_DELAY = saved
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(kiosk.results, [(5, None)])

    async def test_scan_over_the_time_limit_leaves_an_open_page_as_it_is(self) -> None:
        await self._open_page("u-w1")
        saved = _entry.SCAN_TIMEOUT
        _entry.SCAN_TIMEOUT = 0.05
        try:
            self.hass.scan_seconds = 0.3
            self.hass.dashboard_entities["dashboard-workshop"] = {
                "sensor.a",
                "sensor.c",
            }
            with self.assertLogs(_entry._LOGGER, level="ERROR"):
                self.hass.bus.fire(
                    "lovelace_updated", {"url_path": "dashboard-workshop"}
                )
                await asyncio.sleep(0.2)
            (live,) = self._live("u-w1")
            self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])
            # The update is over. When the slow scan ends, the next change starts a new
            # scan, and the page gets its new entities.
            self.hass.scan_seconds = 0
            await asyncio.sleep(0.2)
            self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
            await self.hass.drain()
        finally:
            _entry.SCAN_TIMEOUT = saved
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.c"])

    async def test_page_with_all_states_after_a_failed_scan_is_narrowed_at_a_later_try(
        self,
    ) -> None:
        saved = _entry.REGISTRY_REFRESH_DELAY
        _entry.REGISTRY_REFRESH_DELAY = 0.05
        try:
            self.hass.scan_error = RuntimeError("the scan failed")
            with self.assertLogs(_entry._LOGGER, level="ERROR"):
                await self._open_page("u-w1")
            self.assertIsNone(self._live("u-w1")[0]["entity_ids"])
            self.hass.scan_error = None
            await asyncio.sleep(0.2)
            await self.hass.drain()
        finally:
            _entry.REGISTRY_REFRESH_DELAY = saved
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.b"])

    async def test_new_page_after_a_fault_narrows_the_other_pages_of_its_group(
        self,
    ) -> None:
        self.hass.scan_error = RuntimeError("the scan failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            await self._open_page("u-w1")
        self.assertIsNone(self._live("u-w1")[0]["entity_ids"])
        # The later try comes after 10 seconds, so none runs here. The scan works again
        # when a second kiosk connects.
        self.hass.scan_error = None
        await self._open_page("u-w2", msg_id=6)
        self.assertEqual(self._live("u-w2")[0]["entity_ids"], ["sensor.a", "sensor.b"])
        self.assertEqual(self._live("u-w1")[0]["entity_ids"], ["sensor.a", "sensor.b"])

    async def test_later_tries_stop_after_the_limit(self) -> None:
        saved = _entry.REGISTRY_REFRESH_DELAY
        _entry.REGISTRY_REFRESH_DELAY = 0
        try:
            self.hass.scan_error = RuntimeError("the scan failed")
            scans = len(self.hass.include_missing)
            with self.assertLogs(_entry._LOGGER, level="ERROR"):
                await self._open_page("u-w1")
                await asyncio.sleep(0.1)
                await self.hass.drain()
            # The scan of the new page, then one scan for each later try.
            self.assertEqual(
                len(self.hass.include_missing) - scans, 1 + _entry.UPDATE_RETRIES
            )
            await asyncio.sleep(0.05)
            await self.hass.drain()
            self.assertEqual(
                len(self.hass.include_missing) - scans, 1 + _entry.UPDATE_RETRIES
            )
        finally:
            _entry.REGISTRY_REFRESH_DELAY = saved

    async def test_many_saves_close_together_give_few_scans(self) -> None:
        await self._open_page("u-w1")
        self.hass.scan_suspends = 2
        scans = len(self.hass.include_missing)
        for number in range(20):
            self.hass.dashboard_entities["dashboard-workshop"] = {
                "sensor.a",
                f"sensor.other_{number}",
            }
            self.hass.bus.fire("lovelace_updated", {"url_path": "dashboard-workshop"})
        await self.hass.drain()
        (live,) = self._live("u-w1")
        self.assertEqual(live["entity_ids"], ["sensor.a", "sensor.other_19"])
        self.assertLessEqual(len(self.hass.include_missing) - scans, 2)

    async def test_failed_narrowed_call_gives_the_new_page_all_states(self) -> None:
        self.hass.narrowed_handler_error = RuntimeError("the narrowed call failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            kiosk = await self._open_page("u-w1")
        (live,) = self._live("u-w1")
        self.assertIsNone(live["entity_ids"])
        self.assertEqual(kiosk.results, [(5, None)])
        self.assertEqual(kiosk.errors, [])

    async def test_subscription_with_a_filter_is_not_changed(self) -> None:
        connection = _Connection("u-w1")
        only_lights = {"domains": ["light"], "entity_globs": [], "entities": []}
        _subscribe(self.hass, connection, include=only_lights)
        await self.hass.drain()
        (call,) = self._calls("u-w1")
        self.assertIsNone(call["entity_ids"])
        preview = self.hass.services.registered[("lite_resources", "preview")]
        self.assertEqual((await preview(_call()))["open_pages_with_narrowed_states"], 0)

    async def _resources(self, user_id: str):
        connection = _Connection(user_id)
        handler, _schema = self.hass.data["websocket_api"]["lovelace/resources"]
        await handler(self.hass, connection, {"id": 1, "type": "lovelace/resources"})
        return connection.results[-1][1]

    async def test_resources_that_cannot_be_reduced_give_the_full_list(self) -> None:
        self.hass.resolve_error = _entry.CannotNarrow(
            "no dashboard in the group exists"
        )
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            self.assertEqual(await self._resources("u-w1"), "every resource")
            self.assertEqual(await self._resources("u-w2"), "every resource")
        self.assertEqual(len(logs.records), 1)

    async def test_failed_resource_scan_gives_the_full_list(self) -> None:
        self.hass.resolve_error = RuntimeError("the scan failed")
        with self.assertLogs(_entry._LOGGER, level="ERROR"):
            self.assertEqual(await self._resources("u-w1"), "every resource")

    async def test_card_type_with_no_provider_is_in_the_log_one_time(self) -> None:
        self.hass.resolve_gaps = {
            "unresolved": ["a-card"],
            "unverified": ["b-card"],
            "guessed": ["c-card"],
        }
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            await self._resources("u-w1")
            await self._resources("u-w1")
        self.assertEqual(len(logs.records), 3)

    async def test_adoption_removes_only_the_entities_that_the_user_can_read(
        self,
    ) -> None:
        # The tablet user has a policy for four entities. Its page holds only those.
        readable = {"sensor.a", "sensor.b", "light.k", "sensor.other_1"}
        tablet = _Connection("u-k")
        tablet.user.is_admin = False
        tablet.user.permissions = SimpleNamespace(
            access_all_entities=lambda policy: False,
            check_entity=lambda entity_id, policy: entity_id in readable,
        )
        _subscribe(self.hass, tablet, 7)
        await self.hass.drain()
        kitchen = _group("Kitchen tablet", ["u-k"], ["main-dashboard"])
        self.entry.subentries = {**self.entry.subentries, kitchen.subentry_id: kitchen}
        for listener in self.entry.update_listeners:
            await listener(self.hass, self.entry)
        await self.hass.drain()
        # The removal names no entity that the policy hides.
        self.assertEqual(
            tablet.messages[-1]["event"], {"r": ["sensor.a", "sensor.other_1"]}
        )

    async def test_listener_of_another_layout_is_reported(self) -> None:
        # Home Assistant's function with one more argument than this search knows.
        odd = functools.partial(
            _forward_entity_changes,
            "extra",
            lambda message: None,
            None,
            None,
            None,
            b"5",
        )
        listeners = self.hass.bus._listeners.setdefault("state_changed", [])
        listeners.append((SimpleNamespace(target=odd), None))
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            for listener in self.entry.update_listeners:
                await listener(self.hass, self.entry)
            await self.hass.drain()
        self.assertIn("another layout", logs.records[0].getMessage())

    async def test_setup_reports_internals_of_another_layout(self) -> None:
        hass = _Hass()
        del hass.bus._listeners
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            await _entry.async_setup_entry(hass, _Entry())
            await hass.drain()
        self.assertIn("keeps all states", logs.records[0].getMessage())


class SetupWithoutLovelaceTest(unittest.IsolatedAsyncioTestCase):
    """Home Assistant tries the setup again when the dashboards are not set up yet."""

    async def test_setup_waits_for_the_dashboards(self) -> None:
        hass = _Hass()
        hass.data = {"websocket_api": {}}
        with self.assertRaises(_entry.ConfigEntryNotReady):
            await _entry.async_setup_entry(hass, _Entry())


class MigrationTest(unittest.IsolatedAsyncioTestCase):
    """A single-group version's settings become the first group."""

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

    async def test_setup_with_no_state_filter_option_keeps_the_filter_off(self) -> None:
        # A version with no such option did not narrow the states. A group's form shows a
        # missing option as on, so the group states that it is off.
        entry = _Entry(
            version=1, options={"users": ["u-w1"], "dashboards": ["dashboard-workshop"]}
        )
        self.assertTrue(await _entry.async_migrate_entry(_Hass(), entry))
        (group,) = entry.subentries.values()
        self.assertIs(group.data["filter_states"], False)

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
