import unittest
from unittest.mock import patch

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.viewer as _viewer
from src.callbacks.viewer import register_fullscreen_sort_visibility_callback


def find_cb(app, output_id, output_prop):
    for _k, v in app.callback_map.items():
        out = v.get("output")
        outs = out if isinstance(out, list) else [out]
        for o in outs:
            if getattr(o, "component_property", None) == output_prop and getattr(o, "component_id", None) == output_id:
                return v["callback"].__wrapped__
    raise KeyError((output_id, output_prop))


class TestFullscreenSortVisibility(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="fullscreen-sort-container"),
                html.Div(id="photo-list-store"),
            ]
        )
        register_fullscreen_sort_visibility_callback(self.app)
        self.cb = find_cb(self.app, "fullscreen-sort-container", "style")

    def test_preserves_positioning_when_shown(self):
        base_style = {
            "position": "absolute",
            "top": "20px",
            "left": "20px",
            "zIndex": "1100",
            "background": "rgba(0,0,0,0.5)",
            "display": "none",
        }
        result = self.cb({"paths": ["/a.jpg", "/b.jpg"], "index": 0}, base_style)
        self.assertEqual(result["display"], "flex")
        # Positioning must be preserved, not clobbered.
        self.assertEqual(result["position"], "absolute")
        self.assertEqual(result["top"], "20px")
        self.assertEqual(result["left"], "20px")
        self.assertEqual(result["zIndex"], "1100")
        self.assertEqual(result["background"], "rgba(0,0,0,0.5)")

    def test_hides_for_single_photo(self):
        base_style = {"position": "absolute", "top": "20px", "display": "flex"}
        result = self.cb({"paths": ["/a.jpg"], "index": 0}, base_style)
        self.assertEqual(result["display"], "none")
        self.assertEqual(result["position"], "absolute")

    def test_handles_missing_style(self):
        result = self.cb({"paths": ["/a.jpg", "/b.jpg"], "index": 0}, None)
        self.assertEqual(result["display"], "flex")


if __name__ == "__main__":
    unittest.main()
