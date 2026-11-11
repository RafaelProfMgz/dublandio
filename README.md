# dublandio

Transforma os capítulos de um livro (`cap_NNN.md`) em áudio dublado: um `.wav`
por capítulo, com uma voz por personagem.

## Setup

Requer [uv](https://docs.astral.sh/uv/) e `ffmpeg`.

```sh
uv sync
cp .env.example .env   # preencha a chave do provedor que o livro usa
```

### Com Docker (recomendado)

Instale o [Docker](https://docs.docker.com/get-docker/) e, com dois cliques:

- **Windows:** `Abrir dublandio.bat` (botão direito > Enviar para > Área de trabalho, para ter o atalho);
- **Linux/macOS:** `abrir-dublandio.sh` (`./abrir-dublandio.sh --instalar` põe o atalho no menu e na Área de Trabalho).

Ele sobe o container (na primeira vez demora alguns minutos) e abre a interface no navegador.
Na primeira vez, use **Colocar chave** na barra lateral e cole a chave da HeyGen ou do OpenRouter
(ela é conferida e gravada no `.env`).

Detalhes:

Dispensa `uv` e `ffmpeg` na máquina. A pasta do projeto entra como volume (`livros/`,
`.cache/` e o `.env` continuam nela) e `~/Documentos/livros` (de onde vêm os manuscritos do
campo `origem`) entra só para leitura — troque com `LIVROS_ORIGEM=/outra/pasta`.

```sh
docker compose up -d --build
```

Abra **http://127.0.0.1:8765** — é a interface, e dá para fazer tudo por ela. O container
fica rodando e volta sozinho quando o computador reinicia (até um `docker compose down`).
Quem preferir o terminal usa os mesmos comandos da CLI:

```sh
docker compose run --rm dublandio vozes between-worlds
```

O container roda com UID/GID 1000 (o padrão); se o seu for outro, rode com
`UID=$(id -u) GID=$(id -g) docker compose ...` para os arquivos não mudarem de dono.

## Uso

```sh
uv run dublandio livros                      # livros configurados
uv run dublandio tudo o-louco-e-o-bruxo      # preparar + separar + sintetizar
uv run dublandio tudo circle-of-titans --cap 3 4
```

Ou pela interface no navegador:

```sh
uv run dublandio gui                         # abre http://127.0.0.1:8765
```

Ela mostra cada capítulo como uma faixa de falas (uma cor por personagem; vazado =
ainda não sintetizado), edita roteiros e o `livro.yaml`, toca o áudio e roda as
etapas com progresso ao vivo. A aba Catálogo lista as vozes da HeyGen com
uma amostra de cada e mostra quais personagens já usam cada voz. Salvar um roteiro ou o `livro.yaml` já roda o
`separar`. A síntese sempre pede confirmação mostrando quantas falas novas vão
gastar crédito; o `preparar` da interface nunca sobrescreve roteiros.

A barra lateral mostra se cada chave está funcionando, e o livro avisa em destaque quando
não dá para sintetizar: chave faltando no `.env`, chave recusada, créditos acabados ou a cota
gratuita do dia esgotada (essa só aparece depois que uma síntese esbarra nela). Conferir as
chaves não gasta crédito. Clicar numa chave abre um campo para colar outra: ela é conferida
no provedor e só então gravada no `.env`, já valendo sem reiniciar.

Passo a passo, quando quiser revisar no meio do caminho:

| Comando | O que faz |
|---|---|
| `preparar <livro> [--forcar]` | `.md` da origem → `roteiro/cap_NNN.txt` ("Nome: fala"). Não sobrescreve roteiro existente sem `--forcar`. |
| `separar <livro>` | roteiro → `manifesto/cap_NNN.json` (cada fala com a voz resolvida). |
| `vozes <livro>` | personagens, nº de falas e voz; marca quem está sem voz própria. |
| `novo <pasta> [--titulo T] [--arquivos ...]` | cria `livros/<slug>/livro.yaml` a partir de uma pasta com capítulos `.md` ou `.txt` (na interface: **Adicionar livro**). |
| `catalogo [provedor] [--idioma pt]` | vozes que o provedor oferece (só HeyGen; não gasta crédito). A aba Catálogo da `gui` toca a amostra de cada uma. |
| `sintetizar <livro> [--cap N ...]` | manifesto → `audio/cap_NNN.wav`. |

A síntese guarda cada fala em `.cache/<livro>/`: rodar de novo só gera o que
mudou ou falhou. Cota esgotada ou chave recusada param a síntese na hora (ou passam
para a `reserva`), em vez de tentar fala por fala. Um capítulo só é montado quando todas as falas existem.

## Estrutura

```
livros/<livro>/            # tudo de um livro fica aqui
  livro.yaml               # origem, provedor, personagens, apelidos, vozes
  roteiro/cap_NNN.txt      # editável à mão
  manifesto/cap_NNN.json   # gerado pelo `separar`
  audio/cap_NNN.wav        # gerado (fora do git)
src/dublandio/             # código: config, preparar, roteiro, sintetizar, tts/, cli, gui/
tests/
```

## Vídeos com avatares HeyGen

O comando `videos` usa **os áudios já gerados**, sem fazer uma nova leitura.
Cada fala do roteiro identifica o personagem e localiza seu WAV no cache; falas longas
são cortadas em trechos de até 30 segundos, preservando as amostras originais.
O HeyGen recebe cada áudio para sincronizar a boca do avatar. No fim, o ffmpeg monta
`livros/<livro>/video/cap_NNN.mp4`, com a gravação original como fonte da trilha
(codificada em AAC uma única vez para o MP4).

Depois de criar os avatares no HeyGen, acrescente ao `livro.yaml`:

```yaml
avatares:
  Narrador: ID_DO_AVATAR_OU_LOOK_DO_NARRADOR
  Personagem: ID_DO_AVATAR_OU_LOOK_DO_PERSONAGEM
video:
  segundos_por_trecho: 30
  formato: "16:9"  # também aceita "9:16" e "1:1"
  motor: avatar_iv
```

Use os nomes canônicos dos personagens (depois de resolver `apelidos`). Todos precisam
de um avatar explícito; para usar o mesmo apresentador, repita o ID. As vozes permanecem
em `vozes`: seus IDs localizam os áudios existentes, e não são enviados para sintetizar
outra voz. O motor precisa ser compatível com os looks escolhidos.

```sh
uv run dublandio videos <livro> --cap 1          # prévia local, sem rede nem créditos
uv run dublandio videos <livro> --cap 1 --gerar  # envia ao HeyGen e monta o capítulo
```

A prévia grava `video/plano.json`, com personagem, avatar, arquivo e cortes em amostras.
O comando exige os WAVs individuais em `.cache/<livro>/cap_NNN/`; um WAV final sozinho
não identifica as trocas de personagem. Se o roteiro ou as vozes mudaram depois da síntese,
é preciso gerar os áudios correspondentes antes. Guarde o cache dos áudios aprovados.

`--gerar` usa `HEYGEN_API_KEY` do `.env` e consome créditos de vídeo do HeyGen.
O progresso fica em `.cache/<livro>/video/`, incluindo uploads, IDs remotos e clipes.
Rode novamente o mesmo comando para retomar um render ou download interrompido.
O capítulo só é montado após todos os clipes ficarem prontos; falhas não substituem o
MP4 anterior. Um pedido sem resposta fica protegido pela chave de idempotência; após
23 horas sem receber o ID, o programa pede conferência no HeyGen antes de reenviar.
Uma falha definitiva do render mantém seu ID para revisão, sem disparar outra cobrança.

Esta etapa está disponível pela CLI; a interface continua com o fluxo de áudio.
Referências: [áudio para vídeo](https://developers.heygen.com/audio-to-video),
[criar vídeo](https://developers.heygen.com/reference/create-video) e
[upload de áudio](https://developers.heygen.com/reference/upload-asset).

## Testar um avatar pelo Hugging Face

Também é possível animar uma foto com um WAV já existente usando uma demo pública
SadTalker em um Space do Hugging Face. Configure `HF_TOKEN` no `.env` (um token Read
serve para a demo pública). O comando envia a imagem e o áudio ao Space escolhido:

```sh
uv run dublandio video-hf <livro> --avatar caminho/narrador.png --audio caminho/fala.wav --nome teste-narrador
```

O resultado fica em `livros/<livro>/video/teste-narrador.mp4`. A montagem usa o WAV
original como fonte da trilha AAC e preserva a resolução renderizada pela demo.
O padrão é o Space comunitário `henrybit/SadTalker-Demo`, usando `full` e modo estável;
`--space usuario/space` aceita outro Space com a mesma API SadTalker `/generate`.
Os renders baixados ficam em `video/.hf-cache/`, para não consumir outra cota se a
montagem local falhar. Um destino já existente com entradas diferentes é preservado:
escolha outro `--nome`.

O comando não contrata hardware nem compra créditos. A disponibilidade, a fila e a
cota dependem do Space e da conta. ZeroGPU gratuito tem limites de **processamento**,
não uma franquia equivalente em minutos de vídeo; não há garantia de capacidade para
capítulos inteiros. Uma interrupção antes do download não retoma o pedido remoto:
confira a demo antes de reenviar. O comando ainda opera uma foto e um áudio por vez.
Referências: [demo SadTalker](https://huggingface.co/spaces/henrybit/SadTalker-Demo) e
[cotas ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu).

### Capítulo completo pela cota diária

Cada personagem aparece com o **seu** avatar. Regras:

- **cada livro tem avatares próprios**: uma imagem que já é avatar de outro livro é recusada;
- **um avatar por personagem**: a mesma imagem não serve a dois personagens do livro;
- todo personagem que fala no capítulo precisa de avatar antes de gerar.

Na interface, aba **Vídeos**: ao clicar em **Gerar vídeo** num capítulo com áudio, aparecem
os personagens que falam nele; para cada um, escolha um avatar do livro ainda sem dono ou
clique em **Criar novo avatar** e envie a foto. O botão de gerar só libera quando todos têm
avatar. Pela CLI, `--avatar PERSONAGEM=foto.png` (repetível) cria e atribui o avatar:

```sh
uv run dublandio capitulo-hf <livro> --cap 1 --avatar Narrador=narrador.png --avatar Keira=keira.png  # prepara o progresso local
uv run dublandio capitulo-hf <livro> --cap 1 --gerar                                                  # gera até a cota permitir
```

**Criar novo avatar** abre uma tela inteira com a ficha do personagem: nome, idade,
descrição e a voz selecionada no livro. Envie uma ou mais imagens (até 8) e marque a
principal, que é a que o vídeo anima (rosto de frente funciona melhor). Também dá para
criar a imagem com IA:

- **OpenAI** (recomendado, `OPENAI_API_KEY`): desenha a partir da ficha; com imagens
  enviadas, usa-as como referência de aparência.
- **Claude** (`ANTHROPIC_API_KEY`): o Claude não desenha. Ele olha as imagens e a ficha e
  escreve o pedido detalhado, e a OpenAI desenha. Também preenche a descrição pelas fotos.

Gerar imagem ou descrição gasta crédito do provedor e só acontece ao clicar no botão.
As chaves podem ser coladas na própria tela (são conferidas e gravadas no `.env`).
Modelos: `gpt-image-1` e `gpt-4.1-mini` na OpenAI (troque com `OPENAI_MODELO_IMAGEM` e
`OPENAI_MODELO_TEXTO`), `claude-opus-5-5` no Claude.

As imagens ficam em `livros/<livro>/video/avatares/` e as fichas em
`livros/<livro>/video/avatares.json`. Para saber quando cada personagem fala, o comando
soma as falas em cache (`.cache/<livro>/cap_NNN/`), que formam o WAV do capítulo sem pausas;
sem o cache de todas as falas, ou se o roteiro mudou depois da síntese, é preciso sintetizar
o capítulo de novo. Nenhum corte atravessa uma troca de personagem. Capítulos começados
antes dos avatares por personagem continuam com o avatar único com que começaram.

O áudio vem de `livros/<livro>/audio/cap_001.wav`. O progresso fica em
`video/hf/cap_001/progresso.json`. Os cortes têm até 5 segundos e diminuem conforme
a cota disponível e a reserva de GPU exigida pelo Space. Ao parar por cota, o comando
informa a data de renovação: rode o mesmo comando depois para continuar pelos trechos
que faltam. Não há agendamento automático entre os dias.
O Hugging Face também pode interromper por limite de execuções mesmo com tempo de
GPU restante. Nesse caso, o pedido não é repetido e a prévia dos clipes prontos é montada.

Uma prévia do início já gerado fica em `video/cap_001-hf-parcial.mp4`. O capítulo final
`video/cap_001-hf.mp4` só aparece depois de todos os trechos terminarem. A montagem
mantém as amostras em ordem e codifica a trilha original uma única vez em AAC.
Não troque o áudio nem os avatares depois que o primeiro trecho foi pedido: a retomada confere seus hashes.
Este modo está vinculado à API e ao cálculo de reserva da demo SadTalker padrão;
alterações na demo podem exigir atualização. Erros de rede ou da demo interrompem
o processo; os arquivos já baixados são preservados.

## Adicionar um livro

O jeito fácil: **Adicionar livro** na interface (ou `uv run dublandio novo <pasta>`). Escolha a
pasta, marque e ordene os capítulos; `.md` vira roteiro pelo `preparar`, `.txt` já é roteiro e
entra como está. À mão:

1. Crie `livros/<slug>/livro.yaml` (copie o de outro livro). Campos:
   - `origem`: pasta com os `cap_NNN.md` ou `.txt` (aceita `~`);
   - `arquivos` (opcional): capítulos em ordem, relativos à `origem`, quando os nomes não seguem
     `cap_NNN` (o 1º vira `cap_001`, o 2º `cap_002`...);
   - `provedor`: `heygen` ou `openrouter`;
   - `reserva` (opcional): o outro provedor. Se a cota ou o crédito do principal acabar no meio
     da síntese, ela continua na reserva, com a voz de cada personagem em `vozes > <reserva>`.
     Os dois rodam o mesmo modelo da HeyGen: use as mesmas vozes nos dois (o id da HeyGen e o
     nome no OpenRouter; `dublandio catalogo` mostra os dois) para ninguém mudar de voz no meio;
   - `personagens`: ajudam o `preparar` a adivinhar quem fala;
   - `apelidos`: nome que aparece no roteiro → nome canônico;
   - `vozes`: por provedor, `Personagem: voz`. Quem não tiver voz usa a do `Narrador`.
2. `uv run dublandio preparar <slug>` e revise os roteiros.
3. `uv run dublandio separar <slug>` e `uv run dublandio vozes <slug>`; ajuste apelidos e vozes.
4. `uv run dublandio sintetizar <slug> --cap 1` para testar, depois `tudo`.

## Testes

```sh
uv run pytest
```
