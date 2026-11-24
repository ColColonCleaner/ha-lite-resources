"""Work out which dashboard resources a set of dashboards actually needs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
import gzip
import logging
import os
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from homeassistant.components.lovelace.const import LOVELACE_DATA, ConfigNotFound
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    BASE_ENTITIES,
    CONF_ALWAYS_EXCLUDE,
    CONF_ALWAYS_INCLUDE,
    CONF_DASHBOARDS,
    CONF_EXTRA_ENTITIES,
    CONF_INCLUDE_UNSCANNABLE,
    CONF_USERS,
    DEFAULT_DASHBOARD,
    KEY_HINTS,
    LOVELACE_DASHBOARD,
    MEMBER_ATTRIBUTES,
    VALUE_HINTS,
)
from .discovery import (
    AreaCard,
    area_cards,
    area_sensor_entities,
    card_platforms,
    discovered_entities,
    has_location_condition,
    registry_entities,
    unscoped_reason,
    wide_domains,
)

_LOGGER = logging.getLogger(__name__)

# A dashboard string that is "custom:xxx" as a whole (cards, rows, badges, features, and
# cards nested inside pop-ups, stacks, sections or the options of other cards).
_CUSTOM_TYPE = re.compile(r"custom:([A-Za-z0-9_.\-]+)")
# "custom:xxx" inside a longer string names a card in two forms. The first form follows a
# key "type", with quotes or with none, as in YAML text. The second form is a quoted text
# by itself, such as the value that a template returns. The same words in plain text, in
# neither form, name no card. Group 1 is the quote of the second form, and group 2 is the
# type.
_CUSTOM_TYPE_INSIDE = re.compile(
    r"""(?:type["']?\s*[:=]\s*["']?|(["'`]))"""
    r"""custom:([a-z0-9](?:[a-z0-9_-]*[a-z0-9])?)(?(1)\1)"""
)
# A dashed name this file actually registers, not every hyphenated token it
# mentions. Mentions of another card ("button-card" inside an unrelated file)
# must not pull that file in.
_DEFINE_LITERAL = re.compile(
    rb"""customElements\.define\(\s*["'`]([a-z][a-z0-9_]*(?:-[a-z0-9_]+)+)["'`]"""
)
_DEFINE_IDENT = re.compile(
    rb"""customElements\.define\(\s*([A-Za-z_$][A-Za-z0-9_$]{2,40})\s*[,)]"""
)
_ASSIGN = re.compile(
    rb"""(?<![A-Za-z0-9_$])([A-Za-z_$][A-Za-z0-9_$]{0,40})\s*=\s*(["'])([a-z0-9_-]{1,80})\2"""
)
# Mushroom (and similar bundles) build the element name: `${prefix}-light-card`.
_TEMPLATE = re.compile(
    rb"""\$\{([A-Za-z_$][A-Za-z0-9_$]{0,40})\}(-[a-z0-9]+(?:-[a-z0-9]+)*)"""
)
# A name that a file builds from two quoted pieces counts where the file gives it to
# customElements.define or assigns it to a variable. Two pieces with a plus between them
# in another place, such as an argument or a property like className, are no element of
# the file.
_CONCAT_USED = re.compile(
    rb"""(?:customElements\.define\(|(?<![A-Za-z0-9_$.])[A-Za-z_$][A-Za-z0-9_$]{0,40}\s*=)"""
    # A third piece after the two gives another name, so such a pair is no name.
    rb"""\s*(["'])([a-z0-9_-]+)\1\s*\+\s*(["'])([a-z0-9_-]+)\3(?!\s*\+)"""
)
# Two quoted pieces with a plus in any place. Such a name is no registration by itself. It
# counts as a name that the file holds, for the guess of a type with no provider. A third
# piece before the two, or after them, gives another name. So a pair with a plus after it
# does not match, and the caller drops a pair with a plus before it, which group 1 holds.
_CONCAT_ANY = re.compile(
    rb"""(\+\s*)?(["'])([a-z0-9_-]+)\2\s*\+\s*(["'])([a-z0-9_-]+)\4(?!\s*\+)"""
)
# A registration whose name is no quoted text, such as the call inside a minified
# decorator. The scan cannot see which names such a file registers.
_DEFINE_OPAQUE = re.compile(rb"""customElements\.define\(\s*[A-Za-z_$]""")
# The key "type" as a whole word. A key that ends in "type", such as layout_type, is a
# card's option and no registration.
_CUSTOM_CARD_TYPE = re.compile(
    rb"""(?<![A-Za-z0-9_$])type\s*:\s*["']([a-z][a-z0-9_]*(?:-[a-z0-9_]+)+)["']"""
)
# custom:keymaster is implemented by <ll-strategy-dashboard-keymaster>.
_STRATEGY_TYPE = re.compile(
    rb"""ll-strategy-(?:dashboard|view|section)-([a-z0-9]+(?:-[a-z0-9]+)*)"""
)
_QUOTED = re.compile(rb"""["'`]([a-z][a-z0-9_]*(?:-[a-z0-9_]+)+)["'`]""")
_CARDISH = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
# File names that do not identify one card. An unreadable resource with one of
# these names stays under the "include resources that can't be checked" option.
_GENERIC_STEMS = frozenset(
    {
        "app",
        "bundle",
        "card",
        "cards",
        "dist",
        "frontend",
        "index",
        "loader",
        "main",
        "module",
        "plugin",
        "polyfill",
        "resource",
        "resources",
        "script",
        "scripts",
    }
)
# The keys of the warnings that the log already holds.
_WARNED: set[tuple[Any, ...]] = set()
# The dashboard that the current task loads now: its URL path, "active" while the load
# runs, and "fired" when the dashboard's update event came during the load. Each task has
# its own value, so an event from the load of another task does not count.
_OWN_LOAD: ContextVar[dict[str, Any] | None] = ContextVar(
    "lite_resources_own_load", default=None
)
# The configuration that the last load by this integration gave, by the URL path.
_SEEN: dict[Any, Any] = {}
_NOT_SEEN = object()
# The functions that async_listen_changes added.
_CHANGE_LISTENERS: list[Callable[[Any], None]] = []


def _warn_once(key: tuple[Any, ...], message: str, *args: Any) -> None:
    """Log a warning one time. A warning at each request from each page hides a new one."""
    if key not in _WARNED:
        _WARNED.add(key)
        _LOGGER.warning(message, *args)


class CannotNarrow(Exception):
    """The dashboards of a group do not say what a page in that group needs.

    The caller then sends all states, or the full resource list. The text is the reason.
    `retry` is True when a later try can work, such as after a dashboard load that failed.
    """

    def __init__(self, reason: str, retry: bool = False) -> None:
        super().__init__(reason)
        self.retry = retry


@dataclass
class Resolution:
    """Outcome of resolving the resources for a set of dashboards."""

    included: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    needed_types: list[str] = field(default_factory=list)
    unresolved_types: list[str] = field(default_factory=list)
    unverified_types: list[str] = field(default_factory=list)
    # Needed types that no file registers in a way that the scan sees. Each file that
    # names such a type in quotes is included for it.
    guessed_types: list[str] = field(default_factory=list)
    # Readable files in which the scan sees no element, which are not included. Such a
    # file works by a side effect, such as an icon set, or it is a card that the
    # dashboards do not use and whose registration the scan cannot see.
    excluded_without_element: list[str] = field(default_factory=list)
    dashboards: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a summary suitable for a service response."""
        return {
            "dashboards": self.dashboards,
            "needed_types": self.needed_types,
            "unresolved_types": self.unresolved_types,
            "unverified_types": self.unverified_types,
            "guessed_types": self.guessed_types,
            "included": [r["url"] for r in self.included],
            "excluded": [r["url"] for r in self.excluded],
            "excluded_without_element": self.excluded_without_element,
        }


class FileCache:
    """Cache of the names found in each resource file, keyed by mtime/size."""

    def __init__(self) -> None:
        """Initialise an empty cache."""
        self._cache: dict[
            str, tuple[tuple[int, int], frozenset[str], frozenset[str]]
        ] = {}

    def _read(self, path: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """Return the registered names and the quoted names in a file, or None."""
        for candidate, opener in ((path, open), (path + ".gz", gzip.open)):
            try:
                stat = os.stat(candidate)
            except (OSError, ValueError):  # ValueError: a null character in the path
                continue
            key = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(candidate)
            if cached and cached[0] == key:
                return cached[1], cached[2]
            try:
                with opener(candidate, "rb") as fh:
                    data = fh.read()
            # A cut or corrupt .gz file raises an error that is no OSError.
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Cannot read %s: %s", candidate, err)
                return None
            found = names_in_javascript(data, _stem_from_filename(candidate))
            mentioned: frozenset[str] = frozenset()
            if _DEFINE_OPAQUE.search(data):
                # Only such a file can register a name that the scan does not see. A file
                # whose registrations all have a quoted name registers no other one.
                pairs = (
                    (left + right).decode()
                    for plus, _q1, left, _q2, right in _CONCAT_ANY.findall(data)
                    if not plus
                )
                mentioned = frozenset(
                    {name.decode() for name in _QUOTED.findall(data)}
                    | {name for name in pairs if _CARDISH.match(name)}
                )
            self._cache[candidate] = (key, found, mentioned)
            return found, mentioned
        return None

    def names(self, path: str) -> frozenset[str] | None:
        """Return the dashed names a file registers (runs in the executor)."""
        read = self._read(path)
        return None if read is None else read[0]

    def mentions(self, path: str) -> frozenset[str] | None:
        """Return each dashed name that a file can register with no visible registration.

        That is each name in quotes, and each name of two quoted pieces, of a file that
        holds a registration with no quoted name. Another file gives an empty set. It runs
        in the executor.
        """
        read = self._read(path)
        return None if read is None else read[1]


def names_in_javascript(data: bytes, stem: str = "") -> frozenset[str]:
    """Return card and strategy types a resource file registers.

    Quoted hyphenated words are not enough. Mushroom's bundle never contains
    the literal ``mushroom-light-card``; it assigns ``prefix = "mushroom"`` and
    defines ``${prefix}-light-card``. Other files mention card names they do
    not provide (a lock card that talks about ``button-card``), and those
    mentions must not count. A constant inside a file whose name is that card
    still counts (``button-card.js`` containing ``"button-card"``).
    """
    found: set[str] = set()
    # A minified file binds one short name more than one time, so each value counts.
    bindings: dict[str, set[str]] = {}
    for ident, _quote, value in _ASSIGN.findall(data):
        bindings.setdefault(ident.decode(), set()).add(value.decode())

    def consider(name: str) -> None:
        if _CARDISH.match(name):
            found.add(name)

    for literal in _DEFINE_LITERAL.findall(data):
        consider(literal.decode())
    for ident in _DEFINE_IDENT.findall(data):
        for value in bindings.get(ident.decode(), ()):
            consider(value)
    for _q1, left, _q2, right in _CONCAT_USED.findall(data):
        consider(left.decode() + right.decode())
    for ident, tail in _TEMPLATE.findall(data):
        for base in bindings.get(ident.decode(), ()):
            consider(base + tail.decode())
    for card_type in _CUSTOM_CARD_TYPE.findall(data):
        consider(card_type.decode())
    for strategy in _STRATEGY_TYPE.findall(data):
        name = strategy.decode()
        if re.fullmatch(r"[a-z][a-z0-9-]+", name):
            found.add(name)
    if len(stem) >= 3 and stem not in _GENERIC_STEMS and "_" not in stem:
        prefix = stem + "-"
        for quoted in _QUOTED.findall(data):
            name = quoted.decode()
            if name == stem or name.startswith(prefix):
                consider(name)
    return frozenset(found)


def _stem_from_filename(path: str) -> str:
    """Stem of a file on disk, ignoring a trailing ``.gz``."""
    name = os.path.basename(path).lower().removesuffix(".gz")
    return resource_stem(name)


def resource_stem(url: str) -> str:
    """Return the lower-case file name of a resource without its script suffix."""
    name = os.path.basename(urlsplit(url).path).lower()
    for suffix in (".js", ".mjs"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def resource_key(url: str) -> tuple[str, str]:
    """Return a resource URL's host and path.

    The query string is left out: it carries a version that changes on updates.
    """
    parts = urlsplit(url)
    return parts.netloc.lower(), parts.path


def types_for_stem(stem: str, needed: set[str]) -> set[str]:
    """Card types a file name itself accounts for.

    The whole stem has to be the type or its leading prefix (``mushroom.js``
    provides ``mushroom-light-card``). A shared piece is not enough, so
    ``dreame-vacuum-card.js`` does not provide ``mushroom-vacuum-card`` and
    ``lock-manager.js`` does not provide ``mushroom-lock-card``.
    """
    if len(stem) < 3 or stem in _GENERIC_STEMS:
        return set()
    if "_" in stem:
        return {name for name in needed if name == stem}
    prefix = stem + "-"
    return {name for name in needed if name == stem or name.startswith(prefix)}


def stem_names_unused_card(stem: str, needed: set[str]) -> bool:
    """True when the file name is a particular card these dashboards don't use.

    Generic names (``frontend.js``) and integration scripts such as
    ``browser_mod.js`` are not specific enough to drop unread.
    """
    if len(stem) < 3 or stem in _GENERIC_STEMS or "_" in stem:
        return False
    if types_for_stem(stem, needed):
        return False
    return "-" in stem or len(stem) >= 6


def url_to_path(hass: HomeAssistant, url: str) -> str | None:
    """Map a resource URL to a local file, or None if it isn't a local file.

    A URL with a host is another server's file, whatever its path is.
    """
    parts = urlsplit(url)
    if parts.netloc:
        return None
    path = parts.path
    if path.startswith("/local/"):
        base, rel = hass.config.path("www"), path[len("/local/") :]
    elif path.startswith("/hacsfiles/"):
        base, rel = hass.config.path("www", "community"), path[len("/hacsfiles/") :]
    else:
        return None
    # The same form for both paths, so that the folder test compares like with like.
    base = os.path.normpath(base)
    full = os.path.normpath(os.path.join(base, unquote(rel)))
    if not full.startswith(base + os.sep):
        return None
    return full


async def async_all_resources(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return every configured dashboard resource, as core would send it."""
    resources = hass.data[LOVELACE_DATA].resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    return list(resources.async_items() or [])


@dataclass
class DashboardScan:
    """The strings, the keys and the mappings in one dashboard configuration."""

    key: str
    config: Any
    strings: set[str] = field(default_factory=set)
    keys: set[str] = field(default_factory=set)
    nodes: list[Any] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Each string and each key, one on a line, for a search of the whole dashboard."""
        return "\n".join(self.strings | self.keys)

    def custom_types(self) -> set[str]:
        """Return each custom type that the dashboard names."""
        found: set[str] = set()
        for text in self.strings:
            whole = _CUSTOM_TYPE.fullmatch(text)
            if whole:
                found.add(whole.group(1))
            elif "custom:" in text:
                found.update(m.group(2) for m in _CUSTOM_TYPE_INSIDE.finditer(text))
        return found


def scan_dashboard(key: str, config: Any) -> DashboardScan:
    """Walk a dashboard configuration, and return its strings, keys and mappings.

    The walk reads the values themselves and not their JSON text. In JSON text, a line
    break inside a string is a backslash and a letter, which hides the entity ID after it,
    and a value that JSON does not know, such as a date in a YAML dashboard, has no text.
    """
    scan = DashboardScan(key, config)
    todo = [config]
    while todo:
        node = todo.pop()
        if isinstance(node, str):
            scan.strings.add(node)
        elif isinstance(node, Mapping):
            scan.nodes.append(node)
            for name, value in node.items():
                if isinstance(name, str):
                    scan.keys.add(name)
                todo.append(value)
        elif isinstance(node, (list, tuple)):
            todo.extend(node)
    return scan


async def _async_dashboard_scans(
    hass: HomeAssistant, keys: list[str]
) -> tuple[list[DashboardScan], list[str], dict[str, str]]:
    """Return a scan of each dashboard with a stored configuration.

    The second value names each dashboard that exists and has no stored configuration,
    so the browser makes its cards. The third value gives the error text for each
    dashboard that exists and cannot be loaded, such as a YAML dashboard with a syntax
    error. A dashboard that does not exist is left out of all three. CannotNarrow is
    raised when the first two values are empty, with the load error when there is one.
    """
    dashboards = hass.data[LOVELACE_DATA].dashboards
    scans: list[DashboardScan] = []
    without_config: list[str] = []
    failed: dict[str, str] = {}
    for key in keys:
        if key == DEFAULT_DASHBOARD:
            # As Home Assistant's lovelace commands do for a request with no URL path.
            dashboard = dashboards.get(LOVELACE_DASHBOARD) or dashboards.get(None)
        else:
            dashboard = dashboards.get(key)
        if dashboard is None:
            _warn_once(("no dashboard", key), "Dashboard %s not found", key)
            continue
        _WARNED.discard(("no dashboard", key))
        url_path = getattr(dashboard, "url_path", None if key == DEFAULT_DASHBOARD else key)
        load = {"url_path": url_path, "active": True, "fired": False}
        token = _OWN_LOAD.set(load)
        try:
            config = await dashboard.async_load(False)
        except ConfigNotFound:  # no stored configuration: the browser makes the cards
            without_config.append(key)
            continue
        except HomeAssistantError as err:  # such as a YAML dashboard with a syntax error
            failed[key] = str(err)
            continue
        finally:
            # A task that started during the load holds a copy of the record.
            load["active"] = False
            _OWN_LOAD.reset(token)
        previous = _SEEN.get(url_path, _NOT_SEEN)
        _SEEN[url_path] = config
        if load["fired"] and previous is not config and previous != config:
            # This load found the change, so no other event tells the open pages. A file
            # that fires at each load gives the same configuration, and stops here.
            for listener in _CHANGE_LISTENERS.copy():
                listener(url_path)
        scans.append(scan_dashboard(key, config))
    if not scans and not without_config:
        if failed:
            raise _load_failure(failed)
        raise CannotNarrow("no dashboard in the group exists")
    return scans, without_config, failed


def _load_failure(failed: dict[str, str]) -> CannotNarrow:
    """Return the error for the first dashboard that could not be loaded.

    Such a dashboard can load at a later try, so the error asks for one.
    """
    key, error = next(iter(failed.items()))
    return CannotNarrow(f"the dashboard {key} cannot be loaded: {error}", retry=True)


def own_load_fired(url_path: str | None) -> bool:
    """True when the update event of this dashboard came from this task's own load of it.

    Home Assistant fires the update event of a YAML dashboard inside the load that finds
    the changed file, and it calls each listener at once. So a listener that runs in the
    task of a scan, while that scan loads the dashboard, sees the event of that load. The
    scan then compares the new configuration with the last one, and calls the change
    listeners when the two differ. An event from the load of another task gives False.
    """
    load = _OWN_LOAD.get()
    if load is None or not load["active"] or load["url_path"] != url_path:
        return False
    load["fired"] = True
    return True


def async_listen_changes(listener: Callable[[Any], None]) -> Callable[[], None]:
    """Call the listener with the URL path of a dashboard whose own load found a change.

    Return the function that removes the listener.
    """
    _CHANGE_LISTENERS.append(listener)

    def remove() -> None:
        if listener in _CHANGE_LISTENERS:
            _CHANGE_LISTENERS.remove(listener)

    return remove


async def async_dashboard_entities(
    hass: HomeAssistant, options: dict[str, Any], include_missing: bool = False
) -> set[str]:
    """Return every entity the configured dashboards can show.

    Any existing entity id that appears anywhere in the dashboards (cards, pop-ups,
    conditions, actions), the entities that a card finds by itself (the area card, a card
    in CARD_PLATFORMS, and a card that shows each entity in a domain), the members of any
    groups among them, the person entity of each user in the group, the configured extras,
    and a few that the frontend uses itself.

    CannotNarrow is raised when the dashboards do not say which entities a page needs: a
    dashboard with no stored configuration, a strategy, or a card that no rule follows.

    `include_missing` keeps each name that has no state now. A state subscription needs
    those names: the stream sends only the entities in its list, and an entity can get its
    first state after a page connects, for example while Home Assistant starts.
    """
    scans, without_config, failed = await _async_dashboard_scans(
        hass, list(options.get(CONF_DASHBOARDS, []))
    )
    if failed:
        # The page can open this dashboard after a correction, and no event is sure to
        # come then. So the group gets all states, and the caller tries again later.
        raise _load_failure(failed)
    if without_config:
        raise CannotNarrow(
            f"the dashboard {without_config[0]} has no stored configuration, so the "
            "browser makes its cards"
        )
    for scan in scans:
        reason = unscoped_reason(scan.config)
        if reason:
            raise CannotNarrow(f"the dashboard {scan.key} holds {reason}")

    entities = registry_entities(hass)
    states = hass.states.async_all()
    # The registry holds an entity's domain before the entity has a state.
    domains = {state.domain for state in states} | {entity.domain for entity in entities}
    if not domains:
        return set()
    pattern = re.compile(
        r"(?<![\w.])(?:"
        + "|".join(sorted(map(re.escape, domains), key=len, reverse=True))
        + r")\.[a-z0-9_]+"
    )
    found: set[str] = set(BASE_ENTITIES) | set(options.get(CONF_EXTRA_ENTITIES, []))
    cards: list[AreaCard] = []
    platforms: set[str] = set()
    wide: set[str] = set()
    location = False
    for scan in scans:
        found.update(pattern.findall(scan.text))
        cards.extend(area_cards(scan.config))
        platforms |= card_platforms(scan.custom_types())
        wide |= wide_domains(scan.nodes)
        location = location or has_location_condition(scan.nodes)
    if cards or platforms:
        # The entities that a card finds in the registries, which the text does not name.
        found |= discovered_entities(cards, platforms, entities)
        found |= area_sensor_entities(hass, cards)
    # The badge that a tile card shows for a person or for a device tracker reads each
    # zone entity (src/panels/lovelace/cards/tile/badges/tile-badge.ts). A condition on
    # the user's location reads each zone entity also.
    if location or any(
        entity_id.startswith(("person.", "device_tracker.")) for entity_id in found
    ):
        wide.add("zone")
    if wide:
        found.update(state.entity_id for state in states if state.domain in wide)
        found.update(entity.entity_id for entity in entities if entity.domain in wide)
    # The frontend finds the signed-in user's person by a search of all states, for a
    # condition on the user's location and for the user's picture.
    users = set(options.get(CONF_USERS, []))
    found.update(
        state.entity_id
        for state in states
        if state.domain == "person" and state.attributes.get("user_id") in users
    )
    # The attribute that names an entity's members, for an entity whose integration has
    # an attribute of its own.
    member_attribute = {
        entity.entity_id: MEMBER_ATTRIBUTES[entity.platform]
        for entity in entities
        if entity.platform in MEMBER_ATTRIBUTES
    }
    # add group members (light groups, old-style groups, ...), recursively
    todo = list(found)
    while todo:
        entity_id = todo.pop()
        state = hass.states.get(entity_id)
        if state is None:
            continue
        for attribute in (MEMBER_ATTRIBUTES[None], member_attribute.get(entity_id)):
            members = state.attributes.get(attribute) if attribute else None
            if isinstance(members, (list, tuple)):
                for member in members:
                    if isinstance(member, str) and member not in found:
                        found.add(member)
                        todo.append(member)
    if include_missing:
        # A name with no state that is an action's name, such as light.turn_on, is
        # no entity. Each other name with no state stays: its first state can come later.
        return {
            entity_id
            for entity_id in found
            if hass.states.get(entity_id) is not None
            or not hass.services.has_service(*entity_id.split(".", 1))
        }
    return {e for e in found if hass.states.get(e) is not None}


async def async_resolve(
    hass: HomeAssistant, options: dict[str, Any], cache: FileCache
) -> Resolution:
    """Split the resources into those the configured dashboards need and the rest.

    CannotNarrow is raised when no dashboard in the options exists, and when none of
    them can be loaded.
    """
    result = Resolution(dashboards=list(options.get(CONF_DASHBOARDS, [])))
    # Match on the host and the path: the query string carries a version that changes
    # on updates.
    always = {resource_key(u) for u in options.get(CONF_ALWAYS_INCLUDE, [])}
    # Explicit exclusion wins, including over Always include and a real card match.
    excluded_keys = {resource_key(u) for u in options.get(CONF_ALWAYS_EXCLUDE, [])}
    include_unscannable = options.get(CONF_INCLUDE_UNSCANNABLE, True)

    needed: set[str] = set()
    hints: set[str] = set()
    # A dashboard with no stored configuration holds core cards only, so it needs no
    # resource.
    scans, _without_config, failed = await _async_dashboard_scans(hass, result.dashboards)
    # A dashboard that cannot be loaded shows no card in the browser, so its resources
    # are not counted. The warning comes again when the error text changes.
    for key, error in failed.items():
        _warn_once(
            ("load failed", key, error),
            "Dashboard %s cannot be loaded, so the resource list leaves it out: %s",
            key,
            error,
        )
    loaded = set(result.dashboards) - set(failed)
    for warned in [w for w in _WARNED if w[0] == "load failed" and w[1] in loaded]:
        _WARNED.discard(warned)
    for scan in scans:
        needed.update(scan.custom_types())
        named = scan.keys | scan.strings
        hints.update(sub for k, sub in KEY_HINTS.items() if k in named)
        hints.update(sub for v, sub in VALUE_HINTS.items() if v in named)
    result.needed_types = sorted(needed)

    provided: set[str] = set()
    # The needed types of the resources that Always exclude names. The user refused their
    # provider, so no other file is sent for them as a guess.
    refused: set[str] = set()
    # The readable files that provide no needed type, each with its path.
    unmatched: list[tuple[dict[str, Any], str, frozenset[str]]] = []
    for item in await async_all_resources(hass):
        url = item.get("url", "")
        if resource_key(url) in excluded_keys:
            result.excluded.append(item)
            path = url_to_path(hass, url)
            names = (
                await hass.async_add_executor_job(cache.names, path) if path else None
            )
            refused |= types_for_stem(resource_stem(url), needed)
            refused |= needed & (names or frozenset())
            continue
        if resource_key(url) in always or item.get("type") == "css":
            result.included.append(item)
            continue
        if any(sub in url for sub in hints):
            result.included.append(item)
            continue
        stem = resource_stem(url)
        stem_types = types_for_stem(stem, needed)
        path = url_to_path(hass, url)
        names = (
            await hass.async_add_executor_job(cache.names, path) if path else None
        )
        if names is None:
            # Served by an integration, missing, or remote: contents can't be
            # checked. Keep it unless the file name is a card that isn't used.
            provided |= stem_types
            keep = bool(stem_types) or (
                include_unscannable and not stem_names_unused_card(stem, needed)
            )
            (result.included if keep else result.excluded).append(item)
            continue
        matched = (needed & names) | stem_types
        provided |= matched
        if matched:
            result.included.append(item)
        else:
            unmatched.append((item, path, names))

    # A file can register an element in a way that the scan does not see, such as a
    # minified decorator. So for a needed type that no file provides, each file that
    # names the type in quotes is included. A type with a provider never takes this way,
    # so a file that only mentions another file's card stays out.
    guessed: set[str] = set()
    for item, path, names in unmatched:
        missing = needed - provided - refused
        mentioned = (
            await hass.async_add_executor_job(cache.mentions, path) if missing else None
        )
        hit = missing & mentioned if mentioned else set()
        if hit:
            guessed |= hit
            result.included.append(item)
            continue
        result.excluded.append(item)
        if not names:
            # The scan sees no element in the file. Such a file works by a side effect,
            # or it is a card whose registration the scan cannot see.
            result.excluded_without_element.append(item.get("url", ""))
    provided |= guessed
    result.guessed_types = sorted(guessed)

    missing_types = sorted(needed - provided)
    if any(url_to_path(hass, r.get("url", "")) is None for r in result.included):
        # An included resource we couldn't read may well provide these.
        result.unverified_types = missing_types
    else:
        result.unresolved_types = missing_types
    return result
