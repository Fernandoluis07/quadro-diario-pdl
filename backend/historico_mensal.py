r"""Agregados MENSAIS pro Resumo do Mês (fixo em D009) e pro Comparativo Mensal (chave
"comparativo" de cada mês, D009 e D016 separados — ver comparativo_deposito).

Diferente de historico.py/historico_manuais.py/historico_zmm028.py (todos diários), este módulo
agrega por mês inteiro. Existe porque boa parte do Resumo do Mês não dá pra derivar do que já
está congelado por dia (HISTORICO_MB51 no index.html só tem CONTAGEM, não valor em R$, e não tem
Ordem/Centro custo nenhum) — precisa voltar na linha crua da MB51:

- Valor Total Atendido/Recebido/Estornado (R$) — soma de "Montante em MI", não existe nos JSONs
  diários (que só contam linha).
- Atendimento em 5 grupos por tipo de movimento (Reservas 201, Ordens 261, Intercompany 601,
  Transferências 833, Diversos = o resto, ver quebra_atendimento) — até 2026-09-27 eram 3
  (Reservas = Centro custo preenchido, Ordens = Ordem preenchida, Outros = nenhum dos dois); na
  MB51 inteira isso dava exatamente 201 e 261, então Reservas/Ordens não mudaram de número.
- Top 5 Centro de Custo — depende da coluna "Centro custo", que os agregados diários nunca leram.
- Notas Recebidas — dedup de Referência no MÊS INTEIRO (não é a soma de dedups diários, que
  daria um número diferente se a mesma nota aparecesse em mais de um dia).

O Bloco 3 (Inventário Rotativo do mês) É a soma da contagem diária — reaproveita
indicadores.inventario_rotativo() dia a dia, em vez de reimplementar a lógica.

O Bloco 5 (gráfico "SKUs Zerados por Dia") NÃO entra aqui: já tem granularidade diária em
HISTORICO_ZMM028 (embutido no index.html) — o front-end só filtra pro mês selecionado.

Uso:
    python -m backend.historico_mensal --data-inicio 01/04/2026 --arquivo-mb51 "C:\caminho\MB51.xlsx"
"""

from __future__ import annotations

import argparse
import datetime
import json
import os

import pandas as pd

from . import config, extratos, indicadores

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA_PADRAO = os.path.join(REPO_ROOT, "historico_mensal.json")


def _preenchido(serie: pd.Series) -> pd.Series:
    """Vazio = NaN, string vazia após strip, ou literalmente 'nan' — mesmo critério
    já usado em indicadores.itens_sem_endereco() pra Pos.dpst."""
    s = serie.astype(str).str.strip()
    return serie.notna() & ~s.eq("") & ~s.eq("nan")


def _soma_valor(df: pd.DataFrame) -> float:
    return round(float(pd.to_numeric(df["Montante em MI"], errors="coerce").fillna(0).sum()), 2)


def quebra_atendimento(df_atend: pd.DataFrame) -> dict[str, int]:
    """Linhas de atendimento do mês em 5 grupos por tipo de movimento (ver config.BWART_RESUMO_*).
    Diversos é por exclusão, então os 5 sempre somam len(df_atend). Atendimento estornado NÃO é
    descontado — saiu, é atendimento; o estorno conta à parte, no card de Estorno."""
    bwart = df_atend["_bwart_norm"]
    reservas = int(bwart.isin(config.BWART_RESUMO_RESERVAS).sum())
    ordens = int(bwart.isin(config.BWART_RESUMO_ORDENS).sum())
    intercompany = int(bwart.isin(config.BWART_RESUMO_INTERCOMPANY).sum())
    transferencias = int(bwart.isin(config.BWART_RESUMO_TRANSFERENCIAS).sum())
    return {
        "reservas_mes": reservas,
        "ordens_mes": ordens,
        "intercompany_mes": intercompany,
        "transferencias_mes": transferencias,
        "diversos_mes": len(df_atend) - reservas - ordens - intercompany - transferencias,
    }


def _ultimo_dia_do_mes(ano: int, mes: int) -> datetime.date:
    if mes == 12:
        return datetime.date(ano, 12, 31)
    return datetime.date(ano, mes + 1, 1) - datetime.timedelta(days=1)


def _meses_no_periodo(data_inicio: datetime.date, data_fim: datetime.date) -> list[tuple[int, int]]:
    meses = []
    ano, mes = data_inicio.year, data_inicio.month
    while (ano, mes) <= (data_fim.year, data_fim.month):
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
    return meses


DEPOSITOS_COMPARATIVO = (config.DEPOSITO_D009, config.DEPOSITO_D016)


def _valor_abs(df: pd.DataFrame) -> float:
    return round(float(pd.to_numeric(df["Montante em MI"], errors="coerce").fillna(0).abs().sum()), 2)


def comparativo_deposito(
    df_mb51: pd.DataFrame, deposito: str, inicio_mes: datetime.date, fim_mes: datetime.date
) -> dict:
    """Os 7 números do Comparativo Mensal pra UM depósito, com EXATAMENTE a lógica do Resumo
    do Mês (_calcular_mes, que é fixo em D009) — só troca o depósito. Pra D009 os totais batem
    1:1 com as chaves do Resumo (conferido 2026-09-29 nos 6 meses de abril a setembro).
    Valor atendido sai em módulo (o card mostra positivo; o Resumo guarda negativo e aplica
    abs na tela). `diario`: uma lista por indicador, um valor por dia corrido de inicio_mes a
    fim_mes (fim de semana incluso, normalmente 0) — é a linha "evolução dia a dia" do card.
    Notas por dia é o dedup do dia; somar os dias pode dar diferente do total do mês (a
    mesma nota em 2 dias conta nos 2), e é por isso que o total vem calculado à parte."""
    df_dep = df_mb51.loc[df_mb51["_deposito_norm"] == deposito]
    df_mes = df_dep.loc[(df_dep["_data_norm"] >= inicio_mes) & (df_dep["_data_norm"] <= fim_mes)]

    def recortes(df):
        return (
            df.loc[df["_bwart_norm"].isin(config.BWART_ATENDIMENTO)],
            df.loc[df["_bwart_norm"].isin(config.BWART_RECEBIMENTO)],
            df.loc[df["_bwart_norm"].isin(config.BWART_ESTORNO)],
        )

    atend, receb, estorno = recortes(df_mes)
    diario = {chave: [] for chave in (
        "linhas_atendidas", "notas_recebidas", "estornos_qtd", "inventario_rotativo",
        "valor_atendido", "valor_estornado", "valor_recebido",
    )}
    dia, um_dia = inicio_mes, datetime.timedelta(days=1)
    inventario_total = 0
    while dia <= fim_mes:
        df_dia = df_mes.loc[df_mes["_data_norm"] == dia]
        a, r, e = recortes(df_dia)
        inv = int(df_dia["Material"].nunique())  # = indicadores.inventario_rotativo, sem refiltrar a MB51 inteira
        inventario_total += inv
        diario["linhas_atendidas"].append(len(a))
        diario["notas_recebidas"].append(len(indicadores.referencias_recebidas(df_dia)))
        diario["estornos_qtd"].append(len(e))
        diario["inventario_rotativo"].append(inv)
        diario["valor_atendido"].append(abs(_soma_valor(a)))
        diario["valor_estornado"].append(_valor_abs(e))
        diario["valor_recebido"].append(_soma_valor(r))
        dia += um_dia

    return {
        "linhas_atendidas": len(atend),
        "notas_recebidas": len(indicadores.referencias_recebidas(df_mes)),
        "estornos_qtd": len(estorno),
        "inventario_rotativo": inventario_total,
        "valor_atendido": abs(_soma_valor(atend)),
        "valor_estornado": _valor_abs(estorno),
        "valor_recebido": _soma_valor(receb),
        "diario": diario,
    }


def _calcular_mes(
    df_mb51: pd.DataFrame, ano: int, mes: int, data_inicio: datetime.date, data_fim: datetime.date
) -> dict:
    inicio_mes = max(datetime.date(ano, mes, 1), data_inicio)
    fim_mes = min(_ultimo_dia_do_mes(ano, mes), data_fim)

    df_d009 = df_mb51.loc[df_mb51["_deposito_norm"] == config.DEPOSITO_D009]
    df_mes = df_d009.loc[(df_d009["_data_norm"] >= inicio_mes) & (df_d009["_data_norm"] <= fim_mes)]

    # ---- Bloco 1: Atendimento ----
    df_atend = df_mes.loc[df_mes["_bwart_norm"].isin(config.BWART_ATENDIMENTO)]
    grupos = quebra_atendimento(df_atend)
    centro_preenchido = df_atend.loc[_preenchido(df_atend["Centro custo"]), "Centro custo"].astype(str).str.strip()
    top5_centro_custo = [
        {"centro_custo": centro, "qtd": int(qtd)} for centro, qtd in centro_preenchido.value_counts().head(5).items()
    ]

    # ---- Bloco 2: Recebimento ----
    df_receb = df_mes.loc[df_mes["_bwart_norm"].isin(config.BWART_RECEBIMENTO)]

    # ---- Bloco 3: Inventário Rotativo (soma da contagem diária) ----
    inventario_rotativo_mes = 0
    dia, um_dia = inicio_mes, datetime.timedelta(days=1)
    while dia <= fim_mes:
        inventario_rotativo_mes += indicadores.inventario_rotativo(df_mb51, config.DEPOSITO_D009, dia)
        dia += um_dia

    # ---- Bloco 4: Estorno ----
    df_estorno = df_mes.loc[df_mes["_bwart_norm"].isin(config.BWART_ESTORNO)]

    return {
        "linhas_atendidas_mes": len(df_atend),
        "valor_atendido_mes": _soma_valor(df_atend),
        **grupos,
        "top5_centro_custo": top5_centro_custo,
        "notas_recebidas_mes": len(indicadores.referencias_recebidas(df_mes)),
        "valor_recebido_mes": _soma_valor(df_receb),
        "inventario_rotativo_mes": inventario_rotativo_mes,
        "estornos_qtd_mes": len(df_estorno),
        # valor ABSOLUTO: 202/222/262/602/834/123 vêm positivos e o 102 (estorno de recebimento,
        # 2026-09-28) vem sempre negativo — somar com sinal fazia um descontar o outro
        "estornos_valor_mes": round(float(pd.to_numeric(df_estorno["Montante em MI"], errors="coerce").fillna(0).abs().sum()), 2),
        # Comparativo Mensal: mesmos números, separados por depósito (ver comparativo_deposito)
        "comparativo": {dep: comparativo_deposito(df_mb51, dep, inicio_mes, fim_mes) for dep in DEPOSITOS_COMPARATIVO},
    }


def calcular_historico_mensal(
    data_inicio: datetime.date,
    data_fim: datetime.date | None = None,
    bases_dir: str | None = None,
    arquivo_mb51: str | None = None,
    df_mb51: pd.DataFrame | None = None,
) -> dict[str, dict]:
    """`df_mb51`: opcional — passa a MB51 já carregada em memória (ver
    backend/cabecalho.py) pra não reler o arquivo do disco. `main.calcular_todos_indicadores`
    já carrega a MB51 pra calcular os outros indicadores do dia — sem isso, esse módulo
    lia o MESMO arquivo (5,8MB/83 mil linhas) do zero de novo, ~40s à toa por execução."""
    if df_mb51 is not None:
        mb51 = df_mb51
    else:
        caminho_mb51 = arquivo_mb51 or os.path.join(bases_dir or config.BASES_DIR, config.MB51_FILENAME)
        mb51 = extratos.carregar_mb51(caminho_mb51)

    if data_fim is None:
        datas = extratos.datas_disponiveis(mb51)
        if not datas:
            raise ValueError(
                "MB51 não tem nenhuma data válida em 'Data de lançamento' — "
                "não dá pra detectar o fim do intervalo automaticamente, informe --data-fim."
            )
        data_fim = datas[0]

    if data_fim < data_inicio:
        raise ValueError(f"data_fim ({data_fim}) é anterior a data_inicio ({data_inicio}).")

    resultado: dict[str, dict] = {}
    for ano, mes in _meses_no_periodo(data_inicio, data_fim):
        resultado[f"{ano:04d}-{mes:02d}"] = _calcular_mes(mb51, ano, mes, data_inicio, data_fim)
    return resultado


def _parse_data(valor: str) -> datetime.date:
    return datetime.datetime.strptime(valor, "%d/%m/%Y").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agregados mensais do Resumo do Mês (fixo em D009)")
    parser.add_argument("--bases-dir", default=None)
    parser.add_argument("--arquivo-mb51", default=None, help='Caminho direto pro .xlsx (ex: cópia local) — ignora --bases-dir')
    parser.add_argument("--data-inicio", required=True, help="dd/mm/aaaa")
    parser.add_argument("--data-fim", default=None, help="dd/mm/aaaa (padrão: data mais recente disponível na MB51)")
    parser.add_argument("--saida", default=SAIDA_PADRAO, help=f"Caminho do JSON de saída (padrão: {SAIDA_PADRAO})")
    args = parser.parse_args()

    data_inicio = _parse_data(args.data_inicio)
    data_fim = _parse_data(args.data_fim) if args.data_fim else None

    resultado = calcular_historico_mensal(
        data_inicio, data_fim, bases_dir=args.bases_dir, arquivo_mb51=args.arquivo_mb51
    )

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    meses = sorted(resultado)
    print(f"Histórico mensal gerado: {len(resultado)} meses ({meses[0]} a {meses[-1]}) -> {args.saida}")


if __name__ == "__main__":
    main()
