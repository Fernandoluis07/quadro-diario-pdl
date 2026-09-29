"""Regras da Checklist de Bipagem (Fase 2) sobre dados sintéticos — ver backend/checklist_bipagem.py."""

import datetime

import pandas as pd

from backend import checklist_bipagem as C
from backend import config

D = datetime.date
AGORA = datetime.datetime(2026, 9, 28, 9, 0)

# matrícula -> (exibição, nome no SharePoint); 9999 é de fora do time (sem col C)
CAD = {"4058": ("Fernando Luis", "FERNANDO SOUSA"), "1868": ("Luan Okada", "LUAN ARAUJO"),
       "4873": ("Geovane Abreu", "GEOVANE ABREU"), "9999": ("Rogerio", "")}


def _mb51(linhas):
    """linhas: (data, material, bwart, qtd, usuário)"""
    return pd.DataFrame([{
        "Material": m, "Texto breve material": f"MAT {m}", "UM registro": "UN", "Qtd.  UM registro": q,
        "Nome do usuário": u, "_bwart_norm": b, "_data_norm": d, "_deposito_norm": "D009",
    } for d, m, b, q, u in linhas])


def _sp(linhas):
    """linhas: (datahora, material, operador, endereço, qtd)"""
    df = pd.DataFrame([{"DtHr": dt, "COD": m, "OPERADOR": op, "END": e, "QTD": q} for dt, m, op, e, q in linhas],
                      columns=["DtHr", "COD", "OPERADOR", "END", "QTD"])
    df.to_excel  # noqa: B018 — só pra deixar claro que é o mesmo formato da planilha
    df = df.copy()
    df["_dthr"] = pd.to_datetime(df["DtHr"])
    df["_dia"] = df["_dthr"].dt.date
    df["_mat"] = df["COD"].map(C._cod)
    df["_op"] = df["OPERADOR"].map(C._nome)
    df["_end"] = df["END"].map(C._end)
    df["_qtd"] = pd.to_numeric(df["QTD"], errors="coerce")
    return df.sort_values("_dthr")


def _zmm(linhas):
    """linhas: (material, util.livre, endereço)"""
    return pd.DataFrame([{"Material": m, "Util.livre": q, "Pos.dpst.": e} for m, q, e in linhas])


def _auditar(mb, sp, zmm, ultimo="2026-09-24", extracao=D(2026, 9, 28)):
    estado = {"ultimo_dia_auditado": ultimo, "divergencias": []}
    return C.auditar(estado, mb, zmm, sp, CAD, extracao, AGORA)


def _por_id(estado):
    return {d["id"]: d for d in estado["divergencias"]}


def test_nao_bipado_exige_bipagem_do_proprio_operador():
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058")])
    sp = _sp([("2026-09-25 10:00", "100", "Luan araujo", "0200100101", 9)])  # outro operador bipou
    estado, res = _auditar(mb, sp, _zmm([("100", 9, "0200100101")]))
    d = _por_id(estado)["2026-09-25|100|4058"]
    assert d["categoria"] == "nao-bipado" and d["responsavel"] == "Fernando Luis" and d["saldo_sistema"] == 9


def test_recebimento_e_externo_qualquer_bipagem_cobre():
    mb = _mb51([(D(2026, 9, 25), "100", "101", 5, "RFCUSER"), (D(2026, 9, 25), "200", "201", -1, "9999")])
    sp = _sp([("2026-09-25 10:00", "100", "Luan araujo", "0200100101", 5),
              ("2026-09-25 11:00", "200", "Geovane Abreu", "0200200101", 3)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 5, "0200100101"), ("200", 3, "0200200101")]))
    assert estado["divergencias"] == []


def test_endereco_usa_a_bipagem_mais_recente_e_end_vazio_e_incorreto():
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058")])
    sp = _sp([("2026-09-25 09:00", "100", "Fernando Sousa", "0200100101", 4),
              ("2026-09-25 15:00", "100", "Fernando Sousa", None, 4)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 4, "200100101")]))  # zeros à esquerda não importam
    d = _por_id(estado)["2026-09-25|100|4058"]
    assert d["categoria"] == "endereco" and d["end_sistema"] == "200100101"


def test_zmm_sem_endereco_nao_tem_perdao_mas_vazio_com_vazio_e_ok():
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058"), (D(2026, 9, 25), "200", "201", -1, "4058")])
    sp = _sp([("2026-09-25 09:00", "100", "Fernando Sousa", "0300100101", 1),
              ("2026-09-25 09:05", "200", "Fernando Sousa", None, 1)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 1, None), ("200", 1, None)]))
    assert set(_por_id(estado)) == {"2026-09-25|100|4058"}


def test_saldo_e_o_fechamento_do_dia_desfazendo_os_dias_seguintes():
    """ZMM028 é de 28/09; no dia 26 saíram mais 3 — o saldo de 25/09 era 3 a mais."""
    mb = _mb51([(D(2026, 9, 25), "100", "201", -2, "4058"), (D(2026, 9, 26), "100", "201", -3, "1868")])
    sp = _sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 8),
              ("2026-09-26 10:00", "100", "Luan araujo", "0200100101", 5)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 5, "0200100101")]))
    assert estado["divergencias"] == []  # 25/09: 8 bate; 26/09: 5 bate


def test_contagem_so_vale_contra_o_saldo_de_fechamento():
    """Contou 142 às 14h; a 311 de -30 foi lançada depois — fechamento 112. A contagem física é
    a prova: 142 != 112 é divergência (regra "qualquer saldo do dia" rejeitada em 2026-09-28)."""
    mb = _mb51([(D(2026, 9, 25), "552670", "201", -2, "4873"), (D(2026, 9, 25), "552670", "311", -30, "4058")])
    sp = _sp([("2026-09-25 14:48", "552670", "Geovane Abreu", "200111101", 142),
              ("2026-09-25 17:00", "552670", "Fernando Sousa", "200111101", 110)])
    estado, _ = _auditar(mb, sp, _zmm([("552670", 112, "0200111101")]))
    (d,) = estado["divergencias"]
    assert d["categoria"] == "negativo" and d["saldo_sistema"] == 112 and d["saldo_contado"] == 110


def test_saldo_errado_vira_diferenca_com_sinal_e_contagem_de_terceiro_nao_vale():
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058")])
    sp = _sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 7),
              ("2026-09-25 11:00", "100", "Luan araujo", "0200100101", 9)])  # Luan acertou, mas não movimentou
    estado, _ = _auditar(mb, sp, _zmm([("100", 9, "0200100101")]))
    d = _por_id(estado)["2026-09-25|100|4058"]
    assert (d["categoria"], d["divergencia"], d["saldo_contado"]) == ("negativo", C.MENOS + "2", 7.0)


def test_recebimento_aceita_contagem_de_qualquer_pessoa_do_time_mas_nao_de_externo():
    mb = _mb51([(D(2026, 9, 25), "100", "101", 5, "RFCUSER")])
    sp_time = _sp([("2026-09-25 10:00", "100", "Geovane Abreu", "0200100101", 5)])
    assert _auditar(mb, sp_time, _zmm([("100", 5, "0200100101")]))[0]["divergencias"] == []
    sp_fora = _sp([("2026-09-25 10:00", "100", "Visitante", "0200100101", 5)])
    # bipagem de fora cobre a bipagem/endereço, mas não é contagem válida -> sem saldo pra comparar
    assert _auditar(mb, sp_fora, _zmm([("100", 5, "0200100101")]))[0]["divergencias"] == []


def test_endereco_e_saldo_do_mesmo_responsavel_viram_uma_linha_amarela():
    mb = _mb51([(D(2026, 9, 25), "100", "261", -1, "1868")])
    sp = _sp([("2026-09-25 18:20", "100", "Luan araujo", "0300414214", 0)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 82, "0200111101")]))
    (d,) = estado["divergencias"]
    assert d["categoria"] == "endereco-saldo" and d["divergencia"] == f"{C.MENOS}82 e endereço"


def test_so_audita_dias_fechados_a_partir_de_25_09():
    datas = [D(2026, 9, 24), D(2026, 9, 25), D(2026, 9, 26), D(2026, 9, 28)]
    assert C.dias_a_auditar("2026-09-20", datas, D(2026, 9, 28)) == [D(2026, 9, 25), D(2026, 9, 26), D(2026, 9, 27)]
    assert C.dias_a_auditar("2026-09-25", datas, D(2026, 9, 26)) == []  # 26 ainda em andamento na extração


def test_dia_sem_nenhuma_bipagem_e_nao_bipado_sem_trava():
    """Sábado 26/09: 3 movimentos e ZERO bipagens no SharePoint — é "Não bipado", sempre
    (Fernando 2026-09-28: não existe trava de "planilha desatualizada")."""
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058"), (D(2026, 9, 26), "200", "101", 2, "4895"),
                (D(2026, 9, 26), "300", "601", -5, "4895")])
    sp = _sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 5)])
    estado, res = _auditar(mb, sp, _zmm([("100", 5, "0200100101"), ("200", 2, "0200200101"), ("300", 0, "0200300101")]))
    assert res["dias_auditados"][-1] == D(2026, 9, 26) and estado["ultimo_dia_auditado"] == "2026-09-26"
    assert sorted((d["data"], d["codigo"], d["categoria"]) for d in estado["divergencias"]) == [
        ("26/09/2026", "200", "nao-bipado"), ("26/09/2026", "300", "nao-bipado")]


def test_reauditar_nao_duplica():
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058")])
    sp = _sp([("2026-09-25 10:00", "200", "Luan araujo", "0200100101", 1)])
    estado, _ = _auditar(mb, sp, _zmm([("100", 4, "0200100101")]))
    de_novo, res = C.auditar({**estado, "ultimo_dia_auditado": "2026-09-24"}, mb, _zmm([("100", 4, "0200100101")]), sp, CAD, D(2026, 9, 28), AGORA)
    assert len(de_novo["divergencias"]) == 1 and res["novas"] == []


# ---- Checklist 2.0 (reavaliação) ------------------------------------------------------

# bipagem de OUTRO material no dia: sem nenhuma bipagem no dia a Checklist para (base desatualizada)
_OUTRO = ("2026-09-25 07:00", "999", "Luan araujo", "0100000001", 1)


def _uma_divergencia(sp_original, zmm):
    mb = _mb51([(D(2026, 9, 25), "100", "201", -1, "4058")])
    sp = _sp([_OUTRO] + [tuple(r) for r in sp_original[["DtHr", "COD", "OPERADOR", "END", "QTD"]].itertuples(index=False)])
    estado, _ = _auditar(mb, sp, zmm)
    assert len(estado["divergencias"]) == 1
    return estado


def test_2_0_remove_nao_bipado_corrigido_na_data_original():
    estado = _uma_divergencia(_sp([]), _zmm([("100", 4, "0200100101")]))
    corrigido = _sp([("2026-09-25 20:00", "100", "Fernando Sousa", "0200100101", 4)])
    novo, corr = C.reavaliar(estado, corrigido, CAD, AGORA)
    assert len(corr) == 1 and novo["divergencias"][0]["status"] == "corrigida"
    assert C.constante_site(novo, AGORA)["rows"] == []


def test_2_0_nao_aceita_correcao_lancada_na_data_de_hoje():
    estado = _uma_divergencia(_sp([]), _zmm([("100", 4, "0200100101")]))
    hoje = _sp([("2026-09-28 08:00", "100", "Fernando Sousa", "0200100101", 4)])
    assert C.reavaliar(estado, hoje, CAD, AGORA)[1] == []


def test_2_0_nao_bipado_bipado_errado_troca_a_etiqueta():
    """Bipado depois na data original, mas com saldo errado: a linha vira "−5", não fica "Não bipado"."""
    estado = _uma_divergencia(_sp([]), _zmm([("100", 4, "0200100101")]))
    errado = _sp([("2026-09-25 20:00", "100", "Fernando Sousa", "0200100101", 1)])
    novo, corr = C.reavaliar(estado, errado, CAD, AGORA)
    (d,) = novo["divergencias"]
    assert corr == [] and d["status"] == "aberta" and d["categoria"] == "negativo" and d["divergencia"] == C.MENOS + "3"
    end_errado = _sp([("2026-09-25 20:00", "100", "Fernando Sousa", "0999999999", 4)])
    assert C.reavaliar(estado, end_errado, CAD, AGORA)[0]["divergencias"][0]["categoria"] == "endereco"


def test_2_0_usa_o_saldo_gravado_e_nunca_cria_divergencia_nova():
    estado = _uma_divergencia(_sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 7)]),
                              _zmm([("100", 4, "0200100101")]))
    assert estado["divergencias"][0]["saldo_sistema"] == 4
    ainda_errado = _sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 6)])
    novo, corr = C.reavaliar(estado, ainda_errado, CAD, AGORA)
    assert corr == [] and len(novo["divergencias"]) == 1
    certo = _sp([("2026-09-25 10:00", "100", "Fernando Sousa", "0200100101", 4)])
    assert len(C.reavaliar(estado, certo, CAD, AGORA)[1]) == 1


def test_estado_inicial_comeca_em_25_09():
    assert C.estado_inicial() == {"ultimo_dia_auditado": "2026-09-24", "divergencias": []}
    assert config.CHECKLIST_BIPAGEM_INICIO == "2026-09-25"


def test_gravar_escreve_json_e_constante_do_mesmo_dict(tmp_path):
    index = tmp_path / "index.html"
    index.write_text('<script>\nconst CHECKLIST_BIPAGEM = {"rows":[]};\n</script>', encoding="utf-8")
    estado = _uma_divergencia(_sp([]), _zmm([("100", 4, "0200100101")]))
    C.gravar(str(tmp_path), str(index), estado, AGORA)
    assert '"categoria":"nao-bipado"' in index.read_text(encoding="utf-8")
    assert (tmp_path / "checklist_bipagem.json").exists()
