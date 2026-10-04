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


def test_atendimento_em_5_grupos_por_tipo_de_movimento(tmp_path):
    """Reservas 201, Ordens 261, Intercompany 601, Transferências 833, Diversos = o resto
    (decisão 2026-09-27). Ordem/Centro custo NÃO decidem mais o grupo."""
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("1001", "D009", 201, "01.04.2026", "NF-A", ordem="4001", centro_custo=None),
            _linha("1002", "D009", 201, "02.04.2026", "NF-B", ordem=None, centro_custo="2003CSC"),
            _linha("1003", "D009", 261, "03.04.2026", "NF-C", ordem="4002", centro_custo="2003SEG"),
            _linha("1004", "D009", 601, "04.04.2026", "NF-D"),
            _linha("1005", "D009", 601, "04.04.2026", "NF-D"),
            _linha("1006", "D009", 833, "05.04.2026", "NF-E"),
            _linha("1007", "D009", 122, "06.04.2026", "NF-F"),
            _linha("1008", "D009", 921, "06.04.2026", "NF-G", ordem="5001"),
        ],
    )
    mes = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )["2026-04"]
    assert (mes["reservas_mes"], mes["ordens_mes"], mes["intercompany_mes"],
            mes["transferencias_mes"], mes["diversos_mes"]) == (2, 1, 2, 1, 2)
    assert "outros_mes" not in mes


def test_os_5_grupos_somam_linhas_atendidas_e_estorno_nao_desconta(tmp_path):
    """Atendimento estornado continua atendimento (o 602 só aparece no card de Estorno)."""
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha("2001", "D009", 601, "01.04.2026", "NF-X"),
            _linha("2001", "D009", 602, "01.04.2026", "NF-X"),
            _linha("2002", "D009", 221, "02.04.2026", "NF-Y"),
        ],
    )
    mes = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=bases_dir
    )["2026-04"]
    soma = sum(mes[k] for k in ("reservas_mes", "ordens_mes", "intercompany_mes", "transferencias_mes", "diversos_mes"))
    assert soma == mes["linhas_atendidas_mes"] == 2
    assert mes["intercompany_mes"] == 1 and mes["diversos_mes"] == 1
    assert mes["estornos_qtd_mes"] == 1


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


def test_102_e_estorno_com_valor_absoluto_e_nota_estornada_continua_recebida(tmp_path):
    """55216-1: 101 e 102 de 16 un no mesmo mês -> continua nota recebida (contagem bruta,
    Fernando 2026-10-03); o 102 entra em Estornos com valor em módulo (Fernando 2026-09-28)."""
    linhas = [
        _linha("552558", "D009", 101, "04.09.2026", "55216-1", valor=26837.78),
        _linha("552558", "D009", 102, "04.09.2026", "55216-1", valor=-26837.78),
        _linha("7001", "D009", 101, "05.09.2026", "NF-P", valor=100.0),
        _linha("7001", "D009", 102, "05.09.2026", "NF-P", valor=-40.0),
        _linha("7002", "D009", 202, "05.09.2026", "R", valor=10.0),
    ]
    linhas[0]["Qtd.  UM registro"], linhas[1]["Qtd.  UM registro"] = 16, -16
    linhas[2]["Qtd.  UM registro"], linhas[3]["Qtd.  UM registro"] = 10, -4
    bases_dir = _preparar_mb51(tmp_path, linhas)
    mes = historico_mensal.calcular_historico_mensal(datetime.date(2026, 9, 1), datetime.date(2026, 9, 30), bases_dir=bases_dir)["2026-09"]
    assert mes["notas_recebidas_mes"] == 2  # 55216-1 (estornada por inteiro) e NF-P (parcial)
    assert mes["estornos_qtd_mes"] == 3
    assert mes["estornos_valor_mes"] == 26837.78 + 40.0 + 10.0


# ---- Comparativo Mensal: mesmos números do Resumo, separados por depósito ----

def _mes_misto(tmp_path):
    linhas = [
        _linha("1001", "D009", 201, "01.04.2026", "R1", valor=-10.0),
        _linha("1002", "D009", 261, "01.04.2026", "R2", valor=-5.0),
        _linha("1003", "D009", 101, "02.04.2026", "NF-1", valor=100.0),
        _linha("1004", "D009", 202, "03.04.2026", "E1", valor=4.0),
        _linha("2001", "D016", 201, "02.04.2026", "R3", valor=-7.0),
        _linha("2002", "D016", 101, "02.04.2026", "NF-2", valor=50.0),
        _linha("2002", "D016", 101, "03.04.2026", "NF-2", valor=25.0),  # mesma nota em 2 dias
    ]
    return historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), bases_dir=_preparar_mb51(tmp_path, linhas)
    )["2026-04"]


def test_comparativo_d009_bate_com_as_chaves_do_resumo_do_mes(tmp_path):
    mes = _mes_misto(tmp_path)
    d009 = mes["comparativo"]["D009"]
    assert d009["linhas_atendidas"] == mes["linhas_atendidas_mes"] == 2
    assert d009["notas_recebidas"] == mes["notas_recebidas_mes"] == 1
    assert d009["estornos_qtd"] == mes["estornos_qtd_mes"] == 1
    assert d009["inventario_rotativo"] == mes["inventario_rotativo_mes"] == 4
    assert d009["valor_atendido"] == abs(mes["valor_atendido_mes"]) == 15.0
    assert d009["valor_estornado"] == mes["estornos_valor_mes"] == 4.0
    assert d009["valor_recebido"] == mes["valor_recebido_mes"] == 100.0


def test_comparativo_d016_separado_e_diario_por_dia_corrido(tmp_path):
    d016 = _mes_misto(tmp_path)["comparativo"]["D016"]
    assert (d016["linhas_atendidas"], d016["notas_recebidas"], d016["valor_atendido"], d016["valor_recebido"]) == (1, 1, 7.0, 75.0)
    assert d016["inventario_rotativo"] == 3  # dia 2: 2001 e 2002; dia 3: 2002 de novo
    diario = d016["diario"]
    assert all(len(serie) == 30 for serie in diario.values())  # abril inteiro, fim de semana incluso
    assert diario["notas_recebidas"][:4] == [0, 1, 1, 0]  # dedup por dia: soma 2, total do mês 1
    assert diario["valor_recebido"][:4] == [0.0, 50.0, 25.0, 0.0]
    assert diario["linhas_atendidas"][1] == 1


def test_comparativo_mes_parcial_vai_ate_data_fim(tmp_path):
    bases_dir = _preparar_mb51(tmp_path, [_linha("1001", "D009", 201, "10.09.2026", "A")])
    mes = historico_mensal.calcular_historico_mensal(
        datetime.date(2026, 9, 1), datetime.date(2026, 9, 10), bases_dir=bases_dir
    )["2026-09"]
    assert len(mes["comparativo"]["D009"]["diario"]["linhas_atendidas"]) == 10
    assert mes["comparativo"]["D016"]["linhas_atendidas"] == 0
