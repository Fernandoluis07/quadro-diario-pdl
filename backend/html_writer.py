"""Escreve os valores calculados dentro do index.html existente.

Importante: o index.html guarda os dados dos cards em arrays JS (BLOCK1,
BLOCK2, BLOCK3, LOOSE), cada card como `{ n:X, title:'...', value:'...',
yesterday:'...', deltaPct:N, dir:'...', color:'...', icon:'...', spark:[...] }`.
Para não arriscar tocar em estrutura/CSS/textos, a edição é uma substituição
de texto cirúrgica: localiza o `title:'TÍTULO EXATO'` de cada card
automatizado e troca só os campos relevantes daquele objeto. Nada mais no
arquivo é reescrito — `spark` (o gráfico de tendência) nunca é tocado, porque
só temos 2 pontos reais (hoje/ontem), não os 8 do mock.

Os 8 cards que vêm da MB51 (Linhas Atendidas, Estornos, Recebimentos,
Inventário Rotativo — D009/D016) também ganham `yesterday`/`deltaPct`/`dir`
reais, porque a MB51 tem histórico suficiente pra comparar hoje com ontem.
Os outros 6 (MB25/ZMM028) só têm o valor de hoje — essas fontes são
pendências/snapshot, sem uma leitura "de ontem" equivalente.
"""

from __future__ import annotations

import re


def formatar_inteiro_br(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def formatar_valor_estoque_milhares(valor: float) -> str:
    """Valor em milhares de reais, arredondado pro milhar mais próximo, sem
    decimais, ponto como separador de milhar (ex: 24.852.474,12 -> '24.852')."""
    milhares = round(valor / 1_000)
    return formatar_inteiro_br(milhares)


def calcular_delta(hoje: int, ontem: int) -> tuple[str, float]:
    """Retorna (dir, deltaPct) no mesmo formato usado pelo template do card."""
    if hoje == ontem:
        return "flat", 0.0
    if ontem == 0:
        # cresceu a partir de zero: percentual não é matematicamente definido
        # (divisão por zero). 100.0 é só um valor de referência pra não quebrar
        # o campo numérico do JS — não é uma % real.
        return "up", 100.0
    pct = (hoje - ontem) / ontem * 100
    return ("up" if pct > 0 else "down"), round(pct, 1)


# (chave no dict de indicadores, título EXATO do card no index.html, formatador)
# Curva ABC (#17) NÃO entra aqui — é card manual, não é tocado pelo Python.
# Os 8 cards da MB51 (com comparação "ontem") estão em MAPEAMENTO_CARD_COM_ONTEM.
MAPEAMENTO_CARD = [
    ("pendencias_atendimento_linhas", "Pendências Atendimento Linhas", formatar_inteiro_br),
    ("reservas_pendentes", "Reservas Pendentes", formatar_inteiro_br),
    ("itens_estoque_com_saldo", "Itens em Estoque com Saldo", formatar_inteiro_br),
    ("valor_estoque_total", "Valor do Estoque Total", formatar_valor_estoque_milhares),
    ("itens_mrp_saldo_zero", "Itens MRP Saldo Zero", formatar_inteiro_br),
    ("itens_sem_endereco", "Itens sem Endereço", formatar_inteiro_br),
]

# (chave no dict de indicadores == chave no dict "ontem", título EXATO do card, formatador)
MAPEAMENTO_CARD_COM_ONTEM = [
    ("linhas_atendidas_d009", "Linhas Atendidas D009", formatar_inteiro_br),
    ("linhas_atendidas_d016", "Linhas Atendidas D016", formatar_inteiro_br),
    ("recebimentos_d009", "Recebimentos D009", formatar_inteiro_br),
    ("recebimentos_d016", "Recebimentos D016", formatar_inteiro_br),
    ("estornos_d009", "Estornos D009", formatar_inteiro_br),
    ("estornos_d016", "Estornos D016", formatar_inteiro_br),
    ("inventario_rotativo_d009", "Inventário Rotativo D009", formatar_inteiro_br),
    ("inventario_rotativo_d016", "Inventário Rotativo D016", formatar_inteiro_br),
]

_PADRAO_VALUE = "(title:'{titulo}'\\s*,\\s*value:')([^']*)(')"
_PADRAO_VALUE_ONTEM_DELTA_DIR = (
    "(title:'{titulo}'\\s*,\\s*value:')([^']*)"
    "('\\s*,\\s*yesterday:')([^']*)"
    "('\\s*,\\s*deltaPct:)(-?[\\d.]+)"
    "(\\s*,\\s*dir:')([^']*)"
    "(')"
)


def _atualizar_somente_value(html: str, chave: str, titulo: str, formatador, indicadores: dict, aplicados: list, nao_encontrados: list) -> str:
    valor_formatado = formatador(indicadores[chave])
    padrao = re.compile(_PADRAO_VALUE.format(titulo=re.escape(titulo)))
    ocorrencias = list(padrao.finditer(html))
    if not ocorrencias:
        nao_encontrados.append(titulo)
        return html
    valor_anterior = ocorrencias[0].group(2)
    html = padrao.sub(lambda m: m.group(1) + valor_formatado + m.group(3), html)
    aplicados.append(
        {
            "indicador": chave,
            "card_titulo": titulo,
            "valor_anterior": valor_anterior,
            "valor_novo": valor_formatado,
            "ocorrencias_substituidas": len(ocorrencias),
        }
    )
    return html


def _atualizar_com_ontem(html: str, chave: str, titulo: str, formatador, indicadores: dict, ontem: dict, aplicados: list, nao_encontrados: list) -> str:
    hoje_valor = indicadores[chave]
    ontem_valor = ontem[chave]
    valor_formatado = formatador(hoje_valor)
    yesterday_formatado = formatador(ontem_valor)
    dir_novo, delta_pct_novo = calcular_delta(hoje_valor, ontem_valor)
    delta_pct_str = f"{delta_pct_novo:.1f}"

    padrao = re.compile(_PADRAO_VALUE_ONTEM_DELTA_DIR.format(titulo=re.escape(titulo)))
    ocorrencias = list(padrao.finditer(html))
    if not ocorrencias:
        nao_encontrados.append(titulo)
        return html

    m = ocorrencias[0]
    valor_anterior, yesterday_anterior, delta_anterior, dir_anterior = m.group(2), m.group(4), m.group(6), m.group(8)

    def _sub(mm):
        return (
            mm.group(1) + valor_formatado
            + mm.group(3) + yesterday_formatado
            + mm.group(5) + delta_pct_str
            + mm.group(7) + dir_novo
            + mm.group(9)
        )

    html = padrao.sub(_sub, html)
    aplicados.append(
        {
            "indicador": chave,
            "card_titulo": titulo,
            "valor_anterior": valor_anterior,
            "valor_novo": valor_formatado,
            "yesterday_anterior": yesterday_anterior,
            "yesterday_novo": yesterday_formatado,
            "deltaPct_anterior": delta_anterior,
            "deltaPct_novo": delta_pct_str,
            "dir_anterior": dir_anterior,
            "dir_novo": dir_novo,
            "ocorrencias_substituidas": len(ocorrencias),
        }
    )
    return html


def atualizar_html(html: str, indicadores: dict) -> tuple[str, list[dict], list[str]]:
    """Retorna (html_atualizado, mapeamentos_aplicados, titulos_nao_encontrados).

    Se `indicadores['ontem']` for None (arquivo só tinha uma data), os 8 cards
    da MB51 recebem só o `value` de hoje — yesterday/deltaPct/dir ficam como
    estavam, sem dado real pra comparar."""
    aplicados: list[dict] = []
    nao_encontrados: list[str] = []

    ontem = indicadores.get("ontem")
    for chave, titulo, formatador in MAPEAMENTO_CARD_COM_ONTEM:
        if ontem is not None:
            html = _atualizar_com_ontem(html, chave, titulo, formatador, indicadores, ontem, aplicados, nao_encontrados)
        else:
            html = _atualizar_somente_value(html, chave, titulo, formatador, indicadores, aplicados, nao_encontrados)

    for chave, titulo, formatador in MAPEAMENTO_CARD:
        html = _atualizar_somente_value(html, chave, titulo, formatador, indicadores, aplicados, nao_encontrados)

    return html, aplicados, nao_encontrados
