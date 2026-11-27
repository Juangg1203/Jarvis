@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalando Jarvis ===
where python >nul 2>nul || (echo Necesitas Python 3.10 o superior: https://www.python.org/downloads/ & echo Marca "Add python.exe to PATH" al instalarlo. & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Hubo un error instalando las librerias. & pause & exit /b 1)
python scripts\descargar_modelo.py || (echo No se pudo descargar el modelo de voz. & pause & exit /b 1)
echo.
echo Listo. Ahora abre iniciar.bat para encender a Jarvis.
pause
