@echo off
setlocal enabledelayedexpansion

:: Setup and run Photo Feature Extractor via Docker Compose
::
:: Usage:
::   setup.bat                     # Start without mounting a host folder
::   setup.bat "C:\path\to\photos" # Mount a host folder into /photos in the container

set "FOLDER_PATH=%~1"
set "COMPOSE_OVERRIDE=docker-compose.override.yml"

:: Handle folder mounting via compose override
if not "%FOLDER_PATH%"=="" (
    if not exist "%FOLDER_PATH%" (
        echo Error: '%FOLDER_PATH%' is not a directory or does not exist.
        exit /b 1
    )

    :: Get absolute path
    pushd "%FOLDER_PATH%"
    set "ABS_FOLDER=%CD%"
    popd

    echo services: > "%COMPOSE_OVERRIDE%"
    echo   photo-agent: >> "%COMPOSE_OVERRIDE%"
    echo     volumes: >> "%COMPOSE_OVERRIDE%"
    echo       - "%ABS_FOLDER%:/photos" >> "%COMPOSE_OVERRIDE%"

    echo Mounting host folder: %ABS_FOLDER% -^> /photos
) else (
    if exist "%COMPOSE_OVERRIDE%" (
        del "%COMPOSE_OVERRIDE%"
    )
)

echo ================================================
echo Photo Feature Extractor - Docker Setup (Windows)
echo ================================================

:: Determine if 'docker compose' or 'docker-compose' is available
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "COMPOSE_CMD=docker compose"
) else (
    set "COMPOSE_CMD=docker-compose"
)

echo Using compose command: %COMPOSE_CMD%
echo.

:: Build and run
echo Building container and starting app...
%COMPOSE_CMD% up -d --build

echo.
echo ================================================
echo Done! The app is running.
echo ================================================
echo.
echo Open in your browser:
echo    http://localhost:8050
echo.

if not "%FOLDER_PATH%"=="" (
    echo Mounted folder inside container:
    echo    /photos
    echo.
)

echo View logs:
echo    %COMPOSE_CMD% logs -f
echo.
echo Stop the app:
echo    %COMPOSE_CMD% down
echo.

endlocal
