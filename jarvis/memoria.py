"""Memoria de Jarvis: datos tuyos que le pides recordar y resúmenes de conversaciones anteriores.

Todo se guarda solo en tu computador, en %LOCALAPPDATA%\\Jarvis\\:
  memoria.json            datos y resúmenes
  conversaciones\\*.jsonl  lo que hablaron cada día (para poder buscarlo después)
"""
import datetime as dt
import json
import threading

from . import config
from .texto import normalizar

def _ARCHIVO():
    return config.CARPETA_DATOS / "memoria.json"

def _CARPETA_CHARLAS():
    return config.CARPETA_DATOS / "conversaciones"

MAX_DATOS = 200
MAX_RESUMENES_EN_CONTEXTO = 12


class Memoria:
    def __init__(self):
        self._lock = threading.Lock()
        datos = self._cargar()
        self.datos: list = datos.get("datos", [])
        self.resumenes: list = datos.get("resumenes", [])

    def _cargar(self):
        try:
            return json.loads(_ARCHIVO().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar(self):
        try:
            config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
            _ARCHIVO().write_text(json.dumps({"datos": self.datos, "resumenes": self.resumenes[-200:]},
                                           indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ---------- datos ----------
    def recordar(self, dato: str) -> bool:
        dato = dato.strip().rstrip(".")
        if not dato:
            return False
        with self._lock:
            if any(normalizar(d["texto"]) == normalizar(dato) for d in self.datos):
                return False
            self.datos.append({"texto": dato[:300], "fecha": dt.date.today().isoformat()})
            self.datos = self.datos[-MAX_DATOS:]
            self._guardar()
        return True

    def olvidar(self, texto) -> int:
        """Olvida los datos que contengan el texto (o el número 1..n). Devuelve cuántos quitó."""
        with self._lock:
            antes = len(self.datos)
            if isinstance(texto, int) or str(texto).strip().isdigit():
                n = int(texto)
                if 1 <= n <= len(self.datos):
                    self.datos.pop(n - 1)
            else:
                palabras = [p for p in normalizar(str(texto)).split() if len(p) > 2]
                if palabras:
                    self.datos = [d for d in self.datos
                                  if not all(p in normalizar(d["texto"]) for p in palabras)]
            self._guardar()
            return antes - len(self.datos)

    def olvidar_todo(self):
        with self._lock:
            self.datos, self.resumenes = [], []
            self._guardar()

    # ---------- conversaciones ----------
    def agregar_resumen(self, resumen: str):
        resumen = resumen.strip()
        if resumen:
            with self._lock:
                self.resumenes.append({"fecha": dt.datetime.now().isoformat(timespec="minutes"), "resumen": resumen})
                self._guardar()

    def anotar(self, quien: str, texto: str):
        """Guarda una línea de la conversación del día."""
        if not texto.strip():
            return
        try:
            _CARPETA_CHARLAS().mkdir(parents=True, exist_ok=True)
            archivo = _CARPETA_CHARLAS() / f"{dt.date.today().isoformat()}.jsonl"
            with open(archivo, "a", encoding="utf-8") as f:
                f.write(json.dumps({"hora": dt.datetime.now().isoformat(timespec="seconds"),
                                    "quien": quien, "texto": texto}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def buscar_conversaciones(self, consulta: str, limite=12) -> list:
        palabras = [p for p in normalizar(consulta).split() if len(p) > 2]
        if not palabras or not _CARPETA_CHARLAS().exists():
            return []
        encontrados = []
        for archivo in sorted(_CARPETA_CHARLAS().glob("*.jsonl"), reverse=True):
            try:
                lineas = archivo.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for linea in reversed(lineas):
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                if all(p in normalizar(d.get("texto", "")) for p in palabras):
                    encontrados.append(f"{d['hora'][:16].replace('T', ' ')} {d['quien']}: {d['texto']}")
                    if len(encontrados) >= limite:
                        return encontrados
        return encontrados

    # ---------- para Claude ----------
    def contexto(self) -> str:
        partes = []
        if self.datos:
            partes.append("Lo que sabes de él (porque te lo pidió recordar):\n" +
                          "\n".join(f"- {d['texto']}" for d in self.datos))
        if self.resumenes:
            partes.append("Resúmenes de conversaciones anteriores (de la más antigua a la más reciente):\n" +
                          "\n".join(f"- {r['fecha'][:10]}: {r['resumen']}" for r in self.resumenes[-MAX_RESUMENES_EN_CONTEXTO:]))
        return "\n\n".join(partes)
