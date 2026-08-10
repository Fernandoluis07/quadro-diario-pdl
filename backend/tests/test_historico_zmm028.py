import pandas as pd
import pytest

from backend import historico_zmm028


def _linha(data, estoque=0, mrp_zero=0, valor=0.0):
    return {
        "Data": data,
        "Itens em Estoque com Saldo": estoque,
        "Itens MRP Saldo Zero (VB)": mrp_zero,
        "Valor do Estoque Total (R$)": valor,
    }


def _escrever_planilha(tmp_path, linhas):
    caminho = tmp_path / "zmm028.xlsx"
    pd.DataFrame(linhas).to_excel(caminho, index=False)
    return str(caminho)


def test_importa_3_colunas_e_fixa_itens_sem_endereco_em_zero(tmp_path):
    caminho = _escrever_planilha(
        tmp_path,
        [_linha("08/08/2026", estoque=5335, mrp_zero=174, valor=28885676.47)],
    )
    resultado = historico_zmm028.importar_historico_zmm028(caminho)
    assert resultado["2026-08-08"] == {
        "itens_estoque_com_saldo": 5335,
        "itens_mrp_saldo_zero": 174,
        "valor_estoque_total": 28885676.47,
        "itens_sem_endereco": 0,
    }


def test_um_registro_por_dia_para_varios_dias(tmp_path):
    caminho = _escrever_planilha(
        tmp_path,
        [_linha("01/04/2026", estoque=5328), _linha("02/04/2026", estoque=5343)],
    )
    resultado = historico_zmm028.importar_historico_zmm028(caminho)
    assert set(resultado.keys()) == {"2026-04-01", "2026-04-02"}
    assert resultado["2026-04-01"]["itens_sem_endereco"] == 0
    assert resultado["2026-04-02"]["itens_sem_endereco"] == 0


def test_coluna_esperada_ausente_lanca_erro(tmp_path):
    caminho = tmp_path / "zmm028.xlsx"
    pd.DataFrame([{"Data": "01/04/2026", "Itens em Estoque com Saldo": 1}]).to_excel(caminho, index=False)
    with pytest.raises(ValueError, match="Colunas esperadas ausentes"):
        historico_zmm028.importar_historico_zmm028(str(caminho))


def test_data_duplicada_lanca_erro(tmp_path):
    caminho = _escrever_planilha(tmp_path, [_linha("01/04/2026"), _linha("01/04/2026")])
    with pytest.raises(ValueError, match="Datas duplicadas"):
        historico_zmm028.importar_historico_zmm028(caminho)
