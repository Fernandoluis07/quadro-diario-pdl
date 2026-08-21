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


# ---- Tela Gestão de Estoque — Indicadores 1, 2 e 5 --------------------------

def _zmm028_gestao(rows):
    base = {"Material": "", "Util.livre": 0, "Val.total": 0.0, "Tp.MRP": "VB", "Pt.reabast": 0, "Estq.máx.": 0}
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
