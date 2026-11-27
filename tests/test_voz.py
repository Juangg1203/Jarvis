"""El oído: termina la orden cuando dejas de hablar y usa Whisper si está."""
import sys
import threading
import time
import types

import numpy as np

from jarvis import config, voz


class _Rec:
    """Vosk falso que nunca decide solo que terminaste (como pasa con ruido de fondo)."""
    def __init__(self, *a):
        self.finales = 0

    def AcceptWaveform(self, b):
        return False

    def PartialResult(self):
        return '{"partial": "abre documento"}'

    def FinalResult(self):
        self.finales += 1
        return '{"text": "abre documento"}'

    def Result(self):
        return '{"text": ""}'

    def Reset(self):
        pass

    def SetSpkModel(self, m):
        pass


def _preparar(monkeypatch, tmp_path):
    flujo = {}

    class Stream:
        def __init__(self, **k):
            flujo["cb"] = k["callback"]

        def start(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, "vosk", types.SimpleNamespace(
        KaldiRecognizer=_Rec, Model=lambda p: None, SetLogLevel=lambda n: None, SpkModel=lambda p: None))
    monkeypatch.setattr(config, "CARPETA_MODELO", tmp_path)
    monkeypatch.setattr(config, "SILENCIO_FIN_SEG", 0.3)
    return flujo


def _bloque(amplitud):
    rng = np.random.default_rng(0)
    return (rng.standard_normal(1600) * amplitud).astype(np.int16).tobytes()


def _oir(flujo, oyente, voz_seg, silencio_seg):
    while "cb" not in flujo:
        time.sleep(0.01)
    oyente.escuchar_ahora()
    time.sleep(0.6)
    for amp, seg in ((3000, voz_seg), (30, silencio_seg)):
        fin = time.monotonic() + seg
        while time.monotonic() < fin:
            flujo["cb"](_bloque(amp), 1600, None, None)
            time.sleep(0.02)


def test_corta_cuando_dejas_de_hablar(monkeypatch, tmp_path):
    flujo = _preparar(monkeypatch, tmp_path)
    ordenes, estados = [], []
    hecho = threading.Event()
    o = voz.Oyente(estados.append, lambda t, h: (ordenes.append(t), hecho.set()), lambda: False)
    o.transcriptor = None
    threading.Thread(target=o._bucle, daemon=True).start()
    _oir(flujo, o, voz_seg=0.6, silencio_seg=1.0)
    assert hecho.wait(3) and ordenes == ["abre documento"]


def test_usa_whisper_si_esta(monkeypatch, tmp_path):
    flujo = _preparar(monkeypatch, tmp_path)
    ordenes = []
    hecho = threading.Event()
    o = voz.Oyente(lambda e: None, lambda t, h: (ordenes.append(t), hecho.set()), lambda: False)
    audios = []
    o.transcriptor = types.SimpleNamespace(disponible=True,
                                           transcribir=lambda a: audios.append(len(a)) or "Abre la carpeta de Documentos.")
    threading.Thread(target=o._bucle, daemon=True).start()
    _oir(flujo, o, voz_seg=0.6, silencio_seg=1.0)
    assert hecho.wait(3) and ordenes == ["abre la carpeta de documentos"] and audios[0] > 16000


def test_quitar_jarvis_del_texto_de_whisper():
    o = voz.Oyente(lambda e: None, lambda t, h: None, lambda: False)
    o.transcriptor = types.SimpleNamespace(disponible=True, transcribir=lambda a: "Jarvis, pon música de Shakira.")
    assert o._texto_final("yervis pon musica de shakira", b"x" * 40000, escuchando=False) == "pon musica de shakira"
    o.transcriptor = types.SimpleNamespace(disponible=True, transcribir=lambda a: "Garfield, pon música.")
    assert o._texto_final("jarvis pon musica", b"x" * 40000, escuchando=False) == "pon musica"
    assert o._texto_final("hola mama como estas", b"x" * 40000, escuchando=False) is None
