# Reorganização do dublandio — design

Data: 2026-10-28 · Status: aprovado em conversa · Revisão: uma pasta por livro

## Objetivo

Um comando único e confiável que transforma os capítulos `.md` de um livro em
áudios dublados (um `.wav` por capítulo, vozes por personagem), sem editar
código para cada livro novo.

**Sucesso =** `uv run dublandio tudo <livro>` gera `livros/<livro>/audio/cap_NNN.wav`;
rodar de novo só sintetiza falas novas/alteradas; nenhuma fala some em silêncio.

## Fora de escopo

Identificação de falante via LLM, paralelismo de chamadas TTS, UI.

## Estrutura

```
pyproject.toml              # uv; deps: requests, pyyaml; dev: pytest
src/dublandio/
  config.py                 # .env + Livro (dataclass) a partir do livro.yaml
  preparar.py               # md -> roteiro "Nome: fala\n\n..."
  roteiro.py                # roteiro -> manifesto (falas com voz resolvida)
  tts/base.py               # Protocol Provedor.sintetizar(texto, voz) -> bytes wav
  tts/openrouter.py
  tts/heygen.py
  audio.py                  # pcm_to_wav, concatenar (ffmpeg)
  sintetizar.py             # cache, retry, relatório, junção por capítulo
  cli.py                    # argparse, entrypoint `dublandio`
tests/
livros/<slug>/              # TUDO de um livro fica aqui
  livro.yaml                # config: origem, provedor, vozes, apelidos
  roteiro/cap_NNN.txt       # versionado, editável
  manifesto/cap_NNN.json    # versionado, regenerável
  audio/cap_NNN.wav         # ignorado pelo git
.cache/<slug>/cap_NNN/<hash>.wav      # ignorado
.claude/skills/dublar/SKILL.md
CLAUDE.md  README.md  .env.example
```

Regra: nada específico de um livro fica fora de `livros/<slug>/` (exceto o
cache). Adicionar um livro = criar `livros/<slug>/livro.yaml`.

Scripts antigos (`*.py` na raiz, `*.sh`, `mapa_vozes*.json`, `guia.yaml`,
`manifesto*.json`, `INSTRUCOES_TTS.md`) são removidos.

## Config do livro

```yaml
titulo: O Louco e o Bruxo
origem: ~/Documentos/livros/o-louco-e-o-bruxo/05_manuscrito/vol1   # pasta com cap_*.md
provedor: heygen                 # heygen | openrouter
idioma: pt
personagens: [Ciri, Vesemir]     # opcional: usado pelo preparar para inferir falante por contexto
apelidos: { Ele: Fonoti, Green: Narrador }   # nome no roteiro -> nome canônico
vozes:
  openrouter: { Narrador: lucian, Zoltan: weston }
  heygen:     { Narrador: 83548de556df48ba8c09c42a57c51d85 }
```

Resolução de voz: `apelidos` → `vozes[provedor][nome]` → `vozes[provedor]["Narrador"]`.
Personagem sem voz própria cai no Narrador e aparece no comando `vozes`.

## Fluxo de dados

1. **preparar**: lê `origem/cap_*.md`, remove título/markdown, divide parágrafos,
   detecta diálogo (`— fala — disse Nome`, `— fala — Nome`), usa `personagens`
   para contexto; escreve `livros/<slug>/roteiro/cap_NNN.txt`. Não sobrescreve
   roteiro existente sem `--forcar` (roteiros podem ter sido editados à mão).
2. **separar**: roteiro → manifesto JSON `[{ordem, personagem, voz, texto}]`.
   Linhas sem `Nome:` = Narrador. Aplica apelidos. Sempre regenerável.
3. **sintetizar** (`--cap N` opcional): para cada fala, chave =
   sha256(provedor, voz, idioma, texto)[:16]; se `.cache/.../<chave>.wav`
   existe, reusa; senão chama o provedor com até 3 tentativas (backoff em
   429/5xx/timeout). Se todas as falas existem, concatena em
   `livros/<slug>/audio/cap_NNN.wav`; senão lista as falhas e não junta.
   Exit code ≠ 0 se houve falha.
4. **tudo** = preparar (sem forçar) + separar + sintetizar.
5. **vozes**: lista personagens do livro com contagem de falas e se têm voz própria.

## Provedores

- **OpenRouter**: `POST /api/v1/audio/speech`, modelo `heygen/heygen-voice-1-turbo`,
  `response_format=pcm`, converte para WAV usando rate/channels do Content-Type.
- **HeyGen**: `POST https://api.heygen.com/v3/models/audio/tts`, modelo
  `heygen-voice-1-turbo-free`, baixa `data.audio_url`.

Chaves via `.env` (`OPENROUTER_API_KEY`, `HEYGEN_API_KEY`); erro claro se faltar a do provedor escolhido.

## Migração

- `textos_o_louco_bruxo/` → `livros/o-louco-e-o-bruxo/roteiro/`; vozes de `mapa_vozes*.json`/`guia.yaml`.
- circle: novo `livros/circle-of-titans/livro.yaml` (apelidos de `fix_manifesto.py`, personagens de
  `preparar_circles.py`); roteiros regenerados a partir dos `.md` originais.
- `textos_para_tts/teste_ptbr.txt` → `livros/teste/roteiro/cap_001.txt` + `livros/teste/livro.yaml`.
  Cópias duplicadas e fragmentos `*_NNN.txt` são apagados.
- `audio_gerado/gundam:circle/` → `livros/circle-of-titans/audio/`; `audio_gerado/o-louco-e-o-bruxo/` → `livros/o-louco-e-o-bruxo/audio/`.

## Testes (pytest, sem rede)

preparar (padrões de diálogo, contexto), separar (parse, apelidos, fallback de voz),
`pcm_to_wav`, chave de cache, sintetizar com provedor fake (cache hit, falha não junta).
