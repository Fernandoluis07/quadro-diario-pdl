import datetime
import json

import pandas as pd
import pytest

from backend import reconstruir

D = datetime.date


def _mb51(linhas):
    return pd.DataFrame(linhas, columns=["Material", "_deposito_norm", "_data_norm", "Qtd.  UM registro", "Montante em MI"])


def _zmm(linhas):
    return pd.DataFrame(linhas, columns=["Material", "Util.livre", "Val.total", "Tp.MRP", "Pos.dpst."])


def test_desfaz_so_movimentos_posteriores_ao_dia_e_ate_o_snapshot():
    z = _zmm([["1001", 10, 100.0, "VB", "A1"], ["1002", 0, 0.0, "VB", "A2"]])
    mb = _mb51([
        ["1001", "D009", D(2026, 9, 5), -4, -40.0],   # saída depois do dia: desfazer -> +4
        ["1001", "D009", D(2026, 9, 3), -1, -10.0],   # antes/no dia: mantém
        ["1002", "D009", D(2026, 9, 6), 3, 30.0],     # entrada depois do dia: desfazer -> -3
        ["1001", "D016", D(2026, 9, 5), -9, -90.0],   # outro depósito: ignora
        ["1001", "D009", D(2026, 9, 19), -7, -70.0],  # depois do snapshot: nunca fez parte do saldo
    ])
    r = reconstruir.zmm028_no_fim_do_dia(z, mb, D(2026, 9, 4), D(2026, 9, 18))
    assert r.loc[0, "Util.livre"] == 14 and r.loc[0, "Val.total"] == 140.0
    assert r.loc[1, "Util.livre"] == -3
    assert z.loc[0, "Util.livre"] == 10   # não muta o original


def test_recusa_reconstruir_dia_posterior_ao_snapshot():
    with pytest.raises(ValueError):
        reconstruir.zmm028_no_fim_do_dia(_zmm([]), _mb51([]), D(2026, 9, 19), D(2026, 9, 18))


def test_no_proprio_dia_do_snapshot_devolve_o_saldo_intacto():
    z = _zmm([["1001", 10, 100.0, "VB", "A1"]])
    mb = _mb51([["1001", "D009", D(2026, 9, 18), -4, -40.0]])
    assert reconstruir.zmm028_no_fim_do_dia(z, mb, D(2026, 9, 18), D(2026, 9, 18)).loc[0, "Util.livre"] == 10


INDEX = 'x\nconst HISTORICO_MB51 = {"2026-09-03":{"a":1}};\nconst HISTORICO_ZMM028 = {"2026-09-03":{"b":2}};\ny\n'


def _repo(tmp_path):
    (tmp_path / "historico_mb51.json").write_text(json.dumps({"2026-09-03": {"a": 1}}))
    (tmp_path / "historico_zmm028.json").write_text(json.dumps({"2026-09-03": {"b": 2}}))
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    return str(tmp_path), str(tmp_path / "index.html")


def test_gravar_dia_escreve_json_index_e_registro_de_proveniencia(tmp_path):
    repo, index = _repo(tmp_path)
    dias = {"2026-09-04": {"mb51": {"a": 9}, "zmm028": {"b": 8}}}
    reconstruir.gravar_dia(repo, index, dias, D(2026, 9, 17), datetime.datetime(2026, 9, 18, 14, 0))

    assert json.loads((tmp_path / "historico_mb51.json").read_text())["2026-09-04"] == {"a": 9}
    assert json.loads((tmp_path / "historico_zmm028.json").read_text())["2026-09-04"] == {"b": 8}
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '"2026-09-04":{"a":9}' in html and '"2026-09-04":{"b":8}' in html
    reg = json.loads((tmp_path / "dias_reconstruidos.json").read_text())
    assert reg["2026-09-04"]["snapshot"] == "2026-09-17" and "historico_paineis" in reg["2026-09-04"]["sem_fonte_retroativa"]


def test_gravar_dia_recusa_sobrescrever_dia_ja_congelado_e_nao_escreve_nada(tmp_path):
    repo, index = _repo(tmp_path)
    antes = (tmp_path / "index.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="já congelado"):
        reconstruir.gravar_dia(repo, index, {"2026-09-03": {"mb51": {}, "zmm028": {}}}, D(2026, 9, 17), datetime.datetime.now())
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == antes
    assert not (tmp_path / "dias_reconstruidos.json").exists()
