@echo off
python diffeditor.py
if errorlevel 1 (
    echo.
    echo Ошибка: Python не найден или произошла ошибка запуска.
    echo Установите Python 3.10+ с сайта https://python.org/downloads/
    echo При установке отметьте "Add Python to PATH"
    pause
)
