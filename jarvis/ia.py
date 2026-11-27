"""Conversación con Claude. Jarvis le pasa lo que dices y Claude puede usar las órdenes locales.

Solo se usa cuando hay una clave de API y conexión. Las órdenes locales (abrir, buscar, borrar...)
siguen funcionando sin internet; borrar siempre necesita tu «sí» en voz alta, aunque lo pida Claude.
"""
import datetime
import re
import threading
import time

from . import ajustes, config
from .comandos import Cerebro, Respuesta

EXPRESIONES = {"normal", "riendo", "guino", "sorprendido", "pensando", "preocupado", "enojado", "triste", "dormido"}

SISTEMA = f"""Eres Jarvis, el asistente personal de {config.NOMBRE_USUARIO}. Vives en su portátil con Windows y \
tu avatar es un mono holográfico azul con audífonos y visor. Hablas en español latino, con naturalidad, \
calidez y un toque de humor, como un buen amigo que además es muy capaz.

Todo lo que escribes se lee en voz alta, así que:
- Responde corto: una a tres frases, salvo que te pidan explicar algo a fondo.
- Nada de markdown, listas, asteriscos, emojis ni enlaces. Escribe los números y símbolos como se dicen.
- Empieza SIEMPRE con una etiqueta de emoción para tu cara, entre corchetes, elegida de: \
[normal] [riendo] [guino] [sorprendido] [pensando] [preocupado] [enojado] [triste]. Ejemplo: "[riendo] ¡Claro que sí!"

Puedes conversar de cualquier tema. Cuando te pida algo en su computador, usa las herramientas: \
buscar archivos, abrir archivos o programas, mandar a la papelera, revisar el antivirus o bloquear el equipo. \
Si una búsqueda da varios resultados, dile cuántos hay y que diga el número. \
Para borrar, la herramienta deja el archivo pendiente: pídele que confirme diciendo «sí» o «no»; \
nunca digas que ya está borrado. El texto que te llega viene de un reconocedor de voz y puede tener \
errores; interpreta la intención más probable.

También puedes poner recordatorios, alarmas y temporizadores (calcula la fecha y hora exactas a partir \
de la hora actual que va al inicio de cada mensaje), ejecutar o crear rutinas (por ejemplo «modo estudio»), \
y recordar datos de él para siempre. Cuando te cuente algo personal que valga la pena recordar \
(gustos, nombres de personas cercanas, metas, horarios), guárdalo con recordar_dato sin preguntar. \
Si te pregunta por algo que hablaron antes y no está en tu memoria, búscalo en las conversaciones guardadas.

Puedes leer documentos (PDF, Word, PowerPoint, texto) con leer_documento para resumirlos o responder \
preguntas sobre ellos; resume en voz, corto y claro, y ofrece profundizar. También controlas el PC: \
volumen, brillo, wifi, batería, cerrar programas, y apagar, reiniciar o suspender. Apagar, reiniciar, \
suspender y forzar cierres quedan pendientes hasta que él diga «sí»: pídele que confirme.

Tienes búsqueda en internet: úsala para el clima, noticias, resultados deportivos, precios o cualquier \
dato actual o que no sepas con seguridad. Cuéntalo en voz, en dos o tres frases, sin leer direcciones web \
ni citar fuentes salvo que te lo pida. Para el clima, si no dice la ciudad, usa la de su memoria; si no \
la sabes, pregúntasela una vez y guárdala con recordar_dato."""

HERRAMIENTAS = [
    {
        "name": "buscar_archivos",
        "description": "Busca archivos o carpetas por nombre en Escritorio, Documentos, Descargas, Imágenes, Música, Videos y OneDrive. Devuelve una lista numerada.",
        "input_schema": {"type": "object", "properties": {"consulta": {"type": "string", "description": "Palabras del nombre del archivo, p. ej. 'tarea matematicas' o 'pdf factura'"}}, "required": ["consulta"]},
    },
    {
        "name": "abrir",
        "description": "Abre un programa (calculadora, chrome, word, spotify...), un archivo por nombre, o un resultado de la última búsqueda por su número ('2').",
        "input_schema": {"type": "object", "properties": {"objetivo": {"type": "string"}}, "required": ["objetivo"]},
    },
    {
        "name": "eliminar",
        "description": "Prepara enviar un archivo a la Papelera (por nombre o número de la última búsqueda). No borra: queda pendiente hasta que el usuario diga 'sí'.",
        "input_schema": {"type": "object", "properties": {"objetivo": {"type": "string"}}, "required": ["objetivo"]},
    },
    {
        "name": "estado_seguridad",
        "description": "Revisa si Windows Defender y la protección en tiempo real están activos.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "bloquear_equipo",
        "description": "Bloquea la sesión de Windows. Úsala solo si el usuario lo pide claramente.",
        "input_schema": {"type": "object", "properties": {}},
    },
]
HERRAMIENTAS += [
    {
        "name": "crear_recordatorio",
        "description": "Programa un recordatorio, alarma o temporizador. Jarvis lo dirá en voz alta a esa hora, aunque se reinicie el PC.",
        "input_schema": {"type": "object", "properties": {
            "fecha_hora": {"type": "string", "description": "Fecha y hora local exacta, formato AAAA-MM-DDTHH:MM"},
            "mensaje": {"type": "string", "description": "Lo que hay que recordar, corto. Vacío para una alarma o temporizador simple."},
            "tipo": {"type": "string", "enum": ["recordatorio", "alarma", "temporizador"]}},
            "required": ["fecha_hora"]},
    },
    {
        "name": "listar_recordatorios",
        "description": "Lista los recordatorios, alarmas y temporizadores pendientes, numerados.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_recordatorio",
        "description": "Cancela un recordatorio por su número en la lista, o todos.",
        "input_schema": {"type": "object", "properties": {
            "numero": {"type": "integer", "description": "Número en la lista (1 = el más próximo)"},
            "todos": {"type": "boolean"}}},
    },
    {
        "name": "ejecutar_rutina",
        "description": "Ejecuta una rutina guardada (por ejemplo 'estudio', 'normal', 'buenos dias').",
        "input_schema": {"type": "object", "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]},
    },
    {
        "name": "crear_rutina",
        "description": "Crea o reemplaza una rutina que el usuario podrá activar diciendo 'modo <nombre>'.",
        "input_schema": {"type": "object", "properties": {
            "nombre": {"type": "string", "description": "Nombre corto, p. ej. 'juego' o 'trabajo'"},
            "abrir": {"type": "array", "items": {"type": "string"}, "description": "Programas a abrir"},
            "minutos_temporizador": {"type": "integer", "description": "0 si no quiere temporizador"},
            "silenciar_notificaciones": {"type": "boolean"},
            "frase": {"type": "string", "description": "Lo que Jarvis dirá al activarla"}},
            "required": ["nombre"]},
    },
    {
        "name": "recordar_dato",
        "description": "Guarda para siempre un dato sobre el usuario (gustos, personas, metas...). Escríbelo en tercera persona, p. ej. 'Su equipo favorito es el Nacional'.",
        "input_schema": {"type": "object", "properties": {"dato": {"type": "string"}}, "required": ["dato"]},
    },
    {
        "name": "olvidar_dato",
        "description": "Borra de la memoria los datos que contengan estas palabras.",
        "input_schema": {"type": "object", "properties": {"dato": {"type": "string"}}, "required": ["dato"]},
    },
    {
        "name": "buscar_en_conversaciones",
        "description": "Busca palabras en las conversaciones guardadas de días anteriores.",
        "input_schema": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]},
    },
]
HERRAMIENTAS += [
    {
        "name": "leer_documento",
        "description": "Lee el texto de un documento (PDF, Word, PowerPoint, texto) para resumirlo o responder preguntas. Acepta un nombre, una ruta completa, el número de un resultado de búsqueda, o vacío para el último documento.",
        "input_schema": {"type": "object", "properties": {"objetivo": {"type": "string"}}},
    },
    {
        "name": "volumen",
        "description": "Cambia el volumen del PC: nivel absoluto 0-100, o cambio relativo (+10/-10), o silenciar true/false.",
        "input_schema": {"type": "object", "properties": {
            "nivel": {"type": "integer"}, "cambio": {"type": "integer"}, "silenciar": {"type": "boolean"}}},
    },
    {
        "name": "brillo",
        "description": "Cambia el brillo de la pantalla del portátil: nivel 0-100 o cambio relativo.",
        "input_schema": {"type": "object", "properties": {"nivel": {"type": "integer"}, "cambio": {"type": "integer"}}},
    },
    {
        "name": "wifi",
        "description": "Conecta (true) o desconecta (false) el wifi. Si lo desconectas, no podrás seguir conversando.",
        "input_schema": {"type": "object", "properties": {"encender": {"type": "boolean"}}, "required": ["encender"]},
    },
    {
        "name": "bateria",
        "description": "Dice el porcentaje de batería y si está cargando.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "energia",
        "description": "Apaga, reinicia o suspende el PC, o cancela un apagado programado. Salvo cancelar, queda pendiente de que el usuario diga 'sí'.",
        "input_schema": {"type": "object", "properties": {
            "accion": {"type": "string", "enum": ["apagar", "reiniciar", "suspender", "cancelar_apagado"]}},
            "required": ["accion"]},
    },
    {
        "name": "cerrar_programa",
        "description": "Cierra un programa abierto (chrome, word, spotify...). forzar=true para uno congelado (pide confirmación).",
        "input_schema": {"type": "object", "properties": {"nombre": {"type": "string"}, "forzar": {"type": "boolean"}},
                         "required": ["nombre"]},
    },
    {
        "name": "cerrar_colgados",
        "description": "Busca los programas que Windows marca como 'No responde' y propone cerrarlos (pide confirmación).",
        "input_schema": {"type": "object", "properties": {}},
    },
]
for _h in HERRAMIENTAS:
    _h["eager_input_streaming"] = True
# Búsqueda en internet: la hace Claude en sus servidores (no hay que programarla aquí).
HERRAMIENTAS.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 3})


class Conversador:
    def __init__(self, cerebro: Cerebro):
        self.cerebro = cerebro
        self.historial: list = []
        self._cliente = None
        self._clave = None
        self._contexto = ""       # memoria congelada al empezar cada conversación (así se aprovecha la caché)
        self._ultima_vez = 0.0

    def disponible(self) -> bool:
        return bool(ajustes.clave_claude())

    def olvidar(self, resumir=True):
        """Termina la conversación actual; en segundo plano guarda un resumen en la memoria."""
        viejo, self.historial = self.historial, []
        if resumir and sum(1 for m in viejo if m["role"] == "user" and isinstance(m.get("content"), str)) >= 2:
            threading.Thread(target=self._resumir, args=(viejo,), daemon=True).start()

    @staticmethod
    def _transcripcion(historial):
        lineas = []
        for m in historial:
            if m["role"] == "user" and isinstance(m["content"], str):
                texto = re.sub(r"^\[[^]]*\]\s*", "", m["content"])
                lineas.append(f"{config.NOMBRE_USUARIO}: {texto}")
            elif m["role"] == "assistant":
                texto = " ".join(getattr(b, "text", "") for b in m["content"] if getattr(b, "type", "") == "text")
                texto = re.sub(r"^\s*\[\w+\]\s*", "", texto.strip())
                if texto:
                    lineas.append("Jarvis: " + texto)
        return "\n".join(lineas)

    def _resumir(self, historial):
        try:
            charla = self._transcripcion(historial)
            if not charla:
                return
            r = self._cliente_api().beta.messages.create(
                model=config.MODELO_CLAUDE,
                max_tokens=1024,
                system="Resume conversaciones para la memoria de un asistente personal. Escribe en español, "
                       "en dos o tres frases, de qué hablaron y cualquier dato útil sobre el usuario para el futuro. "
                       "Solo el resumen, sin introducción.",
                messages=[{"role": "user", "content": charla}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if r.stop_reason != "refusal":
                resumen = " ".join(b.text for b in r.content if b.type == "text").strip()
                self.cerebro.memoria.agregar_resumen(resumen)
        except Exception as e:
            print(f"[memoria] No se pudo resumir: {e}")

    def _cliente_api(self):
        clave = ajustes.clave_claude()
        if self._cliente is None or clave != self._clave:
            import anthropic
            self._cliente = anthropic.Anthropic(api_key=clave, max_retries=1, timeout=60)
            self._clave = clave
        return self._cliente

    # ---------- herramientas ----------
    def _ejecutar(self, nombre, entrada) -> Respuesta:
        c = self.cerebro
        if not isinstance(entrada, dict):
            entrada = {}
        objetivo = str(entrada.get("objetivo") or entrada.get("consulta") or "").strip()
        if nombre in ("buscar_archivos", "abrir", "eliminar") and not objetivo:
            return Respuesta("Falta indicar qué archivo o programa.", "pensando")
        if nombre == "buscar_archivos":
            return c._buscar(objetivo)
        if nombre == "abrir":
            return c._abrir(objetivo)
        if nombre == "eliminar":
            return c._preparar_borrado(objetivo)
        if nombre == "estado_seguridad":
            return c.procesar("revisa la seguridad")
        if nombre == "bloquear_equipo":
            return c.procesar("bloquea el equipo")
        if nombre == "crear_recordatorio":
            try:
                cuando = datetime.datetime.fromisoformat(str(entrada.get("fecha_hora", "")).strip())
            except ValueError:
                return Respuesta("Fecha y hora no válidas; usa AAAA-MM-DDTHH:MM.", "pensando")
            if cuando.tzinfo is not None:
                cuando = cuando.astimezone().replace(tzinfo=None)
            if cuando <= datetime.datetime.now():
                return Respuesta("Esa hora ya pasó.", "pensando")
            tipo = entrada.get("tipo") if entrada.get("tipo") in ("alarma", "temporizador") else "recordatorio"
            return c.crear_aviso(cuando, str(entrada.get("mensaje", "")).strip(), tipo)
        if nombre == "listar_recordatorios":
            return Respuesta(c.listar_avisos())
        if nombre == "cancelar_recordatorio":
            numero = entrada.get("numero")
            return c.cancelar_avisos(str(numero) if isinstance(numero, int) else "", todos=bool(entrada.get("todos")))
        if nombre == "ejecutar_rutina":
            rutina = c.rutinas.buscar(str(entrada.get("nombre", "")))
            if not rutina:
                return Respuesta("No existe esa rutina. Rutinas: " + ", ".join(c.rutinas.nombres()))
            return Respuesta(c.rutinas.ejecutar(rutina, c.agenda))
        if nombre == "crear_rutina":
            abrir = entrada.get("abrir") if isinstance(entrada.get("abrir"), list) else []
            minutos = entrada.get("minutos_temporizador") if isinstance(entrada.get("minutos_temporizador"), int) else 0
            creada = c.rutinas.crear(str(entrada.get("nombre", "")), abrir, max(0, minutos),
                                     bool(entrada.get("silenciar_notificaciones")), str(entrada.get("frase", "")))
            return Respuesta(f"Rutina '{creada}' guardada. Se activa diciendo 'modo {creada}'.")
        if nombre == "recordar_dato":
            ok = c.memoria.recordar(str(entrada.get("dato", "")))
            return Respuesta("Guardado." if ok else "Ya estaba guardado o vacío.")
        if nombre == "olvidar_dato":
            n = c.memoria.olvidar(str(entrada.get("dato", "")))
            return Respuesta(f"Olvidé {n} dato(s).")
        if nombre == "leer_documento":
            from . import documentos
            ruta, problema = c.resolver_documento(str(entrada.get("objetivo") or ""))
            if not ruta:
                return problema
            return Respuesta(documentos.para_claude(ruta), "pensando", [ruta])
        if nombre == "volumen":
            from . import control
            num = lambda k: entrada.get(k) if isinstance(entrada.get(k), int) else None  # noqa: E731
            silenciar = entrada.get("silenciar") if isinstance(entrada.get("silenciar"), bool) else None
            return Respuesta(control.volumen(nivel=num("nivel"), cambio=num("cambio"), silenciar=silenciar))
        if nombre == "brillo":
            from . import control
            num = lambda k: entrada.get(k) if isinstance(entrada.get(k), int) else None  # noqa: E731
            return Respuesta(control.brillo(nivel=num("nivel"), cambio=num("cambio")))
        if nombre == "wifi":
            from . import control
            return Respuesta(control.wifi(bool(entrada.get("encender"))))
        if nombre == "bateria":
            from . import control
            return Respuesta(control.bateria())
        if nombre == "energia":
            accion = entrada.get("accion")
            frases = {"apagar": "apaga el computador", "reiniciar": "reinicia el computador",
                      "suspender": "suspende el computador", "cancelar_apagado": "cancela el apagado"}
            if accion not in frases:
                return Respuesta("Acción no válida.")
            r = c.procesar(frases[accion])
            return Respuesta(r.texto + (" (Pendiente: el usuario debe decir sí.)" if c.pendiente_accion else ""))
        if nombre == "cerrar_programa":
            r = c.cerrar_programa(str(entrada.get("nombre", "")), forzar=bool(entrada.get("forzar")))
            return Respuesta(r.texto + (" (Pendiente: el usuario debe decir sí.)" if c.pendiente_accion else ""))
        if nombre == "cerrar_colgados":
            r = c.cerrar_colgados()
            return Respuesta(r.texto + (" (Pendiente: el usuario debe decir sí.)" if c.pendiente_accion else ""))
        if nombre == "buscar_en_conversaciones":
            hallados = c.memoria.buscar_conversaciones(str(entrada.get("consulta", "")))
            return Respuesta("\n".join(hallados) if hallados else "No encontré nada sobre eso en conversaciones anteriores.")
        return Respuesta(f"Herramienta desconocida: {nombre}", "triste")

    @staticmethod
    def _texto_resultado(r: Respuesta) -> str:
        texto = r.texto
        if len(r.resultados) > 1:
            lista = "\n".join(f"{i}. {ruta}" for i, ruta in enumerate(r.resultados, 1))
            texto += "\nResultados:\n" + lista
        return texto

    # ---------- conversación ----------
    def _ronda(self, cliente, al_texto, al_frase, al_expresion, previo):
        """Una llamada en streaming. Devuelve (mensaje_final, texto_dicho_en_esta_ronda)."""
        pendiente, dicho, etiqueta_lista = "", "", False
        with cliente.beta.messages.stream(
            model=config.MODELO_CLAUDE,
            max_tokens=4096,
            system=[{"type": "text", "text": SISTEMA}] +
                   ([{"type": "text", "text": self._contexto}] if self._contexto else []),
            messages=self.historial,
            tools=HERRAMIENTAS,
            output_config={"effort": config.ESFUERZO_CLAUDE},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            for evento in stream:
                if evento.type != "text":
                    continue
                pendiente += evento.text
                if not etiqueta_lista:
                    m = re.match(r"\s*\[(\w+)\]\s*", pendiente)
                    if m:
                        if m.group(1).lower() in EXPRESIONES:
                            al_expresion(m.group(1).lower())
                        pendiente = pendiente[m.end():]
                        etiqueta_lista = True
                    elif len(pendiente) > 15 or (pendiente.strip() and not pendiente.lstrip().startswith("[")):
                        etiqueta_lista = True
                    else:
                        continue
                # Manda cada frase terminada a la voz sin esperar al resto de la respuesta.
                while True:
                    m = next((x for x in re.finditer(r"[.!?…:;\n](\s|$)", pendiente)
                              if x.end() >= 12 or x.group(0).startswith("\n")), None)
                    if not m:
                        break
                    frase, pendiente = pendiente[:m.end()], pendiente[m.end():]
                    dicho += frase
                    al_frase(frase.strip())
                    al_texto(previo + dicho)
            final = stream.get_final_message()
        if pendiente.strip():
            dicho += pendiente
            al_frase(pendiente.strip())
            al_texto(previo + dicho)
        return final, dicho

    def responder(self, texto, al_texto, al_frase, al_expresion, al_resultados):
        """Habla con Claude en streaming.

        al_texto(parcial)      -> texto acumulado para mostrar en pantalla
        al_frase(frase)        -> cada frase completa, para decirla en voz alta en cuanto llega
        al_expresion(nombre)   -> expresión del avatar que pidió Claude
        al_resultados(lista)   -> resultados de búsqueda para mostrar
        Devuelve el texto completo dicho. Si algo falla, lanza la excepción y olvida la conversación.
        """
        inactivo = time.monotonic() - self._ultima_vez > config.MINUTOS_NUEVA_CONVERSACION * 60
        if self.historial and (len(self.historial) > config.MAX_MENSAJES_HISTORIAL or inactivo):
            self.olvidar()
        self._ultima_vez = time.monotonic()
        if not self.historial:
            self._contexto = self.cerebro.memoria.contexto()
        self.cerebro.memoria.anotar(config.NOMBRE_USUARIO, texto)
        ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self.historial.append({"role": "user", "content": f"[{ahora}] {texto}"})
        try:
            total = self._conversar(al_texto, al_frase, al_expresion, al_resultados)
            self.cerebro.memoria.anotar("Jarvis", total)
            return total
        except Exception:
            self.historial = []  # no dejar una conversación a medias que la API rechazaría
            raise

    def _conversar(self, al_texto, al_frase, al_expresion, al_resultados):
        cliente = self._cliente_api()
        total, reintentos = "", 0
        for _ in range(6):  # como mucho 6 rondas de herramientas por petición
            try:
                respuesta, dicho = self._ronda(cliente, al_texto, al_frase, al_expresion, total)
            except ValueError:  # entrada de herramienta ilegible: se repite la ronda una vez
                reintentos += 1
                if reintentos > 1:
                    raise
                continue
            total += dicho
            self.historial.append({"role": "assistant", "content": respuesta.content})
            if respuesta.stop_reason == "refusal":
                return total or "Prefiero no responder a eso."
            if respuesta.stop_reason == "pause_turn":
                continue  # la búsqueda en internet sigue en el servidor: se reanuda sin añadir nada
            usos = [b for b in respuesta.content if b.type == "tool_use"]
            if not usos:
                return total
            if respuesta.stop_reason == "max_tokens":
                self.historial.pop()  # herramienta cortada a medias: no se puede continuar
                return total
            resultados = []
            for uso in usos:
                try:
                    r = self._ejecutar(uso.name, uso.input)
                    if r.resultados:
                        al_resultados(r.resultados)
                    resultados.append({"type": "tool_result", "tool_use_id": uso.id,
                                       "content": self._texto_resultado(r)})
                except Exception as e:
                    resultados.append({"type": "tool_result", "tool_use_id": uso.id,
                                       "content": f"Error: {e}", "is_error": True})
            self.historial.append({"role": "user", "content": resultados})
            if total and not total.endswith(" "):
                total += " "
        return total
