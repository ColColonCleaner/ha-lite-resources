"""Constants for Lite Resources."""

DOMAIN = "lite_resources"

# Each group of lite users is a config subentry of this type. Its title is the group name.
SUBENTRY_GROUP = "group"
CONF_NAME = "name"

# Fired on the event bus by the lovelace component when a dashboard configuration changes.
# The event data holds "url_path", which is None for the default dashboard.
EVENT_LOVELACE_UPDATED = "lovelace_updated"

# Fired on the event bus when the entity, device or area registry changes. A card that
# finds its entities in the registries can then show other entities.
REGISTRY_EVENTS = (
    "entity_registry_updated",
    "device_registry_updated",
    "area_registry_updated",
)
# The registries change in bursts. The open pages get one update this number of seconds
# after the first change of a burst.
REGISTRY_REFRESH_DELAY = 10
# The longest wait in seconds for the entity scan of one group. The changes to the open
# pages run one after the other, so a scan with no end would hold each later change.
SCAN_TIMEOUT = 30
# When the scan of a group fails, a later update tries it again. This is the largest
# number of such tries in a row, each REGISTRY_REFRESH_DELAY seconds after the one before.
UPDATE_RETRIES = 6

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

# Home Assistant 2026.11 shows the dashboard with this URL path as the default dashboard
# when it exists. Home Assistant's lovelace commands take it for a request with no URL
# path, before the dashboard with the key None.
LOVELACE_DASHBOARD = "lovelace"

# The websocket command the frontend uses to fetch the resource list.
WS_RESOURCES = "lovelace/resources"

# Dashboard keys that only work when a "mod" resource is loaded. These mods
# don't provide a card type, so they can't be found from "custom:" types.
# key in dashboard JSON -> substring of the resource URL that provides it.
KEY_HINTS: dict[str, str] = {
    "card_mod": "card-mod",
    "kiosk_mode": "kiosk-mode",
    # Advanced Camera Card: a camera with the key "webrtc_card" and no live provider takes
    # the live provider "webrtc-card" by itself, and waits for the <webrtc-camera> element.
    "webrtc_card": "webrtc-camera",
}

# Dashboard values that only work when another resource is loaded. The card that reads
# the value creates an element that the other resource defines, so no "custom:" type
# names that resource.
# value in dashboard JSON -> substring of the resource URL that provides it.
VALUE_HINTS: dict[str, str] = {
    # Advanced Camera Card: the live provider "webrtc-card" shows the stream in the
    # <webrtc-camera> element that the WebRTC Camera integration provides, and waits
    # for that element.
    "webrtc-card": "webrtc-camera",
}

# Custom cards that show one integration's entities. The card gets the list from the
# integration, and it reads each entity's state from the state stream.
# card type -> the integration whose entities the card shows.
CARD_PLATFORMS: dict[str, str] = {
    # Scheduler card: a schedule is a switch that the scheduler integration provides. The
    # card shows an empty row for a schedule whose switch has no state.
    "scheduler-card": "scheduler",
}

# State attributes that name other entities, which a card shows with the entity itself.
# the entity's integration (None: any) -> the attribute.
MEMBER_ATTRIBUTES: dict[str | None, str] = {
    # Light groups, old-style groups and other entities with members.
    None: "entity_id",
    # A schedule names the entities that its actions control.
    "scheduler": "entities",
}

SERVICE_PREVIEW = "preview"
