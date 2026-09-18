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


def _montar_itens_gap(subset: pd.DataFrame, quantidade: pd.Series, mapa_preco: pd.Series, sinal: int) -> list[dict]:
    """Lista detalhada (exportação) dos indicadores 1/2 — mesmas colunas nos dois,
    só muda o sinal de Quantidade/Valor (`sinal` +1/-1; `quantidade` já vem em
    módulo/positiva). Material sem preço cadastrado na MM60 fica com Valor = None
    (não 0 — 0 pareceria um preço real conhecido; a MM60 é fonte única, sem
    estimativa automática quando falta, ver materiais_vb_sem_preco_mm60)."""
    materiais_norm = _normalizar_material(subset["Material"])
    preco = materiais_norm.map(mapa_preco)  # NaN = sem preço na MM60
    valor = quantidade * preco * sinal

    tabela = pd.DataFrame(
        {
            "material": materiais_norm,
            "descricao": subset["Denom."].astype(str).str.strip(),
            "unidade": subset["Unidade"].astype(str).str.strip(),
            "classe": subset["Tp.MRP"].astype(str).str.strip(),
            "saldo_atual": _util_livre(subset).round(2),
            "pt_reabast": pd.to_numeric(subset["Pt.reabast"], errors="coerce").fillna(0).round(2),
            "estoque_maximo": pd.to_numeric(subset["Estq.máx."], errors="coerce").fillna(0).round(2),
            "quantidade": (quantidade * sinal).round(2),
            "valor": valor.round(2),
            "endereco": subset["Pos.dpst."].astype(str).str.strip(),
        }
    )
    registros = tabela.to_dict(orient="records")
    for r in registros:
        if pd.isna(r["valor"]):
            r["valor"] = None
    return registros


def materiais_abaixo_estoque_minimo(
    df_zmm028_d009: pd.DataFrame, df_mm60: pd.DataFrame, valor_total_vb: float
) -> dict:
    """Depósito D009, Classificação MRP = VB. Entra na lista quem tem Util.livre
    ESTRITAMENTE menor que Pt.reabast (saldo igual ao ponto de reabastecimento NÃO
    entra). Valor total é o "gap" até o ponto de reabastecimento × preço médio
    (MM60), sempre NEGATIVO (representa o déficit/quanto falta comprar).
    `valor_total_vb` (Val.total somado dos materiais VB, ver resumo_vb) é o
    denominador do percentual — passado de fora pra ser a MESMA base usada pelo
    indicador 2, calculada uma única vez. `itens`: lista detalhada pra exportação
    (Código/Descrição/Unidade/Classificação/Saldo/Pt.reabast/Estq.máx./Quantidade
    negativa/Valor negativo/Endereço)."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]

    util_livre = _util_livre(vb)
    pt_reabast = pd.to_numeric(vb["Pt.reabast"], errors="coerce").fillna(0)
    abaixo = vb.loc[util_livre < pt_reabast]

    gap = pt_reabast.loc[abaixo.index] - util_livre.loc[abaixo.index]
    mapa_preco = _mapa_preco_medio(df_mm60)
    preco = _juntar_preco(abaixo, mapa_preco)
    valor_gap = float((gap * preco).sum())

    pct_valor_vb = (valor_gap / valor_total_vb * 100) if valor_total_vb else 0.0

    return {
        "qtd": int(len(abaixo)),
        "valor_total": round(-valor_gap, 2),
        "pct_valor_vb": round(pct_valor_vb, 2),
        "itens": _montar_itens_gap(abaixo, gap, mapa_preco, sinal=-1),
    }


def materiais_acima_estoque_maximo(
    df_zmm028_d009: pd.DataFrame, df_mm60: pd.DataFrame, valor_total_vb: float
) -> dict:
    """Classificação MRP = VB só (ND fica de fora mesmo que tenha Estq.máx.
    preenchido por engano). "Saldo Atual" é Util.livre — único campo de saldo que
    a ZMM028 tem. Entra na lista quem tem saldo ESTRITAMENTE maior que Estq.máx.
    cadastrado. Valor total é o excesso acima do máximo × preço médio (MM60),
    sempre POSITIVO (capital parado a mais). Mesmo `valor_total_vb` do indicador 1
    como denominador do percentual. `itens`: mesma lista do indicador 1, com
    Quantidade/Valor POSITIVOS (excesso, não déficit)."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]

    saldo = _util_livre(vb)
    estq_max = pd.to_numeric(vb["Estq.máx."], errors="coerce").fillna(0)
    acima = vb.loc[saldo > estq_max]

    excesso = saldo.loc[acima.index] - estq_max.loc[acima.index]
    mapa_preco = _mapa_preco_medio(df_mm60)
    preco = _juntar_preco(acima, mapa_preco)
    valor_excesso = float((excesso * preco).sum())

    pct_valor_vb = (valor_excesso / valor_total_vb * 100) if valor_total_vb else 0.0

    return {
        "qtd": int(len(acima)),
        "valor_total": round(valor_excesso, 2),
        "pct_valor_vb": round(pct_valor_vb, 2),
        "itens": _montar_itens_gap(acima, excesso, mapa_preco, sinal=1),
    }


def _formatar_tempo_parado(data_entrada: datetime.date, hoje: datetime.date) -> str:
    """'3 anos e 5 meses' — omite a parte de anos quando for 0 (ex: '5 meses')."""
    meses_totais = (hoje.year - data_entrada.year) * 12 + (hoje.month - data_entrada.month)
    if hoje.day < data_entrada.day:
        meses_totais -= 1
    meses_totais = max(meses_totais, 0)
    anos, meses = divmod(meses_totais, 12)

    partes = []
    if anos > 0:
        partes.append(f"{anos} ano" if anos == 1 else f"{anos} anos")
    if meses > 0 or anos == 0:
        partes.append(f"{meses} mês" if meses == 1 else f"{meses} meses")
    return " e ".join(partes)


def _materiais_com_baixa_real(df_mb51: pd.DataFrame) -> set[str]:
    """Materiais (código normalizado) com pelo menos uma linha de baixa/saída real
    — BWART em config.BWART_BAIXA_REAL (Atendimento + 702 + Z30, sem exceção) E
    quantidade (coluna "Qtd.  UM registro" — dois espaços, é o nome real da MB51)
    DIFERENTE DE ZERO. Checa "!= 0", não só "< 0": baixa nessa planilha costuma vir
    negativa na prática (confirmado contra a MB51 real), mas a regra de negócio não
    depende dessa suposição de sinal. Baixa com quantidade exatamente 0 é ajuste
    administrativo (fechar/cancelar reserva ou ordem errada), não representa saída
    física — não conta como "material já teve movimento" em NENHUM lugar que usar
    esse conceito, não só o indicador 4 (por isso é uma função à parte, reutilizável).

    NÃO filtra por depósito — quem decide isso é o chamador, passando o recorte de
    MB51 que fizer sentido pro caso de uso (ver materiais_nunca_movimentados, que
    passa a MB51 inteira, D009 e D016 juntos: "já teve baixa alguma vez, em
    qualquer depósito" é a pergunta, não "já teve baixa no depósito específico X")."""
    bwart_ok = df_mb51["_bwart_norm"].isin(config.BWART_BAIXA_REAL)
    quantidade = pd.to_numeric(df_mb51["Qtd.  UM registro"], errors="coerce").fillna(0)
    baixas = df_mb51.loc[bwart_ok & (quantidade != 0)]
    return set(_normalizar_material(baixas["Material"]))


def materiais_nunca_movimentados(
    df_zmm028_d009: pd.DataFrame,
    df_mb51_completo: pd.DataFrame,
    df_mm60: pd.DataFrame,
    valor_total_vb: float,
    total_materiais_vb: int,
    hoje: datetime.date,
) -> dict:
    """Indicador 4 — universo (candidatos): Depósito D009, Classificação MRP = VB,
    SALDO POSITIVO (Util.livre > 0 — material zerado é só cadastro sem estoque, não
    "capital físico parado", não entra).

    A REGRA DE EXCLUSÃO ("já teve baixa real"), por outro lado, olha a MB51
    COMPLETA — `df_mb51_completo` (extratos.carregar_mb51, sem filtro de dia) SEM
    filtrar por depósito, D009 e D016 juntos (ver _materiais_com_baixa_real): a
    pergunta é "esse material já saiu fisicamente alguma vez, em qualquer
    depósito", não "já saiu do D009 especificamente". Não importa COMO o material
    entrou (nota fiscal, ajuste de inventário, etc.) pra essa regra — só a saída
    importa; o próprio saldo positivo na ZMM028 já prova que houve entrada, seja
    qual for o tipo. Validado manualmente por Fernando, código por código, contra a
    MB51 real: 2.637 candidatos - baixa real (qualquer depósito) = 495 nunca
    movimentados.

    "Data de Entrada" (só pra Tempo Parado — não afeta quem entra/sai da lista) é a
    PRIMEIRA linha de entrada em config.BWART_ENTRADA_AMPLA (nota fiscal normal
    101/835 + ajuste de inventário/entrada não-nota, legada e atual: 918/Z15/Z29/
    701/920), também sem filtrar depósito, mesma lógica da baixa. Sem nenhuma
    entrada registrada no período coberto pela MB51, fica None (Tempo Parado não é
    calculável, não estimado).

    `pct_valor_vb`: % do valor sobre o valor total dos materiais VB (mesma base de
    1/2). `pct_distribuicao`: % da QUANTIDADE de materiais sobre o total de
    materiais VB (`total_materiais_vb`, ver resumo_vb) — indicador diferente, não
    confundir com pct_valor_vb."""
    tp_mrp = df_zmm028_d009["Tp.MRP"].astype(str).str.strip()
    vb = df_zmm028_d009.loc[tp_mrp == "VB"]
    vb = vb.loc[_util_livre(vb) > 0].copy()
    vb["_material_norm"] = _normalizar_material(vb["Material"])

    materiais_com_saida = _materiais_com_baixa_real(df_mb51_completo)
    nunca_mov = vb.loc[~vb["_material_norm"].isin(materiais_com_saida)]

    mb51_entrada = df_mb51_completo.copy()
    mb51_entrada["_material_norm"] = _normalizar_material(mb51_entrada["Material"])
    entradas = mb51_entrada.loc[mb51_entrada["_bwart_norm"].isin(config.BWART_ENTRADA_AMPLA)]
    primeira_entrada = entradas.groupby("_material_norm")["_data_norm"].min()

    mapa_preco = _mapa_preco_medio(df_mm60)
    preco = nunca_mov["_material_norm"].map(mapa_preco)
    saldo = _util_livre(nunca_mov)
    valor = saldo * preco  # NaN onde o material não tem preço na MM60

    valor_total = float(valor.fillna(0).sum())
    pct_valor_vb = (valor_total / valor_total_vb * 100) if valor_total_vb else 0.0
    pct_distribuicao = (len(nunca_mov) / total_materiais_vb * 100) if total_materiais_vb else 0.0

    tabela = pd.DataFrame(
        {
            "material": nunca_mov["_material_norm"],
            "descricao": nunca_mov["Denom."].astype(str).str.strip(),
            "unidade": nunca_mov["Unidade"].astype(str).str.strip(),
            "classe": nunca_mov["Tp.MRP"].astype(str).str.strip(),
            "quantidade": saldo.round(2),
            "endereco": nunca_mov["Pos.dpst."].astype(str).str.strip(),
            "valor": valor.round(2),
            "_data_entrada": nunca_mov["_material_norm"].map(primeira_entrada),
        }
    )

    registros = []
    for r in tabela.to_dict(orient="records"):
        data_entrada = r.pop("_data_entrada")
        if pd.isna(r["valor"]):
            r["valor"] = None
        if pd.notna(data_entrada):
            r["data_entrada"] = data_entrada.isoformat()
            r["tempo_parado"] = _formatar_tempo_parado(data_entrada, hoje)
        else:
            r["data_entrada"] = None
            r["tempo_parado"] = None
        registros.append(r)

    # entrada mais antiga primeiro; sem entrada conhecida vai pro final
    registros.sort(key=lambda r: (r["data_entrada"] is None, r["data_entrada"] or ""))

    return {
        "qtd": int(len(nunca_mov)),
        "valor_total": round(valor_total, 2),
        "pct_valor_vb": round(pct_valor_vb, 2),
        "pct_distribuicao": round(pct_distribuicao, 2),
        "itens": registros,
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


# ---- Indicador 6 — Avaliação de MRP (tela Gestão de Estoque) ----------------
# Especificação final validada com Fernando 2026-08-24/25 contra dado real de
# 21/08/2026, depois de duas rodadas de investigação de divergência: a primeira versão
# (só D009) batia nos materiais com maior frequência de zeragem mas divergia no total
# (351 vs 348 zeraram, 52 vs 44 críticos) e a segunda (D009+D016 somados mas com âncora
# só do D009) fazia 17 materiais terminarem com saldo combinado NEGATIVO — impossível
# fisicamente — porque a âncora de partida não incluía o saldo real que esses materiais
# já tinham no D016 em 01/04. A versão final usa os DOIS arquivos-âncora (D009 e D016,
# separados por decisão de rastreabilidade — ver config.SALDO_ANCORA_D009/D016_FILENAME)
# somados por material, e isso eliminou os 17 saldos negativos por completo. Dois dos 5
# materiais de maior frequência da validação original mudaram de resultado com a âncora
# corrigida (805280 nunca mais zera — tinha saldo real no D016 que a âncora antiga não
# via; 856949 caiu de 4x pra 3x) — Fernando confirmou os dois manualmente contra o SAP.

DATA_REF_SALDO_ANCORA = datetime.date(2026, 4, 1)
_CORTE_CRITICIDADE_ALTO = 0.7
# ordem de exibição da tabela (pedido do usuário 2026-08-25: crítico no topo, depois
# alto, depois médio) — não é ordem alfabética nem a ordem que GE_CRIT_LABEL usa no
# front-end, é só o rank pra sort() abaixo.
_ORDEM_NIVEL_CRITICIDADE = {"critico": 0, "alto": 1, "medio": 2}


def _saldo_ancora_combinado(df_saldo_ancora_d009: pd.DataFrame, df_saldo_ancora_d016: pd.DataFrame) -> pd.DataFrame:
    """Universo do indicador 6 (só Classificação MRP = VB, do arquivo D009 — o D016 não
    tem essa coluna) com o saldo-âncora de 01/04/2026 já combinado (D009 + D016, soma
    por material; quem não aparece no arquivo D016 entra com 0 ali, sem erro)."""
    classe = df_saldo_ancora_d009["Classificacao MRP"].astype(str).str.strip()
    vb = df_saldo_ancora_d009.loc[classe == "VB"].copy()
    vb["_material_norm"] = _normalizar_material(vb["Material"])
    vb["_saldo_d009"] = pd.to_numeric(vb["Saldo em 01/04/2026"], errors="coerce").fillna(0)
    vb = vb.drop_duplicates(subset="_material_norm", keep="first")

    d016 = df_saldo_ancora_d016.copy()
    d016["_material_norm"] = _normalizar_material(d016["Material"])
    d016["_saldo_d016"] = pd.to_numeric(d016["Saldo em 01/04/2026 (D016)"], errors="coerce").fillna(0)
    mapa_d016 = d016.drop_duplicates(subset="_material_norm", keep="first").set_index("_material_norm")["_saldo_d016"]

    vb["_saldo_ancora"] = vb["_saldo_d009"] + vb["_material_norm"].map(mapa_d016).fillna(0)
    return vb


def _reconstruir_saldo_material(movimentos: pd.DataFrame, saldo_inicial: float) -> dict:
    """Caminha CRONOLOGICAMENTE, linha a linha (não agregado por dia — testado contra
    dado real: agregar por dia escondia zeragens intra-dia que Fernando confirmou como
    reais), pelos movimentos já combinados D009+D016 de UM material, a partir do saldo-
    âncora combinado. `movimentos` precisa vir ordenado por data (ver avaliacao_mrp) e
    com as colunas data/bwart/quantidade.

    Transferência entre depósitos (313/315/311/... — qualquer tipo, sem lista fixa)
    soma as duas pontas na mesma conta, então se cancela sozinha; só não cancela no
    MESMO instante se as pontas caírem em linhas diferentes na ordem cronológica, o que
    pode registrar uma zeragem tecnicamente real mas causada pelo trânsito da
    transferência — aceito por decisão de Fernando (não filtramos por tipo de
    movimento em lugar nenhum daqui, nem deduplicamos linha nenhuma da MB51)."""
    saldo = saldo_inicial
    zeragens = 0
    ultimo_dia_zerou = None
    datas_zeragem: list[datetime.date] = []
    soma_saidas_reais = 0.0
    ultimo_dia_mov = None

    for row in movimentos.itertuples(index=False):
        saldo_antes = saldo
        saldo += row.quantidade
        if row.quantidade < 0 and row.bwart in config.BWART_BAIXA_REAL:
            soma_saidas_reais += row.quantidade
        if row.data is not None:
            ultimo_dia_mov = row.data
        if saldo_antes > 0 and saldo <= 0:
            zeragens += 1
            ultimo_dia_zerou = row.data
            datas_zeragem.append(row.data)

    return {
        "zeragens": zeragens,
        "ultimo_dia_zerou": ultimo_dia_zerou,
        "soma_saidas_reais": soma_saidas_reais,
        "ultimo_dia_mov": ultimo_dia_mov,
        "datas_zeragem": datas_zeragem,
    }


def _tempo_medio_reposicao(datas_zeragem: list, datas_entrada: list | None) -> float | None:
    """Média de dias corridos entre cada zeragem e a entrada real (BWART_ENTRADA_AMPLA)
    seguinte do MESMO material — inclui qualquer tempo "circulando" entre depósitos,
    porque `datas_entrada` já vem do universo combinado D009+D016 (ver avaliacao_mrp).
    Zeragem sem nenhuma entrada real depois dela (material ainda zerado, não repôs)
    fica fora da média — não dá pra medir um intervalo que ainda não terminou. Material
    sem NENHUM intervalo calculável devolve None, não 0 (mesma convenção de "não
    calculável" de materiais_nunca_movimentados/_formatar_tempo_parado)."""
    if not datas_entrada:
        return None
    intervalos = []
    for data_zerou in datas_zeragem:
        seguintes = [d for d in datas_entrada if d >= data_zerou]
        if seguintes:
            intervalos.append((min(seguintes) - data_zerou).days)
    if not intervalos:
        return None
    return round(sum(intervalos) / len(intervalos), 1)


def _classificar_criticidade(consumo_medio_mensal: float, estoque_maximo: float) -> tuple[str, int]:
    """CRÍTICO: consumo médio mensal já ultrapassa o Estoque Máximo cadastrado —
    matematicamente impossível não zerar com esse parâmetro (regra de negócio, ver
    especificação). Sem isso, ALTO/MÉDIO pela proporção consumo/máximo — corte em 70%
    é escolha de implementação (sem critério de negócio definido, Fernando autorizou
    decidir), não um número validado por ele. `criticidade` (0-100, só pra largura da
    barra visual) é sempre a proporção CAPADA em 100% — o rótulo textual de crítico não
    usa esse número capado, mas também não expõe a proporção real (pode passar de
    100%); é só pra barra não ficar maior que o próprio track."""
    if estoque_maximo > 0:
        proporcao = consumo_medio_mensal / estoque_maximo
    else:
        proporcao = 1.0 if consumo_medio_mensal > 0 else 0.0

    if consumo_medio_mensal > estoque_maximo:
        nivel = "critico"
    elif proporcao >= _CORTE_CRITICIDADE_ALTO:
        nivel = "alto"
    else:
        nivel = "medio"

    criticidade = round(min(proporcao, 1.0) * 100)
    return nivel, criticidade


def avaliacao_mrp(
    df_zmm028_d009: pd.DataFrame,
    df_mb51_completo: pd.DataFrame,
    df_saldo_ancora_d009: pd.DataFrame,
    df_saldo_ancora_d016: pd.DataFrame,
) -> dict:
    """Indicador 6 — só materiais que zeraram (saldo combinado D009+D016 passou de
    positivo pra zero/negativo) pelo menos 1 vez desde 01/04/2026. `df_zmm028_d009` é
    só pra Estoque Mínimo/Máximo (Pt.reabast/Estq.máx.) — continua só D009, mesma fonte
    dos indicadores 1/2, SEM mudança (decisão explícita de Fernando: combinar depósito
    é só pra reconstrução de saldo/consumo, não pros parâmetros cadastrados)."""
    ancora = _saldo_ancora_combinado(df_saldo_ancora_d009, df_saldo_ancora_d016)

    mb51 = df_mb51_completo.loc[df_mb51_completo["_data_norm"] >= DATA_REF_SALDO_ANCORA].copy()
    mb51["_material_norm"] = _normalizar_material(mb51["Material"])
    tabela_mov = pd.DataFrame(
        {
            "material": mb51["_material_norm"],
            "data": mb51["_data_norm"],
            "bwart": mb51["_bwart_norm"],
            "quantidade": pd.to_numeric(mb51["Qtd.  UM registro"], errors="coerce").fillna(0),
        }
    ).sort_values("data", kind="stable")
    movimentos_por_material = {mat: grupo for mat, grupo in tabela_mov.groupby("material")}

    entradas = tabela_mov.loc[tabela_mov["bwart"].isin(config.BWART_ENTRADA_AMPLA)]
    entradas_por_material = {mat: sorted(grupo["data"].tolist()) for mat, grupo in entradas.groupby("material")}

    zmm028 = df_zmm028_d009.copy()
    zmm028["_material_norm"] = _normalizar_material(zmm028["Material"])
    zmm028 = zmm028.drop_duplicates(subset="_material_norm", keep="first").set_index("_material_norm")

    registros = []
    for _, anc in ancora.iterrows():
        material = anc["_material_norm"]
        if material not in zmm028.index:
            continue
        movimentos = movimentos_por_material.get(material)
        if movimentos is None or movimentos.empty:
            continue

        reconstrucao = _reconstruir_saldo_material(movimentos, anc["_saldo_ancora"])
        if reconstrucao["zeragens"] == 0:
            continue

        linha_zmm028 = zmm028.loc[material]
        estoque_minimo = pd.to_numeric(linha_zmm028["Pt.reabast"], errors="coerce")
        estoque_minimo = float(estoque_minimo) if pd.notna(estoque_minimo) else 0.0
        estoque_maximo = pd.to_numeric(linha_zmm028["Estq.máx."], errors="coerce")
        estoque_maximo = float(estoque_maximo) if pd.notna(estoque_maximo) else 0.0

        dias_decorridos = max((reconstrucao["ultimo_dia_mov"] - DATA_REF_SALDO_ANCORA).days, 1)
        meses_decorridos = dias_decorridos / 30
        consumo_medio_mensal = round(-reconstrucao["soma_saidas_reais"] / meses_decorridos, 2)

        tempo_reposicao = _tempo_medio_reposicao(reconstrucao["datas_zeragem"], entradas_por_material.get(material))
        nivel, criticidade = _classificar_criticidade(consumo_medio_mensal, estoque_maximo)

        registros.append(
            {
                "material": material,
                "descricao": str(linha_zmm028["Denom."]).strip(),
                "classe": "VB",
                "consumo": consumo_medio_mensal,
                "vezesZerou": reconstrucao["zeragens"],
                "ultimoZerou": reconstrucao["ultimo_dia_zerou"].strftime("%d/%m/%Y"),
                "tempoReposicao": tempo_reposicao,
                "min": round(estoque_minimo, 2),
                "max": round(estoque_maximo, 2),
                "criticidade": criticidade,
                "nivel": nivel,
            }
        )

    # Ordem da tabela: nível de criticidade primeiro (Crítico > Alto > Médio, ver
    # _ORDEM_NIVEL_CRITICIDADE), % de criticidade decrescente dentro do mesmo nível —
    # trocado de "vezes que zerou" pra isso a pedido do usuário 2026-08-25, pra quem
    # abre a tela ver primeiro o que é mais grave agora, não só o que zerou mais vezes
    # no passado (as duas coisas não são a mesma coisa — ver 808275 no histórico da
    # conversa: zera bastante mas não é o mais crítico).
    registros.sort(key=lambda r: (_ORDEM_NIVEL_CRITICIDADE[r["nivel"]], -r["criticidade"], r["material"]))
    return {"qtd": len(registros), "itens": registros}


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
