@echo off
title ASCII Video Player
color 0A
echo.
echo  ======================================
echo    ASCII VIDEO PLAYER
echo    Powered by OpenCV + Loguru
echo  ======================================
echo.

if "%~1"=="" (
    echo  No video specified. Opening TUI...
    echo.
    "C:\Users\Tonpa\AppData\Local\Programs\Python\Python312\python.exe" -m ascii_player -t
    goto :done
)

"C:\Users\Tonpa\AppData\Local\Programs\Python\Python312\python.exe" -m ascii_player %*

:done
echo.
pause
