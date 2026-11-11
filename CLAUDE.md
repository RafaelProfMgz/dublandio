# dublandio — regras para agentes

Leia o `README.md` para uso e estrutura.

- **Uma pasta por livro.** Tudo de um livro fica em `livros/<slug>/`
  (`livro.yaml`, `roteiro/`, `manifesto/`, `audio/`). Não crie arquivos de livro
  na raiz nem scripts avulsos: comportamento novo entra em `src/dublandio/` e
  vira subcomando da CLI (`cli.py`).
- **Nada de código por livro.** Diferenças entre livros vão para o `livro.yaml`
  (personagens, apelidos, vozes), nunca em `if livro == ...`.
- **Roteiros são editados à mão.** Nunca rode `preparar --forcar` sem o usuário
  pedir: sobrescreve as edições. `separar` pode rodar sempre.
- **Síntese gasta crédito.** Não rode `sintetizar`/`tudo` sem o usuário pedir;
  para testar, use `--cap` com um capítulo.
- **Avatares de vídeo: um por personagem, próprios de cada livro.** Todo
  personagem que fala no capítulo precisa do seu avatar (`livros/<slug>/video/avatares.json`);
  a mesma imagem não serve a dois personagens nem a dois livros. Ao gerar o
  vídeo de um capítulo, liste os personagens dele e deixe escolher um avatar
  livre do livro ou criar um novo. Regras ficam em `src/dublandio/avatares.py`.
- Nunca versionar `.env`, `.cache/` nem áudio (`livros/*/audio/`).
- Testes: `uv run pytest` (sem rede; provedores e ffmpeg são simulados).
  Toda mudança em `src/` vem com teste.
- Código, mensagens e comentários em pt-BR.
