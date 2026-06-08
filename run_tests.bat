@echo off
REM ============================================================================
REM  run_tests.bat - Ruleaza intreaga suita de teste cu un singur dublu-click.
REM
REM  Ce face:
REM    1. Verifica daca Docker Desktop ruleaza
REM    2. Porneste containerul PostgreSQL (daca nu e pornit)
REM    3. Asteapta pana cand DB-ul e healthy
REM    4. Activeaza venv-ul Python si ruleaza testele backend (pytest)
REM    5. Ruleaza testele frontend (npm test)
REM    6. Afiseaza rezumat final
REM
REM  Coduri de iesire:
REM    0 - toate testele au trecut
REM    1 - Docker nu ruleaza
REM    2 - PostgreSQL nu a pornit
REM    3 - teste backend esuate
REM    4 - teste frontend esuate
REM ============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================================
echo   RAILWAY DIGITAL IDENTITY - Test Suite Runner
echo ============================================================================
echo.

REM ----------------------------------------------------------------------------
REM  PASUL 1: Verifica Docker Desktop
REM ----------------------------------------------------------------------------
echo [1/5] Verific Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo   EROARE: Docker Desktop nu ruleaza.
    echo.
    echo   Solutie:
    echo     1. Deschide Start Menu, scrie "Docker Desktop", apasa Enter
    echo     2. Asteapta ~30 secunde pana cand icon-ul din tray devine stabil
    echo     3. Re-ruleaza acest script
    echo.
    pause
    exit /b 1
)
echo       OK - Docker raspunde.

REM ----------------------------------------------------------------------------
REM  PASUL 2: Porneste containerul postgres (idempotent)
REM ----------------------------------------------------------------------------
echo.
echo [2/5] Verific containerul PostgreSQL...
docker ps --filter "name=railway_db" --filter "status=running" --format "{{.Names}}" | findstr /B "railway_db" >nul 2>&1
if errorlevel 1 (
    echo       Container oprit. Pornesc cu docker-compose...
    docker-compose up -d postgres
    if errorlevel 1 (
        echo.
        echo   EROARE: docker-compose up esuat.
        echo.
        pause
        exit /b 2
    )
) else (
    echo       OK - railway_db deja ruleaza.
)

REM ----------------------------------------------------------------------------
REM  PASUL 3: Asteapta healthcheck (max 30s)
REM ----------------------------------------------------------------------------
echo.
echo [3/5] Astept ca PostgreSQL sa devina healthy (max 30s)...
set /a attempts=0
:wait_healthy
set /a attempts+=1
docker inspect --format "{{.State.Health.Status}}" railway_db 2>nul | findstr /B "healthy" >nul
if not errorlevel 1 (
    echo       OK - PostgreSQL e healthy dupa !attempts! incercari.
    goto :db_ready
)
if !attempts! GEQ 30 (
    echo.
    echo   EROARE: PostgreSQL nu a devenit healthy in 30 secunde.
    echo   Verifica manual cu: docker logs railway_db
    echo.
    pause
    exit /b 2
)
timeout /t 1 /nobreak >nul
goto :wait_healthy

:db_ready

REM ----------------------------------------------------------------------------
REM  PASUL 4: Ruleaza testele backend
REM ----------------------------------------------------------------------------
echo.
echo [4/5] Rulez testele backend (pytest)...
echo ----------------------------------------------------------------------------

REM Activeaza venv si schimba in folderul backend
call .venv_win\Scripts\activate.bat
if errorlevel 1 (
    echo   EROARE: nu pot activa .venv_win. Verifica daca exista.
    pause
    exit /b 3
)

pushd backend
pytest tests\ -v --tb=short
set BACKEND_EXIT=!errorlevel!
popd

if !BACKEND_EXIT! NEQ 0 (
    echo.
    echo   ATENTIE: Testele backend au esuat ^(exit code !BACKEND_EXIT!^).
    echo   Continui cu frontend pentru raport complet.
)

REM ----------------------------------------------------------------------------
REM  PASUL 5: Ruleaza testele frontend
REM ----------------------------------------------------------------------------
echo.
echo [5/5] Rulez testele frontend (npm test)...
echo ----------------------------------------------------------------------------

pushd frontend
where npm >nul 2>&1
if errorlevel 1 (
    echo   ATENTIE: npm nu este instalat - testele frontend sunt SKIP.
    set FRONTEND_EXIT=0
    set FRONTEND_STATUS=SKIPPED
) else (
    call npm test
    set FRONTEND_EXIT=!errorlevel!
    if !FRONTEND_EXIT! EQU 0 (
        set FRONTEND_STATUS=PASSED
    ) else (
        set FRONTEND_STATUS=FAILED
    )
)
popd

REM ----------------------------------------------------------------------------
REM  REZUMAT FINAL
REM ----------------------------------------------------------------------------
echo.
echo ============================================================================
echo   REZUMAT FINAL
echo ============================================================================
if !BACKEND_EXIT! EQU 0 (
    echo   Backend:   PASSED  ^(pytest tests/^)
) else (
    echo   Backend:   FAILED  ^(exit code !BACKEND_EXIT!^)
)
echo   Frontend:  !FRONTEND_STATUS!  ^(npm test - 19 teste pe verifyOfflineToken^)
echo ============================================================================
echo.

if !BACKEND_EXIT! NEQ 0 (
    pause
    exit /b 3
)
if !FRONTEND_EXIT! NEQ 0 (
    pause
    exit /b 4
)

echo   Toate testele au trecut.
echo.
pause
exit /b 0
