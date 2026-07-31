from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
    FollowEvent,
    GiftEvent,
)

from services.tiktok.gift_image_service import (
    get_gift_image,
    get_overlay_image_url,
)


TIKTOK_USERNAME = "@latidosmusicales3"
OVERLAY_EVENTS_URL = "http://127.0.0.1:5050/api/events"

StatusCallback = Callable[[str, str], None]
ActivityCallback = Callable[[str, str, str, str], None]


def get_first_image_url(gift: object) -> str:
    image = getattr(gift, "image", None)

    if image is None:
        return ""

    url_list = getattr(image, "url_list", None)

    if url_list:
        return str(url_list[0]).strip()

    url = getattr(image, "url", None)

    if url:
        return str(url).strip()

    return ""


def send_event_to_overlay(
    *,
    gift_id: str,
    gift_name: str,
    quantity: int,
    image_url: str,
) -> bool:
    payload = {
        "type": "gift",
        "gift_id": gift_id,
        "gift_name": gift_name,
        "quantity": quantity,
        "image_url": image_url,
    }

    request_data = json.dumps(payload).encode("utf-8")

    overlay_request = Request(
        OVERLAY_EVENTS_URL,
        data=request_data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            overlay_request,
            timeout=10,
        ) as response:
            response_data = response.read().decode("utf-8")

        print(
            "[TikTokService] Regalo enviado al overlay:",
            response_data,
        )

        return True

    except HTTPError as error:
        error_content = error.read().decode(
            "utf-8",
            errors="replace",
        )

        print(
            "[TikTokService] El overlay rechazó el evento:",
            error.code,
            error_content,
        )

    except URLError as error:
        print(
            "[TikTokService] No se pudo conectar al overlay:",
            error,
        )

    except Exception as error:
        print(
            "[TikTokService] Error enviando el regalo:",
            error,
        )

    return False


class TikTokService:
    def __init__(
        self,
        username: str,
        status_callback: StatusCallback | None = None,
        activity_callback: ActivityCallback | None = None,
    ) -> None:
        self.username = username.strip()
        self.status_callback = status_callback
        self.activity_callback = activity_callback

        if not self.username.startswith("@"):
            self.username = f"@{self.username}"

        self.client = TikTokLiveClient(
            unique_id=self.username
        )

        self.register_events()

    def notify_status(
        self,
        status: str,
        message: str,
    ) -> None:
        if self.status_callback is not None:
            self.status_callback(
                status,
                message,
            )

    def notify_activity(
        self,
        icon: str,
        title: str,
        user: str,
        amount: str = "",
    ) -> None:
        if self.activity_callback is not None:
            self.activity_callback(
                icon,
                title,
                user,
                amount,
            )

    def register_events(self) -> None:
        @self.client.on(ConnectEvent)
        async def on_connect(
            event: ConnectEvent,
        ) -> None:
            print("=" * 60)
            print("PANDAIA CONECTADO A TIKTOK")
            print("=" * 60)
            print("Usuario:", self.username)
            print("Room ID:", self.client.room_id)
            print("=" * 60)

            self.notify_status(
                "tiktok_connected",
                (
                    "PandaIA está conectado al LIVE de "
                    f"{self.username}."
                ),
            )

        @self.client.on(DisconnectEvent)
        async def on_disconnect(
            event: DisconnectEvent,
        ) -> None:
            print("=" * 60)
            print("PANDAIA DESCONECTADO DE TIKTOK")
            print("=" * 60)

            self.notify_status(
                "tiktok_disconnected",
                (
                    "PandaIA se desconectó de "
                    f"{self.username}."
                ),
            )

        @self.client.on(CommentEvent)
        async def on_comment(
            event: CommentEvent,
        ) -> None:
            sender = getattr(
                event.user,
                "unique_id",
                "usuario",
            )

            comment = str(
                getattr(
                    event,
                    "comment",
                    "",
                )
            ).strip()

            if not comment:
                return

            print("=" * 60)
            print("COMENTARIO RECIBIDO")
            print("=" * 60)
            print("Usuario:", sender)
            print("Comentario:", comment)
            print("=" * 60)

            self.notify_activity(
                "💬",
                comment,
                f"@{sender}",
                "",
            )

        @self.client.on(FollowEvent)
        async def on_follow(
            event: FollowEvent,
        ) -> None:
            sender = getattr(
                event.user,
                "unique_id",
                "usuario",
            )

            print("=" * 60)
            print("NUEVO SEGUIDOR")
            print("=" * 60)
            print("Usuario:", sender)
            print("=" * 60)

            self.notify_activity(
                "👤",
                "Nuevo Seguidor",
                f"@{sender}",
                "",
            )

        @self.client.on(GiftEvent)
        async def on_gift(
            event: GiftEvent,
        ) -> None:
            gift = event.gift

            if gift is None:
                return

            gift_type = int(
                getattr(
                    gift,
                    "type",
                    0,
                )
                or 0
            )

            if gift_type == 1 and event.streaking:
                return

            gift_id = str(
                getattr(
                    gift,
                    "id",
                    "",
                )
            ).strip()

            gift_name = str(
                getattr(
                    gift,
                    "name",
                    "Regalo",
                )
            ).strip()

            quantity = max(
                1,
                int(
                    event.repeat_count
                    or 1
                ),
            )

            image_url = get_first_image_url(
                gift
            )

            sender = getattr(
                event.user,
                "unique_id",
                "usuario",
            )

            print("=" * 60)
            print("REGALO RECIBIDO")
            print("=" * 60)
            print("Usuario:", sender)
            print("ID:", gift_id)
            print("Nombre:", gift_name)
            print("Cantidad:", quantity)
            print(
                "Imagen oficial:",
                image_url or "No disponible",
            )

            self.notify_activity(
                "🎁",
                f"Regalo {gift_name}",
                f"@{sender}",
                f"x{quantity}",
            )

            local_image = get_gift_image(
                gift_id=gift_id,
                image_url=image_url,
            )

            if local_image is None:
                print(
                    "Resultado: no se pudo obtener "
                    "la imagen del regalo."
                )
                print("=" * 60)
                return

            local_image_url = get_overlay_image_url(
                local_image
            )

            print(
                "Archivo en caché:",
                local_image,
            )

            print(
                "URL local:",
                local_image_url,
            )

            sent = send_event_to_overlay(
                gift_id=gift_id,
                gift_name=gift_name,
                quantity=quantity,
                image_url=image_url,
            )

            if sent:
                print(
                    "Resultado: enviado al overlay."
                )
            else:
                print(
                    "Resultado: no enviado al overlay."
                )

            print("=" * 60)

    async def connect(self) -> None:
        await self.client.connect(
            fetch_gift_info=True
        )

    async def disconnect(self) -> None:
        await self.client.disconnect()

    def run(self) -> None:
        print("=" * 60)
        print("INICIANDO PANDAIA TIKTOK")
        print("=" * 60)
        print("Cuenta:", self.username)
        print(
            "Esperando que la cuenta se encuentre "
            "transmitiendo en vivo..."
        )
        print("=" * 60)

        self.client.run(
            fetch_gift_info=True
        )


def main() -> None:
    service = TikTokService(
        username=TIKTOK_USERNAME
    )

    service.run()


if __name__ == "__main__":
    main()