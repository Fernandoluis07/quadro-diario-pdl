"""Testa a detecção automática de 'hoje'/'ontem' a partir da própria MB51,
sem depender do relógio do computador (a extração é feita de manhã e só
reflete até o dia anterior)."""

import datetime

import pandas as pd

from backend import config, main

DIA1 = "01.08.2026"  # mais antigo
DIA2 = "04.08.2026"  # "ontem" esperado
DIA3 = "05.08.2026"  # "hoje" esperado (mais recente do arquivo)


def _linha_mb51(material, deposito, bwart, data, referencia):
    return {
        "Material": material, "Texto breve material": "x", "Centro": "2003",
        "Depósito": deposito, "Tipo de movimento": bwart, "Data de lançamento": data,
        "Qtd. UM registro": 1, "UM registro": "UN", "Montante em MI": 1.0,
        "Reserva": "R1", "Referência": referencia, "Nome do usuário": "fernando",
    }


def _preparar_bases(tmp_path):
    mb51 = pd.DataFrame(
        [
            _linha_mb51("1001", "D009", 201, DIA1, "NF-A"),  # dia mais antigo
            _linha_mb51("1002", "D009", 201, DIA2, "NF-B"),  # "ontem"
            _linha_mb51("1003", "D009", 201, DIA2, "NF-C"),  # "ontem" (2 linhas)
            _linha_mb51("1004", "D009", 201, DIA3, "NF-D"),  # "hoje"
        ]
    )
    mb25 = pd.DataFrame(
        [{"Reserva": "R1", "Material": "2001", "Texto breve material": "x", "Depósito": "D009",
          "Qtd.necessária": None, "Data da necessidade": None, "Centro custo": None, "Ordem": None}]
    )
    zmm028 = pd.DataFrame(
        [{"Material": "3001", "Denom.": "x", "Unidade": "UN", "Centro": "2003", "Util.livre": 1,
          "Val.total": 10.0, "Pos.dpst.": "A-01", "Tp.MRP": "VB", "Depósito": "D009",
          "Estq.máx.": 1, "Pt.reabast": 1}]
    )
    mb51.to_excel(tmp_path / config.MB51_FILENAME, index=False)
    mb25.to_excel(tmp_path / config.MB25_FILENAME, index=False)
    zmm028.to_excel(tmp_path / config.ZMM028_FILENAME, index=False)
    return str(tmp_path)


def test_detecta_hoje_como_data_mais_recente_do_arquivo_sem_usar_relogio(tmp_path):
    bases_dir = _preparar_bases(tmp_path)
    resultado = main.calcular_todos_indicadores(bases_dir=bases_dir)
    assert resultado["data_referencia"] == "2026-08-05"
    assert resultado["linhas_atendidas_d009"] == 1  # só a linha do dia 3
    assert resultado["checklist_reservas"] == [
        {
            "numero_reserva": "R1", "material": "2001", "descricao": "x", "data_necessidade": "",
            "qtd_necessaria": 0.0, "centro_custo": "", "ordem": "", "saldo_atual": 0.0, "endereco": "",
        }
    ]


def test_detecta_ontem_como_segunda_data_mais_recente(tmp_path):
    bases_dir = _preparar_bases(tmp_path)
    resultado = main.calcular_todos_indicadores(bases_dir=bases_dir)
    assert resultado["data_referencia_ontem"] == "2026-08-04"
    assert resultado["ontem"]["linhas_atendidas_d009"] == 2  # as 2 linhas do dia 2


def test_ontem_traz_os_mesmos_8_indicadores_do_bloco1():
    from backend.main import _CHAVES_BLOCO1
    assert len(_CHAVES_BLOCO1) == 8


def test_parametro_data_forca_hoje_manualmente_e_ontem_vira_a_data_anterior_no_arquivo(tmp_path):
    bases_dir = _preparar_bases(tmp_path)
    resultado = main.calcular_todos_indicadores(bases_dir=bases_dir, data_ref=datetime.date(2026, 8, 4))
    assert resultado["data_referencia"] == "2026-08-04"
    assert resultado["data_referencia_ontem"] == "2026-08-01"
    assert resultado["ontem"]["linhas_atendidas_d009"] == 1  # a linha do dia 1


def test_sem_segunda_data_no_arquivo_ontem_fica_none(tmp_path):
    mb51 = pd.DataFrame([_linha_mb51("1001", "D009", 201, DIA3, "NF-D")])
    mb25 = pd.DataFrame(
        [{"Reserva": "R1", "Material": "2001", "Texto breve material": "x", "Depósito": "D009",
          "Qtd.necessária": None, "Data da necessidade": None, "Centro custo": None, "Ordem": None}]
    )
    zmm028 = pd.DataFrame(
        [{"Material": "3001", "Denom.": "x", "Unidade": "UN", "Centro": "2003", "Util.livre": 1,
          "Val.total": 10.0, "Pos.dpst.": "A-01", "Tp.MRP": "VB", "Depósito": "D009",
          "Estq.máx.": 1, "Pt.reabast": 1}]
    )
    mb51.to_excel(tmp_path / config.MB51_FILENAME, index=False)
    mb25.to_excel(tmp_path / config.MB25_FILENAME, index=False)
    zmm028.to_excel(tmp_path / config.ZMM028_FILENAME, index=False)

    resultado = main.calcular_todos_indicadores(bases_dir=str(tmp_path))
    assert resultado["data_referencia"] == "2026-08-05"
    assert resultado["data_referencia_ontem"] is None
    assert resultado["ontem"] is None
