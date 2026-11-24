"""A YAML dashboard whose file changes, with the real dashboard scan.

Home Assistant fires the update event of a YAML dashboard inside the load that finds the
changed file. When that load is a scan of this integration, each open page of each group
with the dashboard still needs the new entities. A file that fires at each load must start
no update with no end.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
import unittest

from test_setup_entry import (
    _call,
    _Connection,
    _Entry,
    _entry,
    _group,
    _Hass,
    _resolver,
    _run_unload,
    _subscribe,
)

STATES = ("sun.sun", "zone.home", "light.hall", "sensor.old", "sensor.new")


def _cards(*entities: str) -> dict:
    return {"views": [{"cards": [{"type": "tile", "entity": e} for e in entities]}]}


class _YamlDashboard:
    """Stand-in for LovelaceYAML: the load that finds a changed file fires the event.

    `always` makes each load fire and give a new object, as a file does whose
    configuration is empty or whose time is in the future. `error` makes the load raise.
    """

    def __init__(self, hass, url_path: str, config: dict) -> None:
        self.hass = hass
        self.url_path = url_path
        self.config = config
        self.changed = False
        self.always = False
        self.error: Exception | None = None
        self.loads = 0

    def write(self, config: dict) -> None:
        """The file changes on the disk. No event comes before the next load."""
        self.config = config
        self.changed = True

    async def async_load(self, force: bool) -> dict:
        self.loads += 1
        await asyncio.sleep(0)  # the read of the file, in the executor
        if self.error is not None:
            raise self.error
        if self.changed or self.always:
            self.changed = False
            self.hass.bus.fire("lovelace_updated", {"url_path": self.url_path})
        return dict(self.config) if self.always else self.config


def _hass() -> _Hass:
    """The stand-in for hass, with what the real scan reads."""
    hass = _Hass()
    states = {
        entity_id: SimpleNamespace(
            entity_id=entity_id, domain=entity_id.partition(".")[0], attributes={}
        )
        for entity_id in STATES
    }
    hass.states = SimpleNamespace(
        async_all=lambda: list(states.values()),
        get=states.get,
        async_entity_ids=lambda: list(states),
    )
    hass.entity_registry = SimpleNamespace(entities={})
    hass.device_registry = SimpleNamespace(async_get={}.get)
    hass.area_registry = SimpleNamespace(async_get_area=lambda area_id: None)
    hass.services.has_service = lambda domain, service: False
    hass.data["lovelace"] = SimpleNamespace(
        dashboards={}, resources=SimpleNamespace(loaded=True, async_items=list)
    )
    return hass


class YamlDashboardTest(unittest.IsolatedAsyncioTestCase):
    """Two groups show one YAML dashboard. A kiosk and the tablet have an open page."""

    async def asyncSetUp(self) -> None:
        _resolver._SEEN.clear()
        _resolver._CHANGE_LISTENERS.clear()
        self.hass = _hass()
        self.dashboard = _YamlDashboard(self.hass, "yaml-dash", _cards("sensor.old"))
        self.hass.data["lovelace"].dashboards["yaml-dash"] = self.dashboard
        self.entry = _Entry(
            subentries=[
                _group("Workshop kiosks", ["u-w1", "u-w2"], ["yaml-dash"]),
                _group("Kitchen tablet", ["u-k"], ["yaml-dash"]),
            ]
        )
        self.assertTrue(await _entry.async_setup_entry(self.hass, self.entry))
        await self.hass.drain()
        await self._open("u-w1")
        await self._open("u-k", 7)
        self.saved_delay = _entry.REGISTRY_REFRESH_DELAY

    async def asyncTearDown(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY = self.saved_delay
        _run_unload(self.entry)
        await self.hass.drain()

    async def _open(self, user_id: str, msg_id: int = 5) -> _Connection:
        connection = _Connection(user_id)
        _subscribe(self.hass, connection, msg_id)
        await self.hass.drain()
        return connection

    def _ids(self, user_id: str):
        (live,) = [
            call
            for call in self.hass.core_subscriptions
            if call["user"] == user_id and not call["ended"]
        ]
        return live["entity_ids"]

    def _assert_each_open_page_has_the_new_entity(self) -> None:
        for user_id in ("u-w1", "u-k"):
            self.assertIn("sensor.new", self._ids(user_id), user_id)

    async def test_setup_narrows_both_pages(self) -> None:
        self.assertEqual(self._ids("u-w1"), ["sensor.old", "sun.sun", "zone.home"])
        self.assertEqual(self._ids("u-k"), ["sensor.old", "sun.sun", "zone.home"])

    async def test_change_that_a_new_page_loads_first(self) -> None:
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await self._open("u-w2", 9)
        self.assertIn("sensor.new", self._ids("u-w2"))
        self._assert_each_open_page_has_the_new_entity()

    async def test_change_that_the_preview_action_loads_first(self) -> None:
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        preview = self.hass.services.registered[("lite_resources", "preview")]
        await preview(_call())
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()

    async def test_change_that_a_resources_request_loads_first(self) -> None:
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        handler, _schema = self.hass.data["websocket_api"]["lovelace/resources"]
        await handler(
            self.hass, _Connection("u-w2"), {"id": 1, "type": "lovelace/resources"}
        )
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()

    async def test_change_that_a_browser_loads_first(self) -> None:
        # The load of another task fires the event, as the frontend's load does.
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await self.dashboard.async_load(False)
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()

    async def test_event_of_another_task_during_a_scan_is_not_dropped(self) -> None:
        # A new page's scan waits in its load. Another task then finds the changed file.
        late = _Connection("u-w2")
        _subscribe(self.hass, late, 9)
        self.dashboard.config = _cards("sensor.old", "sensor.new")
        self.hass.bus.fire("lovelace_updated", {"url_path": "yaml-dash"})
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()

    async def test_file_that_fires_at_each_load_starts_no_update_with_no_end(
        self,
    ) -> None:
        self.dashboard.always = True
        await self._open("u-w2", 9)
        loads = self.dashboard.loads
        for _turn in range(200):
            await asyncio.sleep(0)
        await self.hass.drain()
        self.assertEqual(self.dashboard.loads, loads)
        # An update from another cause loads the file, and that load starts no update.
        self.hass.bus.fire("lovelace_updated", {"url_path": "yaml-dash"})
        for _turn in range(200):
            await asyncio.sleep(0)
        await self.hass.drain()
        self.assertLessEqual(self.dashboard.loads - loads, 4)

    async def test_load_that_fails_leaves_no_own_load_behind(self) -> None:
        error = sys.modules["homeassistant.exceptions"].HomeAssistantError("bad YAML")
        self.dashboard.error = error
        with self.assertRaises(_resolver.CannotNarrow) as raised:
            await _resolver._async_dashboard_scans(self.hass, ["yaml-dash"])
        self.assertEqual(
            str(raised.exception), "the dashboard yaml-dash cannot be loaded: bad YAML"
        )
        # This task loaded the dashboard a moment ago. Its load is over.
        self.assertFalse(_resolver.own_load_fired("yaml-dash"))

    async def test_dashboard_that_cannot_be_loaded_gives_all_states_and_a_later_try(
        self,
    ) -> None:
        _entry.REGISTRY_REFRESH_DELAY = 0.05
        self.dashboard.error = sys.modules[
            "homeassistant.exceptions"
        ].HomeAssistantError("bad YAML")
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            await self._open("u-w2", 9)
        self.assertIn("cannot be loaded: bad YAML", logs.records[0].getMessage())
        self.assertIsNone(self._ids("u-w2"))
        # The operator corrects the file. No event comes: Home Assistant never held it.
        self.dashboard.error = None
        await asyncio.sleep(0.2)
        await self.hass.drain()
        self.assertEqual(self._ids("u-w2"), ["sensor.old", "sun.sun", "zone.home"])

    async def test_tries_stop_when_the_dashboard_stays_broken(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY = 0
        self.dashboard.error = sys.modules[
            "homeassistant.exceptions"
        ].HomeAssistantError("bad YAML")
        loads = self.dashboard.loads
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            await self._open("u-w2", 9)
            await asyncio.sleep(0.1)
            await self.hass.drain()
        tries = self.dashboard.loads - loads
        # The page's scan, then two scans for each later try: the open narrowed page of
        # the group, and the pages that hold all states.
        self.assertLessEqual(tries, 1 + 2 * _entry.UPDATE_RETRIES)
        await asyncio.sleep(0.05)
        await self.hass.drain()
        self.assertEqual(self.dashboard.loads - loads, tries)


if __name__ == "__main__":
    unittest.main()
