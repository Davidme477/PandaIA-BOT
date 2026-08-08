from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError

PROJECT_DIR=Path(__file__).resolve().parents[1]; SITE=PROJECT_DIR/".venv"/"Lib"/"site-packages"
for path in (PROJECT_DIR,SITE):
    if str(path) not in sys.path: sys.path.insert(0,str(path))

from PySide6.QtWidgets import QApplication
from app.views.settings_view import SettingsView
from services.live_watchdog.alarm import AlertCycle
from services.live_watchdog.detector import ConsecutiveWarningDetector,classify_warning,normalize_detection_text
from services.live_watchdog.runtime import LiveWatchdog
from services.live_watchdog.telegram import TelegramClient,TelegramError,TelegramLocalStore,redact_secret

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

class Response:
    def __init__(self,value): self.value=value; self.status=200
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def read(self): return json.dumps(self.value).encode()

class FakeOpener:
    def __init__(self,values): self.values=list(values); self.requests=[]
    def __call__(self,request,timeout=0): self.requests.append(request); return Response(self.values.pop(0))

class LiveWatchdogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_valid_and_invalid_token(self):
        self.assertEqual(TelegramClient("fake",opener=FakeOpener([{"ok":True,"result":{"id":1}}])).validate()["id"],1)
        with self.assertRaisesRegex(TelegramError,"inválido"):
            TelegramClient("fake",opener=FakeOpener([{"ok":False,"error_code":401}])).validate()

    def test_private_chat_preferred_and_groups_ignored(self):
        updates=[{"update_id":1,"message":{"text":"hola","chat":{"id":9,"type":"group","title":"g"}}},
                 {"update_id":2,"message":{"text":"otro","chat":{"id":2,"type":"private","first_name":"Ana"}}},
                 {"update_id":3,"message":{"text":"/start","chat":{"id":3,"type":"private","first_name":"David"}}}]
        client=TelegramClient("fake",opener=FakeOpener([{"ok":True,"result":updates}]))
        self.assertEqual(client.detect_private_chat(),("3","David",4))

    def test_send_message_is_audible_and_has_ack_button(self):
        opener=FakeOpener([{"ok":True,"result":{}}]); TelegramClient("fake",opener=opener).send_message("1","alerta",alert_id="x")
        body=opener.requests[0].data.decode(); self.assertIn("disable_notification=false",body); self.assertIn("watchdog_ack",body)

    def test_send_photo_only_when_explicitly_called(self):
        opener=FakeOpener([{"ok":True,"result":{}}]); client=TelegramClient("fake",opener=opener)
        client.send_message("1","alerta"); self.assertEqual(len(opener.requests),1)
        opener.values.append({"ok":True,"result":{}}); client.send_photo("1",b"png","captura"); self.assertEqual(len(opener.requests),2)

    def test_redacts_token(self):
        token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd"
        self.assertNotIn(token,redact_secret(f"falló {token}",token))

    def test_atomic_store_and_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            store=TelegramLocalStore(Path(folder)/"telegram_local.json"); store.save({"bot_token":"x","chat_id":"1"})
            self.assertEqual(store.load()["chat_id"],"1"); self.assertFalse(list(Path(folder).glob("*.tmp"))); store.clear(); self.assertEqual(store.load(),{})

    def test_http_statuses_and_network(self):
        for status in (401,403,409,429):
            with self.assertRaises(TelegramError) as raised:
                TelegramClient("x",opener=FakeOpener([{"ok":False,"error_code":status,"parameters":{"retry_after":7}}])).validate()
            self.assertEqual(raised.exception.status,status)
        def offline(*_,**__): raise URLError("offline")
        with self.assertRaisesRegex(TelegramError,"Internet"): TelegramClient("x",opener=offline).validate()

    def test_warning_types_ocr_and_false_positives(self):
        self.assertEqual(classify_warning("Advertencia por inactividad").kind,"Advertencia de inactividad")
        self.assertEqual(classify_warning("Debe confirmar la validación").kind,"Validación")
        self.assertEqual(classify_warning("Advertencia: restricción").kind,"Restricción")
        self.assertIn("inactividad",normalize_detection_text("INACTIVlDAD"))
        for text in ("Live normal","actividad reciente","hola mundo"): self.assertIsNone(classify_warning(text))

    def test_high_priority_real_live_inactivity_phrase(self):
        match = classify_warning("Se ha detectado inactividad durante el LIVE")
        self.assertIsNotNone(match)
        self.assertEqual(match.kind, "Advertencia de inactividad")
        self.assertTrue(match.immediate)

    def test_high_priority_live_verification_phrase(self):
        match = classify_warning("Completa la verificación en LIVE Studio dentro de 5 minutos para continuar con el LIVE actual.")
        self.assertIsNotNone(match)
        self.assertEqual(match.kind, "Validación")
        self.assertTrue(match.immediate)

    def test_cancelled_live_inactivity_phrase(self):
        match = classify_warning("LIVE cancelado. Tu LIVE se canceló por inactividad.")
        self.assertIsNotNone(match)
        self.assertEqual(match.kind, "Advertencia de inactividad")

    def test_multiline_ocr_live_inactivity_phrase(self):
        match = classify_warning("Se ha detectado\ninactividad durante el LIVE.\nCompleta la verificación\ndentro de 5 minutos")
        self.assertIsNotNone(match)
        self.assertEqual(match.kind, "Advertencia de inactividad")

    def test_ocr_noise_variants_normalize(self):
        match = classify_warning("Se ha detectado inactividád duranre el LIV3")
        self.assertIsNotNone(match)
        self.assertEqual(match.kind, "Advertencia de inactividad")

    def test_false_positives_do_not_warn(self):
        for text in ("Actividad reciente", "Resultados del LIVE", "Información sobre el LIVE"):
            self.assertIsNone(classify_warning(text))

    def test_uia_safe_text_and_ocr_warning_can_combine(self):
        uia_text = "Información sobre el LIVE. Objetivo del LIVE"
        ocr_text = "Se ha detectado inactividad durante el LIVE"
        combined = "\n".join((uia_text, ocr_text))
        self.assertIsNotNone(classify_warning(combined))

    def test_uia_warning_classification_is_not_relying_on_ocr(self):
        match = classify_warning("Se ha detectado inactividad durante el LIVE")
        self.assertIsNotNone(match)
        self.assertTrue(match.immediate)
        self.assertEqual(classify_warning("Se ha detectado\ninactividad durante el LIVE").event_id, match.event_id)

    def test_same_warning_does_not_emit_a_new_event(self):
        cycle = AlertCycle()
        first = cycle.start("same-warning", 0)
        second = cycle.start("same-warning", 1)
        self.assertTrue(first)
        self.assertFalse(second)

    def test_two_reads_and_high_priority(self):
        detector=ConsecutiveWarningDetector(); self.assertIsNone(detector.inspect("advertencia inactividad"))
        self.assertIsNotNone(detector.inspect("advertencia inactividad")); self.assertIsNotNone(detector.inspect("Continuar en vivo"))

    def test_cycle_repeats_and_acknowledges(self):
        cycle=AlertCycle(); cycle.start("x",0)
        results=[cycle.due(t,60,240) for t in (0,60,120,180,242)]
        self.assertEqual(results,[(True,False)]*4+[(True,True)])
        self.assertEqual(cycle.due(300,60,240),(False,False))
        cycle.acknowledge(); self.assertFalse(cycle.due(300,60,240)[0])

    def test_disappearance_stops_after_two_reads(self):
        cycle=AlertCycle(); cycle.start("x",0); self.assertFalse(cycle.observe_missing()); self.assertTrue(cycle.observe_missing()); self.assertTrue(cycle.attended)

    def test_unexpected_disconnect_but_not_manual(self):
        alarms=[]; watchdog=LiveWatchdog({"enabled":True},alarm_callback=lambda:alarms.append(1)); watchdog.set_live_state(True); watchdog.set_live_state(False,manual=True); self.assertEqual(alarms,[])
        watchdog.set_live_state(True); watchdog.set_live_state(False,manual=False); self.assertEqual(alarms,[1]); watchdog.shutdown()

    def test_local_simulation_without_tiktok(self):
        alarms=[]; watchdog=LiveWatchdog({},alarm_callback=lambda:alarms.append(1)); watchdog.test_alarm(); self.assertEqual(alarms,[1]); watchdog.shutdown()

    def test_responsive_settings_view_and_hidden_token(self):
        view=SettingsView({}); self.assertEqual(view.token.echoMode(),view.token.EchoMode.Password)
        view.set_available_width(500); self.assertEqual(view.grid.getItemPosition(view.grid.indexOf(view.open_studio))[1],0)
        view.set_available_width(900); self.assertEqual(view.grid.getItemPosition(view.grid.indexOf(view.open_studio))[1],1); view.deleteLater()

    def test_private_files_are_ignored(self):
        import subprocess
        output=subprocess.check_output(["git","check-ignore","config/telegram_local.json"],cwd=PROJECT_DIR,text=True)
        self.assertIn("telegram_local.json",output)

if __name__=="__main__": unittest.main()
