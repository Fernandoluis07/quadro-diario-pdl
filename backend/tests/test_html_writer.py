from backend import html_writer

# Recorte fiel ao formato real do index.html: mesma ordem de campos no objeto
# JS, incluindo um card automatizado (Linhas Atendidas D009) e um manual
# (Contagem Pendentes) que NÃO pode ser tocado.
HTML_SINTETICO = """
const BLOCK1 = [
  { n:1, title:'Linhas Atendidas D009',    value:'21', yesterday:'18', deltaPct:16.7, dir:'up',   color:'green', icon:'trendUp', spark:[9,12] },
];
const BLOCK2 = [
  { n:9,  title:'Pendências Atendimento Linhas', value:'32', yesterday:'25', deltaPct:28.0,  dir:'up',   color:'orange', icon:'alertCircle', spark:[19,22] },
  { n:11, title:'Contagem Pendentes',            value:'0',  yesterday:'0',  deltaPct:0,     dir:'flat', color:'purple', icon:'clipboardCheck', spark:[0,0] },
];
const BLOCK3 = [
  { n:15, title:'Valor do Estoque Total',     value:'28,70', yesterday:'28,59', deltaPct:0.39, dir:'up',   color:'purple', icon:'cash', spark:[28.0,28.15] },
  { n:17, title:'Curva ABC',                  value:'30',    yesterday:'30',    deltaPct:0,    dir:'flat', color:'purple', icon:'abcBars', spark:[30,30] },
];
"""

INDICADORES = {
    "linhas_atendidas_d009": 140,
    "linhas_atendidas_d016": 0,
    "recebimentos_d009": 14,
    "recebimentos_d016": 0,
    "estornos_d009": 1,
    "estornos_d016": 0,
    "inventario_rotativo_d009": 113,
    "inventario_rotativo_d016": 0,
    "pendencias_atendimento_linhas": 93,
    "reservas_pendentes": 45,
    "itens_estoque_com_saldo": 5341,
    "valor_estoque_total": 28786943.43,
    "itens_mrp_saldo_zero": 168,
    "itens_sem_endereco": 2,
}


def test_atualiza_valor_de_card_automatizado():
    novo_html, aplicados, nao_encontrados = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    assert "title:'Linhas Atendidas D009',    value:'140'" in novo_html
    assert any(a["indicador"] == "linhas_atendidas_d009" and a["valor_novo"] == "140" for a in aplicados)


def test_nao_toca_card_manual_contagem_pendentes():
    novo_html, _, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    linha_manual_original = "{ n:11, title:'Contagem Pendentes',            value:'0',  yesterday:'0',  deltaPct:0,     dir:'flat', color:'purple', icon:'clipboardCheck', spark:[0,0] },"
    assert linha_manual_original in novo_html


def test_formata_valor_estoque_total_em_milhares_sem_decimais():
    novo_html, aplicados, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    assert "title:'Valor do Estoque Total',     value:'28.787'" in novo_html
    item = next(a for a in aplicados if a["indicador"] == "valor_estoque_total")
    assert item["valor_novo"] == "28.787"


def test_reporta_titulo_nao_encontrado_quando_card_falta_no_html():
    """O HTML sintético só tem 3 dos 14 cards automatizados — os outros 11
    devem ser reportados em `nao_encontrados`, sem derrubar o processamento
    dos que existem."""
    _, aplicados, nao_encontrados = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    assert len(aplicados) == 3
    assert "Itens MRP Saldo Zero" in nao_encontrados
    assert "Itens sem Endereço" in nao_encontrados
    assert len(nao_encontrados) == 11


def test_curva_abc_nao_e_mais_indicador_automatizado():
    """Curva ABC (#17) voltou a ser card manual — o card existe no HTML mas
    não deve ser tocado, mesmo estando presente e mesmo que um dict de
    indicadores traga outras 14 chaves preenchidas."""
    novo_html, aplicados, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    linha_curva_abc_original = "{ n:17, title:'Curva ABC',                  value:'30',    yesterday:'30',    deltaPct:0,    dir:'flat', color:'purple', icon:'abcBars', spark:[30,30] },"
    assert linha_curva_abc_original in novo_html
    assert not any(a["indicador"] == "curva_abc" for a in aplicados)
    assert not any(m[0] == "curva_abc" for m in html_writer.MAPEAMENTO_CARD)


def test_formata_inteiros_com_separador_de_milhar_br():
    assert html_writer.formatar_inteiro_br(5341) == "5.341"
    assert html_writer.formatar_inteiro_br(93) == "93"
    assert html_writer.formatar_inteiro_br(0) == "0"


def test_formata_valor_estoque_milhares_arredonda_pro_milhar_mais_proximo():
    assert html_writer.formatar_valor_estoque_milhares(24852474.12) == "24.852"
    assert html_writer.formatar_valor_estoque_milhares(28786943.43) == "28.787"


# ---- Comparação "ontem" nos 8 cards da MB51 -------------------------------

INDICADORES_COM_ONTEM = dict(
    INDICADORES,
    ontem={
        "linhas_atendidas_d009": 65,
        "linhas_atendidas_d016": 0,
        "recebimentos_d009": 35,
        "recebimentos_d016": 1,
        "estornos_d009": 0,
        "estornos_d016": 0,
        "inventario_rotativo_d009": 91,
        "inventario_rotativo_d016": 4,
    },
)


def test_com_ontem_atualiza_value_yesterday_deltapct_e_dir_juntos():
    novo_html, aplicados, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES_COM_ONTEM)
    # 140 vs 65 -> up, +115.4%
    assert "title:'Linhas Atendidas D009',    value:'140', yesterday:'65', deltaPct:115.4, dir:'up'" in novo_html
    item = next(a for a in aplicados if a["indicador"] == "linhas_atendidas_d009")
    assert item["valor_novo"] == "140"
    assert item["yesterday_novo"] == "65"
    assert item["dir_novo"] == "up"


def test_com_ontem_nao_toca_n_color_icon_spark_do_card():
    novo_html, _, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES_COM_ONTEM)
    assert "color:'green', icon:'trendUp', spark:[9,12] }," in novo_html
    assert "{ n:1, title:'Linhas Atendidas D009'" in novo_html


def test_sem_ontem_atualiza_so_value_do_card_mb51():
    """Se indicadores['ontem'] for None (arquivo só tinha uma data), os cards
    da MB51 recebem só o value novo — yesterday/deltaPct/dir ficam como
    estavam no mock, sem dado real pra comparar."""
    novo_html, aplicados, _ = html_writer.atualizar_html(HTML_SINTETICO, INDICADORES)
    assert "title:'Linhas Atendidas D009',    value:'140', yesterday:'18', deltaPct:16.7, dir:'up'" in novo_html
    item = next(a for a in aplicados if a["indicador"] == "linhas_atendidas_d009")
    assert "yesterday_novo" not in item


def test_calcular_delta_flat_quando_igual():
    assert html_writer.calcular_delta(65, 65) == ("flat", 0.0)


def test_calcular_delta_up_e_down():
    dir_, pct = html_writer.calcular_delta(90, 65)
    assert dir_ == "up"
    assert round(pct, 1) == 38.5

    dir_, pct = html_writer.calcular_delta(2, 35)
    assert dir_ == "down"
    assert round(pct, 1) == -94.3


def test_calcular_delta_crescimento_a_partir_de_zero_nao_quebra():
    dir_, pct = html_writer.calcular_delta(5, 0)
    assert dir_ == "up"
    assert pct == 100.0
