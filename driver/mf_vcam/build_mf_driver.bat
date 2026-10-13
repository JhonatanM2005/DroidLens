@echo off
setlocal
cd /d "%~dp0"

echo [DroidLensMF] Compilando DroidLensMF.dll (x64) con MSVC...
cl.exe /nologo /std:c++17 /O2 /MT /LD /EHsc DroidLensMF.cpp /Fe:..\DroidLensMF.dll /link /DEF:DroidLensMF.def mfplat.lib mfuuid.lib mf.lib shlwapi.lib ole32.lib advapi32.lib user32.lib
if %errorlevel% neq 0 (
    echo [ERROR] Fallo la compilacion de DroidLensMF.dll
    exit /b %errorlevel%
)

del /q *.obj *.exp *.lib 2>nul
echo [OK] driver\DroidLensMF.dll generado con exito.
exit /b 0
