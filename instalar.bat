@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalando Jarvis ===
where python >nul 2>nul || (echo Necesitas Python 3.10 o superior: https://www.python.org/downloads/ & echo Marca "Add python.exe to PATH" al instalarlo. & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Hubo un error instalando las librerias. & pause & exit /b 1)
echo Instalando la camara: gestos, tu cara y vigilancia (opcional)...
pip install "opencv-python>=4.9" || echo Aviso: no se pudo instalar la camara.
pip install -r requirements-gestos.txt || echo Aviso: no se pudieron instalar los gestos. Jarvis funciona igual sin ellos.
echo Instalando el lector de notificaciones (opcional)...
pip install -r requirements-extra.txt || echo Aviso: no se pudo instalar el lector de notificaciones.
python scripts\descargar_modelo.py || (echo No se pudo descargar los modelos de voz. & pause & exit /b 1)
echo.
echo Listo. Ahora abre iniciar.bat para encender a Jarvis.
pause
