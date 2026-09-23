import unittest

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.chat as _chat
from src.callbacks.chat import register_gallery_sort_callback
from tests.test_callbacks import find_callback, patch_callback_context


def _make_app():
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = html.Div(
        [
            html.Div(id={"type": "gallery-grid", "index": 0}),
            html.Div(id="photo-list-store"),
            html.Div(id={"type": "sort-order", "index": 0}),
            html.Div(id={"type": "gallery-sort", "index": 0}),
            html.Div(id="chat-history-store"),
            html.Div(id="input-folder"),
        ]
    )
    register_gallery_sort_callback(app)
    return app


class TestGallerySortCallback(unittest.TestCase):
    """Regression tests for the preview-gallery and slideshow sort-row order toggle.

    The ``sort-order`` toggle button is shared by gallery sort rows and
    slideshow sort rows (both keyed by chat history index). Clicking it must
    flip the asc/desc arrow label and reorder the gallery when one exists.
    """

    def _cb(self):
        return find_callback(self.app, "photo-list-store", "data").__wrapped__

    def setUp(self):
        self.app = _make_app()

    def _history(self):
        return [
            {
                "type": "photos",
                "photo_paths": [
                    {"path": "/photos/a.jpg", "score": 0.1},
                    {"path": "/photos/b.jpg", "score": 0.9},
                    {"path": "/photos/c.jpg", "score": 0.5},
                ],
            }
        ]

    def test_gallery_order_toggle_flips_and_resorts(self):
        triggered = [{"prop_id": '{"type":"sort-order","index":0}.n_clicks', "value": 1}]
        with patch_callback_context(_chat, triggered):
            grid_outputs, store, label_outputs = self._cb()(
                ["relevance"],
                [1],
                [{"type": "gallery-sort", "index": 0}],
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
                self._history(),
                "/photos",
            )
        self.assertEqual(label_outputs, ["\u25b2"])
        self.assertEqual(
            store["paths"],
            ["/photos/a.jpg", "/photos/c.jpg", "/photos/b.jpg"],
        )

    def test_gallery_sort_key_change_resets_order(self):
        triggered = [{"prop_id": '{"type":"gallery-sort","index":0}.value', "value": "relevance"}]
        with patch_callback_context(_chat, triggered):
            _grid, store, label_outputs = self._cb()(
                ["relevance"],
                [0],
                [{"type": "gallery-sort", "index": 0}],
                [{"type": "sort-order", "index": 0}],
                ["\u25b2"],  # currently asc; key change should reset to desc
                self._history(),
                "/photos",
            )
        # relevance defaults to descending.
        self.assertEqual(label_outputs, ["\u25bc"])

    def test_slideshow_sortrow_toggle_flips_label_only(self):
        """When no gallery grid exists (slideshow-only chat), the sort-row
        order toggle must still flip its label, and must NOT clobber
        photo-list-store (so an open fullscreen viewer is untouched)."""
        triggered = [{"prop_id": '{"type":"sort-order","index":0}.n_clicks', "value": 1}]
        with patch_callback_context(_chat, triggered):
            grid_outputs, store, label_outputs = self._cb()(
                [],  # no gallery-sort dropdowns
                [1],
                [],  # no gallery-sort ids
                [{"type": "sort-order", "index": 0}],
                ["\u25bc"],
                self._history(),
                "/photos",
            )
        self.assertEqual(label_outputs, ["\u25b2"])
        self.assertIs(store, dash.no_update)
        self.assertEqual(grid_outputs, [])


if __name__ == "__main__":
    unittest.main()
