"""El cerebro de Jarvis: entiende la orden en español y la ejecuta.

Todo funciona sin internet. Las acciones peligrosas (eliminar) siempre piden confirmación
y mandan a la Papelera, nunca borran para siempre.
"""
import datetime
import os
import re
from dataclasses import dataclass, field

from . import archivos, config, seguridad
from .texto import extraer_numero, normalizar


@dataclass
class Respuesta:
    texto: str
    expresion: str = "normal"  # una de las 9 expresiones del avatar
    resultados: list = field(default_factory=list)
    dormir: bool = False


_SI = {"si", "claro", "confirmo", "dale", "hazlo", "adelante", "correcto", "si hazlo", "si borralo", "si eliminalo"}
_NO = {"no", "cancela", "cancelar", "mejor no", "detente", "olvidalo"}

_ARTICULOS = r"(?:(?:el|la|los|las|un|una|mi|mis)\s+)?"
_TIPO = r"(?:(?:archivo|archivos|documento|documentos|carpeta|carpetas|foto|fotos|programa|aplicacion|app)\s+)?"
_LLAMADO = r"(?:(?:llamado|llamada|que se llama|de nombre|con nombre|sobre|de)\s+)?"

_RE_BUSCAR = re.compile(r"^(?:busca|buscar|buscame|encuentra|encuentrame|localiza)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")
_RE_ABRIR = re.compile(r"^(?:abre|abrir|abreme|ejecuta|ejecutar|inicia|iniciar|lanza|pon)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")
_RE_BORRAR = re.compile(r"^(?:elimina|eliminar|eliminame|borra|borrar|borrame|quita)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")


class Cerebro:
    def __init__(self):
        self.ultimos_resultados: list[str] = []
        self.pendiente_borrar: str | None = None

    # ---------- punto de entrada ----------
    def procesar(self, texto: str) -> Respuesta:
        t = normalizar(texto)
        if t.split(" ")[0] in config.VARIANTES_ACTIVACION:  # "Jarvis, abre..." escrito a mano
            t = t.split(" ", 1)[1] if " " in t else ""
        if not t:
            return Respuesta("No escuché nada.", "pensando")
        seguridad.registrar("orden", t)

        if self.pendiente_borrar:
            return self._confirmar_borrado(t)

        if t in {"hola", "hola jarvis", "buenas", "buenos dias", "buenas tardes", "buenas noches"}:
            return Respuesta(f"Hola, {config.NOMBRE_USUARIO}. ¿En qué te ayudo?", "riendo")
        if "que hora" in t:
            return Respuesta(f"Son las {datetime.datetime.now():%H:%M}.", "normal")
        if "que dia" in t or "fecha" in t:
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                     "septiembre", "octubre", "noviembre", "diciembre"]
            hoy = datetime.date.today()
            return Respuesta(f"Hoy es {hoy.day} de {meses[hoy.month - 1]} de {hoy.year}.", "normal")
        if t in {"gracias", "muchas gracias", "gracias jarvis"}:
            return Respuesta("Para eso estoy.", "guino")
        if t in {"duerme", "a dormir", "descansa", "dormir", "silencio"}:
            return Respuesta("Me voy a dormir. Di mi nombre cuando me necesites.", "dormido", dormir=True)
        if re.search(r"\b(seguridad|antivirus|defender)\b", t):
            estado = seguridad.estado_antivirus()
            return Respuesta(estado, "preocupado" if "Atención" in estado or "No pude" in estado else "guino")
        if re.match(r"^(bloquea|bloquear)\b", t):
            ok = seguridad.bloquear_equipo()
            seguridad.registrar("bloquear_equipo", str(ok))
            return Respuesta("Equipo bloqueado." if ok else "No pude bloquear el equipo.", "normal" if ok else "triste")
        if t in {"ayuda", "que puedes hacer", "que sabes hacer"}:
            return Respuesta("Puedo buscar archivos, abrir archivos y aplicaciones, mandar archivos a la papelera, "
                             "decirte la hora, revisar el antivirus y bloquear el equipo.", "riendo")

        if m := _RE_BUSCAR.match(t):
            return self._buscar(m.group(1))
        if m := _RE_ABRIR.match(t):
            return self._abrir(m.group(1))
        if m := _RE_BORRAR.match(t):
            return self._preparar_borrado(m.group(1))

        return Respuesta("No entendí esa orden. Di «ayuda» para ver lo que sé hacer.", "pensando")

    # ---------- acciones ----------
    def _buscar(self, consulta: str) -> Respuesta:
        resultados = archivos.buscar_archivos(consulta)
        self.ultimos_resultados = resultados
        if not resultados:
            return Respuesta(f"No encontré nada con «{consulta}».", "triste")
        if len(resultados) == 1:
            return Respuesta(f"Encontré un resultado: {os.path.basename(resultados[0])}. "
                             "Di «abre el uno» para abrirlo.", "riendo", resultados)
        return Respuesta(f"Encontré {len(resultados)} resultados. Dime el número que quieres abrir.",
                         "riendo", resultados)

    def _elegir(self, objetivo: str):
        """Resuelve 'el dos' a un resultado anterior, o busca el nombre."""
        n = extraer_numero(objetivo)
        if n is not None and 1 <= n <= len(self.ultimos_resultados):
            return [self.ultimos_resultados[n - 1]]
        return None

    def _abrir(self, objetivo: str) -> Respuesta:
        elegido = self._elegir(objetivo)
        if elegido:
            archivos.abrir(elegido[0])
            seguridad.registrar("abrir", elegido[0])
            return Respuesta(f"Abriendo {os.path.basename(elegido[0])}.", "guino")
        app = archivos.buscar_app(objetivo)
        if app:
            etiqueta, destino = app
            try:
                archivos.abrir(destino)
            except OSError:
                return Respuesta(f"No pude abrir {etiqueta}. ¿Está instalado?", "triste")
            seguridad.registrar("abrir_app", destino)
            return Respuesta(f"Abriendo {etiqueta}.", "guino")
        resultados = archivos.buscar_archivos(objetivo)
        self.ultimos_resultados = resultados
        if len(resultados) == 1:
            archivos.abrir(resultados[0])
            seguridad.registrar("abrir", resultados[0])
            return Respuesta(f"Abriendo {os.path.basename(resultados[0])}.", "guino", resultados)
        if resultados:
            return Respuesta(f"Hay {len(resultados)} opciones con ese nombre. ¿Cuál abro? Di el número.",
                             "pensando", resultados)
        return Respuesta(f"No encontré ninguna aplicación ni archivo llamado «{objetivo}».", "triste")

    def _preparar_borrado(self, objetivo: str) -> Respuesta:
        elegido = self._elegir(objetivo)
        if not elegido:
            resultados = archivos.buscar_archivos(objetivo)
            self.ultimos_resultados = resultados
            if not resultados:
                return Respuesta(f"No encontré «{objetivo}».", "triste")
            if len(resultados) > 1:
                return Respuesta(f"Hay {len(resultados)} archivos con ese nombre. Di «elimina el» y el número.",
                                 "pensando", resultados)
            elegido = resultados
        ruta = elegido[0]
        ok, motivo = seguridad.puede_eliminar(ruta)
        if not ok:
            seguridad.registrar("borrado_bloqueado", f"{ruta} ({motivo})")
            return Respuesta(f"No puedo eliminar eso: {motivo}.", "enojado")
        self.pendiente_borrar = ruta
        return Respuesta(f"¿Seguro que quieres mandar «{os.path.basename(ruta)}» a la papelera? Di sí o no.",
                         "preocupado", [ruta])

    def _confirmar_borrado(self, t: str) -> Respuesta:
        ruta, self.pendiente_borrar = self.pendiente_borrar, None
        if t in _SI or t.startswith("si "):
            ok, motivo = seguridad.puede_eliminar(ruta)
            if not ok:
                return Respuesta(f"Ya no puedo eliminarlo: {motivo}.", "enojado")
            try:
                archivos.enviar_a_papelera(ruta)
            except Exception as e:  # permisos, archivo en uso, etc.
                seguridad.registrar("borrado_error", f"{ruta} ({e})")
                return Respuesta("No pude eliminarlo. Puede que esté abierto en otro programa.", "triste")
            seguridad.registrar("borrado", ruta)
            self.ultimos_resultados = [r for r in self.ultimos_resultados if r != ruta]
            return Respuesta("Listo, lo mandé a la papelera. Puedes recuperarlo desde allí.", "guino")
        if t in _NO or t.startswith("no "):
            return Respuesta("Cancelado. No borré nada.", "normal")
        # Respuesta no clara: por seguridad, no se borra.
        return Respuesta("No entendí si querías borrarlo, así que no borré nada.", "preocupado")
