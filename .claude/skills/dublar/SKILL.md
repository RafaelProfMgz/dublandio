---
name: dublar
description: Gera o áudio dublado de um livro com o dublandio. Use quando o usuário pedir para dublar, narrar ou gerar áudio de capítulos, adicionar um livro novo ao dublandio, ou ajustar vozes e personagens de um livro.
---

# Dublar um livro

1. **Livro existe?** `uv run dublandio livros`. Se não, crie `livros/<slug>/livro.yaml`
   copiando o de outro livro e ajuste `origem`, `provedor`, `personagens` e `vozes`.
2. **Roteiros.** `uv run dublandio preparar <slug>` (só cria os que faltam).
   Nunca use `--forcar` sem o usuário pedir: apaga edições manuais.
3. **Manifestos e vozes.** `uv run dublandio separar <slug>` e depois
   `uv run dublandio vozes <slug>`. Para cada personagem marcado "sem voz
   própria":
   - é apelido de alguém ("Bright" → "Bright Noa") ou não é nome ("Ele",
     "Mas") → adicione em `apelidos` no `livro.yaml`;
   - é personagem relevante → peça ao usuário uma voz e adicione em `vozes`.
   Rode `separar` de novo depois de editar o yaml.
4. **Teste curto.** Com o OK do usuário (gasta crédito):
   `uv run dublandio sintetizar <slug> --cap <N>`.
5. **Tudo.** `uv run dublandio tudo <slug>`. Se houver falhas, rode de novo:
   o cache faz só as falas que faltaram.

Informe ao usuário: capítulos montados (`livros/<slug>/audio/`), falhas e
personagens que ainda caem na voz do Narrador.
