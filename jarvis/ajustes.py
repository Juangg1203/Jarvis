"""Ajustes guardados en tu computador (%LOCALAPPDATA%\\Jarvis\\ajustes.json)."""
import json
import os

from . import config

def _ARCHIVO():
    return config.CARPETA_DATOS / "ajustes.json"


POR_DEFECTO = {
    "anthropic_api_key": "",
    "voz_motor": "piper",       # piper (natural, sin internet) | edge (más natural, con internet) | windows
    "voz_edge": "es-CO-GonzaloNeural",
    "modo_conversacion": True,  # tras responder, sigue escuchando sin tener que decir "Jarvis"
}


def cargar() -> dict:
    datos = dict(POR_DEFECTO)
    try:
        datos.update(json.loads(_ARCHIVO().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return datos


def guardar(cambios: dict) -> dict:
    datos = cargar()
    datos.update({k: v for k, v in cambios.items() if k in POR_DEFECTO})
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    _ARCHIVO().write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return datos


def clave_claude() -> str:
    return os.environ.get("ANTHROPIC_API_KEY") or cargar().get("anthropic_api_key", "")
