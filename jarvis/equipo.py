"""Datos del computador para el panel de la esquina: batería, procesador, memoria, disco y más."""
import os
import platform
import socket
import time

_fijos = None


def _nombre_procesador():
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _windows():
    if os.name != "nt":
        return f"{platform.system()} {platform.release()}"
    version = platform.version().split(".")
    compilacion = int(version[2]) if len(version) > 2 and version[2].isdigit() else 0
    return "Windows 11" if compilacion >= 22000 else f"Windows {platform.release()}"


def _duracion(segundos):
    segundos = int(segundos)
    h, m = segundos // 3600, segundos % 3600 // 60
    if h >= 24:
        return f"{h // 24} d {h % 24} h"
    return f"{h} h {m} min" if h else f"{m} min"


def fijos():
    """Lo que no cambia (se calcula una sola vez)."""
    global _fijos
    if _fijos is None:
        import psutil
        _fijos = {"equipo": socket.gethostname(), "procesador": _nombre_procesador(),
                  "nucleos": psutil.cpu_count(logical=True) or 0, "sistema": _windows()}
    return _fijos


def ram_total_gb() -> float:
    """GB de RAM del equipo (16 si no se puede saber)."""
    try:
        import psutil
        return psutil.virtual_memory().total / 1024 ** 3
    except Exception:
        return 16.0


def poca_ram() -> bool:
    """Equipos de 8 GB o menos: hay que usar modelos más ligeros o todo se vuelve lento."""
    return ram_total_gb() < 10


def estado(en_linea=None, cerebro="") -> dict:
    import psutil
    f = fijos()
    gb = 1024 ** 3
    ram = psutil.virtual_memory()
    raiz = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    try:
        disco = psutil.disk_usage(raiz)
        d = {"libre": round(disco.free / gb), "total": round(disco.total / gb), "porcentaje": round(disco.percent)}
    except OSError:
        d = {"libre": 0, "total": 0, "porcentaje": 0}
    bateria = None
    try:
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if b is not None:
        minutos = ""
        if not b.power_plugged and b.secsleft not in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED) and b.secsleft > 0:
            minutos = _duracion(b.secsleft)
        bateria = {"porcentaje": round(b.percent), "cargando": bool(b.power_plugged), "minutos": minutos}
    datos = [["Procesador", f["procesador"]], ["Núcleos", str(f["nucleos"])], ["Sistema", f["sistema"]],
             ["Encendido", _duracion(time.time() - psutil.boot_time())]]
    if en_linea is not None:
        datos.append(["Internet", "Conectado" if en_linea else "Sin conexión"])
    return {"equipo": f["equipo"], "cpu": psutil.cpu_percent(interval=None), "cerebro": cerebro,
            "ram": {"usada": round(ram.used / gb, 1), "total": round(ram.total / gb), "porcentaje": round(ram.percent)},
            "disco": d, "bateria": bateria, "datos": datos}
