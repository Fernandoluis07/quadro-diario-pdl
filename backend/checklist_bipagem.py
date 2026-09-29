r"""Checklist de Bipagem — Fase 2 (motor). Confere cada movimento da MB51 (D009) contra a
bipagem do SharePoint e a ZMM028.

Dois jeitos de rodar, com papéis diferentes (decisão de Fernando 2026-09-27):

- DENTRO DO CABEÇALHO (`auditar`): DETECTA. Audita todo dia FECHADO depois do
  `ultimo_dia_auditado` (nunca antes de config.CHECKLIST_BIPAGEM_INICIO — 21–24/09 foram o teste
  da Fase 1) e lista as divergências. Depois reavalia as abertas, igual ao 2.0.
- CHECKLIST 2.0 (`python -m backend.checklist_bipagem`, sem senha): SÓ REAVALIA. Lê o
  Share Point.xlsx (atualizado num Excel escondido), relê as linhas da DATA ORIGINAL de cada divergência aberta (Fernando sempre
  corrige a linha da data original, nunca lança na data de hoje) e remove as que passaram.
  NUNCA cria divergência nova, e commita só checklist_bipagem.json + a constante
  CHECKLIST_BIPAGEM do index.html (o portão de push deixa esse commit passar — ver saude.py).

Regras (fechadas com Fernando entre 2026-09-26 e 2026-09-27):
- Ocorrência = (dia, material, matrícula) de cada linha da MB51 no D009 — linhas Qtd 0 e 311
  também. Exige bipagem do PRÓPRIO operador no dia (Matricula.xlsx, aba Data: col A matrícula,
  col B nome de exibição, col C nome no SharePoint; comparação sem acento/caixa).
  RFCUSER = Recebimento, JOBUSER = Estorno NF, matrícula fora do Matricula.xlsx = Usuário
  desconhecido, matrícula sem col C = pessoa de fora do time (externo): nesses 4 casos
  qualquer bipagem do material no dia cobre.
- Endereço: a bipagem MAIS RECENTE do dia do próprio operador (sem operador próprio: de
  qualquer um) × Pos.dpst. da ZMM028. END vazio na bipagem = endereço incorreto; vazio×vazio
  = ok; ZMM028 sem endereço não tem perdão automático.
- Saldo: saldo do sistema = saldo de FECHAMENTO do dia = ZMM028 (a base de verdade, foto do
  momento da extração, logo depois do último movimento da MB51 extraída junto) menos tudo que a
  MB51 lançou no D009 depois daquele dia. Basta UMA contagem válida do dia bater com o saldo de
  FECHAMENTO (decisão de Fernando 2026-09-28: a contagem física é a prova; uma baixa posterior
  no sistema não prova que a entrega saiu certa — a regra "qualquer saldo do dia" foi
  rejeitada). Contagem válida = do próprio responsável; para Recebimento/Estorno NF/externo/desconhecido, de
  qualquer pessoa do time (quem tem col C). Com vários responsáveis no material, a divergência
  vai pra quem tem contagem válida, na ordem da última linha da MB51.
- Endereço + saldo do mesmo responsável = uma linha só (amarela).
- O saldo esperado e o endereço do sistema ficam GRAVADOS com a divergência e nunca são
  recalculados com ZMM028 nova. Divergência não corrigida continua visível na data dela.

Dia só é auditado quando FECHADO (anterior à data de gravação da MB51): um dia auditado ainda
em andamento perderia os movimentos do fim do dia para sempre, já que o 2.0 não cria nada novo.
Qualquer dia (inclusive sábado/domingo) com movimento na MB51 é auditado; movimento sem bipagem
é "Não bipado", sempre — não existe trava de "planilha desatualizada" (Fernando 2026-09-28: a
trava escondeu as 3 linhas do Roberio em 26/09).
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import unicodedata

import pandas as pd

from . import config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_ESTADO = "checklist_bipagem.json"
CONSTANTE_JS = "CHECKLIST_BIPAGEM"
TOLERANCIA = 1e-6
MENOS = "−"  # sinal de menos tipográfico, igual à vitrine aprovada


class ChecklistError(Exception):
    """Falha que impede auditar/reavaliar com segurança — nada é gravado."""


# ---- Normalização ------------------------------------------------------------------

def _cod(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def _nome(v) -> str:
    s = unicodedata.normalize("NFKD", _cod(v)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _end(v) -> str:
    return re.sub(r"[^0-9A-Z]", "", _cod(v).upper()).lstrip("0")


def _data_br(iso: str) -> str:
    return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y")


# ---- Fontes ------------------------------------------------------------------------

def carregar_sharepoint(caminho: str) -> pd.DataFrame:
    sp = pd.read_excel(caminho)
    faltando = {"DtHr", "COD", "OPERADOR", "END", "QTD"} - set(sp.columns)
    if faltando:
        raise ChecklistError(f"{os.path.basename(caminho)} sem as colunas {sorted(faltando)}")
    sp = sp.copy()
    sp["_dthr"] = pd.to_datetime(sp["DtHr"], errors="coerce", dayfirst=True)
    sp = sp.loc[sp["_dthr"].notna()]
    sp["_dia"] = sp["_dthr"].dt.date
    sp["_mat"] = sp["COD"].map(_cod)
    sp["_op"] = sp["OPERADOR"].map(_nome)
    sp["_end"] = sp["END"].map(_end)
    sp["_qtd"] = pd.to_numeric(sp["QTD"], errors="coerce")
    return sp.sort_values("_dthr", kind="stable")


def carregar_matriculas(caminho: str) -> dict[str, tuple[str, str]]:
    """matrícula -> (nome de exibição, nome no SharePoint normalizado ou '' se fora do time)."""
    mt = pd.read_excel(caminho, sheet_name="Data")
    cad = {}
    for _, r in mt.iterrows():
        mat = _cod(r.iloc[0])
        if mat:
            cad[mat] = (_cod(r.iloc[1]).title(), _nome(r.iloc[2]) if len(r) > 2 else "")
    return cad


TEMPO_LIMITE_SHAREPOINT_S = 240
EXCEL_EXE_PADRAO = r"C:\Program Files\Microsoft Office\Root\Office16\EXCEL.EXE"


def atualizar_sharepoint(caminho: str, tempo_limite: int = TEMPO_LIMITE_SHAREPOINT_S) -> None:
    """Atualiza o Share Point.xlsx num Excel ESCONDIDO que o próprio motor abre, atualiza, salva e
    fecha (autorizado por Fernando 2026-09-29). Regras aprendidas nos testes de 28/09:
    - Excel iniciado do jeito normal (EXCEL.EXE /x), janela oculta — o de automação COM
      (DispatchEx) não tem a conta do Office e pede login;
    - o objeto COM é pego pela JANELA do processo que o motor abriu (conferindo o PID), NUNCA por
      GetObject(arquivo): isso entregou o arquivo pro Excel aberto do Fernando e o derrubou;
    - a 1ª tentativa às vezes falha ("conexão com o site do SharePoint não pode ser estabelecida")
      -> até 4 tentativas; e uma vez voltou só 2.000 de 7.352 linhas -> Atualizar DUAS vezes e só
      salvar se nenhuma das duas trouxe menos linhas do que o arquivo já tinha.
    Roda num processo filho com tempo limite; estourou (ou apareceu janela de login), mata SÓ o
    Excel que abriu e sobe ChecklistError — o Cabeçalho segue e avisa."""
    import subprocess
    import tempfile

    # planilha aberta no Excel de alguém = o Excel escondido para numa caixa invisível de "arquivo
    # em uso" (28/09 23:42). Testa antes e nem abre o Excel.
    try:
        with open(caminho, "r+b"):
            pass
    except PermissionError:
        raise ChecklistError("o Share Point.xlsx está ABERTO no Excel (seu ou de outra pessoa) — feche a planilha e rode de novo.")
    pid_arquivo = os.path.join(tempfile.gettempdir(), f"checklist_sp_excel_{os.getpid()}.pid")
    cmd = [sys.executable, "-m", "backend.checklist_bipagem", "--atualizar-sharepoint", caminho, "--pid-arquivo", pid_arquivo]
    proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        saida, _ = proc.communicate(timeout=tempo_limite)
    except subprocess.TimeoutExpired:
        proc.kill()
        _encerrar_meu_excel(pid_arquivo)
        raise ChecklistError(f"o Share Point.xlsx não atualizou em {tempo_limite} s — rede/VPN ou SharePoint fora? "
                             "Nada foi salvo na planilha.")
    _encerrar_meu_excel(pid_arquivo)
    if proc.returncode != 0:
        raise ChecklistError(f"o Share Point.xlsx não atualizou: {saida.strip().splitlines()[-1] if saida.strip() else 'erro'}")
    print(saida.strip())


def _encerrar_meu_excel(pid_arquivo: str) -> None:
    """Mata SÓ o Excel que o processo filho abriu (PID gravado por ele), se ainda estiver vivo."""
    import subprocess

    try:
        with open(pid_arquivo, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return
    for _ in range(3):  # confere que fechou mesmo (28/09 23:42 um ficou aberto segurando a planilha)
        vivo = str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        if not vivo:
            break
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    try:
        os.remove(pid_arquivo)
    except OSError:
        pass


def _excel_da_janela(pid: int):
    """Application do Excel do processo `pid`, pela janela dele (nunca pelo nome do arquivo)."""
    import pythoncom
    import win32com.client as win32
    import win32gui
    import win32process

    achou = []

    def cb(h, _):
        if win32process.GetWindowThreadProcessId(h)[1] == pid and win32gui.GetClassName(h) == "XLMAIN":
            desk = win32gui.FindWindowEx(h, 0, "XLDESK", None)
            w7 = win32gui.FindWindowEx(desk, 0, "EXCEL7", None) if desk else 0
            if w7:
                achou.append(w7)

    win32gui.EnumWindows(cb, None)
    if not achou:
        return None
    r = win32gui.SendMessageTimeout(achou[0], 0x003D, 0, 0xFFFFFFF0, 2, 2000)  # WM_GETOBJECT, OBJID_NATIVEOM
    xl = win32.Dispatch(pythoncom.ObjectFromLresult(r[1], pythoncom.IID_IDispatch, 0)).Application
    if win32process.GetWindowThreadProcessId(xl.Hwnd)[1] != pid:
        raise ChecklistError("o Excel encontrado não é o que o motor abriu — abortado sem mexer em nada.")
    return xl


def _pediu_login(pid: int) -> bool:
    import win32gui
    import win32process

    achou = []
    win32gui.EnumWindows(lambda h, a: a.append(h) if win32process.GetWindowThreadProcessId(h)[1] == pid
                         and win32gui.GetClassName(h) == "BasicEmbeddedBrowser" else None, achou)
    return bool(achou)


def _atualizar_no_excel(caminho: str, pid_arquivo: str) -> None:
    """Corpo do processo filho de atualizar_sharepoint."""
    import subprocess
    import time

    import pythoncom

    caminho = os.path.abspath(caminho)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    exe = EXCEL_EXE_PADRAO if os.path.exists(EXCEL_EXE_PADRAO) else "excel.exe"
    excel = subprocess.Popen([exe, "/x", caminho], startupinfo=si, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    with open(pid_arquivo, "w", encoding="utf-8") as f:
        f.write(str(excel.pid))
    try:
        _atualizar_no_excel_aberto(caminho, excel)
    except BaseException:
        excel.kill()  # qualquer falha: o próprio filho fecha o Excel que abriu
        raise


def _atualizar_no_excel_aberto(caminho: str, excel) -> None:
    import time

    import pythoncom

    pythoncom.CoInitialize()
    xl = None
    for _ in range(60):
        try:
            xl = _excel_da_janela(excel.pid)
        except ChecklistError:
            raise
        except Exception:  # noqa: BLE001 — Excel ainda abrindo
            xl = None
        if xl is not None:
            break
        time.sleep(1)
    if xl is None:
        raise ChecklistError("o Excel escondido não abriu o Share Point.xlsx.")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = xl.Workbooks(1)
    if os.path.abspath(wb.FullName) != caminho:
        raise ChecklistError("o Excel escondido abriu outro arquivo — abortado.")
    if wb.ReadOnly:
        raise ChecklistError("o Share Point.xlsx está aberto por outra pessoa (somente leitura) — feche e rode de novo.")
    tabelas = [lo for ws in wb.Worksheets for lo in ws.ListObjects if lo.SourceType == 3]  # xlSrcQuery
    antes = {lo.Name: lo.ListRows.Count for lo in tabelas}
    time.sleep(20)  # a conta do Office precisa carregar antes da 1ª atualização (testes 28/09)
    passadas = 0
    for tentativa in range(1, 5):
        if _pediu_login(excel.pid):
            raise ChecklistError("o SharePoint pediu login no Excel escondido — nada foi salvo.")
        try:
            completas = True
            for lo in tabelas:
                qt = lo.QueryTable
                qt.BackgroundQuery = False
                qt.Refresh(False)
                if lo.ListRows.Count < antes[lo.Name]:
                    completas = False
            if completas:
                passadas += 1
                if passadas == 2:  # Atualizar Tudo DUAS vezes, as duas completas
                    break
                continue
        except Exception:  # noqa: BLE001 — "conexão com o site do SharePoint não pode ser estabelecida"
            pass
        time.sleep(15)
    if passadas < 2:
        wb.Close(False)
        xl.Quit()
        raise ChecklistError("o SharePoint não respondeu completo em 4 tentativas — planilha NÃO foi salva (ficou como estava).")
    depois = {lo.Name: lo.ListRows.Count for lo in tabelas}
    wb.Save()
    wb.Close(False)
    xl.Quit()
    print(f"Share Point.xlsx atualizado (2x) em Excel escondido: linhas {sum(antes.values())} -> {sum(depois.values())}.")


# ---- Regras ------------------------------------------------------------------------

def responsavel(matricula: str, cad: dict) -> tuple[str, str, str]:
    """(rótulo, operador no SharePoint ou '' se qualquer bipagem cobre, tipo p/ o site)."""
    if matricula == "RFCUSER":
        return "Recebimento", "", "recebimento"
    if matricula == "JOBUSER":
        return "Estorno NF", "", "estorno"
    if matricula not in cad:
        return "Usuário desconhecido", "", "desconhecido"
    exibicao, op = cad[matricula]
    return (exibicao, op, "") if op else (exibicao or matricula, "", "externo")


def _time(cad: dict) -> set[str]:
    return {op for _, op in cad.values() if op}


def _bipagens_elegiveis(bips: pd.DataFrame, op: str) -> pd.DataFrame:
    return bips.loc[bips["_op"] == op] if op else bips


def _contagens_validas(bips: pd.DataFrame, op: str, time: set[str]) -> pd.DataFrame:
    return bips.loc[bips["_op"] == op] if op else bips.loc[bips["_op"].isin(time)]


def _bate(contagens: pd.DataFrame, fechamento: float | None) -> bool:
    return fechamento is not None and bool(((contagens["_qtd"] - fechamento).abs() <= TOLERANCIA).any())


def _diferenca(contado: float, sistema: float) -> str:
    d = round(contado - sistema, 3)
    txt = f"{abs(d):g}".replace(".", ",")
    return ("+" if d > 0 else MENOS) + txt


def saldo_fechamento(livre: pd.Series, mb51_d009: pd.DataFrame, dia: datetime.date) -> pd.Series:
    """Util.livre da ZMM028 (por material) menos tudo que a MB51 lançou no D009 DEPOIS de `dia`."""
    depois = mb51_d009.loc[mb51_d009["_data_norm"].map(lambda d: d is not None and d > dia)]
    qtd = pd.to_numeric(depois["Qtd.  UM registro"], errors="coerce").fillna(0).groupby(depois["_mat"]).sum()
    return livre.sub(qtd, fill_value=0)


def detectar_dia(
    dia: datetime.date,
    mb51_dia: pd.DataFrame,
    sp_dia: pd.DataFrame,
    zmm_end: dict[str, tuple[str, str]],
    saldo_dia: pd.Series,
    cad: dict,
    agora: datetime.datetime,
) -> list[dict]:
    """Divergências de um dia. `mb51_dia`: linhas D009 do dia, na ordem do arquivo."""
    time = _time(cad)
    iso = dia.isoformat()
    linhas: list[dict] = []
    for mat, mv in mb51_dia.groupby("_mat", sort=False):
        bips = sp_dia.loc[sp_dia["_mat"] == mat]
        primeira = mv.iloc[0]
        saldo = float(saldo_dia[mat]) if mat in saldo_dia.index else None
        end_sis_norm, end_sis = zmm_end.get(mat, (None, None))
        por_resp: dict[str, dict] = {}
        for matricula, mu in mv.groupby("_user", sort=False):
            rot, op, tipo = responsavel(matricula, cad)
            base = {
                "id": f"{iso}|{mat}|{matricula}", "data": _data_br(iso), "data_iso": iso,
                "codigo": mat, "descricao": _cod(primeira["Texto breve material"]), "un": _cod(primeira["UM registro"]),
                "tipo_mov": "/".join(dict.fromkeys(mu["_bwart_norm"])), "responsavel": rot, "resp_tipo": tipo,
                "matricula": matricula, "saldo_sistema": saldo, "saldo_contado": None,
                "end_sistema": end_sis, "end_bipado": None, "bipado_por": None,
                "status": "aberta", "detectada_em": agora.isoformat(timespec="seconds"), "corrigida_em": None,
                "_endereco": False, "_saldo": False, "_nao_bipado": False, "_ordem": int(mu["_ordem"].max()),
            }
            eleg = _bipagens_elegiveis(bips, op)
            if eleg.empty:
                base["_nao_bipado"] = True
            elif end_sis_norm is not None:
                ref = eleg.iloc[-1]
                if ref["_end"] != end_sis_norm:
                    base.update(_endereco=True, end_bipado=_cod(ref["END"]), bipado_por=_cod(ref["OPERADOR"]),
                                saldo_contado=None if pd.isna(ref["_qtd"]) else float(ref["_qtd"]))
            base["_contagens"] = _contagens_validas(bips, op, time)
            por_resp[matricula] = base

        # saldo: por material — basta uma contagem válida (de qualquer responsável) bater
        if saldo is not None:
            com_contagem = [r for r in por_resp.values() if not r["_contagens"].empty]
            if com_contagem and not any(_bate(r["_contagens"], saldo) for r in com_contagem):
                alvo = max(com_contagem, key=lambda r: r["_ordem"])
                ult = alvo["_contagens"].iloc[-1]
                alvo.update(_saldo=True, saldo_contado=None if pd.isna(ult["_qtd"]) else float(ult["_qtd"]))
                if not alvo["_endereco"]:
                    alvo.update(bipado_por=_cod(ult["OPERADOR"]))

        for r in por_resp.values():
            if r["_nao_bipado"]:
                r.update(categoria="nao-bipado", divergencia="Não bipado", saldo_contado=None)
            elif r["_endereco"] and r["_saldo"]:
                r.update(categoria="endereco-saldo", divergencia=f"{_diferenca(r['saldo_contado'], saldo)} e endereço")
            elif r["_endereco"]:
                r.update(categoria="endereco", divergencia="Endereço incorreto")
            elif r["_saldo"]:
                dif = _diferenca(r["saldo_contado"], saldo)
                r.update(categoria="positivo" if dif.startswith("+") else "negativo", divergencia=dif)
            else:
                continue
            linhas.append({k: v for k, v in r.items() if not k.startswith("_")})
    return linhas


def corrigida(div: dict, sp: pd.DataFrame, cad: dict) -> bool:
    """A divergência passou na regra dela, relida só com as linhas da DATA ORIGINAL? Usa o
    saldo e o endereço GRAVADOS. 'Não bipado' só sai quando a bipagem nova também está certa
    (endereço e, havendo saldo gravado, contagem) — senão o 2.0 trocaria um erro por outro
    que ninguém veria, já que ele nunca cria divergência nova."""
    dia = datetime.date.fromisoformat(div["data_iso"])
    bips = sp.loc[(sp["_dia"] == dia) & (sp["_mat"] == div["codigo"])]
    _, op, _ = responsavel(div["matricula"], cad)
    eleg = _bipagens_elegiveis(bips, op)
    if eleg.empty:
        return False
    end_ok = True if div["end_sistema"] is None else eleg.iloc[-1]["_end"] == _end(div["end_sistema"])
    # só o fechamento — "saldos_aceitos" gravado nas divergências de 28/09 (regra rejeitada) é ignorado
    saldo_ok = _bate(_contagens_validas(bips, op, _time(cad)), div["saldo_sistema"])
    cat = div["categoria"]
    if cat == "endereco":
        return end_ok
    if cat in ("positivo", "negativo"):
        return saldo_ok
    if cat == "endereco-saldo":
        return end_ok and saldo_ok
    return end_ok and (saldo_ok or div["saldo_sistema"] is None)


# ---- Estado ------------------------------------------------------------------------

def estado_inicial() -> dict:
    inicio = datetime.date.fromisoformat(config.CHECKLIST_BIPAGEM_INICIO)
    return {"ultimo_dia_auditado": (inicio - datetime.timedelta(days=1)).isoformat(), "divergencias": []}


def carregar_estado(repo_root: str) -> dict:
    from .congelar import _carregar_json

    estado = _carregar_json(os.path.join(repo_root, ARQUIVO_ESTADO))
    return estado or estado_inicial()


def dias_a_auditar(
    ultimo_auditado: str, datas_mb51: list[datetime.date], data_extracao: datetime.date
) -> list[datetime.date]:
    """Dias corridos depois do último auditado, até o último dia FECHADO (anterior à data da
    extração) que a MB51 cobre. Nunca antes de CHECKLIST_BIPAGEM_INICIO."""
    if not datas_mb51:
        return []
    inicio = max(datetime.date.fromisoformat(ultimo_auditado) + datetime.timedelta(days=1),
                 datetime.date.fromisoformat(config.CHECKLIST_BIPAGEM_INICIO))
    fim = min(max(datas_mb51), data_extracao - datetime.timedelta(days=1))
    return [inicio + datetime.timedelta(days=i) for i in range((fim - inicio).days + 1)]


def _preparar_mb51(mb51: pd.DataFrame) -> pd.DataFrame:
    d = mb51.loc[mb51["_deposito_norm"] == config.DEPOSITO_D009].copy()
    d["_ordem"] = range(len(d))
    d["_mat"] = d["Material"].map(_cod)
    d["_user"] = d["Nome do usuário"].map(_cod)
    return d


def auditar(
    estado: dict,
    mb51: pd.DataFrame,
    zmm028_d009: pd.DataFrame,
    sp: pd.DataFrame,
    cad: dict,
    data_extracao: datetime.date,
    agora: datetime.datetime,
) -> tuple[dict, dict]:
    """Detecção (Cabeçalho). Devolve (estado novo, resumo). Audita TODOS os dias fechados
    pendentes, sem trava: movimento sem bipagem = 'Não bipado' (inclusive dia sem nenhuma
    bipagem no SharePoint, como 26/09)."""
    d009 = _preparar_mb51(mb51)
    datas = sorted({d for d in d009["_data_norm"] if d is not None})
    zmat = zmm028_d009["Material"].map(_cod)
    livre = pd.to_numeric(zmm028_d009["Util.livre"], errors="coerce").fillna(0).groupby(zmat).sum()
    zmm_end = {m: (_end(e), _cod(e)) for m, e in zip(zmat, zmm028_d009["Pos.dpst."])}

    ids = {d["id"] for d in estado["divergencias"]}
    novas, auditados = [], []
    for dia in dias_a_auditar(estado["ultimo_dia_auditado"], datas, data_extracao):
        mb_dia = d009.loc[d009["_data_norm"] == dia]
        sp_dia = sp.loc[sp["_dia"] == dia]
        if not mb_dia.empty:
            for linha in detectar_dia(dia, mb_dia, sp_dia, zmm_end, saldo_fechamento(livre, d009, dia), cad, agora):
                if linha["id"] not in ids:
                    novas.append(linha)
                    ids.add(linha["id"])
        auditados.append(dia)

    novo = {
        "ultimo_dia_auditado": auditados[-1].isoformat() if auditados else estado["ultimo_dia_auditado"],
        "divergencias": estado["divergencias"] + novas,
    }
    return novo, {"dias_auditados": auditados, "novas": novas}


def situacao_atual(div: dict, sp: pd.DataFrame, cad: dict) -> dict | None:
    """Relê a divergência só com as linhas da DATA ORIGINAL, contra o saldo e o endereço
    GRAVADOS. None = corrigida. Senão devolve a divergência com a etiqueta ATUAL: um "Não
    bipado" que foi bipado com saldo errado vira "−5"; com endereço errado vira "Endereço
    incorreto" (Fernando 2026-09-28: o saldo errado aparecia como "Não bipado")."""
    dia = datetime.date.fromisoformat(div["data_iso"])
    bips = sp.loc[(sp["_dia"] == dia) & (sp["_mat"] == div["codigo"])]
    _, op, _ = responsavel(div["matricula"], cad)
    eleg = _bipagens_elegiveis(bips, op)
    if eleg.empty:
        return {**div, "categoria": "nao-bipado", "divergencia": "Não bipado", "saldo_contado": None}
    ref = eleg.iloc[-1]
    end_err = div["end_sistema"] is not None and ref["_end"] != _end(div["end_sistema"])
    contagens = _contagens_validas(bips, op, _time(cad))
    saldo = div["saldo_sistema"]
    saldo_err = saldo is not None and not contagens.empty and not _bate(contagens, saldo)
    if not end_err and not saldo_err:
        return None
    novo = dict(div)
    if end_err:
        novo.update(end_bipado=_cod(ref["END"]), bipado_por=_cod(ref["OPERADOR"]))
    if saldo_err:
        ult = contagens.iloc[-1]
        contado = None if pd.isna(ult["_qtd"]) else float(ult["_qtd"])
        novo.update(saldo_contado=contado, bipado_por=novo.get("bipado_por") or _cod(ult["OPERADOR"]))
        dif = _diferenca(contado or 0.0, saldo)
        if end_err:
            novo.update(categoria="endereco-saldo", divergencia=f"{dif} e endereço")
        else:
            novo.update(categoria="positivo" if dif.startswith("+") else "negativo", divergencia=dif)
    else:
        novo.update(categoria="endereco", divergencia="Endereço incorreto",
                    saldo_contado=None if pd.isna(ref["_qtd"]) else float(ref["_qtd"]))
    return novo


def reavaliar(estado: dict, sp: pd.DataFrame, cad: dict, agora: datetime.datetime) -> tuple[dict, list[dict]]:
    """Checklist 2.0: marca como corrigidas as abertas que passaram e ATUALIZA a etiqueta das que
    continuam abertas. Nunca acrescenta divergência nova."""
    corrigidas, divs = [], []
    for d in estado["divergencias"]:
        if d["status"] == "aberta":
            atual = situacao_atual(d, sp, cad)
            if atual is None:
                d = {**d, "status": "corrigida", "corrigida_em": agora.isoformat(timespec="seconds")}
                corrigidas.append(d)
            else:
                d = atual
        divs.append(d)
    return {**estado, "divergencias": divs}, corrigidas


def constante_site(estado: dict, agora: datetime.datetime) -> dict:
    abertas = [d for d in estado["divergencias"] if d["status"] == "aberta"]
    abertas.sort(key=lambda d: d["data_iso"])  # sort estável: dentro do dia, ordem da MB51
    return {
        "meta": {"ultimo_dia_auditado": estado["ultimo_dia_auditado"], "atualizado_em": agora.isoformat(timespec="seconds")},
        "rows": abertas,
    }


def gravar(repo_root: str, index_path: str, estado: dict, agora: datetime.datetime) -> list[str]:
    """checklist_bipagem.json + constante CHECKLIST_BIPAGEM no index.html, do MESMO dict."""
    from .congelar import _salvar_json, atualizar_constante_historico_js

    caminho = os.path.join(repo_root, ARQUIVO_ESTADO)
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = atualizar_constante_historico_js(html, CONSTANTE_JS, constante_site(estado, agora))
    _salvar_json(caminho, estado)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    return [caminho, index_path]


def ler_bases_bipagem(data_extracao_mb51: datetime.datetime | None = None, atualizar: bool = True) -> tuple[pd.DataFrame, dict]:
    """Atualiza o Share Point.xlsx no Excel escondido (atualizar_sharepoint) e lê. Se a atualização
    falhar, AVISA em destaque e segue com a planilha como estava (sem trava). Se o arquivo foi salvo
    ANTES da extração da MB51, avisa também — pode estar faltando bipagem ("Não bipado" falso)."""
    sp_path = os.path.join(config.MM60_DIR, config.SHAREPOINT_FILENAME)
    mt_path = os.path.join(config.MM60_DIR, config.MATRICULA_FILENAME)
    for p in (sp_path, mt_path):
        if not os.path.exists(p):
            raise ChecklistError(f"arquivo não encontrado: {p}")
    if atualizar:
        print("Atualizando o Share Point.xlsx (Excel escondido, 2x)...")
        try:
            atualizar_sharepoint(sp_path)
        except ChecklistError as e:
            print("\n" + "!" * 78 + f"\n!! NÃO CONSEGUI ATUALIZAR O SHARE POINT.XLSX: {e}\n"
                  "!! Seguindo com a planilha como estava. Confira a VPN/rede e rode de novo.\n" + "!" * 78)
    salvo_em = datetime.datetime.fromtimestamp(os.path.getmtime(sp_path))
    sp = carregar_sharepoint(sp_path)
    ultima = sp["_dthr"].max() if len(sp) else None
    print(f"Base de bipagem: {len(sp)} linhas, salva em {salvo_em:%d/%m %H:%M}, última bipagem em "
          + (f"{ultima:%d/%m/%Y %H:%M}." if ultima is not None else "(vazia)."))
    if data_extracao_mb51 is not None and salvo_em < data_extracao_mb51:
        print("\n" + "!" * 78 + f"\n!! ATENÇÃO: o Share Point.xlsx foi salvo ({salvo_em:%d/%m %H:%M}) ANTES da extração da MB51 "
              f"({data_extracao_mb51:%d/%m %H:%M}).\n!! Bipagem feita depois disso NÃO está na conta e vira \"Não bipado\". "
              "Abra o arquivo, Dados > Atualizar Tudo,\n!! salve e rode de novo se precisar.\n" + "!" * 78)
    return sp, carregar_matriculas(mt_path)


def resumo_texto(estado: dict) -> str:
    abertas = [d for d in estado["divergencias"] if d["status"] == "aberta"]
    por_dia: dict[str, int] = {}
    for d in abertas:
        por_dia[d["data"]] = por_dia.get(d["data"], 0) + 1
    detalhe = ", ".join(f"{k}: {v}" for k, v in sorted(por_dia.items(), key=lambda kv: kv[0][6:] + kv[0][3:5] + kv[0][:2]))
    return f"{len(abertas)} divergência(s) aberta(s)" + (f" ({detalhe})" if detalhe else "")


# ---- Checklist 2.0 (linha de comando) -------------------------------------------------

def executar_2_0(index_path: str | None = None, atualizar: bool = True) -> int:
    from . import cabecalho

    index_path = index_path or os.path.join(REPO_ROOT, "index.html")
    print("=== Checklist de Bipagem 2.0 — Quadro Diário PDL ===")
    erro = cabecalho.sincronizar_com_remoto(REPO_ROOT)
    if erro:
        print(f"ERRO — {erro}")
        return 1
    estado = carregar_estado(REPO_ROOT)
    antes = resumo_texto(estado)
    try:
        sp, cad = ler_bases_bipagem(atualizar=atualizar)
    except Exception as e:  # noqa: BLE001 — qualquer falha aqui tem que parar com mensagem clara
        print(f"ERRO — não consegui ler a base de bipagem: {e}\nNada foi alterado.")
        return 1
    agora = datetime.datetime.now()
    novo, corrigidas = reavaliar(estado, sp, cad, agora)
    etiquetas = [n for v, n in zip(estado["divergencias"], novo["divergencias"])
                 if n["status"] == "aberta" and n["categoria"] != v["categoria"]]
    print(f"\nAntes: {antes}")
    if not corrigidas and not etiquetas:
        print("Nenhuma divergência aberta mudou no SharePoint desde a última atualização. Nada a gravar.")
        return 0
    for d in corrigidas:
        print(f"  ✔ {d['data']}  {d['codigo']}  {d['responsavel']:<20} {d['divergencia']} (corrigida)")
    for d in etiquetas:
        print(f"  ↻ {d['data']}  {d['codigo']}  {d['responsavel']:<20} agora: {d['divergencia']}")
    print(f"Depois: {resumo_texto(novo)}")
    if not cabecalho._confirmar("\nPosso gravar e subir pro GitHub?"):
        print("Ok, nada foi alterado.")
        return 0
    arquivos = gravar(REPO_ROOT, index_path, novo, agora)
    try:
        cabecalho.subir_para_github(REPO_ROOT, None, arquivos, mensagem=f"Checklist de Bipagem 2.0: {len(corrigidas)} corrigida(s), {len(etiquetas)} com etiqueta atualizada")
    except RuntimeError as e:
        print(f"ERRO ao subir pro GitHub:\n{e}\nAs alterações ficaram salvas localmente.")
        return 1
    print("\n✅ Checklist de Bipagem atualizada e publicada.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--index-path", default=None)
    p.add_argument("--sem-atualizar", action="store_true", help="não atualiza o Share Point.xlsx (usa como está)")
    p.add_argument("--atualizar-sharepoint", default=None, help=argparse.SUPPRESS)  # processo filho interno
    p.add_argument("--pid-arquivo", default=None, help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.atualizar_sharepoint:
        try:
            _atualizar_no_excel(args.atualizar_sharepoint, args.pid_arquivo)
        except ChecklistError as e:
            print(e)
            sys.exit(1)
        return
    sys.exit(executar_2_0(args.index_path, atualizar=not args.sem_atualizar))


if __name__ == "__main__":
    main()
