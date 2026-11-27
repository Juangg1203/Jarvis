"""Ajustes guardados en tu computador (%LOCALAPPDATA%\\Jarvis\\ajustes.json)."""
import json
import os

from . import config

def _ARCHIVO():
    return config.CARPETA_DATOS / "ajustes.json"


POR_DEFECTO = {
    "proveedor": "gemini",      # quién conversa: gemini (gratis) | claude (de pago)
    "gemini_api_key": "",
    "anthropic_api_key": "",
    "voz_motor": "piper",       # piper (natural, sin internet) | edge (más natural, con internet) | windows
    "voz_edge": "es-CO-GonzaloNeural",
    "modo_conversacion": True,  # tras responder, sigue escuchando sin tener que decir "Jarvis"
    "gestos_al_iniciar": False,  # encender la cámara para los gestos al abrir Jarvis
    "solo_dueno": False,         # solo obedece órdenes de voz de tu voz o con tu cara frente a la cámara
    "avisos_seguridad": True,    # avisar de memorias USB nuevas y disco casi lleno
    "celular": False,            # app del celular por el wifi de casa
    "codigo_celular": "",        # código secreto que guarda el celular al escanear el QR
    "tema": "aurora",            # colores: aurora | oceano | esmeralda | atardecer
}


def cargar() -> dict:
    datos = dict(POR_DEFECTO)
    try:
        datos.update(json.loads(_ARCHIVO().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    # Una clave de Gemini (empieza por "AIza") pegada en el campo de Claude: se pasa a su sitio.
    if datos.get("anthropic_api_key", "").startswith("AIza") and not datos.get("gemini_api_key"):
        datos["gemini_api_key"], datos["anthropic_api_key"] = datos["anthropic_api_key"], ""
    return datos


def guardar(cambios: dict) -> dict:
    datos = cargar()
    datos.update({k: v for k, v in cambios.items() if k in POR_DEFECTO})
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    _ARCHIVO().write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return datos


def clave_gemini() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or cargar().get("gemini_api_key", "")


def clave_claude() -> str:
    return os.environ.get("ANTHROPIC_API_KEY") or cargar().get("anthropic_api_key", "")
