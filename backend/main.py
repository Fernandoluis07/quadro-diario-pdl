"""Ponto de entrada: lê as 3 extrações, calcula os 14 indicadores e imprime o
resultado em JSON — etapa de validação antes de gerar o index.html.

'Hoje' NÃO é a data do sistema operacional: a MB51 costuma ser extraída de
manhã e só reflete até o dia anterior, então 'hoje' é a data mais recente
presente na própria coluna 'Data de lançamento' da MB51. 'Ontem' é a segunda
data mais recente presente no arquivo — usada para o comparativo dos 8
indicadores do Bloco 1 (Linhas Atendidas, Estornos, Recebimentos, Inventário
Rotativo, D009 e D016).

Uso:
    python -m backend.main
    python -m backend.main --data 05/08/2026 --bases-dir "C:\\caminho\\Bases"
"""

from __future__ import annotations

import argparse
import datetime
import json
import os

import pandas as pd

from . import config, extratos, indicadores

_CHAVES_BLOCO1 = (
    "linhas_atendidas_d009",
    "linhas_atendidas_d016",
    "estornos_d009",
    "estornos_d016",
    "recebimentos_d009",
    "recebimentos_d016",
    "inventario_rotativo_d009",
    "inventario_rotativo_d016",
)


def _detectar_hoje_ontem(
    df_mb51,
    data_forcada: datetime.date | None,
) -> tuple[datetime.date, datetime.date | None]:
    """Se `data_forcada` vier do --data, ela vira 'hoje' e 'ontem' é a data
    presente no arquivo mais recente anterior a ela. Sem `data_forcada`,
    'hoje' é a data mais recente do arquivo e 'ontem' a segunda mais recente."""
    datas = extratos.datas_disponiveis(df_mb51)

    if data_forcada is not None:
        anteriores = [d for d in datas if d < data_forcada]
        ontem = anteriores[0] if anteriores else None
        return data_forcada, ontem

    if not datas:
        raise ValueError(
            "MB51 não tem nenhuma data válida em 'Data de lançamento' "
            "após remover linhas de rodapé — não dá pra detectar 'hoje' automaticamente."
        )
    hoje = datas[0]
    ontem = datas[1] if len(datas) > 1 else None
    return hoje, ontem


def _calcular_bloco1(df_mb51, data: datetime.date) -> dict:
    return {
        "linhas_atendidas_d009": indicadores.linhas_atendidas(df_mb51, config.DEPOSITO_D009, data),
        "linhas_atendidas_d016": indicadores.linhas_atendidas(df_mb51, config.DEPOSITO_D016, data),
        "estornos_d009": indicadores.estornos(df_mb51, config.DEPOSITO_D009, data),
        "estornos_d016": indicadores.estornos(df_mb51, config.DEPOSITO_D016, data),
        "recebimentos_d009": indicadores.recebimentos(df_mb51, config.DEPOSITO_D009, data),
        "recebimentos_d016": indicadores.recebimentos(df_mb51, config.DEPOSITO_D016, data),
        "inventario_rotativo_d009": indicadores.inventario_rotativo(df_mb51, config.DEPOSITO_D009, data),
        "inventario_rotativo_d016": indicadores.inventario_rotativo(df_mb51, config.DEPOSITO_D016, data),
    }


def calcular_todos_indicadores(
    bases_dir: str | None = None,
    data_ref: datetime.date | None = None,
    df_mb51: pd.DataFrame | None = None,
) -> dict:
    """`df_mb51`: opcional — passa a MB51 já carregada em memória (ver
    backend/cabecalho.py) pra não reler o arquivo do disco (~40s numa MB51 de 5,8MB/
    83 mil linhas, sobre a rede). Sem isso, carrega do zero como sempre (uso normal:
    CLI standalone, testes)."""
    bases_dir = bases_dir or config.BASES_DIR

    mb51 = df_mb51 if df_mb51 is not None else extratos.carregar_mb51(os.path.join(bases_dir, config.MB51_FILENAME))
    mb25 = extratos.carregar_mb25(os.path.join(bases_dir, config.MB25_FILENAME))
    # Lê a ZMM028 do disco UMA VEZ só (~780KB/12,5 mil linhas, ~5s de leitura sobre a
    # rede) e deriva a versão D009 EM MEMÓRIA (instantâneo) — antes disso, carregar_zmm028
    # e carregar_zmm028_todos_depositos liam o mesmo arquivo duas vezes, ~5s à toa em
    # toda execução do Cabeçalho (ver extratos.filtrar_zmm028_d009).
    zmm028_todos_depositos = extratos.carregar_zmm028_todos_depositos(os.path.join(bases_dir, config.ZMM028_FILENAME))
    zmm028 = extratos.filtrar_zmm028_d009(zmm028_todos_depositos)
    # MM60 é preço de REFERÊNCIA (atualizado esporadicamente por quem administra o
    # Almoxarifado) — mora fixo dentro do repo (config.MM60_DIR), independente de
    # `bases_dir`/--bases-dir, que só vale pras 3 planilhas trocadas todo dia.
    mm60 = extratos.carregar_mm60(os.path.join(config.MM60_DIR, config.MM60_FILENAME))

    hoje, ontem = _detectar_hoje_ontem(mb51, data_ref)

    # Gestão de Estoque — indicadores 1 e 2 dividem o mesmo denominador (qtd/valor
    # dos materiais VB em D009), calculado uma única vez aqui.
    qtd_total_vb, valor_total_vb = indicadores.resumo_vb(zmm028)
    abaixo_minimo = indicadores.materiais_abaixo_estoque_minimo(zmm028, mm60, valor_total_vb)
    acima_maximo = indicadores.materiais_acima_estoque_maximo(zmm028, mm60, valor_total_vb)
    nunca_movimentados = indicadores.materiais_nunca_movimentados(
        zmm028, mb51, mm60, valor_total_vb, qtd_total_vb, hoje
    )

    resultado = {
        "data_referencia": hoje.isoformat(),
        "data_referencia_ontem": ontem.isoformat() if ontem else None,
        **_calcular_bloco1(mb51, hoje),
        "pendencias_atendimento_linhas": indicadores.pendencias_atendimento_linhas(mb25),
        "reservas_pendentes": indicadores.reservas_pendentes(mb25),
        "itens_estoque_com_saldo": indicadores.itens_estoque_com_saldo(zmm028),
        "valor_estoque_total": indicadores.valor_estoque_total(zmm028),
        "itens_mrp_saldo_zero": indicadores.itens_mrp_saldo_zero(zmm028),
        "itens_sem_endereco": indicadores.itens_sem_endereco(zmm028),
        "checklist_reservas": indicadores.montar_checklist_reservas(mb25, zmm028),
        "total_materiais_vb_d009": qtd_total_vb,
        "materiais_abaixo_estoque_minimo_qtd": abaixo_minimo["qtd"],
        "materiais_abaixo_estoque_minimo_valor_total": abaixo_minimo["valor_total"],
        "materiais_abaixo_estoque_minimo_pct_valor_vb": abaixo_minimo["pct_valor_vb"],
        "materiais_acima_estoque_maximo_qtd": acima_maximo["qtd"],
        "materiais_acima_estoque_maximo_valor_total": acima_maximo["valor_total"],
        "materiais_acima_estoque_maximo_pct_valor_vb": acima_maximo["pct_valor_vb"],
        "materiais_abaixo_estoque_minimo_itens": abaixo_minimo["itens"],
        "materiais_acima_estoque_maximo_itens": acima_maximo["itens"],
        "materiais_nunca_movimentados_qtd": nunca_movimentados["qtd"],
        "materiais_nunca_movimentados_valor_total": nunca_movimentados["valor_total"],
        "materiais_nunca_movimentados_pct_valor_vb": nunca_movimentados["pct_valor_vb"],
        "materiais_nunca_movimentados_pct_distribuicao": nunca_movimentados["pct_distribuicao"],
        "materiais_nunca_movimentados_itens": nunca_movimentados["itens"],
        "classificacao_mrp": indicadores.classificacao_mrp(zmm028_todos_depositos),
        "materiais_vb_sem_preco_mm60": indicadores.materiais_vb_sem_preco_mm60(zmm028, mm60),
        "ontem": _calcular_bloco1(mb51, ontem) if ontem else None,
    }
    return resultado


def _parse_data(valor: str) -> datetime.date:
    return datetime.datetime.strptime(valor, "%d/%m/%Y").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula os indicadores do Quadro Diário PDL")
    parser.add_argument("--bases-dir", default=None, help="Pasta com mb51.xlsx, mb25.xlsx, ZMM028.xlsx")
    parser.add_argument(
        "--data", default=None,
        help="Força 'hoje' manualmente, dd/mm/aaaa (padrão: detecta automaticamente a data mais recente da MB51)",
    )
    args = parser.parse_args()

    data_ref = _parse_data(args.data) if args.data else None
    resultado = calcular_todos_indicadores(bases_dir=args.bases_dir, data_ref=data_ref)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
