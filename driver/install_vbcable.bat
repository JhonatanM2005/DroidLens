@echo off
chcp 65001 >nul
title DroidLens - Instalador de Microfono Virtual (VB-Cable)
echo ===========================================================
echo   DroidLens - Instalador de Microfono Virtual (VB-Cable)
echo ===========================================================
echo.

:: Comprobar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Descargando paquete oficial VB-Audio Virtual Cable...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop'; " ^
    "$workDir = Join-Path $env:TEMP 'droidlens_vbcable'; " ^
    "$zipPath = Join-Path $workDir 'vbcable.zip'; " ^
    "New-Item -ItemType Directory -Path $workDir -Force | Out-Null; " ^
    "Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip' -OutFile $zipPath -UseBasicParsing; " ^
    "Expand-Archive -Path $zipPath -DestinationPath $workDir -Force; " ^
    "$exe = if ([Environment]::Is64BitOperatingSystem) { Join-Path $workDir 'VBCABLE_Setup_x64.exe' } else { Join-Path $workDir 'VBCABLE_Setup.exe' }; " ^
    "Write-Host 'Abriendo instalador oficial de VB-Cable (haz clic en Install Driver)...' -ForegroundColor Cyan; " ^
    "Start-Process -FilePath $exe -Verb RunAs -Wait"

if %errorlevel% equ 0 (
    echo.
    echo ===========================================================
    echo  [OK] Proceso finalizado.
    echo  1. En DroidLens selecciona: CABLE Input (VB-Audio Virtual Cable)
    echo  2. En Discord/Meet/Zoom selecciona como Microfono:
    echo     CABLE Output (VB-Audio Virtual Cable)
    echo ===========================================================
) else (
    echo.
    echo [ERROR] No se pudo descargar o ejecutar el instalador de VB-Cable.
    echo Verifica tu conexion a Internet o descargalo manualmente desde:
    echo https://vb-audio.com/Cable/
)

echo.
pause
