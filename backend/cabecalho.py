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
  3. Descobre os dias a congelar: TODOS os dias com movimento na MB51 depois do último
     congelado (planejar_dias — 2026-09-27, substituiu a trava de dia pulado: sexta e
     sábado que chegam na mesma extração são os dois processados, nenhum é pulado). Dia
     útil = completo; sábado/domingo/feriado com movimento = só os 8 indicadores da MB51
     (sem movimento em D009/D016 nem entra, e o Calendário o bloqueia). Dia útil seguido de
     outros dias na mesma extração tem os 4 indicadores de saldo reconstruídos desfazendo os
     dias seguintes (config.INDICADORES_SALDO_RECONSTRUIDOS); MB25 fica a foto da extração.
     Dia que ainda não acabou só entra digitando CONTINUAR.
     Calcula os 20 indicadores + Resumo do Mês, reaproveitando main.py/indicadores.py/
     historico_mensal.py — não recalcula nada que já existe. NÃO mostra esses números
     na tela (removido por pedido — ninguém queria mais conferir o resumo antes de
     confirmar); só imprime um ALERTA, se houver, de material VB sem preço na MM60.
  4. Pergunta "Posso congelar?" (uma vez, listando os dias). Depois de congelar, roda a
     Checklist de Bipagem (detecta nos dias fechados; falha dela nunca derruba o congelamento).
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

from . import checklist_bipagem, config, congelar, extratos, historico, historico_mensal, planilha_manual, reconstruir, saude
from . import indicadores as indicadores_mod
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
        # MM60 e os 2 saldos-âncora do indicador 6 NÃO são trocados todo dia
        # (referência fixa) — ficam fixos em config.MM60_DIR (dentro do próprio
        # repo), não em bases_dir.
        ("MM60.xlsx", os.path.join(config.MM60_DIR, config.MM60_FILENAME)),
        ("saldo âncora D009", os.path.join(config.MM60_DIR, config.SALDO_ANCORA_D009_FILENAME)),
        ("saldo âncora D016", os.path.join(config.MM60_DIR, config.SALDO_ANCORA_D016_FILENAME)),
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


def _confirmar_continuar() -> bool:
    return input("Digite CONTINUAR (em maiúsculas) para congelar mesmo assim, ou Enter para deixar esse dia de fora: ").strip() == "CONTINUAR"


def _alertar_saude(bases_dir, df_mb51) -> None:
    """Imprime o banner de alertas (nunca em log escondido) e grava alertas_saude.js pro site.
    Não bloqueia mais nada (2026-09-27): dia pulado deixou de existir (o Cabeçalho congela todos
    os pendentes) e dia em aberto é tratado em executar(). Falha do próprio verificador é
    mostrada na tela — o alarme não pode falhar em silêncio."""
    agora = datetime.datetime.now()
    try:
        gerais = saude.verificar(repo_root=REPO_ROOT, bases_dir=bases_dir, agora=agora, mb51=df_mb51)
        saude.imprimir(saude.formatar_banner(gerais))
        saude.gravar_alertas_js(REPO_ROOT, gerais, agora)
    except Exception as e:  # noqa: BLE001 — o verificador nunca pode derrubar o Cabeçalho, mas TEM que avisar
        saude.imprimir(f"!! NÃO CONSEGUI VERIFICAR A SAÚDE DO SISTEMA ({type(e).__name__}: {e}) — avise quem mantém o projeto.")


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


def subir_para_github(repo_root: str, data_iso: str | None, arquivos: list[str], mensagem: str | None = None) -> None:
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
        r_commit = _git(repo_root, "commit", "-m", mensagem or f"Congela dia {data_iso}", "--", *arquivos)
        if r_commit.returncode != 0:
            raise RuntimeError(f"git commit falhou:\n{r_commit.stderr}")
        print(r_commit.stdout.strip())

    r_push = _git(repo_root, "push")
    if r_push.returncode != 0:
        raise RuntimeError(f"git push falhou:\n{r_push.stderr}")
    print("Push concluído.")


class PlanoError(Exception):
    """A extração não permite saber com segurança quais dias congelar — nada é gravado."""


def planejar_dias(datas_mb51: set, congelados: set[str]) -> list[datetime.date]:
    """Todos os dias com movimento na MB51 DEPOIS do último dia congelado, em ordem (2026-09-27:
    substitui a trava de dia pulado — sexta e sábado que chegam na mesma extração são os dois
    processados). Sem nenhum dia congelado ainda (repositório novo), só o último da MB51.

    A MB51 tem que incluir o último dia já congelado: extraída com período curto, um dia útil
    sem nenhuma linha seria congelado como zero, em silêncio."""
    datas = sorted(d for d in datas_mb51 if d is not None)
    if not datas:
        raise PlanoError("A MB51 não tem nenhuma data válida em 'Data de lançamento'.")
    if not congelados:
        return [datas[-1]]
    ultimo = max(datetime.date.fromisoformat(c) for c in congelados)
    if datas[0] > ultimo:
        raise PlanoError(
            f"A MB51 começa em {datas[0]:%d/%m/%Y}, depois do último dia congelado ({ultimo:%d/%m/%Y}) — "
            "pode estar faltando dia no meio. Extraia a MB51 com um período que inclua o último dia congelado."
        )
    return [d for d in datas if d > ultimo]


def _descrever_dia(d: datetime.date) -> str:
    nome = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")[d.weekday()]
    tipo = "completo" if saude.eh_dia_util(d) else "só os 8 indicadores da MB51"
    return f"{d:%d/%m/%Y} ({nome}, {tipo})"


def _reconstruir_saldos(indicadores: dict, zmm028_d009, df_mb51, mm60, dia: datetime.date, ultima: datetime.date) -> list[str]:
    """Dia útil numa extração que já traz dias posteriores (sexta + sábado): os 4 indicadores de
    saldo (config.INDICADORES_SALDO_RECONSTRUIDOS) saem da ZMM028 com os movimentos posteriores
    DESFEITOS, em vez da foto tirada depois do sábado. Devolve os campos trocados ([] = nada a
    desfazer). MB25 e o resto continuam sendo a foto da extração (decisão 2026-09-27)."""
    d009 = df_mb51.loc[df_mb51["_deposito_norm"] == config.DEPOSITO_D009, "_data_norm"]
    if not d009.map(lambda d: d is not None and d > dia).any():
        return []
    z = reconstruir.zmm028_no_fim_do_dia(zmm028_d009, df_mb51, dia, ultima, mm60)
    calculos = {
        "itens_estoque_com_saldo": indicadores_mod.itens_estoque_com_saldo,
        "valor_estoque_total": indicadores_mod.valor_estoque_total,
        "itens_mrp_saldo_zero": indicadores_mod.itens_mrp_saldo_zero,
        "itens_sem_endereco": indicadores_mod.itens_sem_endereco,
    }
    for campo in config.INDICADORES_SALDO_RECONSTRUIDOS:
        indicadores[campo] = calculos[campo](z)
    return list(config.INDICADORES_SALDO_RECONSTRUIDOS)


def _registrar_reconstrucao(repo_root: str, reconstruidos: dict[str, list[str]], ultima: datetime.date, agora: datetime.datetime) -> str | None:
    if not reconstruidos:
        return None
    caminho = os.path.join(repo_root, "dias_reconstruidos.json")
    registro = congelar._carregar_json(caminho)
    for iso, campos in reconstruidos.items():
        registro[iso] = {
            "metodo": "só os indicadores de saldo: ZMM028 da extração com os movimentos da MB51 posteriores ao dia desfeitos "
                      "(dia útil congelado junto com o fim de semana)",
            "snapshot": ultima.isoformat(),
            "gerado_em": agora.isoformat(timespec="seconds"),
            "campos_reconstruidos": campos,
            "parcial": True,
        }
    congelar._salvar_json(caminho, registro)
    return caminho


def _rodar_checklist(df_mb51, bases_dir: str, index_path: str, agora: datetime.datetime) -> list[str]:
    """Checklist de Bipagem dentro do Cabeçalho: DETECTA nos dias fechados ainda não auditados e
    reavalia as abertas. Qualquer falha é mostrada na tela e NÃO derruba o congelamento — a
    Checklist fica pendente (o último dia auditado não anda) e entra na próxima execução."""
    try:
        extracao = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(bases_dir, config.MB51_FILENAME)))
        sp, cad = checklist_bipagem.ler_bases_bipagem(extracao)
        zmm = extratos.carregar_zmm028(os.path.join(bases_dir, config.ZMM028_FILENAME))
        data_extracao = extracao.date()
        estado = checklist_bipagem.carregar_estado(REPO_ROOT)
        estado, res = checklist_bipagem.auditar(estado, df_mb51, zmm, sp, cad, data_extracao, agora)
        estado, corrigidas = checklist_bipagem.reavaliar(estado, sp, cad, agora)
        arquivos = checklist_bipagem.gravar(REPO_ROOT, index_path, estado, agora)
    except Exception as e:  # noqa: BLE001 — a Checklist nunca derruba o congelamento, mas TEM que avisar
        saude.imprimir(f"\n!! CHECKLIST DE BIPAGEM NÃO FOI ATUALIZADA ({type(e).__name__}: {e}).\n"
                       "   Os dias continuam pendentes e entram na próxima execução.")
        return []
    auditados = ", ".join(f"{d:%d/%m}" for d in res["dias_auditados"]) or "nenhum dia novo fechado"
    print(f"\nChecklist de Bipagem: auditado(s) {auditados}; {len(res['novas'])} divergência(s) nova(s), "
          f"{len(corrigidas)} corrigida(s). {checklist_bipagem.resumo_texto(estado)}.")
    return arquivos


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
    # VEZ aqui e reaproveitada pra todos os dias, pro Resumo do Mês e pra Checklist.
    df_mb51 = extratos.carregar_mb51(os.path.join(bases_dir, config.MB51_FILENAME))
    caminho_mb51_json = os.path.join(REPO_ROOT, "historico_mb51.json")
    historico_mb51 = congelar._carregar_json(caminho_mb51_json)
    datas_mb51 = {d for d in extratos.datas_disponiveis(df_mb51) if d is not None}
    agora = datetime.datetime.now()

    # Alertas de saúde (backend/saude.py) — banner ANTES de qualquer pergunta.
    _alertar_saude(bases_dir, df_mb51)

    # Dias a congelar: todos os pendentes (ou só o --data). Dia já congelado só com senha —
    # checado ANTES de qualquer resumo (bug de 2026-08-12/13: resumo antes da senha parecia
    # sucesso mesmo quando nada era gravado).
    forcar = False
    if data_forcada is not None:
        dias = [data_forcada]
    else:
        try:
            dias = planejar_dias(datas_mb51, set(historico_mb51))
        except PlanoError as e:
            print(f"ERRO — {e}\nNada foi alterado.")
            return 1
    if not dias or congelar.ja_congelado(historico_mb51, dias[-1].isoformat()):
        dia = dias[-1] if dias else max(datas_mb51)
        print(f"O dia {dia:%d/%m/%Y} já tinha sido congelado antes (nenhum dia pendente na MB51).")
        if not _confirmar("Quer forçar o reprocessamento mesmo assim?"):
            print("Ok, nada foi alterado.")
            return 0
        if not _senha_forcar_correta():
            print("Senha incorreta — o dia continua bloqueado, nada foi alterado.")
            return 0
        dias, forcar = [dia], True

    # Dia que ainda não acabou: só entra digitando CONTINUAR (congelamento à noite, fim de
    # turno); sem isso, os dias anteriores seguem e ele fica pra próxima execução.
    em_aberto = [d for d in dias if d >= agora.date()]
    if em_aberto:
        saude.imprimir(saude.formatar_banner(saude.checar_dia_em_aberto(em_aberto[0], agora)))
        if not _confirmar_continuar():
            dias = [d for d in dias if d < agora.date()]
            if not dias:
                print("Ok, nada foi alterado.")
                return 1
            print(f"Ok — congelo só os dias anteriores, sem o {em_aberto[0]:%d/%m}.")

    uteis = [d for d in dias if saude.eh_dia_util(d)]
    manuais_planilha = planilha_manual.ler_indicadores_diarios(manual_path)
    sem_manual = [d for d in uteis if d.isoformat() not in manuais_planilha]
    if sem_manual:
        print(
            f"\nERRO: a planilha manual não tem uma linha preenchida para {', '.join(f'{d:%d/%m/%Y}' for d in sem_manual)} "
            "(aba 'Indicadores Diarios') — preencha antes de continuar. Nada foi alterado."
        )
        return 1

    ultima_mb51 = max(datas_mb51)
    zmm028_d009 = mm60 = None
    por_dia: dict[datetime.date, dict] = {}
    reconstruidos: dict[str, list[str]] = {}
    ignorados: list[datetime.date] = []
    for d in dias:
        if d in uteis:
            ind = calcular_todos_indicadores(bases_dir=bases_dir, data_ref=d, df_mb51=df_mb51)
            if d < ultima_mb51:
                if zmm028_d009 is None:
                    zmm028_d009 = extratos.carregar_zmm028(os.path.join(bases_dir, config.ZMM028_FILENAME))
                    mm60 = extratos.carregar_mm60(os.path.join(config.MM60_DIR, config.MM60_FILENAME))
                campos = _reconstruir_saldos(ind, zmm028_d009, df_mb51, mm60, d, ultima_mb51)
                if campos:
                    reconstruidos[d.isoformat()] = campos
            por_dia[d] = ind
        else:
            entrada = historico._calcular_dia(df_mb51, d)
            if not any(entrada[c] for c in congelar.CAMPOS_MB51):
                ignorados.append(d)  # sem movimento em D009/D016: fica bloqueado no Calendário
                continue
            por_dia[d] = entrada
    dias = [d for d in dias if d in por_dia]
    if not dias:
        print("Nenhum dia com movimento em D009/D016 para congelar. Nada foi alterado.")
        return 0

    pontos_avisos = planilha_manual.ler_pontos_avisos(manual_path)
    datas_importantes = planilha_manual.ler_datas_importantes(manual_path)
    # Resumo do Mês fecha no último DIA ÚTIL do lote: sábado/domingo copiam a sexta em tudo que
    # não é os 8 da MB51 nem a Checklist (Fernando 2026-09-28). O movimento do fim de semana
    # entra no mês quando a segunda for congelada. Lote só de fim de semana: o mês não muda.
    uteis_no_lote = [d for d in dias if d in uteis]
    resumo_mes = (
        historico_mensal.calcular_historico_mensal(uteis_no_lote[0].replace(day=1), uteis_no_lote[-1], df_mb51=df_mb51)
        if uteis_no_lote else None
    )

    for d in uteis:
        if d in por_dia:
            _avisar_materiais_sem_preco_mm60(por_dia[d])
            break

    print("\nDias a congelar:")
    for d in dias:
        extra = " — saldo reconstruído desfazendo os dias seguintes" if d.isoformat() in reconstruidos else ""
        print(f"  • {_descrever_dia(d)}{extra}")
    for d in ignorados:
        print(f"  • {d:%d/%m/%Y}: sem movimento em D009/D016 — fica bloqueado no Calendário")

    if not _confirmar("\nPosso congelar?"):
        print("Ok, nada foi alterado.")
        return 0

    arquivos: list[str] = []
    for d in dias:
        try:
            if d in uteis:
                resultado = congelar.congelar_dia(
                    repo_root=REPO_ROOT,
                    index_path=index_path,
                    data_ref=d,
                    indicadores=por_dia[d],
                    manual_hoje=manuais_planilha[d.isoformat()],
                    pontos_atencao=pontos_avisos["pontos_atencao"],
                    avisos_importantes=pontos_avisos["avisos_importantes"],
                    datas_importantes=datas_importantes,
                    resumo_mes=resumo_mes,
                    forcar=forcar,
                )
                if resultado["cards_nao_encontrados"]:
                    print(f"ATENÇÃO — títulos de card não encontrados no index.html: {resultado['cards_nao_encontrados']}")
            else:
                resultado = congelar.congelar_fim_de_semana(
                    repo_root=REPO_ROOT, index_path=index_path, data_ref=d,
                    entrada_mb51=por_dia[d], forcar=forcar,
                )
        except congelar.DiaJaCongeladoError as e:
            print(str(e))
            return 0
        print(f"Dia {d:%d/%m/%Y} congelado.")
        arquivos += [a for a in resultado["arquivos_json_atualizados"] + [resultado["index_html_atualizado"]] if a not in arquivos]

    # composição por material dos 8 indicadores de cada dia congelado — base do aviso de
    # lançamento retroativo (saude.checar_dias_fechados_incompletos), que só avisa, não corrige
    caminho_detalhe = os.path.join(REPO_ROOT, historico.ARQUIVO_DETALHE)
    detalhe = congelar._carregar_json(caminho_detalhe)
    for d in dias:
        detalhe[d.isoformat()] = historico.detalhe_dia(df_mb51, d)
    congelar._salvar_json(caminho_detalhe, detalhe)
    arquivos.append(caminho_detalhe)

    registro = _registrar_reconstrucao(REPO_ROOT, reconstruidos, ultima_mb51, agora)
    if registro:
        arquivos.append(registro)
    arquivos += [a for a in _rodar_checklist(df_mb51, bases_dir, index_path, agora) if a not in arquivos]

    if not _confirmar("\nPosso subir pro GitHub?"):
        print("Ok — as alterações ficaram salvas localmente. Suba manualmente quando quiser (git add/commit/push).")
        return 0

    # Portão de push: alerta crítico pendente CANCELA o envio, sem perguntar (nada foi
    # commitado ainda; os arquivos congelados ficam salvos localmente).
    if saude.portao_de_push(REPO_ROOT, bases_dir, df_mb51) != 0:
        print("As alterações ficaram salvas localmente. Resolva os alertas e rode o Cabeçalho de novo pra subir.")
        return 1

    rotulo = " e ".join(d.isoformat() for d in dias)
    try:
        subir_para_github(REPO_ROOT, rotulo, arquivos)
    except RuntimeError as e:
        print(f"ERRO ao subir pro GitHub:\n{e}")
        return 1

    feitos = ", ".join(f"{d:%d/%m/%Y}" for d in dias)
    print(f"\n✅ Tudo certo! {'Dias' if len(dias) > 1 else 'Dia'} {feitos} processado(s) e publicado(s) com sucesso.")
    _alertar_saude(bases_dir, df_mb51)
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
