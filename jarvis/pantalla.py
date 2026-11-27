"""Mirar la pantalla: Jarvis toma una captura SOLO cuando se lo pides y se la muestra a la IA que elegiste."""
import base64
import io
import json
import urllib.request

from . import ajustes, config

INSTRUCCION = ("Eres Jarvis, el asistente de {nombre}. Esta es una captura de su pantalla. Responde en español a lo "
               "que pregunta: «{pregunta}». Habla en dos a cuatro frases cortas para leer en voz alta, sin markdown, "
               "sin listas ni enlaces. Si se ve un error, di qué significa y cómo arreglarlo paso a paso, simple.")


def captura(max_lado=1600) -> bytes:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    img.thumbnail((max_lado, max_lado))
    salida = io.BytesIO()
    img.convert("RGB").save(salida, format="JPEG", quality=85)
    return salida.getvalue()


def _gemini(prompt, imagen):
    from .gemini import peticion
    cuerpo = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(imagen).decode()}}, {"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 800}}
    with peticion("generateContent", cuerpo) as r:
        datos = json.loads(r.read().decode("utf-8"))
    partes = datos["candidates"][0]["content"]["parts"]
    return " ".join(p.get("text", "") for p in partes if not p.get("thought")).strip()


def _claude(prompt, imagen):
    import anthropic
    cliente = anthropic.Anthropic(api_key=ajustes.clave_claude(), max_retries=1, timeout=90)
    r = cliente.beta.messages.create(
        model=config.MODELO_CLAUDE, max_tokens=1024, output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(imagen).decode()}},
            {"type": "text", "text": prompt}]}])
    if r.stop_reason == "refusal":
        return "Prefiero no comentar lo que hay en la pantalla."
    return " ".join(b.text for b in r.content if b.type == "text").strip()


def _ollama(prompt, imagen):
    from .ollama import BASE, modelos_instalados, tiene
    if not tiene(config.MODELO_OLLAMA_VISION, modelos_instalados()):
        return ("Para mirar la pantalla sin internet necesito el modelo de visión de Ollama. "
                "Ejecuta instalar_ollama.bat y elige instalarlo, o usa Gemini.")
    cuerpo = {"model": config.MODELO_OLLAMA_VISION, "stream": False, "messages": [
        {"role": "user", "content": prompt, "images": [base64.b64encode(imagen).decode()]}]}
    req = urllib.request.Request(BASE + "/api/chat", data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "").strip()


def proveedor_vision() -> str:
    """El que elegiste en Ajustes si tiene clave; si no, cualquiera que esté disponible."""
    elegido = ajustes.cargar().get("proveedor", "gemini")
    opciones = [elegido] + [p for p in ("gemini", "claude", "ollama") if p != elegido]
    for p in opciones:
        if (p == "gemini" and ajustes.clave_gemini()) or (p == "claude" and ajustes.clave_claude()) or p == "ollama":
            return p
    return ""


def preguntar(pregunta: str, imagen: bytes = None) -> str:
    imagen = imagen or captura()
    prompt = INSTRUCCION.format(nombre=config.NOMBRE_USUARIO, pregunta=pregunta or "¿qué hay en mi pantalla?")
    p = proveedor_vision()
    if p == "gemini":
        return _gemini(prompt, imagen)
    if p == "claude":
        return _claude(prompt, imagen)
    return _ollama(prompt, imagen)
