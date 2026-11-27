"""Conversación con Gemini usando respuestas simuladas (sin internet)."""
import io
import json

from jarvis import ajustes, gemini
from jarvis.comandos import Cerebro


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _sse(*trozos):
    return _Resp("".join("data: " + json.dumps(t) + "\r\n\r\n" for t in trozos).encode())


def _texto(t, fin=None):
    c = {"content": {"role": "model", "parts": [{"text": t}]}}
    if fin:
        c["finishReason"] = fin
    return {"candidates": [c]}


def test_clave_de_gemini_en_el_campo_de_claude_se_mueve():
    ajustes.guardar({"anthropic_api_key": "AIzaFalsa123"})
    a = ajustes.cargar()
    assert a["gemini_api_key"] == "AIzaFalsa123" and a["anthropic_api_key"] == ""
    assert ajustes.clave_gemini() == "AIzaFalsa123" and a["proveedor"] == "gemini"


def test_declaraciones_para_gemini():
    decl = gemini.declaraciones()[0]["functionDeclarations"]
    nombres = {d["name"] for d in decl}
    assert {"abrir", "volumen", "buscar_internet", "crear_recordatorio"} <= nombres
    assert "web_search" not in nombres
    assert all("eager_input_streaming" not in json.dumps(d) for d in decl)
    assert all("parameters" not in d or d["parameters"]["properties"] for d in decl)


def test_conversa_con_herramienta_y_voz(monkeypatch):
    ajustes.guardar({"gemini_api_key": "AIzaFalsa123"})
    c = Cerebro()
    conv = gemini.ConversadorGemini(c)
    assert conv.disponible()
    llamadas = []
    respuestas = [
        _sse({"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "volumen", "args": {"nivel": 30}}, "thoughtSignature": "abc"}]}}]}),
        _sse(_texto("[riendo] ¡Listo! Puse el volumen "), _texto("al treinta por ciento. ¿Algo más?", "STOP")),
    ]

    def peticion(metodo, cuerpo, modelo=None):
        llamadas.append(cuerpo)
        return respuestas.pop(0)

    monkeypatch.setattr(conv, "_peticion", peticion)
    monkeypatch.setattr(c, "_control", lambda o, t, s: None)
    ejecutadas = []
    monkeypatch.setattr(gemini.Conversador, "_ejecutar",
                        lambda self, n, e: ejecutadas.append((n, e)) or gemini.Respuesta("Volumen al 30 %."))
    frases, caras = [], []
    total = conv.responder("pon el volumen al 30", al_texto=lambda t: None, al_frase=frases.append,
                           al_expresion=caras.append, al_resultados=lambda r: None)
    assert ejecutadas == [("volumen", {"nivel": 30})]
    assert caras == ["riendo"] and frases[0].startswith("¡Listo!") and "treinta" in total
    # la segunda llamada devuelve la firma del modelo y el resultado de la herramienta
    segunda = llamadas[1]["contents"]
    assert segunda[1]["parts"][0]["thoughtSignature"] == "abc"
    assert segunda[2]["parts"][0]["functionResponse"]["response"]["resultado"] == "Volumen al 30 %."
    assert "Eres Jarvis" in llamadas[0]["systemInstruction"]["parts"][0]["text"]


def test_buscar_internet_desde_gemini(monkeypatch):
    conv = gemini.ConversadorGemini(Cerebro())
    monkeypatch.setattr(gemini.internet, "clima", lambda lugar, manana=False: f"clima {lugar} {manana}")
    assert conv._ejecutar("buscar_internet", {"tipo": "clima", "consulta": "Cali", "manana": True}).texto == "clima Cali True"


def test_error_de_cuota_es_amable(monkeypatch):
    import urllib.error
    conv = gemini.ConversadorGemini(Cerebro())
    ajustes.guardar({"gemini_api_key": "AIzaFalsa123"})

    def falla(*a, **k):
        raise urllib.error.HTTPError("u", 429, "quota", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(gemini.urllib.request, "urlopen", falla)
    try:
        conv._peticion("generateContent", {})
        assert False
    except gemini.ErrorGemini as e:
        assert "gratis" in e.mensaje
