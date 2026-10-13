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
    if "%~1"=="" (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -Wait"
    ) else (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%~1' -Verb RunAs -Wait"
    )
    exit /b
)

cd /d "%~dp0"

echo [1/2] Registrando filtros DirectShow (UnityCapture)...
if exist "%~dp0UnityCaptureFilter32.dll" regsvr32.exe /s "%~dp0UnityCaptureFilter32.dll"
if exist "%~dp0UnityCaptureFilter64.dll" regsvr32.exe /s "%~dp0UnityCaptureFilter64.dll"

echo [2/2] Registrando driver nativo Windows 11 (DroidLensMF.dll)...
if exist "%~dp0DroidLensMF.dll" (
    net stop FrameServer /y >nul 2>&1
    if not exist "%ProgramData%\DroidLens" mkdir "%ProgramData%\DroidLens"
    copy /Y "%~dp0DroidLensMF.dll" "%ProgramData%\DroidLens\DroidLensMF.dll" >nul 2>&1
    icacls "%ProgramData%\DroidLens" /grant "*S-1-1-0:(OI)(CI)(RX)" "*S-1-5-19:(OI)(CI)(RX)" "*S-1-15-2-1:(OI)(CI)(RX)" >nul 2>&1
    icacls "%~dp0" /grant "*S-1-1-0:(OI)(CI)(RX)" "*S-1-5-19:(OI)(CI)(RX)" "*S-1-15-2-1:(OI)(CI)(RX)" >nul 2>&1
    if exist "%ProgramData%\DroidLens\DroidLensMF.dll" (
        regsvr32.exe /s "%ProgramData%\DroidLens\DroidLensMF.dll"
    ) else (
        regsvr32.exe /s "%~dp0DroidLensMF.dll"
    )
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

if "%~1" neq "--silent" (
    echo.
    pause
)
