@echo off
title DroidLens - Instalador de Drivers de Camara Virtual
echo ===================================================
echo   DroidLens - Instalador de Drivers de Camara Virtual
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

echo [1/2] Registrando filtros DirectShow (UnityCapture)...
if exist "%~dp0UnityCaptureFilter32.dll" regsvr32.exe /s "%~dp0UnityCaptureFilter32.dll"
if exist "%~dp0UnityCaptureFilter64.dll" regsvr32.exe /s "%~dp0UnityCaptureFilter64.dll"

echo [2/2] Registrando driver nativo Windows 11 (DroidLensMF.dll)...
if exist "%~dp0DroidLensMF.dll" (
    regsvr32.exe /s "%~dp0DroidLensMF.dll"
)

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo  [OK] Drivers instalados y registrados con exito!
    echo  - Windows 11 Nativo: DroidLens Virtual Camera
    echo  - DirectShow:        Unity Video Capture
    echo ===================================================
) else (
    echo.
    echo [ERROR] Hubo un problema al registrar las DLL.
)

if "%1" neq "--silent" (
    echo.
    pause
)
