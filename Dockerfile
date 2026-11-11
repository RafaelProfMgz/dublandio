# Imagem do dublandio: CLI + interface web, com ffmpeg.
# A pasta do projeto (livros/, .cache/, .env) e os manuscritos de origem entram por volume; ver compose.yaml.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

# Dependências primeiro, para o cache de camadas sobreviver a mudanças no código.
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# O livro.yaml usa origem em ~/Documentos/livros; o compose monta essa pasta aqui.
# Permissões abertas porque o container roda com o UID de quem chama (arquivos não viram do root).
ENV HOME=/home/dublandio
RUN mkdir -p $HOME/Documentos/livros /dados && chmod 777 $HOME /dados
WORKDIR /dados

EXPOSE 8765
ENTRYPOINT ["dublandio"]
CMD ["gui", "--host", "0.0.0.0", "--sem-navegador"]
