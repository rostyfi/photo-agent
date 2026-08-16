import unittest

from src.callbacks.chat import _history_to_messages


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

    def test_empty_history(self):
        self.assertEqual(_history_to_messages([], "/photos"), [])
        self.assertEqual(_history_to_messages(None, "/photos"), [])


if __name__ == "__main__":
    unittest.main()
