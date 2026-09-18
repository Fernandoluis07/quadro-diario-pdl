import datetime

import pandas as pd

from backend import indicadores

HOJE = datetime.date(2026, 8, 5)
ONTEM = datetime.date(2026, 8, 4)


def _mb51(rows):
    """Monta um DataFrame MB51 já com as colunas normalizadas que
    extratos.carregar_mb51 produziria (_deposito_norm, _bwart_norm, _data_norm)."""
    df = pd.DataFrame(rows)
    return df


def test_linhas_atendidas_conta_linha_sem_dedup():
    df = _mb51(
        [
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
            {"Material": "2", "Referência": "NF2", "_deposito_norm": "D016", "_bwart_norm": "201", "_data_norm": HOJE},
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "999", "_data_norm": HOJE},
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": ONTEM},
        ]
    )
    assert indicadores.linhas_atendidas(df, "D009", HOJE) == 2
    assert indicadores.linhas_atendidas(df, "D016", HOJE) == 1


def test_estornos_conta_linha_sem_dedup():
    df = _mb51(
        [
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "202", "_data_norm": HOJE},
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "202", "_data_norm": HOJE},
            {"Material": "1", "Referência": "NF1", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
        ]
    )
    assert indicadores.estornos(df, "D009", HOJE) == 2


def test_recebimentos_dedup_por_referencia_nao_por_linha_nem_material():
    """A mesma nota fiscal (Referência) pode ter várias linhas/materiais
    diferentes — deve contar 1 por nota, não 1 por linha."""
    df = _mb51(
        [
            {"Material": "1001", "Referência": "NF-100", "_deposito_norm": "D009", "_bwart_norm": "101", "_data_norm": HOJE},
            {"Material": "1002", "Referência": "NF-100", "_deposito_norm": "D009", "_bwart_norm": "101", "_data_norm": HOJE},
            {"Material": "1003", "Referência": "NF-100", "_deposito_norm": "D009", "_bwart_norm": "835", "_data_norm": HOJE},
            {"Material": "1004", "Referência": "NF-200", "_deposito_norm": "D009", "_bwart_norm": "101", "_data_norm": HOJE},
        ]
    )
    assert indicadores.recebimentos(df, "D009", HOJE) == 2


def test_inventario_rotativo_sem_filtro_bwart_dedup_por_material():
    df = _mb51(
        [
            {"Material": "1001", "Referência": "A", "_deposito_norm": "D009", "_bwart_norm": "311", "_data_norm": HOJE},
            {"Material": "1001", "Referência": "B", "_deposito_norm": "D009", "_bwart_norm": "701", "_data_norm": HOJE},
            {"Material": "1002", "Referência": "C", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
        ]
    )
    assert indicadores.inventario_rotativo(df, "D009", HOJE) == 2


def test_intercompany_dedup_por_referencia_filtra_601_e_833():
    df = _mb51(
        [
            # mesma NF (2 linhas, 601) -> conta 1
            {"Material": "1", "Referência": "NF-IC1", "_deposito_norm": "D009", "_bwart_norm": "601", "_data_norm": HOJE},
            {"Material": "2", "Referência": "NF-IC1", "_deposito_norm": "D009", "_bwart_norm": "601", "_data_norm": HOJE},
            # 833, depósito diferente -> NÃO filtra por depósito, conta separado
            {"Material": "3", "Referência": "NF-IC2", "_deposito_norm": "D016", "_bwart_norm": "833", "_data_norm": HOJE},
            # BWART fora de 601/833 -> não conta
            {"Material": "4", "Referência": "NF-IC3", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
            # mesma data mas fora do dia de referência -> não conta
            {"Material": "5", "Referência": "NF-IC4", "_deposito_norm": "D009", "_bwart_norm": "601", "_data_norm": ONTEM},
        ]
    )
    assert indicadores.intercompany(df, HOJE) == 2


def test_intercompany_sem_nenhuma_referencia_601_833_no_dia_retorna_zero():
    df = _mb51(
        [
            {"Material": "1", "Referência": "NF-1", "_deposito_norm": "D009", "_bwart_norm": "201", "_data_norm": HOJE},
        ]
    )
    assert indicadores.intercompany(df, HOJE) == 0


def test_pendencias_atendimento_linhas_conta_tudo_sem_dedup():
    df = pd.DataFrame({"Reserva": ["R1", "R1", "R2"], "Material": ["1", "2", "3"]})
    assert indicadores.pendencias_atendimento_linhas(df) == 3


def test_reservas_pendentes_dedup_por_reserva():
    df = pd.DataFrame({"Reserva": ["R1", "R1", "R2"], "Material": ["1", "2", "3"]})
    assert indicadores.reservas_pendentes(df) == 2


def test_itens_estoque_com_saldo_e_valor_total_ignoram_saldo_zero():
    df = pd.DataFrame(
        {
            "Util.livre": [10, 0, -5, 0],
            "Val.total": [100.5, 999.0, 50.25, 1.0],
        }
    )
    assert indicadores.itens_estoque_com_saldo(df) == 2
    assert indicadores.valor_estoque_total(df) == 150.75


def test_itens_mrp_saldo_zero_filtra_vb_antes_de_contar():
    df = pd.DataFrame(
        {
            "Tp.MRP": ["VB", "VB", "PD", "VB"],
            "Util.livre": [0, 5, 0, 0],
        }
    )
    assert indicadores.itens_mrp_saldo_zero(df) == 2


def test_itens_sem_endereco_exige_saldo_e_pos_dpst_vazia():
    df = pd.DataFrame(
        {
            "Util.livre": [10, 10, 0, 5],
            "Pos.dpst.": ["", None, "", "A-01"],
        }
    )
    assert indicadores.itens_sem_endereco(df) == 2


def _mb25_checklist(rows):
    base = {
        "Reserva": "", "Material": "", "Texto breve material": "", "Depósito": "D009",
        "Qtd.necessária": 0, "Data da necessidade": None, "Centro custo": None, "Ordem": "",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _zmm028_checklist(rows):
    base = {"Material": "", "Util.livre": 0, "Pos.dpst.": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_montar_checklist_reservas_cruza_por_material_e_ordena_por_endereco():
    mb25 = _mb25_checklist(
        [
            {"Reserva": "R1", "Material": "100", "Texto breve material": "Item A", "Qtd.necessária": 5,
             "Data da necessidade": datetime.date(2026, 8, 20), "Centro custo": 2003, "Ordem": "O1"},
            {"Reserva": "R2", "Material": "200", "Texto breve material": "Item B", "Qtd.necessária": 3,
             "Data da necessidade": datetime.date(2026, 8, 21), "Ordem": "O2"},
        ]
    )
    zmm028 = _zmm028_checklist(
        [
            {"Material": "100", "Util.livre": 42, "Pos.dpst.": "0200105201"},
            {"Material": "200", "Util.livre": 7, "Pos.dpst.": "0100101101"},
        ]
    )
    linhas = indicadores.montar_checklist_reservas(mb25, zmm028)
    assert [l["numero_reserva"] for l in linhas] == ["R2", "R1"]  # endereço 01... vem antes de 02...
    assert linhas[0] == {
        "numero_reserva": "R2", "material": "200", "descricao": "Item B",
        "data_necessidade": "21/08/2026", "qtd_necessaria": 3.0, "centro_custo": "",
        "ordem": "O2", "saldo_atual": 7.0, "endereco": "0100101101",
    }
    assert linhas[1]["centro_custo"] == "2003"


def test_montar_checklist_reservas_mantem_linha_sem_material_no_zmm028():
    mb25 = _mb25_checklist([{"Reserva": "R9", "Material": "999", "Texto breve material": "Sem estoque"}])
    zmm028 = _zmm028_checklist([{"Material": "100", "Util.livre": 1, "Pos.dpst.": "A"}])
    linhas = indicadores.montar_checklist_reservas(mb25, zmm028)
    assert len(linhas) == 1
    assert linhas[0]["saldo_atual"] == 0
    assert linhas[0]["endereco"] == ""


def test_montar_checklist_reservas_endereco_vazio_vai_para_o_final():
    mb25 = _mb25_checklist(
        [
            {"Reserva": "R1", "Material": "1"},
            {"Reserva": "R2", "Material": "2"},
        ]
    )
    zmm028 = _zmm028_checklist(
        [
            {"Material": "1", "Pos.dpst.": None},
            {"Material": "2", "Pos.dpst.": "Z-99"},
        ]
    )
    linhas = indicadores.montar_checklist_reservas(mb25, zmm028)
    assert [l["numero_reserva"] for l in linhas] == ["R2", "R1"]


def test_montar_checklist_reservas_normaliza_material_com_sufixo_float():
    mb25 = _mb25_checklist([{"Reserva": "R1", "Material": "1500022.0"}])
    zmm028 = _zmm028_checklist([{"Material": "1500022", "Util.livre": 9, "Pos.dpst.": "A-01"}])
    linhas = indicadores.montar_checklist_reservas(mb25, zmm028)
    assert linhas[0]["material"] == "1500022"
    assert linhas[0]["saldo_atual"] == 9.0


# ---- Tela Gestão de Estoque — Indicadores 1, 2, 4 e 5 -----------------------

def _zmm028_gestao(rows):
    base = {
        "Material": "", "Util.livre": 0, "Val.total": 0.0, "Tp.MRP": "VB", "Pt.reabast": 0, "Estq.máx.": 0,
        "Denom.": "Item x", "Unidade": "UN", "Pos.dpst.": "A-01", "Depósito": "D009",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _mm60(rows):
    return pd.DataFrame([{"Material": m, "Preço": p} for m, p in rows])


def test_materiais_vb_sem_preco_mm60_ignora_preco_zero_valido():
    """Material 2 tem R$ 0,00 cadastrado na MM60 — preço real e válido, não é 'sem
    preço'. Material 3 não aparece na MM60 nenhuma — esse sim entra no alerta.
    Material 4 é ND, fora do escopo (só VB entra)."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Tp.MRP": "VB"},
            {"Material": "2", "Tp.MRP": "VB"},
            {"Material": "3", "Tp.MRP": "VB"},
            {"Material": "4", "Tp.MRP": "ND"},
        ]
    )
    mm60 = _mm60([("1", 10.0), ("2", 0.0)])
    resultado = indicadores.materiais_vb_sem_preco_mm60(zmm028, mm60)
    assert resultado == ["3"]


def test_materiais_vb_sem_preco_mm60_vazio_quando_tudo_cadastrado():
    zmm028 = _zmm028_gestao([{"Material": "1", "Tp.MRP": "VB"}])
    mm60 = _mm60([("1", 10.0)])
    assert indicadores.materiais_vb_sem_preco_mm60(zmm028, mm60) == []


def test_materiais_abaixo_estoque_minimo_e_estrito_igual_nao_entra():
    """Ponto de Reabastecimento 10, saldo 10 -> NÃO entra (não é estritamente menor).
    Saldo 9 -> entra."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 10, "Pt.reabast": 10, "Val.total": 100.0},
            {"Material": "2", "Util.livre": 9, "Pt.reabast": 10, "Val.total": 90.0},
        ]
    )
    mm60 = _mm60([("1", 10.0), ("2", 10.0)])
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=190.0)
    assert resultado["qtd"] == 1


def test_materiais_abaixo_estoque_minimo_valor_e_gap_vezes_preco_negativo():
    """Material 2: gap = Pt.reabast(10) - Util.livre(4) = 6, preço 15 -> -90.0."""
    zmm028 = _zmm028_gestao([{"Material": "2", "Util.livre": 4, "Pt.reabast": 10, "Val.total": 60.0}])
    mm60 = _mm60([("2", 15.0)])
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=60.0)
    assert resultado["valor_total"] == -90.0
    # pct_valor_vb é magnitude (sem sinal) — só valor_total carrega o sinal negativo
    assert resultado["pct_valor_vb"] == 150.0  # 90/60*100


def test_materiais_abaixo_estoque_minimo_material_zerado_usa_preco_mm60_nao_val_total():
    """Saldo 0 -> Val.total também é 0 (0 x preço); o gap tem que usar o preço da
    MM60, não Val.total/Util.livre (que daria 0/0)."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 0, "Pt.reabast": 5, "Val.total": 0.0}])
    mm60 = _mm60([("1", 20.0)])
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=1.0)
    assert resultado["qtd"] == 1
    assert resultado["valor_total"] == -100.0  # gap 5 * preço 20


def test_materiais_abaixo_estoque_minimo_ignora_material_sem_preco_na_mm60():
    """Material fora da MM60 conta na quantidade, mas soma 0 ao valor (não quebra)."""
    zmm028 = _zmm028_gestao([{"Material": "999", "Util.livre": 0, "Pt.reabast": 5, "Val.total": 0.0}])
    mm60 = _mm60([("1", 20.0)])
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=1.0)
    assert resultado["qtd"] == 1
    assert resultado["valor_total"] == 0.0


def test_materiais_acima_estoque_maximo_estrito_igual_nao_entra_e_exclui_nd():
    """Saldo igual ao máximo não entra; ND é excluído mesmo com Estq.máx. preenchido."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 50, "Estq.máx.": 50, "Val.total": 500.0, "Tp.MRP": "VB"},
            {"Material": "2", "Util.livre": 60, "Estq.máx.": 50, "Val.total": 600.0, "Tp.MRP": "VB"},
            {"Material": "3", "Util.livre": 999, "Estq.máx.": 10, "Val.total": 9990.0, "Tp.MRP": "ND"},
        ]
    )
    mm60 = _mm60([("1", 10.0), ("2", 10.0), ("3", 10.0)])
    resultado = indicadores.materiais_acima_estoque_maximo(zmm028, mm60, valor_total_vb=1100.0)
    assert resultado["qtd"] == 1  # só o material 2 (VB, 60 > 50)


def test_materiais_acima_estoque_maximo_valor_e_excesso_vezes_preco_positivo():
    """Material: excesso = 60 - 50 = 10, preço 12 -> +120.0 (positivo)."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 60, "Estq.máx.": 50, "Val.total": 600.0}])
    mm60 = _mm60([("1", 12.0)])
    resultado = indicadores.materiais_acima_estoque_maximo(zmm028, mm60, valor_total_vb=600.0)
    assert resultado["valor_total"] == 120.0
    assert resultado["pct_valor_vb"] == 20.0  # 120/600*100


def test_materiais_abaixo_estoque_minimo_itens_colunas_e_sinal_negativo():
    zmm028 = _zmm028_gestao(
        [{"Material": "2.0", "Util.livre": 4, "Pt.reabast": 10, "Estq.máx.": 50, "Denom.": "Parafuso",
          "Unidade": "UN", "Pos.dpst.": "B-02"}]
    )
    mm60 = _mm60([("2", 15.0)])
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=100.0)
    assert resultado["itens"] == [
        {
            "material": "2", "descricao": "Parafuso", "unidade": "UN", "classe": "VB",
            "saldo_atual": 4.0, "pt_reabast": 10.0, "estoque_maximo": 50.0,
            "quantidade": -6.0, "valor": -90.0, "endereco": "B-02",
        }
    ]


def test_materiais_abaixo_estoque_minimo_itens_sem_preco_mm60_valor_none():
    """Material sem preço na MM60: Quantidade continua calculada normalmente, mas
    Valor fica None (não 0 — 0 pareceria preço real conhecido)."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 4, "Pt.reabast": 10}])
    mm60 = _mm60([("999", 15.0)])  # material 1 não está na MM60
    resultado = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb=100.0)
    assert resultado["itens"][0]["quantidade"] == -6.0
    assert resultado["itens"][0]["valor"] is None


def test_materiais_acima_estoque_maximo_itens_colunas_e_sinal_positivo():
    zmm028 = _zmm028_gestao(
        [{"Material": "1", "Util.livre": 60, "Estq.máx.": 50, "Pt.reabast": 5, "Denom.": "Válvula",
          "Unidade": "PC", "Pos.dpst.": "C-03"}]
    )
    mm60 = _mm60([("1", 12.0)])
    resultado = indicadores.materiais_acima_estoque_maximo(zmm028, mm60, valor_total_vb=600.0)
    item = resultado["itens"][0]
    assert item["quantidade"] == 10.0
    assert item["valor"] == 120.0
    assert item["descricao"] == "Válvula"
    assert item["endereco"] == "C-03"


# ---- Indicador 4 — Materiais Nunca Movimentados -----------------------------

def _mb51_mov(rows):
    # -1 por padrão: baixa real nessa planilha vem SEMPRE com quantidade negativa
    # (confirmado contra a MB51 real — ver indicadores._materiais_com_baixa_real).
    # Testes de entrada (BWART 101) não olham o sinal, então o default serve pros dois.
    base = {
        "Material": "", "_deposito_norm": "D009", "_bwart_norm": "", "_data_norm": HOJE,
        "Qtd.  UM registro": -1,
    }
    if not rows:
        # pd.DataFrame([]) não tem colunas nenhuma — mantém o schema mesmo vazio,
        # igual extratos.carregar_mb51() sempre devolve (mesmo filtrado a zero linhas).
        return pd.DataFrame(columns=list(base.keys()))
    return pd.DataFrame([{**base, **r} for r in rows])


def test_materiais_nunca_movimentados_exclui_quem_teve_saida_real():
    """Material 1 teve uma saída (201, BWART_ATENDIMENTO) -> excluído. Material 2
    nunca teve nenhuma linha -> entra na lista."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 10},
            {"Material": "2", "Util.livre": 5},
        ]
    )
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201"}])
    mm60 = _mm60([("1", 1.0), ("2", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=2, hoje=HOJE
    )
    assert [i["material"] for i in resultado["itens"]] == ["2"]
    assert resultado["qtd"] == 1


def test_materiais_nunca_movimentados_702_e_z30_contam_como_baixa_real():
    """702 e Z30 não são exceção — contam como baixa real igual qualquer BWART de
    atendimento, cada um excluindo o material correspondente da lista."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 10},
            {"Material": "2", "Util.livre": 10},
            {"Material": "3", "Util.livre": 10},
        ]
    )
    mb51 = _mb51_mov(
        [
            {"Material": "1", "_bwart_norm": "702"},
            {"Material": "2", "_bwart_norm": "Z30"},
        ]
    )
    mm60 = _mm60([("1", 1.0), ("2", 1.0), ("3", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=3, hoje=HOJE
    )
    assert [i["material"] for i in resultado["itens"]] == ["3"]


def test_materiais_nunca_movimentados_baixa_com_quantidade_zero_nao_conta():
    """Baixa (BWART de saída real) com quantidade 0 é ajuste administrativo (fechar/
    cancelar reserva errada) — não representa saída física, não exclui o material."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "Qtd.  UM registro": 0}])
    mm60 = _mm60([("1", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
    )
    assert resultado["qtd"] == 1  # continua "nunca movimentado"


def test_materiais_nunca_movimentados_exige_saldo_positivo():
    """Material com saldo 0 ou negativo é só cadastro sem estoque, não "capital
    físico parado" — não entra na lista mesmo sem nenhuma saída registrada."""
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 0},
            {"Material": "2", "Util.livre": -3},
            {"Material": "3", "Util.livre": 10},
        ]
    )
    mb51 = _mb51_mov([])
    mm60 = _mm60([("1", 1.0), ("2", 1.0), ("3", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=3, hoje=HOJE
    )
    assert [i["material"] for i in resultado["itens"]] == ["3"]


def test_materiais_nunca_movimentados_entrada_sozinha_nao_exclui():
    """Material só tem ENTRADA (101, BWART_RECEBIMENTO) — comprou/recebeu, nunca
    saiu — continua na lista de nunca movimentados."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "101", "_data_norm": datetime.date(2023, 1, 10)}])
    mm60 = _mm60([("1", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
    )
    assert resultado["qtd"] == 1
    assert resultado["itens"][0]["data_entrada"] == "2023-01-10"


def test_materiais_nunca_movimentados_saida_em_d016_tambem_conta():
    """Regra de exclusão NÃO filtra por depósito — "já teve baixa em qualquer
    depósito" (D009 ou D016), não só no D009 específico (validado manualmente por
    Fernando contra a MB51 real). Só o universo de candidatos (ZMM028) é D009;
    a checagem de baixa na MB51 olha os dois juntos."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_deposito_norm": "D016"}])
    mm60 = _mm60([("1", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
    )
    assert resultado["qtd"] == 0


def test_materiais_nunca_movimentados_baixa_com_quantidade_positiva_tambem_conta():
    """A regra é quantidade DIFERENTE de zero, não "menor que zero" — não depende
    de baixa vir sempre negativa (mesmo sendo o padrão observado na prática)."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "Qtd.  UM registro": 5}])
    mm60 = _mm60([("1", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
    )
    assert resultado["qtd"] == 0


def test_materiais_nunca_movimentados_entrada_ampla_cobre_ajuste_de_inventario():
    """Data de Entrada não é só nota fiscal (101/835) — também conta ajuste de
    inventário/entrada não-nota, legada e atual (918/Z15/Z29/701/920)."""
    for bwart in ("918", "Z15", "Z29", "701", "920"):
        zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
        mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": bwart, "_data_norm": datetime.date(2023, 1, 10)}])
        mm60 = _mm60([("1", 1.0)])
        resultado = indicadores.materiais_nunca_movimentados(
            zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
        )
        assert resultado["itens"][0]["data_entrada"] == "2023-01-10", f"falhou pro BWART {bwart}"


def test_materiais_nunca_movimentados_sem_entrada_conhecida_data_e_tempo_ficam_none():
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([])
    mm60 = _mm60([("1", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=1, hoje=HOJE
    )
    item = resultado["itens"][0]
    assert item["data_entrada"] is None
    assert item["tempo_parado"] is None


def test_materiais_nunca_movimentados_valor_e_percentuais():
    """Saldo 10 x preço 5 = 50.0. pct_valor_vb sobre valor_total_vb=500 -> 10%.
    pct_distribuicao sobre total_materiais_vb=4 (1 de 4) -> 25%."""
    zmm028 = _zmm028_gestao([{"Material": "1", "Util.livre": 10}])
    mb51 = _mb51_mov([])
    mm60 = _mm60([("1", 5.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=500.0, total_materiais_vb=4, hoje=HOJE
    )
    assert resultado["valor_total"] == 50.0
    assert resultado["pct_valor_vb"] == 10.0
    assert resultado["pct_distribuicao"] == 25.0


def test_materiais_nunca_movimentados_ordena_entrada_mais_antiga_primeiro():
    zmm028 = _zmm028_gestao(
        [
            {"Material": "1", "Util.livre": 10},
            {"Material": "2", "Util.livre": 10},
            {"Material": "3", "Util.livre": 10},
        ]
    )
    mb51 = _mb51_mov(
        [
            {"Material": "1", "_bwart_norm": "101", "_data_norm": datetime.date(2024, 6, 1)},
            {"Material": "2", "_bwart_norm": "101", "_data_norm": datetime.date(2022, 1, 15)},
            # material 3: sem entrada nenhuma -> vai pro final
        ]
    )
    mm60 = _mm60([("1", 1.0), ("2", 1.0), ("3", 1.0)])
    resultado = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb=100.0, total_materiais_vb=3, hoje=HOJE
    )
    assert [i["material"] for i in resultado["itens"]] == ["2", "1", "3"]


def test_formatar_tempo_parado_anos_e_meses():
    assert indicadores._formatar_tempo_parado(datetime.date(2023, 3, 5), datetime.date(2026, 8, 5)) == "3 anos e 5 meses"
    assert indicadores._formatar_tempo_parado(datetime.date(2026, 5, 5), datetime.date(2026, 8, 5)) == "3 meses"
    assert indicadores._formatar_tempo_parado(datetime.date(2025, 8, 5), datetime.date(2026, 8, 5)) == "1 ano"
    assert indicadores._formatar_tempo_parado(datetime.date(2026, 8, 5), datetime.date(2026, 8, 5)) == "0 meses"
    assert indicadores._formatar_tempo_parado(datetime.date(2026, 7, 20), datetime.date(2026, 8, 5)) == "0 meses"


def test_classificacao_mrp_agrupa_por_classe_e_manda_zero_e_negativo_pra_fora():
    """Saldo <= 0 não entra em nenhum balde; Tp.MRP em branco cai em 'Vazios';
    depósito D016 entra (indicador 5 não filtra depósito)."""
    df = pd.DataFrame(
        [
            {"Material": "1", "Util.livre": 10, "Val.total": 100.0, "Tp.MRP": "VB", "Depósito": "D009"},
            {"Material": "2", "Util.livre": 5, "Val.total": 50.0, "Tp.MRP": "ND", "Depósito": "D016"},
            {"Material": "3", "Util.livre": 2, "Val.total": 20.0, "Tp.MRP": "PD", "Depósito": "D028"},
            {"Material": "4", "Util.livre": 1, "Val.total": 10.0, "Tp.MRP": "", "Depósito": "D009"},
            {"Material": "5", "Util.livre": 0, "Val.total": 0.0, "Tp.MRP": "VB", "Depósito": "D009"},
            {"Material": "6", "Util.livre": -3, "Val.total": -30.0, "Tp.MRP": "VB", "Depósito": "D009"},
        ]
    )
    resultado = indicadores.classificacao_mrp(df)
    assert resultado["total"] == 4  # materiais 1,2,3,4 (saldo 0 e negativo ficam fora)
    itens_por_classe = {i["classe"]: i for i in resultado["itens"]}
    assert set(itens_por_classe) == {"VB", "ND", "PD", "Vazios"}
    assert itens_por_classe["VB"] == {"classe": "VB", "qtd": 1, "valor_total": 100.0}
    assert itens_por_classe["ND"] == {"classe": "ND", "qtd": 1, "valor_total": 50.0}
    assert itens_por_classe["PD"] == {"classe": "PD", "qtd": 1, "valor_total": 20.0}
    assert itens_por_classe["Vazios"] == {"classe": "Vazios", "qtd": 1, "valor_total": 10.0}


def test_resumo_vb_conta_e_soma_so_classificacao_vb():
    df = _zmm028_gestao(
        [
            {"Material": "1", "Val.total": 100.0, "Tp.MRP": "VB"},
            {"Material": "2", "Val.total": 200.0, "Tp.MRP": "VB"},
            {"Material": "3", "Val.total": 999.0, "Tp.MRP": "ND"},
        ]
    )
    qtd, valor = indicadores.resumo_vb(df)
    assert qtd == 2
    assert valor == 300.0


# ---- Indicador 6 — Avaliação de MRP -----------------------------------------
# Especificação final validada com Fernando 2026-08-24/25 (ver docstring de
# indicadores.avaliacao_mrp) — saldo combinado D009+D016, âncora em 2 arquivos somados
# por material, consumo só com BWART_BAIXA_REAL, sem filtro/dedup de movimento nenhum.

def _saldo_ancora_d009(rows):
    base = {"Material": "", "Classificacao MRP": "VB", "Saldo em 01/04/2026": 0}
    return pd.DataFrame([{**base, **r} for r in rows])


def _saldo_ancora_d016(rows):
    if not rows:
        return pd.DataFrame(columns=["Material", "Saldo em 01/04/2026 (D016)"])
    base = {"Material": "", "Saldo em 01/04/2026 (D016)": 0}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_saldo_ancora_combinado_filtra_vb_e_soma_d009_com_d016():
    d009 = _saldo_ancora_d009(
        [
            {"Material": "1", "Classificacao MRP": "VB", "Saldo em 01/04/2026": 10},
            {"Material": "2", "Classificacao MRP": "ND", "Saldo em 01/04/2026": 999},  # fora, não é VB
        ]
    )
    d016 = _saldo_ancora_d016([{"Material": "1", "Saldo em 01/04/2026 (D016)": 5}])
    resultado = indicadores._saldo_ancora_combinado(d009, d016)
    assert len(resultado) == 1
    linha = resultado.iloc[0]
    assert linha["_material_norm"] == "1"
    assert linha["_saldo_ancora"] == 15.0


def test_saldo_ancora_combinado_material_sem_linha_no_d016_entra_com_zero():
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 7}])
    d016 = _saldo_ancora_d016([])
    resultado = indicadores._saldo_ancora_combinado(d009, d016)
    assert resultado.iloc[0]["_saldo_ancora"] == 7.0


def test_reconstruir_saldo_material_conta_zeragem_positivo_pra_zero_ou_negativo():
    movimentos = pd.DataFrame(
        [
            {"data": datetime.date(2026, 4, 5), "bwart": "201", "quantidade": -5.0},  # 10 -> 5
            {"data": datetime.date(2026, 4, 6), "bwart": "201", "quantidade": -5.0},  # 5 -> 0 (zeragem)
            {"data": datetime.date(2026, 4, 10), "bwart": "101", "quantidade": 8.0},  # 0 -> 8
            {"data": datetime.date(2026, 4, 12), "bwart": "201", "quantidade": -10.0},  # 8 -> -2 (zeragem)
        ]
    )
    resultado = indicadores._reconstruir_saldo_material(movimentos, saldo_inicial=10.0)
    assert resultado["zeragens"] == 2
    assert resultado["ultimo_dia_zerou"] == datetime.date(2026, 4, 12)
    assert resultado["ultimo_dia_mov"] == datetime.date(2026, 4, 12)
    assert resultado["datas_zeragem"] == [datetime.date(2026, 4, 6), datetime.date(2026, 4, 12)]


def test_reconstruir_saldo_material_transferencia_resolvida_no_mesmo_instante_nao_zera():
    """Duas pontas de uma transferência entre depósitos somam 0 na soma combinada —
    partindo de um saldo já positivo (ver 805280, validado por Fernando 2026-08-25:
    âncora combinada 20, sobe pra 40 e volta pra 20), o saldo nunca cai abaixo/igual a
    zero vindo de positivo, então não conta zeragem. (Partir de saldo 0 é um caso
    diferente — aí sim cruza de positivo pra zero de verdade, ver teste abaixo.)"""
    movimentos = pd.DataFrame(
        [
            {"data": datetime.date(2026, 4, 8), "bwart": "311", "quantidade": 20.0},
            {"data": datetime.date(2026, 4, 8), "bwart": "311", "quantidade": -20.0},
        ]
    )
    resultado = indicadores._reconstruir_saldo_material(movimentos, saldo_inicial=20.0)
    assert resultado["zeragens"] == 0


def test_reconstruir_saldo_material_transferencia_partindo_de_zero_conta_zeragem():
    """Diferente do teste acima: partindo de saldo_inicial 0, subir e voltar pra 0
    cruza de positivo (20) pra zero de verdade — é uma zeragem real, não um artefato
    da transferência (a soma ainda fecha em 0, mas passou por >0 no meio)."""
    movimentos = pd.DataFrame(
        [
            {"data": datetime.date(2026, 4, 8), "bwart": "311", "quantidade": 20.0},
            {"data": datetime.date(2026, 4, 8), "bwart": "311", "quantidade": -20.0},
        ]
    )
    resultado = indicadores._reconstruir_saldo_material(movimentos, saldo_inicial=0.0)
    assert resultado["zeragens"] == 1


def test_reconstruir_saldo_material_soma_saidas_reais_ignora_bwart_fora_de_baixa_real():
    """soma_saidas_reais só conta negativo com BWART em config.BWART_BAIXA_REAL
    (atendimento + 702 + Z30) — um estorno negativo (BWART_ESTORNO) não entra."""
    movimentos = pd.DataFrame(
        [
            {"data": datetime.date(2026, 4, 5), "bwart": "201", "quantidade": -5.0},  # baixa real, conta
            {"data": datetime.date(2026, 4, 6), "bwart": "202", "quantidade": -3.0},  # estorno, NÃO conta
            {"data": datetime.date(2026, 4, 7), "bwart": "702", "quantidade": -2.0},  # baixa real (702), conta
        ]
    )
    resultado = indicadores._reconstruir_saldo_material(movimentos, saldo_inicial=100.0)
    assert resultado["soma_saidas_reais"] == -7.0


def test_reconstruir_saldo_material_movimento_zero_nao_gera_zeragem_extra():
    movimentos = pd.DataFrame(
        [
            {"data": datetime.date(2026, 4, 5), "bwart": "201", "quantidade": -5.0},  # 5 -> 0 (zeragem)
            {"data": datetime.date(2026, 4, 6), "bwart": "201", "quantidade": 0.0},  # continua em 0
        ]
    )
    resultado = indicadores._reconstruir_saldo_material(movimentos, saldo_inicial=5.0)
    assert resultado["zeragens"] == 1


def test_tempo_medio_reposicao_media_dos_intervalos():
    datas_zeragem = [datetime.date(2026, 4, 10), datetime.date(2026, 5, 1)]
    datas_entrada = [datetime.date(2026, 4, 15), datetime.date(2026, 5, 6)]  # 5 dias, 5 dias
    assert indicadores._tempo_medio_reposicao(datas_zeragem, datas_entrada) == 5.0


def test_tempo_medio_reposicao_ignora_zeragem_sem_entrada_seguinte():
    """2ª zeragem não tem nenhuma entrada depois dela — só a 1ª entra na média."""
    datas_zeragem = [datetime.date(2026, 4, 10), datetime.date(2026, 8, 1)]
    datas_entrada = [datetime.date(2026, 4, 15)]
    assert indicadores._tempo_medio_reposicao(datas_zeragem, datas_entrada) == 5.0


def test_tempo_medio_reposicao_sem_nenhuma_entrada_retorna_none():
    assert indicadores._tempo_medio_reposicao([datetime.date(2026, 4, 10)], []) is None
    assert indicadores._tempo_medio_reposicao([datetime.date(2026, 4, 10)], None) is None


def test_classificar_criticidade_consumo_maior_que_maximo_e_critico_capado_em_100():
    nivel, criticidade = indicadores._classificar_criticidade(consumo_medio_mensal=50.0, estoque_maximo=40.0)
    assert nivel == "critico"
    assert criticidade == 100  # proporção real é 125%, mas a barra capa em 100


def test_classificar_criticidade_cortes_alto_e_medio():
    nivel_alto, pct_alto = indicadores._classificar_criticidade(consumo_medio_mensal=7.0, estoque_maximo=10.0)
    assert (nivel_alto, pct_alto) == ("alto", 70)

    nivel_medio, pct_medio = indicadores._classificar_criticidade(consumo_medio_mensal=6.9, estoque_maximo=10.0)
    assert (nivel_medio, pct_medio) == ("medio", 69)


def test_classificar_criticidade_maximo_zero_com_consumo_positivo_e_critico():
    """Estoque Máximo não cadastrado (0) e consumo real positivo -> crítico, mesma
    regra matemática (consumo > máximo), sem tratamento especial pro caso 0."""
    nivel, criticidade = indicadores._classificar_criticidade(consumo_medio_mensal=5.0, estoque_maximo=0.0)
    assert nivel == "critico"
    assert criticidade == 100


def test_classificar_criticidade_maximo_e_consumo_zero_e_medio_sem_dividir_por_zero():
    nivel, criticidade = indicadores._classificar_criticidade(consumo_medio_mensal=0.0, estoque_maximo=0.0)
    assert (nivel, criticidade) == ("medio", 0)


def test_avaliacao_mrp_material_que_zera_entra_com_todos_os_campos():
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 5}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "1", "Denom.": "Parafuso", "Pt.reabast": 3, "Estq.máx.": 20}])
    mb51 = _mb51_mov(
        [
            {"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 10), "Qtd.  UM registro": -5},  # 5 -> 0, zeragem
            {"Material": "1", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 15), "Qtd.  UM registro": 10},  # entrada, repõe
        ]
    )
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["qtd"] == 1
    item = resultado["itens"][0]
    assert item["material"] == "1"
    assert item["descricao"] == "Parafuso"
    assert item["classe"] == "VB"
    assert item["vezesZerou"] == 1
    assert item["ultimoZerou"] == "10/04/2026"
    assert item["tempoReposicao"] == 5.0  # 15/04 - 10/04
    assert item["min"] == 3.0
    assert item["max"] == 20.0


def test_avaliacao_mrp_quem_nunca_zera_fica_de_fora_mesmo_com_movimento():
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 100}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "1", "Pt.reabast": 3, "Estq.máx.": 20}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 10), "Qtd.  UM registro": -5}])
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["qtd"] == 0


def test_avaliacao_mrp_ignora_classificacao_diferente_de_vb():
    d009 = _saldo_ancora_d009([{"Material": "1", "Classificacao MRP": "ND", "Saldo em 01/04/2026": 5}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "1", "Pt.reabast": 3, "Estq.máx.": 20}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 10), "Qtd.  UM registro": -5}])
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["qtd"] == 0


def test_avaliacao_mrp_material_sem_zmm028_hoje_fica_de_fora():
    """VB no arquivo-âncora mas não existe mais na ZMM028 de hoje -> sem Estoque
    Mínimo/Máximo pra cruzar, não entra (decisão explícita, ver docstring)."""
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 5}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "999", "Pt.reabast": 3, "Estq.máx.": 20}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 10), "Qtd.  UM registro": -5}])
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["qtd"] == 0


def test_avaliacao_mrp_movimento_anterior_a_01_04_e_ignorado():
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 5}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "1", "Pt.reabast": 3, "Estq.máx.": 20}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 3, 31), "Qtd.  UM registro": -5}])
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["qtd"] == 0


def test_avaliacao_mrp_consumo_medio_mensal_soma_saidas_reais_sobre_meses_decorridos():
    """Saída real de -30 em 01/05 (30 dias corridos após a âncora 01/04) -> consumo
    mensal = 30 / (30/30) = 30.0. Material também zera pra entrar na lista."""
    d009 = _saldo_ancora_d009([{"Material": "1", "Saldo em 01/04/2026": 30}])
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao([{"Material": "1", "Pt.reabast": 3, "Estq.máx.": 100}])
    mb51 = _mb51_mov([{"Material": "1", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -30}])
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert resultado["itens"][0]["consumo"] == 30.0


def test_avaliacao_mrp_ordena_por_criticidade_nao_por_vezes_zerou():
    """Material A zera 5x mas é MÉDIO (consumo bem abaixo do máximo); material B zera
    só 1x mas é CRÍTICO (consumo > máximo); material C zera 3x e é ALTO. A ordem tem
    que ser B, C, A (crítico > alto > médio) — o oposto da ordem por vezesZerou
    (A=5x, C=3x, B=1x), pra provar que trocou o critério de verdade (pedido do usuário
    2026-08-25) e não só coincide num caso particular."""
    d009 = _saldo_ancora_d009(
        [
            {"Material": "A", "Saldo em 01/04/2026": 5},
            {"Material": "B", "Saldo em 01/04/2026": 5},
            {"Material": "C", "Saldo em 01/04/2026": 3},
        ]
    )
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao(
        [
            {"Material": "A", "Pt.reabast": 1, "Estq.máx.": 100},
            {"Material": "B", "Pt.reabast": 1, "Estq.máx.": 10},
            {"Material": "C", "Pt.reabast": 1, "Estq.máx.": 10},
        ]
    )
    mb51 = _mb51_mov(
        [
            # A: zera 5x, saídas somam -17 num mês -> consumo 17, 17/100=17% -> médio
            {"Material": "A", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 5), "Qtd.  UM registro": -5},
            {"Material": "A", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 6), "Qtd.  UM registro": 3},
            {"Material": "A", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 7), "Qtd.  UM registro": -3},
            {"Material": "A", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 8), "Qtd.  UM registro": 3},
            {"Material": "A", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 9), "Qtd.  UM registro": -3},
            {"Material": "A", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 10), "Qtd.  UM registro": 3},
            {"Material": "A", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 11), "Qtd.  UM registro": -3},
            {"Material": "A", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 12), "Qtd.  UM registro": 3},
            {"Material": "A", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -3},
            # B: zera 1x, saída -20 num mês -> consumo 20, > máximo 10 -> crítico
            {"Material": "B", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -20},
            # C: zera 3x, saídas somam -8 num mês -> consumo 8, 8/10=80% -> alto
            {"Material": "C", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 5), "Qtd.  UM registro": -3},
            {"Material": "C", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 6), "Qtd.  UM registro": 2},
            {"Material": "C", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 7), "Qtd.  UM registro": -2},
            {"Material": "C", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 8), "Qtd.  UM registro": 3},
            {"Material": "C", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -3},
        ]
    )
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    niveis = {i["material"]: i["nivel"] for i in resultado["itens"]}
    assert niveis == {"A": "medio", "B": "critico", "C": "alto"}
    assert [i["material"] for i in resultado["itens"]] == ["B", "C", "A"]


def test_avaliacao_mrp_desempate_dentro_do_mesmo_nivel_por_percentual_criticidade_desc():
    """Dois materiais 'alto' — o de maior % de criticidade vem primeiro."""
    d009 = _saldo_ancora_d009(
        [
            {"Material": "X", "Saldo em 01/04/2026": 3},
            {"Material": "Y", "Saldo em 01/04/2026": 3},
        ]
    )
    d016 = _saldo_ancora_d016([])
    zmm028 = _zmm028_gestao(
        [
            {"Material": "X", "Pt.reabast": 1, "Estq.máx.": 10},  # consumo 7 -> 70%
            {"Material": "Y", "Pt.reabast": 1, "Estq.máx.": 10},  # consumo 9 -> 90%
        ]
    )
    mb51 = _mb51_mov(
        [
            {"Material": "X", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 5), "Qtd.  UM registro": -3},
            {"Material": "X", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 6), "Qtd.  UM registro": 4},
            {"Material": "X", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -4},
            {"Material": "Y", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 4, 5), "Qtd.  UM registro": -3},
            {"Material": "Y", "_bwart_norm": "101", "_data_norm": datetime.date(2026, 4, 6), "Qtd.  UM registro": 6},
            {"Material": "Y", "_bwart_norm": "201", "_data_norm": datetime.date(2026, 5, 1), "Qtd.  UM registro": -6},
        ]
    )
    resultado = indicadores.avaliacao_mrp(zmm028, mb51, d009, d016)
    assert [i["material"] for i in resultado["itens"]] == ["Y", "X"]
