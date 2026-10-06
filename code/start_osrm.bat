@echo off
REM Startet beide OSRM-Server fuer mit_fahr_prj
REM   Auto:       C:\osrm\wup_duess_driving  -> http://localhost:5000
REM   Fussgaenger: C:\osrm\wup_duess_walking -> http://localhost:5001
REM Dateiname (.osrm) und Algorithmus (ch/mld) werden automatisch erkannt.

setlocal
call :start osrm-drive "C:\osrm\wup_duess_driving" 5000 || goto :fail
call :start osrm-walk  "C:\osrm\wup_duess_walking" 5001 || goto :fail

echo.
echo Warte 10 Sekunden, bis die Server geladen sind...
timeout /t 10 /nobreak >nul

echo.
echo --- Test Auto (5000) ---
curl -s "http://localhost:5000/route/v1/driving/7.15,51.25;6.78,51.22?overview=false"
echo.
echo --- Test Fussgaenger (5001) ---
curl -s "http://localhost:5001/route/v1/walking/6.78,51.20;6.78,51.21?overview=false"
echo.
echo.
echo Wenn beide Antworten "code":"Ok" enthalten: py main.py
goto :eof

:start
set NAME=%1
set DIR=%~2
set PORT=%3
set OSRM=
for %%f in ("%DIR%\*.osrm") do set OSRM=%%~nxf
if not defined OSRM (
    echo FEHLER: keine .osrm-Datei in %DIR% gefunden
    exit /b 1
)
set ALGO=ch
if exist "%DIR%\%OSRM%.mldgr" set ALGO=mld
if "%ALGO%"=="ch" if not exist "%DIR%\%OSRM%.hsgr" (
    echo FEHLER: %DIR% enthaelt weder .hsgr noch .mldgr - Karten nicht fertig vorbereitet
    exit /b 1
)

REM alte Container auf diesem Port / mit diesem Namen entfernen
for /f %%c in ('docker ps -q --filter "publish=%PORT%"') do docker stop %%c >nul
docker rm -f %NAME% >nul 2>&1

echo Starte %NAME%: %OSRM% (%ALGO%) auf Port %PORT%
docker run -d --name %NAME% -p %PORT%:5000 -v "%DIR%":/data osrm/osrm-backend osrm-routed --algorithm %ALGO% /data/%OSRM% >nul
exit /b %errorlevel%

:fail
echo.
echo Abgebrochen. Siehe Fehler oben.
exit /b 1
