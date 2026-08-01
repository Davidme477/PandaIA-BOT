from __future__ import annotations

from collections import deque
import hmac
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from services.tiktok.gift_image_service import (
    GIFT_CACHE_DIR,
    get_gift_image,
    get_overlay_image_url,
)
from services.overlay.events import sanitize_event


BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

event_queue: deque[dict[str, Any]] = deque(maxlen=256)
client_cursors: dict[str, int] = {}
event_sequence = 0
queue_lock = Lock()
ACCESS_TOKEN = os.environ.get("PANDAIA_OVERLAY_ACCESS_TOKEN", "")
logging.getLogger("werkzeug").disabled = True


def is_external_request() -> bool:
    host = request.host.split(":", 1)[0].casefold()
    return bool(request.headers.get("CF-Connecting-IP")) or host not in {"127.0.0.1", "localhost"}


def valid_external_access() -> bool:
    supplied = str(request.args.get("access", ""))
    return bool(ACCESS_TOKEN and supplied and hmac.compare_digest(supplied, ACCESS_TOKEN))


@app.before_request
def protect_overlay():
    protected_get = request.path == "/overlay" or request.path == "/api/events/next" or request.path.startswith("/gift-assets/")
    if request.path == "/health" and request.args.get("access") is not None and not valid_external_access():
        return jsonify({"ok": False, "error": "Token de instancia incorrecto."}), 403
    if request.method == "GET" and protected_get and is_external_request() and not valid_external_access():
        return jsonify({"ok": False, "error": "Acceso no autorizado."}), 403
    if request.method == "POST" and request.path in {"/api/events", "/api/test/gift", "/api/events/clear"} and is_external_request():
        return jsonify({"ok": False, "error": "Publicación externa no permitida."}), 403
    return None


@app.after_request
def disable_overlay_cache(response):
    if request.path == "/overlay" or request.path == "/api/events/next" or request.path.startswith("/gift-assets/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"
    return response


def enqueue_gift(event: dict[str, Any]) -> int:
    global event_sequence
    event_sequence += 1
    stored = dict(event); stored["_overlay_sequence"] = event_sequence
    event_queue.append(stored)
    return event_sequence


@app.get("/overlay")
def overlay():
    """
    Muestra el overlay que se agregará como fuente de navegador.
    """
    return render_template("overlay.html")


@app.get("/gift-assets/<path:filename>")
def gift_asset(filename: str):
    """
    Entrega al overlay las imágenes oficiales de regalos
    almacenadas dentro de cache/gifts.
    """
    return send_from_directory(
        directory=GIFT_CACHE_DIR,
        path=filename,
    )


@app.get("/api/events/next")
def next_event():
    """
    Entrega el siguiente evento de la cola.

    El evento se elimina de la cola solamente cuando el
    overlay lo solicita.
    """
    client_id = str(request.args.get("client_id", "legacy")).strip()[:64] or "legacy"
    with queue_lock:
        cursor = client_cursors.get(client_id, 0)
        available = [item for item in event_queue if item.get("type") == "gift" and int(item.get("_overlay_sequence", 0)) > cursor]
        stored_event = available[0] if available else None
        if stored_event is not None: client_cursors[client_id] = int(stored_event["_overlay_sequence"])
        remaining_events = max(0, len(available) - 1)
        event = {key: value for key, value in stored_event.items() if key != "_overlay_sequence"} if stored_event else None

    return jsonify(
        {
            "event": event,
            "remaining_events": remaining_events,
        }
    )


@app.post("/api/events")
def add_event():
    """
    Recibe un evento desde PandaIA o TikTokLive.

    Formato esperado para un regalo:

    {
        "type": "gift",
        "gift_id": "5655",
        "gift_name": "Rose",
        "quantity": 5,
        "image_url": "https://url-oficial-de-tiktok..."
    }
    """
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "No se recibió un JSON válido.",
                }
            ),
            400,
        )

    event_type = str(
        payload.get("type", "")
    ).strip().lower()

    if not event_type:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "El campo type es obligatorio.",
                }
            ),
            400,
        )

    if event_type != "gift":
        return jsonify({"ok": False, "error": "El overlay acepta exclusivamente eventos gift."}), 400

    gift_id = str(
        payload.get("gift_id", "")
    ).strip()

    gift_name = str(
        payload.get("gift_name", "")
    ).strip()

    official_image_url = str(
        payload.get("image_url", "")
    ).strip()

    if not gift_id:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "El campo gift_id es obligatorio.",
                }
            ),
            400,
        )

    if not gift_name:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "El campo gift_name es obligatorio.",
                }
            ),
            400,
        )

    try:
        quantity = int(
            payload.get("quantity", 1)
        )
    except (TypeError, ValueError):
        quantity = 1

    quantity = max(1, min(quantity, 999))

    local_image_path = None
    if official_image_url.startswith("/gift-assets/"):
        candidate = (GIFT_CACHE_DIR / Path(official_image_url).name).resolve()
        if candidate.parent == GIFT_CACHE_DIR.resolve() and candidate.is_file(): local_image_path = candidate
    else:
        local_image_path = get_gift_image(gift_id=gift_id, image_url=official_image_url)

    if local_image_path is None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "No se encontró el regalo en caché y "
                        "tampoco se pudo descargar su imagen."
                    ),
                    "gift_id": gift_id,
                    "gift_name": gift_name,
                }
            ),
            422,
        )

    local_image_url = get_overlay_image_url(
        local_image_path
    )

    event = {
        "type": "gift",
        "gift_id": gift_id,
        "gift_name": gift_name,
        "quantity": quantity,
        "image_url": local_image_url,
        "username": str(payload.get("username", "")),
        "animation": str(payload.get("animation", "Resplandor circular")),
        "event_id": str(payload.get("event_id", "")),
        "test": bool(payload.get("test", False)),
        "duration_ms": payload.get("duration_ms", 4200),
    }
    event = sanitize_event(event)

    with queue_lock:
        enqueue_gift(event)
        queue_position = len(event_queue)

    return jsonify(
        {
            "ok": True,
            "message": (
                f"{gift_name} x{quantity} agregado a la cola."
            ),
            "queue_position": queue_position,
            "cached_file": local_image_path.name,
            "event": event,
        }
    )


@app.post("/api/test/gift")
def test_gift():
    """
    Permite probar una imagen de regalo sin tener todavía
    conectada la cuenta de TikTok.

    Recibe el mismo formato que /api/events.
    """
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "No se recibió un JSON válido.",
                }
            ),
            400,
        )

    payload["type"] = "gift"

    gift_id = str(
        payload.get("gift_id", "")
    ).strip()

    gift_name = str(
        payload.get("gift_name", "")
    ).strip()

    official_image_url = str(
        payload.get("image_url", "")
    ).strip()

    if not gift_id or not gift_name:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "gift_id y gift_name son obligatorios."
                    ),
                }
            ),
            400,
        )

    try:
        quantity = int(
            payload.get("quantity", 1)
        )
    except (TypeError, ValueError):
        quantity = 1

    quantity = max(1, min(quantity, 999))

    local_image_path = get_gift_image(
        gift_id=gift_id,
        image_url=official_image_url,
    )

    if local_image_path is None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "No se pudo obtener la imagen del regalo."
                    ),
                }
            ),
            422,
        )

    event = {
        "type": "gift",
        "gift_id": gift_id,
        "gift_name": gift_name,
        "quantity": quantity,
        "image_url": get_overlay_image_url(
            local_image_path
        ),
    }

    with queue_lock:
        enqueue_gift(event)
        queue_position = len(event_queue)

    return jsonify(
        {
            "ok": True,
            "message": (
                f"Prueba de {gift_name} x{quantity} "
                "agregada a la cola."
            ),
            "queue_position": queue_position,
            "event": event,
        }
    )


@app.post("/api/events/clear")
def clear_events():
    """
    Vacía todos los eventos pendientes.
    """
    with queue_lock:
        removed_events = len(event_queue)
        event_queue.clear()
        client_cursors.clear()

    return jsonify(
        {
            "ok": True,
            "removed_events": removed_events,
        }
    )


@app.get("/health")
def health():
    """
    Confirma que el servidor del overlay está funcionando.
    """
    with queue_lock:
        queued_events = len(event_queue)

    cached_files = [
        file_path.name
        for file_path in GIFT_CACHE_DIR.iterdir()
        if file_path.is_file()
        and not file_path.name.endswith(".tmp")
    ]

    return jsonify(
        {
            "status": "ok",
            "service": "PandaIA Overlay Engine",
            "queued_events": queued_events,
            "cached_gifts": len(cached_files),
            "gift_cache_directory": str(
                GIFT_CACHE_DIR
            ),
            "overlay_url": (
                "http://127.0.0.1:5050/overlay"
            ),
        }
    )


def run_server() -> None:
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    run_server()
