r"""Cabeçalho — o motor que roda o Quadro Diário PDL inteiro com um clique.

Única cópia do projeto (produção): mora em "...\08. Quadro Diario\02. Cabeçalho" na
rede da empresa, lê as planilhas da pasta irmã "03. Bases" (config.BASES_DIR — ver
backend/config.py).

Fluxo, com confirmação em cada etapa importante:
  1. Lê as 3 planilhas SAP (MB51.xlsx, MB25.xlsx, ZMM028.xlsx) + a
     planilha_manual_quadro_diario.xlsx da pasta "03. Bases" (ou --bases-dir/--manual).
  2. Calcula os 20 indicadores + Resumo do Mês, reaproveitando main.py/indicadores.py/
     historico_mensal.py — não recalcula nada que já existe.
  3. Mostra um resumo e pergunta "Posso congelar?".
  4. Se sim, congela (backend/congelar.py) — um dia já congelado antes só é
     sobrescrito se o usuário pedir reprocessamento forçado E digitar a senha
     correta (config.SENHA_FORCAR_RECONGELAMENTO_SHA256); sem a senha certa,
     continua bloqueado.
  5. Pergunta "Posso subir pro GitHub?".
  6. Se sim, git add + commit + push.

Uso:
    python -m backend.cabecalho
    python -m backend.cabecalho --data 11/08/2026
    python -m backend.cabecalho --bases-dir "C:\caminho\Bases" --manual "C:\caminho\planilha.xlsx"
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import os
import subprocess
import sys

from . import config, congelar, historico_mensal, planilha_manual
from .html_writer import formatar_inteiro_br, formatar_valor_estoque_milhares
from .main import _parse_data, calcular_todos_indicadores

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Pasta de dados é config.BASES_DIR, a pasta de rede "03. Bases" — irmã de onde
# este Cabeçalho mora ("02. Cabeçalho"). Sempre pode ser sobrescrita com
# --bases-dir/--manual.
BASES_DIR_PADRAO = config.BASES_DIR
MANUAL_FILENAME_PADRAO = "planilha_manual_quadro_diario.xlsx"


def _confirmar(pergunta: str) -> bool:
    resposta = input(f"{pergunta} (s/n): ").strip().lower()
    return resposta in ("s", "sim", "y", "yes")


def _senha_forcar_correta() -> bool:
    """Pede a senha (sem eco no terminal) e compara o hash SHA-256 dela com
    config.SENHA_FORCAR_RECONGELAMENTO_SHA256. Nunca compara a senha em texto puro."""
    senha = getpass.getpass("Senha para forçar o reprocessamento: ")
    hash_digitado = hashlib.sha256(senha.encode("utf-8")).hexdigest()
    return hash_digitado == config.SENHA_FORCAR_RECONGELAMENTO_SHA256


def _checar_arquivos(bases_dir: str, manual_path: str) -> list[str]:
    esperados = [
        ("mb51.xlsx", os.path.join(bases_dir, config.MB51_FILENAME)),
        ("mb25.xlsx", os.path.join(bases_dir, config.MB25_FILENAME)),
        ("ZMM028.xlsx", os.path.join(bases_dir, config.ZMM028_FILENAME)),
        ("planilha manual", manual_path),
    ]
    faltando = [f"{nome} (esperado em {caminho})" for nome, caminho in esperados if not os.path.exists(caminho)]
    return faltando


def _imprimir_resumo(
    hoje: datetime.date,
    indicadores: dict,
    manual_hoje: dict,
    resumo_mes: dict,
    pontos_avisos: dict,
    datas_importantes: list[dict],
) -> None:
    ontem = indicadores.get("ontem") or {}
    linha = "-" * 60

    print(linha)
    print(f"Quadro Diário PDL — resumo calculado para {hoje:%d/%m/%Y}")
    print(linha)

    print("\nBloco 1 — Fluxo do Dia (MB51):")
    for chave, titulo in [
        ("linhas_atendidas_d009", "1. Linhas Atendidas D009"),
        ("linhas_atendidas_d016", "2. Linhas Atendidas D016"),
        ("recebimentos_d009", "3. Recebimentos D009"),
        ("recebimentos_d016", "4. Recebimentos D016"),
        ("estornos_d009", "5. Estornos D009"),
        ("estornos_d016", "6. Estornos D016"),
        ("inventario_rotativo_d009", "7. Inventário Rotativo D009"),
        ("inventario_rotativo_d016", "8. Inventário Rotativo D016"),
    ]:
        hoje_v = indicadores[chave]
        ontem_v = ontem.get(chave)
        sufixo = f" (ontem: {formatar_inteiro_br(ontem_v)})" if ontem_v is not None else ""
        print(f"  {titulo}: {formatar_inteiro_br(hoje_v)}{sufixo}")

    print("\nBloco 2 — Pendências (MB25 automático + planilha manual):")
    print(f"  9. Pendências Atendimento Linhas: {formatar_inteiro_br(indicadores['pendencias_atendimento_linhas'])}")
    print(f"  10. Reservas Pendentes: {formatar_inteiro_br(indicadores['reservas_pendentes'])}")
    print(f"  11. Notas Aguardando Lançamento: {formatar_inteiro_br(manual_hoje['notas_aguardando_lancamento'])}")
    print(f"  12. NF Pendente Faturamento: {formatar_inteiro_br(manual_hoje['nf_pendente_faturamento'])}")
    print(f"  13. Devolução: {formatar_inteiro_br(manual_hoje['devolucao'])}")

    print("\nBloco 3 — Fotografia do Estoque (ZMM028 automático, só D009):")
    print(f"  14. Itens em Estoque com Saldo: {formatar_inteiro_br(indicadores['itens_estoque_com_saldo'])}")
    print(f"  15. Valor do Estoque Total: R$ {formatar_valor_estoque_milhares(indicadores['valor_estoque_total'])} mil")
    print(f"  16. Itens MRP Saldo Zero: {formatar_inteiro_br(indicadores['itens_mrp_saldo_zero'])}")
    print("  17. Curva ABC: 30 (fixo)")
    print(f"  18. Itens sem Endereço: {formatar_inteiro_br(indicadores['itens_sem_endereco'])}")

    print("\nSoltos:")
    print(f"  19. Intercompany (manual): {formatar_inteiro_br(manual_hoje['intercompany'])}")
    print(f"  20. Scanner de Documentos (manual): {formatar_inteiro_br(manual_hoje['scanner_documentos'])}")

    mes_chave = f"{hoje:%Y-%m}"
    mes_dados = resumo_mes.get(mes_chave, {})
    print(f"\nResumo do Mês ({mes_chave}):")
    print(f"  Linhas atendidas no mês: {formatar_inteiro_br(mes_dados.get('linhas_atendidas_mes', 0))}")
    print(f"  Valor atendido no mês: R$ {mes_dados.get('valor_atendido_mes', 0):,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
    print(f"  Notas recebidas no mês: {formatar_inteiro_br(mes_dados.get('notas_recebidas_mes', 0))}")

    print(f"\nPontos de Atenção ({len(pontos_avisos['pontos_atencao'])}):")
    for item in pontos_avisos["pontos_atencao"]:
        print(f"  - {item}")
    print(f"Avisos Importantes ({len(pontos_avisos['avisos_importantes'])}):")
    for item in pontos_avisos["avisos_importantes"]:
        print(f"  - {item}")
    print(f"Datas Importantes: {len(datas_importantes)} registro(s) na matriz de férias/ausências.")
    print(linha)


def _git(repo_root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)


def subir_para_github(repo_root: str, data_iso: str) -> None:
    r_add = _git(repo_root, "add", "-A")
    if r_add.returncode != 0:
        raise RuntimeError(f"git add falhou:\n{r_add.stderr}")

    # "--branch" traz uma 1ª linha tipo "## main...origin/main [ahead 1]" — sem ela,
    # working tree limpa mas com commit local pendente de push (ex.: push anterior que
    # falhou) fazia esta função desistir achando que não havia nada a fazer.
    r_status = _git(repo_root, "status", "--porcelain", "--branch")
    linhas = r_status.stdout.splitlines()
    branch_linha = linhas[0] if linhas else ""
    ha_mudancas = len(linhas) > 1
    ha_commit_pendente_de_push = "[ahead" in branch_linha

    if not ha_mudancas and not ha_commit_pendente_de_push:
        print("Nada para commitar nem para subir (working tree já limpo e nada pendente de push).")
        return

    if ha_mudancas:
        r_commit = _git(repo_root, "commit", "-m", f"Congela dia {data_iso}")
        if r_commit.returncode != 0:
            raise RuntimeError(f"git commit falhou:\n{r_commit.stderr}")
        print(r_commit.stdout.strip())

    r_push = _git(repo_root, "push")
    if r_push.returncode != 0:
        raise RuntimeError(f"git push falhou:\n{r_push.stderr}")
    print("Push concluído.")


def executar(
    bases_dir: str | None = None,
    manual_path: str | None = None,
    index_path: str | None = None,
    data_forcada: datetime.date | None = None,
) -> int:
    bases_dir = bases_dir or BASES_DIR_PADRAO
    manual_path = manual_path or os.path.join(bases_dir, MANUAL_FILENAME_PADRAO)
    index_path = index_path or os.path.join(REPO_ROOT, "index.html")

    print("=== Cabeçalho — Quadro Diário PDL ===")
    print(f"Planilhas SAP: {bases_dir}")
    print(f"Planilha manual: {manual_path}\n")

    faltando = _checar_arquivos(bases_dir, manual_path)
    if faltando:
        print("ERRO — arquivo(s) não encontrado(s):")
        for f in faltando:
            print(f"  - {f}")
        return 1

    print("Lendo planilhas e calculando os indicadores...")
    indicadores = calcular_todos_indicadores(bases_dir=bases_dir, data_ref=data_forcada)
    hoje = datetime.date.fromisoformat(indicadores["data_referencia"])

    # Checa "já congelado?"/senha ANTES de mostrar qualquer resumo: uma senha errada
    # tem que travar a execução imediatamente, sem imprimir nada que pareça sucesso
    # (ver backend/cabecalho.py — bug diagnosticado 2026-08-12/13, resumo era
    # mostrado antes da senha e por isso parecia ter funcionado mesmo quando não
    # gravava nada).
    caminho_mb51_json = os.path.join(REPO_ROOT, "historico_mb51.json")
    forcar = False
    if congelar.ja_congelado(congelar._carregar_json(caminho_mb51_json), hoje.isoformat()):
        print(f"O dia {hoje:%d/%m/%Y} já tinha sido congelado antes.")
        if not _confirmar("Quer forçar o reprocessamento mesmo assim?"):
            print("Ok, nada foi alterado.")
            return 0
        if not _senha_forcar_correta():
            print("Senha incorreta — o dia continua bloqueado, nada foi alterado.")
            return 0
        forcar = True

    manuais_planilha = planilha_manual.ler_indicadores_diarios(manual_path)
    manual_hoje = manuais_planilha.get(hoje.isoformat())
    if manual_hoje is None:
        print(
            f"\nERRO: a planilha manual não tem uma linha preenchida para {hoje:%d/%m/%Y} "
            "(aba 'Indicadores Diarios') — preencha antes de continuar. Nada foi alterado."
        )
        return 1

    pontos_avisos = planilha_manual.ler_pontos_avisos(manual_path)
    datas_importantes = planilha_manual.ler_datas_importantes(manual_path)

    inicio_mes = hoje.replace(day=1)
    resumo_mes = historico_mensal.calcular_historico_mensal(
        inicio_mes, hoje, arquivo_mb51=os.path.join(bases_dir, config.MB51_FILENAME)
    )

    _imprimir_resumo(hoje, indicadores, manual_hoje, resumo_mes, pontos_avisos, datas_importantes)

    if not _confirmar("\nPosso congelar?"):
        print("Ok, nada foi alterado.")
        return 0

    try:
        resultado = congelar.congelar_dia(
            repo_root=REPO_ROOT,
            index_path=index_path,
            data_ref=hoje,
            indicadores=indicadores,
            manual_hoje=manual_hoje,
            pontos_atencao=pontos_avisos["pontos_atencao"],
            avisos_importantes=pontos_avisos["avisos_importantes"],
            datas_importantes=datas_importantes,
            resumo_mes=resumo_mes,
            forcar=forcar,
        )
    except congelar.DiaJaCongeladoError as e:
        print(str(e))
        return 0

    print(f"\nDia {hoje:%d/%m/%Y} congelado com sucesso.")
    print(f"Cards atualizados no index.html: {len(resultado['cards_atualizados'])}")
    if resultado["cards_nao_encontrados"]:
        print(f"ATENÇÃO — títulos de card não encontrados no index.html: {resultado['cards_nao_encontrados']}")

    if not _confirmar("\nPosso subir pro GitHub?"):
        print("Ok — as alterações ficaram salvas localmente. Suba manualmente quando quiser (git add/commit/push).")
        return 0

    try:
        subir_para_github(REPO_ROOT, hoje.isoformat())
    except RuntimeError as e:
        print(f"ERRO ao subir pro GitHub:\n{e}")
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bases-dir", default=None, help=f'Pasta local com mb51.xlsx/mb25.xlsx/ZMM028.xlsx (padrão: "{BASES_DIR_PADRAO}")')
    parser.add_argument("--manual", default=None, help="Caminho da planilha_manual_quadro_diario.xlsx (padrão: dentro da pasta --bases-dir)")
    parser.add_argument("--index-path", default=None, help="Caminho do index.html a atualizar (padrão: na raiz do repo)")
    parser.add_argument("--data", default=None, help="dd/mm/aaaa — força 'hoje' (padrão: detecta pela data mais recente da MB51)")
    args = parser.parse_args()

    data_forcada = _parse_data(args.data) if args.data else None
    codigo = executar(bases_dir=args.bases_dir, manual_path=args.manual, index_path=args.index_path, data_forcada=data_forcada)
    sys.exit(codigo)


if __name__ == "__main__":
    main()
