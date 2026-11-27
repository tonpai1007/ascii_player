@echo off
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
title ASCII Video Player
color 0A
echo.
echo  ======================================
echo    ASCII VIDEO PLAYER
echo    Powered by OpenCV + Loguru
echo  ======================================
echo.

rem Resolve a relative first argument against the launch directory before
rem cd'ing to the script directory (where ascii_player.yaml lives).
set "FIRST="
if not "%~1"=="" if exist "%~f1" set "FIRST=%~f1"
cd /d "%~dp0"

if "%~1"=="" (
    echo  No video specified. Opening TUI...
    echo.
    "C:\Users\Tonpa\AppData\Local\Programs\Python\Python312\python.exe" -m ascii_player -t
    goto :done
)

if defined FIRST (
    "C:\Users\Tonpa\AppData\Local\Programs\Python\Python312\python.exe" -m ascii_player "%FIRST%" %2 %3 %4 %5 %6 %7 %8 %9
) else (
    "C:\Users\Tonpa\AppData\Local\Programs\Python\Python312\python.exe" -m ascii_player %*
)

:done
echo.
pause
