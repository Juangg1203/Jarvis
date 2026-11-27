@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ollama: la IA gratis que funciona sin internet ===
echo Necesita unos 3 GB de espacio (y 3 GB mas si quieres que mire la pantalla sin internet).
echo.
set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA%" goto modelo
where ollama >nul 2>nul && (set "OLLAMA=ollama" & goto modelo)
echo Instalando Ollama...
winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
if not exist "%OLLAMA%" (
  where ollama >nul 2>nul && (set "OLLAMA=ollama") || (
    echo No se pudo instalar con winget. Descargalo de https://ollama.com/download y vuelve a abrir este archivo.
    pause & exit /b 1
  )
)
:modelo
echo Abriendo Ollama...
start "" "%OLLAMA%" serve >nul 2>nul
timeout /t 5 >nul
for /f "usebackq delims=" %%m in (`.venv\Scripts\python.exe -c "from jarvis import config; print(config.MODELO_OLLAMA)"`) do set "MODELO=%%m"
if "%MODELO%"=="" set "MODELO=qwen2.5:3b"
for /f "usebackq delims=" %%m in (`.venv\Scripts\python.exe -c "from jarvis import config; print(config.MODELO_OLLAMA_RAPIDO)"`) do set "RAPIDO=%%m"
if "%RAPIDO%"=="" set "RAPIDO=qwen2.5:1.5b"
if /i "%1"=="--rapido" goto rapido
echo Descargando el cerebro %MODELO% (unos 2 GB, solo esta vez)...
"%OLLAMA%" pull %MODELO% || (echo No se pudo descargar el modelo. & pause & exit /b 1)
:rapido
echo Descargando el cerebro rapido %RAPIDO% (1 GB): responde mas rapido en portatiles sin tarjeta grafica...
"%OLLAMA%" pull %RAPIDO%
echo.
if /i "%1"=="--rapido" goto fin
if /i "%1"=="--sin-pausa" goto fin
if /i "%1"=="--vision" goto vision
choice /c SN /m "Quieres tambien el modelo para mirar la pantalla sin internet (3 GB)"
if errorlevel 2 goto fin
:vision
for /f "usebackq delims=" %%m in (`.venv\Scripts\python.exe -c "from jarvis import config; print(config.MODELO_OLLAMA_VISION)"`) do set "VISION=%%m"
if "%VISION%"=="" set "VISION=qwen2.5vl:3b"
"%OLLAMA%" pull %VISION%
:fin
echo.
echo Listo. En Jarvis abre Ajustes y elige "Automatico" u "Ollama". En Ollama puedes elegir "Rapido".
if /i not "%1"=="--sin-pausa" pause
