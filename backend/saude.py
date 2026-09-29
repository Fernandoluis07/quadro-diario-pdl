r"""Alerta ativo de saúde do sistema — o sistema NÃO pode falhar em silêncio.

Cada checagem devolve uma lista de alertas {codigo, nivel, titulo, detalhe}; nível
"critico" (precisa de ação agora), "aviso" (atenção) ou "info". Quatro famílias:

  1. SEQUÊNCIA   — dia com movimento na MB51 ainda não congelado depois do prazo (atrasado).
                   Só AVISA desde 2026-09-27: o Cabeçalho congela TODOS os dias pendentes de
                   uma vez (sexta + sábado na mesma extração), então não existe mais "dia
                   pulado" a destravar — o risco que sobra é ninguém rodar o Cabeçalho.
  2. EXTRAÇÃO    — MB51/ZMM028/MB25/planilha manual desatualizada; MB51 sem os últimos dias;
                   ZMM028 e MB51 extraídas em horários muito diferentes (saldo e movimento
                   deixam de ser do mesmo instante).
  3. DIA EM ABERTO — congelar uma data que ainda não acabou (hoje ou futuro), ou um dia já
                   congelado cujos números hoje divergem da MB51 completa (foi fechado
                   antes de o movimento do dia terminar de ser lançado).
  4. CÓDIGO SEM COMMIT — mudança em arquivo rastreado/novo arquivo há muito tempo sem commit,
                   ou commit que nunca foi enviado ao GitHub (produção rodando código que
                   ninguém mais vê e que pode se perder ou ser sobrescrito).

Como o alerta chega até você sem você ir procurar:
  - Cabeçalho: banner no início e no fim de toda execução; dia em aberto só é congelado
    digitando CONTINUAR (ver cabecalho.executar).
  - Site (index.html): faixa vermelha no topo, com checagem AO VIVO (último dia congelado x
    relógio) + o arquivo alertas_saude.js gerado por este módulo. Se esse arquivo parar de ser
    atualizado, a própria faixa avisa (o verificador também não pode falhar em silêncio).
  - Verificador agendado (Verificar_Saude.bat, Agendador de Tarefas do Windows): roda em dias
    úteis, grava alertas_saude.js e abre uma janela na tela quando há alerta crítico.

Uso:
    python -m backend.saude                 # verifica tudo e imprime (lê a MB51: ~1 min)
    python -m backend.saude --rapido        # sem ler a MB51 (usa calendário de dias úteis)
    python -m backend.saude --notificar     # + grava alertas_saude.js e abre janela se crítico
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_ALERTAS_JS = "alertas_saude.js"
ARQUIVO_ESTADO = ".saude_estado.json"

INICIO_HISTORICO = datetime.date(2026, 4, 1)
# Feriados nacionais de 2026 (dia útil sem movimento não é "dia pulado"). A MB51 é a
# fonte de verdade quando lida; isto só serve pro modo --rapido e pra "extração atrasada".
FERIADOS = {
    datetime.date(2026, 1, 1), datetime.date(2026, 2, 16), datetime.date(2026, 2, 17),
    datetime.date(2026, 4, 3), datetime.date(2026, 4, 21), datetime.date(2026, 5, 1),
    datetime.date(2026, 6, 4), datetime.date(2026, 9, 7), datetime.date(2026, 10, 12),
    datetime.date(2026, 11, 2), datetime.date(2026, 11, 20), datetime.date(2026, 12, 25),
}
HORA_PRAZO_CONGELAMENTO = 11
LIMITE_DESSINCRONIA_MIN = 60          # ZMM028 x MB51 extraídas com mais que isso de diferença
HORAS_CODIGO_AVISO = 24               # mudança sem commit há mais que isso -> aviso
HORAS_CODIGO_CRITICO = 72             # ... -> crítico
HORAS_COMMIT_SEM_PUSH_AVISO = 2       # commit local sem push há mais que isso -> aviso
DIAS_FECHADOS_A_CONFERIR = 15
CAMPOS_CONFERIDOS = (
    "linhas_atendidas_d009", "linhas_atendidas_d016", "estornos_d009", "estornos_d016",
    "recebimentos_d009", "recebimentos_d016", "inventario_rotativo_d009", "inventario_rotativo_d016",
)


def _alerta(codigo: str, nivel: str, titulo: str, detalhe: str = "") -> dict:
    return {"codigo": codigo, "nivel": nivel, "titulo": titulo, "detalhe": detalhe}


def eh_dia_util(d: datetime.date) -> bool:
    return d.weekday() < 5 and d not in FERIADOS


def dia_util_anterior(d: datetime.date) -> datetime.date:
    d -= datetime.timedelta(days=1)
    while not eh_dia_util(d):
        d -= datetime.timedelta(days=1)
    return d


def dia_util_seguinte(d: datetime.date) -> datetime.date:
    d += datetime.timedelta(days=1)
    while not eh_dia_util(d):
        d += datetime.timedelta(days=1)
    return d


def prazo_de_congelamento(d: datetime.date) -> datetime.datetime:
    """Rotina normal: o dia D é congelado na manhã do próximo dia útil (sexta -> segunda).
    Só depois das 11h desse dia é que a falta do congelamento vira alerta."""
    return datetime.datetime.combine(dia_util_seguinte(d), datetime.time(HORA_PRAZO_CONGELAMENTO))


def _fmt(d: datetime.date | str) -> str:
    if isinstance(d, str):
        d = datetime.date.fromisoformat(d)
    return d.strftime("%d/%m")


# ---- 1. Sequência --------------------------------------------------------------

def checar_sequencia(
    datas_esperadas: set[datetime.date],
    congelados: set[str],
    agora: datetime.datetime,
) -> list[dict]:
    """`datas_esperadas`: dias que DEVEM estar congelados (dias com movimento em D009/D016 na
    MB51; ou, no modo rápido, dias úteis do calendário). Só conta depois do prazo (11h do
    próximo dia útil). Os dias DEPOIS do último congelado o Cabeçalho congela sozinho na
    próxima execução; buraco ANTES dele (dia antigo que ficou de fora) precisa de
    python -m backend.reconstruir."""
    candidatos = [d for d in datas_esperadas if agora >= prazo_de_congelamento(d)]
    atrasados = sorted(d for d in candidatos if d >= INICIO_HISTORICO and d.isoformat() not in congelados)
    if not atrasados:
        return []
    ultimo = max(congelados) if congelados else ""
    buracos = [d for d in atrasados if d.isoformat() < ultimo]
    pendentes = [d for d in atrasados if d.isoformat() > ultimo]
    alertas = []
    if pendentes:
        alertas.append(_alerta(
            "dia_atrasado", "aviso",
            f"{len(pendentes)} dia(s) com movimento ainda não congelados: {', '.join(_fmt(d) for d in pendentes)}",
            "Rode o Cabeçalho — ele congela todos os dias pendentes de uma vez.",
        ))
    if buracos:
        alertas.append(_alerta(
            "dia_pulado", "aviso",
            f"{len(buracos)} dia(s) antigos ficaram fora do histórico: {', '.join(_fmt(d) for d in buracos)}",
            "Ficam bloqueados no Calendário. Para dias antigos use python -m backend.reconstruir.",
        ))
    return alertas


def checar_dia_em_aberto(hoje_a_congelar: datetime.date, agora: datetime.datetime) -> list[dict]:
    if hoje_a_congelar >= agora.date():
        return [_alerta(
            "dia_em_aberto", "critico",
            f"O dia {_fmt(hoje_a_congelar)} AINDA NÃO ACABOU — congelar agora grava movimento incompleto",
            "Movimentos lançados depois desta hora ficariam de fora do dia fechado. Congele só a partir do dia seguinte.",
        )]
    return []


def checar_dias_fechados_incompletos(
    mb51, historico_mb51: dict, calcular_dia, ultimos: int = DIAS_FECHADOS_A_CONFERIR,
    detalhe_congelado: dict | None = None, detalhe_dia=None,
) -> list[dict]:
    """Recalcula os últimos dias congelados a partir da MB51 COMPLETA de hoje e compara com o
    que foi congelado: diferença = lançamento retroativo em dia já fechado. SÓ AVISA (Fernando
    2026-09-28: ele decide se corrige). Com o detalhe do congelamento (historico_mb51_detalhe.json)
    o aviso diz o material/nota, o valor antigo e o novo."""
    alertas = []
    for iso in sorted(historico_mb51)[-ultimos:]:
        atual = calcular_dia(mb51, datetime.date.fromisoformat(iso))
        difs = [f"{c}: congelado {historico_mb51[iso].get(c)} x MB51 hoje {atual.get(c)}"
                for c in CAMPOS_CONFERIDOS if historico_mb51[iso].get(c) != atual.get(c)]
        if difs and detalhe_dia is not None and detalhe_congelado and iso in detalhe_congelado:
            from .historico import diferencas_detalhe

            difs += ["por material: " + "; ".join(diferencas_detalhe(detalhe_congelado[iso], detalhe_dia(mb51, datetime.date.fromisoformat(iso))))]
        if difs:
            alertas.append(_alerta(
                "dia_fechado_incompleto", "aviso",
                f"O dia {_fmt(iso)} foi congelado com números diferentes da MB51 atual",
                "; ".join(difs),
            ))
    return alertas


# ---- 2. Extração ---------------------------------------------------------------

def checar_extracoes(
    mtimes: dict[str, datetime.datetime | None],
    ultima_data_mb51: datetime.date | None,
    agora: datetime.datetime,
) -> list[dict]:
    """`mtimes`: nome do arquivo -> data/hora da última gravação (None = não existe)."""
    alertas = []
    hoje = agora.date()
    depois_das_9 = eh_dia_util(hoje) and agora.hour >= 9
    esperado = hoje if depois_das_9 else dia_util_anterior(hoje)
    for nome, m in mtimes.items():
        if m is None:
            alertas.append(_alerta("extracao_ausente", "critico", f"{nome} não encontrado", "O Cabeçalho não roda sem ele."))
        elif m.date() < esperado:
            alertas.append(_alerta(
                "extracao_desatualizada", "critico",
                f"{nome} desatualizado: última gravação {m:%d/%m %H:%M}",
                f"Esperado ao menos de {_fmt(esperado)}.",
            ))
    if ultima_data_mb51 is not None:
        minimo = dia_util_anterior(hoje)
        if depois_das_9 and ultima_data_mb51 < minimo:
            alertas.append(_alerta(
                "mb51_sem_ultimos_dias", "critico",
                f"MB51 só vai até {_fmt(ultima_data_mb51)} (esperado ao menos {_fmt(minimo)})",
                "Extração incompleta ou não atualizada.",
            ))
    mb, zmm = mtimes.get("MB51.xlsx"), mtimes.get("ZMM028.xlsx")
    if mb and zmm and abs((mb - zmm).total_seconds()) / 60 > LIMITE_DESSINCRONIA_MIN:
        alertas.append(_alerta(
            "extracoes_dessincronizadas", "aviso",
            f"ZMM028 ({zmm:%d/%m %H:%M}) e MB51 ({mb:%d/%m %H:%M}) foram extraídas com {abs((mb - zmm).total_seconds()) / 3600:.1f} h de diferença",
            "O saldo e os movimentos deixam de ser do mesmo instante — extraia as duas juntas.",
        ))
    return alertas


# ---- 4. Código sem commit ------------------------------------------------------

def _git(repo_root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)


def checar_codigo_sem_commit(repo_root: str, agora: datetime.datetime) -> list[dict]:
    r = _git(repo_root, "status", "--porcelain", "--branch", "-uall")
    if r.returncode != 0:
        return [_alerta("git_indisponivel", "aviso", "Não consegui consultar o git", r.stderr.strip()[:200])]
    linhas = r.stdout.splitlines()
    alertas = []
    caminhos = [l[3:].strip().strip('"') for l in linhas[1:] if len(l) > 3]
    caminhos = [c.split(" -> ")[-1] for c in caminhos if os.path.basename(c) != ARQUIVO_ALERTAS_JS]
    if caminhos:
        idades = []
        for c in caminhos:
            p = os.path.join(repo_root, c)
            if os.path.exists(p):
                idades.append(agora - datetime.datetime.fromtimestamp(os.path.getmtime(p)))
        horas = max(idades).total_seconds() / 3600 if idades else 0
        nivel = "critico" if horas >= HORAS_CODIGO_CRITICO else "aviso" if horas >= HORAS_CODIGO_AVISO else None
        if nivel:
            alertas.append(_alerta(
                "codigo_sem_commit", nivel,
                f"{len(caminhos)} arquivo(s) alterado(s) SEM COMMIT há {horas / 24:.1f} dia(s): "
                + ", ".join(caminhos[:5]) + ("…" if len(caminhos) > 5 else ""),
                "Produção está rodando código que não está no GitHub — risco de perda ou edição concorrente.",
            ))
    r2 = _git(repo_root, "log", "@{u}..HEAD", "--format=%ct")
    if r2.returncode == 0 and r2.stdout.strip():
        n = len(r2.stdout.split())
        horas = (agora - datetime.datetime.fromtimestamp(int(r2.stdout.split()[-1]))).total_seconds() / 3600
        if horas >= HORAS_COMMIT_SEM_PUSH_AVISO:
            alertas.append(_alerta(
                "commit_sem_push", "critico" if horas >= HORAS_CODIGO_CRITICO else "aviso",
                f"{n} commit(s) local(is) NÃO enviado(s) ao GitHub há {horas:.0f} h",
                "Só existem nesta pasta compartilhada.",
            ))
    return alertas


# ---- Info: dados reconstruídos ---------------------------------------------------

def checar_dados_reconstruidos(registro: dict) -> list[dict]:
    """Só avisa dos dias reconstruídos que ninguém conferiu ainda. Depois de conferir que o
    dia foi publicado certo, grave "conferido_em" na entrada do dias_reconstruidos.json: o
    registro de que o dado é aproximado continua lá, só o aviso a cada execução some."""
    pendentes = sorted(d for d, info in registro.items() if not info.get("conferido_em"))
    if not pendentes:
        return []
    return [_alerta(
        "dados_reconstruidos", "info",
        f"{len(pendentes)} dia(s) com ZMM028 RECONSTRUÍDA (aproximada): {', '.join(_fmt(d) for d in pendentes)}",
        "Ver dias_reconstruidos.json — não são medição real.",
    )]


# ---- Orquestração ------------------------------------------------------------------

ORDEM = {"critico": 0, "aviso": 1, "info": 2}


def _carregar(caminho: str) -> dict:
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _mtimes(bases_dir: str, manual: str) -> dict:
    def m(p):
        return datetime.datetime.fromtimestamp(os.path.getmtime(p)) if os.path.exists(p) else None
    return {"MB51.xlsx": m(os.path.join(bases_dir, "MB51.xlsx")), "ZMM028.xlsx": m(os.path.join(bases_dir, "ZMM028.xlsx")),
            "MB25.xlsx": m(os.path.join(bases_dir, "MB25.xlsx")), "planilha manual": m(manual)}


def verificar(
    repo_root: str = REPO_ROOT,
    bases_dir: str | None = None,
    agora: datetime.datetime | None = None,
    mb51=None,
    ler_mb51: bool = True,
) -> list[dict]:
    """Roda tudo. `mb51`: DataFrame já carregado (evita reler ~1 min de rede)."""
    from . import config, extratos, historico  # import tardio: este módulo também roda sem pandas nos testes de git

    agora = agora or datetime.datetime.now()
    bases_dir = bases_dir or config.BASES_DIR
    manual = os.path.join(bases_dir, "planilha_manual_quadro_diario.xlsx")
    historico_mb51 = _carregar(os.path.join(repo_root, "historico_mb51.json"))
    congelados = set(historico_mb51)
    alertas: list[dict] = []

    if mb51 is None and ler_mb51 and os.path.exists(os.path.join(bases_dir, config.MB51_FILENAME)):
        mb51 = extratos.carregar_mb51(os.path.join(bases_dir, config.MB51_FILENAME))
    if mb51 is not None:
        ultima = max((d for d in extratos.datas_disponiveis(mb51) if d is not None), default=None)
        # só dia com movimento nos 8 indicadores (D009/D016) precisa estar congelado: sábado com
        # linha só de outro depósito não entra no histórico e não pode virar alerta eterno
        validos = mb51.loc[mb51["_deposito_norm"].isin(config.DEPOSITOS_VALIDOS), "_data_norm"]
        datas = {d for d in validos if d is not None}
        alertas += checar_dias_fechados_incompletos(
            mb51, historico_mb51, historico._calcular_dia,
            detalhe_congelado=_carregar(os.path.join(repo_root, historico.ARQUIVO_DETALHE)), detalhe_dia=historico.detalhe_dia,
        )
    else:
        datas = {INICIO_HISTORICO + datetime.timedelta(days=i) for i in range((agora.date() - INICIO_HISTORICO).days)
                 if eh_dia_util(INICIO_HISTORICO + datetime.timedelta(days=i))}
        ultima = None
    alertas += checar_sequencia(datas, congelados, agora)
    alertas += checar_extracoes(_mtimes(bases_dir, manual), ultima, agora)
    alertas += checar_codigo_sem_commit(repo_root, agora)
    alertas += checar_dados_reconstruidos(_carregar(os.path.join(repo_root, "dias_reconstruidos.json")))
    return sorted(alertas, key=lambda a: ORDEM[a["nivel"]])


def formatar_banner(alertas: list[dict]) -> str:
    if not alertas:
        return "✅ Saúde do sistema: nenhum alerta."
    icone = {"critico": "🔴", "aviso": "🟠", "info": "🔵"}
    barra = "=" * 78
    linhas = [barra, f"  ⚠  ALERTAS DO SISTEMA ({len(alertas)})", barra]
    for a in alertas:
        linhas.append(f" {icone[a['nivel']]} [{a['nivel'].upper()}] {a['titulo']}")
        if a["detalhe"]:
            linhas.append(f"      {a['detalhe']}")
    linhas.append(barra)
    return "\n".join(linhas)


def imprimir(texto: str) -> None:
    """print() que NUNCA quebra por codificação (tarefa agendada / saída redirecionada usam
    cp1252 e não têm ⚠ ou 🔴) — um alarme que trava ao tentar alarmar é pior que nenhum."""
    try:
        print(texto)
    except UnicodeEncodeError:
        codificacao = getattr(sys.stdout, "encoding", None) or "cp1252"
        print(texto.encode(codificacao, "replace").decode(codificacao))


def gravar_alertas_js(repo_root: str, alertas: list[dict], agora: datetime.datetime) -> str:
    """window.SAUDE_SISTEMA — lido pela faixa do index.html (file://, sem fetch)."""
    caminho = os.path.join(repo_root, ARQUIVO_ALERTAS_JS)
    payload = {"gerado_em": agora.isoformat(timespec="seconds"), "alertas": alertas}
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("window.SAUDE_SISTEMA = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    return caminho


def notificar_janela(alertas: list[dict], repo_root: str, agora: datetime.datetime) -> bool:
    """Janela do Windows na tela (não é log). Só pra críticos, e só se o conjunto mudou ou
    passaram 6 h desde o último aviso — pra não virar ruído que se aprende a ignorar."""
    criticos = [a for a in alertas if a["nivel"] == "critico"]
    if not criticos:
        return False
    assinatura = hashlib.sha1("|".join(sorted(a["titulo"] for a in criticos)).encode()).hexdigest()
    estado_path = os.path.join(repo_root, ARQUIVO_ESTADO)
    estado = _carregar(estado_path)
    ultimo = datetime.datetime.fromisoformat(estado["quando"]) if estado.get("quando") else None
    if estado.get("assinatura") == assinatura and ultimo and (agora - ultimo).total_seconds() < 6 * 3600:
        return False
    with open(estado_path, "w", encoding="utf-8") as f:
        json.dump({"assinatura": assinatura, "quando": agora.isoformat(timespec="seconds")}, f)
    texto = "\n\n".join(f"• {a['titulo']}" for a in criticos)[:900]
    ps = ("Add-Type -AssemblyName PresentationFramework; "
          "[System.Windows.MessageBox]::Show($env:SAUDE_TEXTO, 'Quadro Diário PDL — ALERTA', 'OK', 'Warning') | Out-Null")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     env={**os.environ, "SAUDE_TEXTO": texto})
    return True


def criticos_pendentes(repo_root: str = REPO_ROOT, bases_dir: str | None = None, mb51=None, agora: datetime.datetime | None = None) -> list[dict]:
    """Alertas CRÍTICOS não resolvidos dos 4 tipos (sequência, extração, dia em aberto/fechado
    incompleto, código sem commit). Usado como portão do push: qualquer um cancela o envio."""
    return [a for a in verificar(repo_root=repo_root, bases_dir=bases_dir, agora=agora, mb51=mb51) if a["nivel"] == "critico"]


# Commit da Checklist de Bipagem 2.0 (opção B, Fernando 2026-09-26): a Checklist trabalha direto
# em cima da ZMM028/MB51 e não depende do congelamento — um push que só mexe nela passa pelo
# portão mesmo com alerta pendente. "Só nela" = arquivos desta lista e, no index.html, só a
# linha da constante CHECKLIST_BIPAGEM.
ARQUIVOS_SO_CHECKLIST = {"checklist_bipagem.json", "index.html"}
LINHA_CHECKLIST_NO_INDEX = "const CHECKLIST_BIPAGEM = "
SHA_VAZIO = "0" * 40


def commits_so_da_checklist(repo_root: str, faixas: list[tuple[str, str]]) -> bool:
    """`faixas`: (sha remoto, sha local) de cada ref sendo enviada (stdin do hook pre-push).
    True só se TODA a diferença for da Checklist; na dúvida (ref nova, erro do git), False."""
    if not faixas:
        return False
    for remoto, local in faixas:
        if local == SHA_VAZIO:
            continue  # apagando uma ref remota: nada de conteúdo sendo enviado
        if remoto == SHA_VAZIO:
            return False
        r = _git(repo_root, "diff", "--name-only", f"{remoto}..{local}")
        if r.returncode != 0:
            return False
        arquivos = {l.strip() for l in r.stdout.splitlines() if l.strip()}
        if not arquivos or not arquivos <= ARQUIVOS_SO_CHECKLIST:
            return False
        if "index.html" in arquivos:
            d = _git(repo_root, "diff", "-U0", f"{remoto}..{local}", "--", "index.html")
            if d.returncode != 0:
                return False
            mudadas = [l[1:] for l in d.stdout.splitlines()
                       if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            if any(not l.startswith(LINHA_CHECKLIST_NO_INDEX) for l in mudadas):
                return False
    return True


def _faixas_do_stdin(texto: str) -> list[tuple[str, str]]:
    """Linhas '<ref local> <sha local> <ref remota> <sha remoto>' que o git manda pro pre-push."""
    faixas = []
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) == 4:
            faixas.append((partes[3], partes[1]))
    return faixas


def portao_de_push(repo_root: str = REPO_ROOT, bases_dir: str | None = None, mb51=None,
                   faixas: list[tuple[str, str]] | None = None) -> int:
    """0 = pode subir; 1 = PUSH CANCELADO (sem perguntar). Se o próprio verificador falhar,
    também cancela (falha fechada) — portão que falha aberto é silêncio disfarçado. `faixas`
    (só no hook): push que só mexe na Checklist de Bipagem passa direto (opção B)."""
    if faixas and commits_so_da_checklist(repo_root, faixas):
        imprimir("Portão de push: só a Checklist de Bipagem mudou — liberado sem checar os alertas do congelamento.")
        return 0
    try:
        criticos = criticos_pendentes(repo_root, bases_dir, mb51)
    except Exception as e:  # noqa: BLE001
        imprimir(f"PUSH CANCELADO: não consegui verificar a saúde do sistema ({type(e).__name__}: {e}).")
        return 1
    if criticos:
        imprimir(formatar_banner(criticos))
        imprimir(f"PUSH CANCELADO: {len(criticos)} alerta(s) crítico(s) pendente(s). Resolva-os e tente de novo.")
        return 1
    imprimir("Portão de push: nenhum alerta crítico — liberado.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rapido", action="store_true", help="não lê a MB51 (calendário de dias úteis no lugar)")
    p.add_argument("--notificar", action="store_true", help="grava alertas_saude.js e abre janela se houver crítico")
    p.add_argument("--bases-dir", default=None)
    p.add_argument("--gate", action="store_true", help="portão de push: sai com 1 (cancela) se houver alerta crítico")
    args = p.parse_args()
    if args.gate:
        faixas = _faixas_do_stdin(sys.stdin.read()) if not sys.stdin.isatty() else []
        raise SystemExit(portao_de_push(bases_dir=args.bases_dir, faixas=faixas))
    agora = datetime.datetime.now()
    alertas = verificar(bases_dir=args.bases_dir, agora=agora, ler_mb51=not args.rapido)
    imprimir(formatar_banner(alertas))
    if args.notificar:
        print("Gravado:", gravar_alertas_js(REPO_ROOT, alertas, agora))
        if notificar_janela(alertas, REPO_ROOT, agora):
            print("Janela de alerta aberta.")


if __name__ == "__main__":
    main()
