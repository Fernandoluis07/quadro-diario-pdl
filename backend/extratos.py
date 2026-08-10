"""Leitura e limpeza das 3 extrações do SAP (MB51, MB25, ZMM028)."""

from __future__ import annotations

import pandas as pd

from . import config


def _detectar_linha_cabecalho(caminho: str, colunas_esperadas: set[str], max_linhas: int = 15) -> int:
    """Alguns relatórios do SAP (ex: ZMM028) vêm com um bloco de título antes do
    cabeçalho de verdade (nome do relatório, data de geração, registros
    processados, linha em branco). Procura a primeira linha cujas células batem
    com as colunas esperadas, em vez de assumir que o cabeçalho é a linha 0."""
    bruto = pd.read_excel(caminho, header=None, nrows=max_linhas, dtype=object)
    for i, row in bruto.iterrows():
        valores = {str(v).strip() for v in row.values if pd.notna(v)}
        if colunas_esperadas.issubset(valores):
            return i
    raise ValueError(
        f"Não encontrei a linha de cabeçalho esperada {colunas_esperadas} "
        f"nas primeiras {max_linhas} linhas de {caminho}"
    )


def _ler_excel(caminho: str, colunas_esperadas: set[str]) -> pd.DataFrame:
    linha_cabecalho = _detectar_linha_cabecalho(caminho, colunas_esperadas)
    df = pd.read_excel(caminho, header=linha_cabecalho, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _descartar_linhas_rodape(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas de rodapé/resumo automático do SAP (sem Material preenchido)."""
    material = df["Material"].astype(str).str.strip()
    vazio = material.eq("") | material.eq("nan") | df["Material"].isna()
    return df.loc[~vazio].copy()


def normalizar_deposito(valor: object) -> str:
    """Vazio/em branco conta como D009 (regra de negócio, seção 3 da especificação)."""
    if pd.isna(valor):
        return config.DEPOSITO_D009
    s = str(valor).strip()
    if s == "" or s.lower() == "nan":
        return config.DEPOSITO_D009
    return s


def normalizar_bwart(valor: object) -> str:
    if pd.isna(valor):
        return ""
    s = str(valor).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s.isdigit():
        s = s.zfill(3)
    return s


def normalizar_data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, dayfirst=True, errors="coerce").dt.date


def datas_disponiveis(df_mb51: pd.DataFrame) -> list:
    """Datas distintas presentes em _data_norm (MB51 já carregado), da mais
    recente pra mais antiga. Usada pra detectar 'hoje'/'ontem' sem depender
    do relógio do computador — a extração pode ter sido gerada de manhã e
    refletir só até o dia anterior."""
    datas = df_mb51["_data_norm"].dropna().unique().tolist()
    return sorted(datas, reverse=True)


def _filtrar_deposito_valido(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém apenas linhas com Depósito = D009, D016 ou vazio (seção 3).
    Descarta qualquer outro valor (D014, D028, D003, etc.)."""
    df = df.copy()
    df["_deposito_norm"] = df["Depósito"].map(normalizar_deposito)
    return df.loc[df["_deposito_norm"].isin(config.DEPOSITOS_VALIDOS)].copy()


def _filtrar_deposito_d009_vazio(df: pd.DataFrame) -> pd.DataFrame:
    """MB25 (Pendências) segue a mesma regra dos outros 4 indicadores separados
    por depósito: só D009+vazio, D016 NÃO entra."""
    df = df.copy()
    df["_deposito_norm"] = df["Depósito"].map(normalizar_deposito)
    return df.loc[df["_deposito_norm"] == config.DEPOSITO_D009].copy()


_COLUNAS_MB51 = {"Material", "Depósito", "Tipo de movimento", "Data de lançamento", "Referência"}
_COLUNAS_MB25 = {"Reserva", "Material", "Depósito"}
_COLUNAS_ZMM028 = {"Material", "Util.livre", "Val.total", "Pos.dpst.", "Tp.MRP"}


def carregar_mb51(caminho: str) -> pd.DataFrame:
    df = _ler_excel(caminho, _COLUNAS_MB51)
    df = _descartar_linhas_rodape(df)
    df = _filtrar_deposito_valido(df)
    df["_bwart_norm"] = df["Tipo de movimento"].map(normalizar_bwart)
    df["_data_norm"] = normalizar_data(df["Data de lançamento"])
    return df


def carregar_mb25(caminho: str) -> pd.DataFrame:
    df = _ler_excel(caminho, _COLUNAS_MB25)
    df = _descartar_linhas_rodape(df)
    df = _filtrar_deposito_d009_vazio(df)
    return df


def carregar_zmm028(caminho: str) -> pd.DataFrame:
    """ZMM028 é um snapshot direto — a regra de filtro de Depósito da seção 3
    aplica-se apenas a MB51 e MB25, então aqui não filtramos por Depósito."""
    df = _ler_excel(caminho, _COLUNAS_ZMM028)
    df = _descartar_linhas_rodape(df)
    return df
