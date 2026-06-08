@echo off
REM ============================================================================
REM  run_tests.bat - Ruleaza intreaga suita de teste cu un singur dublu-click.
REM
REM  Utilizare:
REM    run_tests.bat              -> ruleaza TOATE testele (default)
REM    run_tests.bat unit         -> doar backend/tests/unit/
REM    run_tests.bat integration  -> doar backend/tests/integration/
REM    run_tests.bat e2e          -> doar backend/tests/e2e/
REM    run_tests.bat coverage     -> backend cu raport HTML coverage
REM                                  (deschide automat htmlcov/index.html)
REM    run_tests.bat frontend     -> doar npm test
REM    run_tests.bat fast         -> doar unit + frontend (rapid, fara DB)
REM
REM  Ce face (mod default):
REM    1. Verifica Docker Desktop
REM    2. Porneste containerul PostgreSQL (daca nu e pornit)
REM    3. Asteapta pana cand DB-ul e healthy
REM    4. Activeaza venv-ul Python si ruleaza testele backend (pytest)
REM    5. Ruleaza testele frontend (npm test - 19 teste pe verifyOfflineToken)
REM    6. Afiseaza rezumat final cu cifre exacte
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

REM ----------------------------------------------------------------------------
REM  Parsare argument
REM ----------------------------------------------------------------------------
set MODE=%1
if "%MODE%"=="" set MODE=all

if /i "%MODE%"=="unit"        goto :mode_unit
if /i "%MODE%"=="integration" goto :mode_integration
if /i "%MODE%"=="e2e"         goto :mode_e2e
if /i "%MODE%"=="coverage"    goto :mode_coverage
if /i "%MODE%"=="frontend"    goto :mode_frontend
if /i "%MODE%"=="fast"        goto :mode_fast
if /i "%MODE%"=="all"         goto :mode_all
if /i "%MODE%"=="help"        goto :show_help
if /i "%MODE%"=="-h"          goto :show_help
if /i "%MODE%"=="--help"      goto :show_help

echo EROARE: mod necunoscut "%MODE%". Foloseste help pentru optiuni.
goto :show_help

:show_help
echo.
echo Utilizare: run_tests.bat [mod]
echo.
echo Moduri disponibile:
echo   (fara argument)    - ruleaza TOATE testele + coverage (cifra in terminal)
echo   unit               - doar tests/unit/ (rapide, fara DB, fara coverage)
echo   integration        - doar tests/integration/ (cu DB)
echo   e2e                - doar tests/e2e/ (flux complet)
echo   coverage           - backend + coverage + raport HTML auto-deschis
echo   frontend           - doar npm test (19 teste Ed25519 verify offline)
echo   fast               - unit + frontend (rapid, ~5s, fara Docker)
echo.
pause
exit /b 0

REM ============================================================================
REM  MOD: FAST (unit + frontend, fara Docker)
REM ============================================================================
:mode_fast
echo.
echo ============================================================================
echo   RAILWAY TEST SUITE - mod FAST (unit + frontend, fara DB)
echo ============================================================================
echo.
call .venv_win\Scripts\activate.bat
pushd backend
echo [1/2] Rulez unit tests (fara DB)...
pytest tests\unit --tb=line -q
set BACKEND_EXIT=!errorlevel!
popd

pushd frontend
echo.
echo [2/2] Rulez frontend tests (19 teste Ed25519)...
where npm >nul 2>&1
if errorlevel 1 (
    echo   ATENTIE: npm nu este instalat - SKIP frontend.
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
goto :summary

REM ============================================================================
REM  MOD: FRONTEND only
REM ============================================================================
:mode_frontend
echo.
echo ============================================================================
echo   RAILWAY TEST SUITE - doar frontend (19 teste Ed25519)
echo ============================================================================
echo.
pushd frontend
where npm >nul 2>&1
if errorlevel 1 (
    echo EROARE: npm nu este instalat.
    pause
    exit /b 4
)
call npm test
set FRONTEND_EXIT=!errorlevel!
popd
set BACKEND_EXIT=0
set FRONTEND_STATUS=DONE
goto :summary

REM ============================================================================
REM  MODURI care necesita DB: all / unit / integration / e2e / coverage
REM ============================================================================
:mode_unit
set TEST_PATH=tests\unit
set MODE_LABEL=UNIT
goto :need_db

:mode_integration
set TEST_PATH=tests\integration
set MODE_LABEL=INTEGRATION
goto :need_db

:mode_e2e
set TEST_PATH=tests\e2e
set MODE_LABEL=E2E
goto :need_db

:mode_coverage
set TEST_PATH=tests\
set MODE_LABEL=COVERAGE
set COVERAGE=1
goto :need_db

:mode_all
set TEST_PATH=tests\
set MODE_LABEL=ALL
goto :need_db

:need_db
echo.
echo ============================================================================
echo   RAILWAY TEST SUITE - mod %MODE_LABEL%
echo ============================================================================
echo.

REM ----------------------------------------------------------------------------
REM  PAS 1: Verifica Docker Desktop
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
REM  PAS 2: Porneste containerul postgres (idempotent)
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
REM  PAS 3: Asteapta healthcheck (max 30s)
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
REM  PAS 4: Ruleaza testele backend
REM ----------------------------------------------------------------------------
echo.
echo [4/5] Rulez testele backend (pytest %TEST_PATH%)...
echo ----------------------------------------------------------------------------

call .venv_win\Scripts\activate.bat
if errorlevel 1 (
    echo   EROARE: nu pot activa .venv_win. Verifica daca exista.
    pause
    exit /b 3
)

pushd backend
if defined COVERAGE (
    echo   [Coverage mode] Rulez cu --cov=app --cov-report=html --cov-report=term
    pytest %TEST_PATH% --cov=app --cov-report=html --cov-report=term-missing --tb=line -q > _cov_run.log 2>&1
    set BACKEND_EXIT=!errorlevel!
    REM Afisez doar liniile relevante (rezumat + fail-uri + coverage table)
    findstr /R /C:"^=*" /C:"FAILED" /C:"ERROR" /C:"passed" /C:"failed" /C:"warning" /C:"Cover" /C:"TOTAL" /C:"^app\\" /C:"^----" /C:"^tests" _cov_run.log
    REM Extrag cifra TOTAL coverage din output (ultima linie cu "TOTAL")
    for /f "tokens=4" %%a in ('findstr /R /C:"^TOTAL" _cov_run.log') do set COVERAGE_PCT=%%a
    del _cov_run.log 2>nul
    if exist htmlcov\index.html (
        echo.
        echo   Raport HTML generat: backend\htmlcov\index.html
        start "" htmlcov\index.html
    )
) else (
    REM Default mod ALL/unit/integration/e2e: adaug coverage discreet (term only, nu HTML)
    if /i "%MODE%"=="all" (
        pytest %TEST_PATH% --cov=app --cov-report=term --tb=line -q > _cov_run.log 2>&1
        set BACKEND_EXIT=!errorlevel!
        REM Afisez doar liniile relevante (rezumat + fail-uri + coverage table)
        findstr /R /C:"^=*" /C:"FAILED" /C:"ERROR" /C:"passed" /C:"failed" /C:"warning" /C:"Cover" /C:"TOTAL" /C:"^app\\" /C:"^----" _cov_run.log
        for /f "tokens=4" %%a in ('findstr /R /C:"^TOTAL" _cov_run.log') do set COVERAGE_PCT=%%a
        del _cov_run.log 2>nul
    ) else (
        pytest %TEST_PATH% --tb=line -q
        set BACKEND_EXIT=!errorlevel!
    )
)
popd

if !BACKEND_EXIT! NEQ 0 (
    echo.
    echo   ATENTIE: Testele backend au esuat ^(exit code !BACKEND_EXIT!^).
    if /i "%MODE%"=="all" echo   Continui cu frontend pentru raport complet.
)

REM Daca rulam doar backend (nu mod ALL), sar peste frontend
if /i not "%MODE%"=="all" (
    set FRONTEND_EXIT=0
    set FRONTEND_STATUS=SKIPPED ^(mod %MODE_LABEL%^)
    goto :summary
)

REM ----------------------------------------------------------------------------
REM  PAS 5: Ruleaza testele frontend (doar in mod ALL)
REM ----------------------------------------------------------------------------
echo.
echo [5/5] Rulez testele frontend (npm test - 19 teste Ed25519)...
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

REM ============================================================================
REM  REZUMAT FINAL
REM ============================================================================
:summary
echo.
echo ============================================================================
echo   REZUMAT FINAL - mod %MODE_LABEL%
echo ============================================================================
if !BACKEND_EXIT! EQU 0 (
    if defined COVERAGE_PCT (
        echo   Backend:   PASSED  ^(coverage global: !COVERAGE_PCT!^)
    ) else (
        echo   Backend:   PASSED
    )
) else (
    echo   Backend:   FAILED  ^(exit code !BACKEND_EXIT!^)
)
if defined COVERAGE (
    echo   Raport HTML: backend\htmlcov\index.html ^(deschis automat^)
)

if !BACKEND_EXIT! NEQ 0 (
    pause
    exit /b 3
)
if !FRONTEND_EXIT! NEQ 0 (
    pause
    exit /b 4
)

echo   Toate testele au trecut. Proiectul e gata de demo.
echo.
pause
exit /b 0
