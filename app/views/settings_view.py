from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox,QFormLayout,QFrame,QGridLayout,QHBoxLayout,QLabel,QLineEdit,
    QPushButton,QScrollArea,QSpinBox,QTextEdit,QVBoxLayout,QWidget)

class SettingsView(QScrollArea):
    settings_changed=Signal(object); save_token_requested=Signal(str); detect_chat_requested=Signal(); test_telegram_requested=Signal(); disconnect_telegram_requested=Signal()
    test_alarm_requested=Signal(); simulate_warning_requested=Signal(); stop_alarm_requested=Signal(); open_studio_requested=Signal()
    def __init__(self,settings):
        super().__init__(); self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame); self.setObjectName("contentScroll")
        content=QWidget(); content.setObjectName("mainContent"); root=QVBoxLayout(content); root.setContentsMargins(8,8,8,8); root.setSpacing(12)
        title=QLabel("Configuración"); title.setObjectName("pageTitle"); root.addWidget(title)
        subtitle=QLabel("Vigila avisos de TikTok sin pulsar ni controlar Live Studio."); subtitle.setObjectName("pageSubtitle"); subtitle.setWordWrap(True); root.addWidget(subtitle)
        self.banner=QLabel("TikTok requiere atención"); self.banner.setObjectName("warningBanner"); self.banner.setWordWrap(True); self.banner.hide(); root.addWidget(self.banner)
        panel,watch=self._panel("Vigilante del Live"); self.enabled=QCheckBox("Activar Vigilante del Live"); watch.addWidget(self.enabled)
        self.status=QLabel("Desactivado"); self.process=QLabel("—"); self.last_check=QLabel("—"); self.last_alert=QLabel("—")
        form=QFormLayout(); form.addRow("Estado",self.status); form.addRow("Proceso o ventana",self.process); form.addRow("Última comprobación",self.last_check); form.addRow("Última alerta",self.last_alert); watch.addLayout(form)
        self.process_hint=QLineEdit(str(settings.get("process_hint","TikTok Live Studio"))); watch.addWidget(QLabel("Nombre manual del proceso o ventana")); watch.addWidget(self.process_hint)
        self.test_alarm=QPushButton("Probar alarma local"); self.simulate=QPushButton("Simular advertencia"); self.stop_alarm=QPushButton("Detener alarma"); self.open_studio=QPushButton("Abrir TikTok Live Studio")
        box=QWidget(); self.grid=QGridLayout(box); watch.addWidget(box)
        for i,b in enumerate((self.test_alarm,self.simulate,self.stop_alarm,self.open_studio)): self.grid.addWidget(b,i//2,i%2)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(130); self.log.setPlaceholderText("Registro breve de alertas"); watch.addWidget(self.log); root.addWidget(panel)
        panel,tg=self._panel("Telegram — PandaIA Alertas"); self.token=QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password); self.token.setPlaceholderText("Token privado del bot")
        self.save_token=QPushButton("Guardar token"); self.detect_chat=QPushButton("Detectar mi chat"); self.telegram_status=QLabel("No configurado"); self.chat_name=QLabel("—")
        form=QFormLayout(); form.addRow("Token del bot",self.token); form.addRow("Estado Telegram",self.telegram_status); form.addRow("Chat conectado",self.chat_name); tg.addLayout(form)
        row=QHBoxLayout(); row.addWidget(self.save_token); row.addWidget(self.detect_chat); tg.addLayout(row); self.test_telegram=QPushButton("Enviar alerta de prueba"); self.disconnect_telegram=QPushButton("Desconectar Telegram"); row=QHBoxLayout(); row.addWidget(self.test_telegram); row.addWidget(self.disconnect_telegram); tg.addLayout(row)
        self.attach=QCheckBox("Adjuntar captura de advertencia"); self.interval=QSpinBox(); self.interval.setRange(15,300); self.interval.setSuffix(" s"); self.duration=QSpinBox(); self.duration.setRange(60,900); self.duration.setSuffix(" s"); form=QFormLayout(); form.addRow(self.attach); form.addRow("Intervalo de repetición",self.interval); form.addRow("Duración máxima",self.duration); tg.addLayout(form)
        note=QLabel("Para escuchar la alarma, activa sonido y vibración para el chat PandaIA Alertas y no lo silencies."); note.setObjectName("helperText"); note.setWordWrap(True); tg.addWidget(note); root.addWidget(panel); root.addStretch(); self.setWidget(content)
        self.enabled.setChecked(bool(settings.get("enabled",False))); self.attach.setChecked(bool(settings.get("attach_screenshot",False))); self.interval.setValue(int(settings.get("repeat_interval",60))); self.duration.setValue(int(settings.get("repeat_duration",240)))
        for signal in (self.enabled.toggled,self.process_hint.editingFinished,self.attach.toggled,self.interval.valueChanged,self.duration.valueChanged): signal.connect(self._emit)
        self.save_token.clicked.connect(lambda:self.save_token_requested.emit(self.token.text())); self.detect_chat.clicked.connect(self.detect_chat_requested); self.test_telegram.clicked.connect(self.test_telegram_requested); self.disconnect_telegram.clicked.connect(self.disconnect_telegram_requested)
        self.test_alarm.clicked.connect(self.test_alarm_requested); self.simulate.clicked.connect(self.simulate_warning_requested); self.stop_alarm.clicked.connect(self.stop_alarm_requested); self.open_studio.clicked.connect(self.open_studio_requested)
    @staticmethod
    def _panel(title):
        p=QFrame(); p.setObjectName("panel"); l=QVBoxLayout(p); h=QLabel(title); h.setObjectName("panelTitle"); l.addWidget(h); return p,l
    def values(self): return {"enabled":self.enabled.isChecked(),"process_hint":self.process_hint.text().strip() or "TikTok Live Studio","attach_screenshot":self.attach.isChecked(),"repeat_interval":self.interval.value(),"repeat_duration":self.duration.value()}
    def _emit(self,*_): self.settings_changed.emit(self.values())
    def apply_status(self,status,process,checked,alert): self.status.setText(status); self.process.setText(process or "—"); self.last_check.setText(checked or "—"); self.last_alert.setText(alert or self.last_alert.text())
    def set_banner(self,visible,text): self.banner.setText(text); self.banner.setVisible(visible)
    def add_alert(self,text): self.log.append(text)
    def set_telegram(self,status,name): self.telegram_status.setText(status); self.chat_name.setText(name or "—")
    def set_available_width(self,width):
        columns=2 if width>=760 else 1
        for i,b in enumerate((self.test_alarm,self.simulate,self.stop_alarm,self.open_studio)): self.grid.addWidget(b,i//columns,i%columns)
