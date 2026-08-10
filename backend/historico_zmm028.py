r"""Importa o histórico de 3 dos 4 indicadores da ZMM028 (Itens em Estoque com Saldo, Itens MRP
Saldo Zero, Valor do Estoque Total) pro mesmo formato de historico_mb51.json.

Como historico_manuais.py, este módulo NÃO calcula nada a partir de extrato SAP nenhum — só lê
e normaliza uma planilha de snapshot diário já reconstruída retroativamente (revalidada pelo
usuário contra o dado real de 08/08/2026: 5.335 itens em estoque com saldo).

'Itens sem Endereço' (4º indicador deste bloco) NÃO vem da planilha — grava sempre 0, no mesmo
intervalo dos outros 3, por instrução explícita (essa fonte retroativa ainda não existe).

Uso:
    python -m backend.historico_zmm028 --entrada "C:\caminho\zmm028_retroativo.xlsx"
"""

from __future__ import annotations

import argparse
import json
import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA_PADRAO = os.path.join(REPO_ROOT, "historico_zmm028.json")

# cabeçalho exato da planilha -> chave no JSON (mesmo nome usado em indicadores.py)
COLUNAS_INT = {
    "Itens em Estoque com Saldo": "itens_estoque_com_saldo",
    "Itens MRP Saldo Zero (VB)": "itens_mrp_saldo_zero",
}
COLUNA_VALOR = ("Valor do Estoque Total (R$)", "valor_estoque_total")


def importar_historico_zmm028(caminho_entrada: str) -> dict[str, dict]:
    df = pd.read_excel(caminho_entrada)

    colunas_esperadas = set(COLUNAS_INT) | {COLUNA_VALOR[0]}
    faltando = colunas_esperadas - set(df.columns)
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

    valores_int = {chave: df[col].astype(int).tolist() for col, chave in COLUNAS_INT.items()}
    valores_estoque = df[COLUNA_VALOR[0]].astype(float).round(2).tolist()

    historico: dict[str, dict] = {}
    for i, data in enumerate(datas):
        historico[data.isoformat()] = {
            **{chave: valores_int[chave][i] for chave in COLUNAS_INT.values()},
            COLUNA_VALOR[1]: valores_estoque[i],
            "itens_sem_endereco": 0,  # sem fonte retroativa ainda — fixo em 0, ver docstring
        }
    return dict(sorted(historico.items()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa o histórico manual/reconstruído dos indicadores da ZMM028"
    )
    parser.add_argument("--entrada", required=True, help="Caminho do .xlsx (zmm028_retroativo.xlsx)")
    parser.add_argument("--saida", default=SAIDA_PADRAO, help=f"Caminho do JSON de saída (padrão: {SAIDA_PADRAO})")
    args = parser.parse_args()

    resultado = importar_historico_zmm028(args.entrada)

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    dias = sorted(resultado)
    print(f"Histórico ZMM028 importado: {len(resultado)} dias ({dias[0]} a {dias[-1]}) -> {args.saida}")


if __name__ == "__main__":
    main()
