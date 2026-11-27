"""Seguridad activa: memorias USB nuevas, disco casi lleno y vigilancia con la cámara cuando no estás."""
import datetime
import os
import subprocess
import sys
import threading
import time

from . import config, seguridad


def carpeta_intrusos():
    return config.CARPETA_DATOS / "intrusos"


# ---------- memorias USB y disco ----------
def unidades_removibles() -> dict:
    """{punto_de_montaje: dispositivo} de las memorias USB conectadas."""
    try:
        import psutil
    except ImportError:
        return {}
    salida = {}
    for p in psutil.disk_partitions(all=False):
        if "removable" in p.opts or p.mountpoint.startswith(("/media/", "/run/media/")):
            salida[p.mountpoint] = p.device
    return salida


def discos_llenos(umbral=None) -> list:
    """[(unidad, porcentaje_usado, gb_libres)] de los discos fijos que pasan el umbral."""
    try:
        import psutil
    except ImportError:
        return []
    umbral = umbral or config.DISCO_LLENO_PORCENTAJE
    llenos = []
    for p in psutil.disk_partitions(all=False):
        if "removable" in p.opts or "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        if u.percent >= umbral:
            llenos.append((p.mountpoint.rstrip("\\/") or p.mountpoint, round(u.percent), round(u.free / 1e9, 1)))
    return llenos


def nombre_unidad(punto) -> str:
    """'E:\\' -> 'E'."""
    return punto.rstrip(":\\/") if len(punto) <= 3 else os.path.basename(punto.rstrip("/")) or punto


def analizar_usb(punto) -> str:
    """Revisa una memoria con Windows Defender (sin internet). Puede tardar unos minutos."""
    if sys.platform != "win32":
        return "El análisis con el antivirus solo funciona en Windows."
    mpcmd = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Windows Defender", "MpCmdRun.exe")
    if not os.path.exists(mpcmd):
        return "No encontré Windows Defender para revisar la memoria."
    seguridad.registrar("analizar_usb", punto)
    r = subprocess.run([mpcmd, "-Scan", "-ScanType", "3", "-File", punto, "-DisableRemediation"],
                       capture_output=True, text=True, timeout=1800,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode == 0:
        return f"Revisé la memoria {nombre_unidad(punto)} y está limpia."
    if r.returncode == 2:
        return (f"¡Cuidado! El antivirus encontró amenazas en la memoria {nombre_unidad(punto)}. "
                "No abras sus archivos; revisa Seguridad de Windows.")
    return "No pude terminar de revisar la memoria."


def liberar_espacio() -> str:
    if sys.platform == "win32":
        subprocess.Popen(["cleanmgr.exe"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Te abrí el Liberador de espacio. Marca lo que quieras borrar y dale Aceptar."
    return "El liberador de espacio solo está en Windows."


class Monitor:
    """Avisa al conectar una memoria USB y cuando un disco está casi lleno (una vez al día por disco)."""

    def __init__(self, al_alerta, cada=3.0, cada_disco=600.0):
        self.al_alerta = al_alerta  # fn(tipo, texto, dato)
        self.cada, self.cada_disco = cada, cada_disco
        self.activo = True
        self._avisados = {}  # unidad -> fecha del último aviso de disco lleno
        self._conocidas = None

    def iniciar(self):
        threading.Thread(target=self._bucle, daemon=True, name="monitor").start()

    def revisar_usb(self):
        actuales = unidades_removibles()
        if self._conocidas is not None and self.activo:
            for punto in sorted(set(actuales) - set(self._conocidas)):
                seguridad.registrar("usb_conectada", punto)
                self.al_alerta("usb", f"Se conectó una memoria USB, la unidad {nombre_unidad(punto)}. "
                                      "¿Quieres que la revise con el antivirus?", punto)
        self._conocidas = actuales

    def revisar_discos(self):
        hoy = datetime.date.today()
        for unidad, usado, libres in discos_llenos():
            if self._avisados.get(unidad) == hoy or not self.activo:
                continue
            self._avisados[unidad] = hoy
            self.al_alerta("disco", f"Tu disco {nombre_unidad(unidad)} está al {usado} por ciento: quedan {libres} "
                                    "gigas libres. Di «libera espacio» y te ayudo.", unidad)

    def _bucle(self):
        ultimo_disco = -1e9
        time.sleep(20)  # deja arrancar a Jarvis antes de dar avisos
        while True:
            try:
                self.revisar_usb()
                if time.monotonic() - ultimo_disco > self.cada_disco:
                    ultimo_disco = time.monotonic()
                    self.revisar_discos()
            except Exception as e:
                print(f"[monitor] {e}")
            time.sleep(self.cada)


# ---------- vigilancia con la cámara ----------
def segundos_sin_tocar() -> float:
    """Segundos desde que alguien tocó el teclado o el ratón (solo Windows)."""
    if sys.platform != "win32":
        return 0.0
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


class Vigilante:
    """Mientras no estás: si alguien aparece frente a la cámara o usa el PC, le toma una foto.

    Si reconoce tu cara, se apaga solo y te cuenta lo que pasó.
    """
    GRACIA = 20       # segundos para que te alejes después de activarla
    ENTRE_FOTOS = 30  # como mucho una foto cada 30 segundos

    def __init__(self, camara, identidad, al_intruso, al_volver):
        self.camara, self.identidad = camara, identidad
        self.al_intruso = al_intruso  # fn(ruta_foto)
        self.al_volver = al_volver    # fn(fotos)
        self.activa = False
        self.fotos: list[str] = []
        self._desde = 0.0
        self._ultima_foto = -1e9
        self._caras = None

    def activar(self):
        if self.activa:
            return
        from .identidad import Caras
        self._caras = Caras()
        self.activa, self.fotos = True, []
        self._desde = time.monotonic() + self.GRACIA
        self.camara.suscribir("vigilancia", self._mirar, cada=1.5)
        threading.Thread(target=self._vigilar_teclado, daemon=True, name="vigilancia-teclado").start()
        seguridad.registrar("vigilancia", "activada")

    def desactivar(self):
        if not self.activa:
            return []
        self.activa = False
        self.camara.desuscribir("vigilancia")
        seguridad.registrar("vigilancia", f"desactivada, {len(self.fotos)} fotos")
        return self.fotos

    def _mirar(self, cuadro):
        if not self.activa or time.monotonic() < self._desde:
            return
        caras = self._caras.huellas(cuadro)
        if not caras:
            return
        if self._caras.reconoce and self.identidad.conoce_cara:
            if any(self.identidad.es_mi_cara(h) for _, h in caras):
                fotos = self.desactivar()
                self.al_volver(fotos)
                return
        self._foto(cuadro)

    def _vigilar_teclado(self):
        while self.activa:
            time.sleep(1)
            if time.monotonic() >= self._desde and segundos_sin_tocar() < 1.5:
                cuadro = self.camara.ultimo_cuadro
                if cuadro is not None:
                    self._foto(cuadro.copy())

    def _foto(self, cuadro):
        if time.monotonic() - self._ultima_foto < self.ENTRE_FOTOS:
            return
        self._ultima_foto = time.monotonic()
        import cv2
        carpeta_intrusos().mkdir(parents=True, exist_ok=True)
        ruta = carpeta_intrusos() / f"{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.jpg"
        cv2.imwrite(str(ruta), cuadro)
        self.fotos.append(str(ruta))
        seguridad.registrar("intruso", str(ruta))
        self.al_intruso(str(ruta))
