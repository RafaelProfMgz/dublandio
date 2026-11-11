@echo off
rem Abre o dublandio (Windows): sobe o container e abre a interface no navegador.
rem Dois cliques neste arquivo. Para um atalho na Area de Trabalho: botao direito > Enviar para > Area de trabalho.
setlocal
cd /d "%~dp0"
if "%PORTA%"=="" set PORTA=8765
set URL=http://127.0.0.1:%PORTA%

where docker >nul 2>&1 || (
    echo Docker nao encontrado. Instale o Docker Desktop: https://docs.docker.com/desktop/
    pause & exit /b 1
)
docker info >nul 2>&1 || (
    echo O Docker Desktop nao esta rodando. Abra o Docker Desktop e tente de novo.
    pause & exit /b 1
)
if not exist .env copy .env.example .env >nul

rem Pasta dos manuscritos (campo "origem" do livro.yaml).
if "%LIVROS_ORIGEM%"=="" (
    if exist "%USERPROFILE%\Documentos\livros" (
        set "LIVROS_ORIGEM=%USERPROFILE%\Documentos\livros"
    ) else (
        set "LIVROS_ORIGEM=%USERPROFILE%\Documents\livros"
    )
)

echo Subindo o dublandio (na primeira vez demora alguns minutos)...
docker compose up -d --build || (
    echo Nao consegui subir o dublandio. Veja: docker compose logs
    pause & exit /b 1
)

for /l %%i in (1,1,60) do (
    curl -fs %URL% >nul 2>&1 && goto pronto
    timeout /t 1 /nobreak >nul
)
:pronto
start "" %URL%
