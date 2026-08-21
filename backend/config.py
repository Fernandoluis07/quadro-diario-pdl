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

# Hash SHA-256 (nunca a senha em texto puro — este arquivo vai pro GitHub) da senha
# que libera o reprocessamento forçado de um dia já congelado (ver backend/cabecalho.py).
SENHA_FORCAR_RECONGELAMENTO_SHA256 = "3d14c2d4e4ced81e459e4ace7c01466a700000fb94a3bbe944a55fb92693e879"

# Depósitos válidos (seção 3 da especificação). Vazio/em branco é tratado como D009.
DEPOSITO_D009 = "D009"
DEPOSITO_D016 = "D016"
DEPOSITOS_VALIDOS = {DEPOSITO_D009, DEPOSITO_D016}

# Tipos de movimento (BWART) por categoria — Bloco 1 (fonte MB51).
BWART_ATENDIMENTO = {"201", "221", "261", "601", "122", "833", "921"}
BWART_ESTORNO = {"202", "222", "262", "602", "834", "123"}
BWART_RECEBIMENTO = {"101", "835"}
# 601/833 também entram em BWART_ATENDIMENTO acima — Intercompany é uma leitura adicional
# sobre as MESMAS movimentações (por documento único, não por linha), não uma categoria à parte.
BWART_INTERCOMPANY = {"601", "833"}
