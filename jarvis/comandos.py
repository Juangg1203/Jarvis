"""El cerebro de Jarvis: entiende la orden en español y la ejecuta.

Todo funciona sin internet. Las acciones peligrosas (eliminar) siempre piden confirmación
y mandan a la Papelera, nunca borran para siempre.
"""
import datetime
import os
import re
from dataclasses import dataclass, field

import os as _os

from . import archivos, config, control, documentos, internet, musica, organizar, recordatorios, redactar, seguridad
from .memoria import Memoria
from .rutinas import Rutinas
from .texto import extraer_numero, limpiar_peticion, normalizar


@dataclass
class Respuesta:
    texto: str
    expresion: str = "normal"  # una de las 9 expresiones del avatar
    resultados: list = field(default_factory=list)
    dormir: bool = False
    entendida: bool = True  # False si ninguna orden local coincide (entonces conversa Claude)


_SI = {"si", "claro", "confirmo", "dale", "hazlo", "adelante", "correcto", "si hazlo", "si borralo", "si eliminalo"}
_NO = {"no", "cancela", "cancelar", "mejor no", "detente", "olvidalo"}

_ARTICULOS = r"(?:(?:el|la|los|las|un|una|mi|mis)\s+)?"
_TIPO = r"(?:(?:archivo|archivos|documento|documentos|carpeta|carpetas|foto|fotos|programa|aplicacion|app)\s+)?"
_LLAMADO = r"(?:(?:llamado|llamada|que se llama|de nombre|con nombre|sobre|de)\s+)?"

_RE_BUSCAR = re.compile(r"^(?:busca|buscar|buscame|encuentra|encuentrame|localiza)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")
_RE_ABRIR = re.compile(r"^(?:abre|abrir|abreme|ejecuta|ejecutar|inicia|iniciar|lanza|pon)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")
_RE_BORRAR = re.compile(r"^(?:elimina|eliminar|eliminame|borra|borrar|borrame|quita)\s+" + _ARTICULOS + _TIPO + _LLAMADO + r"(.+)$")


_RE_LISTAR_AVISOS = re.compile(r"\b(?:que|cuales|mis|dime (?:mis|los)|lista de)\s+(?:recordatorios|alarmas|temporizadores|avisos|pendientes)\b|"
                               r"\bque (?:tengo|hay) pendiente")
_RE_CANCELAR = re.compile(r"^(?:cancela|cancelar|quita|borra|elimina|apaga|deten|para)\s+(?:el |la |los |las |todos los |todas las |mi |mis )?"
                          r"(recordatorio|alarma|temporizador|aviso)(?:s|es)?\b(.*)$")
_RE_RUTINA = re.compile(r"^(?:(?:activa|activar|inicia|iniciar|empieza|pon|ponme|ejecuta|arranca|entra en|entrar en)\s+)?"
                        r"(?:el |la |en )?(?:modo|rutina)\s+(.+)$")
_RE_SALIR_RUTINA = re.compile(r"^(?:termina|terminar|desactiva|desactivar|sal del|salir del|apaga|quita)\s+(?:el )?modo\b")
_RE_RECORDAR = re.compile(r"^(?:recuerda|acuerdate|apunta|anota|guarda|memoriza)\s+(?:de\s+)?que\s+(.+)$")
_RE_QUE_SABES = re.compile(r"^(?:que (?:sabes|recuerdas) (?:de|sobre) mi|que tienes (?:guardado|anotado))")
_RE_OLVIDAR = re.compile(r"^(?:olvida|olvidate de|borra de tu memoria)\s+(?:que\s+|lo de\s+|lo que te dije de\s+)?(.+)$")


class Cerebro:
    def __init__(self, agenda=None, memoria=None, rutinas=None):
        self.ultimos_resultados: list[str] = []
        self.pendiente_borrar: str | None = None
        self.pendiente_accion = None  # (descripción, función que devuelve el texto a decir)
        self.documento: str | None = None  # último documento leído
        self.agenda = agenda if agenda is not None else recordatorios.Agenda()
        self.memoria = memoria if memoria is not None else Memoria()
        self.rutinas = rutinas if rutinas is not None else Rutinas()
        self.manejadores_extra = []  # main.py añade aquí las órdenes de seguridad y del celular
        self.escritor = None  # main.py: fn(pedido, titulo) -> Respuesta; escribe documentos largos en segundo plano

    # ---------- punto de entrada ----------
    def procesar(self, texto: str, solo_ordenes: bool = False) -> Respuesta:
        """solo_ordenes=True deja los saludos y la charla para Claude."""
        t = normalizar(texto)
        if t.split(" ")[0] in config.VARIANTES_ACTIVACION:  # "Jarvis, abre..." escrito a mano
            t = t.split(" ", 1)[1] if " " in t else ""
        if not t:
            return Respuesta("No escuché nada.", "pensando")
        limpio = limpiar_peticion(t)  # "quiero que me abras..." -> "abre..."
        if limpio != t:
            texto = t = limpio
        seguridad.registrar("orden", t)

        if self.pendiente_borrar:
            return self._confirmar_borrado(t)

        if self.pendiente_accion:
            return self._confirmar_accion(t)

        for manejador in (*self.manejadores_extra, self._organizador, self._control, self._documentos, self._v6, self._internet):
            r = manejador(texto, t, solo_ordenes)
            if r is not None:
                return r

        if solo_ordenes and (t in {"hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "gracias",
                                   "muchas gracias", "ayuda", "que puedes hacer", "que sabes hacer"}):
            return Respuesta("", "normal", entendida=False)
        if t in {"hola", "hola jarvis", "buenas", "buenos dias", "buenas tardes", "buenas noches"}:
            return Respuesta(f"Hola, {config.NOMBRE_USUARIO}. ¿En qué te ayudo?", "riendo")
        if "que hora" in t or t in {"dime la hora", "di la hora", "la hora"}:
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
            return Respuesta("Puedo buscar y abrir archivos y aplicaciones, mandar archivos a la papelera, "
                             "ponerte recordatorios, alarmas y temporizadores, activar rutinas como el modo estudio, "
                             "recordar cosas de ti, resumir documentos, controlar el volumen, el brillo y el wifi, "
                             "buscar el clima y las noticias, vigilar el computador cuando no estás "
                             "y obedecer solo a tu voz.", "riendo")

        if m := _RE_BUSCAR.match(t):
            return self._buscar(m.group(1))
        if m := _RE_ABRIR.match(t):
            return self._abrir(m.group(1))
        if m := _RE_BORRAR.match(t):
            return self._preparar_borrado(m.group(1))

        return Respuesta("No entendí esa orden. Di «ayuda» para ver lo que sé hacer.", "pensando", entendida=False)

    # ---------- internet (sin Claude; con Claude lo responde él con su buscador) ----------
    def ciudad(self) -> str:
        if config.CIUDAD:
            return config.CIUDAD
        for d in reversed(self.memoria.datos):
            m = re.search(r"\b(?i:vivo|vive|estoy|soy de|es de)\s+(?:en\s+)?([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)*)",
                          d.get("texto", ""))
            if m:
                return m.group(1)
        return ""

    def _internet(self, original, t, solo_ordenes):
        clima = re.search(r"\b(?:clima|pronostico|que tiempo hace|como esta el tiempo|va a llover|llovera|temperatura)\b", t)
        noticias = re.search(r"\bnoticias?\b(?:\s+(?:de|del|sobre|acerca de)\s+(?:la |el |los |las )?(.+))?", t)
        web = re.match(r"^(?:busca|buscame|investiga|consulta)\s+(?:en\s+)?(?:internet|google|la web|la red|linea)\s+(?:sobre\s+|acerca de\s+)?(.+)", t) \
            or re.match(r"^(?:busca|buscame|investiga)\s+(.+?)\s+en\s+(?:internet|google|la web)$", t)
        pregunta = re.match(r"^(?:que|quien|quienes|cual|cuales|cuando|donde|cuanto|cuanta|cuantos|como)\s+(?:es|son|fue|fueron|era|mide|pesa|vive|nacio|murio|invento|descubrio|gano|queda|esta)\s+(.+)", t)
        if not (clima or noticias or web or pregunta):
            return None
        from . import ajustes
        if ajustes.solo_local():
            if pregunta and not (clima or noticias or web):
                return None  # la responde Ollama con lo que sabe
            return Respuesta("Estoy en modo solo local, así que no busco en internet. "
                             "Si quieres, cámbialo en Ajustes.", "normal")
        if solo_ordenes:
            return Respuesta("", "pensando", entendida=False)  # Claude busca y responde mejor
        if pregunta and not (clima or noticias or web) and re.search(r"\b(hora|dia|fecha|bateria|wifi|volumen|brillo)\b", t):
            return None  # "qué hora es", "cómo está la batería": son órdenes locales
        try:
            if clima:
                m = re.search(r"\ben\s+([a-z ]+?)(?:\s+(?:hoy|manana|ahora))?$", t)
                lugar = m.group(1) if m and m.group(1) not in {"la calle", "la casa", "casa"} else self.ciudad()
                return Respuesta(internet.clima(lugar, manana="manana" in t), "normal")
            if noticias:
                return Respuesta(internet.noticias((noticias.group(1) or "").strip()), "pensando")
            consulta = (web or pregunta).group(1) if (web or pregunta) else t
            if pregunta and not web:
                consulta = t
            texto = internet.preguntar(consulta)
            if texto:
                return Respuesta(texto, "guino")
            internet.abrir_en_navegador(consulta)
            return Respuesta("No encontré una respuesta corta; te abrí la búsqueda en el navegador.", "pensando")
        except Exception:
            return Respuesta("No pude conectarme a internet para buscar eso.", "preocupado")

    # ---------- v6: música, ordenar carpetas, notificaciones, pantalla, documentos ----------
    def reproducir(self, consulta, donde="youtube") -> Respuesta:
        try:
            return Respuesta(musica.reproducir(consulta, donde), "riendo")
        except Exception:
            return Respuesta("No pude abrir la música.", "triste")

    def tecla_musica(self, accion) -> Respuesta:
        textos = {"siguiente": "Siguiente canción.", "anterior": "Canción anterior.", "pausa": "Listo.",
                  "detener": "Música detenida."}
        if accion not in textos:
            return Respuesta("No sé hacer eso con la música.", "pensando")
        ok = musica.tecla(accion)
        return Respuesta(textos[accion] if ok else "Eso solo funciona en Windows.", "guino" if ok else "triste")

    def preparar_orden(self, nombre, modo="tipo") -> Respuesta:
        origen = organizar.carpeta(normalizar(nombre or "descargas"))
        if origen is None:
            return Respuesta(f"No encontré la carpeta {nombre}.", "pensando")
        plan = organizar.planear(origen, "fecha" if modo == "fecha" else "tipo")
        if not plan:
            n = organizar.contar_subcarpetas(origen)
            if n:
                return Respuesta(f"En {origen.name} no hay archivos sueltos: todo ya está dentro de {n} "
                                 f"{'carpeta' if n == 1 else 'carpetas'}. Solo ordeno los archivos sueltos, para no "
                                 f"desarmar las carpetas que tú hiciste. Si quieres, di «abre {origen.name.lower()}».",
                                 "guino")
            return Respuesta(f"La carpeta {origen.name} está vacía: no hay nada que ordenar.", "guino")
        n = len(plan)
        pregunta = (f"En {origen.name} hay {n} {'archivo suelto' if n == 1 else 'archivos sueltos'}. Voy a mover "
                    f"{organizar.describir(plan)}. Si no te gusta, di «deshaz el orden». ¿Lo hago?")
        return self.pedir_confirmacion(pregunta, lambda: f"Listo, ordené {organizar.ejecutar(plan)} archivos.", "pensando")

    def leer_notificaciones(self, filtro=None) -> Respuesta:
        from . import notificaciones
        try:
            lista = notificaciones.leer(filtro)
        except Exception as e:
            return Respuesta(str(e) if isinstance(e, RuntimeError) else "No pude leer tus notificaciones.", "triste")
        return Respuesta(notificaciones.resumen(lista), "normal" if lista else "guino")

    def responder_mensaje(self, texto, quien="") -> Respuesta:
        from . import notificaciones
        notificaciones.copiar(texto)
        notificaciones.abrir_whatsapp()
        destino = f"el chat de {quien}" if quien else "el chat"
        return Respuesta(f"Copié tu respuesta y abrí WhatsApp. Abre {destino}, pega con Control V y dale enviar.",
                         "guino")

    def mirar_pantalla(self, pregunta="") -> Respuesta:
        from . import pantalla
        try:
            return Respuesta(pantalla.preguntar(pregunta) or "No supe qué decir de tu pantalla.", "pensando")
        except Exception as e:
            mensaje = getattr(e, "mensaje", "") or "No pude mirar tu pantalla ahora."
            return Respuesta(mensaje, "triste")

    def documento(self, titulo, texto) -> Respuesta:
        try:
            ruta = redactar.crear_documento(titulo or "Documento", texto)
        except Exception as e:
            return Respuesta(f"No pude crear el documento: {e}", "triste")
        seguridad.registrar("documento", ruta)
        return Respuesta("Listo, guardé el documento en Documentos, carpeta Jarvis, y te lo abrí.", "riendo",
                         resultados=[ruta])

    def correo(self, para="", asunto="", cuerpo="") -> Respuesta:
        redactar.borrador_correo(para, asunto, cuerpo)
        return Respuesta("Te dejé el correo listo en tu programa de correo. Revísalo y dale enviar tú.", "guino")

    def _v6(self, original, t, solo_ordenes):
        # música
        if re.search(r"\b(?:siguiente|proxima)\s+(?:cancion|tema|canción)\b|^(?:siguiente|salta(?:la)?|cambia(?:la)? de cancion)$", t):
            return self.tecla_musica("siguiente")
        if re.search(r"\b(?:cancion|tema) anterior\b|\banterior cancion\b|^anterior$", t):
            return self.tecla_musica("anterior")
        if re.search(r"^(?:pausa|pausa la musica|para la musica|pausa la cancion|deten la musica|reanuda(?: la musica)?|continua la musica|sigue la musica|quita la pausa)$", t):
            return self.tecla_musica("pausa")
        m = re.match(r"^(?:pon|ponme|reproduce|reproduceme|toca|coloca)\s+(.+?)(?:\s+en\s+(youtube|spotify))?$", t)
        if m and not re.match(r"^(?:el|la|los|las|un|una)\s+(?:alarma|temporizador|recordatorio|volumen|brillo|modo|rutina|vigilancia|wifi)\b"
                              r"|^(?:alarma|temporizador|recordatorio|volumen|brillo|modo|rutina|vigilancia|wifi)\b", m.group(1)):
            consulta = re.sub(r"^(?:algo de |un poco de )", "", m.group(1))
            if consulta in {"musica", "algo", "una cancion", "musica para estudiar", "musica para concentrarme"}:
                consulta = "música para estudiar lofi" if "estudiar" in consulta or "concentr" in consulta or consulta in {"musica", "algo", "una cancion"} else consulta
            return self.reproducir(consulta, m.group(2) or "youtube")
        # abrir carpetas conocidas (Documentos, Descargas...), también si están en OneDrive
        m = re.match(r"^(?:abre|abreme|muestrame|ensename|ve a|vamos a|llevame a)\s+(?:a )?(?:la |mi |mis |el |los )?"
                     r"(?:carpeta\s+(?:de\s+)?(?:mis\s+|las\s+|los\s+)?)?"
                     r"(descargas|escritorio|documentos|imagenes|fotos|videos|musica)$", t)
        if m:
            carpeta = organizar.carpeta(m.group(1))
            if carpeta is None:
                return Respuesta(f"No encontré tu carpeta de {m.group(1)}.", "pensando")
            archivos.abrir(str(carpeta))
            return Respuesta(f"Listo, abrí {carpeta.name}.", "guino")
        # ordenar carpetas
        m = re.search(r"^(?:ordena|organiza|acomoda|arregla)(?:me)?\s+(?:mi |mis |la |las |el |los )?(?:carpeta (?:de )?)?"
                      r"(descargas|escritorio|documentos|imagenes|fotos|videos|musica)(?:\s+por\s+(tipo|fecha|mes))?", t)
        if m:
            return self.preparar_orden(m.group(1), "fecha" if m.group(2) in ("fecha", "mes") else "tipo")
        if re.search(r"\b(?:deshaz|deshacer|devuelve)\s+(?:el |lo )?(?:orden|ordenado)\b|^desordena", t):
            n = organizar.deshacer()
            return Respuesta(f"Listo, devolví {n} archivos a su sitio." if n else "No hay ningún orden para deshacer.",
                             "normal")
        # notificaciones, WhatsApp y correo
        if re.search(r"\b(?:lee|leeme|tengo|hay|revisa|que dicen)\b.*\b(?:notificaciones|mensajes?|whatsapp|correos?|emails?)\b", t):
            filtro = "mensajes" if re.search(r"\b(?:mensajes?|whatsapp|telegram)\b", t) else \
                "correo" if re.search(r"\b(?:correos?|emails?|gmail|outlook)\b", t) else None
            return self.leer_notificaciones(filtro)
        m = re.match(r"^(?:responde|respondele|contesta|contestale)(?:le)?(?:\s+a\s+(\w+(?:\s\w+)?))?\s+(?:que|diciendo que|diciendo)\s+(.+)", normalizar(original))
        if m:
            texto = re.split(r"(?i)\b(?:que|diciendo que|diciendo)\b\s+", original, maxsplit=1)[-1].strip()
            return self.responder_mensaje(texto, m.group(1) or "")
        # pantalla
        if re.search(r"\b(?:mira|lee|leeme|revisa|analiza|explicame)\s+(?:mi |la |lo de la |lo que hay en (?:la|mi) )?pantalla\b"
                     r"|\bque (?:hay|ves|sale|dice) en (?:mi |la )?pantalla\b|\bque (?:es|significa) (?:este|ese) error\b"
                     r"|\bayudame con (?:este|ese) error\b|\bque dice (?:aqui|esto)\b", t):
            return self.mirar_pantalla(original)
        return None

    # ---------- recordatorios, rutinas y memoria ----------
    def _organizador(self, original, t, solo_ordenes):
        # Recordatorios, alarmas y temporizadores
        aviso = recordatorios.interpretar(original)
        if aviso:
            return self.crear_aviso(aviso["cuando"], aviso["mensaje"], aviso["tipo"])
        if recordatorios._RE_PREFIJO.match(t):
            if solo_ordenes:
                return Respuesta("", "pensando", entendida=False)  # Claude entenderá la hora
            return Respuesta("¿Cuándo te aviso? Dime por ejemplo «recuérdame en 10 minutos» o "
                             "«recuérdame mañana a las 8».", "pensando")
        if _RE_LISTAR_AVISOS.search(t):
            return Respuesta(self.listar_avisos(), "normal")
        if m := _RE_CANCELAR.match(t):
            plural = re.search(r"\b(?:tod[oa]s|recordatorios|alarmas|temporizadores|avisos)\b", t)
            return self.cancelar_avisos(m.group(2), todos=bool(plural))

        # Rutinas
        if t in {"que rutinas tengo", "cuales son mis rutinas", "mis rutinas", "que modos tienes", "que modos tengo"}:
            nombres = self.rutinas.nombres()
            return Respuesta("Tus rutinas son: " + ", ".join(nombres) + ". Di «modo» y el nombre para activarla."
                             if nombres else "No tienes rutinas todavía.", "normal")
        if _RE_SALIR_RUTINA.match(t) and "normal" in self.rutinas.rutinas:
            return Respuesta(self.rutinas.ejecutar("normal", self.agenda), "guino")
        nombre = None
        if m := _RE_RUTINA.match(t):
            nombre = self.rutinas.buscar(m.group(1))
            if not nombre:
                return Respuesta(f"No tengo una rutina llamada {m.group(1)}. Puedes pedirme que la cree.", "pensando",
                                 entendida=not solo_ordenes)
        elif t in {normalizar(n) for n in self.rutinas.nombres()}:
            nombre = self.rutinas.buscar(t)
        if nombre:
            return Respuesta(self.rutinas.ejecutar(nombre, self.agenda), "riendo")

        # Memoria
        if re.match(r"^(?:olvida|borra|olvidate de)\s+todo\b", t):
            return self.pedir_confirmacion("¿Borro todo lo que recuerdo de ti y de nuestras conversaciones?",
                                           lambda: (self.memoria.olvidar_todo(), "Listo, empecé de cero.")[1])
        if re.match(r"^(?:de que hablamos|que hablamos|que te dije)\b", t) and not solo_ordenes:
            ultimos = self.memoria.resumenes[-2:]
            if not ultimos:
                return Respuesta("No tengo resúmenes de conversaciones anteriores todavía.", "pensando")
            return Respuesta(" ".join(f"El {r['fecha'][:10]}: {r['resumen']}" for r in ultimos), "normal")
        if m := _RE_RECORDAR.match(t):
            dato = m.group(1)
            originales = {normalizar(w): w for w in re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", original)}
            dato = " ".join(originales.get(w, w) for w in dato.split())
            nuevo = self.memoria.recordar(dato)
            return Respuesta("Anotado, lo recordaré." if nuevo else "Eso ya lo tenía anotado.", "guino")
        if _RE_QUE_SABES.match(t):
            datos = self.memoria.datos
            if not datos:
                return Respuesta("Todavía no me has pedido recordar nada. Dime por ejemplo «recuerda que mi color favorito es el azul».", "normal")
            return Respuesta("Esto es lo que recuerdo: " + "; ".join(d["texto"] for d in datos[-10:]) + ".", "riendo")
        if m := _RE_OLVIDAR.match(t):
            n = self.memoria.olvidar(m.group(1))
            return Respuesta("Listo, lo olvidé." if n else "No tenía nada anotado sobre eso.", "normal" if n else "pensando")
        return None

    def crear_aviso(self, cuando, mensaje="", tipo="recordatorio") -> Respuesta:
        item = self.agenda.agregar(cuando, mensaje, tipo)
        seguridad.registrar("aviso", f"{item['cuando']} {tipo} {mensaje}")
        nombre = {"alarma": "la alarma", "temporizador": "el temporizador"}.get(tipo, "el recordatorio")
        texto = f"Listo, puse {nombre} {recordatorios.describir(cuando)}"
        return Respuesta(texto + (f": {mensaje}." if mensaje else "."), "guino")

    def listar_avisos(self) -> str:
        items = self.agenda.pendientes()
        if not items:
            return "No tienes recordatorios ni alarmas pendientes."
        import datetime as _dt
        partes = [f"{i}, {recordatorios.describir(_dt.datetime.fromisoformat(x['cuando']))} {x['mensaje'] or x['tipo']}"
                  for i, x in enumerate(items[:8], 1)]
        return f"Tienes {len(items)}: " + "; ".join(partes) + "."

    def cancelar_avisos(self, resto="", todos=False) -> Respuesta:
        items = self.agenda.pendientes()
        if not items:
            return Respuesta("No hay nada que cancelar.", "normal")
        n = extraer_numero(resto.strip()) if resto.strip() else None
        if n is not None:
            quitados = self.agenda.cancelar(n)
        elif todos or len(items) == 1:
            quitados = self.agenda.cancelar(None)
        else:
            return Respuesta(f"Tienes {len(items)} pendientes. Dime cuál, por ejemplo «cancela el recordatorio dos», "
                             "o «cancela todos los recordatorios».", "pensando")
        return Respuesta("Cancelado." if quitados else "No encontré ese número.", "normal" if quitados else "pensando")

    # ---------- confirmaciones genéricas ----------
    def pedir_confirmacion(self, pregunta, funcion, cara="preocupado") -> Respuesta:
        self.pendiente_accion = (pregunta, funcion)
        return Respuesta(pregunta + " Di sí o no.", cara)

    def _confirmar_accion(self, t) -> Respuesta:
        (_, funcion), self.pendiente_accion = self.pendiente_accion, None
        if t in _SI or t.startswith("si "):
            try:
                texto = funcion()
            except Exception as e:
                seguridad.registrar("accion_error", str(e))
                return Respuesta("No pude hacerlo.", "triste")
            return Respuesta(texto, "guino")
        if t in _NO or t.startswith("no "):
            return Respuesta("Cancelado.", "normal")
        return Respuesta("No entendí si querías hacerlo, así que lo cancelé.", "preocupado")

    # ---------- control del PC ----------
    def _control(self, original, t, solo_ordenes):
        t2 = recordatorios._a_cifras(t)
        numero = re.search(r"\b(?:a|al|en|hasta)\s+(\d{1,3})\b", t2)
        nivel = int(numero.group(1)) if numero else None
        sube = re.match(r"^(?:sube|subir|subele|aumenta|aumentar|mas)\b", t2)
        baja = re.match(r"^(?:baja|bajar|bajale|disminuye|reduce|menos)\b", t2)
        ajusta = re.match(r"^(?:pon|ponme|ponle|ajusta|cambia|deja|configura)\b", t2)
        cuanto = re.search(r"\b(\d{1,3})\s*(?:puntos|por ciento)?$", t2)

        if re.match(r"^(?:silencia|silenciar|mutea|mute|quita el sonido|sin sonido|apaga el sonido)\b", t2):
            return Respuesta(control.volumen(silenciar=True), "normal")
        if re.match(r"^(?:quita el silencio|desmutea|activa el sonido|pon el sonido|vuelve el sonido|prende el sonido)\b", t2):
            return Respuesta(control.volumen(silenciar=False), "guino")
        if re.search(r"\b(?:volumen|sonido)\b", t2) and (sube or baja or ajusta or nivel is not None):
            if nivel is not None and (ajusta or not (sube or baja)):
                return Respuesta(control.volumen(nivel=nivel), "guino")
            paso = int(cuanto.group(1)) if cuanto and not nivel else 10
            return Respuesta(control.volumen(cambio=paso if sube else -paso if baja else 0, nivel=nivel), "guino")
        if re.search(r"\bbrillo\b", t2) and (sube or baja or ajusta or nivel is not None):
            if nivel is not None and (ajusta or not (sube or baja)):
                return Respuesta(control.brillo(nivel=nivel), "guino")
            paso = int(cuanto.group(1)) if cuanto and not nivel else 20
            return Respuesta(control.brillo(cambio=paso if sube else -paso, nivel=nivel), "guino")

        if re.search(r"\b(?:wifi|wi fi|wi-fi)\b", t2):
            if re.match(r"^(?:apaga|desactiva|desconecta|quita)", t2):
                return Respuesta(control.wifi(False), "normal")
            if re.match(r"^(?:prende|enciende|activa|conecta|pon)", t2):
                return Respuesta(control.wifi(True), "guino")
            conectado, red = control.wifi_estado()
            return Respuesta(f"Estás conectado a {red}." if conectado else "No estás conectado a ningún wifi.", "normal")
        if re.search(r"\b(?:bateria|pila)\b", t2) or t2 in {"cuanta carga tengo", "cuanta carga queda"}:
            return Respuesta(control.bateria(), "normal")

        equipo = r"(?:el |la |mi )?(?:computador|computadora|pc|equipo|portatil|ordenador|laptop|compu)\b"
        if re.match(r"^(?:cancela|cancelar|anula|deten|para)\s+(?:el |la )?(?:apagado|reinicio)|^no (?:te )?apagues", t2):
            return Respuesta(control.cancelar_apagado(), "guino")
        if re.match(r"^(?:apaga|apagar|apagame)\s+" + equipo, t2):
            return self.pedir_confirmacion("¿Seguro que apago el computador? Guarda tu trabajo antes.",
                                           lambda: control.apagar(reiniciar=False))
        if re.match(r"^(?:reinicia|reiniciar|reiniciame)\s+" + equipo, t2):
            return self.pedir_confirmacion("¿Seguro que reinicio el computador? Guarda tu trabajo antes.",
                                           lambda: control.apagar(reiniciar=True))
        if re.match(r"^(?:suspende|suspender|hiberna|hibernar)\s+" + equipo, t2):
            return self.pedir_confirmacion("¿Suspendo el computador?", control.suspender)

        if re.search(r"\b(?:no responden?|congelad[oa]s?|colgad[oa]s?|trabad[oa]s?|pegad[oa]s?)\b", t2) and \
                re.match(r"^(?:cierra|cerrar|mata|quita|arregla|que hago)", t2):
            return self.cerrar_colgados()
        if m := re.match(r"^(?:fuerza el cierre de|forzar el cierre de|cierra a la fuerza|mata|matar)\s+(?:el |la |a )?(?:proceso |programa |aplicacion |app )?(.+)$", t2):
            return self.cerrar_programa(m.group(1), forzar=True)
        if m := re.match(r"^(?:cierra|cerrar|cierrame)\s+(?:el |la |los |las )?(?:programa |aplicacion |app |ventana de )?(.+)$", t2):
            return self.cerrar_programa(m.group(1), forzar=False)
        return None

    def cerrar_programa(self, nombre, forzar=False) -> Respuesta:
        procesos = control.buscar_procesos(nombre)
        if not procesos:
            return Respuesta(f"No veo {nombre} abierto.", "pensando")
        lista = ", ".join(p.removesuffix(".exe").removesuffix(".EXE") for p in procesos)
        if forzar:
            return self.pedir_confirmacion(
                f"¿Fuerzo el cierre de {lista}? Si tenía algo sin guardar, se pierde.",
                lambda: f"Cerré {lista}." if sum(control.cerrar(p, True) for p in procesos) else "No pude cerrarlo.")
        cerrados = sum(1 for p in procesos if control.cerrar(p, forzar=False))
        seguridad.registrar("cerrar", lista)
        if cerrados:
            return Respuesta(f"Cerrando {lista}. Si no se cierra, di «fuerza el cierre de {nombre}».", "guino")
        return Respuesta(f"{nombre} no quiere cerrarse. Di «fuerza el cierre de {nombre}» si está congelado.", "preocupado")

    def cerrar_colgados(self) -> Respuesta:
        lista = control.colgados()
        if not lista:
            return Respuesta("Ningún programa aparece como «No responde» ahora mismo.", "guino")
        nombres = ", ".join(p.rsplit(".", 1)[0] for p in lista)
        return self.pedir_confirmacion(f"No responden: {nombres}. ¿Los cierro a la fuerza?",
                                       lambda: f"Cerré {control.cerrar_colgados(lista)} programa(s) congelado(s).")

    # ---------- documentos ----------
    def _documentos(self, original, t, solo_ordenes):
        if re.search(r"notificacion|mensaje|whatsapp|correo|pantalla", t):
            return None  # eso lo atiende _v6
        m = re.match(r"^(?:resume|resumeme|resumir|resumen de|haz un resumen de|hazme un resumen de|"
                     r"de que (?:se )?trata|que dice|lee|leeme)\s*(?:el |la |este |ese |esta |esa |mi )?"
                     r"(?:documento|archivo|pdf|word|texto|trabajo)?\s*(?:llamado |que se llama |de |del )?(.*)$", t)
        if not m:
            return None
        objetivo = m.group(1).strip()
        # Una ruta completa (por ejemplo, un archivo arrastrado a la ventana) se toma tal cual del original.
        ruta_directa = re.search(r"[A-Za-z]:\\[^\n]+|/[^\n]+\.\w{2,4}$", original)
        if ruta_directa and _os.path.isfile(ruta_directa.group(0).strip()):
            objetivo = ruta_directa.group(0).strip()
        if solo_ordenes:
            return Respuesta("", "pensando", entendida=False)  # Claude lo lee con la herramienta leer_documento
        ruta, r = self.resolver_documento(objetivo)
        if not ruta:
            return r
        texto, nota = documentos.extraer_texto(ruta)
        if not texto:
            return Respuesta(f"No pude leer {_os.path.basename(ruta)}: {nota or 'está vacío'}.", "triste")
        resumen = documentos.resumen_local(texto)
        temas = ", ".join(documentos.temas(texto))
        self.memoria.anotar("Jarvis", f"Resumen de {_os.path.basename(ruta)}: {resumen}")
        return Respuesta(f"{_os.path.basename(ruta)} habla de {temas}. Lo más importante: {resumen} "
                         "Con la clave de Claude te haría un resumen mucho mejor y podrías preguntarme sobre él.",
                         "riendo", [ruta])

    def resolver_documento(self, objetivo):
        """Devuelve (ruta, None) o (None, Respuesta explicando el problema)."""
        objetivo = (objetivo or "").strip()
        if objetivo and _os.path.isfile(objetivo):
            ruta = objetivo
        elif not objetivo or objetivo in {"este", "ese", "el", "lo", "documento", "archivo"}:
            ruta = self.documento or next((r for r in self.ultimos_resultados if documentos.es_documento(r)), None)
            if not ruta:
                return None, Respuesta("¿Qué documento resumo? Dime su nombre o arrástralo a mi ventana.", "pensando")
        else:
            elegido = self._elegir(objetivo)
            if elegido:
                ruta = elegido[0]
            else:
                encontrados = [r for r in archivos.buscar_archivos(objetivo) if documentos.es_documento(r)]
                if not encontrados:
                    return None, Respuesta(f"No encontré ningún documento llamado «{objetivo}».", "triste")
                if len(encontrados) > 1:
                    self.ultimos_resultados = encontrados
                    return None, Respuesta(f"Hay {len(encontrados)} documentos con ese nombre. Di «resume el» y el número.",
                                           "pensando", encontrados)
                ruta = encontrados[0]
        if not documentos.es_documento(ruta):
            return None, Respuesta("Ese archivo no es un documento que sepa leer (PDF, Word, PowerPoint o texto).", "pensando")
        self.documento = ruta
        return ruta, None

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
