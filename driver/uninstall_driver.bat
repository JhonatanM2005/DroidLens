@echo off
title AppCam - Desinstalador de Driver DirectShow
echo ===================================================
echo    AppCam - Desinstalador de Driver DirectShow
echo ===================================================
echo.

:: Comprobar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo Desregistrando UnityCaptureFilter32.dll...
regsvr32.exe /u /s "%~dp0UnityCaptureFilter32.dll"

echo Desregistrando UnityCaptureFilter64.dll...
regsvr32.exe /u /s "%~dp0UnityCaptureFilter64.dll"

echo.
echo ===================================================
echo  [OK] Driver desinstalado con exito.
echo ===================================================
echo.
pause
