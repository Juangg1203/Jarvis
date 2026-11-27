"""Control del PC: volumen, brillo, wifi, batería, apagar/reiniciar y cerrar programas. Sin internet.

Las acciones delicadas (apagar, reiniciar, suspender, forzar el cierre de programas) las pide confirmar
el cerebro de Jarvis antes de llamar a estas funciones.
"""
import csv
import io
import json
import os
import subprocess
import sys

from . import config
from .texto import normalizar

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ES_WINDOWS = sys.platform == "win32"

# Nombres que dices -> proceso de Windows
PROCESOS = {
    "chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe", "navegador": "msedge.exe",
    "firefox": "firefox.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE", "powerpoint": "POWERPNT.EXE",
    "spotify": "Spotify.exe", "bloc de notas": "notepad.exe", "notas": "notepad.exe", "calculadora": "CalculatorApp.exe",
    "visual studio code": "Code.exe", "vs code": "Code.exe", "codigo": "Code.exe", "discord": "Discord.exe",
    "steam": "steam.exe", "whatsapp": "WhatsApp.exe", "teams": "ms-teams.exe", "zoom": "Zoom.exe",
    "paint": "mspaint.exe", "explorador": "explorer.exe", "outlook": "OUTLOOK.EXE", "obs": "obs64.exe",
}
# Jarvis nunca cierra estos procesos (el sistema o él mismo).
PROTEGIDOS = {"system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
              "svchost.exe", "dwm.exe", "fontdrvhost.exe", "msmpeng.exe", "python.exe", "pythonw.exe",
              "conhost.exe", "registry", "memory compression", "securityhealthservice.exe"}


def _ps(comando, timeout=15):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True,
                       timeout=timeout, creationflags=_SIN_VENTANA)
    return r.returncode, (r.stdout or "").strip()


def _cmd(args, timeout=15):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_SIN_VENTANA,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip() + (r.stderr or "").strip()


# ---------- volumen ----------
def _volumen_pycaw():
    from pycaw.pycaw import AudioUtilities
    altavoz = AudioUtilities.GetSpeakers()
    if hasattr(altavoz, "EndpointVolume"):  # pycaw 2024+
        return altavoz.EndpointVolume
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    interfaz = altavoz.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interfaz, POINTER(IAudioEndpointVolume))


def _teclas_volumen(tecla, veces):
    import ctypes
    for _ in range(veces):
        ctypes.windll.user32.keybd_event(tecla, 0, 0, 0)
        ctypes.windll.user32.keybd_event(tecla, 0, 2, 0)


def volumen(nivel=None, cambio=None, silenciar=None) -> str:
    """nivel 0-100, cambio +/- puntos, silenciar True/False. Devuelve frase para decir."""
    if not ES_WINDOWS:
        return "El control de volumen solo funciona en Windows."
    try:
        v = _volumen_pycaw()
        if silenciar is not None:
            v.SetMute(1 if silenciar else 0, None)
            return "Sonido silenciado." if silenciar else "Sonido activado."
        actual = round(v.GetMasterVolumeLevelScalar() * 100)
        nuevo = nivel if nivel is not None else actual + (cambio or 0)
        nuevo = max(0, min(100, int(nuevo)))
        v.SetMute(0, None)
        v.SetMasterVolumeLevelScalar(nuevo / 100, None)
        return f"Volumen al {nuevo} por ciento."
    except Exception:
        pass
    # Respaldo: teclas multimedia (cada pulsación son 2 puntos)
    if silenciar is not None:
        _teclas_volumen(0xAD, 1)
        return "Listo, cambié el silencio."
    if nivel is not None:
        _teclas_volumen(0xAE, 50)
        _teclas_volumen(0xAF, max(0, min(100, int(nivel))) // 2)
        return f"Volumen al {nivel} por ciento."
    _teclas_volumen(0xAF if (cambio or 0) > 0 else 0xAE, max(1, abs(cambio or 10) // 2))
    return "Subí el volumen." if (cambio or 0) > 0 else "Bajé el volumen."


# ---------- brillo ----------
def brillo(nivel=None, cambio=None) -> str:
    if not ES_WINDOWS:
        return "El control de brillo solo funciona en Windows."
    try:
        _, salida = _ps("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
        actual = int(salida.splitlines()[0])
    except Exception:
        return "No puedo cambiar el brillo de esta pantalla. Suele funcionar solo en la pantalla del portátil."
    nuevo = nivel if nivel is not None else actual + (cambio or 0)
    nuevo = max(0, min(100, int(nuevo)))
    codigo, _ = _ps("Invoke-CimMethod -InputObject (Get-CimInstance -Namespace root/WMI -ClassName "
                    f"WmiMonitorBrightnessMethods) -MethodName WmiSetBrightness -Arguments @{{Timeout=0;Brightness={nuevo}}}")
    return f"Brillo al {nuevo} por ciento." if codigo == 0 else "No pude cambiar el brillo."


# ---------- wifi ----------
def _archivo_wifi():
    return config.CARPETA_DATOS / "ultima_wifi.json"


def wifi_estado():
    """Devuelve (conectado, nombre_red)."""
    if not ES_WINDOWS:
        return False, ""
    _, salida = _cmd(["netsh", "wlan", "show", "interfaces"])
    conectado, red = False, ""
    for linea in salida.splitlines():
        clave, _, valor = linea.partition(":")
        clave, valor = normalizar(clave), valor.strip()
        if clave in ("state", "estado") and normalizar(valor) in ("connected", "conectado"):
            conectado = True
        if clave == "ssid":
            red = valor
    return conectado, red


def wifi(encender: bool) -> str:
    if not ES_WINDOWS:
        return "El control del wifi solo funciona en Windows."
    if not encender:
        conectado, red = wifi_estado()
        if not conectado:
            return "El wifi ya estaba desconectado."
        try:
            config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
            _archivo_wifi().write_text(json.dumps({"red": red}), encoding="utf-8")
        except OSError:
            pass
        codigo, _ = _cmd(["netsh", "wlan", "disconnect"])
        return f"Me desconecté de {red}. Ojo: sin internet no puedo conversar con Claude." if codigo == 0 \
            else "No pude desconectar el wifi."
    conectado, red = wifi_estado()
    if conectado:
        return f"Ya estás conectado a {red}."
    try:
        red = json.loads(_archivo_wifi().read_text(encoding="utf-8"))["red"]
    except (OSError, ValueError, KeyError):
        red = ""
    if not red:
        return "No sé a qué red conectarme. Conéctate una vez desde Windows y luego te ayudo."
    codigo, _ = _cmd(["netsh", "wlan", "connect", f"name={red}"])
    return f"Conectando a {red}." if codigo == 0 else f"No pude conectarme a {red}."


# ---------- batería ----------
def bateria() -> str:
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if b is None:
        return "No encuentro la batería de este equipo."
    texto = f"La batería está al {round(b.percent)} por ciento"
    if b.power_plugged:
        return texto + " y el cargador está conectado."
    if b.secsleft and b.secsleft > 0:
        horas, minutos = divmod(b.secsleft // 60, 60)
        return texto + (f", te quedan unas {horas} horas y {minutos} minutos." if horas else f", te quedan unos {minutos} minutos.")
    return texto + "."


# ---------- energía ----------
def apagar(reiniciar=False, segundos=30) -> str:
    if not ES_WINDOWS:
        return "Eso solo funciona en Windows."
    accion = "/r" if reiniciar else "/s"
    codigo, _ = _cmd(["shutdown", accion, "/t", str(segundos), "/c", "Jarvis: apagado pedido por voz"])
    if codigo != 0:
        return "Windows no me dejó hacerlo."
    verbo = "reinicia" if reiniciar else "apaga"
    return f"El computador se {verbo} en {segundos} segundos. Di «cancela el apagado» si cambias de idea."


def cancelar_apagado() -> str:
    if not ES_WINDOWS:
        return "Eso solo funciona en Windows."
    codigo, _ = _cmd(["shutdown", "/a"])
    return "Cancelado, el computador sigue encendido." if codigo == 0 else "No había ningún apagado programado."


def suspender() -> str:
    if not ES_WINDOWS:
        return "Eso solo funciona en Windows."
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=_SIN_VENTANA)
    return "Suspendiendo el computador."


# ---------- programas ----------
def nombre_proceso(nombre: str) -> str:
    n = normalizar(nombre)
    if n in PROCESOS:
        return PROCESOS[n]
    return n.replace(" ", "") + ("" if n.endswith(".exe") else ".exe")


def buscar_procesos(nombre: str) -> list:
    """Procesos en ejecución que coinciden con el nombre. Devuelve nombres .exe únicos."""
    objetivo = normalizar(nombre_proceso(nombre))
    base = objetivo.removesuffix(".exe")
    try:
        import psutil
        vistos = set()
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "")
            nn = normalizar(n)
            if nn in PROTEGIDOS:
                continue
            if nn == objetivo or (len(base) >= 3 and base in nn):
                vistos.add(n)
        return sorted(vistos)
    except Exception:
        return []


def cerrar(proceso: str, forzar=False) -> bool:
    if not ES_WINDOWS or normalizar(proceso) in PROTEGIDOS:
        return False
    args = ["taskkill", "/im", proceso, "/t"] + (["/f"] if forzar else [])
    codigo, _ = _cmd(args)
    return codigo == 0


def colgados() -> list:
    """Programas que Windows marca como «No responde»."""
    if not ES_WINDOWS:
        return []
    _, salida = _cmd(["tasklist", "/fi", "STATUS eq NOT RESPONDING", "/fo", "csv", "/nh"])
    nombres = set()
    for fila in csv.reader(io.StringIO(salida)):
        if fila and fila[0].lower().endswith(".exe") and normalizar(fila[0]) not in PROTEGIDOS:
            nombres.add(fila[0])
    return sorted(nombres)


def cerrar_colgados(nombres) -> int:
    return sum(1 for n in nombres if cerrar(n, forzar=True))


def es_windows():
    return ES_WINDOWS and os.name == "nt"
