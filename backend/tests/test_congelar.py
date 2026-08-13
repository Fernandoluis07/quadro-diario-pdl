import datetime
import json

import pytest

from backend import congelar

# ---- HTML sintético fiel à estrutura real (seção Início + 4 painéis + cards +
# constantes HISTORICO_*), o suficiente pra exercitar congelar_dia() fim a fim. ----
INDEX_HTML_SINTETICO = """<!doctype html>
<html><body>
<main class="content">

    <!-- ===================== INÍCIO ===================== -->
    <section class="screen active" id="screen-inicio">
      <div class="inicio-body">
        <div class="panels-col">
        <div class="panel p-alert">
          <div class="panel-head">Pontos de Atenção</div>
          <ul class="bullet-list">
            <li>Item velho 1</li>
          </ul>
        </div>

        <div class="panel p-notice">
          <div class="panel-head">Avisos Importantes</div>
          <ul class="bullet-list">
            <li>Aviso velho</li>
          </ul>
        </div>

        <div class="panel p-receipt">
          <div class="panel-empty">Fonte de dado ainda não definida</div>
        </div>

        <div class="panel p-vacation">
          <div class="panel-head">Datas Importantes</div>
          <div class="bullet-list vacation-list">
            <div class="vacation-row">
              <div class="vacation-row-top"><span class="name">Fulano Velho</span><span class="vacation-status vacation-status--done">Quitada</span></div>
              <span class="period">01/01/20 a 02/01/20</span>
            </div>
          </div>
        </div>
      </div>
      </div>
    </section>

    <!-- ===================== PLACEHOLDERS ===================== -->
    <section class="screen" id="screen-calendario">
      <div class="panel p-alert">
        <ul class="bullet-list" id="calAttentionList"></ul>
      </div>
      <div class="panel p-notice">
        <ul class="bullet-list" id="calNoticeList"></ul>
      </div>
      <div class="bullet-list vacation-list" id="calVacationList"></div>
    </section>

<script>
const BLOCK1 = [
  { n:1, title:'Linhas Atendidas D009',    value:'0',  yesterday:'0',  deltaPct:0.0, dir:'flat', color:'blue', icon:'trendUp', spark:[0,0] },
  { n:2, title:'Linhas Atendidas D016',    value:'0',  yesterday:'0',  deltaPct:0.0, dir:'flat', color:'blue', icon:'check',   spark:[0,0] },
  { n:3, title:'Recebimentos D009',        value:'0',  yesterday:'0',  deltaPct:0.0, dir:'flat', color:'green',  icon:'truck',   spark:[0,0] },
  { n:4, title:'Recebimentos D016',        value:'0',  yesterday:'0',  deltaPct:0.0, dir:'flat',   color:'green',  icon:'truck',   spark:[0,0] },
  { n:5, title:'Estornos D009',            value:'0',  yesterday:'0',  deltaPct:0.0, dir:'flat',   color:'red',   icon:'undo',    spark:[0,0] },
  { n:6, title:'Estornos D016',            value:'0',  yesterday:'0',  deltaPct:0.0,    dir:'flat', color:'red',   icon:'undo',    spark:[0,0] },
  { n:7, title:'Inventário Rotativo D009', value:'0', yesterday:'0', deltaPct:0.0,dir:'flat', color:'violet',  icon:'refresh', spark:[0,0] },
  { n:8, title:'Inventário Rotativo D016', value:'0',  yesterday:'0',  deltaPct:0.0,dir:'flat',   color:'violet',  icon:'refresh', spark:[0,0] },
];
const BLOCK2 = [
  { n:9,  title:'Pendências Atendimento Linhas', value:'0', yesterday:'0', deltaPct:0.0,  dir:'flat',   color:'magenta', icon:'alertCircle',    spark:[0,0] },
  { n:10, title:'Reservas Pendentes',            value:'0', yesterday:'0', deltaPct:0.0,  dir:'flat',   color:'aqua',    icon:'clipboard',      spark:[0,0] },
  { n:11, title:'Notas Aguardando Lançamento',   value:'0',  yesterday:'0',  deltaPct:0,     dir:'flat', color:'yellow', icon:'clipboardCheck', spark:[0,0] },
  { n:12, title:'NF Pendente Faturamento',       value:'0',  yesterday:'0',  deltaPct:0, dir:'flat', color:'magenta', icon:'doc',            spark:[0,0] },
  { n:13, title:'Devolução',                     value:'0',  yesterday:'0',  deltaPct:0,   dir:'flat',   color:'magenta',   icon:'refresh',        spark:[0,0] },
];
const BLOCK3 = [
  { n:14, title:'Itens em Estoque com Saldo', value:'0', yesterday:'0', deltaPct:0, dir:'flat',   color:'aqua',  icon:'box',     spark:[0,0] },
  { n:15, title:'Valor do Estoque Total',     value:'0', yesterday:'0', deltaPct:0, dir:'flat', color:'orange', icon:'cash',    spark:[0,0] },
  { n:16, title:'Itens MRP Saldo Zero',       value:'0',   yesterday:'0',   deltaPct:0, dir:'flat', color:'yellow',    icon:'warnTri', spark:[0,0] },
  { n:17, title:'Curva ABC',                  value:'30',    yesterday:'30',    deltaPct:0,    dir:'flat', color:'yellow', icon:'abcBars', spark:[30,30] },
  { n:18, title:'Itens sem Endereço',         value:'0',     yesterday:'0',     deltaPct:0,    dir:'flat', color:'aqua', icon:'pin',     spark:[0,0] },
];
const LOOSE = [
  { n:19, title:'Intercompany',            value:'0', yesterday:'0', deltaPct:0, dir:'flat', color:'orange',  icon:'docLine', spark:[0,0] },
  { n:20, title:'Scanner de Documentos',   value:'0', yesterday:'0', deltaPct:0, dir:'flat', color:'orange', icon:'scan',    spark:[0,0] },
];

const HISTORICO_MB51 = {"2026-08-09":{"linhas_atendidas_d009":10,"linhas_atendidas_d016":0,"estornos_d009":0,"estornos_d016":0,"recebimentos_d009":1,"recebimentos_d016":0,"inventario_rotativo_d009":10,"inventario_rotativo_d016":0,"intercompany":3}};
const HISTORICO_MANUAL = {"2026-08-09":{"notas_aguardando_lancamento":1,"devolucao":0,"scanner_documentos":2,"nf_pendente_faturamento":0,"reservas_pendentes":5,"pendencias_atendimento_linhas":9}};
const HISTORICO_ZMM028 = {"2026-08-09":{"itens_estoque_com_saldo":100,"itens_mrp_saldo_zero":5,"valor_estoque_total":1000.0,"itens_sem_endereco":0}};
const HISTORICO_MENSAL = {"2026-08":{"linhas_atendidas_mes":10}};
const HISTORICO_PAINEIS = {"2026-08-09":{"pontos_atencao":["Ponto velho"],"avisos_importantes":[],"datas_importantes":[]}};
const CHECKLIST_RESERVAS = {"rows":[]};
</script>
</body></html>
"""

INDICADORES_HOJE = {
    "data_referencia": "2026-08-10",
    "data_referencia_ontem": "2026-08-09",
    "linhas_atendidas_d009": 116,
    "linhas_atendidas_d016": 0,
    "estornos_d009": 5,
    "estornos_d016": 0,
    "recebimentos_d009": 7,
    "recebimentos_d016": 0,
    "inventario_rotativo_d009": 115,
    "inventario_rotativo_d016": 0,
    "pendencias_atendimento_linhas": 76,
    "reservas_pendentes": 26,
    "itens_estoque_com_saldo": 5323,
    "valor_estoque_total": 28095123.45,
    "itens_mrp_saldo_zero": 173,
    "itens_sem_endereco": 1,
    "checklist_reservas": [
        {"numero_reserva": "R1", "material": "100", "descricao": "Item A", "data_necessidade": "20/08/2026",
         "qtd_necessaria": 5.0, "centro_custo": "", "ordem": "O1", "saldo_atual": 42.0, "endereco": "A-01"},
    ],
    "ontem": {
        "linhas_atendidas_d009": 2, "linhas_atendidas_d016": 0,
        "estornos_d009": 0, "estornos_d016": 0,
        "recebimentos_d009": 0, "recebimentos_d016": 0,
        "inventario_rotativo_d009": 2, "inventario_rotativo_d016": 0,
    },
}

MANUAL_HOJE = {
    "notas_aguardando_lancamento": 0,
    "nf_pendente_faturamento": 6,
    "devolucao": 2,
    "scanner_documentos": 0,
    "intercompany": 2,
}


def _preparar_repo(tmp_path):
    index_path = tmp_path / "index.html"
    index_path.write_text(INDEX_HTML_SINTETICO, encoding="utf-8")

    # espelha o dia 09/08 que já vem embutido no HTML sintético acima, como no repo
    # real (JSON solto e constante embutida sempre começam em sincronia).
    (tmp_path / "historico_mb51.json").write_text(json.dumps({
        "2026-08-09": {
            "linhas_atendidas_d009": 10, "linhas_atendidas_d016": 0,
            "estornos_d009": 0, "estornos_d016": 0,
            "recebimentos_d009": 1, "recebimentos_d016": 0,
            "inventario_rotativo_d009": 10, "inventario_rotativo_d016": 0,
            "intercompany": 3,
        }
    }), encoding="utf-8")
    (tmp_path / "historico_manuais.json").write_text(json.dumps({
        "2026-08-09": {
            "notas_aguardando_lancamento": 1, "devolucao": 0, "scanner_documentos": 2,
            "nf_pendente_faturamento": 0, "reservas_pendentes": 5, "pendencias_atendimento_linhas": 9,
        }
    }), encoding="utf-8")
    (tmp_path / "historico_zmm028.json").write_text(json.dumps({
        "2026-08-09": {
            "itens_estoque_com_saldo": 100, "itens_mrp_saldo_zero": 5,
            "valor_estoque_total": 1000.0, "itens_sem_endereco": 0,
        }
    }), encoding="utf-8")
    (tmp_path / "historico_mensal.json").write_text(json.dumps({"2026-08": {"linhas_atendidas_mes": 10}}), encoding="utf-8")
    (tmp_path / "historico_paineis.json").write_text(json.dumps({
        "2026-08-09": {"pontos_atencao": ["Ponto velho"], "avisos_importantes": [], "datas_importantes": []},
    }), encoding="utf-8")

    return str(tmp_path), str(index_path)


# ---- montagem de entradas (sem IO) -----------------------------------------

def test_montar_entrada_mb51_injeta_intercompany_manual():
    entrada = congelar.montar_entrada_mb51(INDICADORES_HOJE, intercompany_manual=2)
    assert entrada == {
        "linhas_atendidas_d009": 116, "linhas_atendidas_d016": 0,
        "estornos_d009": 5, "estornos_d016": 0,
        "recebimentos_d009": 7, "recebimentos_d016": 0,
        "inventario_rotativo_d009": 115, "inventario_rotativo_d016": 0,
        "intercompany": 2,
    }


def test_montar_entrada_manual_combina_planilha_com_mb25():
    entrada = congelar.montar_entrada_manual(INDICADORES_HOJE, MANUAL_HOJE)
    assert entrada == {
        "notas_aguardando_lancamento": 0, "devolucao": 2, "scanner_documentos": 0,
        "nf_pendente_faturamento": 6, "reservas_pendentes": 26, "pendencias_atendimento_linhas": 76,
    }
    assert "intercompany" not in entrada


def test_montar_entrada_zmm028():
    entrada = congelar.montar_entrada_zmm028(INDICADORES_HOJE)
    assert entrada == {
        "itens_estoque_com_saldo": 5323, "itens_mrp_saldo_zero": 173,
        "valor_estoque_total": 28095123.45, "itens_sem_endereco": 1,
    }


def test_montar_entrada_paineis_omite_status_vazio():
    registros = [
        {"nome": "Ana Silva", "periodo_inicio": datetime.date(2026, 9, 1), "periodo_fim": datetime.date(2026, 9, 10), "duracao_dias": 10, "aprovacao": "OK", "status": "Programada"},
        {"nome": "Milton Junior", "periodo_inicio": datetime.date(2026, 12, 28), "periodo_fim": datetime.date(2027, 1, 16), "duracao_dias": 20, "aprovacao": "", "status": ""},
    ]
    entrada = congelar.montar_entrada_paineis(["Ponto 1"], ["Aviso 1"], registros)
    assert entrada == {
        "pontos_atencao": ["Ponto 1"],
        "avisos_importantes": ["Aviso 1"],
        "datas_importantes": [
            {"name": "Ana Silva", "period": "01/09/26 a 10/09/26 · 10 dias", "statusLabel": "Programada", "statusClasse": "scheduled"},
            {"name": "Milton Junior", "period": "28/12/26 a 16/01/27 · 20 dias"},
        ],
    }


def test_ja_congelado():
    assert congelar.ja_congelado({"2026-08-09": {}}, "2026-08-09") is True
    assert congelar.ja_congelado({"2026-08-09": {}}, "2026-08-10") is False


# ---- constante HISTORICO_* embutida -----------------------------------------

def test_atualizar_constante_historico_js_substitui_bloco_inteiro():
    html = "const HISTORICO_MB51 = {\"2026-08-09\":{\"x\":1}};\nresto do arquivo"
    novo = congelar.atualizar_constante_historico_js(html, "HISTORICO_MB51", {"2026-08-10": {"x": 2}})
    assert '"2026-08-10":{"x":2}' in novo
    assert "2026-08-09" not in novo
    assert novo.endswith("\nresto do arquivo")


def test_atualizar_constante_historico_js_erro_se_nao_achar():
    with pytest.raises(ValueError, match="não encontrada"):
        congelar.atualizar_constante_historico_js("sem const nenhuma aqui", "HISTORICO_MB51", {})


# ---- painéis estáticos da tela Início ----------------------------------------

def test_atualizar_painel_pontos_avisos_troca_bullets_da_tela_inicio_sem_tocar_calendario():
    novo = congelar.atualizar_painel_pontos_avisos(INDEX_HTML_SINTETICO, ["Novo ponto 1", "Novo ponto 2"], ["Novo aviso"])
    assert "Item velho 1" not in novo
    assert "<li>Novo ponto 1</li>" in novo
    assert "<li>Novo ponto 2</li>" in novo
    assert "<li>Novo aviso</li>" in novo
    # tela Calendário (ul com id) não foi tocada
    assert 'id="calAttentionList"></ul>' in novo
    assert 'id="calNoticeList"></ul>' in novo


def test_atualizar_painel_pontos_avisos_escapa_html():
    novo = congelar.atualizar_painel_pontos_avisos(INDEX_HTML_SINTETICO, ["Item com <tag> & \"aspas\""], [])
    assert "<li>Item com &lt;tag&gt; &amp; \"aspas\"</li>" in novo


def test_atualizar_painel_datas_importantes_regenera_linhas():
    registros = [
        {"nome": "Ana Silva", "periodo_inicio": datetime.date(2026, 9, 1), "periodo_fim": datetime.date(2026, 9, 10), "duracao_dias": 10, "aprovacao": "OK", "status": "Programada"},
        {"nome": "Beto Souza", "periodo_inicio": datetime.date(2026, 10, 1), "periodo_fim": datetime.date(2026, 10, 5), "duracao_dias": None, "aprovacao": "OK", "status": "Aguardando aprovação"},
    ]
    novo = congelar.atualizar_painel_datas_importantes(INDEX_HTML_SINTETICO, registros)
    assert "Fulano Velho" not in novo
    assert '<span class="name">Ana Silva</span>' in novo
    assert 'vacation-status--scheduled">Programada</span>' in novo
    assert '<span class="period">01/09/26 a 10/09/26 · 10 dias</span>' in novo
    assert '<span class="name">Beto Souza</span>' in novo
    assert 'vacation-status--pending">Aguardando aprovação</span>' in novo
    assert '<span class="period">01/10/26 a 05/10/26</span>' in novo
    assert 'id="calVacationList"></div>' in novo


# ---- congelar_dia fim a fim --------------------------------------------------

def test_congelar_dia_grava_os_5_json_e_atualiza_index_html(tmp_path):
    repo_root, index_path = _preparar_repo(tmp_path)

    resultado = congelar.congelar_dia(
        repo_root=repo_root,
        index_path=index_path,
        data_ref=datetime.date(2026, 8, 10),
        indicadores=INDICADORES_HOJE,
        manual_hoje=MANUAL_HOJE,
        pontos_atencao=["Ponto novo"],
        avisos_importantes=["Aviso novo"],
        datas_importantes=[],
        resumo_mes={"2026-08": {"linhas_atendidas_mes": 999}},
    )

    assert resultado["data"] == "2026-08-10"

    historico_mb51 = json.loads((tmp_path / "historico_mb51.json").read_text(encoding="utf-8"))
    assert historico_mb51["2026-08-10"]["intercompany"] == 2
    assert historico_mb51["2026-08-09"]["linhas_atendidas_d009"] == 10  # dia antigo intocado

    historico_manuais = json.loads((tmp_path / "historico_manuais.json").read_text(encoding="utf-8"))
    assert historico_manuais["2026-08-10"]["reservas_pendentes"] == 26

    historico_zmm028 = json.loads((tmp_path / "historico_zmm028.json").read_text(encoding="utf-8"))
    assert historico_zmm028["2026-08-10"]["itens_estoque_com_saldo"] == 5323

    historico_mensal = json.loads((tmp_path / "historico_mensal.json").read_text(encoding="utf-8"))
    assert historico_mensal["2026-08"]["linhas_atendidas_mes"] == 999

    historico_paineis = json.loads((tmp_path / "historico_paineis.json").read_text(encoding="utf-8"))
    assert historico_paineis["2026-08-10"] == {"pontos_atencao": ["Ponto novo"], "avisos_importantes": ["Aviso novo"], "datas_importantes": []}
    assert historico_paineis["2026-08-09"]["pontos_atencao"] == ["Ponto velho"]  # dia antigo intocado

    html_novo = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '"2026-08-10":{"linhas_atendidas_d009":116' in html_novo
    assert "title:'Linhas Atendidas D009',    value:'116'" in html_novo
    assert "yesterday:'2'" in html_novo
    assert "title:'Intercompany',            value:'2'" in html_novo
    assert "<li>Ponto novo</li>" in html_novo
    assert "{ n:17, title:'Curva ABC',                  value:'30',    yesterday:'30',    deltaPct:0,    dir:'flat', color:'yellow', icon:'abcBars', spark:[30,30] }," in html_novo
    assert '"2026-08-10":{"pontos_atencao":["Ponto novo"],"avisos_importantes":["Aviso novo"],"datas_importantes":[]}' in html_novo

    assert '"rows":[{"numero_reserva":"R1","material":"100","descricao":"Item A","data_necessidade":"20/08/2026","qtd_necessaria":5.0,"centro_custo":"","ordem":"O1","saldo_atual":42.0,"endereco":"A-01"}]' in html_novo


def test_congelar_dia_recusa_sobrescrever_dia_ja_congelado(tmp_path):
    repo_root, index_path = _preparar_repo(tmp_path)
    kwargs = dict(
        repo_root=repo_root,
        index_path=index_path,
        data_ref=datetime.date(2026, 8, 10),
        indicadores=INDICADORES_HOJE,
        manual_hoje=MANUAL_HOJE,
        pontos_atencao=[],
        avisos_importantes=[],
        datas_importantes=[],
        resumo_mes={},
    )
    congelar.congelar_dia(**kwargs)

    html_antes = (tmp_path / "index.html").read_text(encoding="utf-8")
    with pytest.raises(congelar.DiaJaCongeladoError, match="2026-08-10"):
        congelar.congelar_dia(**kwargs)
    html_depois = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert html_antes == html_depois  # nada foi reescrito na segunda tentativa


def test_congelar_dia_com_forcar_sobrescreve_dia_ja_congelado(tmp_path):
    repo_root, index_path = _preparar_repo(tmp_path)
    kwargs = dict(
        repo_root=repo_root,
        index_path=index_path,
        data_ref=datetime.date(2026, 8, 10),
        indicadores=INDICADORES_HOJE,
        manual_hoje=MANUAL_HOJE,
        pontos_atencao=[],
        avisos_importantes=[],
        datas_importantes=[],
        resumo_mes={},
    )
    congelar.congelar_dia(**kwargs)

    kwargs_recalculado = {**kwargs, "indicadores": {**INDICADORES_HOJE, "linhas_atendidas_d009": 999}}
    resultado = congelar.congelar_dia(**kwargs_recalculado, forcar=True)

    assert resultado["data"] == "2026-08-10"
    historico_mb51 = json.loads((tmp_path / "historico_mb51.json").read_text(encoding="utf-8"))
    assert historico_mb51["2026-08-10"]["linhas_atendidas_d009"] == 999
