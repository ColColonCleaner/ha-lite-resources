"""Entities that a card finds by itself: the area card and the scheduler card.

The cases come from a kitchen tablet. Its dashboard holds area cards for two doors and a
scheduler card. No card of that dashboard names the lights, the motion sensors or the
schedules that those cards show.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from support import install_homeassistant_stubs, load

install_homeassistant_stubs()

load("lite_resources.const", "const.py")
_discovery = load("lite_resources.discovery", "discovery.py")
_resolver = load("lite_resources.resolver", "resolver.py")

RegistryEntity = _discovery.RegistryEntity
area_cards = _discovery.area_cards

CAMERA_CARD = {
    "type": "area",
    "area": "side_door",
    "display_type": "camera",
    "camera_view": "live",
    "alert_classes": ["motion"],
    "sensor_classes": ["temperature", "humidity"],
    "features": [{"type": "area-controls", "controls": ["light"]}],
}
COMPACT_CARD = {
    "type": "area",
    "area": "backyard",
    "alert_classes": ["motion", "occupancy"],
    "features": [{"type": "area-controls"}],
}


def _dashboard() -> dict:
    """A sections dashboard: the cards sit some levels below the views."""
    return {
        "views": [
            {
                "type": "sections",
                "sections": [
                    {"type": "grid", "cards": [CAMERA_CARD, {"type": "tile", "entity": "lock.side_door"}]},
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "vertical-stack", "cards": [COMPACT_CARD]},
                            {"type": "custom:scheduler-card", "include": ["climate"]},
                        ],
                    },
                ],
            }
        ]
    }


class AreaCardTest(unittest.TestCase):
    """What an area card shows of its area."""

    def setUp(self) -> None:
        self.camera, self.compact = area_cards(_dashboard())

    def test_cards_are_found_at_any_depth(self) -> None:
        self.assertEqual(self.camera.area_id, "side_door")
        self.assertEqual(self.compact.area_id, "backyard")

    def test_card_reads_its_display_and_its_classes(self) -> None:
        self.assertTrue(self.camera.camera)
        self.assertEqual(self.camera.sensor_classes, {"temperature", "humidity"})
        self.assertEqual(self.camera.alert_classes, {"motion"})
        self.assertFalse(self.compact.camera)
        self.assertEqual(self.compact.sensor_classes, set())

    def test_old_camera_option_counts(self) -> None:
        (card,) = area_cards({"type": "area", "area": "porch", "show_camera": True})
        self.assertTrue(card.camera)

    def test_controls_come_from_the_feature(self) -> None:
        self.assertEqual(self.camera.control_domains, {"light"})
        # A feature with no list shows each kind of control.
        self.assertEqual(self.compact.control_domains, {"light", "fan", "switch", "cover"})
        (cover,) = area_cards(
            {
                "type": "area",
                "area": "garage",
                "features": [{"type": "area-controls", "controls": ["cover-garage", {"entity_id": "light.a"}]}],
            }
        )
        self.assertEqual(cover.control_domains, {"cover"})
        (plain,) = area_cards({"type": "area", "area": "hall"})
        self.assertEqual(plain.control_domains, set())

    def test_card_shows_the_entities_of_its_area_by_domain_and_class(self) -> None:
        def shown(entity_id, **more) -> bool:
            more.setdefault("area_id", "side_door")
            return self.camera.shows(RegistryEntity(entity_id, **more))

        self.assertTrue(shown("camera.side_door"))
        self.assertTrue(shown("light.side_door"))
        self.assertTrue(shown("sensor.side_temp", device_class="temperature"))
        self.assertTrue(shown("binary_sensor.doorbell_side_motion", device_class="motion"))
        # A climate entity gives the temperature of an area from an attribute.
        self.assertTrue(shown("climate.side_room"))
        # Not in the lists of the card.
        self.assertFalse(shown("sensor.side_power", device_class="power"))
        self.assertFalse(shown("binary_sensor.side_door_open", device_class="door"))
        self.assertFalse(shown("switch.side_door"))
        self.assertFalse(shown("lock.side_door"))

    def test_card_skips_hidden_and_diagnostic_entities_and_other_areas(self) -> None:
        motion = {"device_class": "motion", "area_id": "side_door"}
        self.assertFalse(
            self.camera.shows(RegistryEntity("binary_sensor.cam_motion", hidden=True, **motion))
        )
        self.assertFalse(
            self.camera.shows(
                RegistryEntity("binary_sensor.cam_fault", category="diagnostic", **motion)
            )
        )
        self.assertFalse(
            self.camera.shows(RegistryEntity("light.kitchen", area_id="kitchen"))
        )
        self.assertFalse(self.camera.shows(RegistryEntity("light.no_area")))

    def test_camera_shows_only_on_a_camera_display(self) -> None:
        camera = RegistryEntity("camera.backyard", area_id="backyard")
        self.assertFalse(self.compact.shows(camera))


class CardPlatformTest(unittest.TestCase):
    """A custom card that shows the entities of one integration."""

    def test_scheduler_card_names_the_scheduler_integration(self) -> None:
        self.assertEqual(
            _discovery.card_platforms(["scheduler-card", "mushroom-light-card"]), {"scheduler"}
        )
        self.assertEqual(_discovery.card_platforms(["mushroom-light-card"]), set())

    def test_entities_of_the_integration_are_found(self) -> None:
        entities = [
            RegistryEntity("switch.schedule_1", platform="scheduler"),
            RegistryEntity("switch.porch", platform="shelly"),
        ]
        self.assertEqual(
            _discovery.discovered_entities([], {"scheduler"}, entities), {"switch.schedule_1"}
        )


class _Dashboard:
    def __init__(self, config) -> None:
        self._config = config

    async def async_load(self, force):
        return self._config


def _entry(entity_id, **more) -> SimpleNamespace:
    values = {"area_id": None, "device_id": None, "platform": "test", "disabled": False,
              "hidden": False, "entity_category": None, "device_class": None,
              "original_device_class": None}
    values.update(more)
    return SimpleNamespace(entity_id=entity_id, **values)


class _States:
    def __init__(self, states: dict[str, dict]) -> None:
        self._states = {
            entity_id: SimpleNamespace(domain=entity_id.partition(".")[0], attributes=attributes)
            for entity_id, attributes in states.items()
        }

    def async_all(self):
        return list(self._states.values())

    def get(self, entity_id):
        return self._states.get(entity_id)


class DashboardEntitiesTest(unittest.IsolatedAsyncioTestCase):
    """The entity set of a group whose dashboard holds such cards."""

    async def asyncSetUp(self) -> None:
        entries = [
            _entry("lock.side_door", area_id="side_door"),
            _entry("camera.side_door", area_id="side_door"),
            _entry("light.side_door", area_id="side_door"),
            # The area comes from the device, and for a child device from its parent.
            _entry("light.porch", device_id="d-switch"),
            _entry("binary_sensor.doorbell_side_motion", device_id="d-child"),
            _entry("binary_sensor.side_door_cam_motion", area_id="side_door", hidden=True),
            _entry("sensor.side_door_cam_fps", area_id="side_door",
                   entity_category=SimpleNamespace(value="diagnostic")),
            _entry("binary_sensor.side_door_open", area_id="side_door"),
            _entry("binary_sensor.backyard_person_occupancy", area_id="backyard"),
            _entry("light.disabled", area_id="side_door", disabled=True),
            _entry("light.kitchen", area_id="kitchen"),
            _entry("sensor.temp_outside", area_id="backyard"),
            _entry("switch.schedule_1", platform="scheduler"),
            _entry("climate.thermostat", area_id="hall"),
            _entry("climate.attic", area_id="attic"),
        ]
        devices = {
            "d-switch": SimpleNamespace(area_id="side_door", parent_device_id=None),
            "d-parent": SimpleNamespace(area_id="side_door", parent_device_id=None),
            "d-child": SimpleNamespace(area_id=None, parent_device_id="d-parent"),
        }
        areas = {
            # The area names the sensor of another area for its temperature.
            "side_door": SimpleNamespace(temperature_entity_id="sensor.temp_outside", humidity_entity_id=None),
            "backyard": SimpleNamespace(temperature_entity_id=None, humidity_entity_id=None),
        }
        classes = {
            "binary_sensor.doorbell_side_motion": "motion",
            "binary_sensor.side_door_cam_motion": "motion",
            "binary_sensor.side_door_open": "door",
            "binary_sensor.backyard_person_occupancy": "occupancy",
            "sensor.temp_outside": "temperature",
        }
        states = {
            entry.entity_id: {"device_class": classes.get(entry.entity_id)}
            for entry in entries
            if not entry.disabled
        }
        states["switch.schedule_1"] = {"entities": ["climate.thermostat"]}
        states["sun.sun"] = {}
        self.hass = SimpleNamespace(
            data={"lovelace": SimpleNamespace(dashboards={"kitchen": _Dashboard(_dashboard()),
                                                         "plain": _Dashboard({"views": [{"cards": [
                                                             {"type": "tile", "entity": "lock.side_door"}]}]})})},
            states=_States(states),
            entity_registry=SimpleNamespace(entities={entry.entity_id: entry for entry in entries}),
            device_registry=SimpleNamespace(async_get=devices.get),
            area_registry=SimpleNamespace(async_get_area=areas.get),
        )

    async def test_area_cards_and_scheduler_card_add_their_entities(self) -> None:
        found = await _resolver.async_dashboard_entities(self.hass, {"dashboards": ["kitchen"]})
        self.assertEqual(
            found,
            {
                "sun.sun",
                # Named by a card.
                "lock.side_door",
                # The area card of the side door: its camera, its light control, its motion
                # alert, and the temperature entity that the area names.
                "camera.side_door",
                "light.side_door",
                "light.porch",
                "binary_sensor.doorbell_side_motion",
                "sensor.temp_outside",
                # The area card of the backyard: its occupancy alert.
                "binary_sensor.backyard_person_occupancy",
                # The scheduler card: the schedule, and the entity that the schedule controls.
                "switch.schedule_1",
                "climate.thermostat",
            },
        )

    async def test_dashboard_without_such_cards_adds_nothing(self) -> None:
        found = await _resolver.async_dashboard_entities(self.hass, {"dashboards": ["plain"]})
        self.assertEqual(found, {"sun.sun", "lock.side_door"})


class StartupTest(unittest.IsolatedAsyncioTestCase):
    """A page that connects while Home Assistant starts.

    The registries are complete at that time, and many entities have no state yet. The
    cameras of one home got their first state 27 seconds after the start, later than the
    page of a tablet connected.
    """

    async def asyncSetUp(self) -> None:
        entries = [
            _entry("lock.side_door", area_id="side_door"),
            # No camera has a state yet, so the state machine does not hold the domain.
            _entry("camera.side_door", area_id="side_door"),
            # The device class of an entity with no state comes from the registry.
            _entry("binary_sensor.doorbell_side_motion", area_id="side_door",
                   original_device_class="motion"),
            _entry("binary_sensor.side_door_open", area_id="side_door",
                   original_device_class="door"),
            _entry("light.side_door", area_id="side_door"),
        ]
        dashboard = {"views": [{"cards": [
            CAMERA_CARD,
            {"type": "tile", "entity": "lock.side_door"},
            {"type": "picture-entity", "entity": "camera.side_door"},
        ]}]}
        self.hass = SimpleNamespace(
            data={"lovelace": SimpleNamespace(dashboards={"kitchen": _Dashboard(dashboard)})},
            states=_States({"lock.side_door": {}, "sun.sun": {}}),
            entity_registry=SimpleNamespace(entities={entry.entity_id: entry for entry in entries}),
            device_registry=SimpleNamespace(async_get={}.get),
            area_registry=SimpleNamespace(
                async_get_area=lambda area_id: SimpleNamespace(
                    temperature_entity_id=None, humidity_entity_id=None
                )
            ),
        )

    async def test_subscription_holds_the_entities_with_no_state_yet(self) -> None:
        found = await _resolver.async_dashboard_entities(
            self.hass, {"dashboards": ["kitchen"]}, include_missing=True
        )
        # Named by a card, in a domain that has no state yet.
        self.assertIn("camera.side_door", found)
        # Found by the area card: the device class comes from the registry.
        self.assertIn("binary_sensor.doorbell_side_motion", found)
        self.assertIn("light.side_door", found)
        self.assertNotIn("binary_sensor.side_door_open", found)

    async def test_list_of_the_entities_holds_only_those_with_a_state(self) -> None:
        found = await _resolver.async_dashboard_entities(self.hass, {"dashboards": ["kitchen"]})
        self.assertEqual(found, {"sun.sun", "lock.side_door"})


if __name__ == "__main__":
    unittest.main()
