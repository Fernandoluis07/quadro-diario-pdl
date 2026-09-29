r"""Reconstrução RETROATIVA de dias que nunca foram congelados (ex.: 31/08, 04/09, 05/09/2026).

Não existe cópia guardada da ZMM028 de dias passados (ela é um snapshot do momento da
extração; o Git só tem os indicadores já calculados dos dias que foram congelados). Já a
MB51 é histórico completo — então:

- Os 9 indicadores da MB51 (linhas atendidas, estornos, recebimentos, inventário
  rotativo, intercompany) são recalculados EXATAMENTE (reaproveita historico._calcular_dia).
- Os indicadores da ZMM028 são reconstruídos "de trás pra frente": parte do saldo REAL do
  snapshot mais recente e DESFAZ, movimento a movimento, tudo que a MB51 lançou depois do
  dia pedido (Util.livre -= quantidade assinada; Val.total -= montante assinado), depois
  roda as mesmas funções de indicador de sempre sobre esse saldo reconstruído.

LIMITES (medidos com --backtest, comparando contra dias já congelados de verdade):
- Quantidade de itens com saldo e valor total: erro pequeno (itens ±0-3; valor ~0,1-0,25%).
- itens_sem_endereco, itens_mrp_saldo_zero e mín/máx: usam endereço (Pos.dpst.), classificação
  MRP (Tp.MRP) e parâmetros (Estq.máx./Pt.reabast) de HOJE — a MB51 não registra mudança
  nenhuma disso, então são aproximados. Todo dia gravado por aqui entra em
  dias_reconstruidos.json (proveniência) — nunca se passa por medição real.
- Campos digitados à mão (planilha manual) e reservas/pendências (MB25, só dia corrente) e os
  painéis do dia NÃO têm fonte retroativa: nada é inventado, as entradas ficam ausentes.

Uso:
    python -m backend.reconstruir --backtest 2026-09-16 2026-09-10 2026-09-03
    python -m backend.reconstruir --datas 2026-08-31 2026-09-04 2026-09-05          # só mostra
    python -m backend.reconstruir --datas 2026-08-31 2026-09-04 2026-09-05 --gravar  # grava
"""

from __future__ import annotations

import argparse
import datetime
import json
import os

import pandas as pd

from . import config, congelar, extratos, historico, historico_mensal, indicadores

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRO_PADRAO = os.path.join(REPO_ROOT, "dias_reconstruidos.json")

CAMPOS_APROXIMADOS = ("itens_sem_endereco", "itens_mrp_saldo_zero", "materiais_abaixo_estoque_minimo_*",
                      "materiais_acima_estoque_maximo_*", "materiais_nunca_movimentados_*")
CAMPOS_COMPARAVEIS = ("itens_estoque_com_saldo", "valor_estoque_total", "itens_mrp_saldo_zero", "itens_sem_endereco")


def zmm028_no_fim_do_dia(
    zmm028_d009: pd.DataFrame,
    mb51: pd.DataFrame,
    data: datetime.date,
    data_snapshot: datetime.date,
    mm60: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """ZMM028 (D009) como estava no FECHAMENTO de `data`, sabendo que `zmm028_d009`
    representa o fechamento de `data_snapshot` (movimentos posteriores a `data` e até
    `data_snapshot` são desfeitos). Só Util.livre e Val.total mudam."""
    if data > data_snapshot:
        raise ValueError(f"{data} é posterior ao snapshot ({data_snapshot}) — só dá pra reconstruir pra trás.")
    dep = mb51.loc[mb51["_deposito_norm"] == config.DEPOSITO_D009]
    datas = dep["_data_norm"]
    mov = dep.loc[datas.map(lambda d: d is not None and data < d <= data_snapshot)]
    chave = indicadores._normalizar_material(mov["Material"])
    qtd_linha = pd.to_numeric(mov["Qtd.  UM registro"], errors="coerce").fillna(0)
    val_linha = pd.to_numeric(mov["Montante em MI"], errors="coerce").fillna(0)

    df = zmm028_d009.copy()
    mat = indicadores._normalizar_material(df["Material"])
    livre = pd.to_numeric(df["Util.livre"], errors="coerce").fillna(0)
    total = pd.to_numeric(df["Val.total"], errors="coerce").fillna(0)

    # Transferência entre depósitos (311/313/315...) vem SEMPRE com Montante em MI = 0 na MB51,
    # mas muda o Val.total do D009 na ZMM028 — sem isto, desfazer as 27 transferências de 23/09
    # errava o valor do estoque em ~R$ 161 mil (backtest 2026-09-27). Linha com quantidade e
    # sem valor é valorizada pelo preço da MM60; sem MM60, pelo preço médio do material no
    # snapshot. (Só o preço médio do snapshot não basta: quem transferiu o saldo INTEIRO pro
    # D016 fica com Util.livre 0 no snapshot, sem preço — explicava só R$ 66 mil dos 161 mil.)
    livre_mat, total_mat = livre.groupby(mat).sum(), total.groupby(mat).sum()
    preco = (total_mat / livre_mat).where(livre_mat != 0)
    if mm60 is not None:
        preco_mm60 = pd.to_numeric(mm60["Preço"], errors="coerce")
        preco_mm60 = preco_mm60.where(preco_mm60 > 0).groupby(indicadores._normalizar_material(mm60["Material"])).first()
        preco = preco_mm60.combine_first(preco)
    sem_valor = (val_linha == 0) & (qtd_linha != 0)
    val_linha = val_linha.where(~sem_valor, qtd_linha * chave.map(preco).fillna(0))

    qtd = qtd_linha.groupby(chave).sum()
    val = val_linha.groupby(chave).sum()
    df["Util.livre"] = livre - mat.map(qtd).fillna(0)
    df["Val.total"] = total - mat.map(val).fillna(0)

    # Material cujo PRIMEIRO movimento na MB51 (qualquer depósito) é posterior a `data` ainda
    # não existia na ZMM028 daquele dia — sem isto, voltava como "VB com saldo zero" e o
    # Itens MRP Saldo Zero saía +1/+2 (506096/862599, backtest 2026-09-27).
    com_data = mb51.loc[mb51["_data_norm"].notna()]
    primeiro = com_data.groupby(indicadores._normalizar_material(com_data["Material"]))["_data_norm"].min()
    ainda_nao_existia = mat.map(primeiro).map(lambda d: isinstance(d, datetime.date) and d > data)
    return df.loc[~(ainda_nao_existia & (df["Util.livre"] == 0))]


def indicadores_zmm028_em(
    zmm028_d009: pd.DataFrame,
    mb51: pd.DataFrame,
    mm60: pd.DataFrame,
    data: datetime.date,
    data_snapshot: datetime.date,
) -> dict:
    """Entrada de historico_zmm028.json (mesmos 16 campos de congelar.CAMPOS_ZMM028) para `data`."""
    z = zmm028_no_fim_do_dia(zmm028_d009, mb51, data, data_snapshot, mm60)
    mb51_ate = mb51.loc[mb51["_data_norm"].map(lambda d: d is not None and d <= data)]
    qtd_vb, valor_vb = indicadores.resumo_vb(z)
    abaixo = indicadores.materiais_abaixo_estoque_minimo(z, mm60, valor_vb)
    acima = indicadores.materiais_acima_estoque_maximo(z, mm60, valor_vb)
    nunca = indicadores.materiais_nunca_movimentados(z, mb51_ate, mm60, valor_vb, qtd_vb, data)
    plano = {
        "itens_estoque_com_saldo": indicadores.itens_estoque_com_saldo(z),
        "itens_mrp_saldo_zero": indicadores.itens_mrp_saldo_zero(z),
        "valor_estoque_total": indicadores.valor_estoque_total(z),
        "itens_sem_endereco": indicadores.itens_sem_endereco(z),
        "total_materiais_vb_d009": qtd_vb,
        "materiais_abaixo_estoque_minimo_qtd": abaixo["qtd"],
        "materiais_abaixo_estoque_minimo_valor_total": abaixo["valor_total"],
        "materiais_abaixo_estoque_minimo_pct_valor_vb": abaixo["pct_valor_vb"],
        "materiais_acima_estoque_maximo_qtd": acima["qtd"],
        "materiais_acima_estoque_maximo_valor_total": acima["valor_total"],
        "materiais_acima_estoque_maximo_pct_valor_vb": acima["pct_valor_vb"],
        "materiais_nunca_movimentados_qtd": nunca["qtd"],
        "materiais_nunca_movimentados_valor_total": nunca["valor_total"],
        "materiais_nunca_movimentados_pct_valor_vb": nunca["pct_valor_vb"],
        "materiais_nunca_movimentados_pct_distribuicao": nunca["pct_distribuicao"],
    }
    return congelar.montar_entrada_zmm028(plano)


def backtest(zmm028_d009, mb51, mm60, data_snapshot, historico_zmm028: dict, datas: list[datetime.date]) -> list[dict]:
    """Reconstrói dias JÁ congelados e devolve real x reconstruído (a régua de confiança)."""
    linhas = []
    for d in datas:
        real = historico_zmm028.get(d.isoformat())
        if real is None:
            continue
        rec = indicadores_zmm028_em(zmm028_d009, mb51, mm60, d, data_snapshot)
        for campo in CAMPOS_COMPARAVEIS:
            linhas.append({"data": d.isoformat(), "campo": campo, "real": real[campo], "reconstruido": rec[campo],
                           "erro": round(rec[campo] - real[campo], 2)})
    return linhas


def montar_dia(zmm028_d009, mb51, mm60, data, data_snapshot) -> dict:
    """{'mb51': entrada exata, 'zmm028': entrada reconstruída} — manuais/paineis ficam de fora."""
    return {
        "mb51": historico._calcular_dia(mb51, data),
        "zmm028": indicadores_zmm028_em(zmm028_d009, mb51, mm60, data, data_snapshot),
    }


def gravar_dia(
    repo_root: str, index_path: str, dias: dict[str, dict], data_snapshot: datetime.date, agora: datetime.datetime,
    resumo_mes: dict | None = None,
) -> None:
    """Grava as entradas (recusa sobrescrever dia já congelado) em historico_mb51/zmm028.json,
    nas constantes do index.html e no registro de proveniência — tudo a partir do MESMO dict.
    `resumo_mes`: meses recalculados dos dias reconstruídos — sem isso o Resumo do Mês ficava sem
    o dia (agosto ficou sem o 31/08 até 2026-09-27: 1.146 linhas em vez de 1.202)."""
    caminho_mb51 = os.path.join(repo_root, "historico_mb51.json")
    caminho_zmm = os.path.join(repo_root, "historico_zmm028.json")
    h_mb51 = congelar._carregar_json(caminho_mb51)
    h_zmm = congelar._carregar_json(caminho_zmm)
    ja = [d for d in dias if d in h_mb51 or d in h_zmm]
    if ja:
        raise ValueError(f"Dia(s) já congelado(s), não vou sobrescrever: {ja}")
    for d, entradas in dias.items():
        h_mb51[d] = entradas["mb51"]
        h_zmm[d] = entradas["zmm028"]

    caminho_registro = os.path.join(repo_root, "dias_reconstruidos.json")
    registro = congelar._carregar_json(caminho_registro)
    for d in dias:
        registro[d] = {
            "metodo": "ZMM028 do snapshot mais recente com os movimentos da MB51 posteriores ao dia desfeitos",
            "snapshot": data_snapshot.isoformat(),
            "gerado_em": agora.isoformat(timespec="seconds"),
            "campos_aproximados": list(CAMPOS_APROXIMADOS),
            "sem_fonte_retroativa": ["historico_manuais", "historico_paineis"],
        }

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = congelar.atualizar_constante_historico_js(html, "HISTORICO_MB51", h_mb51)
    html = congelar.atualizar_constante_historico_js(html, "HISTORICO_ZMM028", h_zmm)

    if resumo_mes:
        caminho_mensal = os.path.join(repo_root, "historico_mensal.json")
        h_mensal = congelar.atualizar_historico_mensal(congelar._carregar_json(caminho_mensal), resumo_mes)
        html = congelar.atualizar_constante_historico_js(html, "HISTORICO_MENSAL", h_mensal)
        congelar._salvar_json(caminho_mensal, h_mensal)

    congelar._salvar_json(caminho_mb51, h_mb51)
    congelar._salvar_json(caminho_zmm, h_zmm)
    congelar._salvar_json(caminho_registro, registro)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)


def _parse(v: str) -> datetime.date:
    return datetime.date.fromisoformat(v)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datas", nargs="+", type=_parse, default=[], help="dias a reconstruir (AAAA-MM-DD)")
    p.add_argument("--backtest", nargs="+", type=_parse, default=[], help="dias já congelados, pra medir o erro do método")
    p.add_argument("--gravar", action="store_true", help="grava nos JSONs e no index.html (padrão: só mostra)")
    p.add_argument("--bases-dir", default=None)
    args = p.parse_args()

    bases = args.bases_dir or config.BASES_DIR
    print("Lendo MB51/ZMM028/MM60...")
    mb51 = extratos.carregar_mb51(os.path.join(bases, config.MB51_FILENAME))
    zmm = extratos.carregar_zmm028(os.path.join(bases, config.ZMM028_FILENAME))
    mm60 = extratos.carregar_mm60(os.path.join(config.MM60_DIR, config.MM60_FILENAME))
    data_snapshot = extratos.datas_disponiveis(mb51)[0]
    print(f"Snapshot ZMM028 assumido = fechamento de {data_snapshot:%d/%m/%Y} (última data da MB51)\n")

    h_zmm = congelar._carregar_json(os.path.join(REPO_ROOT, "historico_zmm028.json"))
    if args.backtest:
        for l in backtest(zmm, mb51, mm60, data_snapshot, h_zmm, args.backtest):
            print(f"{l['data']}  {l['campo']:<26} real={l['real']:>14}  reconstruído={l['reconstruido']:>14}  erro={l['erro']:>12}")

    if args.datas:
        dias = {d.isoformat(): montar_dia(zmm, mb51, mm60, d, data_snapshot) for d in args.datas}
        for d, e in dias.items():
            print(f"\n{d}\n  mb51  : {json.dumps(e['mb51'], ensure_ascii=False)}\n  zmm028: {json.dumps(e['zmm028'], ensure_ascii=False)}")
        if args.gravar:
            meses = sorted({d.replace(day=1) for d in args.datas})
            ultimo_dia = max(extratos.datas_disponiveis(mb51))
            resumo = historico_mensal.calcular_historico_mensal(meses[0], ultimo_dia, df_mb51=mb51)
            resumo = {k: v for k, v in resumo.items() if k in {m.strftime("%Y-%m") for m in meses}}
            gravar_dia(REPO_ROOT, os.path.join(REPO_ROOT, "index.html"), dias, data_snapshot, datetime.datetime.now(), resumo)
            print(f"\nGravado: {', '.join(dias)} (historico_mb51/zmm028.json, index.html, dias_reconstruidos.json)")
        else:
            print("\n(nada gravado — use --gravar)")


if __name__ == "__main__":
    main()
