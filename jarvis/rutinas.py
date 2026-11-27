"""Rutinas: varias acciones con una sola frase («modo estudio», «buenos días»...). Funcionan sin internet.

Se guardan en %LOCALAPPDATA%\\Jarvis\\rutinas.json y puedes editarlas o pedirle a Jarvis que cree nuevas.
Cada paso es uno de:
  {"accion": "abrir", "objetivo": "spotify"}
  {"accion": "notificaciones", "activar": false}
  {"accion": "temporizador", "minutos": 25, "mensaje": "toca descansar"}
  {"accion": "decir", "texto": "..."}
  {"accion": "resumen_dia"}
"""
import datetime as dt
import json
import sys

from . import archivos, config, seguridad
from .texto import normalizar

def _ARCHIVO():
    return config.CARPETA_DATOS / "rutinas.json"


POR_DEFECTO = {
    "estudio": {
        "frase": "Modo estudio activado. Te abro Word, Chrome y Spotify, silencio las notificaciones y "
                 "te aviso en 25 minutos para que descanses.",
        "pasos": [
            {"accion": "notificaciones", "activar": False},
            {"accion": "abrir", "objetivo": "word"},
            {"accion": "abrir", "objetivo": "chrome"},
            {"accion": "abrir", "objetivo": "spotify"},
            {"accion": "temporizador", "minutos": 25, "mensaje": "llevas 25 minutos estudiando, tómate un descanso de cinco"},
        ],
    },
    "normal": {
        "frase": "Listo, volvemos a la normalidad. Las notificaciones están activadas otra vez.",
        "pasos": [{"accion": "notificaciones", "activar": True}],
    },
    "buenos dias": {
        "frase": "",
        "pasos": [{"accion": "resumen_dia"}],
    },
}


def silenciar_notificaciones(silenciar: bool) -> bool:
    """Activa o desactiva los avisos emergentes de las apps de Windows (el interruptor de Configuración)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        for ruta, valor in (
            (r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled"),
            (r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", "NOC_GLOBAL_SETTING_TOASTS_ENABLED"),
        ):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta) as k:
                winreg.SetValueEx(k, valor, 0, winreg.REG_DWORD, 0 if silenciar else 1)
        return True
    except OSError:
        return False


class Rutinas:
    def __init__(self):
        self.rutinas = self._cargar()

    def _cargar(self):
        try:
            datos = json.loads(_ARCHIVO().read_text(encoding="utf-8"))
            if isinstance(datos, dict) and datos:
                return datos
        except (OSError, ValueError):
            pass
        return json.loads(json.dumps(POR_DEFECTO))

    def _guardar(self):
        try:
            config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
            _ARCHIVO().write_text(json.dumps(self.rutinas, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def nombres(self):
        return list(self.rutinas)

    def buscar(self, texto):
        """Devuelve el nombre de la rutina mencionada en el texto, o None."""
        t = normalizar(texto)
        for nombre in sorted(self.rutinas, key=len, reverse=True):
            if normalizar(nombre) in t:
                return nombre
        return None

    def crear(self, nombre, abrir=(), minutos=0, silenciar=False, frase="", mensaje_temporizador=""):
        nombre = normalizar(nombre).removeprefix("modo ").removeprefix("rutina ").strip()
        if not nombre:
            raise ValueError("La rutina necesita un nombre.")
        pasos = []
        if silenciar:
            pasos.append({"accion": "notificaciones", "activar": False})
        pasos += [{"accion": "abrir", "objetivo": str(a)} for a in abrir if str(a).strip()]
        if minutos:
            pasos.append({"accion": "temporizador", "minutos": int(minutos),
                          "mensaje": mensaje_temporizador or f"terminó el tiempo del modo {nombre}"})
        self.rutinas[nombre] = {"frase": frase or f"Modo {nombre} activado.", "pasos": pasos}
        self._guardar()
        return nombre

    def borrar(self, nombre):
        if self.rutinas.pop(nombre, None) is not None:
            self._guardar()
            return True
        return False

    def ejecutar(self, nombre, agenda=None):
        """Ejecuta los pasos. Devuelve el texto que Jarvis dirá."""
        rutina = self.rutinas.get(nombre)
        if not rutina:
            return f"No tengo ninguna rutina llamada {nombre}."
        seguridad.registrar("rutina", nombre)
        partes, fallos = [rutina.get("frase", "")], []
        for paso in rutina.get("pasos", []):
            accion = paso.get("accion")
            try:
                if accion == "abrir":
                    app = archivos.buscar_app(paso.get("objetivo", ""))
                    if app:
                        archivos.abrir(app[1])
                    else:
                        fallos.append(paso.get("objetivo", ""))
                elif accion == "notificaciones":
                    silenciar_notificaciones(not paso.get("activar", True))
                elif accion == "temporizador" and agenda is not None:
                    agenda.agregar(dt.datetime.now() + dt.timedelta(minutes=float(paso.get("minutos", 25))),
                                   paso.get("mensaje", ""), "temporizador")
                elif accion == "decir":
                    partes.append(paso.get("texto", ""))
                elif accion == "resumen_dia":
                    partes.append(resumen_dia(agenda))
            except Exception as e:
                print(f"[rutina] paso {paso} falló: {e}")
                fallos.append(str(paso.get("objetivo", accion)))
        if fallos:
            partes.append("No encontré " + ", ".join(fallos) + " en tu computador.")
        return " ".join(p for p in partes if p).strip() or f"Rutina {nombre} lista."


def resumen_dia(agenda=None):
    ahora = dt.datetime.now()
    saludo = "Buenos días" if ahora.hour < 12 else "Buenas tardes" if ahora.hour < 19 else "Buenas noches"
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    texto = (f"{saludo}, {config.NOMBRE_USUARIO}. Hoy es {dias[ahora.weekday()]} {ahora.day} de "
             f"{meses[ahora.month - 1]} y son las {ahora:%H:%M}.")
    if agenda is not None:
        hoy = [x for x in agenda.pendientes() if dt.datetime.fromisoformat(x["cuando"]).date() == ahora.date()]
        if hoy:
            cosas = "; ".join(f"a las {dt.datetime.fromisoformat(x['cuando']):%H:%M} {x['mensaje'] or x['tipo']}" for x in hoy[:5])
            texto += f" Para hoy tienes: {cosas}."
        else:
            texto += " No tienes recordatorios para hoy."
    return texto
