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


# ---- Tela Gestão de Estoque (ZMM028 D009 + MM60) ----------------------------
# Indicadores 1 e 2 (Materiais Abaixo do Estoque Mínimo / Acima do Estoque Máximo)
# — mesmo recorte D009 dos indicadores 14/15/16/18 acima (df_zmm028_d009 vem de
# extratos.carregar_zmm028). Precisam de preço médio (MM60) porque Val.total da
# ZMM028 é saldo atual × preço — não dá pra usar pra valorar um gap hipotético
# até o mínimo, nem funciona pra material zerado (saldo 0 × preço = 0).
# _normalizar_material (Material '1500022' vs '1500022.0') já existe mais abaixo
# neste módulo (usado pelo Checklist de Reservas) — reaproveitado aqui.

def _mapa_preco_medio(df_mm60: pd.DataFrame) -> pd.Series:
    """Series indexada por Material normalizado -> Preço (float). Material
    duplicado (mais de um Centro na MM60) mantém o primeiro."""
    materiais = _normalizar_material(df_mm60["Material"])
    precos = pd.to_numeric(df_mm60["Preço"], errors="coerce").fillna(0)
    tabela = pd.DataFrame({"_material_norm": materiais, "_preco": precos})
    tabela = tabela.drop_duplicates(subset="_material_norm", keep="first")
    return tabela.set_index("_material_norm")["_preco"]


def _juntar_preco(df: pd.DataFrame, mapa_preco: pd.Series) -> pd.Series:
    """Preço médio por linha de `df`, casado pelo Material. Material sem preço
    cadastrado na MM60 entra como 0 — não descarta a linha, só não soma valor."""
    materiais = _normalizar_material(df["Material"])
    return materiais.map(mapa_preco).fillna(0)


def resumo_vb(df_zmm028_d009: pd.DataFrame) -> tuple[int, float]:
    """(quantidade de materiais VB, valor total em R$ dos materiais VB) — usado
    como denominador comum do percentual dos indicadores 1/2 ("% do valor VB") e
    do rótulo "Total de materiais (VB)" mostrado nos dois cards. Valor vem de
    Val.total (já é saldo × preço), não precisa de MM60 aqui."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]
    valor_total = pd.to_numeric(vb["Val.total"], errors="coerce").fillna(0).sum()
    return int(len(vb)), round(float(valor_total), 2)


def materiais_vb_sem_preco_mm60(df_zmm028_d009: pd.DataFrame, df_mm60: pd.DataFrame) -> list[str]:
    """Códigos de Material (VB, D009) que NÃO têm NENHUMA linha na MM60 — preço R$ 0,00
    cadastrado na MM60 é um preço real e válido pra alguns materiais, não entra aqui,
    só quem está mesmo ausente da planilha. Usado pro alerta do Cabeçalho: a MM60 é a
    ÚNICA fonte de preço, sem cálculo alternativo automático quando falta (ver
    materiais_abaixo_estoque_minimo/materiais_acima_estoque_maximo — o preço desses
    materiais entra como 0 no valor total, não estimado)."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]
    materiais_vb = _normalizar_material(vb["Material"])
    materiais_mm60 = set(_normalizar_material(df_mm60["Material"]))
    faltando = materiais_vb.loc[~materiais_vb.isin(materiais_mm60)]
    return sorted(faltando.unique().tolist())


def materiais_abaixo_estoque_minimo(
    df_zmm028_d009: pd.DataFrame, df_mm60: pd.DataFrame, valor_total_vb: float
) -> dict:
    """Depósito D009, Classificação MRP = VB. Entra na lista quem tem Util.livre
    ESTRITAMENTE menor que Pt.reabast (saldo igual ao ponto de reabastecimento NÃO
    entra). Valor total é o "gap" até o ponto de reabastecimento × preço médio
    (MM60), sempre NEGATIVO (representa o déficit/quanto falta comprar).
    `valor_total_vb` (Val.total somado dos materiais VB, ver resumo_vb) é o
    denominador do percentual — passado de fora pra ser a MESMA base usada pelo
    indicador 2, calculada uma única vez."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]

    util_livre = _util_livre(vb)
    pt_reabast = pd.to_numeric(vb["Pt.reabast"], errors="coerce").fillna(0)
    abaixo = vb.loc[util_livre < pt_reabast]

    gap = pt_reabast.loc[abaixo.index] - util_livre.loc[abaixo.index]
    preco = _juntar_preco(abaixo, _mapa_preco_medio(df_mm60))
    valor_gap = float((gap * preco).sum())

    pct_valor_vb = (valor_gap / valor_total_vb * 100) if valor_total_vb else 0.0

    return {
        "qtd": int(len(abaixo)),
        "valor_total": round(-valor_gap, 2),
        "pct_valor_vb": round(pct_valor_vb, 2),
    }


def materiais_acima_estoque_maximo(
    df_zmm028_d009: pd.DataFrame, df_mm60: pd.DataFrame, valor_total_vb: float
) -> dict:
    """Classificação MRP = VB só (ND fica de fora mesmo que tenha Estq.máx.
    preenchido por engano). "Saldo Atual" é Util.livre — único campo de saldo que
    a ZMM028 tem. Entra na lista quem tem saldo ESTRITAMENTE maior que Estq.máx.
    cadastrado. Valor total é o excesso acima do máximo × preço médio (MM60),
    sempre POSITIVO (capital parado a mais). Mesmo `valor_total_vb` do indicador 1
    como denominador do percentual."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]

    saldo = _util_livre(vb)
    estq_max = pd.to_numeric(vb["Estq.máx."], errors="coerce").fillna(0)
    acima = vb.loc[saldo > estq_max]

    excesso = saldo.loc[acima.index] - estq_max.loc[acima.index]
    preco = _juntar_preco(acima, _mapa_preco_medio(df_mm60))
    valor_excesso = float((excesso * preco).sum())

    pct_valor_vb = (valor_excesso / valor_total_vb * 100) if valor_total_vb else 0.0

    return {
        "qtd": int(len(acima)),
        "valor_total": round(valor_excesso, 2),
        "pct_valor_vb": round(pct_valor_vb, 2),
    }


_CLASSES_MRP_CONHECIDAS = ("VB", "ND", "PD")


def classificacao_mrp(df_zmm028_todos_depositos: pd.DataFrame) -> dict:
    """Indicador 5 — TODOS os materiais com saldo positivo (Util.livre > 0), TODOS
    os depósitos (df_zmm028_todos_depositos vem de
    extratos.carregar_zmm028_todos_depositos, sem o filtro D009 dos outros
    indicadores da ZMM028). Agrupa por Tp.MRP em 4 baldes fixos (VB/ND/PD/Vazios —
    qualquer valor fora de VB/ND/PD, inclusive em branco, cai em "Vazios"), sempre
    nessa ordem, mesmo que algum balde fique zerado num dia. Valor de cada balde é
    a soma de Val.total (já é saldo × preço, não precisa da MM60 aqui)."""
    com_saldo = df_zmm028_todos_depositos.loc[_util_livre(df_zmm028_todos_depositos) > 0]

    tp_mrp = com_saldo["Tp.MRP"].astype(str).str.strip()
    classe = tp_mrp.where(tp_mrp.isin(_CLASSES_MRP_CONHECIDAS), "Vazios")
    valor = pd.to_numeric(com_saldo["Val.total"], errors="coerce").fillna(0)

    itens = []
    for nome in (*_CLASSES_MRP_CONHECIDAS, "Vazios"):
        selecao = classe == nome
        itens.append(
            {
                "classe": nome,
                "qtd": int(selecao.sum()),
                "valor_total": round(float(valor.loc[selecao].sum()), 2),
            }
        )

    return {"total": int(len(com_saldo)), "itens": itens}


# ---- Tela Checklist de Reservas (MB25 x ZMM028) -----------------------------
# Não é um indicador agregado como os de cima — é a lista completa de linhas de
# reserva pendente (uma por linha do MB25), enriquecida com Saldo Atual/Endereço
# do ZMM028 via código do Material. Sempre a fotografia do dia corrente, sem
# histórico por data (congelar.py grava só a constante embutida no HTML).

def _texto_ou_vazio(serie: pd.Series) -> pd.Series:
    """Vazio/NaN vira ''. Colunas de código (Centro custo, Ordem) que misturam
    número com célula vazia sofrem upcast pra float64 no pandas (2003 -> 2003.0)
    — desfaz esse sufixo pra não vazar '.0' num código que devia ser inteiro."""

    def _formatar(v: object) -> str:
        if pd.isna(v):
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    return serie.apply(_formatar)


def _normalizar_material(serie: pd.Series) -> pd.Series:
    """Material pode chegar como '1500022' ou '1500022.0' dependendo da
    formatação da célula de origem — remove o sufixo antes de cruzar."""
    texto = serie.astype(str).str.strip()
    return texto.str.replace(r"\.0$", "", regex=True)


def montar_checklist_reservas(df_mb25: pd.DataFrame, df_zmm028: pd.DataFrame) -> list[dict]:
    """Cruza cada linha de reserva pendente (MB25, já filtrado D009+vazio) com o
    Saldo Atual/Endereço do ZMM028 pelo código do Material. Reserva sem material
    correspondente no ZMM028 não é descartada — Saldo/Endereço ficam vazios.
    Ordenado por Endereço A-Z (linhas sem endereço vão para o final) pra apoiar
    a conferência física andando pelo almoxarifado em sequência."""
    esquerda = df_mb25.copy()
    esquerda["_material_norm"] = _normalizar_material(esquerda["Material"])

    direita = df_zmm028[["Material", "Util.livre", "Pos.dpst."]].copy()
    direita["_material_norm"] = _normalizar_material(direita["Material"])
    direita = direita.drop_duplicates(subset="_material_norm", keep="first")

    cruzado = esquerda.merge(
        direita[["_material_norm", "Util.livre", "Pos.dpst."]], on="_material_norm", how="left"
    )

    datas = pd.to_datetime(cruzado["Data da necessidade"], dayfirst=True, errors="coerce")

    linhas = pd.DataFrame(
        {
            "numero_reserva": _texto_ou_vazio(cruzado["Reserva"]),
            "material": cruzado["_material_norm"],
            "descricao": _texto_ou_vazio(cruzado["Texto breve material"]),
            "data_necessidade": datas.dt.strftime("%d/%m/%Y").fillna(""),
            "qtd_necessaria": pd.to_numeric(cruzado["Qtd.necessária"], errors="coerce").fillna(0),
            "centro_custo": _texto_ou_vazio(cruzado["Centro custo"]),
            "ordem": _texto_ou_vazio(cruzado["Ordem"]),
            "saldo_atual": pd.to_numeric(cruzado["Util.livre"], errors="coerce").fillna(0),
            "endereco": _texto_ou_vazio(cruzado["Pos.dpst."]),
        }
    )

    sem_endereco = linhas["endereco"].eq("")
    linhas = linhas.assign(_sem_endereco=sem_endereco).sort_values(
        by=["_sem_endereco", "endereco"], kind="stable"
    )
    return linhas.drop(columns="_sem_endereco").to_dict(orient="records")
