@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1

where py >nul 2>nul
if not errorlevel 1 goto :use_py
where python >nul 2>nul
if not errorlevel 1 goto :use_python
goto :python_error

:use_py
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto :python_error
if not exist ".venv-build\Scripts\python.exe" py -3 -m venv .venv-build
goto :venv_ready

:use_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto :python_error
if not exist ".venv-build\Scripts\python.exe" python -m venv .venv-build

:venv_ready
call .venv-build\Scripts\activate.bat
if not defined PIP_INDEX_URL set PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean GarminExporter.spec
if errorlevel 1 goto :error
if not exist "dist\GarminDataExporter.exe" goto :artifact_error

for %%A in ("dist\GarminDataExporter.exe") do set SIZE=%%~zA
if "%SIZE%"=="0" goto :artifact_error

echo.
echo 构建完成：dist\GarminDataExporter.exe
echo 文件大小：%SIZE% 字节
pause
exit /b 0

:python_error
echo.
echo 未找到 Python 3.12 或更高版本，请先安装 Python 并重试。
pause
exit /b 1

:artifact_error
echo.
echo 构建命令完成，但没有生成有效的 dist\GarminDataExporter.exe。
pause
exit /b 1

:error
echo.
echo 构建失败，请检查上方的错误信息。
pause
exit /b 1
