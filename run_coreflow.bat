@echo off
setlocal

cd /d "%~dp0"
if not exist ".coreflow" mkdir ".coreflow" >nul 2>nul
set "READY_URL=http://127.0.0.1:8000/health"
set "OPEN_URL=http://127.0.0.1:8000/admin/"
set "WAIT_SCRIPT=scripts\wait_for_coreflow.py"

if not exist "%WAIT_SCRIPT%" (
    echo Arquivo de espera nao encontrado: %WAIT_SCRIPT%
    exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker nao foi encontrado no PATH.
    goto local_mode
)

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo Arquivo .env criado a partir de .env.example
    ) else (
        echo Nenhum arquivo .env ou .env.example foi encontrado.
        exit /b 1
    )
)

echo Verificando se a API ja esta em execucao...
py -3 "%WAIT_SCRIPT%" --url "%READY_URL%" --timeout 3 --interval 1 >nul 2>nul
if not errorlevel 1 (
    echo API ja estava em execucao.
    goto open_browser
)

docker info >nul 2>nul
if errorlevel 1 (
    echo Docker foi encontrado, mas o Docker Engine nao esta ativo.
    goto local_mode
)

echo Iniciando CoreFlow Agents com Docker Compose...
docker compose up --build -d
if errorlevel 1 (
    echo Falha ao iniciar a stack CoreFlow com Docker.
    goto local_mode
)
goto wait_for_api

:local_mode
echo Iniciando CoreFlow Agents em modo local...
set "COREFLOW_ASYNC_BACKEND=memory"
set "DATABASE_URL=sqlite:///./.coreflow/coreflow.db"
set "COREFLOW_API_TOKEN=local-token"
set "COREFLOW_LLM_PROVIDER=template"
for /f "usebackq delims=" %%i in (`py -3 -c "import sys; print(sys.executable)"`) do set "PYTHON_EXE=%%i"
if not defined PYTHON_EXE (
    echo Nao foi possivel localizar o Python para iniciar o Uvicorn.
    exit /b 1
)
powershell -NoProfile -Command ^
  "$wd = '%~dp0';" ^
  "$out = Join-Path $wd '.coreflow\\orchestrator.out.log';" ^
  "$err = Join-Path $wd '.coreflow\\orchestrator.err.log';" ^
  "$pidFile = Join-Path $wd '.coreflow\\orchestrator.pid';" ^
  "$proc = Start-Process '%PYTHON_EXE%' -ArgumentList '-m','uvicorn','apps.orchestrator.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $wd -RedirectStandardOutput $out -RedirectStandardError $err -PassThru;" ^
  "Set-Content -Path $pidFile -Value $proc.Id"
if errorlevel 1 (
    echo Falha ao iniciar o modo local.
    exit /b 1
)

:wait_for_api
echo Aguardando a API ficar disponivel...
py -3 "%WAIT_SCRIPT%" --url "%READY_URL%" --timeout 60 --interval 2 >nul 2>nul
if errorlevel 1 (
    echo A API nao respondeu dentro do tempo esperado.
    echo Verifique os logs em .coreflow\orchestrator.out.log e .coreflow\orchestrator.err.log
    exit /b 1
)
goto open_browser

:open_browser
echo API disponivel. Abrindo navegador...
start "" "%OPEN_URL%"
echo CoreFlow Agents em execucao.
echo API: %OPEN_URL%

endlocal
exit /b 0

