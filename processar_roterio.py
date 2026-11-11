#!/usr/bin/env python3
"""
Processa roteiro no formato:
    Personagem: fala do personagem

Ações:
- Lê guia (JSON/YAML) -> mapa de voz
- Separa blocos por linha vazia (\n\n)
- Extrai nome (antes do primeiro ':') e fala (depois)
- Remove o nome da fala (envia só a fala + voz para IA)
- Gera arquivos .txt limpos em textos_para_tts/
- Gera manifesto.json indexado (ordem, arquivo, personagem, voz, texto)

Uso:
    python3 processar_roterio.py roteiro.txt [nome_saida]
"""
import os, sys, json, re
from pathlib import Path

# --- Config ---
GUIA_JSON = Path("mapa_vozes.json")
GUIA_YAML = Path("guia.yaml")
SAIDA_DIR = Path("textos_para_tts")
MANIFESTO = Path("manifesto.json")

# --- Leitura do guia (JSON nativo = mais rápido; YAML só se tiver pyyaml) ---
def carregar_guia():
    mapa = {}
    # Prioridade: JSON nativo (rápido, sem lib externa)
    if GUIA_JSON.exists():
        try:
            mapa.update(json.loads(GUIA_JSON.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[aviso] erro lendo {GUIA_JSON}: {e}")
    # Se quiser YAML, tenta; se não tiver pyyaml, ignora
    if GUIA_YAML.exists():
        try:
            import yaml
            with open(GUIA_YAML, "r", encoding="utf-8") as f:
                dados = yaml.safe_load(f)
                if isinstance(dados, dict):
                    mapa.update(dados)
        except ImportError:
            pass  # sem pyyaml, ignora YAML
        except Exception as e:
            print(f"[aviso] erro lendo {GUIA_YAML}: {e}")
    # Fallback padrão
    mapa.setdefault("Narrador", "lucian")
    return mapa

# --- Processamento ---
def processar_roterio(origem: Path, stem: str = None):
    texto = origem.read_text(encoding="utf-8")
    guia = carregar_guia()
    SAIDA_DIR.mkdir(exist_ok=True)

    # Detectar formato: se há \n\n, usa blocos; senão, se cada linha tem 'Nome:', trata linha a linha
    if "\n\n" in texto or "\r\n\r\n" in texto:
        blocos_crus = re.split(r"\n\s*\n", texto)
        blocos = [b.strip() for b in blocos_crus if b.strip()]
    else:
        # Formato uma fala por linha (como circle.txt)
        blocos = []
        for linha in texto.splitlines():
            linha = linha.strip()
            if linha:
                blocos.append(linha)

    # Se blocos estão muito grandes (ex: 7 blocos com 30+ linhas), quebrar internamente por linha
    blocos_finais = []
    for b in blocos:
        linhas = [l.strip() for l in b.splitlines() if l.strip()]
        # Heurística: se bloco tem > 3 linhas e várias começam com Nome:, dividir
        if len(linhas) > 3 and sum(1 for l in linhas if re.search(r"^[A-Z][a-záéíóúãõç\.\s]+?:", l)) >= 2:
            for lin in linhas:
                blocos_finais.append(lin)
        else:
            blocos_finais.append(b)
    blocos = blocos_finais

    registros = []
    arquivos_gerados = []

    for idx, bloco in enumerate(blocos, 1):
        # Extrair nome e fala: primeiro ':' separa
        if ":" in bloco:
            nome_raw = bloco.split(":", 1)[0].strip()
            fala = bloco.split(":", 1)[1].strip()
        else:
            nome_raw = "Narrador"
            fala = bloco

        # Normalizar nome (remover acentos? Manter como está, o guia define chave exata)
        nome = nome_raw

        # Buscar voz; se não achar, tenta chave parcial; senão padrão
        voz = guia.get(nome)
        if not voz:
            # Tentativa parcial (ex: "Fonoti" se chave for "Fonoti")
            for k, v in guia.items():
                if nome.lower() == k.lower() or nome in k:
                    voz = v
                    break
        if not voz:
            voz = "weston"  # padrão seguro

        # Limpar fala: remover quebras de linha internas para não quebrar parses futuros
        fala_limpa = " ".join(fala.splitlines()).strip()
        # Remover aspas estranhas no início/fim
        fala_limpa = fala_limpa.strip('"\'')

        # Nome do arquivo de saída (se não passou stem, usa ori)
        out_stem = stem or origem.stem
        txt_path = SAIDA_DIR / f"{out_stem}_{idx:03d}.txt"
        txt_path.write_text(fala_limpa, encoding="utf-8")

        arquivos_gerados.append(txt_path)
        registros.append({
            "ordem": idx,
            "arquivo": str(txt_path.name),
            "personagem": nome,
            "voz_ia": voz,
            "texto": fala_limpa,
            "bloco_raw": bloco[:200] + "..." if len(bloco) > 200 else bloco
        })
        print(f"[{idx:03d}] {nome} -> {voz} | {fala_limpa[:70]}...")

    # Manifesto indexado (array por ordem, mas permite busca linear rápida)
    MANIFESTO.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[ok] {len(registros)} falas -> {SAIDA_DIR}")
    print(f"[ok] manifesto -> {MANIFESTO}")
    return registros

# --- Main ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 processar_roterio.py <arquivo_roterio.txt> [nome_saida]")
        sys.exit(1)

    origem = Path(sys.argv[1])
    stem = sys.argv[2] if len(sys.argv) > 2 else origem.stem
    if not origem.exists():
        print(f"ERRO: arquivo não encontrado: {origem}")
        sys.exit(1)

    processar_roterio(origem, stem)
