r"""Leitura da planilha manual diária (planilha_manual_quadro_diario.xlsx) usada pelo
Cabeçalho — 4 abas:

- 'Indicadores Diarios': os 5 indicadores 100% manuais (Notas Aguardando Lancamento,
  NF Pendente Faturamento, Devolucao, Scanner Documentos, Intercompany), uma linha por
  dia. Intercompany é manual aqui — substitui o cálculo automático via BWART que existia
  antes em indicadores.intercompany()/config.BWART_INTERCOMPANY (decisão de negócio).
- 'Pontos e Avisos': texto livre dos painéis 'Pontos de Atenção' e 'Avisos Importantes'
  da tela Início, uma seção marcada por linha de cabeçalho ('PONTOS DE ATENÇÃO' /
  'AVISOS IMPORTANTES'), bullets nas linhas seguintes até a próxima seção ou o fim.
- 'Datas Importantes': matriz de férias/ausências (Nome, Periodo Inicio, Periodo Fim,
  Duracao (dias), Aprovacao, Status).
- 'Recebimento do Dia': PROPOSITALMENTE não lida aqui — sem fonte de dado definida.

Uso:
    from backend import planilha_manual
    indicadores_por_dia = planilha_manual.ler_indicadores_diarios(caminho)
    paineis = planilha_manual.ler_pontos_avisos(caminho)
    ferias = planilha_manual.ler_datas_importantes(caminho)
"""

from __future__ import annotations

import unicodedata

import pandas as pd

ABA_INDICADORES = "Indicadores Diarios"
ABA_PONTOS_AVISOS = "Pontos e Avisos"
ABA_DATAS_IMPORTANTES = "Datas Importantes"

# cabeçalho exato da aba -> chave usada no resto do projeto (bate com os nomes já
# usados em historico_mb51.json/HISTORICO_MB51 pro intercompany, e são novas chaves
# pros outros 4 — não existiam em historico_manuais.py, que tinha um layout antigo
# sem Intercompany e com Reservas Pendentes/Pendências Atendimento Linhas, que agora
# são automáticas via MB25 e não vêm mais desta planilha).
_COLUNAS_INDICADORES = {
    "Notas Aguardando Lancamento": "notas_aguardando_lancamento",
    "NF Pendente Faturamento": "nf_pendente_faturamento",
    "Devolucao": "devolucao",
    "Scanner Documentos": "scanner_documentos",
    "Intercompany": "intercompany",
}

_COLUNAS_DATAS_IMPORTANTES = {"Nome", "Periodo Inicio", "Periodo Fim", "Duracao (dias)", "Aprovacao", "Status"}

_SECAO_PONTOS_ATENCAO = "PONTOS DE ATENCAO"
_SECAO_AVISOS_IMPORTANTES = "AVISOS IMPORTANTES"


def sem_acento_maiusculo(texto: str) -> str:
    """Normaliza pra comparação tolerante a acento/caixa (cabeçalhos de seção da aba
    'Pontos e Avisos' e valores de Status da aba 'Datas Importantes')."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip().upper()


def _detectar_linha_cabecalho(caminho: str, sheet_name: str, colunas_esperadas: set[str], max_linhas: int = 15) -> int:
    """Mesma ideia de extratos._detectar_linha_cabecalho, mas com sheet_name — as abas
    desta planilha têm um bloco de título/instruções antes do cabeçalho de verdade."""
    bruto = pd.read_excel(caminho, sheet_name=sheet_name, header=None, nrows=max_linhas, dtype=object)
    for i, row in bruto.iterrows():
        valores = {str(v).strip() for v in row.values if pd.notna(v)}
        if colunas_esperadas.issubset(valores):
            return i
    raise ValueError(
        f"Não encontrei a linha de cabeçalho esperada {colunas_esperadas} "
        f"nas primeiras {max_linhas} linhas da aba '{sheet_name}'."
    )


def ler_indicadores_diarios(caminho: str) -> dict[str, dict]:
    """Retorna {'aaaa-mm-dd': {5 campos}, ...} — uma entrada por linha preenchida."""
    colunas_esperadas = {"Data", *_COLUNAS_INDICADORES}
    linha_cabecalho = _detectar_linha_cabecalho(caminho, ABA_INDICADORES, colunas_esperadas)
    df = pd.read_excel(caminho, sheet_name=ABA_INDICADORES, header=linha_cabecalho, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(subset=["Data"]).reset_index(drop=True)

    if df.empty:
        return {}

    datas = pd.to_datetime(df["Data"], dayfirst=True, errors="coerce").dt.date
    invalidas = df.loc[datas.isna(), "Data"]
    if len(invalidas):
        raise ValueError(f"Datas inválidas na aba '{ABA_INDICADORES}': {invalidas.tolist()}")

    duplicadas = datas[datas.duplicated()]
    if len(duplicadas):
        raise ValueError(f"Datas duplicadas na aba '{ABA_INDICADORES}': {sorted(set(duplicadas))}")

    for col_planilha in _COLUNAS_INDICADORES:
        vazias = df[col_planilha].isna()
        if vazias.any():
            datas_vazias = datas.loc[vazias].tolist()
            raise ValueError(
                f"Coluna '{col_planilha}' vazia na aba '{ABA_INDICADORES}' pra: {datas_vazias} — preencha antes de continuar."
            )

    valores_por_coluna = {
        chave_json: df[col_planilha].astype(int).tolist() for col_planilha, chave_json in _COLUNAS_INDICADORES.items()
    }
    resultado: dict[str, dict] = {}
    for i, data in enumerate(datas):
        resultado[data.isoformat()] = {chave: valores_por_coluna[chave][i] for chave in _COLUNAS_INDICADORES.values()}
    return dict(sorted(resultado.items()))


def ler_pontos_avisos(caminho: str) -> dict[str, list[str]]:
    """Retorna {'pontos_atencao': [...], 'avisos_importantes': [...]} — cada linha não
    vazia depois de um cabeçalho de seção vira um item de bullet. Linha em branco não
    fecha a seção (só é ignorada) — é o jeito de "remover" um item específico sem
    perder o resto da seção."""
    df = pd.read_excel(caminho, sheet_name=ABA_PONTOS_AVISOS, header=None, dtype=object)
    linhas = [str(v).strip() if pd.notna(v) else "" for v in df.iloc[:, 0]]

    pontos_atencao: list[str] = []
    avisos_importantes: list[str] = []
    secao_atual: list[str] | None = None

    for linha in linhas:
        chave = sem_acento_maiusculo(linha)
        if chave == _SECAO_PONTOS_ATENCAO:
            secao_atual = pontos_atencao
            continue
        if chave == _SECAO_AVISOS_IMPORTANTES:
            secao_atual = avisos_importantes
            continue
        if not linha or secao_atual is None:
            continue
        secao_atual.append(linha)

    return {"pontos_atencao": pontos_atencao, "avisos_importantes": avisos_importantes}


def ler_datas_importantes(caminho: str) -> list[dict]:
    """Retorna uma lista de registros (ordem da planilha preservada):
    {'nome', 'periodo_inicio' (date), 'periodo_fim' (date), 'duracao_dias' (int|None),
    'aprovacao' (str), 'status' (str)}."""
    linha_cabecalho = _detectar_linha_cabecalho(caminho, ABA_DATAS_IMPORTANTES, _COLUNAS_DATAS_IMPORTANTES)
    df = pd.read_excel(caminho, sheet_name=ABA_DATAS_IMPORTANTES, header=linha_cabecalho, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(subset=["Nome"]).reset_index(drop=True)

    registros: list[dict] = []
    for _, row in df.iterrows():
        nome = str(row["Nome"]).strip()
        inicio = pd.to_datetime(row["Periodo Inicio"], dayfirst=True, errors="coerce")
        fim = pd.to_datetime(row["Periodo Fim"], dayfirst=True, errors="coerce")
        if pd.isna(inicio) or pd.isna(fim):
            raise ValueError(f"Período inválido pra '{nome}' na aba '{ABA_DATAS_IMPORTANTES}'.")

        duracao = row.get("Duracao (dias)")
        duracao_dias = int(duracao) if pd.notna(duracao) else None

        registros.append(
            {
                "nome": nome,
                "periodo_inicio": inicio.date(),
                "periodo_fim": fim.date(),
                "duracao_dias": duracao_dias,
                "aprovacao": str(row.get("Aprovacao")).strip() if pd.notna(row.get("Aprovacao")) else "",
                "status": str(row.get("Status")).strip() if pd.notna(row.get("Status")) else "",
            }
        )
    return registros
