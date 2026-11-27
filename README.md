# Jarvis 🐒

Asistente personal **100 % local y privado** para tu portátil con Windows. Te escucha por voz,
habla en español y tiene el avatar del mono holográfico de tu diseño, que cambia de expresión
según lo que está haciendo.

![Captura](docs/captura.png)

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

También puedes **escribir** las órdenes en la caja de abajo o pulsar el botón del micrófono.

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

## Privacidad y seguridad

- **Nada sale de tu computador.** El reconocimiento de voz (Vosk) y la voz (la de Windows)
  funcionan sin internet. Solo se usa internet una vez, al instalar, para descargar el modelo de voz.
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
   el modelo de voz en español (unos 40 MB).

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
- Para que la voz suene en español, Windows necesita una voz en español
  (Configuración → Hora e idioma → Voz → Agregar voces → Español).

## Personalizar

Todo lo configurable está en `jarvis/config.py`: tu nombre, la palabra de activación, las carpetas
donde busca y cuánto tiempo espera la orden. Los nombres de apps que reconoce de forma directa están
en `ALIAS_APPS` dentro de `jarvis/archivos.py`.

## Estructura

```
jarvis/
  main.py        ventana, bandeja del sistema y conexión de todo
  voz.py         escucha (Vosk, offline) y habla (voz de Windows)
  comandos.py    entiende la orden y la ejecuta
  archivos.py    buscar / abrir / mandar a la papelera, apps del menú Inicio
  seguridad.py   rutas protegidas, registro, Windows Defender, bloquear equipo
  ui/            interfaz con tu diseño (HTML + CSS + JS)
tests/           pruebas automáticas (python -m pytest)
```

## Próximos pasos

- Lenguaje de señas con la cámara (MediaPipe, también offline).
- Más órdenes: cerrar programas, mover y copiar archivos, controlar volumen, recordatorios.
- Un «cerebro» con IA local (por ejemplo Ollama) para entender frases más libres.
- Reconocimiento de tu voz para que solo te obedezca a ti.
