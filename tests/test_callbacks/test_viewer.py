import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.viewer as _viewer
from src.callbacks.viewer import (
    _extract_paths_and_scores,
    register_detail_modal_callback,
    register_fullscreen_close_callback,
    register_fullscreen_folder_change_callback,
    register_fullscreen_metadata_toggle_callback,
    register_fullscreen_nav_callback,
    register_fullscreen_open_callback,
    register_fullscreen_sort_callback,
    register_slideshow_open_callback,
)
from tests.test_callbacks import find_callback, patch_callback_context


class TestDetailModalCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="detail-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="btn-prev-photo"),
                html.Div(id="btn-next-photo"),
                html.Div(id="btn-close-detail"),
                html.Div(id="input-folder"),
            ]
        )
        register_detail_modal_callback(self.app)

    def test_close_detail(self):
        cb = find_callback(self.app, "detail-modal", "is_open").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-close-detail.n_clicks", "value": 1}]):
            result = cb([], [], [], 1, [], {}, "")
        self.assertFalse(result[0])
        self.assertEqual(result[1], dash.no_update)
        self.assertEqual(result[2], dash.no_update)


class TestFullscreenOpenCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="btn-open-fullscreen"),
                html.Div(id="photo-list-store"),
                html.Div(id="detail-modal"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_open_callback(self.app)

    def test_no_click_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(None, {"paths": [], "index": None}, True, "", "relevance", "\u25bc")
        self.assertEqual(
            result,
            (dash.no_update, dash.no_update, dash.no_update, dash.no_update),
        )

    def test_no_folder_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(1, {"paths": ["/a.jpg"], "index": 0}, True, "", "relevance", "\u25bc")
        self.assertEqual(
            result,
            (dash.no_update, dash.no_update, dash.no_update, dash.no_update),
        )


class TestFullscreenNavCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="btn-prev-fullscreen"),
                html.Div(id="btn-next-fullscreen"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_nav_callback(self.app)

    def test_no_trigger_no_update(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, []):
            result = cb(None, None, {"paths": [], "index": 0}, "")
        self.assertEqual(result, (dash.no_update, dash.no_update))

    def test_next_wraps(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-next-fullscreen.n_clicks", "value": 1}]):
            result = cb(None, 1, {"paths": ["/a.jpg", "/b.jpg"], "index": 0}, "")
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1]["index"], 1)

    def test_prev_wraps(self):
        cb = find_callback(self.app, "fullscreen-modal-body", "children").__wrapped__
        with patch_callback_context(_viewer, [{"prop_id": "btn-prev-fullscreen.n_clicks", "value": 1}]):
            result = cb(1, None, {"paths": ["/a.jpg", "/b.jpg"], "index": 0}, "")
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1]["index"], 1)


class TestFullscreenCloseCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="detail-modal-body"),
                html.Div(id="btn-close-fullscreen"),
                html.Div(id="photo-list-store"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_close_callback(self.app)

    def test_close_returns_false(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb(1, {"paths": ["/a.jpg"], "index": 0}, "")
        self.assertFalse(result[0])
        self.assertTrue(result[1])
        self.assertIsNotNone(result[2])


class TestFullscreenMetadataToggleCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-metadata-overlay"),
                html.Div(id="btn-toggle-metadata-fullscreen"),
            ]
        )
        register_fullscreen_metadata_toggle_callback(self.app)

    def test_toggles_display(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(1, {"display": "block"})
        self.assertEqual(result["display"], "none")

    def test_toggles_back(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(1, {"display": "none"})
        self.assertEqual(result["display"], "block")

    def test_no_click_no_update(self):
        cb = find_callback(self.app, "fullscreen-metadata-overlay", "style").__wrapped__
        result = cb(None, {"display": "block"})
        self.assertEqual(result, dash.no_update)


class TestFullscreenFolderChangeCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_folder_change_callback(self.app)

    def test_closes_on_change(self):
        cb = find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__
        result = cb("/new/folder")
        self.assertFalse(result)


class TestExtractPathsAndScores(unittest.TestCase):
    def test_photos_entry_with_score_dicts(self):
        entry = {
            "type": "photos",
            "photo_paths": [{"path": "/a.jpg", "score": 0.9}, {"path": "/b.jpg", "score": 0.8}],
        }
        paths, scores = _extract_paths_and_scores(entry)
        self.assertEqual(paths, ["/a.jpg", "/b.jpg"])
        self.assertEqual(scores, {"/a.jpg": 0.9, "/b.jpg": 0.8})

    def test_photos_and_tags_entry_has_no_scores(self):
        entry = {
            "type": "photos_and_tags",
            "photos": [{"path": "/a.jpg", "description": "a cat"}, "/b.jpg"],
        }
        paths, scores = _extract_paths_and_scores(entry)
        self.assertEqual(paths, ["/a.jpg", "/b.jpg"])
        self.assertEqual(scores, {})

    def test_decodes_bytes_paths(self):
        entry = {"type": "photos", "photo_paths": [b"/a.jpg"]}
        paths, scores = _extract_paths_and_scores(entry)
        self.assertEqual(paths, ["/a.jpg"])

    def test_empty(self):
        self.assertEqual(_extract_paths_and_scores({}), ([], {}))

    def test_all_photo_paths_preferred_over_photos(self):
        """``all_photo_paths`` (the full /tag result set) is preferred over
        the 20-photo ``photos`` preview so the slideshow gets every match."""
        entry = {
            "type": "photos_and_tags",
            "photos": [{"path": f"/photos/{i}.jpg"} for i in range(20)],
            "all_photo_paths": [f"/photos/{i}.jpg" for i in range(25)],
            "total_photos": 25,
        }
        paths, scores = _extract_paths_and_scores(entry)
        self.assertEqual(len(paths), 25)
        self.assertEqual(paths[0], "/photos/0.jpg")
        self.assertEqual(paths[-1], "/photos/24.jpg")
        self.assertEqual(scores, {})

    def test_all_photo_paths_empty_falls_back_to_photos(self):
        """An empty ``all_photo_paths`` falls back to ``photos``."""
        entry = {
            "type": "photos_and_tags",
            "photos": [{"path": "/a.jpg"}],
            "all_photo_paths": [],
        }
        paths, _scores = _extract_paths_and_scores(entry)
        self.assertEqual(paths, ["/a.jpg"])


class TestSlideshowOpenCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal"),
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="chat-history-store"),
                html.Div(id="input-folder"),
                html.Div(id="fullscreen-sort-select"),
                html.Div(id={"type": "slideshow-sort", "index": 0}),
                html.Div(id={"type": "gallery-sort", "index": 0}),
            ]
        )
        register_slideshow_open_callback(self.app)

    def _cb(self):
        return find_callback(self.app, "fullscreen-modal", "is_open").__wrapped__

    def test_no_trigger_no_update(self):
        with patch_callback_context(_viewer, []):
            result = self._cb()(
                [], [], "/photos", ["relevance"],
                [{"type": "slideshow-sort", "index": 0}],
                [], [],
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
            )
        self.assertEqual(
            result,
            (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update),
        )

    def test_no_folder_no_update(self):
        triggered = [{"prop_id": '{"type":"btn-start-slideshow","index":0}.n_clicks', "value": 1}]
        with patch_callback_context(_viewer, triggered):
            result = self._cb()(
                [1], [{"type": "photos", "photo_paths": ["/a.jpg"]}], "", ["relevance"],
                [{"type": "slideshow-sort", "index": 0}],
                [], [],
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
            )
        self.assertEqual(
            result,
            (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update),
        )

    def test_opens_fullscreen_and_seeds_store(self):
        history = [
            {"type": "photos", "photo_paths": ["/photos/a.jpg", "/photos/b.jpg"]},
        ]
        triggered = [{"prop_id": '{"type":"btn-start-slideshow","index":0}.n_clicks', "value": 1}]
        with patch_callback_context(_viewer, triggered):
            result = self._cb()(
                [1], history, "/photos", ["relevance"],
                [{"type": "slideshow-sort", "index": 0}],
                [], [],
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
            )
        self.assertTrue(result[0])  # fullscreen-modal is_open
        self.assertIsNotNone(result[1])  # fullscreen-modal-body children
        self.assertEqual(
            result[2],
            {
                "paths": ["/photos/a.jpg", "/photos/b.jpg"],
                "original_paths": ["/photos/a.jpg", "/photos/b.jpg"],
                "index": 0,
            },
        )
        self.assertEqual(result[3], "relevance")  # fullscreen-sort-select synced
        # fullscreen-sort-order synced to relevance's default (desc = \u25bc)
        self.assertEqual(result[4], "\u25bc")

    def test_index_out_of_range_no_update(self):
        history = [{"type": "photos", "photo_paths": ["/photos/a.jpg"]}]
        triggered = [{"prop_id": '{"type":"btn-start-slideshow","index":5}.n_clicks', "value": 1}]
        with patch_callback_context(_viewer, triggered):
            result = self._cb()(
                [1], history, "/photos", ["relevance"],
                [{"type": "slideshow-sort", "index": 0}],
                [], [],
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
            )
        self.assertEqual(
            result,
            (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update),
        )

    def test_gallery_sort_fallback_when_no_slideshow_sort(self):
        """Below the slideshow threshold, the "Start slideshow" button lives
        in the gallery sort row, so there is no ``slideshow-sort`` dropdown.
        The callback must fall back to the ``gallery-sort`` dropdown to read
        the chosen sort key."""
        history = [
            {"type": "photos_and_tags", "photos": ["/photos/a.jpg", "/photos/b.jpg"]},
        ]
        triggered = [{"prop_id": '{"type":"btn-start-slideshow","index":0}.n_clicks', "value": 1}]
        with patch_callback_context(_viewer, triggered):
            result = self._cb()(
                [1], history, "/photos",
                [],  # no slideshow-sort values
                [],  # no slideshow-sort ids
                ["name"],  # gallery-sort value
                [{"type": "gallery-sort", "index": 0}],
                [{"type": "sort-order", "index": 0}],
                ["\u25b2"],  # ascending
            )
        self.assertTrue(result[0])  # fullscreen-modal is_open
        self.assertEqual(result[3], "name")  # fullscreen-sort-select synced to gallery sort
        self.assertEqual(result[4], "\u25b2")  # order preserved from gallery toggle


class TestFullscreenSortCallback(unittest.TestCase):
    """Regression tests for the fullscreen viewer sort/order toggle.

    The order toggle is a plain-id button (``fullscreen-sort-order``); its
    click must be detected via the unquoted prop_id (``fullscreen-sort-order.
    n_clicks``), not a quoted-substring match that never succeeds for plain
    ids. Previously the toggle never recognised its own click, so it always
    reset to the sort key's default direction instead of flipping.
    """

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-modal-body"),
                html.Div(id="photo-list-store"),
                html.Div(id="fullscreen-sort-order"),
                html.Div(id="fullscreen-sort-select"),
                html.Div(id="input-folder"),
            ]
        )
        register_fullscreen_sort_callback(self.app)

    def _cb(self):
        return find_callback(self.app, "fullscreen-sort-order", "children").__wrapped__

    def _store(self, paths, index=0):
        return {"paths": paths, "original_paths": paths, "index": index}

    def test_order_toggle_flips_desc_to_asc(self):
        triggered = [{"prop_id": "fullscreen-sort-order.n_clicks", "value": 1}]
        with patch_callback_context(_viewer, triggered):
            _content, store, label = self._cb()(
                "relevance", 1, self._store(["/a.jpg", "/b.jpg"]), "/photos", "\u25bc"
            )
        self.assertEqual(label, "\u25b2")
        self.assertIsInstance(store, dict)

    def test_order_toggle_flips_asc_to_desc(self):
        triggered = [{"prop_id": "fullscreen-sort-order.n_clicks", "value": 1}]
        with patch_callback_context(_viewer, triggered):
            _content, store, label = self._cb()(
                "relevance", 1, self._store(["/a.jpg", "/b.jpg"]), "/photos", "\u25b2"
            )
        self.assertEqual(label, "\u25bc")

    def test_sort_key_change_resets_to_default(self):
        # Changing the dropdown (not the toggle) resets to the key's default.
        triggered = [{"prop_id": "fullscreen-sort-select.value", "value": "relevance"}]
        with patch_callback_context(_viewer, triggered):
            _content, store, label = self._cb()(
                "relevance", 0, self._store(["/a.jpg", "/b.jpg"]), "/photos", "\u25b2"
            )
        # relevance defaults to descending.
        self.assertEqual(label, "\u25bc")


if __name__ == "__main__":
    unittest.main()
