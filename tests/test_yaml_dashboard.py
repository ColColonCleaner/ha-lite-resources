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
    _reset_resolver,
    _resolver,
    _run_unload,
    _subscribe,
)

STATES = ("sun.sun", "zone.home", "light.hall", "sensor.old", "sensor.new")
OLD = ["sensor.old", "sun.sun", "zone.home"]


def _cards(*entities: str) -> dict:
    return {"views": [{"cards": [{"type": "tile", "entity": e} for e in entities]}]}


def _bad_yaml() -> Exception:
    return sys.modules["homeassistant.exceptions"].HomeAssistantError("bad YAML")


class _YamlDashboard:
    """Stand-in for LovelaceYAML, with its cache rules.

    As in Home Assistant, a load reads the file again when the file is newer than the
    cache, and it fires the update event when a cache existed before that read. A load
    that fails keeps the older cache. `always` makes each load read the file and give a
    new object, as a file does whose time is in the future. `turns` gives the number of
    event loop turns that each load in a row takes, so that a test can let a later load
    return before an earlier one.
    """

    def __init__(self, hass, url_path, config: dict) -> None:
        self.hass = hass
        self.url_path = url_path
        self.file: dict | Exception = config
        self.cache: dict | None = None
        self.file_is_newer = True
        self.always = False
        self.turns: list[int] = []
        self.loads = 0

    def write(self, content: dict | Exception) -> None:
        """The file changes on the disk. No event comes before the next load."""
        self.file = content
        self.file_is_newer = True

    async def async_load(self, force: bool) -> dict:
        self.loads += 1
        fired = False
        error: Exception | None = None
        # The read of the file, in the executor: it replaces the cache at once.
        if self.file_is_newer or self.always:
            if isinstance(self.file, Exception):
                error = self.file
            else:
                fired = self.cache is not None
                self.cache = dict(self.file) if self.always else self.file
                self.file_is_newer = False
        config = self.cache
        for _turn in range(self.turns.pop(0) if self.turns else 1):
            await asyncio.sleep(0)
        if error is not None:
            raise error
        if fired:
            self.hass.bus.fire("lovelace_updated", {"url_path": self.url_path})
        return config


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

    url_path: str | None = "yaml-dash"
    dashboard_key = "yaml-dash"

    async def asyncSetUp(self) -> None:
        _reset_resolver()
        self.hass = _hass()
        self.dashboard = _YamlDashboard(self.hass, self.url_path, _cards("sensor.old"))
        self.hass.data["lovelace"].dashboards[self.url_path] = self.dashboard
        self.entry = _Entry(
            subentries=[
                _group("Workshop kiosks", ["u-w1", "u-w2"], [self.dashboard_key]),
                _group("Kitchen tablet", ["u-k"], [self.dashboard_key]),
            ]
        )
        self.assertTrue(await _entry.async_setup_entry(self.hass, self.entry))
        await self.hass.drain()
        await self._open("u-w1")
        await self._open("u-k", 7)
        self.saved = (_entry.REGISTRY_REFRESH_DELAY, _entry.UPDATE_RETRIES)

    async def asyncTearDown(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY, _entry.UPDATE_RETRIES = self.saved
        _run_unload(self.entry)
        await self.hass.drain()

    async def _open(self, user_id: str, msg_id: int = 5) -> _Connection:
        connection = _Connection(user_id)
        _subscribe(self.hass, connection, msg_id)
        await self.hass.drain()
        return connection

    async def _preview(self) -> dict:
        answer = await self.hass.services.registered[("lite_resources", "preview")](
            _call()
        )
        await self.hass.drain()
        return answer

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
        self.assertEqual(self._ids("u-w1"), OLD)
        self.assertEqual(self._ids("u-k"), OLD)

    async def test_change_that_a_new_page_loads_first(self) -> None:
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await self._open("u-w2", 9)
        self.assertIn("sensor.new", self._ids("u-w2"))
        self._assert_each_open_page_has_the_new_entity()

    async def test_change_that_the_preview_action_loads_first(self) -> None:
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await self._preview()
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
        loads = self.dashboard.loads
        await self.dashboard.async_load(False)
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()
        # The browser's load, and one scan for each of the two groups. The scan sees
        # the configuration that the event announced, so no second update follows.
        self.assertEqual(self.dashboard.loads - loads, 3)

    async def test_event_of_another_task_during_a_scan_is_not_dropped(self) -> None:
        # A new page's scan waits in its load. Another task then finds the changed file.
        late = _Connection("u-w2")
        _subscribe(self.hass, late, 9)
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await self.dashboard.async_load(False)
        await self.hass.drain()
        self._assert_each_open_page_has_the_new_entity()

    async def test_two_loads_at_one_time_do_not_hide_the_change(self) -> None:
        # A new page sends its resources request and its state subscription together.
        # The first load finds the changed file and returns last. The second load reads
        # the new cache, fires nothing, and returns first.
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        self.dashboard.turns = [5, 1]
        handler, _schema = self.hass.data["websocket_api"]["lovelace/resources"]
        request = asyncio.ensure_future(
            handler(
                self.hass, _Connection("u-w2"), {"id": 1, "type": "lovelace/resources"}
            )
        )
        await asyncio.sleep(0)
        _subscribe(self.hass, _Connection("u-w2"), 9)
        await request
        await self.hass.drain()
        self.assertIn("sensor.new", self._ids("u-w2"))
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
        self.hass.bus.fire("lovelace_updated", {"url_path": self.url_path})
        for _turn in range(200):
            await asyncio.sleep(0)
        await self.hass.drain()
        self.assertEqual(self.dashboard.loads - loads, 2)

    async def test_file_with_a_number_that_is_not_equal_to_itself(self) -> None:
        # Two loads of a NaN value give two objects that are not equal as values.
        self.dashboard.always = True
        self.dashboard.write({**_cards("sensor.old"), "ratio": float("nan")})
        await self._open("u-w2", 9)
        for _turn in range(200):
            await asyncio.sleep(0)
        await self.hass.drain()
        loads = self.dashboard.loads
        for _turn in range(200):
            await asyncio.sleep(0)
        await self.hass.drain()
        self.assertEqual(self.dashboard.loads, loads)

    async def test_load_that_fails_leaves_no_own_load_behind(self) -> None:
        self.dashboard.write(_bad_yaml())
        with self.assertRaises(_resolver.CannotNarrow) as raised:
            await _resolver._async_dashboard_scans(self.hass, [self.dashboard_key])
        self.assertEqual(
            str(raised.exception),
            f"the dashboard {self.dashboard_key} cannot be loaded: bad YAML",
        )
        # This task loaded the dashboard a moment ago. Its load is over.
        self.assertFalse(_resolver.is_own_load(self.url_path))

    async def test_dashboard_that_cannot_be_loaded(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY = 0.05
        self.dashboard.write(_bad_yaml())
        with self.assertLogs(_entry._LOGGER, level="WARNING") as logs:
            await self._open("u-w2", 9)
        self.assertIn("cannot be loaded: bad YAML", logs.records[0].getMessage())
        # The new page gets all states, and each open page keeps its entities.
        self.assertIsNone(self._ids("u-w2"))
        self.assertEqual(self._ids("u-w1"), OLD)
        self.assertEqual(self._ids("u-k"), OLD)
        # The operator corrects the file. A later try finds it, and each page of each
        # group gets the entities of the corrected file.
        self.dashboard.write(_cards("sensor.old", "sensor.new"))
        await asyncio.sleep(0.2)
        await self.hass.drain()
        self.assertIn("sensor.new", self._ids("u-w2"))
        self._assert_each_open_page_has_the_new_entity()

    async def test_file_that_is_put_back_after_the_tries_ran_out(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY = 0
        self.dashboard.write(_bad_yaml())
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            await self._open("u-w2", 9)
            await asyncio.sleep(0.1)
            await self.hass.drain()
        self.assertIsNone(self._ids("u-w2"))
        # The operator puts the file back as it was, and looks at the preview.
        self.dashboard.write(_cards("sensor.old"))
        answer = await self._preview()
        self.assertEqual(answer["groups"][0]["state_entities"], OLD)
        # The preview's load found the file, so the page with all states is narrowed.
        self.assertEqual(self._ids("u-w2"), OLD)
        self.assertEqual(self._ids("u-w1"), OLD)

    async def test_tries_stop_when_the_dashboard_stays_broken(self) -> None:
        _entry.REGISTRY_REFRESH_DELAY = 0
        self.dashboard.write(_bad_yaml())
        loads = self.dashboard.loads
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            await self._open("u-w2", 9)
            await asyncio.sleep(0.1)
            await self.hass.drain()
        # The scan of the new page, and one scan for each later try of its group. The
        # kitchen group has no scan, because its page keeps its entities.
        self.assertEqual(self.dashboard.loads - loads, 1 + _entry.UPDATE_RETRIES)
        await asyncio.sleep(0.05)
        await self.hass.drain()
        self.assertEqual(self.dashboard.loads - loads, 1 + _entry.UPDATE_RETRIES)


class DefaultYamlDashboardTest(YamlDashboardTest):
    """The same cases for the default dashboard, whose URL path is None."""

    url_path = None
    dashboard_key = "__default__"


class TwoYamlDashboardsTest(unittest.IsolatedAsyncioTestCase):
    """One group shows two YAML dashboards, and a second group shows one of the two."""

    _open = YamlDashboardTest._open
    _ids = YamlDashboardTest._ids

    async def asyncSetUp(self) -> None:
        _reset_resolver()
        self.hass = _hass()
        self.first = _YamlDashboard(self.hass, "first-dash", _cards("light.hall"))
        self.second = _YamlDashboard(self.hass, "second-dash", _cards("sensor.old"))
        self.hass.data["lovelace"].dashboards.update(
            {"first-dash": self.first, "second-dash": self.second}
        )
        self.entry = _Entry(
            subentries=[
                _group(
                    "Workshop kiosks", ["u-w1", "u-w2"], ["first-dash", "second-dash"]
                ),
                _group("Kitchen tablet", ["u-k"], ["second-dash"]),
            ]
        )
        self.assertTrue(await _entry.async_setup_entry(self.hass, self.entry))
        await self.hass.drain()
        await self._open("u-w1")
        await self._open("u-k", 7)

    async def asyncTearDown(self) -> None:
        _run_unload(self.entry)
        await self.hass.drain()

    async def test_change_to_one_of_two_dashboards_gives_one_update(self) -> None:
        both = ["light.hall", "sensor.new", "sensor.old", "sun.sun", "zone.home"]
        self.second.write(_cards("sensor.old", "sensor.new"))
        loads = (self.first.loads, self.second.loads)
        await self._open("u-w2", 9)
        self.assertEqual(self._ids("u-w2"), both)
        self.assertEqual(self._ids("u-w1"), both)
        self.assertEqual(self._ids("u-k"), ["sensor.new", "sensor.old", *OLD[1:]])
        # The scan of the new page loads each dashboard one time. The one update after
        # it scans each of the two groups one time, and no further update follows.
        self.assertEqual(self.first.loads - loads[0], 2)
        self.assertEqual(self.second.loads - loads[1], 3)


class _StoredDashboard:
    """Stand-in for LovelaceStorage, the dashboard that the UI stores.

    As in Home Assistant, a save keeps the new configuration as a new object and fires
    the update event at once, and a load gives the object of the last save. A delete
    leaves no stored configuration, and it fires the same event.
    """

    def __init__(self, hass, url_path: str, config: dict | None) -> None:
        self.hass = hass
        self.url_path = url_path
        self.config = config
        self.loads = 0

    async def async_load(self, force: bool) -> dict:
        self.loads += 1
        if self.config is None:
            raise sys.modules["homeassistant.components.lovelace.const"].ConfigNotFound
        return self.config

    def save(self, config: dict | None) -> None:
        """A save from the dashboard editor. None stands for a delete."""
        self.config = config
        self.hass.bus.fire("lovelace_updated", {"url_path": self.url_path})


class StoredDashboardTest(unittest.IsolatedAsyncioTestCase):
    """Two groups show one stored dashboard. A kiosk and the tablet have an open page."""

    _open = YamlDashboardTest._open
    _ids = YamlDashboardTest._ids

    async def asyncSetUp(self) -> None:
        _reset_resolver()
        self.hass = _hass()
        self.dashboard = _StoredDashboard(
            self.hass, "stored-dash", _cards("sensor.old")
        )
        self.hass.data["lovelace"].dashboards["stored-dash"] = self.dashboard
        self.entry = _Entry(
            subentries=[
                _group("Workshop kiosks", ["u-w1", "u-w2"], ["stored-dash"]),
                _group("Kitchen tablet", ["u-k"], ["stored-dash"]),
            ]
        )
        self.assertTrue(await _entry.async_setup_entry(self.hass, self.entry))
        await self.hass.drain()
        await self._open("u-w1")
        await self._open("u-k", 7)

    async def asyncTearDown(self) -> None:
        _run_unload(self.entry)
        await self.hass.drain()

    async def test_save_gives_each_group_one_scan(self) -> None:
        loads = self.dashboard.loads
        self.dashboard.save(_cards("sensor.old", "sensor.new"))
        await self.hass.drain()
        for user_id in ("u-w1", "u-k"):
            self.assertIn("sensor.new", self._ids(user_id), user_id)
        # The event starts one update, which scans each of the two groups one time.
        self.assertEqual(self.dashboard.loads - loads, 2)

    async def test_delete_gives_each_group_one_scan(self) -> None:
        loads = self.dashboard.loads
        with self.assertLogs(_entry._LOGGER, level="WARNING"):
            self.dashboard.save(None)
            await self.hass.drain()
        # With no stored configuration, the browser makes the cards.
        self.assertIsNone(self._ids("u-w1"))
        self.assertIsNone(self._ids("u-k"))
        self.assertEqual(self.dashboard.loads - loads, 2)

    async def test_page_that_connects_after_a_save_starts_no_update(self) -> None:
        self.dashboard.save(_cards("sensor.old", "sensor.new"))
        await self.hass.drain()
        loads = self.dashboard.loads
        await self._open("u-w2", 9)
        self.assertIn("sensor.new", self._ids("u-w2"))
        self.assertEqual(self.dashboard.loads - loads, 1)


if __name__ == "__main__":
    unittest.main()
