from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))

from config.settings_store import read_settings, write_settings_atomic
from services.live.comment_response_queue import CommentResponseQueue
from services.live.command_router import CommandRouter
from services.ollama.personalities import build_system_prompt, dashboard_defaults
from services.ollama.response_length import (
    RESPONSE_LENGTHS, clean_ollama_response, count_words, finalize_ollama_response,
    sentence_count,
)


VALID_RESPONSES = {
    "Corta": "Esta respuesta breve suena natural y funciona perfectamente durante nuestro live de hoy.",
    "Normal": "Esta respuesta contesta directamente con claridad para todo el público. También mantiene un tono natural durante nuestro live de hoy.",
    "Detallada": "Esta respuesta explica el punto principal con claridad para todos. También añade contexto útil sin repetir innecesariamente la pregunta original. Finalmente mantiene un tono natural, cercano y apropiado para nuestro live de hoy.",
}


class SequenceOllama:
    def __init__(self, responses): self.responses=list(responses); self.calls=[]
    def generate(self, **values):
        self.calls.append(values)
        response=self.responses.pop(0)
        if isinstance(response,Exception): raise response
        return response


class FakeVoice:
    def __init__(self): self.calls=[]
    def speak(self, **values): self.calls.append(values)


class ResponseLengthTests(unittest.TestCase):
    def test_each_level_respects_word_and_sentence_limits(self):
        for level, text in VALID_RESPONSES.items():
            result=finalize_ollama_response(text,level); profile=RESPONSE_LENGTHS[level]
            self.assertGreaterEqual(count_words(result),profile.min_words)
            self.assertLessEqual(count_words(result),profile.max_words)
            self.assertLessEqual(sentence_count(result),profile.max_sentences)

    def test_prompt_contains_exact_selected_limits_and_rules(self):
        for level,profile in RESPONSE_LENGTHS.items():
            prompt=build_system_prompt({"response_length":level,"language":"Español"})
            self.assertIn(f"entre {profile.min_words} y {profile.max_words} palabras",prompt)
            self.assertIn(f"máximo de {profile.max_sentences}",prompt)
            for rule in ("no repitas la pregunta","No uses Markdown","te presentes como una IA"):
                self.assertIn(rule,prompt)

    def test_markdown_and_repeated_whitespace_are_removed(self):
        source="## Título\n- **Esta respuesta**   es `clara` y natural para todo nuestro público durante el live de hoy."
        clean=clean_ollama_response(source)
        for marker in ("#","**","`","\n"): self.assertNotIn(marker,clean)
        self.assertNotIn("  ",clean)

    def test_slight_excess_trims_only_at_complete_sentence(self):
        source="Esta primera frase es completa, clara y natural para todos. Esta segunda sobra totalmente."
        result=finalize_ollama_response(source,"Corta")
        self.assertEqual(result,"Esta primera frase es completa, clara y natural para todos.")
        self.assertTrue(result.endswith(".")); self.assertNotIn("sobra",result)

    def test_large_excess_reformulates_once_without_cutting_words(self):
        calls=[]
        def reformulate(original,profile): calls.append((original,profile)); return VALID_RESPONSES["Corta"]
        result=finalize_ollama_response(" ".join(["palabra"]*50),"Corta",reformulate=reformulate)
        self.assertEqual(result,VALID_RESPONSES["Corta"]); self.assertEqual(len(calls),1)
        self.assertTrue(result.endswith(".")); self.assertNotIn(" palab",result[-6:])

    def test_failed_reformulation_uses_safe_complete_response(self):
        result=finalize_ollama_response(" ".join(["larga"]*60),"Corta",
                                        reformulate=lambda *_: (_ for _ in ()).throw(RuntimeError("falló")))
        self.assertLessEqual(count_words(result),15); self.assertTrue(result.endswith("?"))

    def test_manual_command_reaches_ollama_and_clean_tts(self):
        ollama=SequenceOllama([f"**{VALID_RESPONSES['Corta']}**"]); voice=FakeVoice()
        queue=CommentResponseQueue(dashboard_settings={"model":"m","respond_comments":True,"command_only_mode":True,
            "chat_command":"/","response_length":"Corta","use_memory":False},tts_settings={"engine":"fake","voice":"v"},
            ollama=ollama,voice_manager=voice)
        self.assertTrue(queue.enqueue_comment("Ana","/ hola"))
        deadline=time.time()+1
        while not voice.calls and time.time()<deadline: time.sleep(.01)
        queue.stop(); self.assertEqual(len(ollama.calls),1)
        self.assertEqual(voice.calls[0]["text"],VALID_RESPONSES["Corta"])

    def test_music_route_never_enters_conversation_queue(self):
        self.assertEqual(CommandRouter().route("a/ canción bonita").kind,"music")
        ollama=SequenceOllama([VALID_RESPONSES["Corta"]]); queue=CommentResponseQueue(
            dashboard_settings={"respond_comments":True,"command_only_mode":True},tts_settings={},ollama=ollama,voice_manager=FakeVoice())
        self.assertFalse(queue.enqueue_comment("Ana","a/ canción bonita")); time.sleep(.03); queue.stop()
        self.assertEqual(ollama.calls,[])

    def test_ollama_error_does_not_stop_next_queue_response(self):
        ollama=SequenceOllama([RuntimeError("sin Ollama"),VALID_RESPONSES["Corta"]]); voice=FakeVoice()
        queue=CommentResponseQueue(dashboard_settings={"model":"m","respond_comments":True,"command_only_mode":False,
            "automatic_responses":True,"response_length":"Corta"},tts_settings={"engine":"fake"},ollama=ollama,voice_manager=voice)
        queue.enqueue_comment("Ana","primero"); queue.enqueue_comment("Bea","segundo")
        deadline=time.time()+1
        while not voice.calls and time.time()<deadline: time.sleep(.01)
        queue.stop(); self.assertEqual(len(ollama.calls),2); self.assertEqual(len(voice.calls),1)

    def test_default_and_persistence_preserve_existing_selection(self):
        self.assertEqual(dashboard_defaults({})["response_length"],"Corta")
        self.assertEqual(dashboard_defaults({"response_length":"Detallada"})["response_length"],"Detallada")
        with TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"; data={"dashboard":{"response_length":"Normal"},"private":"intacto"}
            write_settings_atomic(path,data); self.assertEqual(read_settings(path),data)


if __name__=="__main__": unittest.main()
