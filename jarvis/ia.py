"""Conversación con Claude. Jarvis le pasa lo que dices y Claude puede usar las órdenes locales.

Solo se usa cuando hay una clave de API y conexión. Las órdenes locales (abrir, buscar, borrar...)
siguen funcionando sin internet; borrar siempre necesita tu «sí» en voz alta, aunque lo pida Claude.
"""
import datetime
import re

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
errores; interpreta la intención más probable."""

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
for _h in HERRAMIENTAS:
    _h["eager_input_streaming"] = True


class Conversador:
    def __init__(self, cerebro: Cerebro):
        self.cerebro = cerebro
        self.historial: list = []
        self._cliente = None
        self._clave = None

    def disponible(self) -> bool:
        return bool(ajustes.clave_claude())

    def olvidar(self):
        self.historial = []

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
            system=SISTEMA,
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
        if len(self.historial) > config.MAX_MENSAJES_HISTORIAL:
            self.historial = []
        ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self.historial.append({"role": "user", "content": f"[{ahora}] {texto}"})
        try:
            return self._conversar(al_texto, al_frase, al_expresion, al_resultados)
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
