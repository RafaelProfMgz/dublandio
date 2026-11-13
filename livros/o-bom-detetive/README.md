# O Bom Detetive

Livro preparado para o fluxo de dublagem do Dublandio. Estão disponíveis o prólogo **Quarenta e Um Vírgula Dois** e os capítulos **002 — Gente de Whitby**, **003 — Primeira Classe**, **004 — O Gabinete** e **005 — A Copa Fria**, do volume 1.

## Arquivos

- `originais/roteiro/vol1/cap_000.md`: roteiro Markdown recebido, preservado integralmente.
- `originais/roteiro/vol1/cap_000.txt`: fonte de dublagem revisada, no formato `Nome: fala`, com uma linha vazia entre blocos.
- `originais/roteiro/vol1/cap_002.md` e `cap_003.md`: roteiros Markdown importados em 13/11/2026 de `/home/angel/Documentos/livros/o_bom_detetive/05_manuscrito/roteiro/vol1/`.
- `originais/roteiro/vol1/cap_002.txt` e `cap_003.txt`: fontes convertidas para `Nome: fala`, preservando os falantes explícitos e o texto; somente a marcação Markdown foi removida.
- `roteiro/cap_001.txt`, `cap_002.txt` e `cap_003.txt`: roteiros usados pelo aplicativo.
- `manifesto/cap_001.json`, `cap_002.json` e `cap_003.json`: respectivamente 152, 289 e 256 falas numeradas, com personagem canônico, voz e texto.
- `livro.yaml`: título, ordem de leitura, personagens, apelidos e vozes da HeyGen.

O prólogo é `cap_000` na obra e `cap_001` no aplicativo, pois é o primeiro item de `arquivos`. Os capítulos 002 e 003 da obra são os itens `cap_002` e `cap_003` no aplicativo. O capítulo 001 da obra não foi encontrado na origem e não foi criado nem substituído. Se ele for incluído depois, a ordem e a numeração do aplicativo precisarão ser revistas preservando os áudios existentes.

Na importação de 13/11/2026 foram mantidos o roteiro do prólogo e todas as vozes existentes. Os novos falantes foram cadastrados com nomes canônicos; quem ainda não tem voz própria usa a voz padrão do Narrador: Tunstall, Bly, Dra. Pell, Fenwick, Martha Garside, Lady Honoria, Cecily, Lister, Srta. Vale, Walter Rudd e Vendedora. Essa atribuição pode ser ajustada no `livro.yaml` ou pela interface antes da síntese. Nenhum áudio foi gerado nesta importação.

## Conferência

| Personagem | Falas no prólogo | Voz | Referência e limite |
|---|---:|---|---|
| Narrador | 104 | Murilo (masculino, Portuguese) | Narração em português |
| Nell Tasker | 14 | Tabitha (feminino, English) | Jovem, local; região não informada na voz |
| Pybus | 14 | Educated British Baritone (masculino, English) | Formalidade de mordomo; voz declara British |
| Sra. Agnes Gaunt | 16 | Nadine (feminino, English) | Calma e maternal; região não informada na voz |
| Margaret Marchbank | 4 | Meredith (feminino, English) | Contida; região não informada na voz |
| Lucian Ashcombe | 0 | Afonso (masculino, Portuguese) | Português solicitado para o protagonista; diferente do narrador Murilo |
| Hollis Brand | 0 | Weston (masculino, English) | Lancashire na ficha; sotaque regional pendente |
| Inspetor Thomas Garside | 0 | Bram (masculino, English) | Yorkshire na ficha; sotaque regional pendente |
| Inspetor James Dunmore | 0 | Gareth (masculino, English) | Escocês na ficha; sotaque regional pendente |

Seleção revisada em 12/11/2026 com base no catálogo atual da HeyGen e nas fichas de `/home/angel/Documentos/livros/o_bom_detetive/02_personagens/`. Os quatro personagens que ainda não falam foram cadastrados para os próximos capítulos. Pybus usa a voz com identificação britânica explícita no nome. Por escolha do usuário, Ashcombe usa Afonso e o narrador usa Murilo: duas vozes masculinas distintas em português. O catálogo identifica ambas como Portuguese, sem especificar a variante regional; o sotaque brasileiro ainda depende de audição.

O texto e `idioma: pt` continuam em português. A origem inglesa de uma voz não comprova sotaque britânico ao falar português: o modelo pode adaptar a pronúncia à língua de destino. Os sotaques regionais permanecem pendentes de teste de audição e de uma voz apropriada; as demais vozes inglesas são escolhas provisórias por perfil e gênero. Não foi identificado personagem francês ou alemão nas fichas. Ashcombe estudou em Viena e Paris, o que não estabelece nacionalidade nem sotaque estrangeiro.

A reserva OpenRouter permanece desativada para preservar a seleção HeyGen. Nenhuma síntese foi executada nesta revisão.

O texto literário foi preservado. Título, marcas de negrito e separadores de cena ficam no Markdown original; não entram como falas. Os nomes antes dos dois-pontos são identificadores e não fazem parte do texto falado.

## Atualização

Para alterar o texto de forma persistente, edite `originais/roteiro/vol1/cap_000.txt` e execute, na raiz do projeto:

```sh
uv run dublandio preparar o-bom-detetive --forcar
uv run dublandio separar o-bom-detetive
uv run dublandio vozes o-bom-detetive
```

A fonte TXT evita que a conversão de prosa acrescente `Narrador:` aos falantes já identificados. Ao incluir novos capítulos, acrescente seus arquivos na ordem de leitura em `livro.yaml`.

A formatação não gera áudio nem consome créditos. Para produzir o áudio corrigido, use a etapa de síntese do aplicativo após revisar as vozes.

Para gerar somente os dois capítulos adicionados (consome créditos HeyGen):

```sh
uv run dublandio sintetizar o-bom-detetive --cap 2 3
```

## Reimportação do prólogo em 13/11/2026

O prólogo refeito foi importado de `/home/angel/Documentos/livros/o_bom_detetive/05_manuscrito/roteiro/vol1/cap_000.md` para a fonte Markdown, a fonte TXT e o roteiro `cap_001` do aplicativo. O manifesto contém 152 falas; as vozes foram mantidas. Os capítulos 002 e 003 permanecem intactos.

A versão anterior do texto e do manifesto está em `revisoes/antes-atualizacao-prologo-20261113T203209681043Z`. O áudio anterior e seu mapa de falas foram arquivados em `audio/anteriores/20261113T203209681043Z`. O cache das falas foi preservado para reaproveitar trechos idênticos. Esta importação não executou síntese nem consumiu créditos.

Para gerar o novo áudio do prólogo:

```sh
uv run dublandio sintetizar o-bom-detetive --cap 1
```

## Importação do capítulo 004

**004 — O Gabinete** adicionado a partir de `/home/angel/Documentos/livros/o_bom_detetive/05_manuscrito/roteiro/vol1/cap_004.md`. A fonte Markdown está preservada em `originais/roteiro/vol1/cap_004.md`; a fonte TXT e o roteiro do aplicativo usam falantes explícitos. O manifesto `cap_004.json` contém 233 falas. O capítulo está cadastrado na ordem de leitura; vozes e capítulos anteriores foram preservados. Não foi executada síntese nesta importação.

```sh
uv run dublandio sintetizar o-bom-detetive --cap 4
```

## Importação do capítulo 005

**005 — A Copa Fria** importado de `/home/angel/Documentos/livros/o_bom_detetive/05_manuscrito/roteiro/vol1/cap_005.md`. O Markdown original está preservado em `originais/roteiro/vol1/cap_005.md`; a fonte TXT e o roteiro `cap_005.txt` mantêm os falantes explícitos. O manifesto contém 181 falas. Lavadeira foi cadastrada como nova personagem e usa a voz padrão do Narrador; Dra. Eleanor Pell também permanece com a voz do Narrador enquanto não tiver seleção própria. As demais vozes e os capítulos anteriores foram preservados. Nenhuma síntese foi executada nesta importação.

```sh
uv run dublandio sintetizar o-bom-detetive --cap 5
```
