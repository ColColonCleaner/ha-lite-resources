"""Work out which dashboard resources a set of dashboards actually needs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
import gzip
import json
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
# neither form, name no card. The key is "type" or a name that ends in "_type", and not
# a longer word such as "prototype". Group 1 is the quote of the second form, and group
# 2 is the type, which can hold a dot as the name of a custom element can.
_CUSTOM_TYPE_INSIDE = re.compile(
    r"""(?:(?<![A-Za-z0-9])type["']?\s*[:=]\s*["']?|(["'`]))"""
    r"""custom:([a-z0-9](?:[a-z0-9_.-]*[a-z0-9])?)(?(1)\1)"""
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
# decorator. The resource scan cannot read which names such a file registers.
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
# these names stays under the option "Include resources that the integration cannot
# read".
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
# The value of the last warning for each subject, such as the error text of a dashboard
# that cannot be loaded.
_WARNED: dict[tuple[Any, ...], Any] = {}
# The dashboard that the current task loads now: its URL path, and "active" while the
# load runs. A task that starts during the load holds the same record, and "active" is
# False for it when the load is over. A task that runs beside the load has no record.
_OWN_LOAD: ContextVar[dict[str, Any] | None] = ContextVar(
    "lite_resources_own_load", default=None
)
# What the last load by this integration gave for each URL path: _NO_CONFIG,
# _LOAD_FAILED, or the configuration with its text. _ANNOUNCED stands for an update
# event from another task with no load by this integration after it.
_SEEN: dict[Any, Any] = {}
_NOT_SEEN = object()
_NO_CONFIG = object()
_LOAD_FAILED = object()
_ANNOUNCED = object()
# The functions that async_listen_changes added.
_CHANGE_LISTENERS: list[Callable[[Any], None]] = []


def _warn_change(key: tuple[Any, ...], value: Any, message: str, *args: Any) -> None:
    """Write a warning to the log when its value is new.

    A warning at each request hides a new one.
    """
    if _WARNED.get(key, _NOT_SEEN) != value:
        _WARNED[key] = value
        _LOGGER.warning(message, *args)


class CannotNarrow(Exception):
    """The dashboards of a group do not say what a page in that group needs.

    The caller then sends all states, or the full resource list. The text is the reason.
    `retry` is True when a retry can work, such as after a dashboard load that failed.
    """

    def __init__(self, reason: str, retry: bool = False) -> None:
        super().__init__(reason)
        self.retry = retry


@dataclass
class Resolution:
    """Outcome of the resource scan for a set of dashboards."""

    included: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    needed_types: list[str] = field(default_factory=list)
    unresolved_types: list[str] = field(default_factory=list)
    unverified_types: list[str] = field(default_factory=list)
    # Needed types that no file registers in a way that the resource scan can read. Each
    # file that names such a type in quotes is included for it.
    guessed_types: list[str] = field(default_factory=list)
    # Readable files in which the resource scan finds no element, which are not
    # included. Such a file works by a side effect, such as an icon set, or it is a card
    # that the dashboards do not use and whose registration the resource scan cannot
    # read.
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
                # Only such a file can register a name that the resource scan cannot
                # read. A file whose registrations all have a quoted name registers no
                # other one.
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
    # A minified file binds one short name more than once, so each value counts.
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
        # Only the stored collection can be not loaded yet. The YAML collection is
        # loaded from its start, and it has no load function.
        load = getattr(resources, "async_load", None)
        if load is not None:
            await load()
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
    """Return the DashboardScan of each dashboard with a stored configuration.

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
            _warn_change(("no dashboard", key), True, "Dashboard %s not found", key)
            continue
        _WARNED.pop(("no dashboard", key), None)
        url_path = getattr(
            dashboard, "url_path", None if key == DEFAULT_DASHBOARD else key
        )
        load = {"url_path": url_path, "active": True}
        token = _OWN_LOAD.set(load)
        try:
            config = await dashboard.async_load(False)
        except ConfigNotFound:  # no stored configuration: the browser makes the cards
            without_config.append(key)
            state: Any = _NO_CONFIG
        except (HomeAssistantError, OSError) as err:
            # Such as a YAML dashboard with a syntax error, or one whose file is gone.
            failed[key] = str(err) or type(err).__name__
            state = _LOAD_FAILED
        else:
            scans.append(scan_dashboard(key, config))
            state = config
        finally:
            # A task that started during the load holds the same record.
            load["active"] = False
            _OWN_LOAD.reset(token)
        _note_state(url_path, state)
    if not scans and not without_config:
        if failed:
            raise _load_failure(failed)
        raise CannotNarrow("no dashboard in the group exists")
    return scans, without_config, failed


def _load_failure(failed: dict[str, str]) -> CannotNarrow:
    """Return the error for the first dashboard that could not be loaded.

    Such a dashboard can load at a retry, so the error asks for one.
    """
    key, error = next(iter(failed.items()))
    return CannotNarrow(f"the dashboard {key} cannot be loaded: {error}", retry=True)


def _note_state(url_path: str | None, state: Any) -> None:
    """Keep what a load of a dashboard gave, and call the change listeners when it is new.

    `state` is the configuration, _NO_CONFIG or _LOAD_FAILED. Each load by this
    integration comes here, whether an event came with it or not. So the listeners hear
    of each change that this integration sees: a changed YAML file that an entity scan
    or a resource scan finds first, and a dashboard that loads again after a fault. The
    first load of a dashboard is no change. A load that fails is none either: the entity
    scan that found it gets a retry, and the pages of each other group keep their
    entities until the dashboard loads. A file that fires its event at each load gives
    the same configuration each time, so it calls no listener. The first load after
    `note_event` calls none either, because the event of that call started an update
    already.
    """
    previous = _SEEN.get(url_path, _NOT_SEEN)
    if state is _LOAD_FAILED:
        _SEEN[url_path] = state
        return
    if state is _NO_CONFIG:
        changed = previous is not state
        _SEEN[url_path] = state
    elif isinstance(previous, tuple) and previous[0] is state:
        # The same object as at the last load: a stored dashboard with no new save, or
        # a YAML dashboard from the cache of Home Assistant.
        return
    else:
        text = _configuration_text(state)
        changed = not (isinstance(previous, tuple) and previous[1] == text)
        _SEEN[url_path] = (state, text)
    if changed and previous is not _NOT_SEEN and previous is not _ANNOUNCED:
        for listener in _CHANGE_LISTENERS.copy():
            listener(url_path)


def note_event(url_path: str | None) -> None:
    """Record an update event of this dashboard that came from another task.

    Such an event comes from a save, or from the load of a browser that found a changed
    YAML file. The caller starts an update of each group with the dashboard. The entity
    scans of that update load the configuration that the event announced, so the first
    load after the event is no second change. A change after that load is a change
    again.
    """
    _SEEN[url_path] = _ANNOUNCED


def _configuration_text(config: Any) -> str:
    """Return a text that is equal for two loads of the same configuration.

    Two loads of one YAML file give two objects. Their comparison as values fails for a
    value that is not equal to itself, such as a NaN number, so the texts are compared.
    """
    try:
        return json.dumps(config, default=str)
    except (TypeError, ValueError):  # such as a key that JSON cannot hold
        return repr(config)


def is_own_load(url_path: str | None) -> bool:
    """True while this integration loads this dashboard in the current task.

    An entity scan and a resource scan each load a group's dashboards. Home Assistant
    fires the update event of a YAML dashboard inside the load that finds the changed
    file, and it calls each listener immediately, in the task of that load. So a
    listener that gets True here sees the event of a load that this integration
    started. The integration itself reports the change, through the change listeners.
    An event from the load of another task gives False.
    """
    load = _OWN_LOAD.get()
    return load is not None and load["active"] and load["url_path"] == url_path


def forget_warnings() -> None:
    """Forget each warning of this module.

    A new setup then writes its warnings to the log again.
    """
    _WARNED.clear()


def async_listen_changes(listener: Callable[[Any], None]) -> Callable[[], None]:
    """Call the listener with the URL path of a dashboard whose state is new at a load.

    `_note_state` says what counts as new. Return the function that removes the listener.
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

    Any existing entity ID that appears anywhere in the dashboards (cards, pop-ups,
    conditions, actions), the entities that a card finds by itself (the area card, a card
    in CARD_PLATFORMS, and a card that shows each entity in a domain), the members of any
    groups among them, the person entity of each user in the group, the configured extras,
    and a few that the frontend uses itself.

    CannotNarrow is raised when the dashboards do not say which entities a page needs: a
    dashboard with no stored configuration, a strategy, or a card that no rule follows.

    `include_missing` keeps each entity ID that has no state now. A state subscription
    needs those entity IDs: Home Assistant sends only the entities in the subscription's
    list, and an entity can get its first state after a page connects, for example while
    Home Assistant starts.
    """
    scans, without_config, failed = await _async_dashboard_scans(
        hass, list(options.get(CONF_DASHBOARDS, []))
    )
    if failed:
        # A page can open this dashboard after a correction, so a set with no entity of
        # that dashboard is no result. The caller retries the entity scan later.
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
    domains = {state.domain for state in states} | {
        entity.domain for entity in entities
    }
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
    # The frontend finds the logged-in user's person by a search of all states, for a
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
        # An entity ID with no state that is an action's name, such as light.turn_on, is
        # no entity. Each other entity ID with no state stays: its first state can come
        # later.
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
    scans, _without_config, failed = await _async_dashboard_scans(
        hass, result.dashboards
    )
    # A dashboard that cannot be loaded shows no card in the browser, so its resources
    # are not counted. The warning comes again when the error text changes, and when
    # the error comes back after a load that worked.
    for key in result.dashboards:
        if key in failed:
            _warn_change(
                ("load failed", key),
                failed[key],
                "Dashboard %s cannot be loaded, so the resource list leaves it out: %s",
                key,
                failed[key],
            )
        else:
            _WARNED.pop(("load failed", key), None)
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
    # The names that a file registers. None for a file that the resource scan cannot
    # read.
    names: frozenset[str] | None
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
        names = await hass.async_add_executor_job(cache.names, path) if path else None
        if not path or names is None:
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

    # A file can register an element in a way that the resource scan cannot read, such
    # as a minified decorator. So for a needed type that no file provides, each file
    # that names the type in quotes is included. A type with a provider never takes this
    # way, so a file that only mentions another file's card stays out.
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
            # The resource scan finds no element in the file. Such a file works by a
            # side effect, or it is a card whose registration the resource scan cannot
            # read.
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
