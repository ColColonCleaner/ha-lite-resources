"""What the scan of a dashboard gives a state subscription, and when it gives nothing.

Each case comes from a finding of a review of the scan: a dashboard that names no
entity because the browser makes its cards, a card that shows each entity of a domain,
and an entity ID that the search of the JSON text of a dashboard did not see.
"""

from __future__ import annotations

import datetime
import sys
import unittest
from types import SimpleNamespace

from support import install_homeassistant_stubs, load

install_homeassistant_stubs()

load("lite_resources.const", "const.py")
_discovery = load("lite_resources.discovery", "discovery.py")
_resolver = load("lite_resources.resolver", "resolver.py")

CannotNarrow = _resolver.CannotNarrow

STATES = {
    "sun.sun": {},
    "zone.home": {},
    "zone.work": {},
    "light.hall": {},
    "light.second": {},
    "light.third": {},
    "sensor.bare": {},
    "person.kiosk": {"user_id": "u-kiosk"},
    "person.anna": {"user_id": "u-anna"},
    "device_tracker.phone": {},
    "geo_location.quake_1": {},
    "update.core": {},
    "update.card": {},
}


class _Dashboard:
    """A dashboard of the lovelace table. `config` None means no stored configuration."""

    def __init__(self, config) -> None:
        self._config = config

    async def async_load(self, force):
        if self._config is None:
            raise sys.modules["homeassistant.components.lovelace.const"].ConfigNotFound
        if self._config == "broken":
            # A YAML dashboard with a syntax error.
            raise sys.modules["homeassistant.exceptions"].HomeAssistantError("bad YAML")
        return self._config


def _hass(dashboards: dict) -> SimpleNamespace:
    states = {
        entity_id: SimpleNamespace(
            entity_id=entity_id, domain=entity_id.partition(".")[0], attributes=attributes
        )
        for entity_id, attributes in STATES.items()
    }
    return SimpleNamespace(
        data={
            "lovelace": SimpleNamespace(
                dashboards={key: _Dashboard(config) for key, config in dashboards.items()}
            )
        },
        states=SimpleNamespace(async_all=lambda: list(states.values()), get=states.get),
        entity_registry=SimpleNamespace(entities={}),
        device_registry=SimpleNamespace(async_get={}.get),
        area_registry=SimpleNamespace(async_get_area=lambda area_id: None),
        services=SimpleNamespace(
            has_service=lambda domain, service: (domain, service) == ("light", "turn_on")
        ),
    )


def _cards(*cards) -> dict:
    return {"views": [{"cards": list(cards)}]}


async def _entities(dashboards: dict, keys=None, **options) -> set[str]:
    options = {"dashboards": keys or list(dashboards), "users": ["u-kiosk"], **options}
    return await _resolver.async_dashboard_entities(_hass(dashboards), options)


class CannotNarrowTest(unittest.IsolatedAsyncioTestCase):
    """Dashboards that do not say which entities a page needs."""

    async def _reason(self, dashboards: dict, keys=None) -> str:
        with self.assertRaises(CannotNarrow) as raised:
            await _entities(dashboards, keys)
        return str(raised.exception)

    async def test_strategy_dashboard(self) -> None:
        reason = await self._reason({"home": {"strategy": {"type": "original-states"}}})
        self.assertIn("strategy", reason)
        self.assertIn("home", reason)

    async def test_strategy_view_and_strategy_section(self) -> None:
        view = {"views": [{"strategy": {"type": "area", "area": "kitchen"}}]}
        section = {"views": [{"sections": [{"strategy": {"type": "device"}}]}]}
        self.assertIn("strategy", await self._reason({"d": view}))
        self.assertIn("strategy", await self._reason({"d": section}))

    async def test_dashboard_with_no_stored_configuration(self) -> None:
        # Home Assistant generates such a dashboard in the browser.
        reason = await self._reason({"generated": None})
        self.assertIn("no stored configuration", reason)

    async def test_one_dashboard_of_two_with_no_stored_configuration(self) -> None:
        plain = _cards({"type": "tile", "entity": "light.hall"})
        self.assertIn("generated", await self._reason({"plain": plain, "generated": None}))

    async def test_no_dashboard_of_the_group_exists(self) -> None:
        self.assertIn("exists", await self._reason({}, keys=["deleted"]))

    async def test_deleted_dashboard_beside_a_stored_one_is_left_out(self) -> None:
        plain = _cards({"type": "tile", "entity": "light.hall"})
        found = await _entities({"plain": plain}, keys=["plain", "deleted"])
        self.assertIn("light.hall", found)

    async def test_cards_that_find_their_entities_by_themselves(self) -> None:
        for card_type in ("home-summary", "power-sankey", "energy-usage-graph", "water-sankey"):
            reason = await self._reason({"d": _cards({"type": card_type})})
            self.assertIn(card_type, reason)

    async def test_card_feature_with_a_like_name_stops_nothing(self) -> None:
        # The feature of a water heater is no water card. A prefix of a type is no test.
        card = {
            "type": "tile",
            "entity": "light.hall",
            "features": [{"type": "water-heater-operation-modes"}, {"type": "power-total"}],
        }
        self.assertIn("light.hall", await _entities({"d": _cards(card)}))
        custom = {"type": "custom:chart-card", "series": [{"type": "power-flow", "entity": "light.hall"}]}
        self.assertIn("light.hall", await _entities({"d": _cards(custom)}))

    async def test_key_strategy_in_a_card_or_an_action_is_no_strategy(self) -> None:
        # The frontend reads the key only at a dashboard, a view and a section.
        button = {
            "type": "button",
            "entity": "light.hall",
            "tap_action": {"action": "perform-action", "data": {"strategy": "eco"}},
        }
        custom = {"type": "custom:charger-card", "entity": "light.second", "strategy": "solar"}
        found = await _entities({"d": _cards(button, custom)})
        self.assertLessEqual({"light.hall", "light.second"}, found)

    async def test_dashboard_that_cannot_be_loaded_is_left_out(self) -> None:
        # A YAML dashboard with a syntax error shows nothing, and the browser makes no card
        # for it. The group stays narrowed to its other dashboard.
        plain = _cards({"type": "tile", "entity": "light.hall"})
        found = await _entities({"plain": plain, "yaml": "broken"})
        self.assertIn("light.hall", found)
        self.assertIn("can be loaded", await self._reason({"yaml": "broken"}))

    async def test_badge_of_the_energy_settings(self) -> None:
        dashboard = {"views": [{"badges": [{"type": "gas-total"}], "cards": []}]}
        self.assertIn("gas-total", await self._reason({"d": dashboard}))

    async def test_area_view_strategy_is_no_area_card(self) -> None:
        view = {"views": [{"strategy": {"type": "area", "area": "kitchen"}}]}
        self.assertEqual(_discovery.area_cards(view), [])

    async def test_default_dashboard_is_the_lovelace_dashboard_when_it_exists(self) -> None:
        # The lovelace commands of Home Assistant take "lovelace" before the key None.
        dashboards = {
            "lovelace": _cards({"type": "tile", "entity": "light.hall"}),
            None: None,
        }
        found = await _entities(dashboards, keys=["__default__"])
        self.assertIn("light.hall", found)

    async def test_default_dashboard_is_the_key_none_with_no_lovelace_dashboard(self) -> None:
        dashboards = {None: _cards({"type": "tile", "entity": "light.second"})}
        self.assertIn("light.second", await _entities(dashboards, keys=["__default__"]))


class EntityScanTest(unittest.IsolatedAsyncioTestCase):
    """The entities that the scan of a stored dashboard finds."""

    async def test_entity_after_a_line_break_or_a_tab_in_a_string(self) -> None:
        card = {"type": "custom:list-card", "entities": "light.hall\nlight.second\tlight.third"}
        template = {"type": "markdown", "content": "Value:\nsensor.bare is on"}
        found = await _entities({"d": _cards(card, template)})
        self.assertLessEqual({"light.hall", "light.second", "light.third", "sensor.bare"}, found)

    async def test_value_that_json_does_not_know(self) -> None:
        # A YAML dashboard can hold a date with no quotes.
        card = {"type": "tile", "entity": "light.hall", "since": datetime.date(2026, 1, 1)}
        self.assertIn("light.hall", await _entities({"d": _cards(card)}))

    async def test_entity_as_a_key(self) -> None:
        card = {"type": "custom:state-map", "states": {"light.second": {"icon": "mdi:lamp"}}}
        self.assertIn("light.second", await _entities({"d": _cards(card)}))

    async def test_person_of_each_user_of_the_group(self) -> None:
        found = await _entities({"d": _cards({"type": "tile", "entity": "light.hall"})})
        self.assertIn("person.kiosk", found)
        self.assertNotIn("person.anna", found)
        # The person of a user is no person that a card names, so no zone follows.
        self.assertNotIn("zone.work", found)

    async def test_location_condition_gives_each_zone(self) -> None:
        card = {
            "type": "tile",
            "entity": "light.hall",
            "visibility": [{"condition": "location", "locations": ["zone.home"]}],
        }
        self.assertIn("zone.work", await _entities({"d": _cards(card)}))

    async def test_tile_card_of_a_person_gives_each_zone(self) -> None:
        card = {"type": "tile", "entity": "person.anna"}
        self.assertIn("zone.work", await _entities({"d": _cards(card)}))

    async def test_tile_card_of_a_device_tracker_gives_each_zone(self) -> None:
        # The tile card gives a device tracker the same zone badge as a person.
        card = {"type": "tile", "entity": "device_tracker.phone"}
        self.assertIn("zone.work", await _entities({"d": _cards(card)}))

    async def test_map_card_that_shows_all(self) -> None:
        found = await _entities({"d": _cards({"type": "map", "show_all": True})})
        self.assertLessEqual({"person.anna", "device_tracker.phone", "zone.work"}, found)
        self.assertNotIn("geo_location.quake_1", found)

    async def test_map_card_with_geo_location_sources(self) -> None:
        card = {"type": "map", "entities": ["person.anna"], "geo_location_sources": ["all"]}
        found = await _entities({"d": _cards(card)})
        self.assertIn("geo_location.quake_1", found)
        self.assertNotIn("device_tracker.phone", found)

    async def test_updates_card_gives_each_update_entity(self) -> None:
        found = await _entities({"d": _cards({"type": "updates"})})
        self.assertLessEqual({"update.core", "update.card"}, found)

    async def test_dashboard_with_no_such_card_gets_no_domain(self) -> None:
        found = await _entities({"d": _cards({"type": "tile", "entity": "light.hall"})})
        self.assertEqual(found, {"sun.sun", "zone.home", "light.hall", "person.kiosk"})


if __name__ == "__main__":
    unittest.main()
