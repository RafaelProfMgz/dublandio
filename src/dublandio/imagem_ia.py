"""IA para criar avatares: descrever o personagem e desenhar a foto.

- OpenAI (padrão): desenha a imagem (gpt-image-1) e também descreve fotos.
- Claude: entende fotos e texto, mas não desenha. Aqui ele descreve as fotos e
  escreve o pedido detalhado da imagem; quem desenha continua sendo a OpenAI.

Tudo isso gasta crédito do provedor; nada roda sem o usuário pedir na interface.
"""

import base64
import os

import requests

OPENAI_URL = 'https://api.openai.com/v1'
MODELO_CLAUDE = 'claude-opus-5-5'
IAS = ('openai', 'claude')
VARIAVEIS = {'openai': 'OPENAI_API_KEY', 'claude': 'ANTHROPIC_API_KEY'}

# SadTalker anima melhor um rosto de frente, ombros para cima e fundo liso.
ENQUADRAMENTO = ('Retrato de frente, da cabeça aos ombros, olhando para a câmera, boca fechada, '
                 'expressão neutra, rosto bem iluminado e nítido, fundo liso, sem texto.')


class ErroIA(Exception):
    """Falha ao falar com o provedor de IA (chave, crédito, rede ou recusa)."""


def _modelo_imagem() -> str:
    return os.getenv('OPENAI_MODELO_IMAGEM', 'gpt-image-1')


def _modelo_texto() -> str:
    return os.getenv('OPENAI_MODELO_TEXTO', 'gpt-4.1-mini')


def situacao() -> dict:
    """Quais IAs têm chave no .env (só os 4 últimos caracteres saem daqui)."""
    resultado = {}
    for ia, variavel in VARIAVEIS.items():
        chave = os.getenv(variavel, '')
        resultado[ia] = {'configurado': bool(chave), 'final': chave[-4:] if chave else None, 'variavel': variavel}
    return resultado


def _chave(ia: str) -> str:
    chave = os.getenv(VARIAVEIS[ia], '')
    if not chave:
        raise ErroIA(f'configure {VARIAVEIS[ia]} para usar a {"OpenAI" if ia == "openai" else "Claude"}')
    return chave


def _tipo(imagem: bytes) -> str:
    return 'image/png' if imagem.startswith(b'\x89PNG') else 'image/jpeg'


def _ficha(dados: dict) -> str:
    linhas = [f"Nome: {dados.get('nome') or '—'}", f"Idade: {dados.get('idade') or '—'}",
              f"Descrição: {dados.get('descricao') or '—'}"]
    return '\n'.join(linhas)


# ---------- OpenAI ----------

def _openai(metodo: str, rota: str, **kwargs) -> dict:
    try:
        r = requests.request(metodo, f'{OPENAI_URL}/{rota}', timeout=180,
                             headers={'Authorization': f'Bearer {_chave("openai")}'}, **kwargs)
    except requests.RequestException as e:
        raise ErroIA('a OpenAI não respondeu; tente de novo') from e
    if r.status_code in (401, 403):
        raise ErroIA('a OpenAI recusou a chave')
    if r.status_code == 429:
        raise ErroIA('a OpenAI recusou por limite ou falta de crédito')
    if not r.ok:
        try:
            detalhe = r.json()['error']['message']
        except (ValueError, KeyError, TypeError):
            detalhe = r.text[:300]
        raise ErroIA(f'a OpenAI recusou o pedido: {detalhe}')
    return r.json()


def _openai_texto(instrucao: str, imagens: list[bytes]) -> str:
    conteudo = [{'type': 'text', 'text': instrucao}] + [
        {'type': 'image_url', 'image_url': {'url': f'data:{_tipo(i)};base64,{base64.b64encode(i).decode()}'}}
        for i in imagens]
    dados = _openai('POST', 'chat/completions', json={
        'model': _modelo_texto(), 'messages': [{'role': 'user', 'content': conteudo}]})
    try:
        return dados['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise ErroIA('resposta inesperada da OpenAI') from e


def desenhar(pedido: str, referencias: list[bytes]) -> bytes:
    """PNG gerado pela OpenAI. Com fotos de referência, usa a edição (mantém a aparência)."""
    if referencias:
        arquivos = [('image[]', (f'ref{i}.png', r, _tipo(r))) for i, r in enumerate(referencias)]
        dados = _openai('POST', 'images/edits', files=arquivos,
                        data={'model': _modelo_imagem(), 'prompt': pedido, 'size': '1024x1024'})
    else:
        dados = _openai('POST', 'images/generations',
                        json={'model': _modelo_imagem(), 'prompt': pedido, 'size': '1024x1024', 'n': 1})
    try:
        return base64.b64decode(dados['data'][0]['b64_json'])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ErroIA('a OpenAI não devolveu a imagem') from e


# ---------- Claude ----------

def _claude_texto(instrucao: str, imagens: list[bytes]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=_chave('claude'))
    conteudo = [{'type': 'image', 'source': {'type': 'base64', 'media_type': _tipo(i),
                                             'data': base64.standard_b64encode(i).decode()}}
                for i in imagens] + [{'type': 'text', 'text': instrucao}]
    try:
        resposta = client.beta.messages.create(
            model=MODELO_CLAUDE, max_tokens=4000,
            output_config={'effort': 'low'},
            betas=['server-side-fallback-2026-07-01'], fallbacks='default',
            messages=[{'role': 'user', 'content': conteudo}],
        )
    except anthropic.AuthenticationError as e:
        raise ErroIA('a Anthropic recusou a chave do Claude') from e
    except anthropic.RateLimitError as e:
        raise ErroIA('o Claude recusou por limite de uso; tente mais tarde') from e
    except anthropic.BadRequestError as e:
        raise ErroIA(f'o Claude recusou o pedido: {e.message}') from e
    except anthropic.APIStatusError as e:
        raise ErroIA(f'erro do Claude ({e.status_code}); tente de novo') from e
    except anthropic.APIConnectionError as e:
        raise ErroIA('o Claude não respondeu; confira a conexão') from e
    if resposta.stop_reason == 'refusal':
        raise ErroIA('o Claude não quis descrever estas imagens')
    texto = ''.join(b.text for b in resposta.content if b.type == 'text').strip()
    if not texto:
        raise ErroIA('o Claude não devolveu texto')
    return texto


def _texto(ia: str, instrucao: str, imagens: list[bytes]) -> str:
    if ia not in IAS:
        raise ErroIA(f'IA desconhecida: {ia}')
    return (_openai_texto if ia == 'openai' else _claude_texto)(instrucao, imagens)


# ---------- o que a interface usa ----------

def descrever(dados: dict, imagens: list[bytes], ia: str = 'openai') -> str:
    """Descrição física do personagem (pt-BR), a partir das fotos e da ficha."""
    if not imagens:
        raise ErroIA('envie ao menos uma imagem para descrever')
    instrucao = ('Você ajuda a criar o avatar de um personagem de audiolivro. Descreva em português, '
                 'em um parágrafo curto, a aparência da pessoa nas imagens: rosto, cabelo, pele, idade aparente, '
                 'roupa e estilo. Só o que se vê, sem inventar história. Responda só com o parágrafo.\n\n'
                 + _ficha(dados))
    return _texto(ia, instrucao, imagens)


def pedido_de_imagem(dados: dict, referencias: list[bytes], ia: str = 'openai') -> str:
    """Texto enviado ao desenho. Com o Claude, ele escreve o pedido olhando as referências."""
    base = f'Personagem de livro.\n{_ficha(dados)}\n{ENQUADRAMENTO}'
    if ia == 'openai':
        return base
    instrucao = ('Escreva o pedido para um gerador de imagens criar o avatar deste personagem de audiolivro. '
                 'Use a ficha e, se houver, a aparência das imagens de referência. Seja concreto sobre rosto, '
                 'cabelo, pele, idade, roupa e luz. O enquadramento é obrigatório: ' + ENQUADRAMENTO
                 + ' Responda só com o pedido, em um parágrafo.\n\n' + _ficha(dados))
    return _texto(ia, instrucao, referencias)


def criar_imagem(dados: dict, referencias: list[bytes], ia: str = 'openai') -> tuple[bytes, str]:
    """(PNG, pedido usado). O Claude só escreve o pedido; a OpenAI desenha."""
    _chave('openai')  # sem a OpenAI não há desenho: avisa antes de gastar com o Claude
    pedido = pedido_de_imagem(dados, referencias, ia)
    return desenhar(pedido, referencias), pedido


def validar_chave(ia: str, valor: str) -> None:
    """Confere a chave no provedor sem gastar crédito (lista de modelos)."""
    if ia == 'openai':
        try:
            r = requests.get(f'{OPENAI_URL}/models', headers={'Authorization': f'Bearer {valor}'}, timeout=20)
        except requests.RequestException as e:
            raise ErroIA('a OpenAI não respondeu; tente de novo') from e
        if r.status_code in (401, 403):
            raise ValueError('A OpenAI recusou essa chave; nada foi salvo.')
        if not r.ok:
            raise ErroIA(f'a OpenAI respondeu {r.status_code}; tente de novo')
        return
    import anthropic

    try:
        anthropic.Anthropic(api_key=valor).models.list(limit=1)
    except anthropic.AuthenticationError as e:
        raise ValueError('A Anthropic recusou essa chave; nada foi salvo.') from e
    except anthropic.APIError as e:
        raise ErroIA('não foi possível conferir a chave do Claude; tente de novo') from e
