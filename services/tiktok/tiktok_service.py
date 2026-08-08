from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
    FollowEvent,
    GiftEvent,
    LikeEvent,
    RoomUserSeqEvent,
)

from services.tiktok.gift_image_service import (
    get_gift_image,
    get_overlay_image_url,
)
from services.tiktok.like_ranking import (
    LikeRankingManager,
)
from services.tiktok.live_state import (
    LiveState,
    LiveStats,
)


TIKTOK_USERNAME = "@latidosmusicales3"

StatusCallback = Callable[[str, str], None]
ActivityCallback = Callable[
    [str, str, str, str],
    None,
]
CommentCallback = Callable[[str, str], None]
GiftCallback = Callable[[str, str, int], None]
StatsCallback = Callable[[LiveStats], None]
ResetCallback = Callable[[], None]
MemberLevelCallback = Callable[..., object]


class GiftAnimationCallback(Protocol):
    def __call__(
        self,
        *,
        gift_id: str,
        gift_name: str,
        quantity: int,
        username: str,
        image_url: str = "",
        event_id: str = "",
    ) -> object:
        ...


def get_first_image_url(gift: object) -> str:
    image = getattr(gift, "image", None)

    if image is None:
        return ""

    url_list = getattr(
        image,
        "url_list",
        None,
    )

    if url_list:
        return str(url_list[0]).strip()

    url = getattr(
        image,
        "url",
        None,
    )

    if url:
        return str(url).strip()

    return ""


class TikTokService:
    def __init__(
        self,
        username: str,
        status_callback: StatusCallback | None = None,
        activity_callback: ActivityCallback | None = None,
        comment_callback: CommentCallback | None = None,
        gift_callback: GiftCallback | None = None,
        gift_animation_callback:
            GiftAnimationCallback | None = None,
        stats_callback: StatsCallback | None = None,
        reset_callback: ResetCallback | None = None,
        member_level_callback:
            MemberLevelCallback | None = None,
    ) -> None:
        self.username = username.strip()
        self.status_callback = status_callback
        self.activity_callback = activity_callback
        self.comment_callback = comment_callback
        self.gift_callback = gift_callback
        self.gift_animation_callback = (
            gift_animation_callback
        )
        self.stats_callback = stats_callback
        self.reset_callback = reset_callback
        self.member_level_callback = (
            member_level_callback
        )

        self.live_state = LiveState()
        self.like_ranking = LikeRankingManager()

        self._timer_task: asyncio.Task[None] | None = None
        self._live_connected = False

        if not self.username.startswith("@"):
            self.username = f"@{self.username}"

        self.client = TikTokLiveClient(
            unique_id=self.username
        )

        self.register_events()

    def inspect_member_level(
        self,
        event: object,
    ) -> None:
        if self.member_level_callback is None:
            return

        user = getattr(event, "user", None)

        if user is None:
            return

        try:
            self.member_level_callback(
                user,
                event_id=str(
                    getattr(event, "id", "")
                ),
            )
        except Exception as error:
            print(
                "[TikTokService] Error al procesar "
                "nivel de miembro:",
                error,
            )

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

    def notify_stats(
        self,
        stats: LiveStats | None = None,
    ) -> None:
        if self.stats_callback is not None:
            self.stats_callback(
                stats or self.live_state.snapshot()
            )

    async def update_elapsed(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                self.notify_stats()
        except asyncio.CancelledError:
            return

    def register_events(self) -> None:
        @self.client.on(ConnectEvent)
        async def on_connect(
            event: ConnectEvent,
        ) -> None:
            self._live_connected = True
            self.like_ranking.reset()

            self.notify_stats(
                self.live_state.connect()
            )

            if self.reset_callback is not None:
                self.reset_callback()

            self._timer_task = asyncio.create_task(
                self.update_elapsed()
            )

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
            self._live_connected = False

            if self._timer_task is not None:
                self._timer_task.cancel()
                self._timer_task = None

            self.notify_stats(
                self.live_state.disconnect()
            )

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
            if not self._live_connected:
                return

            self.inspect_member_level(event)

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

            self.notify_stats(
                self.live_state.add_comment(
                    comment,
                    f"@{sender}",
                )
            )

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

            if self.comment_callback is not None:
                self.comment_callback(
                    str(sender),
                    comment,
                )

        @self.client.on(FollowEvent)
        async def on_follow(
            event: FollowEvent,
        ) -> None:
            if not self._live_connected:
                return

            self.inspect_member_level(event)

            sender = getattr(
                event.user,
                "unique_id",
                "usuario",
            )

            self.live_state.add_follow(
                f"@{sender}"
            )

            print("=" * 60)
            print("NUEVO SEGUIDOR")
            print("=" * 60)
            print("Usuario:", sender)
            print("=" * 60)

            self.notify_activity(
                "👤",
                "Nuevo seguidor",
                f"@{sender}",
                "",
            )

        @self.client.on(GiftEvent)
        async def on_gift(
            event: GiftEvent,
        ) -> None:
            if not self._live_connected:
                return

            self.inspect_member_level(event)

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

            if (
                gift_type == 1 and
                event.streaking
            ):
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
                    event.repeat_count or 1
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

            self.notify_stats(
                self.live_state.add_gift(
                    name=gift_name,
                    user=f"@{sender}",
                    quantity=quantity,
                    streaking=False,
                )
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

            if self.gift_callback is not None:
                self.gift_callback(
                    str(sender),
                    gift_name,
                    quantity,
                )

            if (
                self.gift_animation_callback
                is not None
            ):
                try:
                    self.gift_animation_callback(
                        gift_id=gift_id,
                        gift_name=gift_name,
                        quantity=quantity,
                        username=str(sender),
                        image_url=image_url,
                        event_id=str(
                            getattr(
                                event,
                                "id",
                                "",
                            )
                        ),
                    )
                except Exception as error:
                    print(
                        "[TikTokService] Error al "
                        "enviar la animación del regalo:",
                        error,
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

            local_image_url = (
                get_overlay_image_url(
                    local_image
                )
            )

            print(
                "Archivo en caché:",
                local_image,
            )
            print(
                "URL local:",
                local_image_url,
            )
            print("=" * 60)

        @self.client.on(RoomUserSeqEvent)
        async def on_room_users(
            event: RoomUserSeqEvent,
        ) -> None:
            if not self._live_connected:
                return

            self.notify_stats(
                self.live_state.update_viewers(
                    event.total
                )
            )

        @self.client.on(LikeEvent)
        async def on_like(
            event: LikeEvent,
        ) -> None:
            if not self._live_connected:
                return

            self.notify_stats(
                self.live_state.update_likes(
                    total=event.total,
                    count=event.count,
                )
            )

            user = getattr(
                event,
                "user",
                None,
            )

            if user is not None:
                self.like_ranking.observe(
                    user,
                    int(event.count or 0),
                )

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