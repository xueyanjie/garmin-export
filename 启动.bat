@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 bootstrap.py
    goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python bootstrap.py
    goto :done
)

echo.
echo Python 3.12+ was not found.
echo Please install it from https://www.python.org/downloads/
echo On Windows you can also run: winget install Python.Python.3.12
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:done
if errorlevel 1 pause
endlocal
