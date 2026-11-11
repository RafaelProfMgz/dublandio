#!/usr/bin/env python3
"""
Limpa capítulos .md do vol1 e gera .txt limpos para TTS.
Heurística simples: extrai diálogo quando há '— fala — disse Nome'.
Se não acha nome claro, usa Narrador.
"""
import re
from pathlib import Path

ORIGEM = Path("/home/angel/Documentos/livros/circle_of_titans/05_manuscrito/vol1")
SAIDA = Path("textos_circles")
SAIDA.mkdir(exist_ok=True)

def limpar_texto(texto: str) -> str:
    # Remover título do capítulo
    texto = re.sub(r"#\s*Capítulo\s+\d+[\s\-—].*?$", "", texto, flags=re.MULTILINE)
    # Remover itálico markdown
    texto = texto.replace("*", "")
    return texto

def processar_paragrafo(p: str, contexto: str = "Narrador") -> str:
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
    # Dividir em parágrafos por linhas vazias
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
    
    # Heurística de contexto: rastrear último personagem mencionado em blocos narrativos
    contexto = "Narrador"
    nomes_conhecidos = ["Bright Noa", "Fa Yuiry", "Kamille", "Quattro", "Emma", "Reyes", "Fonoti", "Delgado", "Astonaige", "Lenz", "Green Noa", "Side 7"]
    
    resultado = []
    for b in blocos:
        b_limpo = b.strip()
        if not b_limpo:
            continue
        
        res = processar_paragrafo(b_limpo, contexto)
        
        # Atualiza contexto se o bloco era narrativa (não começa com — ) e menciona personagem
        if not b_limpo.startswith("— ") and not b_limpo.startswith("—"):
            # Tentar extrair nome de personagem mencionado neste bloco narrativo
            for n in nomes_conhecidos:
                # Se o nome aparece no bloco e não é parte de outro nome (ex: Bright Noa dentro de Bright Noa)
                if n in b_limpo:
                    # Verificar se é referência a outro bloco (ex: "o sargento Fonoti")
                    contexto = n.split()[0] if len(n.split()) > 1 else n
                    # Normalizar nomes para chave do mapa
                    if "Bright" in n:
                        contexto = "Bright Noa"
                    elif "Fa" in n:
                        contexto = "Fa Yuiry"
                    elif "Kamille" in n:
                        contexto = "Kamille"
                    elif "Quattro" in n:
                        contexto = "Quattro"
                    elif "Emma" in n:
                        contexto = "Emma"
                    elif "Reyes" in n:
                        contexto = "Reyes"
                    elif "Fonoti" in n:
                        contexto = "Fonoti"
                    elif "Delgado" in n:
                        contexto = "Delgado"
                    elif "Astonaige" in n:
                        contexto = "Astonaige Medoz"
                    break
        
        # Se o resultado é diálogo sem nome claro (ex: "Narrador: Janta" quando deveria ser Fonoti)
        # E se o contexto não é Narrador, tentar corrigir
        if res.startswith("Narrador: ") and not b_limpo.startswith("— "):
            pass  # narrativa real, manter
        elif res.startswith("Narrador: ") and b_limpo.startswith("— "):
            # Diálogo que ficou com Narrador — tentar usar contexto se não é descrição
            fala = res.replace("Narrador: ", "").strip()
            # Se fala é curto (< 60 char) e contexto é personagem, usar contexto
            # Mas cuidado: algumas falas podem ser de Narrador (descrições de ações)
            # Se contém "disse" after a fala, é ação narrada
            if len(fala) < 80 and contexto != "Narrador" and "disse" not in fala[:50] and "parou" not in fala[:50] and "levantou" not in fala[:50]:
                # Tentar usar contexto como falante
                nome_falante = contexto
                # Normalizar para nomes simples usados no mapa
                if nome_falante == "Bright Noa":
                    res = f"Bright Noa: {fala}"
                elif nome_falante == "Fa Yuiry":
                    res = f"Fa Yuiry: {fala}"
                elif nome_falante == "Kamille":
                    res = f"Kamille: {fala}"
                elif nome_falante == "Quattro":
                    res = f"Quattro: {fala}"
                elif nome_falante == "Emma":
                    res = f"Emma: {fala}"
                elif nome_falante == "Reyes":
                    res = f"Reyes: {fala}"
                elif nome_falante == "Fonoti":
                    res = f"Fonoti: {fala}"
                elif nome_falante == "Delgado":
                    res = f"Delgado: {fala}"
                elif nome_falante == "Astonaige Medoz":
                    res = f"Astonaige: {fala}"
                else:
                    res = f"{nome_falante}: {fala}"
        
        if res:
            resultado.append(res)
    
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
