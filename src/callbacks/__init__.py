from dash import Input, Output

from src.config import AppConfig

from .chat import (
    register_chat_callback,
    register_chat_endpoint_test_callback,
    register_chat_history_init_callback,
    register_chat_history_navigation_callback,
    register_chat_scroll_callback,
    register_chat_stream_callback,
    register_chat_tag_clear_callback,
    register_chat_tag_click_callback,
    register_chat_tag_remove_callback,
    register_clear_chat_callback,
)
from .errors import register_all_errors_callbacks
from .health_settings import (
    register_concurrency_setting_callback,
    register_embedding_status_indicator_callback,
    register_health_callback,
    register_settings_modal_callback,
    register_store_vector_callback,
    register_vector_db_check_callback,
    register_vector_search_status_callback,
    register_vector_test_callback,
)
from .metadata_tester import register_metadata_tester_callbacks
from .prompt_tester import register_prompt_tester_callbacks
from .similarity import (
    register_display_similar_photos_callback,
    register_find_similar_callback,
    register_similarity_search_callback,
)
from .sql_explorer import register_sql_explorer_callback
from .viewer import (
    register_detail_modal_callback,
    register_fullscreen_close_callback,
    register_fullscreen_find_similar_callback,
    register_fullscreen_folder_change_callback,
    register_fullscreen_metadata_toggle_callback,
    register_fullscreen_nav_callback,
    register_fullscreen_open_callback,
    register_reveal_callbacks,
)

__all__ = [
    "register_all_errors_callbacks",
    "register_callbacks",
    "register_chat_callback",
    "register_chat_endpoint_test_callback",
    "register_chat_history_init_callback",
    "register_chat_history_navigation_callback",
    "register_chat_scroll_callback",
    "register_chat_stream_callback",
    "register_chat_tag_clear_callback",
    "register_chat_tag_click_callback",
    "register_chat_tag_remove_callback",
    "register_clear_chat_callback",
    "register_concurrency_setting_callback",
    "register_detail_modal_callback",
    "register_display_similar_photos_callback",
    "register_embedding_status_indicator_callback",
    "register_find_similar_callback",
    "register_fullscreen_close_callback",
    "register_fullscreen_find_similar_callback",
    "register_fullscreen_folder_change_callback",
    "register_fullscreen_metadata_toggle_callback",
    "register_fullscreen_nav_callback",
    "register_fullscreen_open_callback",
    "register_health_callback",
    "register_metadata_tester_callbacks",
    "register_prompt_tester_callbacks",
    "register_reveal_callbacks",
    "register_similarity_search_callback",
    "register_sql_explorer_callback",
    "register_store_vector_callback",
    "register_vector_db_check_callback",
    "register_vector_search_status_callback",
    "register_vector_test_callback",
]


def register_callbacks(app, create_extractor_fn, processing_config, app_config: AppConfig):
    """Register all Dash callbacks on the app."""
    # Note: We no longer need ExtractorProvider since we create extractors directly

    register_health_callback(app, create_extractor_fn, app_config)
    register_embedding_status_indicator_callback(app, app_config)
    register_vector_search_status_callback(app)
    register_vector_test_callback(app, app_config)
    register_store_vector_callback(app, app_config)
    register_vector_db_check_callback(app)
    register_prompt_tester_callbacks(app, create_extractor_fn, app_config)
    register_metadata_tester_callbacks(app)
    register_chat_callback(app, app_config)
    register_chat_stream_callback(app)
    register_clear_chat_callback(app)
    register_chat_endpoint_test_callback(app, app_config)
    register_chat_history_init_callback(app)
    register_chat_history_navigation_callback(app)
    register_chat_scroll_callback(app)
    register_chat_tag_click_callback(app)
    register_chat_tag_clear_callback(app)
    register_chat_tag_remove_callback(app)
    register_settings_modal_callback(app)
    register_concurrency_setting_callback(app, app_config)
    register_sql_explorer_callback(app)
    register_detail_modal_callback(app)
    register_fullscreen_open_callback(app)
    register_fullscreen_nav_callback(app)
    register_fullscreen_close_callback(app)
    register_fullscreen_metadata_toggle_callback(app)
    register_fullscreen_folder_change_callback(app)
    register_fullscreen_find_similar_callback(app)
    register_reveal_callbacks(app)

    # Similarity search callbacks
    register_find_similar_callback(app)
    register_similarity_search_callback(app)
    register_display_similar_photos_callback(app)
    register_all_errors_callbacks(app)

    app.clientside_callback(
        """
        function(is_open) {
            if (!window._photoKeyboardNav) {
                window._photoKeyboardNav = true;
                document.addEventListener('keydown', function(e) {
                    // Any open Bootstrap modal on the page?
                    var modal = document.querySelector('.modal.show');
                    if (!modal) return;
                    // Don't hijack when typing in inputs
                    var active = document.activeElement;
                    if (active) {
                        var tag = active.tagName;
                        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
                    }
                    // Full-screen modal takes priority for navigation keys.
                    // #fullscreen-modal is the .modal-dialog; the .show class
                    // toggles on its ancestor .modal, so check via closest().
                    var fsModal = document.getElementById('fullscreen-modal');
                    var isFullscreen = fsModal && fsModal.closest('.modal.show') !== null;
                    if (e.key === 'ArrowLeft') {
                        e.preventDefault();
                        if (isFullscreen) {
                            var btn = document.getElementById('btn-prev-fullscreen');
                        } else {
                            var btn = document.getElementById('btn-prev-photo');
                        }
                        if (btn) btn.click();
                    } else if (e.key === 'ArrowRight') {
                        e.preventDefault();
                        if (isFullscreen) {
                            var btn = document.getElementById('btn-next-fullscreen');
                        } else {
                            var btn = document.getElementById('btn-next-photo');
                        }
                        if (btn) btn.click();
                    } else if (e.key === 'Escape') {
                        e.preventDefault();
                        if (isFullscreen) {
                            var btn = document.getElementById('btn-close-fullscreen');
                        } else {
                            var btn = document.getElementById('btn-close-detail');
                        }
                        if (btn) btn.click();
                    } else if (e.key === 'i' || e.key === 'I') {
                        e.preventDefault();
                        if (isFullscreen) {
                            var btn = document.getElementById('btn-toggle-metadata-fullscreen');
                            if (btn) btn.click();
                        }
                    }
                });
            }
            return "";
        }
        """,
        Output("keyboard-dummy", "children"),
        Input("detail-modal", "is_open"),
    )
