"""Cálculo dos 15 indicadores automatizáveis do Quadro Diário PDL.

Cada função recebe um DataFrame já carregado/limpo (ver extratos.py) e devolve
o valor do indicador. Nenhuma função lê arquivo — mantém a lógica de negócio
testável isoladamente com DataFrames sintéticos.
"""

from __future__ import annotations

import datetime

import pandas as pd

from . import config


def _filtrar_dia(df: pd.DataFrame, data_ref: datetime.date) -> pd.DataFrame:
    return df.loc[df["_data_norm"] == data_ref]


def _filtrar_deposito(df: pd.DataFrame, deposito: str) -> pd.DataFrame:
    return df.loc[df["_deposito_norm"] == deposito]


# ---- Bloco 1 — Fluxo do Dia (MB51) ----------------------------------------

def linhas_atendidas(df_mb51: pd.DataFrame, deposito: str, data_ref: datetime.date) -> int:
    df = _filtrar_dia(df_mb51, data_ref)
    df = _filtrar_deposito(df, deposito)
    df = df.loc[df["_bwart_norm"].isin(config.BWART_ATENDIMENTO)]
    return len(df)


def estornos(df_mb51: pd.DataFrame, deposito: str, data_ref: datetime.date) -> int:
    df = _filtrar_dia(df_mb51, data_ref)
    df = _filtrar_deposito(df, deposito)
    df = df.loc[df["_bwart_norm"].isin(config.BWART_ESTORNO)]
    return len(df)


def recebimentos(df_mb51: pd.DataFrame, deposito: str, data_ref: datetime.date) -> int:
    """Conta valores ÚNICOS de Referência (nota fiscal) — NÃO conta linha."""
    df = _filtrar_dia(df_mb51, data_ref)
    df = _filtrar_deposito(df, deposito)
    df = df.loc[df["_bwart_norm"].isin(config.BWART_RECEBIMENTO)]
    return df["Referência"].nunique()


def inventario_rotativo(df_mb51: pd.DataFrame, deposito: str, data_ref: datetime.date) -> int:
    """Sem filtro de tipo de movimento. Conta Material único."""
    df = _filtrar_dia(df_mb51, data_ref)
    df = _filtrar_deposito(df, deposito)
    return df["Material"].nunique()


def intercompany(df_mb51: pd.DataFrame, data_ref: datetime.date) -> int:
    """BWART 601/833, conta valores ÚNICOS de Referência (nota fiscal) — um
    documento pode gerar várias linhas, conta como 1 intercompany só. NÃO
    filtra por depósito (D009+D016 juntos, ao contrário dos outros 4 pares
    deste bloco). Sem nenhuma referência 601/833 no dia, retorna 0
    naturalmente (nunique() de uma seleção vazia já é 0)."""
    df = _filtrar_dia(df_mb51, data_ref)
    df = df.loc[df["_bwart_norm"].isin(config.BWART_INTERCOMPANY)]
    return df["Referência"].nunique()


# ---- Bloco 2 — Pendências (MB25) -------------------------------------------
# MB25 já chega pré-filtrada pelo SAP (só reservas em aberto) e é filtrada por
# Depósito D009+vazio antes de chegar aqui — mesma regra dos outros 4
# indicadores separados por depósito. D016 NÃO entra neste bloco.

def pendencias_atendimento_linhas(df_mb25: pd.DataFrame) -> int:
    """Conta todas as linhas, sem remover duplicado nenhum."""
    return len(df_mb25)


def reservas_pendentes(df_mb25: pd.DataFrame) -> int:
    """Conta valores únicos da coluna Reserva."""
    return df_mb25["Reserva"].nunique()


# ---- Bloco 3 — Fotografia do Estoque (ZMM028) ------------------------------
# ZMM028 já chega pré-filtrada por Depósito D009+vazio (extratos.carregar_zmm028)
# — D016 NÃO entra em nenhum destes 4 indicadores.

def _util_livre(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["Util.livre"], errors="coerce").fillna(0)


def itens_estoque_com_saldo(df_zmm028: pd.DataFrame) -> int:
    return int((_util_livre(df_zmm028) != 0).sum())


def valor_estoque_total(df_zmm028: pd.DataFrame) -> float:
    com_saldo = df_zmm028.loc[_util_livre(df_zmm028) != 0]
    valores = pd.to_numeric(com_saldo["Val.total"], errors="coerce").fillna(0)
    return round(float(valores.sum()), 2)


def itens_mrp_saldo_zero(df_zmm028: pd.DataFrame) -> int:
    """Filtra Tp.MRP = VB primeiro, depois conta linhas com Util.livre = 0."""
    tp_mrp = df_zmm028["Tp.MRP"].astype(str).str.strip()
    df_vb = df_zmm028.loc[tp_mrp == "VB"]
    return int((_util_livre(df_vb) == 0).sum())


def itens_sem_endereco(df_zmm028: pd.DataFrame) -> int:
    """Util.livre != 0 E Pos.dpst. vazio/em branco."""
    pos_dpst = df_zmm028["Pos.dpst."].astype(str).str.strip()
    pos_vazia = pos_dpst.eq("") | pos_dpst.eq("nan") | df_zmm028["Pos.dpst."].isna()
    return int(((_util_livre(df_zmm028) != 0) & pos_vazia).sum())
