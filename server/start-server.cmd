@echo off
setlocal
set "PAUSE_ON_FAILURE="
if "%~1"=="" set "PAUSE_ON_FAILURE=1"
where py >nul 2>&1
if errorlevel 1 goto use_python
py -3 "%~dp0manage.py" %*
set "EXIT_STATUS=%errorlevel%"
goto finish
:use_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python "%~dp0manage.py" %*
set "EXIT_STATUS=%errorlevel%"
goto finish
:no_python
echo Python 3.8 or later is required. See docs/service-startup.md for installation.
set "EXIT_STATUS=1"
:finish
if not "%EXIT_STATUS%"=="0" if defined PAUSE_ON_FAILURE pause
exit /b %EXIT_STATUS%
