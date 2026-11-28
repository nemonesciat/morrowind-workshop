@echo off
title Morrowind Workshop
cd /d "%~dp0"
set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
rem (Python's own library is all it needs; zstandard, for compressed Blender files, is optional)
%PY% "app\workshop.py"
if errorlevel 1 (
    echo.
    echo Morrowind Workshop could not start. Python 3 may be missing:
    echo get it from https://www.python.org/downloads/ and tick "Add to PATH".
    pause
)
