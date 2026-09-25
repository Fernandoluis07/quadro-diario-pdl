import datetime
import json
import os
import subprocess

import pytest

from backend import saude

D = datetime.date
DT = datetime.datetime


def _codigos(alertas):
    return [a["codigo"] for a in alertas]


# ---- calendário ------------------------------------------------------------------

def test_prazo_de_sexta_e_o_proximo_dia_util_as_11h():
    assert saude.prazo_de_congelamento(D(2026, 9, 4)) == DT(2026, 9, 8, 11, 0)  # 07/09 é feriado


# ---- 1. sequência ------------------------------------------------------------------

def test_dia_pulado_so_vira_alerta_depois_do_prazo():
    esperadas = {D(2026, 9, 16), D(2026, 9, 17)}
    congelados = {"2026-09-16"}
    assert saude.checar_sequencia(esperadas, congelados, DT(2026, 9, 18, 8, 0)) == []  # 17 ainda no prazo
    alertas = saude.checar_sequencia(esperadas, congelados, DT(2026, 9, 18, 11, 30))
    assert _codigos(alertas) == ["dia_pulado"] and "17/09" in alertas[0]["titulo"]


def test_dia_pulado_no_meio_do_historico_continua_critico_dias_depois():
    alertas = saude.checar_sequencia({D(2026, 8, 31), D(2026, 9, 1)}, {"2026-09-01"}, DT(2026, 9, 18, 8, 0))
    assert alertas[0]["nivel"] == "critico" and "31/08" in alertas[0]["titulo"]


def test_ao_congelar_conta_como_pulado_tudo_antes_da_data_sem_prazo():
    esperadas = {D(2026, 9, 16), D(2026, 9, 17)}
    alertas = saude.checar_sequencia(esperadas, {"2026-09-15"}, DT(2026, 9, 18, 7, 0), hoje_a_congelar=D(2026, 9, 17))
    assert _codigos(alertas) == ["dia_pulado"] and "16/09" in alertas[0]["titulo"]


def test_congelar_dia_anterior_a_um_ja_congelado_e_fora_de_sequencia():
    alertas = saude.checar_sequencia(
        {D(2026, 9, 17)}, {"2026-09-17", "2026-09-18"}, DT(2026, 9, 18, 10, 0), hoje_a_congelar=D(2026, 9, 17)
    )
    assert "fora_de_sequencia" in _codigos(alertas)


def test_dia_anterior_ao_inicio_do_historico_nao_conta():
    assert saude.checar_sequencia({D(2026, 3, 30)}, set(), DT(2026, 9, 18, 12, 0)) == []


# ---- 3. dia em aberto --------------------------------------------------------------

def test_congelar_hoje_ou_futuro_e_dia_em_aberto():
    agora = DT(2026, 9, 18, 8, 32)
    assert _codigos(saude.checar_dia_em_aberto(D(2026, 9, 18), agora)) == ["dia_em_aberto"]
    assert _codigos(saude.checar_dia_em_aberto(D(2026, 9, 19), agora)) == ["dia_em_aberto"]
    assert saude.checar_dia_em_aberto(D(2026, 9, 17), agora) == []


def test_dia_fechado_incompleto_compara_congelado_com_mb51_atual():
    hist = {"2026-09-01": {"estornos_d009": 0, "inventario_rotativo_d009": 54}, "2026-09-02": {"estornos_d009": 1}}
    atual = {"2026-09-01": {"estornos_d009": 2, "inventario_rotativo_d009": 55}, "2026-09-02": {"estornos_d009": 1}}
    alertas = saude.checar_dias_fechados_incompletos(None, hist, lambda _mb, d: atual[d.isoformat()])
    assert len(alertas) == 1 and "01/09" in alertas[0]["titulo"]
    assert "estornos_d009: congelado 0 x MB51 hoje 2" in alertas[0]["detalhe"]


# ---- 2. extração -------------------------------------------------------------------

def test_extracao_de_ontem_num_dia_util_depois_das_9h_esta_desatualizada():
    m = {"MB51.xlsx": DT(2026, 9, 17, 9, 0), "ZMM028.xlsx": DT(2026, 9, 18, 7, 42)}
    alertas = saude.checar_extracoes(m, D(2026, 9, 17), DT(2026, 9, 18, 10, 0))
    desatualizados = [a for a in alertas if a["codigo"] == "extracao_desatualizada"]
    assert len(desatualizados) == 1 and "MB51.xlsx" in desatualizados[0]["titulo"]
    assert "extracoes_dessincronizadas" in _codigos(alertas)  # MB51 de ontem x ZMM028 de hoje também não são do mesmo instante


def test_arquivo_ausente_e_critico():
    assert saude.checar_extracoes({"MB25.xlsx": None}, None, DT(2026, 9, 18, 10, 0))[0]["codigo"] == "extracao_ausente"


def test_mb51_sem_os_ultimos_dias():
    alertas = saude.checar_extracoes({"MB51.xlsx": DT(2026, 9, 18, 9, 30)}, D(2026, 9, 15), DT(2026, 9, 18, 10, 0))
    assert "mb51_sem_ultimos_dias" in _codigos(alertas)


def test_extracoes_com_horarios_muito_diferentes():
    m = {"MB51.xlsx": DT(2026, 9, 18, 9, 57), "ZMM028.xlsx": DT(2026, 9, 18, 7, 42)}
    assert _codigos(saude.checar_extracoes(m, D(2026, 9, 17), DT(2026, 9, 18, 10, 0))) == ["extracoes_dessincronizadas"]


def test_fim_de_semana_nao_exige_extracao_do_proprio_dia():
    m = {"MB51.xlsx": DT(2026, 9, 18, 9, 30), "ZMM028.xlsx": DT(2026, 9, 18, 9, 0)}
    assert saude.checar_extracoes(m, D(2026, 9, 17), DT(2026, 9, 19, 15, 0)) == []


# ---- 4. código sem commit ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    bare = tmp_path / "remoto.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "main")
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "a.py").write_text("x = 1\n")
    _git(r, "add", "a.py")
    _git(r, "commit", "-m", "inicio")
    _git(r, "remote", "add", "origin", str(bare))
    _git(r, "push", "-u", "origin", "main")
    return r


def _envelhecer(caminho, horas):
    t = (DT.now() - datetime.timedelta(hours=horas)).timestamp()
    os.utime(caminho, (t, t))


def test_repositorio_limpo_nao_gera_alerta(repo):
    assert saude.checar_codigo_sem_commit(str(repo), DT.now()) == []


def test_arquivo_novo_sem_commit_so_alerta_depois_de_24h_e_vira_critico_com_3_dias(repo):
    (repo / "novo.py").write_text("y = 2\n")
    assert saude.checar_codigo_sem_commit(str(repo), DT.now()) == []
    _envelhecer(repo / "novo.py", 30)
    alertas = saude.checar_codigo_sem_commit(str(repo), DT.now())
    assert alertas[0]["codigo"] == "codigo_sem_commit" and alertas[0]["nivel"] == "aviso" and "novo.py" in alertas[0]["titulo"]
    _envelhecer(repo / "novo.py", 24 * 21)
    assert saude.checar_codigo_sem_commit(str(repo), DT.now())[0]["nivel"] == "critico"


def test_arquivo_alterado_e_rastreado_tambem_conta(repo):
    (repo / "a.py").write_text("x = 2\n")
    _envelhecer(repo / "a.py", 100)
    assert "a.py" in saude.checar_codigo_sem_commit(str(repo), DT.now())[0]["titulo"]


def test_alertas_saude_js_gerado_nao_conta_como_codigo_sem_commit(repo):
    (repo / "alertas_saude.js").write_text("window.SAUDE_SISTEMA = {};\n")
    _envelhecer(repo / "alertas_saude.js", 500)
    assert saude.checar_codigo_sem_commit(str(repo), DT.now()) == []


def test_commit_local_sem_push_alerta(repo):
    (repo / "b.py").write_text("z = 3\n")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-m", "local")
    alertas = saude.checar_codigo_sem_commit(str(repo), DT.now() + datetime.timedelta(hours=5))
    assert _codigos(alertas) == ["commit_sem_push"]


def test_pasta_que_nao_e_repositorio_avisa_em_vez_de_calar(tmp_path):
    assert saude.checar_codigo_sem_commit(str(tmp_path), DT.now())[0]["codigo"] == "git_indisponivel"


# ---- saída / notificação -----------------------------------------------------------------

def test_banner_mostra_detalhe_e_sem_alerta_diz_ok():
    assert "nenhum alerta" in saude.formatar_banner([])
    a = [saude._alerta("y", "critico", "T2", "det"), saude._alerta("x", "aviso", "T1")]
    banner = saude.formatar_banner(a)
    assert banner.index("T2") < banner.index("T1") and "det" in banner


def test_gravar_alertas_js_e_javascript_valido(tmp_path):
    caminho = saude.gravar_alertas_js(str(tmp_path), [saude._alerta("x", "critico", "Título ç")], DT(2026, 9, 18, 8, 0))
    texto = open(caminho, encoding="utf-8").read()
    assert texto.startswith("window.SAUDE_SISTEMA = ") and texto.rstrip().endswith(";")
    payload = json.loads(texto[len("window.SAUDE_SISTEMA = "):].rstrip().rstrip(";"))
    assert payload["gerado_em"] == "2026-09-18T08:00:00" and payload["alertas"][0]["titulo"] == "Título ç"


def test_notificar_so_abre_janela_para_critico_e_nao_repete_o_mesmo_alerta(tmp_path, monkeypatch):
    abertas = []
    monkeypatch.setattr(saude.subprocess, "Popen", lambda *a, **k: abertas.append(a))
    agora = DT(2026, 9, 18, 8, 0)
    assert saude.notificar_janela([saude._alerta("x", "aviso", "só aviso")], str(tmp_path), agora) is False
    crit = [saude._alerta("dia_pulado", "critico", "31/08 pulado")]
    assert saude.notificar_janela(crit, str(tmp_path), agora) is True
    assert saude.notificar_janela(crit, str(tmp_path), agora + datetime.timedelta(hours=2)) is False   # mesmo alerta, <6h
    assert saude.notificar_janela(crit, str(tmp_path), agora + datetime.timedelta(hours=7)) is True    # lembra depois de 6h
    novo = crit + [saude._alerta("z", "critico", "novo")]
    assert saude.notificar_janela(novo, str(tmp_path), agora + datetime.timedelta(hours=8)) is True     # alerta novo
    assert len(abertas) == 3


# ---- portão de push -------------------------------------------------------------------

def _fake_verificar(alertas):
    return lambda **_kw: alertas


def test_portao_libera_quando_so_ha_aviso_e_info(monkeypatch, capsys):
    monkeypatch.setattr(saude, "verificar", _fake_verificar([saude._alerta("a", "aviso", "x"), saude._alerta("b", "info", "y")]))
    assert saude.portao_de_push() == 0
    assert "liberado" in capsys.readouterr().out


def test_portao_cancela_com_qualquer_alerta_critico(monkeypatch, capsys):
    monkeypatch.setattr(saude, "verificar", _fake_verificar([saude._alerta("dia_pulado", "critico", "31/08 pulado")]))
    assert saude.portao_de_push() == 1
    saida = capsys.readouterr().out
    assert "PUSH CANCELADO" in saida and "31/08 pulado" in saida


def test_portao_falha_fechado_se_o_verificador_quebrar(monkeypatch, capsys):
    def quebra(**_kw):
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(saude, "verificar", quebra)
    assert saude.portao_de_push() == 1
    assert "PUSH CANCELADO" in capsys.readouterr().out


def test_hook_pre_push_versionado_cancela_o_push_de_verdade(tmp_path):
    """Push real (git) contra um remoto temporário: com o hook do repositório e um portão
    que retorna 1, o push é recusado e o remoto continua vazio."""
    hook = os.path.join(os.path.dirname(saude.__file__), "..", "hooks", "pre-push")
    assert open(hook, encoding="utf-8").read().rstrip().endswith("python -m backend.saude --gate")
    bare = tmp_path / "r.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "main")
    w = tmp_path / "w"
    (w / "hooks").mkdir(parents=True)
    _git(w, "init", "-b", "main")
    _git(w, "config", "user.email", "t@t")
    _git(w, "config", "user.name", "t")
    (w / "hooks" / "pre-push").write_text("#!/bin/sh\necho PORTAO; exit 1\n", newline="\n")
    _git(w, "config", "core.hooksPath", "hooks")
    (w / "a.txt").write_text("a")
    _git(w, "add", "a.txt")
    _git(w, "commit", "-m", "c")
    _git(w, "remote", "add", "origin", str(bare))
    r = subprocess.run(["git", "push", "origin", "main"], cwd=w, capture_output=True, text=True)
    assert r.returncode != 0 and "PORTAO" in (r.stdout + r.stderr)
    assert subprocess.run(["git", "branch", "--list"], cwd=bare, capture_output=True, text=True).stdout.strip() == ""


def test_dados_reconstruidos_so_avisa_dos_dias_ainda_nao_conferidos():
    registro = {
        "2026-08-31": {"snapshot": "2026-09-17", "conferido_em": "2026-09-24"},
        "2026-09-04": {"snapshot": "2026-09-17"},
    }
    alertas = saude.checar_dados_reconstruidos(registro)
    assert len(alertas) == 1
    assert "1 dia(s)" in alertas[0]["titulo"] and "04/09" in alertas[0]["titulo"] and "31/08" not in alertas[0]["titulo"]
    registro["2026-09-04"]["conferido_em"] = "2026-09-24"
    assert saude.checar_dados_reconstruidos(registro) == []
