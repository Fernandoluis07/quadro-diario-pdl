import datetime

import pandas as pd
import pytest

from backend import config, historico


def _linha_mb51(material, deposito, bwart, data, referencia):
    return {
        "Material": material, "Texto breve material": "x", "Centro": "2003",
        "Depósito": deposito, "Tipo de movimento": bwart, "Data de lançamento": data,
        "Qtd. UM registro": 1, "UM registro": "UN", "Montante em MI": 1.0,
        "Reserva": "R1", "Referência": referencia, "Nome do usuário": "fernando",
    }


def _preparar_mb51(tmp_path, linhas):
    mb51 = pd.DataFrame(linhas)
    mb51.to_excel(tmp_path / config.MB51_FILENAME, index=False)
    return str(tmp_path)


def test_gera_um_dia_por_data_no_intervalo_incluindo_dias_sem_movimento(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha_mb51("1001", "D009", 201, "01.04.2026", "NF-A"),
            _linha_mb51("1002", "D009", 601, "03.04.2026", "NF-B"),
        ],
    )
    resultado = historico.calcular_historico_mb51(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 3), bases_dir=bases_dir
    )
    # 3 dias no intervalo (01, 02, 03), mesmo o 02 sem nenhuma movimentação
    assert set(resultado.keys()) == {"2026-04-01", "2026-04-02", "2026-04-03"}
    assert resultado["2026-04-01"]["linhas_atendidas_d009"] == 1
    assert resultado["2026-04-02"]["linhas_atendidas_d009"] == 0
    assert resultado["2026-04-03"]["intercompany"] == 1  # NF-B, BWART 601


def test_cada_dia_tem_os_9_indicadores(tmp_path):
    bases_dir = _preparar_mb51(tmp_path, [_linha_mb51("1001", "D009", 201, "01.04.2026", "NF-A")])
    resultado = historico.calcular_historico_mb51(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 1), bases_dir=bases_dir
    )
    chaves_esperadas = {
        "linhas_atendidas_d009", "linhas_atendidas_d016",
        "estornos_d009", "estornos_d016",
        "recebimentos_d009", "recebimentos_d016",
        "inventario_rotativo_d009", "inventario_rotativo_d016",
        "intercompany",
    }
    assert set(resultado["2026-04-01"].keys()) == chaves_esperadas


def test_sem_data_fim_usa_a_data_mais_recente_disponivel_na_mb51(tmp_path):
    bases_dir = _preparar_mb51(
        tmp_path,
        [
            _linha_mb51("1001", "D009", 201, "01.04.2026", "NF-A"),
            _linha_mb51("1002", "D009", 201, "05.04.2026", "NF-B"),  # mais recente do arquivo
        ],
    )
    resultado = historico.calcular_historico_mb51(datetime.date(2026, 4, 1), bases_dir=bases_dir)
    assert max(resultado.keys()) == "2026-04-05"


def test_data_fim_antes_de_data_inicio_lanca_erro(tmp_path):
    bases_dir = _preparar_mb51(tmp_path, [_linha_mb51("1001", "D009", 201, "01.04.2026", "NF-A")])
    with pytest.raises(ValueError):
        historico.calcular_historico_mb51(
            datetime.date(2026, 4, 5), datetime.date(2026, 4, 1), bases_dir=bases_dir
        )


def test_arquivo_mb51_aceita_caminho_direto_e_ignora_bases_dir(tmp_path):
    """Máquina sem acesso à rede da empresa: aponta --arquivo-mb51 pra uma
    cópia local, em vez de bases_dir/config.MB51_FILENAME."""
    caminho_arquivo = tmp_path / "qualquer_nome.xlsx"
    pd.DataFrame([_linha_mb51("1001", "D009", 201, "01.04.2026", "NF-A")]).to_excel(caminho_arquivo, index=False)

    resultado = historico.calcular_historico_mb51(
        datetime.date(2026, 4, 1), datetime.date(2026, 4, 1),
        bases_dir="\\\\caminho\\de\\rede\\que\\nao\\existe",  # não deve ser usado
        arquivo_mb51=str(caminho_arquivo),
    )
    assert resultado["2026-04-01"]["linhas_atendidas_d009"] == 1
