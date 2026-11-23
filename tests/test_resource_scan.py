"""Resources that the scan of a file did not see, and files that it could not read.

Each case comes from a finding of a review of the resource scan.
"""

from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from test_resolver import _Dashboard, _Hass, _resolver, _write

FileCache = _resolver.FileCache
names_in_javascript = _resolver.names_in_javascript

# A bundle that registers its elements only through the minified decorator of Lit. The
# scan sees the element of the file name, and it does not see the second element.
LAYOUT_CARD_JS = b"""
const t=t=>(e,o)=>{void 0!==o?o.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)};
let Grid=class extends s{};Grid=e([t("grid-layout")],Grid);
let Card=class extends s{};Card=e([t("layout-card")],Card);
"""
# A file that names a card of another file, and registers its own element.
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
        # Each file that names the type in quotes is sent, because the scan cannot tell
        # which one registers it.
        self.assertIn("/hacsfiles/helper-row/helper-row.js", summary["included"])

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
        # The stem of the excluded file does not account for the type, so the guess of
        # the other file still applies. A type of the excluded file itself gets none.
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["excluded"])
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
        summary = await self._resolve({"type": "tile", "entity": "light.hall"})
        # The icon set is listed. The file with the name of a card is not.
        self.assertEqual(summary["excluded_without_element"], ["/hacsfiles/icons/icons.js"])
        self.assertIn("/hacsfiles/icons/icons.js", summary["excluded"])
        self.assertIn("/hacsfiles/big-camera-card/big-camera-card.js", summary["excluded"])

    async def test_custom_type_inside_a_template(self) -> None:
        card = {
            "type": "custom:button-card",
            "custom_fields": {"chips": "[[[ return {type: 'custom:layout-card'} ]]]"},
        }
        summary = await self._resolve(card)
        self.assertIn("layout-card", summary["needed_types"])
        self.assertIn("/hacsfiles/layout-card/layout-card.js", summary["included"])

    async def test_camera_with_a_webrtc_card_key_keeps_the_webrtc_script(self) -> None:
        # The live provider "auto" of the Advanced Camera Card takes webrtc-card for it.
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
