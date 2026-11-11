"""Capítulo WAV completo -> clipes SadTalker com retomada pela cota diária.

Cada personagem aparece com o seu avatar: os cortes nunca atravessam uma troca de
personagem e cada trecho anima a foto de quem está falando nele.
"""

import hashlib
import json
import wave
from pathlib import Path

from dublandio import avatares as registro
from dublandio.config import NARRADOR, Livro, caminho_do_livro
from dublandio.video import ErroVideo, Trecho, _gravar, juntar, recortar
from dublandio.video_hf import SPACE_PADRAO, gerar_video_hf


def _digest(path: Path) -> str:
    with path.open('rb') as arquivo:
        return hashlib.file_digest(arquivo, 'sha256').hexdigest()


def _fontes_avatares(livro: Livro, cap: str, avatares: dict[str, Path] | None) -> tuple[dict, list]:
    segmentos = registro.segmentos(livro, cap)
    avatares = registro.mapa(livro) if avatares is None else avatares
    if faltam := [p for p in dict.fromkeys(s[0] for s in segmentos) if p not in avatares]:
        raise ValueError(f'escolha ou crie um avatar para: {", ".join(faltam)}')
    usados = {p: avatares[p] for p in dict.fromkeys(s[0] for s in segmentos)}
    for imagem in usados.values():
        if not imagem.is_file():
            raise FileNotFoundError(f'arquivo não encontrado: {imagem}')
    repetidos = [str(i) for i in set(usados.values()) if list(usados.values()).count(i) > 1]
    if repetidos:
        raise ValueError('cada personagem precisa de um avatar próprio; imagem repetida: ' + ', '.join(repetidos))
    return ({p: {'caminho': str(i.resolve()), 'sha256': _digest(i)} for p, i in sorted(usados.items())},
            [list(s) for s in segmentos])


def preparar_capitulo(livro: Livro, cap: int, avatares: dict[str, Path] | None = None) -> tuple[dict, Path]:
    """Cria ou confere o progresso do capítulo. `avatares` (personagem -> foto) vem do livro por padrão."""
    if cap < 0:
        raise ValueError('capítulo deve ser positivo ou zero')
    nome = f'cap_{cap:03d}'
    audio = livro.dir_audio / f'{nome}.wav'
    if not audio.is_file():
        raise FileNotFoundError(f'arquivo não encontrado: {audio}')
    with wave.open(str(audio)) as wav:
        total, taxa = wav.getnframes(), wav.getframerate()
    if not total:
        raise ValueError('o capítulo está vazio')
    pasta = livro.dir / 'video' / 'hf' / nome
    path = pasta / 'progresso.json'
    base = {'audio': str(audio.resolve()), 'audio_sha256': _digest(audio),
            'space': SPACE_PADRAO, 'total_amostras': total, 'taxa': taxa}
    if path.exists():
        estado = json.loads(path.read_text(encoding='utf-8'))
        f = estado['fontes']
        f['audio'] = str(caminho_do_livro(livro, f['audio']))
        if 'avatar' in f:  # progresso antigo, de um avatar só: retoma como começou
            f['avatar'] = str(caminho_do_livro(livro, f['avatar']))
            atual = {**base, 'avatar': f['avatar'], 'avatar_sha256': _digest(Path(f['avatar']))}
        else:
            for a in f['avatares'].values():
                a['caminho'] = str(caminho_do_livro(livro, a['caminho']))
            fontes, segmentos = _fontes_avatares(livro, nome, avatares)
            atual = {**base, 'avatares': fontes, 'segmentos': segmentos}
        for trecho in estado['trechos']:
            for campo in ('audio', 'video'):
                trecho[campo] = str(caminho_do_livro(livro, trecho[campo]))
        for campo in ('arquivo', 'previa'):
            if estado.get(campo):
                estado[campo] = str(caminho_do_livro(livro, estado[campo]))
        if f != atual and not estado['trechos'] and 'avatar' not in f:
            estado['fontes'] = f = atual  # nada gerado ainda: vale a escolha atual de avatares
            _gravar(path, estado)
        if f != atual:
            raise ValueError('o áudio ou um avatar mudou desde o início; preserve a pasta de progresso antes de reiniciar')
    else:
        fontes, segmentos = _fontes_avatares(livro, nome, avatares)
        estado = {'fontes': {**base, 'avatares': fontes, 'segmentos': segmentos},
                  'trechos': [], 'proximo_inicio': 0, 'situacao': 'preparado'}
        _gravar(path, estado)
    # Um arquivo apagado não pode transformar um capítulo incompleto em final.
    inicio = 0
    for trecho in estado['trechos']:
        if trecho['inicio'] != inicio:
            raise ValueError('progresso com intervalo ou sobreposição de áudio')
        inicio += trecho['quadros']
        if trecho.get('concluido') and not Path(trecho['video']).is_file():
            trecho['concluido'] = False
    if inicio != estado['proximo_inicio'] or inicio > total:
        raise ValueError('progresso com posição final inconsistente')
    return estado, path


def _segmentos(estado: dict) -> list[list]:
    f = estado['fontes']
    return f.get('segmentos') or [[NARRADOR, 0, f['total_amostras']]]


def _imagem(estado: dict, personagem: str) -> Path:
    f = estado['fontes']
    return Path(f['avatar'] if 'avatar' in f else f['avatares'][personagem]['caminho'])


def _trecho(estado: dict, item: dict) -> Trecho:
    f = estado['fontes']
    personagem = item.get('personagem', NARRADOR)
    return Trecho('capitulo', 0, personagem, str(_imagem(estado, personagem)), f['audio'],
                  item['inicio'], item['quadros'], f['taxa'], Path(item['video']).stem)


def montar_previa(livro: Livro, cap: int, estado: dict, path: Path, montar=juntar) -> None:
    """Monta só o prefixo contínuo já pronto, sempre identificado como parcial."""
    prontos = []
    for t in estado['trechos']:
        if not t.get('concluido'):
            break
        prontos.append(t)
    if prontos:
        previa = livro.dir / 'video' / f'cap_{cap:03d}-hf-parcial.mp4'
        montar([_trecho(estado, t) for t in prontos], [Path(t['video']) for t in prontos], previa, '16:9')
        estado['previa'] = str(previa.resolve())
        _gravar(path, estado)


def executar_capitulo(
    livro: Livro, cap: int, token: str, avatares: dict[str, Path] | None = None, ao_progredir=print,
    consultar_cota=None, gerar=gerar_video_hf, montar=juntar,
) -> dict:
    """Gera só enquanto houver cota incluída. Nenhum crédito extra é solicitado."""
    if not token:
        raise ValueError('HF_TOKEN não definido no .env')
    estado, path = preparar_capitulo(livro, cap, avatares)
    f = estado['fontes']
    total, taxa = f['total_amostras'], f['taxa']
    segmentos = _segmentos(estado)
    if (estado['situacao'] == 'concluido' and estado.get('arquivo')
            and Path(estado['arquivo']).is_file()
            and all(t.get('concluido') for t in estado['trechos'])):
        return estado
    if consultar_cota is None:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        consultar_cota = api.get_zero_gpu_quota
    # Impede duas execuções de consumirem cota para o mesmo trecho.
    trava = path.parent / 'gerando.lock'
    try:
        lock = trava.open('x')
    except FileExistsError as e:
        raise ErroVideo(f'já existe uma geração em andamento; se foi encerrada à força, confira e remova {trava}') from e
    try:
        # Pedidos recusados na admissão não usaram GPU e podem ser recortados.
        recortar_recusado = 'requested GPU duration' in estado.get('ultimo_erro', '')
        estado.pop('ultimo_erro', None)
        while True:
            pendente = next((t for t in estado['trechos'] if not t.get('concluido')), None)
            if pendente is None and estado['proximo_inicio'] >= total:
                estado['situacao'] = 'montando'
                _gravar(path, estado)
                final = livro.dir / 'video' / f'cap_{cap:03d}-hf.mp4'
                montar([_trecho(estado, t) for t in estado['trechos']],
                       [Path(t['video']) for t in estado['trechos']], final, '16:9')
                estado.update(situacao='concluido', arquivo=str(final.resolve()))
                _gravar(path, estado)
                return estado
            try:
                q = consultar_cota()
            except Exception as e:
                detalhe = str(e).replace(token, '[token oculto]')
                raise ErroVideo(f'não foi possível consultar a cota gratuita: {detalhe}') from e
            estado['cota'] = {'restante_segundos': q.remaining, 'renova_em': str(q.resets_at)}
            # A admissão observada aplica 1,5x à reserva declarada pelo Space.
            # 10 s pediram 412 s; limitamos a 5 s e deixamos margem por chamada.
            maximo_segundos = min(5, int((q.remaining / 1.5 - 80) // 20))
            if (pendente and recortar_recusado and maximo_segundos >= 1
                    and pendente is estado['trechos'][-1]
                    and pendente['quadros'] > maximo_segundos * taxa):
                estado['trechos'].pop()
                estado['proximo_inicio'] = pendente['inicio']
                pendente = None
                recortar_recusado = False
            necessario = 1.5 * max(90, int(75 + pendente['quadros'] / taxa * 20)) if pendente else None
            if maximo_segundos < 1 or (necessario and necessario + 5 > q.remaining):
                estado['situacao'] = 'aguardando_cota'
                _gravar(path, estado)
                break
            if pendente is None:
                inicio = estado['proximo_inicio']
                # O corte termina, no máximo, onde o personagem atual para de falar.
                personagem, comeco, quadros_seg = next(s for s in segmentos if s[1] <= inicio < s[1] + s[2])
                quadros = min(int(maximo_segundos * taxa), comeco + quadros_seg - inicio)
                nome = f'trecho_{inicio:012d}_{quadros:09d}'
                pendente = {'inicio': inicio, 'quadros': quadros, 'personagem': personagem,
                            'audio': str((path.parent / f'{nome}.wav').resolve()),
                            'video': str((path.parent / f'{nome}.mp4').resolve()), 'concluido': False}
                estado['trechos'].append(pendente)
                estado['proximo_inicio'] = inicio + quadros
            corte = Path(pendente['audio'])
            if not corte.exists():
                corte.write_bytes(recortar(_trecho(estado, pendente)))
            estado['situacao'] = 'gerando'
            _gravar(path, estado)
            quem = pendente.get('personagem', NARRADOR)
            ao_progredir(f"Gerando {pendente['inicio'] / taxa:.2f}s–{(pendente['inicio'] + pendente['quadros']) / taxa:.2f}s "
                         f"({quem}); cota: {q.remaining:.0f}s de GPU")
            try:
                gerar(_imagem(estado, quem), corte, Path(pendente['video']), token, space=SPACE_PADRAO, ao_progredir=ao_progredir)
            except ErroVideo as e:
                msg = str(e).lower()
                if any(m in msg for m in ('exceeded your zerogpu', 'gpu quota', 'quota exceeded', 'zerogpu runs limit')):
                    estado.update(situacao='aguardando_cota', motivo_pausa=str(e).replace(token, '[token oculto]'))
                    _gravar(path, estado)
                    break
                raise
            pendente['concluido'] = True
            _gravar(path, estado)
        montar_previa(livro, cap, estado, path, montar)
        return estado
    except Exception as e:
        estado['situacao'] = 'interrompido'
        estado['ultimo_erro'] = str(e).replace(token, '[token oculto]')
        _gravar(path, estado)
        raise
    finally:
        lock.close()
        trava.unlink()
