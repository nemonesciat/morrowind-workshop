@echo off
title Morrowind Workshop
cd /d "%~dp0"
set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
rem The AI assistant needs Anthropic's Python library, and the Library's Blender (.blend) import
rem needs zstandard; install them once if missing.
%PY% -c "import anthropic, zstandard" >nul 2>nul
if errorlevel 1 (
    echo Installing the libraries the Workshop needs - one time only...
    %PY% -m pip install --quiet anthropic zstandard
)
%PY% "app\workshop.py"
if errorlevel 1 (
    echo.
    echo Morrowind Workshop could not start. Python 3 may be missing:
    echo get it from https://www.python.org/downloads/ and tick "Add to PATH".
    pause
)
