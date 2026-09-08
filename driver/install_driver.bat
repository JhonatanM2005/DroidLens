@echo off
title AppCam - Instalador de Driver DirectShow
echo ===================================================
echo     AppCam - Instalador de Driver DirectShow
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

echo Registrando UnityCaptureFilter32.dll...
regsvr32.exe /s "%~dp0UnityCaptureFilter32.dll"

echo Registrando UnityCaptureFilter64.dll...
regsvr32.exe /s "%~dp0UnityCaptureFilter64.dll"

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo  [OK] Driver instalado y registrado con exito!
    echo  Dispositivo disponible: Unity Video Capture
    echo ===================================================
) else (
    echo.
    echo [ERROR] Hubo un problema al registrar las DLL.
)

echo.
pause
