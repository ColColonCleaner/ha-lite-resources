"""Entities that a card finds by itself.

A dashboard names most of its entities, and the resolver finds those in the text of the
dashboard. Some cards name an area or an integration instead, and find their entities in the
registries of Home Assistant. A user with a narrowed state stream needs those entities too.

The rules of the area card follow the frontend: the card in
src/panels/lovelace/cards/hui-area-card.ts and its feature "area-controls" in
src/data/area/area_controls.ts. The card shows an entity of its area only when the entity
is not hidden and has no entity category. The Home Assistant imports are inside the
functions that need them, so that the selection logic runs in a plain unit test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .const import CARD_PLATFORMS

AREA_CARD_TYPE = "area"
AREA_CONTROLS_FEATURE = "area-controls"
# A dashboard, a view or a section with this key has no stored cards. The browser makes
# them from the registries and the states (src/data/lovelace/config/types.ts,
# isStrategyDashboard, and the same test for a view and a section).
STRATEGY_KEY = "strategy"
# Core cards and badges that find their entities by themselves, in a way that no rule of
# this module follows. The home-summary card filters each entity by domain and area
# (src/panels/lovelace/cards/hui-home-summary-card.ts). The energy, water and power cards
# and the three total badges take their entities from the energy settings. The names are
# those of src/panels/lovelace/create-element/create-card-element.ts and
# create-badge-element.ts of the frontend 20261028.5. A prefix is no test: the card feature
# "water-heater-operation-modes" is none of these.
UNSCOPED_TYPES = frozenset(
    {
        "home-summary",
        "energy-carbon-consumed-gauge",
        "energy-compare",
        "energy-date-selection",
        "energy-devices-detail-graph",
        "energy-devices-graph",
        "energy-distribution",
        "energy-gas-graph",
        "energy-grid-balance",
        "energy-grid-neutrality-gauge",
        "energy-sankey",
        "energy-self-sufficiency-gauge",
        "energy-solar-consumed-gauge",
        "energy-solar-graph",
        "energy-sources-table",
        "energy-usage-graph",
        "energy-water-graph",
        "power-sankey",
        "power-sources-graph",
        "water-flow-sankey",
        "water-sankey",
        "gas-total",
        "power-total",
        "water-total",
    }
)
# The features of a card have type names of their own, so no card type is read there.
FEATURES_KEY = "features"
# The map card shows each entity of some domains for two of its options
# (src/panels/lovelace/cards/hui-map-card.ts): `geo_location_sources` gives each
# geo_location entity, and `show_all` gives each person, device_tracker and zone entity.
MAP_CARD_TYPE = "map"
# Core cards that show each entity of a domain. The updates card counts each update entity
# (src/panels/lovelace/cards/hui-updates-card.ts).
DOMAIN_CARDS: dict[str, tuple[str, ...]] = {"updates": ("update",)}
# The visibility condition on the location of the user
# (src/panels/lovelace/common/validate-condition.ts).
LOCATION_CONDITION = "location"
# The domains of the control buttons of the feature "area-controls". The name of a cover
# control is "cover-" and its device class.
CONTROL_DOMAINS = ("light", "fan", "switch", "cover")
# An area card also reads these sensor classes from an attribute of entities of other domains.
ATTRIBUTE_SENSOR_DOMAINS: dict[str, tuple[str, ...]] = {
    "temperature": ("climate",),
    "humidity": ("climate", "humidifier"),
}


@dataclass(frozen=True)
class RegistryEntity:
    """What the registries and the state machine hold about one entity."""

    entity_id: str
    area_id: str | None = None
    platform: str | None = None
    hidden: bool = False
    category: str | None = None
    device_class: str | None = None

    @property
    def domain(self) -> str:
        """The domain of the entity."""
        return self.entity_id.partition(".")[0]


@dataclass(frozen=True)
class AreaCard:
    """What one area card shows of its area."""

    area_id: str
    camera: bool
    sensor_classes: frozenset[str]
    alert_classes: frozenset[str]
    control_domains: frozenset[str]

    def shows(self, entity: RegistryEntity) -> bool:
        """True when the card can show this entity."""
        if entity.area_id != self.area_id or entity.hidden or entity.category:
            return False
        domain = entity.domain
        if domain == "camera":
            return self.camera
        if domain == "sensor":
            return entity.device_class in self.sensor_classes
        if domain == "binary_sensor":
            return entity.device_class in self.alert_classes
        if domain in self.control_domains:
            return True
        return any(
            domain in ATTRIBUTE_SENSOR_DOMAINS.get(sensor_class, ())
            for sensor_class in self.sensor_classes
        )


def _strings(value: Any) -> frozenset[str]:
    """Return the strings of a configuration value that is a list or one string."""
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, list):
        return frozenset(item for item in value if isinstance(item, str))
    return frozenset()


def _control_domains(card: dict[str, Any]) -> frozenset[str]:
    """Return the domains of the control buttons of an area card."""
    domains: set[str] = set()
    features = card.get("features")
    for feature in features if isinstance(features, list) else []:
        if not isinstance(feature, dict) or feature.get("type") != AREA_CONTROLS_FEATURE:
            continue
        controls = feature.get("controls")
        if not isinstance(controls, list):
            # The feature shows each kind of control when its configuration names none.
            domains.update(CONTROL_DOMAINS)
            continue
        for control in controls:
            if isinstance(control, str):
                domain = control.partition("-")[0]
                if domain in CONTROL_DOMAINS:
                    domains.add(domain)
    return frozenset(domains)


def _area_card(card: dict[str, Any]) -> AreaCard:
    display = card.get("display_type") or (
        "camera" if card.get("show_camera") else "picture"
    )
    return AreaCard(
        area_id=card["area"],
        camera=display == "camera",
        sensor_classes=_strings(card.get("sensor_classes")),
        alert_classes=_strings(card.get("alert_classes")),
        control_domains=_control_domains(card),
    )


def area_cards(config: Any) -> list[AreaCard]:
    """Return each area card of a dashboard configuration, at any depth.

    The configuration of a strategy is left out: a strategy with the type "area" is no
    area card, and the browser makes its cards.
    """
    found: list[AreaCard] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == AREA_CARD_TYPE and isinstance(node.get("area"), str):
                found.append(_area_card(node))
            for key, value in node.items():
                if key != STRATEGY_KEY:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(config)
    return found


def has_strategy(config: Any) -> bool:
    """True when the dashboard, one of its views or one of their sections has a strategy.

    The frontend reads the key only at these three places (isStrategyDashboard,
    isStrategyView and isStrategySection). The same key in another mapping, such as an
    option of a custom card or the data of an action, is no strategy.
    """
    if not isinstance(config, dict):
        return False
    if STRATEGY_KEY in config:
        return True
    views = config.get("views")
    for view in views if isinstance(views, list) else []:
        if not isinstance(view, dict):
            continue
        if STRATEGY_KEY in view:
            return True
        sections = view.get("sections")
        for section in sections if isinstance(sections, list) else []:
            if isinstance(section, dict) and STRATEGY_KEY in section:
                return True
    return False


def unscoped_reason(config: Any) -> str | None:
    """Return why a dashboard configuration does not say which entities a page needs.

    None means that it does.
    """
    if has_strategy(config):
        return "a strategy, so the browser makes the cards"
    todo = [config]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            card_type = node.get("type")
            if isinstance(card_type, str) and card_type in UNSCOPED_TYPES:
                return f"the card or badge {card_type}, which finds its entities by itself"
            todo.extend(value for key, value in node.items() if key != FEATURES_KEY)
        elif isinstance(node, list):
            todo.extend(node)
    return None


def wide_domains(nodes: Iterable[Any]) -> set[str]:
    """Return the domains of which a card of the dashboard shows each entity."""
    domains: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        card_type = node.get("type")
        if card_type == MAP_CARD_TYPE:
            if node.get("geo_location_sources"):
                domains.add("geo_location")
            if node.get("show_all"):
                domains.update(("person", "device_tracker", "zone"))
        elif isinstance(card_type, str):
            domains.update(DOMAIN_CARDS.get(card_type, ()))
    return domains


def has_location_condition(nodes: Iterable[Any]) -> bool:
    """True when the dashboard holds a condition on the location of the user.

    The frontend then reads the person entity of the user and the zone entities.
    """
    return any(
        isinstance(node, dict) and node.get("condition") == LOCATION_CONDITION
        for node in nodes
    )


def card_platforms(custom_types: Iterable[str]) -> set[str]:
    """Return the integrations whose entities the custom cards of a dashboard show."""
    types = set(custom_types)
    return {platform for card, platform in CARD_PLATFORMS.items() if card in types}


def discovered_entities(
    cards: Iterable[AreaCard],
    platforms: Iterable[str],
    entities: Iterable[RegistryEntity],
) -> set[str]:
    """Return the entities that the area cards and the cards of these integrations show."""
    cards = list(cards)
    platforms = set(platforms)
    return {
        entity.entity_id
        for entity in entities
        if entity.platform in platforms or any(card.shows(entity) for card in cards)
    }


def registry_entities(hass: Any) -> list[RegistryEntity]:
    """Return each enabled entity of the entity registry, with its area and device class.

    The area is that of the entity, or else the effective area of its device: a child
    device with no area of its own has the area of its parent device. The device class is
    the attribute of the state, which is the value that the frontend filters on. An entity
    with no state yet takes the device class of the registry.
    """
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    devices = dr.async_get(hass)
    result: list[RegistryEntity] = []
    for entry in er.async_get(hass).entities.values():
        if entry.disabled:
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = devices.async_get(entry.device_id)
            if device is not None:
                area_id = dr.async_get_effective_area_id(hass, device)
        state = hass.states.get(entry.entity_id)
        if state is not None:
            device_class = state.attributes.get("device_class")
        else:
            device_class = entry.device_class or entry.original_device_class
        category = entry.entity_category
        result.append(
            RegistryEntity(
                entity_id=entry.entity_id,
                area_id=area_id,
                platform=entry.platform,
                hidden=entry.hidden,
                category=str(getattr(category, "value", category)) if category else None,
                device_class=device_class,
            )
        )
    return result


def area_sensor_entities(hass: Any, cards: Iterable[AreaCard]) -> set[str]:
    """Return the temperature and humidity entities that the areas of the cards name.

    An area can name one entity for its temperature and one for its humidity. An area card
    then shows that entity, which can belong to another area.
    """
    from homeassistant.helpers import area_registry as ar

    areas = ar.async_get(hass)
    found: set[str] = set()
    for card in cards:
        area = areas.async_get_area(card.area_id)
        for sensor_class in ("temperature", "humidity"):
            entity_id = getattr(area, f"{sensor_class}_entity_id", None)
            if entity_id and sensor_class in card.sensor_classes:
                found.add(entity_id)
    return found
