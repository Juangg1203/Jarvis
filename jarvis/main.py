"""Arranca Jarvis: ventana con el avatar, voz, conversación con Claude e icono en la bandeja."""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

if __package__ in (None, ""):  # permite ejecutar "python jarvis/main.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "jarvis"

import webview

from jarvis import ajustes, config, recordatorios
from jarvis.comandos import Cerebro, Respuesta
from jarvis.gemini import ConversadorGemini, ErrorGemini
from jarvis.ollama import ConversadorOllama
from jarvis import redactar
from jarvis.ia import Conversador
from jarvis.memoria import Memoria
from jarvis.rutinas import Rutinas
from jarvis import celular, control, gestos, identidad, internet, seguridad, vigilancia
from jarvis.texto import normalizar
from jarvis.voz import Hablante, Oyente

UI = Path(__file__).resolve().parent / "ui"


class Jarvis:
    def __init__(self):
        self.ventana = None
        self.ajustes = ajustes.cargar()
        self.agenda = recordatorios.Agenda(al_sonar=self._sonar)
        self.cerebro = Cerebro(agenda=self.agenda, memoria=Memoria(), rutinas=Rutinas())
        self._alarma_activa = None
        self.camara = gestos.Camara(al_gesto=self._gesto, al_estado=self._estado_camara)
        self._conversadores = {}
        self.conversador = self._conversador()
        self.hablante = Hablante(self.ajustes["voz_motor"], self.ajustes["voz_edge"], al_nivel=self._nivel)
        self.dormido = False
        self._lock = threading.Lock()
        self._ultimo_nivel = 0.0
        # v5: seguridad, celular
        self.identidad = identidad.Identidad()
        self._caras_det = None
        self.vigilante = vigilancia.Vigilante(self.camara, self.identidad,
                                              al_intruso=self._intruso, al_volver=self._dueno_volvio)
        self.monitor = vigilancia.Monitor(self._alerta_seguridad)
        self.monitor.activo = self.ajustes.get("avisos_seguridad", True)
        self.celular = None
        self._silencio = False      # True mientras responde al celular (no habla por los parlantes del PC)
        self._salida = None         # lo que se le responde al celular
        self._estado_ui = {"estado": "esperando", "expresion": "normal"}
        self._aprendiendo_voz, self._huellas_voz = 0, []
        self._dictado = None        # {"tipo": "documento"|"correo", "titulo": str, "partes": [...]}
        self._deletreo = ""
        self.cerebro.manejadores_extra += [self._ordenes_seguridad, self._ordenes_dictado]
        self.oyente = Oyente(
            al_cambiar_estado=self._estado_voz,
            al_recibir_orden=self._orden_de_voz,
            esta_hablando=self.hablante.hablando.is_set,
            al_oir_parcial=lambda t: self._ui(estado="escuchando", parcial=t),
        )

    # ---------- comunicación con la interfaz ----------
    def _ui(self, **datos):
        if "estado" in datos:
            self._estado_ui["estado"] = datos["estado"]
        if datos.get("expresion"):
            self._estado_ui["expresion"] = datos["expresion"]
        salida = self._salida
        if salida is not None:
            if datos.get("expresion"):
                salida["expresion"] = datos["expresion"]
            if datos.get("respuesta_parcial"):
                salida["respuesta"] = datos["respuesta_parcial"]
            for k in ("respuesta", "mensaje"):
                if datos.get(k):
                    salida["respuesta"] = (salida["respuesta"] + " " + datos[k]).strip() if k == "mensaje" else datos[k]
        if self.ventana:
            try:
                self.ventana.evaluate_js(f"window.jarvis && window.jarvis.actualizar({json.dumps(datos)})")
            except Exception:
                pass

    def _nivel(self, n):
        # El nivel del audio mueve la boca/brillo del avatar y la onda de voz.
        if abs(n - self._ultimo_nivel) > 0.03 or n == 0:
            self._ultimo_nivel = n
            if self.ventana:
                try:
                    self.ventana.evaluate_js(f"window.jarvis && window.jarvis.nivel({n:.2f})")
                except Exception:
                    pass

    def _estado_voz(self, estado):
        if estado == "escuchando":
            self.dormido = False
        if estado == "sin_voz":
            self._ui(estado="sin_voz", mensaje=self.oyente.error)
            return
        if estado == "esperando" and self.dormido:
            estado = "dormido"
        self._ui(estado=estado)

    def _al_terminar_de_hablar(self):
        if self._aprendiendo_voz and self.oyente.disponible:
            self.oyente.escuchar_ahora()  # esperando la siguiente frase para aprender tu voz
        elif self.dormido:
            self._ui(estado="dormido")
        elif self.ajustes.get("modo_conversacion") and self.oyente.disponible:
            self.oyente.escuchar_ahora()  # sigue la charla sin repetir "Jarvis"
        else:
            self._ui(estado="esperando")

    # ---------- recordatorios ----------
    def _sonar(self, item):
        """Llega la hora de un recordatorio, alarma o temporizador."""
        texto = recordatorios.texto_aviso(item)
        cara = "sorprendido" if item.get("tipo") != "recordatorio" else "guino"
        try:
            self.mostrar()
        except Exception:
            pass
        self.dormido = False
        self._ui(estado="hablando", expresion=cara, respuesta="⏰ " + texto, aviso=True,
                 avisos=len(self.agenda.pendientes()))
        self.hablante.decir(texto)
        self.hablante.despues(lambda: self._ui(estado="esperando"))
        if self.celular:
            self.celular.alerta("⏰ " + texto)
        if item.get("tipo") == "alarma":
            # La alarma se repite hasta 3 veces si no le haces caso.
            self._alarma_activa = item["id"]

            def repetir():
                for _ in range(2):
                    time.sleep(25)
                    if self._alarma_activa != item["id"]:
                        return
                    self._ui(estado="hablando", expresion="sorprendido")
                    self.hablante.decir(texto)
                    self.hablante.despues(lambda: self._ui(estado="esperando"))
                self._alarma_activa = None
            threading.Thread(target=repetir, daemon=True).start()

    def _avisos_cambiaron(self):
        self._ui(avisos=len(self.agenda.pendientes()))

    # ---------- cerebro ----------
    def _decir(self, texto):
        if not self._silencio:
            self.hablante.decir(texto)

    def _despues(self, funcion):
        if self._silencio:
            self._ui(estado="esperando")
        else:
            self.hablante.despues(funcion)

    def responder_celular(self, texto):
        """Orden que llega desde la app del celular: se hace en el PC y la respuesta vuelve al teléfono."""
        salida = self.ejecutar(texto, origen="celular") or {}
        return {"respuesta": salida.get("respuesta") or "Listo.", "expresion": salida.get("expresion") or "normal"}

    def ejecutar(self, texto: str, origen="pc"):
        self._alarma_activa = None  # cualquier orden apaga la alarma que esté sonando
        with self._lock:
            self._silencio = origen == "celular"
            self._salida = {"respuesta": "", "expresion": "normal"} if self._silencio else None
            try:
                self._ejecutar(texto, origen)
            finally:
                salida, self._salida, self._silencio = self._salida, None, False
        return salida

    def _ejecutar(self, texto, origen):
        if True:
            if not self._silencio:
                self.hablante.callar()
            self._ui(estado="pensando", orden=("📱 " if origen == "celular" else "") + texto)
            t = normalizar(texto)
            if self._dictado is not None:
                return self._seguir_dictado(texto, t)
            if re.search(r"\b(?:gestos|senas|camara)\b", t) and re.match(r"^(?:activa|enciende|prende|usa|desactiva|apaga|quita|deja de usar)", t):
                encender = bool(re.match(r"^(?:activa|enciende|prende|usa)", t))
                self.mostrar_u_ocultar_gestos(encender)
                msg = ("Listo, te estoy mirando para los gestos: palma abierta para hablarme, puño para silencio, "
                       "pulgar arriba o abajo para sí o no." if encender else "Apagué la cámara.")
                self._ui(estado="hablando", expresion="guino", respuesta=msg)
                self._decir(msg)
                self._despues(self._al_terminar_de_hablar)
                return
            self.conversador = self._conversador()
            hay_claude = self.conversador.disponible()  # Gemini o Claude, según Ajustes
            r = self.cerebro.procesar(texto, solo_ordenes=hay_claude)
            if not r.entendida and hay_claude:
                self._conversar(texto)
                return
            if not r.entendida:
                r.texto += " Si quieres conversar conmigo, pon tu clave gratis de Gemini en Ajustes."
            self.dormido = r.dormir
            self._ui(estado="hablando", expresion=r.expresion, respuesta=r.texto,
                     resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in r.resultados])
            self._decir(r.texto)
            self._despues(self._al_terminar_de_hablar)
            self._avisos_cambiaron()

    def _conversar(self, texto):
        import anthropic

        estado = {"empezo": False}

        def al_frase(frase):
            if not estado["empezo"]:
                estado["empezo"] = True
                self._ui(estado="hablando")
            self._decir(frase)

        try:
            self.conversador.responder(
                texto,
                al_texto=lambda t: self._ui(respuesta_parcial=t),
                al_frase=al_frase,
                al_expresion=lambda e: self._ui(estado="hablando", expresion=e),
                al_resultados=lambda res: self._ui(resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in res]),
            )
            self._ui(respuesta_fin=True)
            self._avisos_cambiaron()
        except ErrorGemini as e:
            otro = self._conversador("ollama")
            if (self.ajustes.get("proveedor") == "auto" and not estado["empezo"] and self.conversador is not otro
                    and otro.disponible()):
                print(f"[jarvis] Gemini falló ({e.mensaje}); respondo con Ollama.")
                self.conversador = otro
                return self._conversar(texto)
            self._avisar(e.mensaje, e.cara)
        except anthropic.AuthenticationError:
            self._avisar("Mi clave de Claude no es válida. Revísala en Ajustes.", "triste")
        except anthropic.PermissionDeniedError:
            self._avisar("Claude no me deja usar esa clave. Revisa tu cuenta en console.anthropic.com.", "triste")
        except anthropic.RateLimitError:
            self._avisar("Claude está saturado en este momento. Inténtalo en un ratito.", "preocupado")
        except anthropic.APIConnectionError:
            self._avisar("No tengo conexión a internet. Las órdenes del computador siguen funcionando.", "preocupado")
        except anthropic.APIStatusError as e:
            msg = "Se me acabó el saldo de Claude." if "credit" in str(e).lower() else "Claude tuvo un problema."
            self._avisar(msg + " Las órdenes del computador siguen funcionando.", "triste")
        except Exception as e:
            print(f"[jarvis] Error con Claude: {e}")
            self._avisar("Algo salió mal al pensar la respuesta.", "triste")
        self._despues(self._al_terminar_de_hablar)

    def _conversador(self, proveedor=None):
        """El cerebro para conversar que elegiste en Ajustes.

        «auto»: Gemini cuando hay internet y clave (rápido y gratis); Ollama cuando no hay internet."""
        proveedor = proveedor or self.ajustes.get("proveedor")
        if proveedor == "auto":
            proveedor = "gemini" if ajustes.clave_gemini() and internet.en_linea() else "ollama"
            if proveedor == "ollama" and not self._conversador("ollama").disponible():
                proveedor = "gemini"
        proveedor = proveedor if proveedor in ("claude", "ollama") else "gemini"
        if proveedor not in self._conversadores:
            clase = {"claude": Conversador, "ollama": ConversadorOllama}.get(proveedor, ConversadorGemini)
            self._conversadores[proveedor] = clase(self.cerebro)
        return self._conversadores[proveedor]

    def _precalentar(self):
        """Si Ollama puede tocar, lo carga en memoria ya, para que la primera respuesta no tarde."""
        if self.ajustes.get("proveedor") in ("ollama", "auto"):
            threading.Thread(target=lambda: self._conversador("ollama").precalentar(), daemon=True).start()

    def _avisar(self, texto, expresion):
        self._ui(estado="hablando", expresion=expresion, respuesta=texto)
        self._decir(texto)

    # ---------- seguridad: solo el dueño, vigilancia, USB y disco ----------
    def _anunciar(self, texto, cara="preocupado", hablar=True):
        """Aviso que Jarvis da por su cuenta (no es respuesta a una orden)."""
        self._ui(estado="hablando", expresion=cara, respuesta=texto, aviso=True)
        if self.celular:
            self.celular.alerta(texto)
        if hablar:
            self.hablante.decir(texto)
        self.hablante.despues(lambda: self._ui(estado="esperando"))

    def _alerta_seguridad(self, tipo, texto, dato):
        if tipo == "usb":
            def revisar():
                threading.Thread(target=lambda: self._anunciar(vigilancia.analizar_usb(dato), "guino"),
                                 daemon=True).start()
                return "Empiezo a revisarla. Te aviso cuando termine."
            r = self.cerebro.pedir_confirmacion(texto, revisar, "sorprendido")
            self._anunciar(r.texto, r.expresion)
        else:
            self._anunciar(texto, "preocupado")

    def _detector_caras(self):
        if self._caras_det is None:
            try:
                self._caras_det = identidad.Caras()
            except Exception as e:
                print(f"[seguridad] Sin detector de caras: {e}")
                return None
        return self._caras_det

    def _ve_al_dueno(self) -> bool:
        caras = self._detector_caras()
        if not caras or not caras.reconoce or not self.identidad.conoce_cara:
            return False
        cuadro = self.camara.foto()
        return cuadro is not None and any(self.identidad.es_mi_cara(h) for _, h in caras.huellas(cuadro))

    def _es_el_dueno(self, huella) -> bool:
        if not (self.identidad.conoce_voz or self.identidad.conoce_cara):
            return True  # aún no le has enseñado tu voz ni tu cara
        if self.identidad.conoce_voz and huella and self.identidad.es_mi_voz(*huella):
            return True
        return self._ve_al_dueno()

    def _orden_de_voz(self, texto, huella=None):
        if self._aprendiendo_voz:
            return self._muestra_de_voz(huella)
        if self.ajustes.get("solo_dueno") and not self._es_el_dueno(huella):
            seguridad.registrar("voz_rechazada", texto)
            msg = f"No reconozco tu voz. Solo le hago caso a {config.NOMBRE_USUARIO}."
            self._ui(estado="hablando", expresion="enojado", orden=texto, respuesta=msg)
            self.hablante.decir(msg)
            self.hablante.despues(lambda: self._ui(estado="esperando"))
            return
        self.ejecutar(texto)

    def _muestra_de_voz(self, huella):
        if huella and huella[1] >= identidad.Identidad.MIN_CUADROS_VOZ:
            self._huellas_voz.append(huella[0])
            self._aprendiendo_voz -= 1
            if not self._aprendiendo_voz:
                self.identidad.guardar_voz(self._huellas_voz)
                seguridad.registrar("voz_registrada", str(len(self._huellas_voz)))
                return self._anunciar("Listo, ya conozco tu voz. Activa «solo obedéceme a mí» cuando quieras.",
                                      "riendo")
            msg = ["Perfecto. Ahora otra frase, por ejemplo: hoy quiero escuchar música.",
                   "Muy bien. Una última: Jarvis, revisa mis recordatorios de mañana."][min(1, 2 - self._aprendiendo_voz)]
        else:
            msg = "Esa frase fue muy corta. Dime una un poco más larga."
        self._ui(estado="hablando", expresion="guino", respuesta=msg)
        self.hablante.decir(msg)
        self.hablante.despues(self.oyente.escuchar_ahora)

    def _aprender_cara(self):
        caras = self._detector_caras()
        if not caras or not caras.reconoce:
            return self._anunciar("Me faltan los modelos de caras. Vuelve a ejecutar instalar.bat.", "triste")
        huellas = []
        for _ in range(12):
            cuadro = self.camara.foto()
            encontradas = caras.huellas(cuadro) if cuadro is not None else []
            if len(encontradas) == 1:
                huellas.append(encontradas[0][1])
            if len(huellas) >= 5:
                break
            time.sleep(0.4)
        if len(huellas) < 3:
            return self._anunciar("No logré verte bien. Ponte frente a la cámara, con buena luz y solo tú, "
                                  "y dime otra vez «aprende mi cara».", "preocupado")
        self.identidad.guardar_cara(huellas)
        seguridad.registrar("cara_registrada", str(len(huellas)))
        self._anunciar("Listo, ya conozco tu cara.", "riendo")

    def _intruso(self, ruta):
        self._ui(intrusos=len(self.vigilante.fotos))
        if self.celular:
            self.celular.alerta("📸 Alguien está usando tu computador. Le tomé una foto y lo bloqueé.")
        seguridad.bloquear_equipo()

    def _dueno_volvio(self, fotos):
        n = len(fotos)
        texto = (f"Bienvenido, {config.NOMBRE_USUARIO}. Mientras no estabas no pasó nada." if not n else
                 f"Bienvenido, {config.NOMBRE_USUARIO}. Mientras no estabas vi a alguien "
                 f"{'una vez' if n == 1 else f'{n} veces'}. Guardé las fotos; di «muéstrame las fotos» para verlas.")
        self._ui(vigilando=False)
        self._anunciar(texto, "riendo" if not n else "preocupado")

    def vigilar(self, encender=True) -> str:
        if encender:
            try:
                self.vigilante.activar()
            except Exception as e:
                return f"No pude encender la cámara para vigilar: {e}"
            self._ui(vigilando=True)
            if self.celular:
                self.celular.alerta("🛡️ Vigilancia activada.")
            extra = "" if self.identidad.conoce_cara else " Como aún no conozco tu cara, cuando vuelvas dime «ya volví»."
            return ("Vigilancia activada. Tienes veinte segundos para irte. Si alguien usa el computador, "
                    "le tomo una foto y lo bloqueo." + extra)
        fotos = self.vigilante.desactivar()
        self._ui(vigilando=False)
        if not fotos:
            return "Vigilancia apagada. No pasó nada mientras no estabas."
        return (f"Vigilancia apagada. Tomé {len(fotos)} {'foto' if len(fotos) == 1 else 'fotos'} de alguien que usó "
                "el computador. Di «muéstrame las fotos» para verlas.")

    def ver_fotos(self) -> str:
        carpeta = vigilancia.carpeta_intrusos()
        if not carpeta.exists() or not any(carpeta.iterdir()):
            return "No hay fotos de intrusos."
        if sys.platform == "win32":
            os.startfile(str(carpeta))
        return "Te abrí la carpeta de fotos."

    def activar_celular(self, encender=True) -> str:
        if not encender:
            if self.celular:
                self.celular.detener()
            self.celular = None
            return "Apagué la app del celular."
        if not self.ajustes.get("codigo_celular"):
            self.ajustes = ajustes.guardar({"codigo_celular": celular.nuevo_codigo()})
        if self.celular is None:
            self.celular = celular.Servidor(
                self.responder_celular,
                lambda: {**self._estado_ui, "vigilando": self.vigilante.activa},
                self.ajustes["codigo_celular"])
        if not self.celular.iniciar():
            self.celular = None
            return "No pude abrir la conexión para el celular. ¿Otro programa usa el puerto?"
        return "La app del celular está lista. Abre Ajustes y escanea el código QR con tu celular."

    def _ordenes_seguridad(self, original, t, solo_ordenes):
        """Órdenes de seguridad y del celular (se revisan antes que las demás)."""
        if re.search(r"\b(?:aprende|aprender|memoriza|registra|graba|reconoce)\s+(?:a\s+)?(?:mi|como es mi)\s+voz\b", t):
            if not self.oyente.reconoce_hablante:
                return Respuesta("Me falta el modelo para reconocer voces. Vuelve a ejecutar instalar.bat.", "triste")
            self._aprendiendo_voz, self._huellas_voz = 3, []
            return Respuesta("Vamos a aprender tu voz. Dime tres frases, una a la vez. La primera: "
                             "hola Jarvis, soy yo y este es mi computador.", "guino")
        if re.search(r"\b(?:aprende|aprender|memoriza|registra|reconoce)\s+(?:a\s+)?mi\s+(?:cara|rostro)\b", t):
            threading.Thread(target=self._aprender_cara, daemon=True).start()
            return Respuesta("Mírame a la cámara unos segundos, sin moverte mucho.", "sorprendido")
        if m := re.search(r"\b(?:olvida|borra)\s+(?:mi|como es mi)\s+(voz|cara|rostro)\b", t):
            self.identidad.olvidar("voz" if m.group(1) == "voz" else "cara")
            return Respuesta(f"Listo, olvidé tu {m.group(1)}.", "normal")
        if re.search(r"\bsolo\s+(?:obedeceme|hazme caso|escuchame)\b|\b(?:obedeceme|hazme caso) solo a mi\b|\bactiva (?:el modo )?solo yo\b", t):
            if not (self.identidad.conoce_voz or self.identidad.conoce_cara):
                return Respuesta("Primero tengo que conocerte. Di «aprende mi voz» o «aprende mi cara».", "pensando")
            self.ajustes = ajustes.guardar({"solo_dueno": True})
            return Respuesta(f"Hecho. Desde ahora solo le hago caso a la voz de {config.NOMBRE_USUARIO}.", "guino")
        if re.search(r"\b(?:obedece|hazle caso|escucha) a todos\b|\bdesactiva (?:el modo )?solo yo\b", t):
            self.ajustes = ajustes.guardar({"solo_dueno": False})
            return Respuesta("Listo, ahora le hago caso a cualquiera.", "normal")
        if re.search(r"\b(?:vigila|cuida|protege)\s+(?:el|mi)\s+(?:computador|pc|portatil|equipo|computadora)\b"
                     r"|\b(?:activa|enciende|pon)\s+(?:la|el modo)\s+vigilancia\b|^modo vigilancia$", t):
            return Respuesta(self.vigilar(True), "guino")
        if re.search(r"\b(?:desactiva|apaga|quita)\s+(?:la\s+)?vigilancia\b|\bdeja de vigilar\b|^ya volvi\b|^volvi$", t):
            if not self.vigilante.activa:
                return Respuesta("La vigilancia no estaba activada." if "vigil" in t else "¡Qué bueno verte!", "riendo")
            return Respuesta(self.vigilar(False), "riendo")
        if re.search(r"\b(?:muestrame|ensename|abre|ver)\s+(?:las\s+)?fotos\b|\bfotos de (?:los )?intrusos\b", t):
            return Respuesta(self.ver_fotos(), "normal")
        if re.search(r"\b(?:revisa|analiza|escanea)\s+(?:la|las|mi|mis)\s+(?:memoria|memorias|usb)\b", t):
            unidades = list(vigilancia.unidades_removibles())
            if not unidades:
                return Respuesta("No veo ninguna memoria USB conectada.", "pensando")
            threading.Thread(target=lambda: self._anunciar(vigilancia.analizar_usb(unidades[-1]), "guino"),
                             daemon=True).start()
            return Respuesta("Empiezo a revisarla con el antivirus. Te aviso cuando termine.", "pensando")
        if re.search(r"\blibera(?:r)?\s+espacio\b|\blimpia(?:r)?\s+el\s+disco\b", t):
            return Respuesta(vigilancia.liberar_espacio(), "guino")
        if re.search(r"\b(?:espacio|como esta)\s+(?:en\s+)?(?:el\s+)?disco\b|\bdisco lleno\b", t):
            llenos = vigilancia.discos_llenos(umbral=1)
            if not llenos:
                return Respuesta("No pude leer el disco.", "pensando")
            u, usado, libres = llenos[0]
            return Respuesta(f"El disco {vigilancia.nombre_unidad(u)} está al {usado} por ciento y quedan {libres} gigas libres.",
                             "preocupado" if usado >= config.DISCO_LLENO_PORCENTAJE else "guino")
        if re.search(r"\b(?:activa|conecta|enciende|abre)\s+(?:la app del |el )?celular\b", t):
            self.ajustes = ajustes.guardar({"celular": True})
            return Respuesta(self.activar_celular(True), "guino")
        if re.search(r"\b(?:desactiva|desconecta|apaga)\s+(?:la app del |el )?celular\b", t):
            self.ajustes = ajustes.guardar({"celular": False})
            return Respuesta(self.activar_celular(False), "normal")
        return None

    # ---------- dictado de documentos y correos ----------
    def _ordenes_dictado(self, original, t, solo_ordenes):
        if re.search(r"^(?:vamos a |quiero )?deletre(?:ar|a)\b|^modo deletre", t):
            self._deletreo = ""
            self.camara.modo = "letras"
            self.camara.iniciar("gestos")
            return Respuesta("Modo deletrear activado. Haz las letras frente a la cámara, la mano abierta es un espacio, "
                             "y baja la mano tres segundos cuando termines.", "guino")
        m = re.match(r"^(?:quiero dictar|dicta(?:r)?|toma(?:r)? (?:una )?nota|empieza (?:un )?dictado|(escribe|escribeme|redacta|redactame))"
                     r"\s*(?:un |una |el |la )?(documento|nota|carta|correo|email|mail|texto)?"
                     r"(?:\s+(?:sobre|para|de|llamad[oa]|titulad[oa]|que diga)\s+(.+))?$", t)
        if not m:
            return None
        if m.group(1) and (solo_ordenes or m.group(3)) and self.conversador.disponible():
            return None  # «escribe una carta para mi profe…»: que la IA la redacte
        tipo = "correo" if m.group(2) in ("correo", "email", "mail") else "documento"
        titulo = (m.group(3) or "").strip()
        if titulo:
            titulo = re.split(r"(?i)\b(?:sobre|para|de|llamad[oa]|titulad[oa])\b\s+", original, maxsplit=1)[-1].strip()
        self._dictado = {"tipo": tipo, "titulo": titulo, "partes": []}
        return Respuesta(("Dicta tu correo." if tipo == "correo" else "Dicta tu documento.") +
                         " Di «coma», «punto» o «punto y aparte» para puntuar, «borra lo último» si me equivoco, "
                         "y «termina el dictado» cuando acabes.", "guino")

    def _seguir_dictado(self, texto, t):
        d = self._dictado
        if re.search(r"\b(?:cancela|olvida|descarta)\b.*\b(?:dictado|documento|correo)\b", t):
            self._dictado = None
            return self._responder(Respuesta("Dictado cancelado.", "normal"))
        if re.search(r"^borra (?:lo ultimo|la ultima frase)|^borra eso$", t):
            if d["partes"]:
                d["partes"].pop()
            return self._responder(Respuesta("Borrado. Sigue.", "normal"), seguir=True)
        if re.search(r"\b(?:termina|terminar|finaliza|acaba|fin del|guarda)\b.*\b(?:dictado|documento|correo|nota|texto)\b"
                     r"|^(?:listo|ya termine|eso es todo|fin)$", t):
            self._dictado = None
            cuerpo = redactar.puntuar(" ".join(d["partes"]))
            if not cuerpo:
                return self._responder(Respuesta("No dictaste nada, así que no guardé nada.", "pensando"))
            if d["tipo"] == "correo":
                r = self.cerebro.correo("", d["titulo"], cuerpo)
            else:
                r = self.cerebro.documento(d["titulo"] or "Dictado", cuerpo)
            return self._responder(r)
        d["partes"].append(texto.strip())
        self._ui(estado="escuchando", respuesta="✍️ " + redactar.puntuar(" ".join(d["partes"]))[-300:])
        if self.oyente.disponible and not self._silencio:
            self.oyente.escuchar_ahora()  # sigue escuchando sin decir nada
        return None

    def _responder(self, r, seguir=False):
        self._ui(estado="hablando", expresion=r.expresion, respuesta=r.texto,
                 resultados=[{"nombre": os.path.basename(p), "ruta": p} for p in r.resultados])
        self._decir(r.texto)
        self._despues(self.oyente.escuchar_ahora if seguir and self.oyente.disponible else self._al_terminar_de_hablar)

    # ---------- deletrear con la mano ----------
    def _letra(self, nombre):
        if nombre.startswith("letra_"):
            self._deletreo += " " if nombre == "letra_espacio" else nombre[6:]
            self._ui(gesto="✍️ " + self._deletreo.strip()[-24:])
            return
        if nombre == "fin_deletreo":
            palabra, self._deletreo = self._deletreo.strip(), ""
            self.camara.modo = "gestos"
            if not palabra:
                return
            self._ui(gesto="✍️ " + palabra)
            threading.Thread(target=self.ejecutar, args=(palabra.lower(),), daemon=True).start()

    # ---------- bandeja del sistema (segundo plano) ----------
    def mostrar(self):
        self._oculta = False
        self.ventana.show()
        self.ventana.restore()

    def _bandeja(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        icono = pystray.Icon(
            "Jarvis", Image.open(UI / "assets" / "icono.png"), "Jarvis",
            menu=pystray.Menu(
                pystray.MenuItem("Mostrar", lambda: self.mostrar(), default=True),
                pystray.MenuItem("Escuchar ahora", lambda: self.oyente.escuchar_ahora()),
                pystray.MenuItem("Salir", lambda i: (i.stop(), self.salir())),
            ),
        )
        icono.run_detached()

    def salir(self):
        self._saliendo = True
        try:
            self.ventana.destroy()
        finally:
            os._exit(0)

    def _al_cerrar(self):
        # Cerrar la ventana solo la oculta: Jarvis sigue escuchando en segundo plano.
        if getattr(self, "_saliendo", False):
            return True
        self.ventana.hide()
        return False

    # ---------- gestos (lenguaje de señas) ----------
    def _estado_camara(self, activa, error=""):
        self._ui(gestos_activos=activa)
        if error:
            self._ui(mensaje=error)

    def _gesto(self, nombre):
        if self.camara.modo == "letras":
            return self._letra(nombre)
        self._ui(gesto=gestos.NOMBRES.get(nombre, nombre))
        c = self.cerebro
        hay_pendiente = bool(c.pendiente_borrar or c.pendiente_accion)
        if nombre == "palma":
            self._alarma_activa = None
            self.hablante.callar()
            self.oyente.escuchar_ahora() if self.oyente.disponible else None
        elif nombre == "puno":
            self._alarma_activa = None
            self.hablante.callar()
            control.volumen(silenciar=True)
            self._ui(estado="esperando")
        elif nombre in ("pulgar_arriba", "pulgar_abajo") and hay_pendiente:
            self.ejecutar("sí" if nombre == "pulgar_arriba" else "no")
        elif nombre == "indice":
            control.volumen(cambio=+10)
        elif nombre == "dos":
            control.volumen(cambio=-10)
        elif nombre == "te_quiero":
            if getattr(self, "_oculta", False):
                self.mostrar()
            else:
                self._oculta = True
                self.ventana.hide()

    def mostrar_u_ocultar_gestos(self, encender=None):
        encender = (not self.camara.gestos_activos) if encender is None else encender
        if encender:
            self.camara.iniciar("gestos")
        else:
            self.camara.detener("gestos")
        return encender

    # ---------- arrastrar documentos a la ventana ----------
    def _activar_soltar_archivos(self):
        try:
            from webview.dom import DOMEventHandler

            def al_soltar(e):
                archivos_soltados = (e.get("dataTransfer") or {}).get("files") or []
                for a in archivos_soltados[:1]:
                    ruta = a.get("pywebviewFullPath")
                    if ruta:
                        threading.Thread(target=self.ejecutar, args=(f"resume el documento {ruta}",), daemon=True).start()

            self.ventana.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
            self.ventana.dom.document.events.drop += DOMEventHandler(al_soltar, True, True)
        except Exception as e:
            print(f"[jarvis] No se pudo activar arrastrar archivos: {e}")

    def iniciar(self):
        api = Api(self)
        self.ventana = webview.create_window(
            "Jarvis", str(UI / "index.html"), js_api=api,
            width=480, height=840, min_size=(400, 640), background_color="#02050c",
        )
        self.ventana.events.closing += self._al_cerrar

        def al_arrancar():
            self._bandeja()
            self._activar_soltar_archivos()
            self.oyente.iniciar()
            if self.ajustes.get("gestos_al_iniciar"):
                self.camara.iniciar("gestos")
            self.monitor.iniciar()
            if self.ajustes.get("celular"):
                self.activar_celular(True)
            self._precalentar()
            time.sleep(0.5)
            self._avisos_cambiaron()
            self._ui(estado="hablando", expresion="riendo")
            self.hablante.decir(f"Hola {config.NOMBRE_USUARIO}, estoy listo.")
            self.hablante.despues(lambda: (self._ui(estado="esperando"), self.agenda.iniciar()))

        webview.start(al_arrancar, debug="--debug" in sys.argv)


class Api:
    """Funciones que la interfaz (JavaScript) puede llamar."""

    def __init__(self, jarvis: Jarvis):
        self._j = jarvis

    def enviar_texto(self, texto):
        threading.Thread(target=self._j.ejecutar, args=(texto,), daemon=True).start()

    def escuchar(self):
        self._j._alarma_activa = None
        self._j.hablante.callar()
        self._j.oyente.escuchar_ahora()

    def callar(self):
        self._j.hablante.callar()

    def abrir_resultado(self, indice):
        self.enviar_texto(f"abre el {int(indice) + 1}")

    def ocultar(self):
        self._j.ventana.hide()

    def salir(self):
        self._j.salir()

    def gestos(self, encender=None):
        return self._j.mostrar_u_ocultar_gestos(encender)

    def nueva_conversacion(self):
        self._j.conversador.olvidar()

    # ---------- panel de recordatorios, rutinas y memoria ----------
    def leer_panel(self):
        import datetime as dt
        c = self._j.cerebro
        return {
            "avisos": [{"id": x["id"], "tipo": x["tipo"], "mensaje": x["mensaje"],
                        "cuando": recordatorios.describir(dt.datetime.fromisoformat(x["cuando"]))}
                       for x in self._j.agenda.pendientes()],
            "rutinas": c.rutinas.nombres(),
            "datos": [d["texto"] for d in c.memoria.datos],
            "resumenes": len(c.memoria.resumenes),
        }

    def cancelar_aviso(self, id_):
        self._j.agenda.cancelar(str(id_))
        self._j._avisos_cambiaron()
        return self.leer_panel()

    def olvidar_dato(self, indice):
        self._j.cerebro.memoria.olvidar(int(indice) + 1)
        return self.leer_panel()

    def ejecutar_rutina(self, nombre):
        self.enviar_texto(f"modo {nombre}")

    def leer_ajustes(self):
        a = ajustes.cargar()
        clave = ajustes.clave_claude()
        j = self._j
        datos = {
            "tiene_clave": bool(clave),
            "proveedor": a.get("proveedor", "gemini"),
            "ollama_modelo": a.get("ollama_modelo") or config.MODELO_OLLAMA,
            "tiene_gemini": bool(ajustes.clave_gemini()),
            "gemini_final": ajustes.clave_gemini()[-4:],
            "clave_final": clave[-4:] if clave else "",
            "voz_motor": a["voz_motor"],
            "modo_conversacion": a["modo_conversacion"],
            "gestos_al_iniciar": a.get("gestos_al_iniciar", False),
            "nombre": config.NOMBRE_USUARIO,
            "tema": a.get("tema", "aurora"),
            "solo_dueno": a.get("solo_dueno", False),
            "avisos_seguridad": a.get("avisos_seguridad", True),
            "conoce_voz": j.identidad.conoce_voz,
            "conoce_cara": j.identidad.conoce_cara,
            "vigilando": j.vigilante.activa,
            "celular": a.get("celular", False),
            "celular_activo": bool(j.celular and j.celular.activo),
        }
        if j.celular and j.celular.activo:
            datos["celular_direccion"] = j.celular.direccion
            datos["celular_qr"] = celular.qr_svg(j.celular.enlace())
        return datos

    def guardar_ajustes(self, cambios):
        cambios = dict(cambios or {})
        for campo in ("anthropic_api_key", "gemini_api_key"):
            if not str(cambios.get(campo) or "").strip():
                cambios.pop(campo, None)  # campo vacío = conservar la clave actual
            else:
                cambios[campo] = str(cambios[campo]).strip()
        cambios.pop("codigo_celular", None)
        antes = ajustes.cargar()
        a = ajustes.guardar(cambios)
        j = self._j
        j.ajustes = a
        j.hablante.motor = a["voz_motor"]
        j.monitor.activo = a.get("avisos_seguridad", True)
        if a.get("celular") != antes.get("celular") or (a.get("celular") and not j.celular):
            j.activar_celular(bool(a.get("celular")))
        if (a.get("proveedor"), a.get("ollama_modelo")) != (antes.get("proveedor"), antes.get("ollama_modelo")):
            j._precalentar()
        return self.leer_ajustes()

    def estado_ollama(self):
        from jarvis import ollama
        import shutil
        instalados = ollama.modelos_instalados()
        exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        return {"instalado": bool(instalados) or os.path.exists(exe) or bool(shutil.which("ollama")),
                "abierto": bool(instalados), "modelo": ollama.tiene(ollama.modelo(), instalados),
                "rapido": ollama.tiene(config.MODELO_OLLAMA_RAPIDO, instalados),
                "normal": ollama.tiene(config.MODELO_OLLAMA, instalados),
                "elegido": ollama.modelo(), "modelo_rapido": config.MODELO_OLLAMA_RAPIDO,
                "modelo_normal": config.MODELO_OLLAMA,
                "vision": ollama.tiene(config.MODELO_OLLAMA_VISION, instalados), "nombre": ollama.modelo()}

    def instalar_ollama(self, rapido=False):
        """Abre el instalador en una ventana aparte (descarga unos 3 GB; solo el cerebro rápido: 1 GB)."""
        import subprocess
        bat = config.RAIZ / "instalar_ollama.bat"
        if sys.platform == "win32" and bat.exists():
            extra = ["--rapido"] if rapido else []
            subprocess.Popen(["cmd", "/c", "start", "Instalar Ollama", str(bat), *extra], cwd=str(config.RAIZ))
            return True
        return False

    def nuevo_codigo_celular(self):
        """Cambia el código: los celulares vinculados dejan de funcionar hasta escanear el QR nuevo."""
        j = self._j
        j.ajustes = ajustes.guardar({"codigo_celular": celular.nuevo_codigo()})
        if j.celular:
            j.celular.codigo = j.ajustes["codigo_celular"]
        return self.leer_ajustes()

    def orden(self, texto):
        """Botones de seguridad del panel: se ejecutan como si los dijeras."""
        self.enviar_texto(texto)

    def vigilancia(self, encender=None):
        j = self._j
        encender = (not j.vigilante.activa) if encender is None else encender
        self.enviar_texto("vigila el computador" if encender else "desactiva la vigilancia")
        return encender

    def olvidar_identidad(self, que):
        self._j.identidad.olvidar(que)
        if not (self._j.identidad.conoce_voz or self._j.identidad.conoce_cara):
            self._j.ajustes = ajustes.guardar({"solo_dueno": False})
        return self.leer_ajustes()


def main():
    Jarvis().iniciar()


if __name__ == "__main__":
    main()
