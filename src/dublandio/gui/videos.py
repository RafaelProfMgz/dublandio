"""Dados e arquivos de vídeo expostos pela interface, sem revelar tokens nem caminhos externos."""

import json
import os
import wave
from pathlib import Path

import requests

from dublandio.config import Livro, caminho_do_livro


def validar_token_hf(token: str) -> None:
    r = requests.get('https://huggingface.co/api/whoami-v2',
                     headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if r.status_code in (401, 403):
        raise ValueError('O Hugging Face recusou esse token; nada foi salvo.')
    r.raise_for_status()


def chave_hf(atualizar: bool = False) -> dict:
    token = os.getenv('HF_TOKEN', '')
    resultado = {'configurado': bool(token), 'final': token[-4:] if token else None}
    if atualizar and token:
        from huggingface_hub import HfApi

        try:
            q = HfApi(token=token).get_zero_gpu_quota()
            resultado['cota'] = {'restante_segundos': q.remaining, 'renova_em': str(q.resets_at)}
        except Exception:
            resultado['aviso'] = 'Não foi possível conferir a cota. Confira o token e tente novamente.'
    return resultado


def progresso(livro: Livro, cap: str) -> dict:
    path = livro.dir / 'video' / 'hf' / cap / 'progresso.json'
    resultado = {'situacao': 'nao_iniciado', 'segundos': 0, 'total': None}
    if path.exists():
        try:
            dados = json.loads(path.read_text(encoding='utf-8'))
            f = dados['fontes']
            segundos = 0
            for t in dados['trechos']:
                if not t.get('concluido') or not caminho_do_livro(livro, t['video']).is_file():
                    break
                segundos += t['quadros'] / f['taxa']
            resultado.update(situacao=dados['situacao'], segundos=segundos,
                             total=f['total_amostras'] / f['taxa'], cota=dados.get('cota'),
                             motivo=dados.get('motivo_pausa') or dados.get('ultimo_erro'),
                             avatar_unico='avatar' in f)
        except (ValueError, KeyError, TypeError, OSError):
            resultado.update(situacao='erro', motivo='O progresso salvo não pôde ser lido; os arquivos foram preservados.')
    if resultado['total'] is None:
        try:
            with wave.open(str(livro.dir_audio / f'{cap}.wav')) as wav:
                resultado['total'] = wav.getnframes() / wav.getframerate()
        except (OSError, wave.Error, EOFError):
            pass
    resultado['parcial'] = (livro.dir / 'video' / f'{cap}-hf-parcial.mp4').is_file()
    resultado['final'] = (livro.dir / 'video' / f'{cap}-hf.mp4').is_file()
    return resultado
