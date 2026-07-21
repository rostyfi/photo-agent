import unittest
from src.layout import create_layout
from src.config import AppConfig
from dash import html, dcc
import dash_bootstrap_components as dbc

class TestLayout(unittest.TestCase):
    def test_create_layout_structure(self):
        config = AppConfig()

        layout = create_layout(config)
        
        # Check if it's a dbc.Container
        self.assertIsInstance(layout, dbc.Container)
        
        # Check for critical IDs to be present in the layout children
        # We flatten the nested layout to search for IDs
        def find_ids(element, found_ids=None):
            if found_ids is None:
                found_ids = set()
            
            if hasattr(element, 'id') and element.id:
                found_ids.add(element.id)
            
            if hasattr(element, 'children'):
                children = element.children
                if isinstance(children, list):
                    for child in children:
                        find_ids(child, found_ids)
                elif children is not None:
                    find_ids(children, found_ids)
            
            return found_ids

        all_ids = find_ids(layout)
        
        expected_ids = [
            "input-host",
            "input-port",
            "input-model",
            "input-backend",
            "input-timeout",
            "btn-health",
            "input-folder",
            "chk-recursive",
            "btn-rescan",
            "folder-file-list",
            "batch-progress-overall",
            "batch-progress-current",
            "batch-progress-label",
            "batch-progress-wrapper",
            "batch-history",
            "batch-history-wrapper",
            "btn-toggle-history",
            "history-collapse",
            "health-status",
            "processing-status",
            "queue-status",
            "poll-interval",
            "chk-dry-run",
            "sql-input",
            "btn-run-sql",
            "sql-results",
            "btn-load-tag-cloud",
            "tag-cloud-container",
            "tag-cloud-results",
            "detail-modal",
            "detail-modal-body",
            "btn-close-detail",
            "btn-prev-photo",
            "btn-next-photo",
            "photo-list-store",
            "keyboard-dummy",
            # Embedding and vector search status in settings
            "embedding-status-indicator",
            "vector-search-status-indicator",
            # Errors in settings
            "errors-count",
            "errors-list",
            "btn-refresh-errors",
            "btn-clear-errors",
        ]
        
        for eid in expected_ids:
            with self.subTest(expected_id=eid):
                self.assertIn(eid, all_ids, f"Layout is missing expected element with id: {eid}")

if __name__ == "__main__":
    unittest.main()
