"""Lê as 3 extrações, calcula os 14 indicadores e escreve os valores no
index.html existente (mesmo arquivo, mesmo lugar — só os `value:'...'` dos
14 cards automatizados mudam).

Uso:
    python -m backend.gerar_html
    python -m backend.gerar_html --bases-dir "C:\\caminho\\Bases" --data 05/08/2026
    python -m backend.gerar_html --index-path "C:\\caminho\\index.html"
"""

from __future__ import annotations

import argparse
import datetime
import os
import time

from . import html_writer
from .main import _parse_data, calcular_todos_indicadores

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH_PADRAO = os.path.join(REPO_ROOT, "index.html")


def gerar(
    bases_dir: str | None = None,
    data_ref: datetime.date | None = None,
    index_path: str | None = None,
) -> dict:
    index_path = index_path or INDEX_HTML_PATH_PADRAO

    t0 = time.perf_counter()
    indicadores = calcular_todos_indicadores(bases_dir=bases_dir, data_ref=data_ref)
    t1 = time.perf_counter()

    with open(index_path, "r", encoding="utf-8") as f:
        html_original = f.read()

    html_novo, aplicados, nao_encontrados = html_writer.atualizar_html(html_original, indicadores)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_novo)
    t2 = time.perf_counter()

    chaves_mapeadas = {a["indicador"] for a in aplicados}
    chaves_metadados = {"data_referencia", "data_referencia_ontem", "ontem"}
    chaves_indicador = set(indicadores.keys()) - chaves_metadados
    indicadores_sem_card = sorted(chaves_indicador - chaves_mapeadas)

    return {
        "indicadores": indicadores,
        "cards_atualizados": aplicados,
        "cards_nao_encontrados": nao_encontrados,
        "indicadores_sem_card": indicadores_sem_card,
        "index_path": index_path,
        "tempo_calculo_segundos": round(t1 - t0, 3),
        "tempo_escrita_html_segundos": round(t2 - t1, 3),
        "tempo_total_segundos": round(t2 - t0, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o index.html do Quadro Diário PDL com os valores reais")
    parser.add_argument("--bases-dir", default=None)
    parser.add_argument("--data", default=None, help="dd/mm/aaaa (padrão: hoje)")
    parser.add_argument("--index-path", default=None)
    args = parser.parse_args()

    data_ref = _parse_data(args.data) if args.data else None
    resultado = gerar(bases_dir=args.bases_dir, data_ref=data_ref, index_path=args.index_path)

    print(f"index.html atualizado: {resultado['index_path']}")
    print(f"\nCards atualizados ({len(resultado['cards_atualizados'])}):")
    for a in resultado["cards_atualizados"]:
        print(f"  [{a['indicador']}] '{a['card_titulo']}': {a['valor_anterior']} -> {a['valor_novo']}")

    if resultado["cards_nao_encontrados"]:
        print(f"\nATENÇÃO — títulos de card não encontrados no HTML ({len(resultado['cards_nao_encontrados'])}):")
        for t in resultado["cards_nao_encontrados"]:
            print(f"  - {t}")

    if resultado["indicadores_sem_card"]:
        print(f"\nATENÇÃO — indicadores calculados sem card correspondente ({len(resultado['indicadores_sem_card'])}):")
        for k in resultado["indicadores_sem_card"]:
            print(f"  - {k}")

    print(f"\nTempo cálculo (ler planilhas + indicadores): {resultado['tempo_calculo_segundos']}s")
    print(f"Tempo escrita do HTML: {resultado['tempo_escrita_html_segundos']}s")
    print(f"Tempo total: {resultado['tempo_total_segundos']}s")


if __name__ == "__main__":
    main()
