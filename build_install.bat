@echo off
rem Builds and installs RefCanvas in one go: stages src into plugins\refcanvas_plugin, then copies it into Painter's python plugins folder.
setlocal
cd /d "%~dp0"
set "PAUSE_CMD=pause"
if /i "%~1"=="--no-pause" set "PAUSE_CMD=ver >nul"
where python >nul 2>nul
if errorlevel 1 (
  echo [build] python not found on PATH
  goto fail
)
if not exist "%~dp0src\main.py" (
  echo [build] src\main.py missing
  goto fail
)
if not exist "%~dp0plugins\refcanvas_plugin" mkdir "%~dp0plugins\refcanvas_plugin"
for %%F in ("%~dp0src\*.py") do copy /y "%%F" "%~dp0plugins\refcanvas_plugin\" >nul
if errorlevel 1 goto fail
if not exist "%~dp0plugins\refcanvas_plugin\__init__.py" (
  echo [build] plugins\refcanvas_plugin\__init__.py missing
  goto fail
)
if not exist "%~dp0plugins\refcanvas_plugin\main.py" (
  echo [build] plugins\refcanvas_plugin\main.py missing
  goto fail
)
if exist "%~dp0plugins\refcanvas_plugin\__pycache__" rmdir /s /q "%~dp0plugins\refcanvas_plugin\__pycache__"
echo [build] OK - plugins\refcanvas_plugin

set "SRC=%~dp0plugins\refcanvas_plugin"
set "DEST=%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\refcanvas_plugin"
if not exist "%DEST%" mkdir "%DEST%"
for %%F in ("%SRC%\*.py") do copy /y "%%F" "%DEST%\" >nul
if errorlevel 1 (
  echo [install] module copy failed - close Painter and retry
  %PAUSE_CMD%
  exit /b 1
)
for %%F in ("%DEST%\*.py") do if not exist "%SRC%\%%~nxF" del /q "%%F"
echo [install] installed RefCanvas to:
echo [install]   %DEST%
echo [install] restart Painter, then open the REFCANVAS dock.
%PAUSE_CMD%
exit /b 0
:fail
echo [build] BUILD FAILED
%PAUSE_CMD%
exit /b 1
