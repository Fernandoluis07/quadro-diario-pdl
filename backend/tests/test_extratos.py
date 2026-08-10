import numpy as np
import pandas as pd

from backend import extratos


def test_normalizar_deposito_vazio_conta_como_d009():
    assert extratos.normalizar_deposito(np.nan) == "D009"
    assert extratos.normalizar_deposito("") == "D009"
    assert extratos.normalizar_deposito("   ") == "D009"
    assert extratos.normalizar_deposito("D016") == "D016"
    assert extratos.normalizar_deposito("D014") == "D014"


def test_normalizar_bwart_variacoes_de_formato():
    assert extratos.normalizar_bwart(101) == "101"
    assert extratos.normalizar_bwart(101.0) == "101"
    assert extratos.normalizar_bwart(" 101 ") == "101"
    assert extratos.normalizar_bwart(1) == "001"
    assert extratos.normalizar_bwart(np.nan) == ""


def test_descartar_linhas_rodape_remove_linhas_sem_material():
    df = pd.DataFrame(
        {
            "Material": ["1001", "1002", np.nan, ""],
            "Depósito": ["D009", "D009", "D009", "D009"],
        }
    )
    limpo = extratos._descartar_linhas_rodape(df)
    assert len(limpo) == 2
    assert set(limpo["Material"]) == {"1001", "1002"}


def test_filtrar_deposito_valido_mantem_d009_d016_e_vazio_descarta_outros():
    df = pd.DataFrame(
        {
            "Depósito": ["D009", "D016", np.nan, "D014", "D028", ""],
        }
    )
    filtrado = extratos._filtrar_deposito_valido(df)
    assert len(filtrado) == 4


def test_filtrar_deposito_d009_vazio_exclui_d016_mb25():
    """Pendências (MB25) segue a mesma regra dos 4 indicadores separados por
    depósito: só D009+vazio. D016 é excluído, ao contrário do filtro geral."""
    df = pd.DataFrame(
        {
            "Depósito": ["D009", "D016", np.nan, "D014", "D028", ""],
        }
    )
    filtrado = extratos._filtrar_deposito_d009_vazio(df)
    assert len(filtrado) == 3
    assert set(filtrado["_deposito_norm"]) == {"D009"}
