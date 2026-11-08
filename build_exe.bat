@echo off
echo ════════════════════════════════════════
echo  Сборка DiffEditor.exe (PyInstaller)
echo ════════════════════════════════════════
echo.

python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo Ошибка установки PyInstaller
    pause
    exit /b 1
)

pyinstaller --onefile --windowed --name DiffEditor diffeditor.py
if errorlevel 1 (
    echo Ошибка сборки!
    pause
    exit /b 1
)

echo.
echo ════════════════════════════════════════
echo  Готово! Файл: dist\DiffEditor.exe
echo ════════════════════════════════════════
pause
