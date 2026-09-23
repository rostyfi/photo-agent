import unittest
from unittest.mock import patch

from src.callbacks.chat import _history_to_messages


def _walk_components(comp):
    """Yield every Dash component reachable from ``comp`` (depth-first).

    Dash components raise ``AttributeError`` for unset ``id``, so we cannot
    gate on ``hasattr(comp, "id")``; instead we yield any non-primitive value
    and recurse into its ``children``.
    """
    if isinstance(comp, (str, bytes, int, float, type(None))):
        return
    if isinstance(comp, list):
        for c in comp:
            yield from _walk_components(c)
        return
    yield comp
    children = getattr(comp, "children", None)
    if children is not None:
        yield from _walk_components(children)


def _has_component_with_id(messages, id_type, index=None):
    for comp in _walk_components(messages):
        cid = getattr(comp, "id", None)
        if isinstance(cid, dict) and cid.get("type") == id_type and (index is None or cid.get("index") == index):
            return True
    return False


def _has_gallery_grid(messages):
    return any(getattr(comp, "className", None) == "gallery-grid" for comp in _walk_components(messages))


class TestHistoryToMessages(unittest.TestCase):
    """Regression tests for chat history rendering.

    Covers the ``photos`` entry-type branch that previously referenced
    undefined ``count`` / ``photo_paths`` names and raised ``NameError``
    (HTTP 500 on ``chat-response.children``).
    """

    def _assert_renders(self, entry, folder="/photos"):
        messages = _history_to_messages([entry], folder)
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 1)
        return messages[0]

    def test_photos_entry_with_photo_paths_key(self):
        """JS streaming handler stores photos under ``photo_paths``."""
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photo_paths": ["/photos/a.jpg", "/photos/b.jpg"],
            "count": 2,
        }
        self._assert_renders(entry)

    def test_photos_entry_with_photos_key(self):
        """Backend /find tool stores photos under ``photos`` with score dicts."""
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photos": [{"path": "/photos/a.jpg", "score": 0.9}],
        }
        self._assert_renders(entry)

    def test_photos_entry_missing_count_derives_from_length(self):
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photos": ["/photos/a.jpg"],
        }
        rendered = self._assert_renders(entry)
        self.assertIn("1 matching photos", str(rendered))

    def test_photos_and_tags_entry_renders(self):
        entry = {
            "sender": "assistant",
            "type": "photos_and_tags",
            "photos": [{"path": "/photos/a.jpg", "description": "a cat"}],
            "related_tags": [{"name": "nature", "count": 3}],
            "text": "header",
            "tag": "nature",
            "total_photos": 1,
            "selected_tags": ["nature"],
        }
        messages = _history_to_messages([entry], "/photos")
        # photos container + selected-tags row + related tags
        self.assertEqual(len(messages), 3)

    def test_photos_and_tags_selected_chips_are_removable(self):
        """Each selected tag renders as a remove chip encoding the chain."""
        from src.callbacks.chat import _history_to_messages

        entry = {
            "sender": "assistant",
            "type": "photos_and_tags",
            "photos": [],
            "related_tags": [],
            "text": "header",
            "tag": "nature, sunset",
            "total_photos": 0,
            "selected_tags": ["nature", "sunset"],
        }
        messages = _history_to_messages([entry], "/photos")
        # Find remove chips across all rendered messages.
        remove_ids = []

        def walk(comp):
            if isinstance(comp, list):
                for c in comp:
                    walk(c)
                return
            if hasattr(comp, "id") and isinstance(comp.id, dict) and comp.id.get("type") == "chat-tag-remove-btn":
                remove_ids.append(comp.id)
            children = getattr(comp, "children", None)
            if children is not None:
                walk(children)

        for m in messages:
            walk(m)

        self.assertEqual(len(remove_ids), 2)
        chains = {rid["chain"] for rid in remove_ids}
        self.assertEqual(chains, {"nature,sunset"})
        removes = sorted(rid["remove"] for rid in remove_ids)
        self.assertEqual(removes, ["nature", "sunset"])

    def test_tags_entry_renders_buttons(self):
        entry = {
            "sender": "assistant",
            "type": "tags",
            "tags": [{"name": "sunset", "count": 5}],
            "text": "All tags",
            "topic": None,
        }
        self._assert_renders(entry)

    def test_tags_entry_empty_shows_text(self):
        """When no tags match, the explanatory text is shown instead of buttons."""
        entry = {
            "sender": "assistant",
            "type": "tags",
            "tags": [],
            "text": "No tags found related to 'car'. Try a different keyword.",
            "topic": "car",
        }
        messages = _history_to_messages([entry], "/photos")
        self.assertEqual(len(messages), 1)
        # The text message should be present in the rendered children.
        texts = [c.children for c in _walk_components(messages[0]) if isinstance(getattr(c, "children", None), str)]
        self.assertTrue(any("No tags found related to 'car'" in t for t in texts), texts)

    def test_empty_history(self):
        self.assertEqual(_history_to_messages([], "/photos"), [])
        self.assertEqual(_history_to_messages(None, "/photos"), [])

    def test_photos_over_threshold_renders_slideshow_button(self):
        """When photos exceed the threshold, a Start slideshow button replaces the gallery."""
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photo_paths": [f"/photos/{i}.jpg" for i in range(5)],
            "count": 5,
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=2):
            messages = _history_to_messages([entry], "/photos")
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertFalse(_has_gallery_grid(messages))

    def test_photos_at_threshold_renders_gallery(self):
        """At exactly the threshold, the gallery is still shown (strictly greater-than)."""
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photo_paths": [f"/photos/{i}.jpg" for i in range(3)],
            "count": 3,
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=3):
            messages = _history_to_messages([entry], "/photos")
        # The gallery always includes a "Start slideshow" button so the user
        # can open the fullscreen viewer even for small result sets.
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertTrue(_has_gallery_grid(messages))

    def test_photos_threshold_zero_always_renders_gallery(self):
        """A threshold of 0 disables the slideshow shortcut."""
        entry = {
            "sender": "assistant",
            "type": "photos",
            "photo_paths": [f"/photos/{i}.jpg" for i in range(100)],
            "count": 100,
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=0):
            messages = _history_to_messages([entry], "/photos")
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertTrue(_has_gallery_grid(messages))

    def test_photos_and_tags_over_threshold_renders_slideshow_button(self):
        entry = {
            "sender": "assistant",
            "type": "photos_and_tags",
            "photos": [{"path": f"/photos/{i}.jpg"} for i in range(5)],
            "related_tags": [{"name": "nature", "count": 3}],
            "text": "header",
            "tag": "nature",
            "total_photos": 5,
            "selected_tags": ["nature"],
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=2):
            messages = _history_to_messages([entry], "/photos")
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertFalse(_has_gallery_grid(messages))

    def test_photos_and_tags_slideshow_label_uses_total_photos(self):
        """The "Start slideshow" button label shows the full match count
        (``total_photos``), not the 20-photo preview cap."""
        entry = {
            "sender": "assistant",
            "type": "photos_and_tags",
            "photos": [{"path": f"/photos/{i}.jpg"} for i in range(20)],
            "all_photo_paths": [f"/photos/{i}.jpg" for i in range(100)],
            "related_tags": [],
            "text": "header",
            "tag": "nature",
            "total_photos": 100,
            "selected_tags": ["nature"],
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=50):
            messages = _history_to_messages([entry], "/photos")
        # Above threshold (100 > 50): gallery replaced by slideshow button.
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertFalse(_has_gallery_grid(messages))
        # The button label must report all 100 photos, not 20.
        self.assertIn("100 photos", str(messages))

    def test_photos_and_tags_below_threshold_slideshow_label_uses_total(self):
        """Below the threshold the gallery is shown and its "Start slideshow"
        button still labels the full match count."""
        entry = {
            "sender": "assistant",
            "type": "photos_and_tags",
            "photos": [{"path": f"/photos/{i}.jpg"} for i in range(20)],
            "all_photo_paths": [f"/photos/{i}.jpg" for i in range(25)],
            "related_tags": [],
            "text": "header",
            "tag": "nature",
            "total_photos": 25,
            "selected_tags": ["nature"],
        }
        with patch("src.callbacks.chat._slideshow_threshold_for", return_value=50):
            messages = _history_to_messages([entry], "/photos")
        self.assertTrue(_has_component_with_id(messages, "btn-start-slideshow", index=0))
        self.assertTrue(_has_gallery_grid(messages))
        self.assertIn("25 photos", str(messages))


if __name__ == "__main__":
    unittest.main()
