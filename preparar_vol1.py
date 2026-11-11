#!/usr/bin/env python3
"""
Limpa capítulos .md do vol1 e gera .txt limpos para TTS.
Heurística simples: extrai diálogo quando há '— fala — disse Nome'.
Se não acha nome claro, usa Narrador.
"""
import re
from pathlib import Path

ORIGEM = Path("/home/angel/Documentos/livros/o-louco-e-o-bruxo/05_manuscrito/vol1")
SAIDA = Path("textos_para_tts")
SAIDA.mkdir(exist_ok=True)

def limpar_texto(texto: str) -> str:
    # Remover título do capítulo
    texto = re.sub(r"#\s*Capítulo\s+\d+[\s\-—].*?$", "", texto, flags=re.MULTILINE)
    # Remover itálico markdown
    texto = texto.replace("*", "")
    return texto

def processar_paragrafo(p: str) -> str:
    p = p.strip()
    if not p:
        return ""
    # Se começa com travessão de diálogo
    if p.startswith("— ") or p.startswith("—"):
        # Tentar padrão: — fala — disse Nome , / .
        # Captura até o primeiro " — disse " e pega nome depois
        m = re.search(r"—\s+(.*?)\s+—\s+disse\s+([A-Za-záéíóúãõç\.\s]+?)" + r"(?:,|\.|;|\s+—|\n)", p, re.DOTALL)
        if m:
            fala = m.group(1).strip()
            nome_raw = m.group(2).strip()
            # Pegar primeiro nome (ex: Zoltan Chivay -> Zoltan)
            nome = nome_raw.split()[0] if nome_raw.split() else "Narrador"
            # Mas se o nome for "ela", "a mulher", etc., usar Narrador? Vamos manter para revisão
            if nome.lower() in ("ela", "ele", "a", "o", "ela.", "ele.", "a.", "o.", "mulher", "homem", "velho"):
                nome = "Narrador"
            return f"{nome}: {fala}"
        # Outro padrão: apenas — fala seguida de — Nome (sem disse)
        m2 = re.search(r"—\s+(.*?)\s+—\s+([A-Z][a-záéíóúãõç]+)", p, re.DOTALL)
        if m2:
            fala = m2.group(1).strip()
            nome = m2.group(2).strip().split()[0]
            return f"{nome}: {fala}"
        # Se não achou falante claro, manter como narrativa mas sem travessão
        p_limpo = re.sub(r"^—\s+", "", p)
        return f"Narrador: {p_limpo}"
    else:
        return f"Narrador: {p}"

def processar_arquivo(md_path: Path, txt_path: Path):
    texto = md_path.read_text(encoding="utf-8")
    texto = limpar_texto(texto)
    # Dividir em parágrafos por linhas vazias, mas manter diálogo contínuo
    # Vamos juntar linhas que não estão separadas por vazio, mas respeitar parágrafo
    paragrafo = []
    blocos = []
    for linha in texto.splitlines():
        linha = linha.rstrip()
        if linha.strip() == "":
            if paragrafo:
                blocos.append(" ".join(paragrafo))
                paragrafo = []
        else:
            paragrafo.append(linha)
    if paragrafo:
        blocos.append(" ".join(paragrafo))
    
    resultado = []
    for b in blocos:
        res = processar_paragrafo(b)
        if res:
            resultado.append(res)
    
    # Separar blocos por linha em branco
    txt_path.write_text("\n\n".join(resultado), encoding="utf-8")

def main():
    arquivos = sorted(ORIGEM.glob("cap_*.md"))
    for f in arquivos:
        nome = f.stem + ".txt"
        out = SAIDA / nome
        processar_arquivo(f, out)
        print(f"[ok] {nome}")

if __name__ == "__main__":
    main()
