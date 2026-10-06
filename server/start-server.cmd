@echo off
setlocal
where py >nul 2>&1
if errorlevel 1 goto use_python
py -3 "%~dp0manage.py" %*
exit /b %errorlevel%
:use_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python "%~dp0manage.py" %*
exit /b %errorlevel%
:no_python
echo Python 3.8 or later is required. Install Python and try again.
exit /b 1
