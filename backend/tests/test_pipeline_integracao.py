"""Teste de integração: grava 3 planilhas .xlsx sintéticas (com o mesmo layout
de colunas e peculiaridades do SAP real — linha de rodapé sem Material,
Depósito vazio, tipo de movimento com variação de formato) e roda o pipeline
completo (extratos + indicadores) fim a fim, sem depender dos arquivos reais
da rede da empresa."""

import datetime

import pandas as pd

from backend import config, extratos, indicadores

HOJE = datetime.date(2026, 8, 5)


def _escrever(path, df):
    df.to_excel(path, index=False)


def test_pipeline_completo_com_planilhas_sinteticas(tmp_path):
    mb51 = pd.DataFrame(
        [
            {
                "Material": "1001", "Texto breve material": "Parafuso", "Centro": "2003",
                "Depósito": "D009", "Tipo de movimento": 201, "Data de lançamento": "05.08.2026",
                "Qtd. UM registro": 5, "UM registro": "UN", "Montante em MI": 10.0,
                "Reserva": "R1", "Referência": "NF-1", "Nome do usuário": "fernando",
            },
            {
                "Material": "1002", "Texto breve material": "Porca", "Centro": "2003",
                "Depósito": "", "Tipo de movimento": "101", "Data de lançamento": "05.08.2026",
                "Qtd. UM registro": 2, "UM registro": "UN", "Montante em MI": 4.0,
                "Reserva": "R2", "Referência": "NF-2", "Nome do usuário": "fernando",
            },
            {
                "Material": "1003", "Texto breve material": "Arruela", "Centro": "2003",
                "Depósito": "D016", "Tipo de movimento": 261, "Data de lançamento": "05.08.2026",
                "Qtd. UM registro": 1, "UM registro": "UN", "Montante em MI": 1.0,
                "Reserva": "R3", "Referência": "NF-3", "Nome do usuário": "fernando",
            },
            {
                "Material": "1004", "Texto breve material": "Excluída (D014)", "Centro": "2003",
                "Depósito": "D014", "Tipo de movimento": 201, "Data de lançamento": "05.08.2026",
                "Qtd. UM registro": 1, "UM registro": "UN", "Montante em MI": 1.0,
                "Reserva": "R4", "Referência": "NF-4", "Nome do usuário": "fernando",
            },
            # linha de rodapé/resumo do SAP (sem Material) -> deve ser descartada
            {
                "Material": None, "Texto breve material": "*** Total ***", "Centro": None,
                "Depósito": None, "Tipo de movimento": None, "Data de lançamento": None,
                "Qtd. UM registro": 9, "UM registro": None, "Montante em MI": 16.0,
                "Reserva": None, "Referência": None, "Nome do usuário": None,
            },
        ]
    )

    mb25 = pd.DataFrame(
        [
            {"Reserva": "R10", "Material": "2001", "Texto breve material": "Item A", "Depósito": "D009"},
            {"Reserva": "R10", "Material": "2002", "Texto breve material": "Item B", "Depósito": ""},
            {"Reserva": "R11", "Material": "2003", "Texto breve material": "Item C", "Depósito": "D016"},  # fora: Pendências é D009+vazio só
            {"Reserva": "R99", "Material": "2099", "Texto breve material": "Fora", "Depósito": "D028"},
            {"Reserva": None, "Material": None, "Texto breve material": None, "Depósito": None},
        ]
    )

    zmm028 = pd.DataFrame(
        [
            {"Material": "3001", "Denom.": "A", "Unidade": "UN", "Centro": "2003", "Util.livre": 10,
             "Val.total": 100.0, "Pos.dpst.": "A-01", "Tp.MRP": "VB", "Depósito": "D009",
             "Estq.máx.": 50, "Pt.reabast": 10},
            {"Material": "3002", "Denom.": "B", "Unidade": "UN", "Centro": "2003", "Util.livre": 0,
             "Val.total": 0.0, "Pos.dpst.": "", "Tp.MRP": "VB", "Depósito": "D009",
             "Estq.máx.": 50, "Pt.reabast": 10},
            {"Material": "3003", "Denom.": "C", "Unidade": "UN", "Centro": "2003", "Util.livre": 5,
             "Val.total": 250.5, "Pos.dpst.": "", "Tp.MRP": "PD", "Depósito": "D009",
             "Estq.máx.": 50, "Pt.reabast": 10},
        ]
    )

    _escrever(tmp_path / config.MB51_FILENAME, mb51)
    _escrever(tmp_path / config.MB25_FILENAME, mb25)
    _escrever(tmp_path / config.ZMM028_FILENAME, zmm028)

    df_mb51 = extratos.carregar_mb51(str(tmp_path / config.MB51_FILENAME))
    df_mb25 = extratos.carregar_mb25(str(tmp_path / config.MB25_FILENAME))
    df_zmm028 = extratos.carregar_zmm028(str(tmp_path / config.ZMM028_FILENAME))

    # rodapé e depósito D014/D028 devem ter sumido
    assert len(df_mb51) == 3
    # MB25: R11 (D016) também sai — Pendências é D009+vazio só, sem D016
    assert len(df_mb25) == 2

    assert indicadores.linhas_atendidas(df_mb51, "D009", HOJE) == 1  # só 201 (101 é Recebimento, não Atendimento)
    assert indicadores.linhas_atendidas(df_mb51, "D016", HOJE) == 1  # 261
    assert indicadores.recebimentos(df_mb51, "D009", HOJE) == 1  # 101 (vazio -> D009), dedup por Referência NF-2
    assert indicadores.pendencias_atendimento_linhas(df_mb25) == 2
    assert indicadores.reservas_pendentes(df_mb25) == 1  # só R10 (R11 era D016, excluído)
    assert indicadores.itens_estoque_com_saldo(df_zmm028) == 2
    assert indicadores.valor_estoque_total(df_zmm028) == 350.5
    assert indicadores.itens_mrp_saldo_zero(df_zmm028) == 1  # só 3002 (VB e saldo 0)
    assert indicadores.itens_sem_endereco(df_zmm028) == 1  # só 3003 (saldo != 0 e Pos.dpst. vazia)
