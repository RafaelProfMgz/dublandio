#!/usr/bin/env sh
# Abre o dublandio (Linux/macOS): sobe o container e abre a interface no navegador.
# Uso: ./abrir-dublandio.sh             (ou dois cliques, se o gerenciador de arquivos deixar)
#      ./abrir-dublandio.sh --instalar  cria um atalho no menu de aplicativos e na Área de Trabalho
set -e
cd "$(dirname "$0")"
URL=http://127.0.0.1:${PORTA:-8765}

if [ "$1" = "--instalar" ]; then
    atalho="[Desktop Entry]
Type=Application
Name=dublandio
Comment=Livros em áudio dublado
Exec=\"$(pwd)/abrir-dublandio.sh\"
Icon=audio-x-generic
Terminal=false
Categories=AudioVideo;"
    mkdir -p "$HOME/.local/share/applications"
    printf '%s\n' "$atalho" > "$HOME/.local/share/applications/dublandio.desktop"
    mesa=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
    if [ -d "$mesa" ]; then
        printf '%s\n' "$atalho" > "$mesa/dublandio.desktop"
        chmod +x "$mesa/dublandio.desktop"
        gio set "$mesa/dublandio.desktop" metadata::trusted true 2>/dev/null || true
    fi
    echo "Atalho criado: procure 'dublandio' no menu de aplicativos."
    exit 0
fi

avisar() {
    echo "$1" >&2
    notify-send dublandio "$1" 2>/dev/null || true
    exit 1
}

command -v docker >/dev/null 2>&1 || avisar "Docker não encontrado. Instale em https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || avisar "O Docker não está rodando. Abra o Docker e tente de novo."
[ -f .env ] || cp .env.example .env

# UID é só leitura em alguns shells: passa pelo `env` para o compose rodar com o seu usuário.
env UID="$(id -u)" GID="$(id -g)" docker compose up -d --build || avisar "Não consegui subir o dublandio (veja: docker compose logs)."

i=0
until curl -fs "$URL" >/dev/null 2>&1 || [ $i -ge 60 ]; do sleep 1; i=$((i + 1)); done
xdg-open "$URL" >/dev/null 2>&1 || open "$URL" >/dev/null 2>&1 || echo "Abra $URL no navegador."
