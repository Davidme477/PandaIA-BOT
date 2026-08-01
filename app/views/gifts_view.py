from __future__ import annotations

import time
import webbrowser

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget, QInputDialog,
    QTableWidgetItem, QVBoxLayout, QWidget, QApplication,
)

from config.settings_store import read_settings
from services.overlay.events import OVERLAY_URL, post_overlay_event
from services.tiktok.gift_image_service import GIFT_CACHE_DIR
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.oauth import SCOPES, SpotifyAuthError, SpotifyOAuthPKCE
from services.spotify.runtime import SpotifyRuntime


class SpotifyAuthWorker(QThread):
    authorized = Signal(object)
    failed = Signal(str)

    def __init__(self, client_id: str) -> None:
        super().__init__()
        self.oauth = SpotifyOAuthPKCE(client_id)

    def run(self) -> None:
        try:
            self.authorized.emit(self.oauth.authorize())
        except SpotifyAuthError as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        self.oauth.cancel()


class GiftsView(QScrollArea):
    settings_changed = Signal(object)

    def __init__(self, runtime: SpotifyRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.store = runtime.store
        self.auth_worker: SpotifyAuthWorker | None = None
        self._loading = True
        self.settings = dict(runtime.settings)
        self.setObjectName("giftsScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._build()
        self._connect()
        self.load_values()
        self._loading = False

    def _build(self) -> None:
        content = QWidget(); content.setObjectName("giftsContent")
        root = QVBoxLayout(content); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(12)
        title = QLabel("Regalos y Animaciones"); title.setObjectName("pageTitle")
        subtitle = QLabel("Gestiona animaciones reales, solicitudes musicales y el overlay local.")
        subtitle.setObjectName("pageSubtitle"); subtitle.setWordWrap(True)
        self.tabs = QTabWidget(); self.tabs.setObjectName("featureTabs")
        self.tabs.addTab(self._animations_tab(), "Animaciones")
        self.tabs.addTab(self._spotify_tab(), "Spotify")
        self.tabs.addTab(self._overlay_tab(), "Overlay")
        root.addWidget(title); root.addWidget(subtitle); root.addWidget(self.tabs, 1)
        self.setWidget(content)

    @staticmethod
    def panel(title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(); frame.setObjectName("tiktokPanel")
        layout = QVBoxLayout(frame); layout.setContentsMargins(18, 16, 18, 18); layout.setSpacing(12)
        heading = QLabel(title); heading.setObjectName("panelTitle"); layout.addWidget(heading)
        return frame, layout

    def _tab_scroll(self, panel: QWidget) -> QScrollArea:
        scroll = QScrollArea(); scroll.setObjectName("featureScroll")
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrapper = QWidget(); wrapper.setObjectName("featureContent")
        layout = QVBoxLayout(wrapper); layout.setContentsMargins(8, 12, 8, 8); layout.addWidget(panel); layout.addStretch()
        scroll.setWidget(wrapper); return scroll

    def _animations_tab(self) -> QWidget:
        panel, layout = self.panel("Animaciones de regalos")
        self.animations_enabled = QCheckBox("Activar animaciones")
        self.animation_info = QLabel("Se reutiliza la animación Resplandor circular y las imágenes oficiales cacheadas de TikTok.")
        self.animation_info.setWordWrap(True); self.animation_info.setObjectName("helperText")
        resource_row = QHBoxLayout()
        self.gift_resource = QComboBox()
        for path in sorted(GIFT_CACHE_DIR.glob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                self.gift_resource.addItem(path.stem, path.name)
        self.add_assignment = QPushButton("Añadir asignación")
        self.add_assignment.setObjectName("voiceSecondaryButton")
        self.add_assignment.setEnabled(self.gift_resource.count() > 0)
        self.add_assignment.clicked.connect(self.add_selected_assignment)
        resource_row.addWidget(self.gift_resource, 1); resource_row.addWidget(self.add_assignment)
        self.assignments = QTableWidget(0, 6); self.assignments.setHorizontalHeaderLabels(
            ["Regalo / ID", "Animación", "Estado", "Duración", "Sonido", "Acciones"]
        )
        self.assignments.horizontalHeader().setStretchLastSection(True)
        self.assignments.setMinimumHeight(220)
        test = QPushButton("Probar animación seleccionada"); test.setObjectName("primaryButton")
        test.clicked.connect(self.test_animation)
        layout.addWidget(self.animations_enabled); layout.addWidget(self.animation_info); layout.addLayout(resource_row)
        layout.addWidget(self.assignments); layout.addWidget(test)
        return self._tab_scroll(panel)

    def _spotify_tab(self) -> QWidget:
        panel, layout = self.panel("Solicitudes musicales Spotify Premium")
        grid = QGridLayout(); grid.setColumnStretch(1, 1)
        self.client_id = QLineEdit(); self.client_id.setEchoMode(QLineEdit.EchoMode.Password)
        self.save_client = QPushButton("Guardar ID"); self.connect_spotify = QPushButton("Conectar Spotify")
        self.disconnect_spotify = QPushButton("Desconectar cuenta")
        for button in (self.save_client, self.connect_spotify): button.setObjectName("primaryButton")
        self.disconnect_spotify.setObjectName("voiceSecondaryButton")
        grid.addWidget(QLabel("ID de cliente"), 0, 0); grid.addWidget(self.client_id, 0, 1); grid.addWidget(self.save_client, 0, 2)
        buttons = QHBoxLayout(); buttons.addWidget(self.connect_spotify); buttons.addWidget(self.disconnect_spotify)
        grid.addLayout(buttons, 1, 1, 1, 2)
        self.spotify_state = QLabel("No configurado"); self.spotify_state.setObjectName("connectionDisconnected")
        self.spotify_message = QLabel(""); self.spotify_message.setWordWrap(True); self.spotify_message.setObjectName("helperText")
        self.account_label = QLabel("Cuenta: —"); self.device_label = QLabel("Dispositivo activo: —")
        self.playback_label = QLabel("Reproduciendo ahora: —"); self.progress_label = QLabel("Progreso: —")
        layout.addLayout(grid); layout.addWidget(self.spotify_state); layout.addWidget(self.spotify_message)
        for label in (self.account_label, self.device_label, self.playback_label, self.progress_label):
            label.setWordWrap(True); layout.addWidget(label)
        controls, controls_layout = self.panel("Controles de solicitudes")
        self.requests_enabled = QCheckBox("Activar solicitudes musicales")
        self.command = QLineEdit("M"); self.command.setMaxLength(3)
        self.max_pending = QSpinBox(); self.max_pending.setRange(1, 100)
        self.max_user = QSpinBox(); self.max_user.setRange(1, 20)
        self.cooldown = QSpinBox(); self.cooldown.setRange(0, 3600); self.cooldown.setSuffix(" s")
        self.allow_explicit = QCheckBox("Permitir contenido explícito")
        self.block_duplicates = QCheckBox("Evitar canciones duplicadas")
        self.only_connected = QCheckBox("Aceptar solo con TikTok conectado")
        self.announce_tts = QCheckBox("Anunciar solicitudes mediante TTS")
        form = QGridLayout(); form.addWidget(self.requests_enabled, 0, 0, 1, 2)
        for row, (name, widget) in enumerate((("Comando", self.command), ("Máximo pendiente", self.max_pending),
                ("Máximo por usuario", self.max_user), ("Espera por usuario", self.cooldown)), start=1):
            form.addWidget(QLabel(name), row, 0); form.addWidget(widget, row, 1)
        for widget in (self.allow_explicit, self.block_duplicates, self.only_connected, self.announce_tts):
            form.addWidget(widget, form.rowCount(), 0, 1, 2)
        controls_layout.addLayout(form); layout.addWidget(controls)
        queue_panel, queue_layout = self.panel("Cola musical interna")
        self.queue_table = QTableWidget(0, 6); self.queue_table.setHorizontalHeaderLabels(
            ["Posición", "Título", "Artista", "Usuario", "Duración", "Estado"])
        self.queue_table.horizontalHeader().setStretchLastSection(True); self.queue_table.setMinimumHeight(220)
        row = QHBoxLayout()
        self.remove_request = QPushButton("Eliminar pendiente"); self.clear_queue = QPushButton("Limpiar cola")
        self.skip_track = QPushButton("Saltar canción"); self.pause_track = QPushButton("Pausar/Reanudar")
        self.refresh_device = QPushButton("Actualizar dispositivo")
        for button in (self.remove_request, self.clear_queue, self.skip_track, self.pause_track, self.refresh_device):
            button.setObjectName("voiceSecondaryButton"); row.addWidget(button)
        queue_layout.addWidget(self.queue_table); queue_layout.addLayout(row); layout.addWidget(queue_panel)
        return self._tab_scroll(panel)

    def _overlay_tab(self) -> QWidget:
        panel, layout = self.panel("Overlay para OBS / TikTok Live Studio")
        self.overlay_state = QLabel("URL local del overlay existente")
        self.overlay_url = QLineEdit(OVERLAY_URL); self.overlay_url.setReadOnly(True)
        buttons = QHBoxLayout(); copy = QPushButton("Copiar URL"); preview = QPushButton("Abrir vista previa")
        copy.setObjectName("primaryButton"); preview.setObjectName("voiceSecondaryButton")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(OVERLAY_URL))
        preview.clicked.connect(lambda: webbrowser.open(OVERLAY_URL))
        buttons.addWidget(copy); buttons.addWidget(preview)
        self.show_animations = QCheckBox("Mostrar animaciones")
        self.show_current = QCheckBox("Mostrar canción actual")
        self.show_next = QCheckBox("Mostrar próxima canción")
        self.show_requester = QCheckBox("Mostrar nombre del solicitante")
        info = QLabel("Fuente de navegador: 1080×1920, fondo transparente. El audio permanece en Spotify/OBS.")
        info.setWordWrap(True); info.setObjectName("helperText")
        layout.addWidget(self.overlay_state); layout.addWidget(self.overlay_url); layout.addLayout(buttons); layout.addWidget(info)
        for widget in (self.show_animations, self.show_current, self.show_next, self.show_requester): layout.addWidget(widget)
        return self._tab_scroll(panel)

    def _connect(self) -> None:
        self.save_client.clicked.connect(self.save_client_id); self.connect_spotify.clicked.connect(self.start_authorization)
        self.disconnect_spotify.clicked.connect(self.runtime.disconnect); self.refresh_device.clicked.connect(lambda: self.runtime.request_action("refresh"))
        self.clear_queue.clicked.connect(self.clear_pending); self.remove_request.clicked.connect(self.remove_selected)
        self.skip_track.clicked.connect(lambda: self._playback_action("next")); self.pause_track.clicked.connect(self.toggle_pause)
        self.runtime.state_changed.connect(self.set_spotify_state); self.runtime.account_changed.connect(self.set_account)
        self.runtime.queue_changed.connect(self.set_queue); self.runtime.playback_changed.connect(self.set_playback)
        for widget in (self.animations_enabled, self.requests_enabled, self.allow_explicit, self.block_duplicates,
                       self.only_connected, self.announce_tts, self.show_animations, self.show_current,
                       self.show_next, self.show_requester): widget.toggled.connect(self.save_settings)
        for widget in (self.command,): widget.editingFinished.connect(self.save_settings)
        for widget in (self.max_pending, self.max_user, self.cooldown): widget.valueChanged.connect(self.save_settings)

    def load_values(self) -> None:
        local = self.store.load(); self.client_id.setText(str(local.get("client_id", "")))
        if local.get("access_token"): self.spotify_state.setText("Desconectado"); self.runtime.request_action("refresh")
        values = self.settings
        self.animations_enabled.setChecked(bool(values.get("animations_enabled", True)))
        self.requests_enabled.setChecked(bool(values.get("requests_enabled", False)))
        self.command.setText(str(values.get("command", "M"))); self.max_pending.setValue(int(values.get("max_pending", 20)))
        self.max_user.setValue(int(values.get("max_per_user", 2))); self.cooldown.setValue(int(values.get("user_cooldown", 120)))
        self.allow_explicit.setChecked(bool(values.get("allow_explicit", False))); self.block_duplicates.setChecked(bool(values.get("block_duplicates", True)))
        self.only_connected.setChecked(bool(values.get("only_when_tiktok_connected", True))); self.announce_tts.setChecked(bool(values.get("announce_tts", False)))
        overlay = values.get("overlay", {}) if isinstance(values.get("overlay"), dict) else {}
        self.show_animations.setChecked(bool(overlay.get("show_animations", True))); self.show_current.setChecked(bool(overlay.get("show_current", True)))
        self.show_next.setChecked(bool(overlay.get("show_next", True))); self.show_requester.setChecked(bool(overlay.get("show_requester", True)))
        self.load_assignments()

    def values(self) -> dict[str, object]:
        return {"animations_enabled": self.animations_enabled.isChecked(), "requests_enabled": self.requests_enabled.isChecked(),
                "command": self.command.text().strip() or "M", "max_pending": self.max_pending.value(), "max_per_user": self.max_user.value(),
                "user_cooldown": self.cooldown.value(), "allow_explicit": self.allow_explicit.isChecked(),
                "block_duplicates": self.block_duplicates.isChecked(), "only_when_tiktok_connected": self.only_connected.isChecked(),
                "announce_tts": self.announce_tts.isChecked(), "assignments": self.settings.get("assignments", {}),
                "overlay": {"show_animations": self.show_animations.isChecked(), "show_current": self.show_current.isChecked(),
                            "show_next": self.show_next.isChecked(), "show_requester": self.show_requester.isChecked()}}

    def save_settings(self, *_args) -> None:
        if self._loading:
            return
        self.settings.update(self.values()); self.settings_changed.emit(self.values())
        post_overlay_event({"type": "visibility", **self.values()["overlay"]})

    def save_client_id(self) -> None:
        self.store.save_client_id(self.client_id.text()); self.set_spotify_state("Desconectado", "ID guardado únicamente en este PC.")

    def start_authorization(self) -> None:
        if self.auth_worker is not None and self.auth_worker.isRunning():
            self.auth_worker.cancel(); return
        client_id = self.client_id.text().strip()
        if not client_id: self.set_spotify_state("No configurado", "Introduce el ID de cliente."); return
        self.store.save_client_id(client_id); self.set_spotify_state("Autorizando", "Completa la autorización en el navegador.")
        self.connect_spotify.setText("Cancelar autorización")
        self.auth_worker = SpotifyAuthWorker(client_id); self.auth_worker.authorized.connect(self.authorization_done)
        self.auth_worker.failed.connect(lambda message: self.set_spotify_state("Cuenta no autorizada", message))
        self.auth_worker.finished.connect(self.authorization_finished); self.auth_worker.start()

    def authorization_done(self, tokens: dict[str, object]) -> None:
        tokens = dict(tokens); tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600)); tokens["scopes"] = SCOPES.split()
        self.store.save(tokens); self.runtime.request_action("refresh")

    def authorization_finished(self) -> None:
        self.connect_spotify.setText("Conectar Spotify"); self.auth_worker = None

    def set_spotify_state(self, state: str, message: str) -> None:
        self.spotify_state.setText(state); self.spotify_message.setText(message)

    def set_account(self, data: dict[str, object]) -> None:
        self.account_label.setText(f"Cuenta: {data.get('name', '—')}")
        device = data.get("device") if isinstance(data.get("device"), dict) else {}
        self.device_label.setText(f"Dispositivo activo: {device.get('name', '—')}")
        if data:
            self.store.save({"account_id": data.get("id", ""), "account_name": data.get("name", "")})

    def set_playback(self, data: dict[str, object]) -> None:
        item = data.get("item") if isinstance(data.get("item"), dict) else {}
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
        self.playback_label.setText(f"Reproduciendo ahora: {item.get('name', '—')} · {artists}")
        self.progress_label.setText(f"Progreso: {self.duration(data.get('progress_ms', 0))} / {self.duration(item.get('duration_ms', 0))}")
        self.pause_track.setProperty("paused", not bool(data.get("is_playing", False)))

    @staticmethod
    def duration(milliseconds: object) -> str:
        seconds = max(0, int(milliseconds or 0) // 1000); return f"{seconds // 60}:{seconds % 60:02d}"

    def set_queue(self, items) -> None:
        self.queue_table.setRowCount(len(items))
        for row, request in enumerate(items):
            for column, value in enumerate((row + 1, request.track.title, request.track.artist, f"@{request.username.lstrip('@')}",
                                            self.duration(request.track.duration_ms), request.status.value)):
                self.queue_table.setItem(row, column, QTableWidgetItem(str(value)))
            self.queue_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, request.request_id)

    def remove_selected(self) -> None:
        row = self.queue_table.currentRow()
        if row >= 0 and self.queue_table.item(row, 0):
            self.runtime.requests.remove_pending(str(self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)))
            self.set_queue(self.runtime.requests.snapshot())

    def clear_pending(self) -> None:
        self.runtime.requests.clear_pending(); self.set_queue(self.runtime.requests.snapshot())

    def _playback_action(self, action: str) -> None:
        self.runtime.request_action(action)

    def toggle_pause(self) -> None:
        self._playback_action("resume" if self.pause_track.property("paused") else "pause")

    def load_assignments(self) -> None:
        assignments = self.settings.get("assignments", {})
        rows = list(assignments.items()) if isinstance(assignments, dict) else []
        self.assignments.setRowCount(len(rows))
        for row, (gift_id, value) in enumerate(rows):
            data = value if isinstance(value, dict) else {}
            for column, text in enumerate((gift_id, data.get("animation", "Resplandor circular"),
                    "Activa" if data.get("active", True) else "Inactiva", data.get("duration", "4.2 s"),
                    data.get("sound", "Sin sonido"))):
                self.assignments.setItem(row, column, QTableWidgetItem(str(text)))
            actions = QWidget(); action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(0, 0, 0, 0)
            test = QPushButton("Probar"); edit = QPushButton("Editar"); toggle = QPushButton("Desactivar" if data.get("active", True) else "Activar")
            for button in (test, edit, toggle): button.setObjectName("voiceSecondaryButton"); action_layout.addWidget(button)
            test.clicked.connect(lambda _checked=False, current=gift_id: self.test_animation_id(current))
            edit.clicked.connect(lambda _checked=False, current=gift_id: self.edit_assignment(current))
            toggle.clicked.connect(lambda _checked=False, current=gift_id: self.toggle_assignment(current))
            self.assignments.setCellWidget(row, 5, actions)

    def add_selected_assignment(self) -> None:
        gift_id = self.gift_resource.currentText().strip()
        if not gift_id:
            return
        assignments = dict(self.settings.get("assignments", {}))
        assignments[gift_id] = {
            "animation": "Resplandor circular", "active": True,
            "duration": "4.2 s", "sound": "Sin sonido",
        }
        self.settings["assignments"] = assignments
        self.load_assignments(); self.save_settings()

    def test_animation(self) -> None:
        row = self.assignments.currentRow()
        if row < 0: return
        self.test_animation_id(self.assignments.item(row, 0).text())

    def test_animation_id(self, gift_id: str) -> None:
        index = self.gift_resource.findText(gift_id)
        post_overlay_event({"type": "gift", "gift_id": gift_id, "gift_name": gift_id, "quantity": 1,
                            "username": "Prueba local", "animation": "Resplandor circular", "test": True,
                            "image_url": f"/gift-assets/{self.gift_resource.itemData(index) or gift_id + '.png'}"})

    def toggle_assignment(self, gift_id: str) -> None:
        assignments = dict(self.settings.get("assignments", {})); value = dict(assignments.get(gift_id, {}))
        value["active"] = not bool(value.get("active", True)); assignments[gift_id] = value
        self.settings["assignments"] = assignments; self.load_assignments(); self.save_settings()

    def edit_assignment(self, gift_id: str) -> None:
        assignments = dict(self.settings.get("assignments", {})); value = dict(assignments.get(gift_id, {}))
        current = float(str(value.get("duration", "4.2 s")).replace("s", "").strip())
        duration, accepted = QInputDialog.getDouble(self, "Duración", "Segundos de animación", current, 0.5, 30.0, 1)
        if accepted:
            value["duration"] = f"{duration:.1f} s"; assignments[gift_id] = value
            self.settings["assignments"] = assignments; self.load_assignments(); self.save_settings()

    def shutdown_workers(self) -> None:
        if self.auth_worker is not None and self.auth_worker.isRunning():
            self.auth_worker.cancel(); self.auth_worker.wait(3000)
