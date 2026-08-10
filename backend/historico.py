r"""Backfill histórico diário dos 9 indicadores da MB51 (Bloco 1 + Intercompany),
pra alimentar o Calendário com dado real em vez de mock.

Só os 9 indicadores cuja fonte (MB51) é histórico completo, sem filtro de data
na extração — por isso dá pra recalcular qualquer dia do passado. Os outros
(ZMM028, MB25, Curva ABC, manuais) são snapshot do momento da extração e não
têm leitura retroativa possível hoje; ficam de fora deste script de propósito,
tratados em etapa separada.

Uso:
    python -m backend.historico --data-inicio 01/04/2026 --data-fim 08/08/2026
    python -m backend.historico --data-inicio 01/04/2026 --saida historico_mb51.json
    python -m backend.historico --data-inicio 01/04/2026 --arquivo-mb51 "C:\caminho\MB51.xlsx"
"""

from __future__ import annotations

import argparse
import datetime
import json
import os

from . import config, extratos, indicadores

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA_PADRAO = os.path.join(REPO_ROOT, "historico_mb51.json")


def _calcular_dia(df_mb51, data: datetime.date) -> dict:
    return {
        "linhas_atendidas_d009": indicadores.linhas_atendidas(df_mb51, config.DEPOSITO_D009, data),
        "linhas_atendidas_d016": indicadores.linhas_atendidas(df_mb51, config.DEPOSITO_D016, data),
        "estornos_d009": indicadores.estornos(df_mb51, config.DEPOSITO_D009, data),
        "estornos_d016": indicadores.estornos(df_mb51, config.DEPOSITO_D016, data),
        "recebimentos_d009": indicadores.recebimentos(df_mb51, config.DEPOSITO_D009, data),
        "recebimentos_d016": indicadores.recebimentos(df_mb51, config.DEPOSITO_D016, data),
        "inventario_rotativo_d009": indicadores.inventario_rotativo(df_mb51, config.DEPOSITO_D009, data),
        "inventario_rotativo_d016": indicadores.inventario_rotativo(df_mb51, config.DEPOSITO_D016, data),
        "intercompany": indicadores.intercompany(df_mb51, data),
    }


def calcular_historico_mb51(
    data_inicio: datetime.date,
    data_fim: datetime.date | None = None,
    bases_dir: str | None = None,
    arquivo_mb51: str | None = None,
) -> dict[str, dict]:
    """Retorna {'aaaa-mm-dd': {9 indicadores}, ...} pra cada dia de data_inicio
    até data_fim (inclusive). Sem data_fim, usa a data mais recente disponível
    na própria MB51 — mesma lógica de 'hoje' do main.py, não confia no relógio
    do sistema porque a extração pode não refletir o dia corrente ainda.

    arquivo_mb51, se informado, é o caminho direto pro .xlsx (ex: cópia local
    numa máquina sem acesso à pasta de rede da empresa) — nesse caso bases_dir
    é ignorado. Sem arquivo_mb51, usa bases_dir/config.MB51_FILENAME como
    sempre (caminho de rede)."""
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

    historico: dict[str, dict] = {}
    dia = data_inicio
    um_dia = datetime.timedelta(days=1)
    while dia <= data_fim:
        historico[dia.isoformat()] = _calcular_dia(mb51, dia)
        dia += um_dia
    return historico


def _parse_data(valor: str) -> datetime.date:
    return datetime.datetime.strptime(valor, "%d/%m/%Y").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill do histórico diário dos 9 indicadores da MB51 (Bloco 1 + Intercompany)"
    )
    parser.add_argument("--bases-dir", default=None, help="Pasta de rede com mb51.xlsx (ignorado se --arquivo-mb51 for informado)")
    parser.add_argument(
        "--arquivo-mb51", default=None,
        help=r'Caminho direto pro .xlsx da MB51 (ex: cópia local "C:\caminho\MB51.xlsx") — usado no lugar de --bases-dir',
    )
    parser.add_argument("--data-inicio", required=True, help="dd/mm/aaaa")
    parser.add_argument(
        "--data-fim", default=None,
        help="dd/mm/aaaa (padrão: data mais recente disponível na MB51)",
    )
    parser.add_argument("--saida", default=SAIDA_PADRAO, help=f"Caminho do JSON de saída (padrão: {SAIDA_PADRAO})")
    args = parser.parse_args()

    data_inicio = _parse_data(args.data_inicio)
    data_fim = _parse_data(args.data_fim) if args.data_fim else None

    resultado = calcular_historico_mb51(
        data_inicio, data_fim, bases_dir=args.bases_dir, arquivo_mb51=args.arquivo_mb51
    )

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    dias = sorted(resultado)
    print(f"Histórico gerado: {len(resultado)} dias ({dias[0]} a {dias[-1]}) -> {args.saida}")


if __name__ == "__main__":
    main()
