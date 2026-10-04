"""Configuração de caminhos e constantes de negócio do Quadro Diário PDL.

Roda direto da pasta de rede da empresa — "08. Quadro Diario\\02. Cabeçalho"
(UNC \\\\fs019flslrv\\DADOS\\...), com "03. Bases" como pasta irmã contendo as
3 extrações SAP + a planilha manual. Única cópia do projeto (produção).
"""

import os

# Pasta de rede onde o usuário substitui as 3 extrações do SAP + a planilha manual
# todo dia, sempre com o mesmo nome de arquivo (sobrescrito).
# IMPORTANTE: sempre usar caminho UNC completo (\\servidor\...), nunca letra de unidade
# mapeada (ex: F:\), pois a letra varia de máquina para máquina.
BASES_DIR = (
    r"\\fs019flslrv\DADOS\ADMINISTRATIVO\GESTÃO E PLANEJAMENTO DE ESTOQUE"
    r"\ALMOXARIFADO - PDL\05. Procedimento\08. Quadro Diario\03. Bases"
)

MB51_FILENAME = "MB51.xlsx"
MB25_FILENAME = "MB25.xlsx"
ZMM028_FILENAME = "ZMM028.xlsx"

# Preço médio por material (aba "Data": Material, Centro, Texto breve material, Preço,
# Moeda) — usado pra calcular o valor em R$ dos indicadores 1/2/5 da tela Gestão de
# Estoque. Fonte de preço independente do saldo atual (ZMM028 só tem Val.total = saldo
# atual × preço, que não serve pra calcular o gap até o mínimo nem pra material zerado).
# ÚNICA fonte de preço — sem cálculo alternativo quando um material VB não está nela
# (ver backend/indicadores.materiais_vb_sem_preco_mm60).
#
# Mora DENTRO do repositório ("01. Calculadora\\Bases", resolvido a partir deste
# arquivo — funciona igual em qualquer máquina/letra de unidade), NÃO na "03. Bases" de
# rede acima: é um preço de REFERÊNCIA atualizado esporadicamente (mensal ou quando
# lembrado), não faz parte da rotina diária das outras 3 planilhas — por isso fica fixo
# junto do código em vez de junto do que é trocado todo dia.
MM60_FILENAME = "MM60.xlsx"
MM60_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Bases")

# Saldo "âncora" de cada material em 01/04/2026 — ponto de partida da reconstrução dia a
# dia do indicador 6 (Avaliação de MRP, tela Gestão de Estoque). Mesma pasta/cadência da
# MM60 acima (referência fixa, atualizada esporadicamente, não faz parte das 3 planilhas
# trocadas todo dia). DOIS arquivos, não um só combinado — decisão explícita de Fernando
# 2026-08-25: rastreabilidade (se um número parecer errado, dá pra saber de qual depósito
# veio) pesa mais que a conveniência de já vir somado, e o código já soma os dois de
# qualquer jeito (ver indicadores._saldo_ancora_combinado). O arquivo D009 tem
# Classificação MRP (é a fonte do universo VB do indicador); o D016 não tem essa coluna —
# só complementa saldo de quem já é VB pelo arquivo D009 (confirmado: os poucos materiais
# exclusivos do D016 são todos ND, comprados direto lá, nunca passam pela ZMM028/D009).
SALDO_ANCORA_D009_FILENAME = "saldo_material_01_04_2026.xlsx"
SALDO_ANCORA_D016_FILENAME = "saldo_material_d016_01_04_2026.xlsx"

# Hash SHA-256 (nunca a senha em texto puro — este arquivo vai pro GitHub) da senha
# que libera o reprocessamento forçado de um dia já congelado (ver backend/cabecalho.py).
SENHA_FORCAR_RECONGELAMENTO_SHA256 = "3d14c2d4e4ced81e459e4ace7c01466a700000fb94a3bbe944a55fb92693e879"

# Depósitos válidos (seção 3 da especificação). Vazio/em branco é tratado como D009.
DEPOSITO_D009 = "D009"
DEPOSITO_D016 = "D016"
DEPOSITOS_VALIDOS = {DEPOSITO_D009, DEPOSITO_D016}

# Tipos de movimento (BWART) por categoria — Bloco 1 (fonte MB51).
BWART_ATENDIMENTO = {"201", "221", "261", "601", "122", "833", "921"}
# 102 = estorno de recebimento (101) — entra como Estorno por decisão de Fernando 2026-09-28
# (970 linhas na MB51 ficavam fora de todos os grupos). O 102 NÃO tira a nota de Recebimentos
# (2026-10-03: contagem bruta, ver indicadores.referencias_recebidas).
BWART_ESTORNO = {"202", "222", "262", "602", "834", "123", "102"}
BWART_RECEBIMENTO = {"101", "835"}
# 601/833 também entram em BWART_ATENDIMENTO acima — Intercompany é uma leitura adicional
# sobre as MESMAS movimentações (por documento único, não por linha), não uma categoria à parte.
BWART_INTERCOMPANY = {"601", "833"}

# Resumo do Mês — quebra do Atendimento em 5 grupos (decisão de Fernando 2026-09-27), todos
# contados em LINHAS da MB51 e somando exatamente "Linhas Atendidas no Mês". 601 = Intercompany
# (saída por remessa SAP), 833 = Transferências (NF de transferência, lançada quase toda pela
# matrícula 4058) — confirmado por Fernando olhando os dados. Diversos = todo o resto de
# BWART_ATENDIMENTO (hoje 122, 221, 921), calculado por exclusão: tipo novo cai aqui sozinho.
# Nada a ver com o card 19 (Intercompany manual da planilha), que é lembrete entre times.
BWART_RESUMO_RESERVAS = {"201"}
BWART_RESUMO_ORDENS = {"261"}
BWART_RESUMO_INTERCOMPANY = {"601"}
BWART_RESUMO_TRANSFERENCIAS = {"833"}

# Checklist de Bipagem (Fase 2): só audita dias a partir desta data. 21–24/09/2026 foram o
# teste da Fase 1 e não são resultado real (decisão de Fernando 2026-09-27).
CHECKLIST_BIPAGEM_INICIO = "2026-09-25"
# Base de bipagem (Power Query sobre o SharePoint) e cadastro de matrículas — ficam em
# "01. Calculadora\\Bases" (gitignored), junto da MM60.
SHAREPOINT_FILENAME = "Share Point.xlsx"
MATRICULA_FILENAME = "Matricula.xlsx"

# Sexta (ou qualquer dia útil) processada numa extração que já traz o fim de semana: estes 4
# indicadores de saldo são RECONSTRUÍDOS desfazendo os movimentos posteriores (backend/
# reconstruir.zmm028_no_fim_do_dia) em vez de usar a foto da ZMM028 tirada depois do sábado.
# Backtest 2026-09-27 (1 a 3 dias desfeitos, 18–23/09): itens com saldo e saldo zero exatos,
# valor com erro de até R$ 2,4 mil; itens sem endereço não enxerga endereço alterado no SAP
# depois do dia (a MB51 não registra). Tirar um nome daqui = volta a usar a foto da extração.
INDICADORES_SALDO_RECONSTRUIDOS = (
    "itens_estoque_com_saldo", "valor_estoque_total", "itens_mrp_saldo_zero", "itens_sem_endereco",
)

# "Já teve baixa/saída real alguma vez" — conceito usado pelo indicador 4 (Materiais
# Nunca Movimentados) e reutilizável por qualquer outro indicador que precise da mesma
# pergunta no futuro. Superset de BWART_ATENDIMENTO: 702 e Z30 são baixa real também,
# não são exceção (confirmados na MB51 real: 48 linhas de 702, 410 de Z30). NÃO conta
# BWART_ESTORNO (são estornos/reversão de uma baixa anterior, não uma baixa em si) nem
# devolução.
# IMPORTANTE: pertencer a este conjunto não basta — uma linha só conta como baixa real
# se a quantidade também for DIFERENTE de zero (ver indicadores._materiais_com_baixa_real
# — checa "!= 0", não só "< 0": baixa nessa planilha costuma vir negativa na prática,
# mas a regra de negócio não depende dessa suposição de sinal). Quantidade 0 é ajuste
# administrativo (fechar/cancelar reserva ou ordem errada), não saída física.
# Validado manualmente por Fernando contra a MB51 real, código por código: 2.637
# materiais VB com saldo - baixa real (qualquer depósito) = 495 nunca movimentados.
BWART_BAIXA_REAL = BWART_ATENDIMENTO | {"702", "Z30"}

# "Entrada" ampla — pra achar a Data de Entrada do indicador 4 (Materiais Nunca
# Movimentados), não basta nota fiscal normal (BWART_RECEBIMENTO): material também
# pode ter entrado no estoque por ajuste de inventário ou outro tipo "não-nota",
# legado ou atual (o saldo positivo na ZMM028 já prova que ENTROU de algum jeito —
# só não sabíamos identificar QUANDO se só olhássemos 101/835). NÃO substitui
# BWART_RECEBIMENTO, que continua sendo só nota fiscal (indicadores "Recebimentos
# D009/D016") — esse conjunto é usado só pra Data de Entrada.
BWART_ENTRADA_AMPLA = BWART_RECEBIMENTO | {"918", "Z15", "Z29", "701", "920"}
