from __future__ import annotations

import time
import webbrowser

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget, QInputDialog, QMessageBox,
    QTableWidgetItem, QVBoxLayout, QWidget, QApplication,
)

from config.settings_store import read_settings
from services.overlay.events import OVERLAY_URL, post_overlay_event
from services.tiktok.gift_image_service import find_cached_gift, get_overlay_image_url
from services.tiktok.gift_image_service import GIFT_CACHE_DIR
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.oauth import SCOPES, SpotifyAuthError, SpotifyOAuthPKCE
from services.spotify.runtime import SpotifyRuntime
from services.spotify.models import RequestStatus
from app.widgets.responsive_grid import ResponsiveGrid
from services.overlay.cloudflare_tunnel import CloudflareTunnel, INSTALL_COMMAND
from services.tiktok.member_levels import DEFAULTS as MEMBER_DEFAULTS, MemberLevelHistory, MemberLevelManager


class SpotifyAuthWorker(QThread):
    authorized = Signal(object)
    failed = Signal(str)

    def __init__(self, client_id: str, *, show_dialog: bool = False) -> None:
        super().__init__()
        self.oauth = SpotifyOAuthPKCE(client_id)
        self.show_dialog = show_dialog

    def run(self) -> None:
        try:
            self.authorized.emit(self.oauth.authorize(show_dialog=self.show_dialog))
        except SpotifyAuthError as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        self.oauth.cancel()


class GiftsView(QScrollArea):
    settings_changed = Signal(object)

    def __init__(self, runtime: SpotifyRuntime, tunnel: CloudflareTunnel | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.tunnel = tunnel
        self.store = runtime.store
        self.auth_worker: SpotifyAuthWorker | None = None
        self._loading = True
        self.settings = dict(runtime.settings)
        self.member_history = MemberLevelHistory()
        self.member_manager = MemberLevelManager(self.settings, history=self.member_history)
        self.responsive_groups: list[ResponsiveGrid] = []
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
        self.tabs.addTab(self._member_levels_tab(), "Niveles de miembros")
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

    def responsive_group(self, widgets: tuple[QWidget, ...], *, wide: int, medium: int = 2) -> ResponsiveGrid:
        group = ResponsiveGrid(wide_columns=wide, medium_columns=medium, minimum_column_width=150, spacing=8)
        for widget in widgets: group.add_responsive_widget(widget)
        self.responsive_groups.append(group); return group

    def _animations_tab(self) -> QWidget:
        panel, layout = self.panel("Animaciones de regalos")
        self.animations_enabled = QCheckBox("Activar animaciones")
        self.animation_info = QLabel("Se reutiliza la animación Resplandor circular y las imágenes oficiales cacheadas de TikTok.")
        self.animation_info.setWordWrap(True); self.animation_info.setObjectName("helperText")
        self.gift_resource = QComboBox()
        for path in sorted(GIFT_CACHE_DIR.glob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                self.gift_resource.addItem(path.stem, path.name)
        self.add_assignment = QPushButton("Añadir asignación")
        self.add_assignment.setObjectName("voiceSecondaryButton")
        self.add_assignment.setEnabled(self.gift_resource.count() > 0)
        self.add_assignment.clicked.connect(self.add_selected_assignment)
        self.assignments = QTableWidget(0, 6); self.assignments.setHorizontalHeaderLabels(
            ["Regalo / ID", "Animación", "Estado", "Duración", "Sonido", "Acciones"]
        )
        self.assignments.horizontalHeader().setStretchLastSection(True)
        self.assignments.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.assignments.setMinimumHeight(220)
        test = QPushButton("Probar animación seleccionada"); test.setObjectName("primaryButton")
        test.clicked.connect(self.test_animation)
        layout.addWidget(self.animations_enabled); layout.addWidget(self.animation_info)
        layout.addWidget(self.responsive_group((self.gift_resource, self.add_assignment), wide=2))
        layout.addWidget(self.assignments); layout.addWidget(test)
        return self._tab_scroll(panel)

    def _spotify_tab(self) -> QWidget:
        panel, layout = self.panel("Solicitudes musicales Spotify Premium")
        self.client_id = QLineEdit(); self.client_id.setEchoMode(QLineEdit.EchoMode.Password)
        self.save_client = QPushButton("Guardar ID"); self.connect_spotify = QPushButton("Conectar Spotify")
        self.disconnect_spotify = QPushButton("Desconectar cuenta")
        for button in (self.save_client, self.connect_spotify): button.setObjectName("primaryButton")
        self.disconnect_spotify.setObjectName("voiceSecondaryButton")
        self.spotify_state = QLabel("No configurado"); self.spotify_state.setObjectName("connectionDisconnected")
        self.spotify_message = QLabel(""); self.spotify_message.setWordWrap(True); self.spotify_message.setObjectName("helperText")
        self.account_label = QLabel("Cuenta: —"); self.device_label = QLabel("Dispositivo activo: —")
        self.playback_label = QLabel("Reproduciendo ahora: —"); self.progress_label = QLabel("Progreso: —")
        layout.addWidget(self.responsive_group((QLabel("ID de cliente"), self.client_id, self.save_client), wide=3, medium=1))
        layout.addWidget(self.responsive_group((self.connect_spotify, self.disconnect_spotify), wide=2))
        layout.addWidget(self.spotify_state); layout.addWidget(self.spotify_message)
        for label in (self.account_label, self.device_label, self.playback_label, self.progress_label):
            label.setWordWrap(True); layout.addWidget(label)
        controls, controls_layout = self.panel("Controles de solicitudes")
        self.requests_enabled = QCheckBox("Activar solicitudes musicales")
        self.command = QLineEdit("a/"); self.command.setMaxLength(8)
        self.max_pending = QSpinBox(); self.max_pending.setRange(1, 100)
        self.max_user = QSpinBox(); self.max_user.setRange(1, 20)
        self.cooldown = QSpinBox(); self.cooldown.setRange(0, 3600); self.cooldown.setSuffix(" s")
        self.allow_explicit = QCheckBox("Permitir contenido explícito")
        self.block_duplicates = QCheckBox("Evitar canciones duplicadas")
        self.only_connected = QCheckBox("Aceptar solo con TikTok conectado")
        self.announce_tts = QCheckBox("Anunciar solicitudes mediante TTS")
        form = QGridLayout(); form.addWidget(self.requests_enabled, 0, 0, 1, 2)
        for row, (name, widget) in enumerate((("Comando musical", self.command), ("Máximo pendiente", self.max_pending),
                ("Máximo por usuario", self.max_user), ("Espera por usuario", self.cooldown)), start=1):
            form.addWidget(QLabel(name), row, 0); form.addWidget(widget, row, 1)
        for widget in (self.allow_explicit, self.block_duplicates, self.only_connected, self.announce_tts):
            form.addWidget(widget, form.rowCount(), 0, 1, 2)
        controls_layout.addLayout(form); layout.addWidget(controls)
        examples = QLabel("Ejemplos: a/Carlos Rivera Si me muero  ·  a/ Carlos Rivera Si me muero")
        examples.setObjectName("helperText"); examples.setWordWrap(True); controls_layout.addWidget(examples)
        queue_panel, queue_layout = self.panel("Cola musical interna")
        self.queue_table = QTableWidget(0, 6); self.queue_table.setHorizontalHeaderLabels(
            ["Posición", "Título", "Artista", "Usuario", "Duración", "Estado"])
        self.queue_table.horizontalHeader().setStretchLastSection(True); self.queue_table.setMinimumHeight(220)
        self.queue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.remove_request = QPushButton("Eliminar pendiente"); self.clear_queue = QPushButton("Limpiar solicitudes pendientes")
        self.clear_queue.setToolTip("Solo elimina solicitudes que todavía no fueron enviadas a Spotify.")
        self.skip_track = QPushButton("Saltar canción"); self.pause_track = QPushButton("Pausar"); self.resume_track = QPushButton("Reanudar")
        self.refresh_device = QPushButton("Actualizar dispositivo")
        for button in (self.remove_request, self.clear_queue, self.skip_track, self.pause_track, self.resume_track, self.refresh_device):
            button.setObjectName("voiceSecondaryButton")
        queue_layout.addWidget(self.queue_table)
        queue_layout.addWidget(self.responsive_group((self.remove_request, self.clear_queue, self.skip_track,
            self.pause_track, self.resume_track, self.refresh_device), wide=6, medium=3))
        test_label = QLabel("Prueba manual (no afecta TikTok, Ollama, TTS ni estadísticas)"); test_label.setObjectName("helperText")
        self.test_search = QLineEdit(); self.test_search.setPlaceholderText("Buscar artista y canción")
        self.add_test_request = QPushButton("Añadir solicitud de prueba"); self.add_test_request.setObjectName("primaryButton")
        queue_layout.addWidget(test_label); queue_layout.addWidget(self.responsive_group((self.test_search, self.add_test_request), wide=2))
        spotify_panel, spotify_layout = self.panel("Cola actual de Spotify")
        self.spotify_queue_table = QTableWidget(0, 5)
        self.spotify_queue_table.setHorizontalHeaderLabels(["Posición", "Título", "Artista", "Duración", "Origen"])
        self.spotify_queue_table.horizontalHeader().setStretchLastSection(True); self.spotify_queue_table.setMinimumHeight(220)
        self.spotify_queue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        spotify_layout.addWidget(self.spotify_queue_table)
        layout.addWidget(queue_panel); layout.addWidget(spotify_panel)
        return self._tab_scroll(panel)

    def _member_levels_tab(self) -> QWidget:
        panel, layout = self.panel("Ascensos y Top 3 de miembros")
        self.member_level_ups = QCheckBox("Activar ascensos")
        self.member_ranking = QCheckBox("Activar ranking")
        self.member_ranking_mode = QComboBox(); self.member_ranking_mode.addItems(["Siempre visible", "Periódicamente", "Oculto"])
        self.member_interval = QSpinBox(); self.member_interval.setRange(1, 120); self.member_interval.setSuffix(" min")
        self.member_rank_duration = QSpinBox(); self.member_rank_duration.setRange(3, 60); self.member_rank_duration.setSuffix(" s")
        self.member_position = QComboBox(); self.member_position.addItems(["Superior", "Inferior"])
        self.member_scale = QSpinBox(); self.member_scale.setRange(50, 150); self.member_scale.setSuffix(" %")
        self.member_sound = QCheckBox("Activar sonido del ascenso")
        self.member_volume = QSpinBox(); self.member_volume.setRange(0, 100); self.member_volume.setSuffix(" %")
        self.member_level_duration = QSpinBox(); self.member_level_duration.setRange(4, 30); self.member_level_duration.setSuffix(" s")
        self.member_text = QLineEdit(); self.member_text.setPlaceholderText("¡FELICIDADES, @{user}!")
        self.member_diagnostics = QCheckBox("Activar diagnóstico de insignias")
        form = QGridLayout()
        controls = (("Modo del ranking", self.member_ranking_mode), ("Intervalo", self.member_interval),
                    ("Duración Top 3", self.member_rank_duration), ("Posición", self.member_position),
                    ("Escala", self.member_scale), ("Duración ascenso", self.member_level_duration),
                    ("Volumen", self.member_volume), ("Texto", self.member_text))
        form.addWidget(self.member_level_ups, 0, 0); form.addWidget(self.member_ranking, 0, 1)
        for row, (name, widget) in enumerate(controls, 1): form.addWidget(QLabel(name), row, 0); form.addWidget(widget, row, 1)
        form.addWidget(self.member_sound, len(controls) + 1, 0, 1, 2); form.addWidget(self.member_diagnostics, len(controls) + 2, 0, 1, 2)
        layout.addLayout(form)
        self.member_summary = QLabel(); self.member_summary.setObjectName("helperText")
        self.member_table = QTableWidget(0, 3); self.member_table.setHorizontalHeaderLabels(["Miembro", "Nivel actual", "Club"])
        self.member_table.horizontalHeader().setStretchLastSection(True); self.member_table.setMinimumHeight(180)
        layout.addWidget(self.member_summary); layout.addWidget(self.member_table)
        self.test_level_up = QPushButton("Probar ascenso"); self.test_top3 = QPushButton("Probar Top 3")
        self.reset_members = QPushButton("Reiniciar historial")
        for button in (self.test_level_up, self.test_top3): button.setObjectName("primaryButton")
        self.reset_members.setObjectName("voiceSecondaryButton")
        layout.addWidget(self.responsive_group((self.test_level_up, self.test_top3, self.reset_members), wide=3, medium=1))
        return self._tab_scroll(panel)

    def _overlay_tab(self) -> QWidget:
        panel, layout = self.panel("Overlay para OBS / TikTok Live Studio")
        self.overlay_state = QLabel("Este overlay muestra exclusivamente regalos, ascensos y ranking de miembros de TikTok.")
        self.overlay_state.setWordWrap(True)
        self.overlay_url = QLineEdit(OVERLAY_URL); self.overlay_url.setReadOnly(True)
        copy = QPushButton("Copiar URL"); preview = QPushButton("Abrir vista previa")
        copy.setObjectName("primaryButton"); preview.setObjectName("voiceSecondaryButton")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(OVERLAY_URL))
        preview.clicked.connect(lambda: webbrowser.open(OVERLAY_URL))
        info = QLabel("Fuente de navegador: 1080×1920, fondo transparente. El audio permanece en Spotify/OBS.")
        info.setWordWrap(True); info.setObjectName("helperText")
        self.overlay_test_status = QLabel(""); self.overlay_test_status.setObjectName("helperText"); self.overlay_test_status.setWordWrap(True)
        layout.addWidget(self.overlay_state); layout.addWidget(self.overlay_url)
        layout.addWidget(self.responsive_group((copy, preview), wide=2)); layout.addWidget(info); layout.addWidget(self.overlay_test_status)
        secure_title = QLabel("Enlace directo para TikTok Live Studio"); secure_title.setObjectName("panelTitle")
        self.tunnel_state = QLabel("Túnel desconectado"); self.tunnel_state.setObjectName("statusRed")
        self.public_overlay_url = QLineEdit(); self.public_overlay_url.setReadOnly(True); self.public_overlay_url.setPlaceholderText("Crea un enlace HTTPS temporal")
        self.create_tunnel = QPushButton("Crear enlace HTTPS"); self.copy_tunnel = QPushButton("Copiar enlace"); self.stop_tunnel = QPushButton("Detener enlace")
        self.copy_tunnel.setEnabled(False); self.stop_tunnel.setEnabled(False)
        keep_open = QLabel("Mantén PandaIA abierta mientras utilizas este enlace"); keep_open.setObjectName("helperText"); keep_open.setWordWrap(True)
        layout.addWidget(secure_title); layout.addWidget(self.tunnel_state); layout.addWidget(self.public_overlay_url)
        layout.addWidget(self.responsive_group((self.create_tunnel, self.copy_tunnel, self.stop_tunnel), wide=3, medium=1)); layout.addWidget(keep_open)
        return self._tab_scroll(panel)

    def _connect(self) -> None:
        self.save_client.clicked.connect(self.save_client_id); self.connect_spotify.clicked.connect(self.handle_spotify_button)
        self.disconnect_spotify.clicked.connect(self.runtime.disconnect); self.refresh_device.clicked.connect(lambda: self.runtime.request_action("refresh"))
        self.clear_queue.clicked.connect(self.clear_pending); self.remove_request.clicked.connect(self.remove_selected)
        self.skip_track.clicked.connect(lambda: self._playback_action("next")); self.pause_track.clicked.connect(lambda: self._playback_action("pause"))
        self.resume_track.clicked.connect(lambda: self._playback_action("resume"))
        self.add_test_request.clicked.connect(lambda: self.runtime.submit_local_request(self.test_search.text()))
        self.runtime.state_changed.connect(self.set_spotify_state); self.runtime.account_changed.connect(self.set_account)
        self.runtime.queue_changed.connect(self.set_queue); self.runtime.playback_changed.connect(self.set_playback)
        self.runtime.spotify_queue_changed.connect(self.set_spotify_queue)
        for widget in (self.animations_enabled, self.requests_enabled, self.allow_explicit, self.block_duplicates,
                       self.only_connected, self.announce_tts, self.member_level_ups, self.member_ranking,
                       self.member_sound, self.member_diagnostics): widget.toggled.connect(self.save_settings)
        for widget in (self.command,): widget.editingFinished.connect(self.save_settings)
        for widget in (self.max_pending, self.max_user, self.cooldown): widget.valueChanged.connect(self.save_settings)
        for widget in (self.member_interval, self.member_rank_duration, self.member_scale, self.member_volume,
                       self.member_level_duration): widget.valueChanged.connect(self.save_settings)
        for widget in (self.member_ranking_mode, self.member_position): widget.currentTextChanged.connect(self.save_settings)
        self.member_text.editingFinished.connect(self.save_settings)
        self.test_level_up.clicked.connect(self.test_member_level_up); self.test_top3.clicked.connect(self.test_member_top3)
        self.reset_members.clicked.connect(self.reset_member_history)
        self.create_tunnel.clicked.connect(self.create_https_tunnel)
        self.copy_tunnel.clicked.connect(lambda: QApplication.clipboard().setText(self.public_overlay_url.text()))
        self.stop_tunnel.clicked.connect(lambda: self.tunnel.stop() if self.tunnel else None)
        if self.tunnel is not None: self.tunnel.state_changed.connect(self.apply_tunnel_state)

    def create_https_tunnel(self) -> None:
        if self.tunnel is not None: self.tunnel.start()

    def apply_tunnel_state(self, state: str, public_url: str, detail: str) -> None:
        self.tunnel_state.setText(state); active = state == "Enlace HTTPS activo"
        self.tunnel_state.setObjectName("statusGreen" if active else "statusRed"); self.tunnel_state.style().unpolish(self.tunnel_state); self.tunnel_state.style().polish(self.tunnel_state)
        if public_url: self.public_overlay_url.setText(public_url)
        elif state in {"Túnel desconectado", "Error"}: self.public_overlay_url.clear()
        self.copy_tunnel.setEnabled(active); self.stop_tunnel.setEnabled(active or state == "Creando enlace seguro")
        if detail: self.overlay_test_status.setText(detail)
        if state == "Componente no instalado": self.show_cloudflared_required()

    def show_cloudflared_required(self) -> None:
        dialog = QMessageBox(self); dialog.setWindowTitle("Se necesita Cloudflare Tunnel")
        dialog.setText("Se necesita Cloudflare Tunnel"); dialog.setInformativeText("Instálalo con Windows Package Manager y vuelve a crear el enlace.")
        copy_button = dialog.addButton("Copiar comando", QMessageBox.ButtonRole.ActionRole); dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() is copy_button: QApplication.clipboard().setText(INSTALL_COMMAND)

    def load_values(self) -> None:
        local = self.store.load(); self.client_id.setText(str(local.get("client_id", "")))
        if self.store.has_authorization():
            self.spotify_state.setText("Reconectando Spotify…")
            self.spotify_message.setText("Renovando la autorización guardada.")
            self.runtime.reconnect()
        values = self.settings
        self.animations_enabled.setChecked(bool(values.get("animations_enabled", True)))
        merged = {**MEMBER_DEFAULTS, **values}
        self.member_level_ups.setChecked(bool(merged["member_level_ups_enabled"])); self.member_ranking.setChecked(bool(merged["member_ranking_enabled"]))
        self.member_ranking_mode.setCurrentText(str(merged["member_ranking_mode"])); self.member_interval.setValue(max(1, int(merged["member_ranking_interval"]) // 60))
        self.member_rank_duration.setValue(int(merged["member_ranking_duration"])); self.member_position.setCurrentText(str(merged["member_ranking_position"]))
        self.member_scale.setValue(int(merged["member_ranking_scale"])); self.member_sound.setChecked(bool(merged["member_level_sound"]))
        self.member_volume.setValue(int(merged["member_level_volume"])); self.member_level_duration.setValue(int(merged["member_level_duration"]))
        self.member_text.setText(str(merged["member_level_text"])); self.member_diagnostics.setChecked(bool(merged["member_badge_diagnostics"]))
        self.requests_enabled.setChecked(bool(values.get("requests_enabled", False)))
        self.command.setText(str(values.get("command", "a/"))); self.max_pending.setValue(int(values.get("max_pending", 20)))
        self.max_user.setValue(int(values.get("max_per_user", 2))); self.cooldown.setValue(int(values.get("user_cooldown", 120)))
        self.allow_explicit.setChecked(bool(values.get("allow_explicit", False))); self.block_duplicates.setChecked(bool(values.get("block_duplicates", True)))
        self.only_connected.setChecked(bool(values.get("only_when_tiktok_connected", True))); self.announce_tts.setChecked(bool(values.get("announce_tts", False)))
        self.load_assignments()
        self.refresh_member_table()
        self.set_spotify_state(self.spotify_state.text(), self.spotify_message.text())

    def set_available_width(self, width: int) -> None:
        for group in self.responsive_groups: group.reflow(force=True, available_width=width)

    def values(self) -> dict[str, object]:
        return {"animations_enabled": self.animations_enabled.isChecked(), "requests_enabled": self.requests_enabled.isChecked(),
                "command": self.command.text().strip() or "a/", "max_pending": self.max_pending.value(), "max_per_user": self.max_user.value(),
                "user_cooldown": self.cooldown.value(), "allow_explicit": self.allow_explicit.isChecked(),
                "block_duplicates": self.block_duplicates.isChecked(), "only_when_tiktok_connected": self.only_connected.isChecked(),
                "announce_tts": self.announce_tts.isChecked(), "assignments": self.settings.get("assignments", {}),
                "member_level_ups_enabled": self.member_level_ups.isChecked(), "member_ranking_enabled": self.member_ranking.isChecked(),
                "member_ranking_mode": self.member_ranking_mode.currentText(), "member_ranking_interval": self.member_interval.value() * 60,
                "member_ranking_duration": self.member_rank_duration.value(), "member_ranking_position": self.member_position.currentText(),
                "member_ranking_scale": self.member_scale.value(), "member_level_sound": self.member_sound.isChecked(),
                "member_level_volume": self.member_volume.value(), "member_level_duration": self.member_level_duration.value(),
                "member_level_text": self.member_text.text().strip() or "¡FELICIDADES, @{user}!",
                "member_badge_diagnostics": self.member_diagnostics.isChecked()}

    def save_settings(self, *_args) -> None:
        if self._loading:
            return
        self.settings.update(self.values()); self.settings_changed.emit(self.values())
        self.member_manager.update_settings(self.values())

    def refresh_member_table(self) -> None:
        self.set_member_rows(self.member_history.top(100))

    def set_member_rows(self, rows) -> None:
        self.member_table.setRowCount(len(rows))
        for row, member in enumerate(rows):
            for column, value in enumerate((member.get("nickname") or member.get("unique_id", ""), member.get("current_level", 0), member.get("club_name", ""))):
                self.member_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.member_summary.setText(f"Miembros detectados: {len(rows)}")

    def test_member_level_up(self) -> None:
        user, accepted = QInputDialog.getText(self, "Probar ascenso", "Usuario simulado", text="PandaFan")
        if not accepted: return
        avatar, accepted = QInputDialog.getText(self, "Probar ascenso", "Avatar simulado (URL opcional)")
        if not accepted: return
        previous, accepted = QInputDialog.getInt(self, "Probar ascenso", "Nivel anterior", 31, 1, 100)
        if not accepted: return
        new, accepted = QInputDialog.getInt(self, "Probar ascenso", "Nivel nuevo", previous + 1, previous + 1, 100)
        if not accepted: return
        record = {"user_id": "simulado", "unique_id": user, "nickname": user, "avatar": avatar.strip(),
                  "previous_level": previous, "current_level": new}
        sent = post_overlay_event(self.member_manager.level_event(record, test=True))
        self.overlay_test_status.setText("Prueba de ascenso enviada al overlay." if sent else "El overlay rechazó la prueba de ascenso.")

    def test_member_top3(self) -> None:
        simulated = [{"user_id": f"test-{i}", "unique_id": name, "nickname": name, "avatar": "", "current_level": level, "first_seen": i}
                     for i, (name, level) in enumerate((("PandaOro", 32), ("PandaPlata", 28), ("PandaBronce", 24)), 1)]
        sent = post_overlay_event(self.member_manager.ranking_event(simulated, test=True))
        self.overlay_test_status.setText("Prueba de Top 3 enviada al overlay." if sent else "El overlay rechazó la prueba de Top 3.")

    def reset_member_history(self) -> None:
        answer = QMessageBox.question(self, "Reiniciar historial", "¿Eliminar el historial local de niveles de miembros?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.member_history.clear(); self.refresh_member_table(); self.overlay_test_status.setText("Historial de miembros reiniciado.")

    def save_client_id(self) -> None:
        self.store.save_client_id(self.client_id.text()); self.set_spotify_state("Desconectado", "ID guardado únicamente en este PC.")

    def start_authorization(self) -> None:
        if self.auth_worker is not None and self.auth_worker.isRunning():
            self.auth_worker.cancel(); return
        client_id = self.client_id.text().strip()
        if not client_id: self.set_spotify_state("No configurado", "Introduce el ID de cliente."); return
        self.store.save_client_id(client_id); self.set_spotify_state("Autorizando", "Completa la autorización en el navegador.")
        self.connect_spotify.setText("Cancelar autorización")
        changing_account = self.runtime.spotify_ready
        self.auth_worker = SpotifyAuthWorker(client_id, show_dialog=changing_account)
        self.auth_worker.authorized.connect(self.authorization_done)
        self.auth_worker.failed.connect(lambda message: self.set_spotify_state("Cuenta no autorizada", message))
        self.auth_worker.finished.connect(self.authorization_finished); self.auth_worker.start()

    def handle_spotify_button(self) -> None:
        if self.spotify_state.text() == "Spotify sin conexión" and self.store.has_authorization():
            self.runtime.reconnect()
            return
        self.start_authorization()

    def authorization_done(self, tokens: dict[str, object]) -> None:
        tokens = dict(tokens)
        granted = set(str(tokens.get("scope", SCOPES)).split())
        required = set(SCOPES.split())
        if not required.issubset(granted):
            self.store.clear_tokens()
            self.set_spotify_state(
                "Cuenta no autorizada", "Faltan permisos obligatorios. Vuelve a conectar Spotify."
            )
            return
        tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
        tokens["scopes"] = sorted(granted)
        self.store.save_authorization(tokens)
        self.runtime.reconnect()

    def authorization_finished(self) -> None:
        self.auth_worker = None
        self.set_spotify_state(self.spotify_state.text(), self.spotify_message.text())

    def set_spotify_state(self, state: str, message: str) -> None:
        self.spotify_state.setText(state); self.spotify_message.setText(message)
        authorized = state in {"Conectado", "Sin dispositivo activo"}
        connected = state == "Conectado"
        self.connect_spotify.setText(
            "Cambiar cuenta" if authorized or state == "Premium requerido" else "Reconectar"
            if state == "Cuenta no autorizada" else "Conectar Spotify"
        )
        if state == "Spotify sin conexión":
            self.connect_spotify.setText("Reintentar")
        self.connect_spotify.setEnabled(True)
        self.disconnect_spotify.setEnabled(state != "No configurado")
        self.refresh_device.setEnabled(authorized); self.add_test_request.setEnabled(authorized)
        for button in (self.skip_track, self.pause_track, self.resume_track): button.setEnabled(connected)

    def set_account(self, data: dict[str, object]) -> None:
        self.account_label.setText(f"Cuenta: {data.get('name', '—')}")
        device = data.get("device") if isinstance(data.get("device"), dict) else {}
        self.device_label.setText(f"Dispositivo activo: {device.get('name', '—')}")

    def set_playback(self, data: dict[str, object]) -> None:
        item = data.get("item") if isinstance(data.get("item"), dict) else {}
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
        self.playback_label.setText(f"Reproduciendo ahora: {item.get('name', '—')} · {artists}")
        self.progress_label.setText(f"Progreso: {self.duration(data.get('progress_ms', 0))} / {self.duration(item.get('duration_ms', 0))}")
        self.pause_track.setProperty("paused", not bool(data.get("is_playing", False)))
        self.pause_track.setEnabled(bool(data.get("is_playing", False)))
        self.resume_track.setEnabled(bool(data) and not bool(data.get("is_playing", False)))

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
        pending = any(request.status == RequestStatus.PENDING for request in items)
        self.remove_request.setEnabled(pending); self.clear_queue.setEnabled(pending)

    def set_spotify_queue(self, tracks) -> None:
        self.spotify_queue_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            position = "Actual" if track.get("current") else str(track.get("position", row))
            for column, value in enumerate((position, track.get("title", ""), track.get("artist", ""),
                                            self.duration(track.get("duration_ms", 0)), track.get("origin", ""))):
                self.spotify_queue_table.setItem(row, column, QTableWidgetItem(str(value)))

    def remove_selected(self) -> None:
        row = self.queue_table.currentRow()
        if row >= 0 and self.queue_table.item(row, 0):
            self.runtime.requests.remove_pending(str(self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)))
            self.set_queue(self.runtime.requests.snapshot())

    def clear_pending(self) -> None:
        self.runtime.requests.clear_pending(); self.set_queue(self.runtime.requests.snapshot())

    def _playback_action(self, action: str) -> None:
        self.runtime.request_action(action)

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
        cached_image = find_cached_gift(gift_id)
        if cached_image is None:
            self.overlay_test_status.setText("Prueba rechazada: no existe una imagen en cache/gifts para este regalo.")
            return
        sent = post_overlay_event({"type": "gift", "gift_id": gift_id, "gift_name": gift_id, "quantity": 1,
                                   "username": "Prueba local", "animation": "Resplandor circular", "test": True,
                                   "image_url": get_overlay_image_url(cached_image)})
        self.overlay_test_status.setText("Prueba enviada al overlay." if sent else "Prueba rechazada: el overlay no está disponible.")

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
