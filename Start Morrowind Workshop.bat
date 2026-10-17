@echo off
title Morrowind Workshop
cd /d "%~dp0"
set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
rem The AI assistant needs Anthropic's Python library; install it once if missing.
%PY% -c "import anthropic" >nul 2>nul
if errorlevel 1 (
    echo Installing the library the AI assistant needs - one time only...
    %PY% -m pip install --quiet anthropic
)
%PY% "app\workshop.py"
if errorlevel 1 (
    echo.
    echo Morrowind Workshop could not start. Python 3 may be missing:
    echo get it from https://www.python.org/downloads/ and tick "Add to PATH".
    pause
)
