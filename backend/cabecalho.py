r"""Cabeçalho — o motor que roda o Quadro Diário PDL inteiro com um clique.

Única cópia do projeto (produção): mora em "...\08. Quadro Diario\02. Cabeçalho" na
rede da empresa, lê as planilhas da pasta irmã "03. Bases" (config.BASES_DIR — ver
backend/config.py).

Fluxo, com confirmação em cada etapa importante:
  1. Sincroniza sozinho com o GitHub (git fetch) ANTES de qualquer outra coisa — várias
     pessoas rodam o Cabeçalho em turnos diferentes sem se coordenar entre si, então
     essa checagem tem que ser automática: se este computador está só atrasado, dá
     "git pull --ff-only" sozinho; se o histórico divergiu (outra pessoa congelou algo
     que este computador ainda não tem, ao mesmo tempo em que este computador tem algo
     pendente de envio), bloqueia e pede intervenção manual — nunca tenta resolver
     sozinho, porque o índice do site (index.html) tem linhas de até 150 mil
     caracteres que git não consegue mesclar automaticamente.
  2. Lê as 3 planilhas SAP do dia (MB51.xlsx, MB25.xlsx, ZMM028.xlsx) + a
     planilha_manual_quadro_diario.xlsx da pasta "03. Bases" (ou --bases-dir/--manual),
     e a MM60.xlsx (preço de referência, atualizada esporadicamente — não faz parte
     do ciclo diário) da pasta fixa "Bases" dentro do próprio repositório.
  3. Calcula os 20 indicadores + Resumo do Mês, reaproveitando main.py/indicadores.py/
     historico_mensal.py — não recalcula nada que já existe. NÃO mostra esses números
     na tela (removido por pedido — ninguém queria mais conferir o resumo antes de
     confirmar); só imprime um ALERTA, se houver, de material VB sem preço na MM60.
  4. Pergunta "Posso congelar?".
  5. Se sim, congela (backend/congelar.py) — um dia já congelado antes só é
     sobrescrito se o usuário pedir reprocessamento forçado E digitar a senha
     correta (config.SENHA_FORCAR_RECONGELAMENTO_SHA256); sem a senha certa,
     continua bloqueado.
  6. Pergunta "Posso subir pro GitHub?".
  7. Se sim, git add SÓ dos arquivos que este congelamento escreveu (nunca
     "git add -A") + commit + push — esta pasta é compartilhada por várias
     pessoas ao mesmo tempo, então "-A" pegaria qualquer coisa solta de outra
     pessoa junto (já aconteceu: código e uma exclusão de arquivo de outra
     pessoa foram parar num commit "Congela dia"). Termina com uma mensagem clara
     de sucesso ("✅ Tudo certo!") quando congela E sobe sem erro.

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

from . import config, congelar, extratos, historico_mensal, planilha_manual
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
        # MM60 NÃO é trocada todo dia (preço de referência) — fica fixa em
        # config.MM60_DIR (dentro do próprio repo), não em bases_dir.
        ("MM60.xlsx", os.path.join(config.MM60_DIR, config.MM60_FILENAME)),
        ("planilha manual", manual_path),
    ]
    faltando = [f"{nome} (esperado em {caminho})" for nome, caminho in esperados if not os.path.exists(caminho)]
    return faltando


def _avisar_materiais_sem_preco_mm60(indicadores: dict) -> None:
    """Alerta de qualidade de dado — a MM60 é a ÚNICA fonte de preço (ver
    backend/config.MM60_DIR) e não tem cálculo alternativo automático quando falta
    (ver indicadores.materiais_vb_sem_preco_mm60). Diferente do resumo de números
    (removido — ninguém queria mais ver na tela antes de confirmar), isso continua
    aparecendo sempre que houver material faltando, porque é acionável: sem isso, o
    valor em R$ dos indicadores 1/2 (Gestão de Estoque) fica silenciosamente
    incompleto até a planilha de referência ser atualizada."""
    sem_preco = indicadores.get("materiais_vb_sem_preco_mm60") or []
    if not sem_preco:
        return
    print(
        f"\nALERTA — {len(sem_preco)} material(is) VB não encontrado(s) na MM60 "
        "(considere atualizar a planilha de referência):"
    )
    print(f"  {', '.join(sem_preco)}")


def _git(repo_root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)


def sincronizar_com_remoto(repo_root: str) -> str | None:
    """Fetch automático (e pull se só está atrasado) ANTES de qualquer trabalho.

    A checagem "esse dia já foi congelado?" em executar() só enxerga o
    historico_mb51.json DESTE clone — se este computador não tiver puxado um commit
    que outra pessoa já enviou de outra máquina, essa checagem fica cega e pode deixar
    congelar o mesmo dia duas vezes. Com várias pessoas rodando isso em turnos sem se
    falar, não dá pra depender de alguém lembrar de rodar "git pull" antes — por isso
    isso roda sozinho, sempre, no início de executar().

    Retorna None se seguiu em frente (sincronizado, ou não é um repositório git — caso
    de testes isolados). Retorna uma mensagem de erro se precisar de intervenção
    manual: histórico divergiu (outra pessoa congelou algo enquanto este computador
    tinha algo pendente de envio) ou não foi possível falar com o GitHub. Nesses casos
    NUNCA tenta resolver sozinho — index.html tem linhas de até 150 mil caracteres que
    git não consegue mesclar automaticamente; forçar um merge/pull aqui arriscaria
    sobrescrever o congelamento de outra pessoa.
    """
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        return None

    r_fetch = _git(repo_root, "fetch", "origin")
    if r_fetch.returncode != 0:
        return (
            "Não consegui verificar se este computador está atualizado com o GitHub "
            f"(git fetch falhou):\n{r_fetch.stderr}\n"
            "Não vou continuar sem essa checagem — ela existe pra nunca congelar por "
            "cima do que outra pessoa já congelou em outro computador."
        )

    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    r_contagem = _git(repo_root, "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD")
    if r_contagem.returncode != 0:
        return None  # sem upstream configurado (ex.: repositório de teste) — não bloqueia

    atras_str, na_frente_str = r_contagem.stdout.split()
    atras, na_frente = int(atras_str), int(na_frente_str)

    if atras and na_frente:
        return (
            f"O repositório divergiu do GitHub: este computador tem {na_frente} "
            f"commit(s) local(is) ainda não enviado(s), e o GitHub tem {atras} "
            "commit(s) que este computador não tem — provavelmente outra pessoa "
            "congelou um dia enquanto este computador tinha algo pendente de envio. "
            "Isso precisa ser resolvido manualmente por quem administra o "
            "repositório antes de continuar."
        )

    if atras:
        r_pull = _git(repo_root, "pull", "--ff-only", "origin", branch)
        if r_pull.returncode != 0:
            return (
                "O GitHub tem commit(s) que este computador não tem, e não consegui "
                f"atualizar sozinho (git pull --ff-only falhou):\n{r_pull.stderr}"
            )
        print(f"Repositório atualizado automaticamente com {atras} commit(s) novo(s) do GitHub.")

    if na_frente:
        print(
            f"Aviso: este computador tem {na_frente} commit(s) local(is) ainda não "
            "enviado(s) ao GitHub (de uma execução anterior). Serão enviados ao final "
            "desta execução, se você confirmar o push."
        )

    return None


def subir_para_github(repo_root: str, data_iso: str, arquivos: list[str]) -> None:
    """`arquivos` tem que ser exatamente os caminhos que congelar_dia() escreveu
    (resultado["arquivos_json_atualizados"] + [resultado["index_html_atualizado"]]) —
    NUNCA "git add -A". Este repositório é uma pasta de rede compartilhada por várias
    pessoas ao mesmo tempo (não clones separados); "git add -A" já comitou por engano
    edição de código de outra pessoa e uma exclusão acidental de arquivo que estavam
    soltas na pasta (2026-08-14). Adicionar só os arquivos que este congelamento de
    fato escreveu evita isso, não importa o que mais esteja sujo na pasta.
    """
    r_add = _git(repo_root, "add", "--", *arquivos)
    if r_add.returncode != 0:
        raise RuntimeError(f"git add falhou:\n{r_add.stderr}")

    # "--branch" traz uma 1ª linha tipo "## main...origin/main [ahead 1]" — sem ela,
    # working tree limpa mas com commit local pendente de push (ex.: push anterior que
    # falhou) fazia esta função desistir achando que não havia nada a fazer. O "--"
    # restringe as linhas de arquivo aos `arquivos` do congelamento — não conta como
    # mudança pendente algo que outra pessoa deixou sujo na pasta compartilhada.
    r_status = _git(repo_root, "status", "--porcelain", "--branch", "--", *arquivos)
    linhas = r_status.stdout.splitlines()
    branch_linha = linhas[0] if linhas else ""
    ha_mudancas = len(linhas) > 1
    ha_commit_pendente_de_push = "[ahead" in branch_linha

    if not ha_mudancas and not ha_commit_pendente_de_push:
        print("Nada para commitar nem para subir (working tree já limpo e nada pendente de push).")
        return

    if ha_mudancas:
        r_commit = _git(repo_root, "commit", "-m", f"Congela dia {data_iso}", "--", *arquivos)
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

    erro_sync = sincronizar_com_remoto(REPO_ROOT)
    if erro_sync:
        print(f"ERRO — {erro_sync}")
        return 1

    faltando = _checar_arquivos(bases_dir, manual_path)
    if faltando:
        print("ERRO — arquivo(s) não encontrado(s):")
        for f in faltando:
            print(f"  - {f}")
        return 1

    print("Lendo planilhas e calculando os indicadores...")
    # MB51 (a maior das 3 planilhas do dia, ~40s pra ler sobre a rede) é carregada UMA
    # VEZ aqui e reaproveitada tanto pros indicadores do dia quanto pro Resumo do Mês
    # (historico_mensal) logo abaixo — antes disso, os dois liam o mesmo arquivo do
    # zero cada um, dobrando à toa o tempo da etapa mais pesada do Cabeçalho.
    df_mb51 = extratos.carregar_mb51(os.path.join(bases_dir, config.MB51_FILENAME))
    indicadores = calcular_todos_indicadores(bases_dir=bases_dir, data_ref=data_forcada, df_mb51=df_mb51)
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
    resumo_mes = historico_mensal.calcular_historico_mensal(inicio_mes, hoje, df_mb51=df_mb51)

    _avisar_materiais_sem_preco_mm60(indicadores)

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

    arquivos_congelados = resultado["arquivos_json_atualizados"] + [resultado["index_html_atualizado"]]
    try:
        subir_para_github(REPO_ROOT, hoje.isoformat(), arquivos_congelados)
    except RuntimeError as e:
        print(f"ERRO ao subir pro GitHub:\n{e}")
        return 1

    print(f"\n✅ Tudo certo! Dia {hoje:%d/%m/%Y} processado e publicado com sucesso.")
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
