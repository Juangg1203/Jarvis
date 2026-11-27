"""Reglas de seguridad: rutas protegidas, registro de acciones y estado del antivirus."""
import datetime
import os
import subprocess
import sys
from pathlib import Path

from . import config

# Jarvis nunca borra nada dentro de estas carpetas.
_RUTAS_PROTEGIDAS = [
    os.environ.get("SystemRoot", r"C:\Windows"),
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    os.environ.get("ProgramData", r"C:\ProgramData"),
    os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")),
    os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
    str(config.RAIZ),  # el propio Jarvis
    "/bin", "/etc", "/usr", "/System",
]


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))).rstrip("\\/")


def puede_eliminar(ruta) -> tuple[bool, str]:
    """Devuelve (permitido, motivo)."""
    r = _norm(ruta)
    if not os.path.exists(r):
        return False, "ese archivo ya no existe"
    if r == _norm(Path.home()) or os.path.dirname(r) == r:
        return False, "no borro carpetas raíz ni tu carpeta personal"
    for prot in _RUTAS_PROTEGIDAS:
        if not prot:
            continue
        p = _norm(prot)
        if r == p or r.startswith(p + os.sep):
            return False, "está en una carpeta protegida del sistema"
    return True, ""


def registrar(accion: str, detalle: str = "") -> None:
    """Guarda cada acción en un registro local para que puedas auditarla."""
    try:
        config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
        with open(config.CARPETA_DATOS / "registro.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\t{accion}\t{detalle}\n")
    except OSError:
        pass


def estado_antivirus() -> str:
    """Consulta Windows Defender sin conexión a internet."""
    if sys.platform != "win32":
        return "La revisión de antivirus solo está disponible en Windows."
    cmd = ["powershell", "-NoProfile", "-Command",
           "$s=Get-MpComputerStatus; \"$($s.AntivirusEnabled)|$($s.RealTimeProtectionEnabled)|$($s.AntivirusSignatureAge)\""]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        av, rt, edad = out.split("|")
    except Exception:
        return "No pude consultar Windows Defender. Puede que otro antivirus esté activo."
    partes = [
        "El antivirus está activo" if av == "True" else "Atención: el antivirus está desactivado",
        "la protección en tiempo real está encendida" if rt == "True" else "la protección en tiempo real está apagada",
        f"y las firmas tienen {edad} días",
    ]
    return ", ".join(partes) + "."


def bloquear_equipo() -> bool:
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.user32.LockWorkStation())
    return False
