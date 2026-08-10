r"""Importa o histórico dos 6 indicadores manuais pro mesmo formato de
historico_mb51.json ({'aaaa-mm-dd': {6 campos}, ...}).

Diferente de historico.py, este módulo NÃO calcula nada a partir de extrato
SAP nenhum — só lê e normaliza uma planilha já preenchida célula a célula à
mão, porque essas fontes (MB25 sem histórico — Reservas Pendentes e
Pendências Atendimento Linhas já são calculadas automaticamente pro dia
corrente, mas MB25 não guarda histórico — e indicadores 100% manuais como
Devolução/Scanner de Documentos/NF Pendente Faturamento) não têm como ser
reconstruídas automaticamente pra trás no tempo. A partir do dia seguinte ao
fim desta planilha, o preenchimento passa a ser diário (fora do escopo deste
script).

'Notas Aguardando Lançamento' na planilha é o card 'Contagem Pendentes'
(nº11) do dashboard — nome antigo do card estava incorreto, foi corrigido
pro nome real do indicador de negócio.

Uso:
    python -m backend.historico_manuais --entrada "C:\caminho\indicadores_manuais_consolidado.xlsx"
    python -m backend.historico_manuais --entrada "...xlsx" --saida historico_manuais.json
"""

from __future__ import annotations

import argparse
import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA_PADRAO = os.path.join(REPO_ROOT, "historico_manuais.json")

# cabeçalho exato da planilha (sem acento, confirmado célula a célula) -> chave no JSON.
# a chave já bate com o nome usado pros mesmos 2 indicadores em indicadores.py
# (pendencias_atendimento_linhas, reservas_pendentes), pra ficar consistente em todo o projeto.
COLUNAS = {
    "Notas Aguardando Lancamento": "notas_aguardando_lancamento",
    "Devolucao": "devolucao",
    "Scanner Documentos": "scanner_documentos",
    "NF Pendente Faturamento": "nf_pendente_faturamento",
    "Reservas Pendentes": "reservas_pendentes",
    "Pendencias Atendimento Linhas": "pendencias_atendimento_linhas",
}


def importar_historico_manuais(caminho_entrada: str) -> dict[str, dict]:
    df = pd.read_excel(caminho_entrada)

    faltando = set(COLUNAS) - set(df.columns)
    if faltando:
        raise ValueError(f"Colunas esperadas ausentes na planilha: {sorted(faltando)}")
    if "Data" not in df.columns:
        raise ValueError("Coluna 'Data' ausente na planilha.")

    datas = pd.to_datetime(df["Data"], dayfirst=True, errors="coerce").dt.date
    invalidas = df.loc[datas.isna(), "Data"]
    if len(invalidas):
        raise ValueError(f"Datas inválidas na planilha: {invalidas.tolist()}")

    duplicadas = datas[datas.duplicated()]
    if len(duplicadas):
        raise ValueError(f"Datas duplicadas na planilha: {sorted(set(duplicadas))}")

    # coluna a coluna (não itertuples/itertuples._asdict(): nomes de coluna com espaço são
    # saneados pra _0, _1... e quebrariam o lookup por nome original)
    valores_por_coluna = {
        chave_json: df[col_planilha].astype(int).tolist() for col_planilha, chave_json in COLUNAS.items()
    }
    historico: dict[str, dict] = {}
    for i, data in enumerate(datas):
        historico[data.isoformat()] = {chave: valores_por_coluna[chave][i] for chave in COLUNAS.values()}
    return dict(sorted(historico.items()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa o histórico manual (planilha preenchida à mão) dos 6 indicadores sem fonte SAP retroativa"
    )
    parser.add_argument("--entrada", required=True, help="Caminho do .xlsx (indicadores_manuais_consolidado.xlsx)")
    parser.add_argument("--saida", default=SAIDA_PADRAO, help=f"Caminho do JSON de saída (padrão: {SAIDA_PADRAO})")
    args = parser.parse_args()

    resultado = importar_historico_manuais(args.entrada)

    import json
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    dias = sorted(resultado)
    print(f"Histórico manual importado: {len(resultado)} dias ({dias[0]} a {dias[-1]}) -> {args.saida}")


if __name__ == "__main__":
    main()
