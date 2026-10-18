@echo off
chcp 65001 >nul
echo Instalando las librerias de Python que usa el kit de modding (numpy, Pillow, scipy)...
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m pip install --user -r "%~dp0requirements.txt"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo No se encuentra Python. Instalalo desde https://www.python.org/downloads/
    echo y marca "Add python.exe to PATH". Luego vuelve a abrir este archivo.
    pause
    exit /b 1
  )
  python -m pip install --user -r "%~dp0requirements.txt"
)
echo.
if errorlevel 1 (
  echo Algo fallo. Revisa el mensaje de arriba.
) else (
  echo Listo. Ya puedes abrir dbz3.exe y usar las pestanas de modding.
)
pause
