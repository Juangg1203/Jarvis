# Jarvis 🐒

Asistente personal para tu portátil con Windows. Te escucha por voz, te responde con una voz
masculina natural y tiene el avatar del mono holográfico de tu diseño en una escena 3D que se
mueve con su voz y cambia de expresión según lo que está haciendo.

Las órdenes del computador funcionan **sin internet**. Si añades una clave de Claude, además
puede **conversar contigo** de cualquier tema y entender órdenes dichas con tus propias palabras.

![Captura](docs/captura.png) ![Agenda](docs/agenda.png)

## Qué hace (versión 1)

| Dices… | Jarvis… |
|---|---|
| «Jarvis» | Despierta y te escucha (cara de sorpresa) |
| «Jarvis, busca el archivo tarea» | Busca en Escritorio, Documentos, Descargas, Imágenes, Música, Videos y OneDrive |
| «Abre el dos» | Abre el resultado número 2 de la última búsqueda |
| «Abre la calculadora» / «abre Chrome» / «abre Word» | Abre la aplicación (busca en todas las del menú Inicio) |
| «Abre la foto playa» | Si hay un solo archivo con ese nombre, lo abre directamente |
| «Elimina el uno» | Pregunta «¿Seguro?» y solo si dices **sí** lo manda a la **Papelera** |
| «Revisa la seguridad» | Te dice si Windows Defender y la protección en tiempo real están activos |
| «Bloquea el equipo» | Bloquea la sesión de Windows |
| «¿Qué hora es?» / «¿Qué día es?» | Te lo dice |
| «Duerme» | Se pone en modo dormido hasta que vuelvas a decir «Jarvis» |
| «Ayuda» | Te dice lo que sabe hacer |

También puedes **escribir** en la caja de abajo o tocar el **micrófono del centro**
(si Jarvis está hablando, tocarlo lo interrumpe).

Después de responder, Jarvis **sigue escuchando unos segundos** para que la charla fluya sin
repetir «Jarvis» cada vez (se puede apagar en Ajustes ⚙).

## Conversar (gratis con Gemini)

Con un "cerebro" de IA, Jarvis deja de ser solo un ejecutor de órdenes: charla contigo, responde
preguntas, busca en internet, recuerda lo que hablaron y entiende frases aunque el micrófono las
entienda a medias. También usa las órdenes del computador por ti. Para borrar o apagar, **siempre**
tienes que decir «sí» tú mismo.

**Gemini de Google (gratis, la opción por defecto):**

1. Entra en <https://aistudio.google.com> con tu cuenta de Google.
2. Toca **Get API key** → **Crear clave de API** (si te pide un proyecto, crea uno nuevo).
   La clave empieza por `AIza`. No necesitas tarjeta.
3. En Jarvis toca ⚙ **Ajustes** → «Cerebro para conversar: Gemini», pega la clave y pulsa **Guardar**.

El plan gratis tiene un límite de preguntas por minuto y por día. Si se acaba, Jarvis te lo dice y
sigue haciendo las órdenes del computador. Google puede usar lo que hablas en el plan gratis para
mejorar sus productos, así que no le cuentes datos delicados. El modelo (`gemini-flash-latest`) se
cambia en `jarvis/config.py`.

**Automático (recomendado):** usa Gemini cuando hay internet (rápido) y Ollama cuando no lo hay. Si Gemini
falla o se acaba la cuota gratis, esa respuesta la da Ollama.

**Ollama (gratis y sin internet):** la IA corre dentro de tu portátil y nada sale de él. Ejecuta
`instalar_ollama.bat` una vez (descarga Ollama y el modelo `qwen2.5:3b`, unos 2 GB) y en Ajustes elige
«Ollama». Es más lento y menos listo que Gemini, pero no tiene límites ni necesita conexión. En Ajustes puedes elegir
el cerebro «Rápido» (`qwen2.5:1.5b`, 1 GB), que responde más o menos el doble de rápido en portátiles sin
tarjeta gráfica. Jarvis lo deja cargado en memoria al abrirse, así la primera respuesta no tarda. Para que
también pueda mirar tu pantalla sin internet, instala el modelo de visión con
`instalar_ollama.bat --vision` (unos 3 GB más).

**Claude (de pago, opcional):** en <https://console.anthropic.com> cargas saldo y creas una clave
`sk-ant-`. En Ajustes eliges «Claude» y la pegas. Cada respuesta corta cuesta uno o dos centavos de
dólar.

Las claves se guardan solo en tu computador (`%LOCALAPPDATA%\Jarvis\ajustes.json`). Lo que hablas
viaja por internet a Google o a Anthropic; las órdenes locales no.

### Recordatorios, alarmas y temporizadores (sin internet)

| Dices… | Jarvis… |
|---|---|
| «Avísame en 20 minutos que saque la ropa» | Te lo recuerda en 20 minutos, en voz alta |
| «Recuérdame mañana a las 8 llamar a mamá» | Te lo dice mañana a las 8:00 |
| «Pon una alarma a las 6 y media» | Suena a las 6:30 (y se repite si no le haces caso) |
| «Pon un temporizador de 5 minutos» | Te avisa cuando acabe |
| «¿Qué recordatorios tengo?» | Te los lee numerados |
| «Cancela el recordatorio dos» / «cancela todos los recordatorios» | Los quita |

Se guardan en el disco: si apagas el portátil, al volver a encenderlo Jarvis te dice los que
vencieron mientras estaba apagado. La campana 🔔 de arriba muestra cuántos hay y te deja quitarlos.

### Rutinas (sin internet)

| Dices… | Jarvis… |
|---|---|
| «Modo estudio» | Abre Word, Chrome y Spotify, silencia las notificaciones y te avisa en 25 minutos para descansar |
| «Termina el modo estudio» / «modo normal» | Vuelve a activar las notificaciones |
| «Buenos días» | Te dice el día, la hora y tus recordatorios de hoy |
| «¿Qué rutinas tengo?» | Te las dice |

Con Claude puedes crear rutinas nuevas hablando: «crea un modo juego que abra Steam y Discord y
me avise en una hora». También puedes editarlas a mano en `%LOCALAPPDATA%\Jarvis\rutinas.json`.

### Resumir documentos

Arrastra un **PDF, Word (.docx), PowerPoint (.pptx) o .txt** a la ventana, o di
«resume el documento informe» (lo busca por nombre). Con Claude te hace un resumen de verdad y luego
puedes preguntarle cosas: «¿qué dice de las fechas?». Sin internet te da las frases más importantes
y los temas. Los PDF escaneados (solo imagen) no tienen texto y Jarvis te avisa.

### Controlar el PC (sin internet)

| Dices… | Jarvis… |
|---|---|
| «Sube el volumen», «volumen al 30», «silencio» | Cambia el volumen |
| «Baja el brillo», «brillo al 70» | Cambia el brillo de la pantalla |
| «Apaga el wifi», «enciende el wifi», «¿cómo está el wifi?» | Controla el wifi |
| «¿Cuánta batería tengo?» | Te dice la batería |
| «Apaga / reinicia / suspende el computador» | **Te pide confirmación** y apaga en 30 s |
| «Cancela el apagado» | Lo detiene |
| «Cierra Chrome» | Lo cierra con calma |
| «Fuerza el cierre de Word» | Lo cierra a la fuerza (pide confirmación) |
| «Cierra las aplicaciones que no responden» | Busca las colgadas y te pregunta |

Nunca cierra procesos de Windows ni a sí mismo.

### Lenguaje de señas con la cámara (sin internet)

Toca el botón ✋ arriba o di «activa los gestos». La cámara se procesa solo en tu portátil
(MediaPipe); no se graba ni se envía nada.

| Gesto | Qué hace |
|---|---|
| ✋ Mano abierta | Jarvis te escucha |
| ✊ Puño | Se calla y deja de escuchar |
| 👍 Pulgar arriba | «Sí» (para confirmar) |
| 👎 Pulgar abajo | «No» |
| ☝️ Índice | Sube el volumen |
| ✌️ Dos dedos | Baja el volumen |
| 🤟 Te quiero | Muestra u oculta la ventana |

Sostén el gesto casi un segundo. En Ajustes puedes hacer que se enciendan al abrir Jarvis.

### Seguridad (nuevo)

| Dices… | Jarvis… |
|---|---|
| «Aprende mi voz» | Te pide tres frases y guarda la huella de tu voz |
| «Aprende mi cara» | Te mira unos segundos por la cámara y guarda la huella de tu cara |
| «Solo obedéceme a mí» | Ignora las órdenes de voz de otras personas (acepta tu voz o tu cara frente a la cámara) |
| «Vigila el computador» (o el botón 🛡️) | Te da 20 segundos para irte. Si alguien usa el PC, le toma una foto y lo bloquea. Si te reconoce la cara al volver, se apaga solo y te cuenta |
| «Ya volví» / «Desactiva la vigilancia» | La apaga y te dice si vio a alguien |
| «Muéstrame las fotos» | Abre la carpeta de fotos de intrusos |
| «Revisa la memoria USB» | La analiza con Windows Defender |
| «¿Cómo está el disco?» / «Libera espacio» | Espacio libre / abre el Liberador de espacio |

Además avisa solo cuando conectas una memoria USB (y te ofrece revisarla) y cuando un disco pasa del
90 % (una vez al día). Lo que escribes en la ventana siempre se obedece: si estás frente al teclado, eres tú.
Las huellas de voz y cara son solo números guardados en tu portátil; nunca se guardan grabaciones ni fotos tuyas.

### Buscar en internet (nuevo)

«¿Qué clima hace en Bogotá?», «¿Va a llover mañana?», «Dame las noticias», «Noticias de fútbol»,
«Busca en internet…», «¿Quién es…?». Con Gemini o Claude, Jarvis busca y te lo cuenta en
voz. Sin clave usa directamente servicios gratis (Open-Meteo, Google Noticias y Wikipedia). Di «recuerda que vivo
en Bogotá» para que sepa tu ciudad.

### App del celular (nuevo)

1. En ⚙ Ajustes marca «Hablar con Jarvis desde el celular». La primera vez Windows pregunta por el
   firewall: deja marcadas las **redes privadas** y dale Permitir.
2. Escanea el código QR con la cámara del celular (debe estar en el mismo wifi).
3. En el navegador del celular, menú ⋮ → «Añadir a pantalla de inicio». Queda como una app.

Escribe o dicta con el micrófono del teclado; Jarvis hace la orden en el PC y te responde en el celular
(con voz si quieres). También te llegan las alertas: intrusos, memorias USB y recordatorios.
Solo funciona dentro del wifi de tu casa y cada celular necesita el código secreto del QR; tras 10 códigos
equivocados ese aparato queda bloqueado 10 minutos. «Cambiar código» desvincula todos los celulares.

### Apariencia (nuevo)

El holograma ahora respira, se balancea, mira a los lados y parpadea solo, y cambia de postura cuando
escucha, piensa o duerme. En Ajustes → Colores eliges el tema: Aurora (multicolor), Océano (el azul
original), Esmeralda o Atardecer. El color también cambia con el estado: verde al escucharte, violeta al
pensar y rojo cuando está vigilando.

### Memoria

| Dices… | Jarvis… |
|---|---|
| «Recuerda que mi equipo favorito es el Nacional» | Lo guarda para siempre |
| «¿Qué sabes de mí?» | Te dice lo que tiene anotado |
| «Olvida que…» | Lo borra |

Con Claude, además, guarda solo lo importante que le cuentas, hace un resumen de cada conversación
para acordarse la próxima vez, y puede buscar en lo que hablaron otros días («¿qué te dije la
semana pasada de mi examen?»). Todo se guarda solo en tu portátil, en `%LOCALAPPDATA%\Jarvis\`.
En la campana 🔔 ves lo que recuerda y puedes borrar cada dato. «¿De qué hablamos la última vez?»
funciona también sin internet, y «olvida todo» borra la memoria (pide confirmación).

### Expresiones del avatar

| Estado | Cara |
|---|---|
| En espera | Normal |
| Te está escuchando | Sorprendido |
| Pensando | Pensando |
| Respondiendo bien | Riendo / Guiño |
| Pide confirmación para borrar | Preocupado |
| Bloquea algo peligroso | Enojado |
| No encontró nada o falló | Triste |
| Modo dormido | Dormido |

Las imágenes están en `jarvis/ui/assets/expresiones/`. Si quieres cambiar alguna, reemplaza el PNG
con el mismo nombre.

## Oído preciso y documentos largos (v6.3)

- **Oído preciso (Whisper, sin internet):** Vosk sigue oyendo «Jarvis» al instante, pero cada orden la vuelve a
  escuchar Whisper, que entiende mucho mejor. Se instala solo con `instalar.bat` (unos 500 MB). Si tarda en tu
  portátil, en `jarvis/config.py` cambia `MODELO_WHISPER = "small"` por `"base"`.
- **Deja de escuchar cuando terminas de hablar:** mide el ruido de tu cuarto y corta tras 1 segundo de silencio
  (`SILENCIO_FIN_SEG` en `config.py`). Si te corta a mitad de frase, súbelo a 1.5.
- **Documentos largos sin esperar:** «crea un documento sobre el cambio climático» o «hazme un resumen de la
  Revolución Francesa». Jarvis te dice que ya está escribiendo, puedes seguir pidiéndole cosas, y te avisa cuando
  el Word esté listo en Documentos\Jarvis.

## Novedades de la versión 6

| Dile… | Qué hace |
|---|---|
| «ordena mis descargas por tipo» / «… por fecha» | Te dice cuántos archivos moverá y a qué carpetas, y espera tu «sí». Los que se están bajando no los toca. |
| «deshaz el orden» | Devuelve todo a donde estaba. |
| «pon Bad Bunny en YouTube» / «pon lofi en Spotify» | Busca y reproduce. «pausa», «siguiente», «anterior» controlan lo que suene. |
| «dicta un documento» | Escribe lo que dices («coma», «punto», «punto y aparte»). «borra lo último», «termina el dictado» lo guarda en Word en Documentos\Jarvis. |
| «escribe un correo a mi profe pidiendo permiso» | Te deja el correo listo en tu programa de correo. **Tú** lo envías. |
| «qué hay en mi pantalla» / «qué es este error» | Toma una captura **solo en ese momento** y se la muestra a la IA. |
| «léeme mis mensajes de WhatsApp» / «¿tengo correos nuevos?» | Lee las notificaciones de Windows. |
| «respóndele a Mamá que ya voy» | Copia la respuesta y abre WhatsApp: tú la pegas y la envías. |
| «vamos a deletrear» | Con la cámara, deletrea con las letras A B D F I L O S U V W Y (la mano abierta con el pulgar es un espacio). Si quitas la mano 3 segundos, termina. |

Jarvis nunca envía mensajes ni correos solo: siempre te los deja listos para que tú los mandes.
Para leer notificaciones, la primera vez Windows te pregunta si le das permiso.

## Privacidad y seguridad

- **Sin clave de Claude, nada sale de tu computador.** El reconocimiento de voz (Vosk) y la voz
  (Piper) funcionan sin internet. Solo se usa internet al instalar, para descargar los modelos.
- Con clave de Claude, solo lo que no es una orden local se envía a Claude para conversar.
- **Nunca borra para siempre**: todo va a la Papelera de reciclaje, y siempre pregunta antes.
- Si la respuesta no es un «sí» claro, **no borra nada**.
- Se niega a borrar dentro de Windows, Archivos de programa, AppData ni la carpeta de Jarvis.
- Cada acción queda anotada en `%LOCALAPPDATA%\Jarvis\registro.log` para que puedas revisarla.

## Instalación (una sola vez)

1. Instala **Python 3.10 o superior** desde <https://www.python.org/downloads/>.
   En el instalador marca la casilla **«Add python.exe to PATH»**.
2. Descarga este proyecto (botón verde **Code → Download ZIP** en GitHub) y descomprímelo,
   por ejemplo en `Documentos\Jarvis`.
3. Haz doble clic en **`instalar.bat`**. Tarda unos minutos: instala las librerías y descarga
   el reconocimiento de voz en español (unos 40 MB), la voz de Jarvis (unos 110 MB) y lo de la
   cámara para los gestos (unos 60 MB, opcional: si falla, todo lo demás funciona igual).

¿Ya tenías la versión anterior? Reemplaza los archivos y vuelve a ejecutar `instalar.bat`:
solo descarga lo nuevo.

## Uso

- Doble clic en **`iniciar.bat`**. Aparece la ventana del mono y Jarvis te saluda.
- Di **«Jarvis»** y después tu orden, o todo seguido: «Jarvis, abre la calculadora».
- Si cierras la ventana, Jarvis **sigue escuchando en segundo plano**. Lo verás como un icono
  del mono junto al reloj de Windows (puede estar en la flechita ^). Clic derecho → **Salir** para apagarlo.
- ¿Quieres que arranque solo al encender el portátil? Doble clic en `scripts\inicio_automatico.bat`.
- Si algo no funciona, abre **`iniciar_con_consola.bat`**: verás los mensajes de error.

### Consejos para la voz

- Habla claro y a distancia normal del micrófono.
- El modelo pequeño a veces entiende «Jarvis» como «yarvis» o «jarbis»; ya están contemplados en
  `jarvis/config.py` (`VARIANTES_ACTIVACION`). Si te entiende otra cosa, añádela ahí.
- La voz de Jarvis es **Piper** (`es_MX-claude-high`), una voz neuronal masculina que suena humana
  y funciona sin internet. En Ajustes puedes cambiar a «Más natural, con internet», que usa la voz
  de Microsoft Gonzalo (Colombia) y necesita conexión. Si ninguna funciona, usa la voz de Windows.

## Personalizar

Todo lo configurable está en `jarvis/config.py`: tu nombre, la palabra de activación, las carpetas
donde busca y cuánto tiempo espera la orden. Los nombres de apps que reconoce de forma directa están
en `ALIAS_APPS` dentro de `jarvis/archivos.py`.

## Estructura

```
jarvis/
  main.py        ventana, bandeja del sistema y conexión de todo
  voz.py         escucha (Vosk, offline) y habla (Piper / Edge / Windows) con nivel de audio
  comandos.py    órdenes locales: entiende la orden y la ejecuta
  ia.py          conversación con Claude en streaming, con las órdenes como herramientas
  ajustes.py     clave y preferencias guardadas en tu computador
  recordatorios.py  recordatorios, alarmas y temporizadores (entiende la hora en español)
  rutinas.py     rutinas como «modo estudio»
  memoria.py     datos que recuerda de ti y resúmenes de conversaciones
  archivos.py    buscar / abrir / mandar a la papelera, apps del menú Inicio
  seguridad.py   rutas protegidas, registro, Windows Defender, bloquear equipo
  control.py     volumen, brillo, wifi, batería, apagar, cerrar programas
  documentos.py  leer y resumir PDF, Word, PowerPoint y texto
  gestos.py      cámara compartida y reconocimiento de gestos de la mano (MediaPipe)
  identidad.py   huella de tu voz (Vosk) y de tu cara (OpenCV) para «solo obedéceme a mí»
  vigilancia.py  memorias USB, disco lleno y vigilancia con foto de intrusos
  internet.py    clima, noticias y preguntas sin clave de Claude
  celular.py     servidor local de la app del celular (con código secreto)
  gemini.py      conversación con Gemini (gratis)
  ollama.py      conversación con Ollama (gratis y sin internet)
  organizar.py   ordenar carpetas por tipo o fecha y deshacer
  musica.py      YouTube, Spotify y teclas multimedia
  redactar.py    documentos de Word y borradores de correo
  pantalla.py    captura de pantalla para preguntarle a la IA
  notificaciones.py  notificaciones de WhatsApp y correo
  ui/celular/    la página que abre el celular
  ui/            interfaz con tu diseño (HTML + CSS + JS)
tests/           pruebas automáticas (python -m pytest)
```

## Próximos pasos

- Letras con movimiento (J, Z) y gestos que tú mismo enseñes.
- Usar la app del celular fuera de casa (con un túnel seguro).
- Mover y copiar archivos por voz.
- Un oído más preciso (Whisper local) para que entienda mejor frases largas.
