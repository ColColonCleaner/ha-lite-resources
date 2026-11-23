"""Constants for Lite Resources."""

DOMAIN = "lite_resources"

# Each group of light users is a config subentry of this type. Its title is the group name.
SUBENTRY_GROUP = "group"
CONF_NAME = "name"

# Fired on the event bus by the lovelace component when a dashboard configuration changes.
# The event data holds "url_path", which is None for the default dashboard.
EVENT_LOVELACE_UPDATED = "lovelace_updated"

CONF_USERS = "users"
CONF_DASHBOARDS = "dashboards"
CONF_ALWAYS_INCLUDE = "always_include"
CONF_ALWAYS_EXCLUDE = "always_exclude"
CONF_INCLUDE_UNSCANNABLE = "include_unscannable"
CONF_FILTER_STATES = "filter_states"
CONF_EXTRA_ENTITIES = "extra_entities"

# The websocket command the frontend uses to stream entity states.
WS_SUBSCRIBE_ENTITIES = "subscribe_entities"

# Always sent when filtering states: the frontend uses these outside any card.
BASE_ENTITIES = ("sun.sun", "zone.home")

# Value used in the dashboards selector for the default (Overview) dashboard,
# whose url_path is None.
DEFAULT_DASHBOARD = "__default__"

# The websocket command the frontend uses to fetch the resource list.
WS_RESOURCES = "lovelace/resources"

# Dashboard keys that only work when a "mod" resource is loaded. These mods
# don't provide a card type, so they can't be found from "custom:" types.
# key in dashboard JSON -> substring of the resource URL that provides it.
KEY_HINTS: dict[str, str] = {
    "card_mod": "card-mod",
    "kiosk_mode": "kiosk-mode",
}

# Dashboard values that only work when another resource is loaded. The card that reads
# the value makes an element of that resource itself, so no "custom:" type names it.
# value in dashboard JSON -> substring of the resource URL that provides it.
VALUE_HINTS: dict[str, str] = {
    # Advanced Camera Card: the live provider "webrtc-card" shows the stream in the
    # <webrtc-camera> element of the WebRTC Camera integration, and waits for it.
    "webrtc-card": "webrtc-camera",
}

SERVICE_PREVIEW = "preview"
