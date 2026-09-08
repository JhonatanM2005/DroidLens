@echo off
title DroidLens - Compilador de APK Android
echo ===================================================
echo     DroidLens - Compilador de APK Android
echo ===================================================
echo.
echo 1. Si tienes Android Studio instalado:
echo    Abre Android Studio -> 'Open Project' -> selecciona la carpeta 'android'.
echo    Haz clic en 'Run' para instalarlo directamente en tu celular por USB.
echo.
echo 2. O compila desde linea de comandos con Gradle:
echo.
cd /d "%~dp0..\android"

if exist gradlew.bat (
    call gradlew.bat assembleDebug
) else (
    gradle assembleDebug
)

echo.
pause
