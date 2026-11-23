"""Shared helpers of the tests.

`load` loads one module of the integration without a Home Assistant checkout.
`install_homeassistant_stubs` puts stand-ins for the Home Assistant modules that the
integration imports into `sys.modules`.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "lite_resources"


def load(module_name: str, filename: str):
    """Load one integration module without running the package __init__."""
    package = sys.modules.setdefault("lite_resources", types.ModuleType("lite_resources"))
    package.__path__ = [str(PACKAGE)]
    package.__package__ = "lite_resources"
    spec = importlib.util.spec_from_file_location(module_name, PACKAGE / filename)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "lite_resources"
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _module(name: str) -> types.ModuleType:
    """Return the module with this name from sys.modules, and make an empty one if needed."""
    module = sys.modules.setdefault(name, types.ModuleType(name))
    parent, _, child = name.rpartition(".")
    if parent:
        # `from parent import child` reads the attribute, because a stand-in has no __path__.
        setattr(_module(parent), child, module)
    return module


def _default(module: types.ModuleType, name: str, value: Any) -> None:
    """Set an attribute of a stand-in module only when another test file did not set it."""
    if not hasattr(module, name):
        setattr(module, name, value)


@dataclass(frozen=True)
class ConfigSubentry:
    """Stand-in for homeassistant.config_entries.ConfigSubentry."""

    data: Any
    subentry_type: str
    title: str
    unique_id: str | None
    subentry_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class Event:
    """Stand-in for homeassistant.core.Event."""

    data: dict[str, Any]


def _websocket_command(schema: dict[Any, Any]):
    """Stand-in for websocket_api.websocket_command: keep the command name and the schema."""

    def decorate(func):
        func._ws_command = next(v for k, v in schema.items() if str(k) == "type")
        func._ws_schema = schema
        return func

    return decorate


def _async_register_command(hass, command_or_handler, handler=None, schema=None) -> None:
    """Stand-in for websocket_api.async_register_command."""
    if handler is None:
        handler = command_or_handler
        command = handler._ws_command
        schema = handler._ws_schema
    else:
        command = command_or_handler
    hass.data.setdefault("websocket_api", {})[command] = (handler, schema)


FILTER_KEYS = ("domains", "entity_globs", "entities")


def empty_filter_part() -> dict[str, list[str]]:
    """Return what the schema of subscribe_entities adds for "include" and for "exclude"."""
    return {key: [] for key in FILTER_KEYS}


def _convert_include_exclude_filter(msg: dict[str, Any]) -> SimpleNamespace:
    """Stand-in for entityfilter.convert_include_exclude_filter.

    As in Home Assistant, it reads "include" and "exclude" with no default, so a message
    that did not pass the schema raises KeyError.
    """
    include, exclude = msg["include"], msg["exclude"]
    return SimpleNamespace(
        empty_filter=not any(include[key] or exclude[key] for key in FILTER_KEYS)
    )


def _async_register_admin_service(
    hass, domain, service, func, schema=None, supports_response=None, **kwargs
) -> None:
    """Stand-in for helpers.service.async_register_admin_service."""
    hass.services.async_register(domain, service, func, supports_response=supports_response)
    hass.services.admin_only.add((domain, service))


def _async_at_started(hass, at_start_cb):
    """Stand-in for helpers.start.async_at_started.

    The callback runs at once when the start is complete (`hass.started`), and otherwise
    at the event homeassistant_started. The result removes a listener that still waits.
    """
    if hass.started:
        hass.async_create_task(at_start_cb(hass))
        return lambda: None
    waiting: list[Any] = []

    def run(event) -> None:
        waiting.clear()
        hass.async_create_task(at_start_cb(hass))

    waiting.append(hass.bus.async_listen_once("homeassistant_started", run))

    def cancel() -> None:
        while waiting:
            waiting.pop()()

    return cancel


def _effective_area_id(hass, device) -> str | None:
    """Stand-in for device_registry.async_get_effective_area_id.

    A child device with no area of its own has the area of its parent device.
    """
    if device.area_id:
        return device.area_id
    parent_id = getattr(device, "parent_device_id", None)
    parent = hass.device_registry.async_get(parent_id) if parent_id else None
    return parent.area_id if parent else None


def install_homeassistant_stubs() -> None:
    """Add each missing stand-in. The order of the test files does not matter."""
    try:
        import voluptuous  # noqa: F401
    except ImportError:
        vol = _module("voluptuous")
        _default(vol, "Required", lambda key, **kwargs: key)
        _default(vol, "Optional", lambda key, **kwargs: key)
        _default(vol, "Schema", lambda schema, **kwargs: schema)

    _default(
        _module("homeassistant.components.lovelace.const"), "LOVELACE_DATA", "lovelace"
    )

    exceptions = _module("homeassistant.exceptions")
    if not hasattr(exceptions, "HomeAssistantError"):

        class HomeAssistantError(Exception):
            """Stand-in for the core error."""

        exceptions.HomeAssistantError = HomeAssistantError
    if not hasattr(exceptions, "ConfigEntryNotReady"):

        class ConfigEntryNotReady(exceptions.HomeAssistantError):
            """Stand-in for the error that asks Home Assistant to try the setup again."""

        exceptions.ConfigEntryNotReady = ConfigEntryNotReady

    _default(
        _module("homeassistant.helpers.service"),
        "async_register_admin_service",
        _async_register_admin_service,
    )
    _default(
        _module("homeassistant.helpers.start"), "async_at_started", _async_at_started
    )

    core = _module("homeassistant.core")
    _default(core, "HomeAssistant", object)
    _default(core, "Event", Event)
    _default(core, "ServiceCall", object)
    _default(core, "ServiceResponse", dict)
    _default(core, "SupportsResponse", SimpleNamespace(ONLY="only"))
    _default(core, "callback", lambda func: func)

    config_entries = _module("homeassistant.config_entries")
    _default(config_entries, "ConfigEntry", object)
    _default(config_entries, "ConfigSubentry", ConfigSubentry)

    websocket_api = _module("homeassistant.components.websocket_api")
    _default(websocket_api, "DOMAIN", "websocket_api")
    _default(websocket_api, "ActiveConnection", object)
    _default(websocket_api, "websocket_command", _websocket_command)
    # The real decorator runs the handler as a task. Here a test awaits the handler.
    _default(websocket_api, "async_response", lambda func: func)
    _default(websocket_api, "async_register_command", _async_register_command)

    _default(
        _module("homeassistant.helpers.entityfilter"),
        "convert_include_exclude_filter",
        _convert_include_exclude_filter,
    )

    # Each registry of a test is an attribute of its stand-in for hass.
    for name in ("entity_registry", "device_registry", "area_registry"):
        _default(
            _module(f"homeassistant.helpers.{name}"),
            "async_get",
            lambda hass, name=name: getattr(hass, name),
        )
    _default(
        _module("homeassistant.helpers.device_registry"),
        "async_get_effective_area_id",
        _effective_area_id,
    )
