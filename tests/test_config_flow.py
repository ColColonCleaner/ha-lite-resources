"""The form for a group of lite users: its options, its defaults and its checks."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from support import ConfigSubentry, _default, _module, install_homeassistant_stubs, load

install_homeassistant_stubs()

# What a schema raises for a value that a selector refuses. The schema of voluptuous
# raises its own error for the ValueError of the stand-in selector. The stand-in schema
# passes the ValueError on.
try:
    from voluptuous import Invalid as _Invalid
except ImportError:
    _REFUSED: tuple[type[Exception], ...] = (ValueError,)
else:
    _REFUSED = (ValueError, _Invalid)


class _Flow:
    """Stand-in for Home Assistant's flow base classes: each result is a dict."""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__()

    def async_show_form(self, **values) -> dict:
        return {"type": "form", **values}

    def async_create_entry(self, **values) -> dict:
        return {"type": "create_entry", **values}

    def async_update_and_abort(self, entry, subentry, **values) -> dict:
        return {"type": "abort", "subentry": subentry, **values}


class _Selector:
    """Stand-in for a selector. It keeps its configuration.

    With options, it refuses a value outside them, as SelectSelector.__call__ of Home
    Assistant does for a field with no custom value. As that function does, it also
    refuses a value that is no list for a field that takes more than one value.
    """

    def __init__(self, config=None) -> None:
        self.config = config or {}

    def __call__(self, value):
        options = self.config.get("options") if isinstance(self.config, dict) else None
        if options is not None:
            if self.config.get("multiple") and not isinstance(value, list):
                raise ValueError("Value should be a list")
            allowed = {option["value"] for option in options}
            for item in value if isinstance(value, list) else [value]:
                if item not in allowed:
                    raise ValueError(f"value must be one of {sorted(allowed)}")
        return value


_config_entries = _module("homeassistant.config_entries")
for _name in ("ConfigFlow", "ConfigSubentryFlow"):
    _default(_config_entries, _name, _Flow)
for _name in ("ConfigFlowResult", "SubentryFlowResult"):
    _default(_config_entries, _name, dict)
_selector = _module("homeassistant.helpers.selector")
for _name in ("BooleanSelector", "EntitySelector", "SelectSelector", "TextSelector"):
    _default(_selector, _name, _Selector)
_default(_selector, "EntitySelectorConfig", lambda **config: config)
_default(_selector, "SelectSelectorConfig", lambda **config: config)
_default(_selector, "SelectOptionDict", lambda **option: option)
_default(_selector, "SelectSelectorMode", SimpleNamespace(DROPDOWN="dropdown"))

load("lite_resources.const", "const.py")
load("lite_resources.groups", "groups.py")
load("lite_resources.resolver", "resolver.py")
_flow = load("lite_resources.config_flow", "config_flow.py")

USERS = [
    SimpleNamespace(id="u-w1", name="Workshop Kiosk 1", system_generated=False, is_active=True),
    SimpleNamespace(id="u-k", name="Kitchen Tablet", system_generated=False, is_active=True),
    SimpleNamespace(id="u-sys", name="Supervisor", system_generated=True, is_active=True),
    SimpleNamespace(id="u-old", name="Old Panel", system_generated=False, is_active=False),
]
RESOURCES = [{"url": "/local/a-card.js?v=2"}, {"url": "/local/b-card.js"}]


def _hass() -> SimpleNamespace:
    async def get_users():
        return USERS

    dashboards = {
        None: SimpleNamespace(config=None),
        "dashboard-workshop": SimpleNamespace(config={"title": "Workshop"}),
    }
    resources = SimpleNamespace(loaded=True, async_items=lambda: list(RESOURCES))
    return SimpleNamespace(
        auth=SimpleNamespace(async_get_users=get_users),
        data={"lovelace": SimpleNamespace(dashboards=dashboards, resources=resources)},
    )


async def _fields(current: dict, new_group: bool) -> dict:
    """Return each of the form's fields as (default, its option values)."""
    schema = await _flow._async_group_schema(_hass(), current, new_group)
    fields = {}
    for key, selector in schema.schema.items():
        options = selector.config.get("options") if isinstance(selector.config, dict) else None
        fields[str(key)] = (key.default(), [o["value"] for o in options or []])
    return fields


class GroupFormTest(unittest.IsolatedAsyncioTestCase):
    async def test_form_lists_the_users_the_dashboards_and_the_resources(self) -> None:
        fields = await _fields({}, True)
        self.assertEqual(fields["users"][1], ["u-w1", "u-k"])
        self.assertEqual(fields["dashboards"][1], ["__default__", "dashboard-workshop"])
        self.assertEqual(fields["always_include"][1], ["/local/a-card.js?v=2", "/local/b-card.js"])

    async def test_stored_value_that_is_no_option_now_stays_in_the_form(self) -> None:
        # A select field refuses a value outside its options. So a deleted user, a deleted
        # dashboard and a resource URL from an older version must stay among them.
        current = {
            "users": ["u-w1", "u-deleted"],
            "dashboards": ["dashboard-old"],
            "always_include": ["/local/a-card.js?v=1"],
            "always_exclude": ["/local/gone.js"],
        }
        fields = await _fields(current, False)
        self.assertIn("u-deleted", fields["users"][1])
        self.assertIn("dashboard-old", fields["dashboards"][1])
        for name in ("always_include", "always_exclude"):
            self.assertIn("/local/a-card.js?v=1", fields[name][1])
            self.assertIn("/local/gone.js", fields[name][1])

    async def test_form_takes_its_stored_values_and_refuses_an_unknown_one(self) -> None:
        current = {
            "name": "Workshop",
            "users": ["u-w1", "u-deleted", "u-old"],
            "dashboards": ["dashboard-old"],
        }
        schema = await _flow._async_group_schema(_hass(), current, False)
        defaults = {str(key): key.default() for key in schema.schema}
        self.assertEqual(schema(dict(defaults))["users"], ["u-w1", "u-deleted", "u-old"])
        with self.assertRaises(_REFUSED):
            schema({**defaults, "users": ["u-nobody"]})
        # A value that is no list is refused for a field that takes more than one value.
        with self.assertRaises(_REFUSED):
            schema({**defaults, "users": "u-w1"})

    async def test_stored_user_that_is_not_active_shows_its_name(self) -> None:
        schema = await _flow._async_group_schema(_hass(), {"users": ["u-old", "u-deleted"]}, False)
        users = next(s for key, s in schema.schema.items() if str(key) == "users")
        labels = {option["value"]: option["label"] for option in users.config["options"]}
        self.assertEqual(labels["u-old"], "Old Panel (not active)")
        self.assertEqual(labels["u-deleted"], "u-deleted (user not found)")
        # A user that is not active is no option for a group that does not hold it.
        self.assertNotIn("u-old", (await _fields({}, True))["users"][1])

    async def test_label_of_a_stored_value_says_that_it_is_gone(self) -> None:
        options = _flow._with_stored([{"value": "a", "label": "A"}], ["a", "b"], "{} (not found)")
        self.assertEqual(
            options, [{"value": "a", "label": "A"}, {"value": "b", "label": "b (not found)"}]
        )

    async def test_state_filter_is_on_for_a_new_group(self) -> None:
        self.assertIs((await _fields({}, True))["filter_states"][0], True)

    async def test_state_filter_of_a_stored_group_shows_its_value(self) -> None:
        # A group with no such value does not narrow the states.
        self.assertIs((await _fields({"users": ["u-w1"]}, False))["filter_states"][0], False)
        self.assertIs((await _fields({"filter_states": True}, False))["filter_states"][0], True)


class GroupChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        workshop = ConfigSubentry(
            data={"users": ["u-w1"], "dashboards": ["dashboard-workshop"]},
            subentry_type="group",
            title="Workshop kiosks",
            unique_id=None,
        )
        self.workshop_id = workshop.subentry_id
        entry = SimpleNamespace(subentries={workshop.subentry_id: workshop})
        self.flow = _flow.GroupSubentryFlow()
        self.flow._get_entry = lambda: entry

    def _errors(self, group_id=None, **changes) -> dict:
        values = {"name": "Kitchen", "users": ["u-k"], "dashboards": ["main-dashboard"]}
        return self.flow._errors({**values, **changes}, group_id)

    def test_complete_input_has_no_error(self) -> None:
        self.assertEqual(self._errors(), {})

    def test_each_missing_part_is_an_error(self) -> None:
        self.assertEqual(self._errors(name="  "), {"name": "no_name"})
        self.assertEqual(self._errors(users=[]), {"users": "no_users"})
        self.assertEqual(self._errors(dashboards=[]), {"dashboards": "no_dashboards"})

    def test_user_of_another_group_is_an_error(self) -> None:
        self.assertEqual(self._errors(users=["u-w1"]), {"users": "user_in_other_group"})

    def test_group_keeps_its_own_users_at_a_change(self) -> None:
        self.assertEqual(self._errors(self.workshop_id, users=["u-w1"]), {})


class GroupStepsTest(unittest.IsolatedAsyncioTestCase):
    """The group form's two steps: add a group, and change one."""

    def setUp(self) -> None:
        self.workshop = ConfigSubentry(
            data={"users": ["u-w1"], "dashboards": ["dashboard-workshop"]},
            subentry_type="group",
            title="Workshop",
            unique_id=None,
        )
        entry = SimpleNamespace(subentries={self.workshop.subentry_id: self.workshop})
        self.flow = _flow.GroupSubentryFlow()
        self.flow.hass = _hass()
        self.flow._get_entry = lambda: entry
        self.flow._get_reconfigure_subentry = lambda: self.workshop

    async def test_first_step_shows_the_form(self) -> None:
        result = await self.flow.async_step_user(None)
        self.assertEqual((result["type"], result["step_id"], result["errors"]), ("form", "user", {}))

    async def test_valid_input_makes_a_group_with_a_clean_name(self) -> None:
        values = {"name": "  Kitchen ", "users": ["u-k"], "dashboards": ["dashboard-workshop"]}
        result = await self.flow.async_step_user(dict(values))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "Kitchen")
        # The name is the group's title, and no part of its data.
        self.assertEqual(result["data"], {"users": ["u-k"], "dashboards": ["dashboard-workshop"]})

    async def test_input_with_an_error_shows_the_form_again(self) -> None:
        values = {"name": "Kitchen", "users": ["u-w1"], "dashboards": ["dashboard-workshop"]}
        result = await self.flow.async_step_user(values)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"users": "user_in_other_group"})

    async def test_change_of_a_group_shows_its_values_and_stores_the_new_ones(self) -> None:
        form = await self.flow.async_step_reconfigure(None)
        self.assertEqual((form["type"], form["step_id"]), ("form", "reconfigure"))
        defaults = {str(key): key.default() for key in form["data_schema"].schema}
        self.assertEqual(defaults["name"], "Workshop")
        self.assertEqual(defaults["users"], ["u-w1"])
        values = {"name": "Workshop panels", "users": ["u-w1"], "dashboards": ["dashboard-workshop"]}
        result = await self.flow.async_step_reconfigure(values)
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["title"], "Workshop panels")
        self.assertEqual(result["data"], {"users": ["u-w1"], "dashboards": ["dashboard-workshop"]})


if __name__ == "__main__":
    unittest.main()
