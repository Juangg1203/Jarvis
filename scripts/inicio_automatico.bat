@echo off
rem Crea un acceso directo en la carpeta Inicio para que Jarvis arranque con Windows.
set "DESTINO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk"
set "RAIZ=%~dp0.."
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%DESTINO%'); $s.TargetPath='%RAIZ%\.venv\Scripts\pythonw.exe'; $s.Arguments='-m jarvis.main'; $s.WorkingDirectory='%RAIZ%'; $s.IconLocation='%RAIZ%\jarvis\ui\assets\icono.ico'; $s.Save()"
echo Jarvis arrancara solo cada vez que enciendas el computador.
echo Para quitarlo, borra: %DESTINO%
pause
