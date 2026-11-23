"""The form of a group of lite users: its options, its defaults and its checks."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from support import ConfigSubentry, _default, _module, install_homeassistant_stubs, load

install_homeassistant_stubs()


class _Flow:
    """Stand-in for the flow base classes of Home Assistant."""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__()


class _Selector:
    """Stand-in for a selector: it keeps its configuration and accepts each value."""

    def __init__(self, config=None) -> None:
        self.config = config or {}

    def __call__(self, value):
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
    """Return each field of the form as (default, values of its options)."""
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
        # dashboard and a resource URL of an older version must stay among them.
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


if __name__ == "__main__":
    unittest.main()
