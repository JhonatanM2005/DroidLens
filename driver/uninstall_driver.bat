@echo off
title DroidLens - Desinstalador de Drivers de Camara Virtual
echo ===================================================
echo  DroidLens - Desinstalador de Drivers de Camara Virtual
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

echo Desregistrando DroidLensMF.dll...
if exist "%~dp0DroidLensMF.dll" regsvr32.exe /u /s "%~dp0DroidLensMF.dll"

echo Desregistrando UnityCaptureFilter32.dll y UnityCaptureFilter64.dll...
if exist "%~dp0UnityCaptureFilter32.dll" regsvr32.exe /u /s "%~dp0UnityCaptureFilter32.dll"
if exist "%~dp0UnityCaptureFilter64.dll" regsvr32.exe /u /s "%~dp0UnityCaptureFilter64.dll"

echo.
echo ===================================================
echo  [OK] Drivers desinstalados con exito.
echo ===================================================
if "%1" neq "--silent" (
    echo.
    pause
)
