import pandas as pd
import pytest

from backend import historico_manuais


def _escrever_planilha(tmp_path, linhas):
    caminho = tmp_path / "manuais.xlsx"
    pd.DataFrame(linhas).to_excel(caminho, index=False)
    return str(caminho)


def _linha(data, notas=0, devolucao=0, scanner=0, nf=0, reservas=0, pendencias=0):
    return {
        "Data": data,
        "Notas Aguardando Lancamento": notas,
        "Devolucao": devolucao,
        "Scanner Documentos": scanner,
        "NF Pendente Faturamento": nf,
        "Reservas Pendentes": reservas,
        "Pendencias Atendimento Linhas": pendencias,
    }


def test_importa_um_registro_por_dia_com_as_6_chaves(tmp_path):
    caminho = _escrever_planilha(
        tmp_path,
        [
            _linha("01/04/2026", notas=30, reservas=17, pendencias=29),
            _linha("02/04/2026", devolucao=1, scanner=2, nf=3),
        ],
    )
    resultado = historico_manuais.importar_historico_manuais(caminho)
    assert set(resultado.keys()) == {"2026-04-01", "2026-04-02"}
    assert resultado["2026-04-01"] == {
        "notas_aguardando_lancamento": 30, "devolucao": 0, "scanner_documentos": 0,
        "nf_pendente_faturamento": 0, "reservas_pendentes": 17, "pendencias_atendimento_linhas": 29,
    }
    assert resultado["2026-04-02"]["devolucao"] == 1
    assert resultado["2026-04-02"]["scanner_documentos"] == 2
    assert resultado["2026-04-02"]["nf_pendente_faturamento"] == 3


def test_coluna_esperada_ausente_lanca_erro(tmp_path):
    caminho = tmp_path / "manuais.xlsx"
    pd.DataFrame([{"Data": "01/04/2026", "Devolucao": 1}]).to_excel(caminho, index=False)
    with pytest.raises(ValueError, match="Colunas esperadas ausentes"):
        historico_manuais.importar_historico_manuais(str(caminho))


def test_data_duplicada_lanca_erro(tmp_path):
    caminho = _escrever_planilha(tmp_path, [_linha("01/04/2026"), _linha("01/04/2026")])
    with pytest.raises(ValueError, match="Datas duplicadas"):
        historico_manuais.importar_historico_manuais(caminho)


def test_data_invalida_lanca_erro(tmp_path):
    caminho = _escrever_planilha(tmp_path, [_linha("não é uma data")])
    with pytest.raises(ValueError, match="Datas inválidas"):
        historico_manuais.importar_historico_manuais(caminho)
