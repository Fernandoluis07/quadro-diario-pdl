r"""Congela um dia calculado pelo Cabeçalho: grava nos 5 JSON de histórico do repo
(historico_mb51.json, historico_manuais.json, historico_zmm028.json,
historico_mensal.json, historico_paineis.json) e atualiza o index.html na MESMA
passada — tanto os `value:'...'` dos cards do dia corrente quanto as constantes
`HISTORICO_*` embutidas e os painéis estáticos da tela Início (Pontos de Atenção /
Avisos Importantes / Datas Importantes).

historico_paineis.json/HISTORICO_PAINEIS é o único dos 5 que também alimenta a tela
Calendário (via `HISTORICO_PAINEIS[data]` no JS) — os outros 4 são só pros cards. Os
painéis da tela Início continuam vindo do HTML estático (atualizar_painel_*, abaixo),
sem depender dessa constante.

As duas cópias (JSON solto no repo + constante embutida no index.html) precisam
ficar sempre em sincronia: o index.html NÃO usa fetch() pra ler os JSON soltos (roda
como file:// e fetch() esbarra em CORS) — ele lê só a constante `const HISTORICO_X =
{...}` embutida direto no HTML. Editar um dos dois e esquecer o outro deixa o site
publicado mostrando dado velho mesmo com o JSON correto. Por isso este módulo grava
os dois a partir do MESMO dict em memória, nunca dois cálculos separados.

Um dia já presente em historico_mb51.json nunca é sobrescrito por padrão — levanta
DiaJaCongeladoError e não grava nada. `congelar_dia(..., forcar=True)` pula essa
trava e sobrescreve o dia; quem decide se `forcar` pode ser True é o chamador
(backend/cabecalho.py exige a senha de reprocessamento antes de passar forcar=True).
"""

from __future__ import annotations

import datetime
import html as html_lib
import json
import os
import re

from . import html_writer
from .planilha_manual import sem_acento_maiusculo

CAMPOS_MB51 = (
    "linhas_atendidas_d009",
    "linhas_atendidas_d016",
    "estornos_d009",
    "estornos_d016",
    "recebimentos_d009",
    "recebimentos_d016",
    "inventario_rotativo_d009",
    "inventario_rotativo_d016",
)

CAMPOS_ZMM028 = (
    "itens_estoque_com_saldo",
    "itens_mrp_saldo_zero",
    "valor_estoque_total",
    "itens_sem_endereco",
    # Gestão de Estoque — indicadores 1 e 2 (o denominador comum "% do valor VB"
    # entra aqui achatado também, pra o front-end não precisar recalcular por dia).
    "total_materiais_vb_d009",
    "materiais_abaixo_estoque_minimo_qtd",
    "materiais_abaixo_estoque_minimo_valor_total",
    "materiais_abaixo_estoque_minimo_pct_valor_vb",
    "materiais_acima_estoque_maximo_qtd",
    "materiais_acima_estoque_maximo_valor_total",
    "materiais_acima_estoque_maximo_pct_valor_vb",
    "materiais_nunca_movimentados_qtd",
    "materiais_nunca_movimentados_valor_total",
    "materiais_nunca_movimentados_pct_valor_vb",
    "materiais_nunca_movimentados_pct_distribuicao",
)

_STATUS_CLASSE = {
    "QUITADA": "done",
    "PROGRAMADA": "scheduled",
    "AGUARDANDO APROVACAO": "pending",
}

_MARCADOR_INICIO_SECAO_INICIO = '<section class="screen active" id="screen-inicio">'
_MARCADOR_FIM_SECAO_INICIO = '<!-- ===================== PLACEHOLDERS ===================== -->'


class DiaJaCongeladoError(Exception):
    """Levantado quando o dia pedido já está presente no histórico — congelar de novo
    sobrescreveria um dia fechado, o que nunca deve acontecer."""


# ---- Montagem das entradas de histórico (dict puro, sem IO) ----------------

def ja_congelado(historico_mb51: dict, data_iso: str) -> bool:
    return data_iso in historico_mb51


def montar_entrada_mb51(indicadores: dict, intercompany_manual: int) -> dict:
    entrada = {campo: indicadores[campo] for campo in CAMPOS_MB51}
    entrada["intercompany"] = intercompany_manual
    return entrada


def montar_entrada_manual(indicadores: dict, manual_hoje: dict) -> dict:
    """6 campos — mesmo schema de historico_manuais.json/HISTORICO_MANUAL. Os 4
    puramente manuais vêm da planilha; reservas_pendentes/pendencias_atendimento_linhas
    são automáticos (MB25, só dia corrente) e já estão em `indicadores`."""
    return {
        "notas_aguardando_lancamento": manual_hoje["notas_aguardando_lancamento"],
        "devolucao": manual_hoje["devolucao"],
        "scanner_documentos": manual_hoje["scanner_documentos"],
        "nf_pendente_faturamento": manual_hoje["nf_pendente_faturamento"],
        "reservas_pendentes": indicadores["reservas_pendentes"],
        "pendencias_atendimento_linhas": indicadores["pendencias_atendimento_linhas"],
    }


def montar_entrada_zmm028(indicadores: dict) -> dict:
    return {campo: indicadores[campo] for campo in CAMPOS_ZMM028}


def _classe_status(status: str) -> str:
    return _STATUS_CLASSE.get(sem_acento_maiusculo(status), "scheduled")


def _formatar_periodo(inicio: datetime.date, fim: datetime.date, duracao_dias: int | None) -> str:
    texto = f"{inicio:%d/%m/%y} a {fim:%d/%m/%y}"
    if duracao_dias is not None:
        texto += f" · {duracao_dias} dias"
    return texto


def _serializar_data_importante(registro: dict) -> dict:
    """Mesmo formato que o front-end já consome de PAINEIS_REAIS/HISTORICO_PAINEIS:
    'name'/'period' sempre presentes, 'statusLabel'/'statusClasse' OMITIDOS quando o
    Status da planilha está vazio (não inventa status pra quem não tem — ver Milton
    Junior no congelamento retroativo original)."""
    entrada = {
        "name": registro["nome"],
        "period": _formatar_periodo(registro["periodo_inicio"], registro["periodo_fim"], registro["duracao_dias"]),
    }
    if registro["status"]:
        entrada["statusLabel"] = registro["status"]
        entrada["statusClasse"] = _classe_status(registro["status"])
    return entrada


def montar_entrada_paineis(pontos_atencao: list[str], avisos_importantes: list[str], datas_importantes: list[dict]) -> dict:
    """Snapshot do dia pros 3 painéis que a tela Calendário mostra pra data selecionada
    — mesmo schema de HISTORICO_PAINEIS/PAINEIS_REAIS no index.html."""
    return {
        "pontos_atencao": list(pontos_atencao),
        "avisos_importantes": list(avisos_importantes),
        "datas_importantes": [_serializar_data_importante(r) for r in datas_importantes],
    }


def atualizar_historico_mensal(historico_mensal: dict, resumo_mes_novo: dict) -> dict:
    """Agregado mensal é sempre substituído pelo mês recalculado (não é congelamento
    diário — é um total corrente do mês, esperado mudar a cada dia até o mês fechar)."""
    return {**historico_mensal, **resumo_mes_novo}


# ---- JSON soltos no repo -----------------------------------------------------

def _carregar_json(caminho: str) -> dict:
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _salvar_json(caminho: str, dados: dict) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(dados.items())), f, ensure_ascii=False, indent=2)


# ---- Constantes HISTORICO_* embutidas no index.html --------------------------

def atualizar_constante_historico_js(html: str, nome_const: str, historico: dict) -> str:
    """Substitui `const NOME = {...};` (uma linha só) pelo dict serializado. Greedy até
    o ÚLTIMO '};' da linha — JSON não tem ';' solto, então só existe um '};' possível
    fechando o statement, mesmo com objetos aninhados dentro do JSON."""
    padrao = re.compile(r"(const " + re.escape(nome_const) + r" = )(\{.*\})(;)")
    novo_valor = json.dumps(dict(sorted(historico.items())), ensure_ascii=False, separators=(",", ":"))
    novo_html, n = padrao.subn(lambda m: m.group(1) + novo_valor + m.group(3), html, count=1)
    if n == 0:
        raise ValueError(f"Constante '{nome_const}' não encontrada no index.html.")
    return novo_html


# ---- Painéis estáticos da tela Início -----------------------------------------

def _dividir_secao_inicio(html: str) -> tuple[str, str, str]:
    try:
        i0 = html.index(_MARCADOR_INICIO_SECAO_INICIO)
        i1 = html.index(_MARCADOR_FIM_SECAO_INICIO, i0)
    except ValueError as e:
        raise ValueError("Não encontrei os marcadores da seção Início no index.html.") from e
    return html[:i0], html[i0:i1], html[i1:]


def _escapar(texto: str) -> str:
    return html_lib.escape(texto, quote=False)


def _substituir_ul_bullet(secao: str, ancora_classe_painel: str, itens: list[str]) -> str:
    """Troca o conteúdo do <ul class="bullet-list"> (sem id — só existe na tela
    Início; a tela Calendário usa id="calAttentionList"/"calNoticeList" pro mesmo
    par de painéis e não deve ser tocada aqui) que vem logo após o painel indicado."""
    idx_ancora = secao.index(ancora_classe_painel)
    marcador_ul = '<ul class="bullet-list">'
    idx_ul_abre = secao.index(marcador_ul, idx_ancora)
    idx_conteudo_ini = idx_ul_abre + len(marcador_ul)
    idx_ul_fecha = secao.index("</ul>", idx_conteudo_ini)

    novo_conteudo = "\n" + "".join(f"            <li>{_escapar(item)}</li>\n" for item in itens) + "          "
    return secao[:idx_conteudo_ini] + novo_conteudo + secao[idx_ul_fecha:]


def atualizar_painel_pontos_avisos(html: str, pontos_atencao: list[str], avisos_importantes: list[str]) -> str:
    antes, secao, depois = _dividir_secao_inicio(html)
    secao = _substituir_ul_bullet(secao, 'class="panel p-alert"', pontos_atencao)
    secao = _substituir_ul_bullet(secao, 'class="panel p-notice"', avisos_importantes)
    return antes + secao + depois


def _linha_vacation(registro: dict) -> str:
    classe = _classe_status(registro["status"])
    periodo = _formatar_periodo(registro["periodo_inicio"], registro["periodo_fim"], registro["duracao_dias"])
    nome = _escapar(registro["nome"])
    status_label = _escapar(registro["status"])
    return (
        '            <div class="vacation-row">\n'
        f'              <div class="vacation-row-top"><span class="name">{nome}</span>'
        f'<span class="vacation-status vacation-status--{classe}">{status_label}</span></div>\n'
        f'              <span class="period">{periodo}</span>\n'
        "            </div>\n"
    )


def atualizar_painel_datas_importantes(html: str, registros: list[dict]) -> str:
    antes, secao, depois = _dividir_secao_inicio(html)

    marcador_div = '<div class="bullet-list vacation-list">'
    idx_div_abre = secao.index(marcador_div)
    idx_conteudo_ini = idx_div_abre + len(marcador_div)
    # fecho do vacation-list é indentado com 10 espaços; cada vacation-row fecha com
    # 12 — a string de busca com 10 espaços exatos não bate com a de 12, então acha
    # certo mesmo com linhas dentro.
    idx_fecha = secao.index("\n          </div>", idx_conteudo_ini)

    novo_conteudo = "\n" + "".join(_linha_vacation(r) for r in registros)
    secao = secao[:idx_conteudo_ini] + novo_conteudo + secao[idx_fecha:]
    return antes + secao + depois


# ---- Orquestração completa -----------------------------------------------------

def congelar_dia(
    *,
    repo_root: str,
    index_path: str,
    data_ref: datetime.date,
    indicadores: dict,
    manual_hoje: dict,
    pontos_atencao: list[str],
    avisos_importantes: list[str],
    datas_importantes: list[dict],
    resumo_mes: dict,
    forcar: bool = False,
) -> dict:
    data_iso = data_ref.isoformat()

    caminho_mb51_json = os.path.join(repo_root, "historico_mb51.json")
    caminho_manuais_json = os.path.join(repo_root, "historico_manuais.json")
    caminho_zmm028_json = os.path.join(repo_root, "historico_zmm028.json")
    caminho_mensal_json = os.path.join(repo_root, "historico_mensal.json")
    caminho_paineis_json = os.path.join(repo_root, "historico_paineis.json")

    historico_mb51 = _carregar_json(caminho_mb51_json)
    historico_manuais = _carregar_json(caminho_manuais_json)
    historico_zmm028 = _carregar_json(caminho_zmm028_json)
    historico_mensal = _carregar_json(caminho_mensal_json)
    historico_paineis = _carregar_json(caminho_paineis_json)

    if ja_congelado(historico_mb51, data_iso) and not forcar:
        raise DiaJaCongeladoError(f"O dia {data_iso} já tinha sido congelado antes — nada foi alterado.")

    intercompany_manual = manual_hoje["intercompany"]

    entrada_mb51 = montar_entrada_mb51(indicadores, intercompany_manual)
    entrada_manual = montar_entrada_manual(indicadores, manual_hoje)
    entrada_zmm028 = montar_entrada_zmm028(indicadores)
    entrada_paineis = montar_entrada_paineis(pontos_atencao, avisos_importantes, datas_importantes)

    data_ontem_iso = indicadores.get("data_referencia_ontem")
    ontem_manual = historico_manuais.get(data_ontem_iso) if data_ontem_iso else None
    entrada_mb51_ontem = historico_mb51.get(data_ontem_iso) if data_ontem_iso else None
    ontem_intercompany = {"intercompany": entrada_mb51_ontem["intercompany"]} if entrada_mb51_ontem else None

    historico_mb51 = {**historico_mb51, data_iso: entrada_mb51}
    historico_manuais = {**historico_manuais, data_iso: entrada_manual}
    historico_zmm028 = {**historico_zmm028, data_iso: entrada_zmm028}
    historico_mensal = atualizar_historico_mensal(historico_mensal, resumo_mes)
    historico_paineis = {**historico_paineis, data_iso: entrada_paineis}

    _salvar_json(caminho_mb51_json, historico_mb51)
    _salvar_json(caminho_manuais_json, historico_manuais)
    _salvar_json(caminho_zmm028_json, historico_zmm028)
    _salvar_json(caminho_mensal_json, historico_mensal)
    _salvar_json(caminho_paineis_json, historico_paineis)

    with open(index_path, "r", encoding="utf-8") as f:
        html_atual = f.read()

    indicadores_para_cards = dict(indicadores)
    indicadores_para_cards["notas_aguardando_lancamento"] = manual_hoje["notas_aguardando_lancamento"]
    indicadores_para_cards["nf_pendente_faturamento"] = manual_hoje["nf_pendente_faturamento"]
    indicadores_para_cards["devolucao"] = manual_hoje["devolucao"]
    indicadores_para_cards["scanner_documentos"] = manual_hoje["scanner_documentos"]
    indicadores_para_cards["intercompany"] = intercompany_manual
    if ontem_manual is not None:
        indicadores_para_cards["ontem_manual"] = ontem_manual
    if ontem_intercompany is not None:
        indicadores_para_cards["ontem_intercompany"] = ontem_intercompany

    html_novo, aplicados, nao_encontrados = html_writer.atualizar_html(html_atual, indicadores_para_cards)

    html_novo = atualizar_constante_historico_js(html_novo, "HISTORICO_MB51", historico_mb51)
    html_novo = atualizar_constante_historico_js(html_novo, "HISTORICO_MANUAL", historico_manuais)
    html_novo = atualizar_constante_historico_js(html_novo, "HISTORICO_ZMM028", historico_zmm028)
    html_novo = atualizar_constante_historico_js(html_novo, "HISTORICO_MENSAL", historico_mensal)
    html_novo = atualizar_constante_historico_js(html_novo, "HISTORICO_PAINEIS", historico_paineis)

    # Checklist de Reservas: fotografia atual (MB25 x ZMM028), não é histórico por
    # data — não tem historico_*.json próprio, só vive nesta constante embutida,
    # sempre sobrescrita a cada congelamento (mesmo raciocínio do comentário no
    # topo do arquivo pra HISTORICO_PAINEIS vs painéis estáticos da tela Início).
    html_novo = atualizar_constante_historico_js(
        html_novo, "CHECKLIST_RESERVAS", {"rows": indicadores["checklist_reservas"]}
    )

    # Classificação de MRP (indicador 5, Gestão de Estoque): mesma lógica de
    # "fotografia atual, sem histórico por data" do CHECKLIST_RESERVAS acima —
    # sempre sobrescrita a cada congelamento.
    html_novo = atualizar_constante_historico_js(
        html_novo, "CLASSIFICACAO_MRP", indicadores["classificacao_mrp"]
    )

    # Listas detalhadas dos indicadores 1/2/4 (Gestão de Estoque) — usadas só pra
    # exportação (planilha com a lista completa de materiais), mesma lógica de
    # "fotografia atual" do CHECKLIST_RESERVAS/CLASSIFICACAO_MRP: não entram no
    # historico_zmm028.json (só os campos achatados de CAMPOS_ZMM028 acima entram
    # lá, pro gráfico de tendência) — a lista em si não tem valor histórico, e
    # guardá-la dia a dia inflaria o JSON à toa.
    html_novo = atualizar_constante_historico_js(
        html_novo, "MATERIAIS_ABAIXO_MINIMO", {"itens": indicadores["materiais_abaixo_estoque_minimo_itens"]}
    )
    html_novo = atualizar_constante_historico_js(
        html_novo, "MATERIAIS_ACIMA_MAXIMO", {"itens": indicadores["materiais_acima_estoque_maximo_itens"]}
    )
    html_novo = atualizar_constante_historico_js(
        html_novo, "MATERIAIS_NUNCA_MOVIMENTADOS", {"itens": indicadores["materiais_nunca_movimentados_itens"]}
    )

    html_novo = atualizar_painel_pontos_avisos(html_novo, pontos_atencao, avisos_importantes)
    html_novo = atualizar_painel_datas_importantes(html_novo, datas_importantes)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_novo)

    return {
        "data": data_iso,
        "cards_atualizados": aplicados,
        "cards_nao_encontrados": nao_encontrados,
        "arquivos_json_atualizados": [
            caminho_mb51_json, caminho_manuais_json, caminho_zmm028_json, caminho_mensal_json, caminho_paineis_json,
        ],
        "index_html_atualizado": index_path,
    }
