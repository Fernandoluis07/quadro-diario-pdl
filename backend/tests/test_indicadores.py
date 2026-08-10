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
