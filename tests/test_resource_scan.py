"""Resources that the file scan did not see, and files that it could not read.

Each case comes from a review finding on the resource scan.
"""

from __future__ import annotations

import gzip
from pathlib import Path
import tempfile
import unittest

from test_resolver import _Dashboard, _Hass, _resolver, _write

FileCache = _resolver.FileCache
names_in_javascript = _resolver.names_in_javascript

# A bundle that registers its elements only through the minified decorator of Lit. The
# scan sees the element that the file name gives, and it does not see the second element.
LAYOUT_CARD_JS = b"""
const t=t=>(e,o)=>{void 0!==o?o.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)};
let Grid=class extends s{};Grid=e([t("grid-layout")],Grid);
let Card=class extends s{};Card=e([t("layout-card")],Card);
"""
# A file that names another file's card, and registers its own element.
MENTION_JS = b"""
const OTHER = ["grid-layout", "missing-card"];
customElements.define("helper-row", class extends HTMLElement {});
"""
# A file with no element, such as an icon set.
ICONS_JS = b"window.customIconsets = window.customIconsets || {};\n"


def _dashboard(*cards) -> _Dashboard:
    return _Dashboard({"views": [{"cards": list(cards)}]})


class ResourceScanTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        _write(self.root, "layout-card/layout-card.js", LAYOUT_CARD_JS)
        _write(self.root, "helper-row/helper-row.js", MENTION_JS)
        _write(self.root, "icons/icons.js", ICONS_JS)
        self.resources = [
            {"url": "/hacsfiles/layout-card/layout-card.js", "type": "module"},
            {"url": "/hacsfiles/helper-row/helper-row.js", "type": "module"},
            {"url": "/hacsfiles/icons/icons.js", "type": "module"},
            {"url": "/webrtc/webrtc-camera.js?v=3.6.1", "type": "module"},
        ]

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def _resolve(self, *cards, **options) -> dict:
        hass = _Hass(self.root, {"d": _dashboard(*cards)}, self.resources)
        base = {"dashboards": ["d"], "include_unscannable": False, **options}
        return (await _resolver.async_resolve(hass, base, FileCache())).as_dict()

    async def test_element_of_a_minified_decorator_keeps_its_file(self) -> None:
        summary = await self._resolve({"type": "custom:grid-layout"})
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])
        self.assertEqual(summary["guessed_types"], ["grid-layout"])
        self.assertEqual(summary["unresolved_types"], [])
        # helper-row.js names the type too. Each of its registrations has a quoted name,
        # so it registers no other element, and it is not sent.
        self.assertIn("/hacsfiles/helper-row/helper-row.js", summary["excluded"])

    async def test_guess_takes_each_file_that_can_hide_a_registration(self) -> None:
        # A second bundle with a registration that the scan cannot read names the type.
        _write(
            self.root,
            "other-kit/other-kit.js",
            b'const t=t=>e=>customElements.define(t,e);const names=["grid-layout"];',
        )
        self.resources.append({"url": "/hacsfiles/other-kit/other-kit.js", "type": "module"})
        summary = await self._resolve({"type": "custom:grid-layout"})
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])
        self.assertIn("/hacsfiles/other-kit/other-kit.js", summary["included"])

    async def test_key_that_ends_in_type_is_no_registration(self) -> None:
        # A card's option, such as layout_type, names a type and registers nothing.
        _write(
            self.root,
            "editor-kit/editor-kit.js",
            b'customElements.define("editor-kit", class {});const stub={layout_type:"grid-layout"};',
        )
        self.resources.append({"url": "/hacsfiles/editor-kit/editor-kit.js", "type": "module"})
        summary = await self._resolve({"type": "custom:grid-layout"})
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])
        self.assertIn("/hacsfiles/editor-kit/editor-kit.js", summary["excluded"])
        self.assertEqual(summary["guessed_types"], ["grid-layout"])

    async def test_name_of_two_pieces_in_a_helper_call_is_found_by_the_guess(self) -> None:
        _write(
            self.root,
            "pieces/pieces.js",
            b'const r=(t,e)=>customElements.define(t,e);r("my"+"-card",class {});',
        )
        self.resources.append({"url": "/hacsfiles/pieces/pieces.js", "type": "module"})
        summary = await self._resolve({"type": "custom:my-card"})
        self.assertIn("/hacsfiles/pieces/pieces.js", summary["included"])
        self.assertEqual(summary["guessed_types"], ["my-card"])

    async def test_type_with_a_provider_takes_no_file_that_only_names_it(self) -> None:
        summary = await self._resolve({"type": "custom:layout-card"})
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])
        self.assertIn("/hacsfiles/helper-row/helper-row.js", summary["excluded"])
        self.assertEqual(summary["guessed_types"], [])

    async def test_type_of_an_excluded_resource_takes_no_guess(self) -> None:
        summary = await self._resolve(
            {"type": "custom:grid-layout"},
            always_exclude=["/hacsfiles/layout-card/layout-card.js"],
        )
        # The excluded file is the only one that can hide the type's registration,
        # so no other file is sent for it, and the type has no provider.
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["excluded"])
        self.assertIn("/hacsfiles/helper-row/helper-row.js", summary["excluded"])
        self.assertEqual(summary["guessed_types"], [])
        self.assertEqual(summary["unresolved_types"], ["grid-layout"])
        summary = await self._resolve(
            {"type": "custom:layout-card"},
            always_exclude=["/hacsfiles/layout-card/layout-card.js"],
        )
        self.assertEqual(summary["guessed_types"], [])
        self.assertEqual(summary["unresolved_types"], ["layout-card"])

    async def test_file_with_no_element_is_listed(self) -> None:
        # A card whose file registers through a decorator, and that no dashboard uses.
        _write(self.root, "big-camera-card/big-camera-card.js", b"let A=e([t(n)],A);")
        self.resources.append(
            {"url": "/hacsfiles/big-camera-card/big-camera-card.js", "type": "module"}
        )
        _write(self.root, "custom-brand-icons/custom-brand-icons.js", ICONS_JS)
        self.resources.append(
            {"url": "/hacsfiles/custom-brand-icons/custom-brand-icons.js", "type": "module"}
        )
        summary = await self._resolve({"type": "tile", "entity": "light.hall"})
        # Each readable file in which the scan sees no element is listed, whatever its
        # name is: an icon set, and a card that registers through a decorator.
        self.assertEqual(
            sorted(summary["excluded_without_element"]),
            [
                "/hacsfiles/big-camera-card/big-camera-card.js",
                "/hacsfiles/custom-brand-icons/custom-brand-icons.js",
                "/hacsfiles/icons/icons.js",
            ],
        )
        for url in summary["excluded_without_element"]:
            self.assertIn(url, summary["excluded"])

    async def test_custom_type_inside_a_template(self) -> None:
        card = {
            "type": "custom:button-card",
            "custom_fields": {"chips": "[[[ return {type: 'custom:layout-card'} ]]]"},
        }
        summary = await self._resolve(card)
        self.assertIn("layout-card", summary["needed_types"])
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])

    async def test_custom_type_that_a_template_gives_as_a_quoted_text(self) -> None:
        # The YAML key is "type", so the string itself holds no word "type".
        for text in (
            "[[[ return 'custom:layout-card' ]]]",
            "${ vars[0] ? 'custom:layout-card' : 'entities' }",
            '{{ "custom:layout-card" if is_state("sun.sun", "above_horizon") }}',
            "type: custom:layout-card\nentity: light.x",
        ):
            summary = await self._resolve({"type": "custom:config-template-card", "card": text})
            self.assertIn("layout-card", summary["needed_types"], text)

    async def test_three_pieces_give_the_guess_no_name(self) -> None:
        # The last two of three pieces are no name that the file holds.
        _write(
            self.root,
            "three/three.js",
            b'const t=t=>e=>customElements.define(t,e);const n="my-"+"fancy-"+"thing";',
        )
        self.resources.append({"url": "/hacsfiles/three/three.js", "type": "module"})
        summary = await self._resolve({"type": "custom:fancy-thing"})
        self.assertIn("/hacsfiles/three/three.js", summary["excluded"])
        self.assertEqual(summary["guessed_types"], [])
        self.assertEqual(summary["unresolved_types"], ["fancy-thing"])

    async def test_dashboard_that_cannot_be_loaded_is_left_out_of_the_resources(self) -> None:
        # The browser shows no card of such a dashboard, so the list needs none of its
        # resources. The log names the dashboard one time for each error text.
        broken = _Dashboard(None, fail=True)
        dashboards = {"d": _dashboard({"type": "custom:layout-card"}), "yaml": broken}
        hass = _Hass(self.root, dashboards, self.resources)
        options = {"dashboards": ["d", "yaml"], "include_unscannable": False}
        with self.assertLogs(_resolver._LOGGER, level="WARNING") as logs:
            summary = (await _resolver.async_resolve(hass, options, FileCache())).as_dict()
            await _resolver.async_resolve(hass, options, FileCache())
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])
        self.assertEqual(len(logs.records), 1)
        self.assertIn("yaml", logs.records[0].getMessage())
        # The file is correct for a time. The same error then comes back, and it is new.
        dashboards["yaml"] = _dashboard({"type": "tile"})
        await _resolver.async_resolve(hass, options, FileCache())
        dashboards["yaml"] = broken
        with self.assertLogs(_resolver._LOGGER, level="WARNING") as logs:
            await _resolver.async_resolve(hass, options, FileCache())
        self.assertEqual(len(logs.records), 1)

    async def test_custom_type_in_plain_text_is_no_card(self) -> None:
        card = {"type": "markdown", "content": "Do not use custom:layout-card here."}
        summary = await self._resolve(card)
        self.assertEqual(summary["needed_types"], [])
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["excluded"])

    async def test_camera_with_a_webrtc_card_key_keeps_the_webrtc_script(self) -> None:
        # The Advanced Camera Card's live provider "auto" takes webrtc-card for it.
        card = {
            "type": "custom:advanced-camera-card",
            "cameras": [{"webrtc_card": {"entity": "camera.door"}}],
        }
        summary = await self._resolve(card)
        self.assertIn("/webrtc/webrtc-camera.js?v=3.6.1", summary["included"])

    async def test_always_include_compares_the_host(self) -> None:
        self.resources = [
            {"url": "https://cdn-one.example/dist/a-card.js", "type": "module"},
            {"url": "https://cdn-two.example/dist/a-card.js", "type": "module"},
        ]
        summary = await self._resolve(
            {"type": "tile"}, always_include=["https://cdn-one.example/dist/a-card.js?v=2"]
        )
        self.assertEqual(summary["included"], ["https://cdn-one.example/dist/a-card.js"])
        self.assertEqual(summary["excluded"], ["https://cdn-two.example/dist/a-card.js"])

    async def test_no_dashboard_of_the_group_exists(self) -> None:
        hass = _Hass(self.root, {}, self.resources)
        with self.assertRaises(_resolver.CannotNarrow):
            await _resolver.async_resolve(hass, {"dashboards": ["deleted"]}, FileCache())


class FileReadTest(unittest.TestCase):
    """A file that the scan cannot read counts as unreadable, and raises nothing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_gz_copy_is_read(self) -> None:
        path = self.root / "a-card.js"
        with gzip.open(str(path) + ".gz", "wb") as fh:
            fh.write(b'customElements.define("a-card", class extends HTMLElement {});')
        self.assertEqual(FileCache().names(str(path)), frozenset({"a-card"}))

    def test_cut_gz_copy_is_unreadable(self) -> None:
        path = self.root / "a-card.js"
        with gzip.open(str(path) + ".gz", "wb") as fh:
            fh.write(b'customElements.define("a-card", class extends HTMLElement {});' * 50)
        data = Path(str(path) + ".gz").read_bytes()
        Path(str(path) + ".gz").write_bytes(data[: len(data) // 2])
        self.assertIsNone(FileCache().names(str(path)))

    def test_path_with_a_null_character_is_unreadable(self) -> None:
        self.assertIsNone(FileCache().names(str(self.root / "a\x00card.js")))

    def test_changed_file_is_read_again(self) -> None:
        path = self.root / "a-card.js"
        cache = FileCache()
        path.write_bytes(b'customElements.define("a-card", class {});')
        self.assertEqual(cache.names(str(path)), frozenset({"a-card"}))
        path.write_bytes(b'customElements.define("b-card", class {});  // longer')
        self.assertEqual(cache.names(str(path)), frozenset({"b-card"}))


class UrlToPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hass = _Hass("/config", {}, [])

    def test_url_of_another_host_is_no_local_file(self) -> None:
        self.assertIsNone(_resolver.url_to_path(self.hass, "https://cdn.example/local/card.js"))

    def test_path_that_leaves_the_folder_is_refused(self) -> None:
        for url in ("/local/../secrets.yaml", "/local/%2e%2e/secrets.yaml", "/other/card.js"):
            self.assertIsNone(_resolver.url_to_path(self.hass, url))

    def test_local_file_maps_into_the_www_folder(self) -> None:
        path = _resolver.url_to_path(self.hass, "/local/cards/a-card.js?v=1")
        self.assertTrue(path.replace("\\", "/").endswith("www/cards/a-card.js"))


class NamesTest(unittest.TestCase):
    def test_name_that_a_file_binds_two_times(self) -> None:
        data = b"""
        var p="mushroom";customElements.define(`${p}-light-card`,A);
        function other(){var p="x";return p}
        """
        self.assertIn("mushroom-light-card", names_in_javascript(data, "cards"))

    def test_two_pieces_outside_a_registration_are_no_element(self) -> None:
        data = b"""el.className = "mini" + "-graph-card"; log("button" + "-card");"""
        self.assertEqual(names_in_javascript(data, "helpers"), frozenset())

    def test_three_pieces_give_no_wrong_name(self) -> None:
        data = b"""customElements.define("my"+"-big"+"-card", A);"""
        self.assertEqual(names_in_javascript(data, "bundle"), frozenset())

    def test_two_pieces_in_a_registration_or_an_assignment_are_an_element(self) -> None:
        data = b"""
        customElements.define("my" + "-card", A);
        var legacy = "my" + "-legacy-card";
        """
        self.assertEqual(
            names_in_javascript(data, "bundle"), frozenset({"my-card", "my-legacy-card"})
        )


if __name__ == "__main__":
    unittest.main()
