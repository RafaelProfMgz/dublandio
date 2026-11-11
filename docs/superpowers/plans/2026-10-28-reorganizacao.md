# Reorganização do dublandio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir os ~20 scripts soltos por um pacote `dublandio` com CLI única, config por livro, cache/retomada e testes.

**Architecture:** Pipeline em 3 estágios puros (preparar → separar → sintetizar) sobre arquivos em `livros/<slug>/` (uma pasta por livro), com provedores TTS atrás de um Protocol. A CLI só orquestra.

**Tech Stack:** Python 3.13, uv, requests, pyyaml, pytest, ffmpeg.

**Spec:** `docs/superpowers/specs/2026-10-28-reorganizacao-design.md`

## Global Constraints

- Comentários, mensagens e identificadores de domínio em pt-br (padrão do código atual).
- Deps de runtime só `requests` e `pyyaml`; dev só `pytest`.
- Testes nunca fazem rede nem chamam ffmpeg real (exceto um teste marcado que pula se `ffmpeg` ausente).
- Modelos: OpenRouter `heygen/heygen-voice-1-turbo` (pcm); HeyGen `heygen-voice-1-turbo-free`.
- Voz padrão de fallback: a do `Narrador` do provedor.

## Review Focus

- Fala vazia/só espaços no roteiro → ignorada, não vira chamada de API (teste em Task 3).
- `:` dentro da fala narrativa ("Era assim: frio") com prefixo longo/minúsculo → tratado como Narrador, não personagem (teste em Task 3: nome só se ≤ 30 chars e começa com maiúscula).
- Livro inexistente / chave API ausente → mensagem clara e exit ≠ 0, sem traceback (Task 6).
- Texto alterado no roteiro → chave de cache muda, fala é regerada (Task 5).
- Pasta `origem` com `~` → expandida (Task 1).

---

### Task 1: Projeto uv + config do livro

**Files:** Create `pyproject.toml`, `src/dublandio/__init__.py`, `src/dublandio/config.py`, `tests/test_config.py`, `.env.example`

**Interfaces — Produces:**
- `@dataclass Livro(slug: str, titulo: str, origem: Path, provedor: str, idioma: str, personagens: list[str], apelidos: dict[str,str], vozes: dict[str, dict[str,str]])`
  - `Livro.dir -> Path` (`livros/<slug>`), `dir_roteiro`, `dir_manifesto`, `dir_audio` (`livros/<slug>/audio`), `dir_cache` (`.cache/<slug>`)
  - `Livro.nome_canonico(nome: str) -> str` (aplica apelidos)
  - `Livro.voz(nome: str) -> str` (canônico → vozes[provedor] → Narrador; `KeyError` se nem Narrador)
- `carregar_livro(slug: str, raiz: Path = Path(".")) -> Livro` — lê `livros/<slug>/livro.yaml`; `FileNotFoundError` com lista de livros disponíveis.
- `carregar_env(path: Path = Path(".env")) -> None` — não sobrescreve vars já definidas.

- [ ] Step 1: `pyproject.toml` com `[project.scripts] dublandio = "dublandio.cli:main"`, build `hatchling`, src layout; `uv sync`.
- [ ] Step 2: testes: `test_voz_resolve_apelido` (apelidos `{Ele: Fonoti}`, vozes heygen `{Fonoti: X, Narrador: N}` → `voz("Ele") == "X"`), `test_voz_fallback_narrador` (`voz("Desconhecido") == "N"`), `test_origem_expande_til`, `test_livro_inexistente_lista_disponiveis`. Rodar → FAIL.
- [ ] Step 3: implementar `config.py`. Rodar `uv run pytest tests/test_config.py -v` → PASS.
- [ ] Step 4: commit `feat: pacote dublandio e config por livro`.

### Task 2: preparar (md → roteiro)

**Files:** Create `src/dublandio/preparar.py`, `tests/test_preparar.py`

**Interfaces — Produces:**
- `md_para_roteiro(md: str, personagens: list[str]) -> str` — blocos `Nome: fala` separados por `\n\n`.
- `preparar_livro(livro: Livro, forcar: bool = False) -> list[Path]` — escreve `dir_roteiro/cap_NNN.txt` para cada `origem/cap_*.md`; pula existentes sem `forcar`.

Lógica: unificar `preparar_circles.py` (versão com contexto) — remover `# Capítulo N ...` e `*`; parágrafos por linha vazia; `— fala — disse Nome` (pronomes ela/ele/etc → Narrador); `— fala — Nome`; diálogo sem falante e < 80 chars → último personagem de `personagens` citado em narrativa; senão Narrador.

- [ ] Step 1: testes: `test_disse_nome` (`"— Vamos. — disse Zoltan Chivay."` → `"Zoltan: Vamos."`), `test_pronome_vira_narrador`, `test_contexto_personagem` (narrativa cita "Kamille", depois `"— Não."` → `"Kamille: Não."`), `test_remove_titulo_e_italico`, `test_nao_sobrescreve_sem_forcar` (tmp_path). FAIL.
- [ ] Step 2: implementar. PASS.
- [ ] Step 3: commit `feat: estágio preparar`.

### Task 3: separar (roteiro → manifesto)

**Files:** Create `src/dublandio/roteiro.py`, `tests/test_roteiro.py`

**Interfaces — Produces:**
- `@dataclass Fala(ordem: int, personagem: str, voz: str, texto: str)`
- `parse_roteiro(texto: str, livro: Livro) -> list[Fala]` — blocos por `\n\s*\n`; prefixo vira personagem só se `re.fullmatch(r"[A-ZÀ-Ý][\w .À-ÿ-]{0,29}", prefixo)`; quebras internas viram espaço; blocos vazios ignorados.
- `separar_livro(livro: Livro) -> list[Path]` — `dir_manifesto/cap_NNN.json` (lista de dicts de `Fala`, `ensure_ascii=False`, indent 2).
- `ler_manifesto(path: Path) -> list[Fala]`

- [ ] Step 1: testes: `test_parse_nome_e_fala`, `test_sem_prefixo_e_narrador`, `test_dois_pontos_na_narrativa` (`"Era assim: frio"` → Narrador, texto inteiro), `test_apelido_aplicado`, `test_bloco_vazio_ignorado`, `test_roundtrip_manifesto`. FAIL.
- [ ] Step 2: implementar. PASS. Commit `feat: estágio separar`.

### Task 4: provedores TTS + áudio

**Files:** Create `src/dublandio/audio.py`, `src/dublandio/tts/__init__.py`, `tts/base.py`, `tts/openrouter.py`, `tts/heygen.py`, `tests/test_audio.py`, `tests/test_tts.py`

**Interfaces — Produces:**
- `audio.pcm_to_wav(pcm: bytes, rate=44100, channels=1, bits=16) -> bytes`
- `audio.concatenar(partes: list[Path], destino: Path) -> None` (ffmpeg concat, `-c copy`, `check=True`)
- `tts.base.Provedor` (Protocol): `nome: str`; `sintetizar(texto: str, voz: str, idioma: str) -> bytes` (WAV); levanta `ErroTTS(msg, retentavel: bool)`.
- `tts.criar_provedor(nome: str) -> Provedor` — lê chave do env; `ErroConfig` se ausente. URLs/modelos conforme spec. 429/5xx/timeout → `retentavel=True`.

- [ ] Step 1: testes: `test_pcm_to_wav_header` (RIFF, tamanho 36+n, rate no offset 24), `test_openrouter_le_rate_do_content_type` (mock `requests.post`, `audio/pcm; rate=24000`), `test_heygen_baixa_audio_url` (mock post+get), `test_429_e_retentavel`, `test_chave_ausente_erro_config`, `test_concatenar` (skip se sem ffmpeg). FAIL.
- [ ] Step 2: implementar. PASS. Commit `feat: provedores openrouter e heygen`.

### Task 5: sintetizar (cache, retry, junção)

**Files:** Create `src/dublandio/sintetizar.py`, `tests/test_sintetizar.py`

**Interfaces — Produces:**
- `chave_cache(provedor: str, voz: str, idioma: str, texto: str) -> str` (sha256 hex[:16])
- `@dataclass Resultado(cap: str, geradas: int, reusadas: int, falhas: list[tuple[Fala, str]], arquivo: Path | None)`
- `sintetizar_capitulo(livro, manifesto: Path, provedor: Provedor, tentativas=3, espera=1.0, juntar=audio.concatenar) -> Resultado` — backoff `espera * 2**i` só para `retentavel`; junta só se `falhas == []`.
- `sintetizar_livro(livro, provedor, caps: list[int] | None = None) -> list[Resultado]`

- [ ] Step 1: testes com `ProvedorFake` e `juntar` fake: `test_cache_hit_nao_chama_provedor`, `test_texto_alterado_muda_chave`, `test_falha_nao_junta`, `test_retenta_retentavel` (falha 2x, sucesso na 3ª, `espera=0`), `test_nao_retenta_erro_fatal`. FAIL.
- [ ] Step 2: implementar. PASS. Commit `feat: síntese com cache e retomada`.

### Task 6: CLI

**Files:** Create `src/dublandio/cli.py`, `tests/test_cli.py`

**Interfaces — Consumes:** Tasks 1–5. **Produces:** `main(argv: list[str] | None = None) -> int`

Subcomandos: `preparar <livro> [--forcar]`, `separar <livro>`, `sintetizar <livro> [--cap N ...]`, `tudo <livro> [--cap N ...]`, `vozes <livro>` (tabela personagem/falas/voz, marca `(Narrador)` quem caiu no fallback), `livros`. Erros `FileNotFoundError`/`ErroConfig` → stderr + return 2; falhas de síntese → return 1.

- [ ] Step 1: testes: `test_livro_inexistente_retorna_2`, `test_vozes_lista_fallback` (fixture livro em tmp_path, `monkeypatch.chdir`), `test_separar_gera_manifestos`. FAIL.
- [ ] Step 2: implementar. PASS. Commit `feat: CLI dublandio`.

### Task 7: Migração de dados e remoção do legado

**Files:** Create `livros/o-louco-e-o-bruxo/livro.yaml`, `livros/circle-of-titans/livro.yaml`, `livros/teste/livro.yaml`; move dados; delete scripts antigos.

- [ ] Step 1: yamls — vozes openrouter de `mapa_vozes.json`, heygen de `mapa_vozes_heygen.json`; circle: `personagens` de `preparar_circles.py`, apelidos de `fix_manifesto.py` (`Ele: Fonoti, Ela: Fa Yuiry, Green: Narrador, Side: Narrador`); origem conforme `preparar_*.py`.
- [ ] Step 2: `git mv textos_o_louco_bruxo livros/o-louco-e-o-bruxo/roteiro`; `textos_para_tts/teste_ptbr.txt` → `livros/teste/roteiro/cap_001.txt`; apagar resto de `textos_para_tts/` (cópias idênticas, conferido); `mv "audio_gerado/gundam:circle" livros/circle-of-titans/audio` e `audio_gerado/o-louco-e-o-bruxo` → `livros/o-louco-e-o-bruxo/audio`; `.gitignore` ignora `livros/*/audio/`.
- [ ] Step 3: `uv run dublandio preparar circle-of-titans`; `uv run dublandio separar` nos 3 livros; `uv run dublandio vozes circle-of-titans` e ajustar apelidos óbvios (Bright→Bright Noa, Fa→Fa Yuiry, Astonaige→Astonaige Medoz, Mas/Uma/Eu→Narrador).
- [ ] Step 4: `git rm` dos `*.py` da raiz, `*.sh`, `mapa_vozes*.json`, `guia.yaml`, `manifesto*.json`, `INSTRUCOES_TTS.md`, `.zed/`. `uv run pytest` → PASS. Commit `refactor: migra dados e remove scripts antigos`.

### Task 8: Docs e skill

**Files:** Create `README.md`, `CLAUDE.md`, `.claude/skills/dublar/SKILL.md`

- [ ] Step 1: README (setup uv/ffmpeg/.env, fluxo, adicionar livro), CLAUDE.md (estrutura, comandos, regra: nunca versionar `.env`/áudio; roteiros são editados à mão — não forçar `preparar`), SKILL.md (frontmatter `name: dublar`, description de quando usar; passos: checar livro → `vozes` → corrigir apelidos/vozes → `sintetizar --cap` de teste → `tudo`).
- [ ] Step 2: smoke real opcional: `uv run dublandio sintetizar teste --cap 1` (gasta crédito — só com OK do usuário).
- [ ] Step 3: commit `docs: README, CLAUDE.md e skill dublar`.
