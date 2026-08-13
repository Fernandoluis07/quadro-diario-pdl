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
