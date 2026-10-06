@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 构建 Markdown 思维导图 exe ===
python -m pip install --upgrade pillow pyinstaller
python build.py %*
if errorlevel 1 (
  echo.
  echo 构建失败，请检查上面的日志。
  pause
  exit /b 1
)
echo.
echo 完成。可执行文件位于 dist\MdMindMap.exe
pause
