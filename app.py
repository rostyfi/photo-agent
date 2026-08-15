"""
Photo Feature Extractor - Dash Web Application
===============================================
Run with: python app.py
Then open http://127.0.0.1:8050 in your browser.
"""

import io
import logging
import mimetypes
import signal
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import diskcache
from dash import DiskcacheManager
from flask import abort, jsonify, make_response, request

from src.config import AppConfig
from src.layout import create_layout
from src.callbacks import register_callbacks
from plugins.llm import create_extractor, OllamaChatClient
from plugins.formats.image import read_image_bytes
from src.services import ChatService
from src.api import api_chat_handler, api_chat_stream_handler, register_vectors_blueprint, register_debug_blueprint

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _resolve_preview_paths(path_str: str, folder_str: str):
    """Resolve and validate the ``path``/``folder`` preview query params.

    Returns ``(image_path, folder_path)`` when ``path_str`` resolves to a real
    file located inside ``folder_str`` (which must be an existing directory).
    On any other condition - missing folder, non-existent path, a directory
    passed as the image, or a path outside the folder (directory traversal) -
    returns ``(None, None)``.

    All failure cases are logged at debug level (traversal attempts at
    warning level) and the caller returns 404 for every failure, so the
    endpoint never leaks filesystem layout through distinct status codes.
    """
    try:
        folder_path = Path(folder_str).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError):
        logger.debug("Preview rejected: folder does not exist: %s", folder_str)
        return None, None
    except OSError as e:
        logger.debug("Preview rejected: folder resolution failed for %s: %s", folder_str, e)
        return None, None
    if not folder_path.is_dir():
        logger.debug("Preview rejected: not a directory: %s", folder_path)
        return None, None

    try:
        image_path = Path(path_str).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError):
        logger.debug("Preview rejected: image does not exist: %s", path_str)
        return None, None
    except OSError as e:
        logger.debug("Preview rejected: image resolution failed for %s: %s", path_str, e)
        return None, None
    if not image_path.is_file():
        logger.debug("Preview rejected: not a file: %s", image_path)
        return None, None

    try:
        image_path.relative_to(folder_path)
    except ValueError:
        logger.warning("Preview rejected: path outside folder (traversal attempt): %s", image_path)
        return None, None
    return image_path, folder_path


def _is_running_in_container() -> bool:
    """Return True when the process is inside a container (Docker, Podman, etc.)."""
    if Path("/.dockerenv").exists():
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            return any(k in f.read() for k in ("docker", "containerd", "lxc", "kubepods"))
    except (FileNotFoundError, OSError):
        return False


# Mount points that are never useful photo bind mounts — skip them.
_SYSTEM_MOUNT_PREFIXES = (
    "/proc", "/sys", "/dev", "/run", "/etc", "/var", "/tmp",
    "/usr", "/lib", "/boot", "/snap", "/root", "/mnt/wsl",
)


def _autodetect_reveal_map() -> str:
    """Build a reveal map from container bind mounts by reading mountinfo.

    Parses ``/proc/self/mountinfo`` and, for each mount entry whose mount
    point (container side) is an existing directory and whose root (host
    side, field 4) is a non-trivial absolute path, adds a
    ``container_mount=host_root`` entry. This auto-translates container
    paths to host paths when ``LOCAL_PHOTO_AGENT_REVEAL_MAP`` is not set,
    so the "Copy Path" feature works in Docker without manual config.

    Returns the auto-detected map string, or ``""`` when not in a container
    or no usable bind mounts are found.
    """
    if not _is_running_in_container():
        return ""

    try:
        with open("/proc/self/mountinfo", "r") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return ""

    entries = []
    for line in lines:
        parts = line.split()
        # mountinfo has at least 10 fields; field 4 is root, field 5 is mount point.
        if len(parts) < 10:
            continue
        root = parts[3]  # host-side path within the source filesystem
        mount_point = parts[4]  # container-side mount point
        # Skip trivial root mounts and system paths.
        if root == "/" or root == "/etc/resolv.conf" or root == "/etc/hostname":
            continue
        if mount_point in _SYSTEM_MOUNT_PREFIXES or any(
            mount_point.startswith(p + "/") for p in _SYSTEM_MOUNT_PREFIXES
        ):
            continue
        if not Path(mount_point).is_dir():
            continue
        # Skip docker overlay/internal layers.
        if root.startswith("/var/lib/docker") or root.startswith("/docker"):
            continue
        entries.append(f"{mount_point}={root}")

    return ";".join(entries)


def _resolve_reveal_map(explicit_map: str) -> str:
    """Return the reveal map to use: explicit if set, else auto-detected."""
    if explicit_map:
        return explicit_map
    return _autodetect_reveal_map()


def _apply_reveal_map(server_path: str, reveal_map: str) -> str:
    """Translate a server-side path to a host path using the reveal map.

    ``reveal_map`` is a newline- or semicolon-separated list of
    ``container_prefix=host_prefix`` entries. The first entry whose
    container prefix matches the start of ``server_path`` is applied. If
    no entry matches (or the map is empty), ``server_path`` is returned
    unchanged, which is correct when the app runs directly on the host.
    """
    if not reveal_map:
        return server_path
    for line in reveal_map.replace("\n", ";").split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        container_prefix, host_prefix = line.split("=", 1)
        container_prefix = container_prefix.rstrip("/").strip()
        host_prefix = host_prefix.rstrip("/").strip()
        if not container_prefix or not host_prefix:
            continue
        if server_path == container_prefix or server_path.startswith(container_prefix + "/"):
            return host_prefix + server_path[len(container_prefix):]
    return server_path


def create_app(config=None):
    """Create and return a configured Dash application instance.

    Args:
        config: Optional AppConfig. If not provided, loaded from env vars.

    Returns:
        A ``dash.Dash`` application ready to be served.
    """
    if config is None:
        config = AppConfig.from_env()
    config.validate()

    cache = diskcache.FanoutCache("/tmp/dash-cache", size_limit=2**30, shards=4)
    background_callback_manager = DiskcacheManager(cache)

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        background_callback_manager=background_callback_manager,
        suppress_callback_exceptions=True,
    )

    def _create_extractor(backend=config.llm_backend, host=config.llm_host,
                          port=config.llm_port, model=config.llm_model,
                          timeout=config.timeout):
        """Factory wrapper that creates an extractor with the app's default prompt."""
        return create_extractor(
            backend=backend,
            host=host, port=port, model=model, timeout=timeout,
            default_prompt=config.default_prompt,
        )

    app.layout = create_layout(config)

    # Initialize services with proper dependency injection
    chat_client = OllamaChatClient(
        host=config.llm_host,
        port=config.llm_port,
        model=config.llm_model,
        timeout=config.timeout,
    )
    chat_service = ChatService(config, chat_client=chat_client)

    register_callbacks(app, _create_extractor, config.to_processing_config(),
                       config)

    # Register extracted Flask blueprints (vector API + diagnostic endpoints)
    register_vectors_blueprint(app.server, config)
    register_debug_blueprint(app.server, config)

    @app.server.route("/preview")
    def preview():
        """Serve a resized image preview with strict path validation.

        Both ``path`` and ``folder`` query params are required. The image must
        resolve to a real file inside ``folder``; anything else (missing
        params, non-existent path, a directory, or a path outside the folder
        i.e. directory traversal) is rejected with 404 so no filesystem layout
        is leaked.
        """
        path_str = request.args.get("path")
        folder_str = request.args.get("folder")
        size = request.args.get("size", "thumb")
        if not path_str or not folder_str:
            logger.debug("Preview rejected: missing path or folder parameter")
            abort(404)

        image_path, folder_path = _resolve_preview_paths(path_str, folder_str)
        if image_path is None:
            abort(404)

        try:
            data = read_image_bytes(image_path)
        except FileNotFoundError:
            logger.debug("Preview rejected: image file not found: %s", image_path)
            abort(404)
        except Exception:
            logger.exception("Preview read error for %s", image_path)
            abort(500)

        suffix = image_path.suffix.lower()
        if suffix in (".heic", ".heif"):
            content_type = "image/jpeg"
        else:
            content_type, _ = mimetypes.guess_type(str(image_path))
            if not content_type:
                content_type = "application/octet-stream"

        if _PIL_AVAILABLE and size == "thumb":
            max_size = 150
            try:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((max_size, max_size))
                buf = io.BytesIO()
                fmt = img.format
                if fmt == "PNG":
                    img.save(buf, format="PNG")
                else:
                    if img.mode in ("RGBA", "P", "LA"):
                        img = img.convert("RGB")
                    img.save(buf, format="JPEG", quality=85)
                data = buf.getvalue()
                content_type = "image/jpeg"
            except Exception:
                logger.warning("Image resize failed for %s, returning original", image_path, exc_info=True)
        elif size == "full":
            # Serve the original, unresized image so the fullscreen viewer
            # can actually fill the viewport at full resolution.
            pass

        response = make_response(data)
        response.headers["Content-Type"] = content_type
        return response

    @app.server.route("/_api/chat", methods=["POST"])
    def api_chat():
        """API endpoint to chat with the Ollama LLM with tool support.
        
        This endpoint has been refactored to use ChatService for business logic.
        The handler delegates to api_chat_handler which uses the ChatService.
        """
        return api_chat_handler(config, chat_service)

    @app.server.route("/_api/chat/stream", methods=["POST"])
    def api_chat_stream():
        """SSE streaming endpoint for chat responses.

        Streams LLM tokens to the browser as Server-Sent Events so that
        text appears incrementally in the chat window.
        """
        return api_chat_stream_handler(config, chat_service)

    @app.server.route("/_api/reveal", methods=["POST"])
    def api_reveal():
        """Return the host path of a photo so the user can locate it.

        Accepts JSON ``{"path": "<server image path>", "folder": "<folder>"}``.
        The path must resolve to a real file inside ``folder`` (same traversal
        guard as ``/preview``). When ``LOCAL_PHOTO_AGENT_REVEAL_MAP`` is set,
        the server-side path is translated to a host path first. The response
        includes both the file path and its containing directory.
        """
        data = request.get_json(silent=True) or {}
        path_str = data.get("path")
        folder_str = data.get("folder")
        if not path_str or not folder_str:
            return jsonify({"status": "error", "message": "path and folder are required"}), 400

        image_path, _folder_path = _resolve_preview_paths(path_str, folder_str)
        if image_path is None:
            return jsonify({"status": "error", "message": "path not found or outside folder"}), 404

        host_path = _apply_reveal_map(str(image_path), _resolve_reveal_map(config.reveal_map))
        return jsonify({
            "status": "success",
            "path": host_path,
            "folder": str(Path(host_path).parent),
        })

    return app, config


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app, config = create_app()
    DASH_HOST = config.dash_host
    DASH_PORT = config.dash_port
    DASH_DEBUG = config.dash_debug

    from src.state import request_shutdown
    signal.signal(signal.SIGINT, lambda _sig, _frame: request_shutdown())
    signal.signal(signal.SIGTERM, lambda _sig, _frame: request_shutdown())
    print(f"Starting Photo Feature Extractor web app on http://{DASH_HOST}:{DASH_PORT}")
    app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)
