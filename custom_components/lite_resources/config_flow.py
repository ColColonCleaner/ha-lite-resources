"""Config flow for Lite Resources, and the subentry flow for its groups of lite users."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_ALWAYS_EXCLUDE,
    CONF_ALWAYS_INCLUDE,
    CONF_DASHBOARDS,
    CONF_EXTRA_ENTITIES,
    CONF_FILTER_STATES,
    CONF_INCLUDE_UNSCANNABLE,
    CONF_NAME,
    CONF_USERS,
    DEFAULT_DASHBOARD,
    DOMAIN,
    SUBENTRY_GROUP,
)
from .groups import groups_from_subentries, users_in_other_groups
from .resolver import async_all_resources


def _multi(options: list[SelectOptionDict]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN
        )
    )


def _with_stored(
    options: list[SelectOptionDict], stored: Any, label: str
) -> list[SelectOptionDict]:
    """Return the options, with each stored value that is no option any more.

    A select field refuses a value outside its options. A group can hold a user or a
    dashboard that was deleted, or a resource URL whose version changed. Without that
    value among the options, the group's form cannot be saved.
    """
    known = {option["value"] for option in options}
    gone = [
        value for value in stored or [] if isinstance(value, str) and value not in known
    ]
    return options + [
        SelectOptionDict(value=value, label=label.format(value)) for value in gone
    ]


async def _async_group_schema(
    hass: HomeAssistant, current: dict[str, Any], new_group: bool
) -> vol.Schema:
    """Return one group's form, with `current` as the values that it shows.

    A new group's state filter is on. A stored group with no such value does not
    narrow the states, so its form shows the filter as off.
    """
    all_users = [u for u in await hass.auth.async_get_users() if not u.system_generated]
    users = [
        SelectOptionDict(value=u.id, label=u.name or u.id)
        for u in all_users
        if u.is_active
    ]
    # A stored user that is not active any more exists, so the form shows its name.
    not_active = {u.id: u.name or u.id for u in all_users if not u.is_active}
    users += [
        SelectOptionDict(value=user_id, label=f"{not_active[user_id]} (not active)")
        for user_id in current.get(CONF_USERS) or []
        if user_id in not_active
    ]
    users = _with_stored(users, current.get(CONF_USERS), "{} (user not found)")
    dashboards = []
    for url_path, dashboard in hass.data[LOVELACE_DATA].dashboards.items():
        if url_path is None:
            dashboards.append(
                SelectOptionDict(value=DEFAULT_DASHBOARD, label="Overview (default)")
            )
            continue
        title = (getattr(dashboard, "config", None) or {}).get("title") or url_path
        dashboards.append(
            SelectOptionDict(value=url_path, label=f"{title} ({url_path})")
        )
    dashboards = _with_stored(
        dashboards, current.get(CONF_DASHBOARDS), "{} (dashboard not found)"
    )
    resources = [
        SelectOptionDict(value=r["url"], label=r["url"])
        for r in await async_all_resources(hass)
    ]
    stored_resources = [
        *current.get(CONF_ALWAYS_INCLUDE, []),
        *current.get(CONF_ALWAYS_EXCLUDE, []),
    ]
    resources = _with_stored(
        resources, stored_resources, "{} (not in the resource list now)"
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get(CONF_NAME, "")): TextSelector(),
            vol.Required(CONF_USERS, default=current.get(CONF_USERS, [])): _multi(
                users
            ),
            vol.Required(
                CONF_DASHBOARDS, default=current.get(CONF_DASHBOARDS, [])
            ): _multi(dashboards),
            vol.Required(
                CONF_FILTER_STATES,
                default=bool(current.get(CONF_FILTER_STATES, new_group)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_EXTRA_ENTITIES, default=current.get(CONF_EXTRA_ENTITIES, [])
            ): EntitySelector(EntitySelectorConfig(multiple=True)),
            vol.Required(
                CONF_INCLUDE_UNSCANNABLE,
                default=current.get(CONF_INCLUDE_UNSCANNABLE, True),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ALWAYS_INCLUDE, default=current.get(CONF_ALWAYS_INCLUDE, [])
            ): _multi(resources),
            vol.Optional(
                CONF_ALWAYS_EXCLUDE, default=current.get(CONF_ALWAYS_EXCLUDE, [])
            ): _multi(resources),
        }
    )


# The type checks run with no Home Assistant installation, so mypy does not know that
# ConfigFlow takes the keyword "domain".
class LiteResourcesConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Set up Lite Resources (single instance). The groups are added afterwards."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup. The entry itself holds no settings."""
        if user_input is not None:
            return self.async_create_entry(title="Lite Resources", data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types: one subentry for each group of lite users."""
        return {SUBENTRY_GROUP: GroupSubentryFlow}


class GroupSubentryFlow(ConfigSubentryFlow):
    """Add or change one group of lite users."""

    def _errors(
        self, user_input: dict[str, Any], group_id: str | None
    ) -> dict[str, str]:
        """Return the form errors for this input.

        `group_id` is the ID of the group, and None for a new group.
        """
        if not str(user_input.get(CONF_NAME, "")).strip():
            return {CONF_NAME: "no_name"}
        if not user_input.get(CONF_USERS):
            return {CONF_USERS: "no_users"}
        if not user_input.get(CONF_DASHBOARDS):
            return {CONF_DASHBOARDS: "no_dashboards"}
        groups = groups_from_subentries(self._get_entry().subentries)
        if users_in_other_groups(groups, group_id, user_input[CONF_USERS]):
            return {CONF_USERS: "user_in_other_group"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a group."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._errors(user_input, None)
            if not errors:
                data = dict(user_input)
                name = str(data.pop(CONF_NAME)).strip()
                return self.async_create_entry(title=name, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=await _async_group_schema(self.hass, user_input or {}, True),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a group."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._errors(user_input, subentry.subentry_id)
            if not errors:
                data = dict(user_input)
                name = str(data.pop(CONF_NAME)).strip()
                # The entry's update listener gives the open pages the new settings.
                return self.async_update_and_abort(
                    entry, subentry, title=name, data=data
                )
        current = user_input or {CONF_NAME: subentry.title, **subentry.data}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=await _async_group_schema(self.hass, current, False),
            errors=errors,
        )
