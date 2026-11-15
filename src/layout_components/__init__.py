"""Layout component builders for the Local Photo Agent web UI.

This package contains focused builders:
- ``settings_modal`` — settings modal and all its tabs
- ``modals``         — SQL explorer, detail modal, fullscreen modal
"""

from .modals import build_detail_modal, build_fullscreen_modal, build_sql_explorer_modal
from .settings_modal import build_settings_modal

__all__ = [
    "build_detail_modal",
    "build_fullscreen_modal",
    "build_settings_modal",
    "build_sql_explorer_modal",
]
