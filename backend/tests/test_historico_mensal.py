import datetime

import pandas as pd
import pytest

from backend import config, historico_mensal


def _linha(material, deposito, bwart, data, referencia, valor=10.0, ordem=None, centro_custo=None):
    return {
        "Material": material, "Texto breve material": "x", "Centro": "2003",
        "Depósito": deposito, "Tipo de movimento": bwart, "Data de lançamento": data,
        "Qtd.  UM registro": 1, "UM registro": "UN", "Montante em MI": valor,
        "Reserva": "R1", "Referência": referencia, "Nome do usuário": "fernando",
        "Ordem": ordem, "Centro custo": centro_custo,
    }


def _preparar_mb51(tmp_path, linhas):
    mb51 = pd.DataFrame(linhas)
    mb51.to_excel(tmp_path / config.MB51_FILENAME, index=False)
    return str(tmp_path)


def test_soma_valor_e_conta_linha_sem_dedup_no_bloco_atendimento(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 201, "01.04.2026", "NF-A", valor=10.0),
            _linha("1001", "D009", 201, "02.04.2026", "NF-A", valor=20.0),  # mesma Referência, NÃO dedup aqui
            _linha("1002", "D016", 201, "03.04.2026", "NF-B", valor=999.0),  # fora: só D009
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )
    mes = resultado["2026-04"]
    assert mes["linhas_atendidas_mes"] == 2
    assert mes["valor_atendido_mes"] == 30.0


def test_ordens_e_reservas_contam_presenca_independente(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 201, "01.04.2026", "NF-A", ordem="4001", centro_custo=None),
            _linha("1002", "D009", 201, "02.04.2026", "NF-B", ordem=None, centro_custo="2003CSC"),
            _linha("1003", "D009", 201, "03.04.2026", "NF-C", ordem="4002", centro_custo="2003SEG"),
            _linha("1004", "D009", 201, "04.04.2026", "NF-D", ordem=None, centro_custo=None),
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )
    mes = resultado["2026-04"]
    assert mes["ordens_mes"] == 2
    assert mes["reservas_mes"] == 2


def test_top5_centro_custo_ordenado_do_maior_pro_menor_sem_outros(tmp_path):
    linhas = []
    contagens = {"2003CSC": 3, "2003SEG": 2, "2003PRD": 1}
    dia = 1
    for centro, n in contagens.items():
        for _ in range(n):
            linhas.append(_linha(f"10{dia:02d}", "D009", 201, f"{dia:02d}.04.2026", f"NF-{dia}", centro_custo=centro))
            dia += 1
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30),
        bases_dir=_preparar_mb51(tmp_path, linhas),
    )
    top5 = resultado["2026-04"]["top5_centro_custo"]
    assert top5[0] == {"centro_custo": "2003CSC", "qtd": 3}
    assert top5[1] == {"centro_custo": "2003SEG", "qtd": 2}
    assert top5[2] == {"centro_custo": "2003PRD", "qtd": 1}
    assert len(top5) == 3  # sem "Outros" nem preenchimento artificial


def test_notas_recebidas_dedup_mensal_mas_valor_nao_dedup(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 101, "01.04.2026", "NF-100", valor=10.0),
            _linha("1002", "D009", 101, "01.04.2026", "NF-100", valor=15.0),  # mesma nota, 2ª linha
            _linha("1003", "D009", 835, "15.04.2026", "NF-200", valor=5.0),   # 835 também conta (confirmado)
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )
    mes = resultado["2026-04"]
    assert mes["notas_recebidas_mes"] == 2  # NF-100 (1 nota, 2 linhas) + NF-200
    assert mes["valor_recebido_mes"] == 30.0  # soma das 3 linhas, sem dedup


def test_inventario_rotativo_mes_soma_contagem_diaria(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 311, "01.04.2026", "A"),
            _linha("1002", "D009", 311, "01.04.2026", "B"),  # dia 1: 2 materiais distintos
            _linha("1001", "D009", 701, "02.04.2026", "C"),  # dia 2: mesmo material 1001 de novo -> conta separado
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )
    assert resultado["2026-04"]["inventario_rotativo_mes"] == 3  # 2 (dia1) + 1 (dia2), não dedup no mês


def test_estorno_conta_linha_e_soma_valor(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 202, "01.04.2026", "A", valor=8.0),
            _linha("1002", "D009", 602, "02.04.2026", "B", valor=2.0),
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )
    mes = resultado["2026-04"]
    assert mes["estornos_qtd_mes"] == 2
    assert mes["estornos_valor_mes"] == 10.0


def test_meses_sem_data_fim_usa_mais_recente_disponivel(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 201, "15.04.2026", "A"),
            _linha("1002", "D009", 201, "10.05.2026", "B"),
        ],
    )
    resultado = historico_mensal.calcular_historico_mensal(datetime.date(2026, 4, 1), bases_dir=bases_dir)
    assert set(resultado.keys()) == {"2026-04", "2026-05"}


def test_data_fim_antes_de_data_inicio_lanca_erro(tmp_path):
    bases_dir = _preparar_mb51(tmp_path, [_linha("1001", "D009", 201, "01.04.2026", "A")])
    with pytest.raises(ValueError):
        historico_mensal.calcular_historico_mensal(
            datetime.date(2026, 5, 1), datetime.date(2026, 4, 1), bases_dir=bases_dir
        )
