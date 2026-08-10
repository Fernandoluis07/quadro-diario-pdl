"""Configuração de caminhos e constantes de negócio do Quadro Diário PDL."""

# Pasta de rede onde o usuário substitui as 3 extrações do SAP todo dia,
# sempre com o mesmo nome de arquivo (sobrescrito).
# IMPORTANTE: sempre usar caminho UNC completo (\\servidor\...), nunca letra de unidade mapeada
# (ex: F:\), pois a letra varia de máquina para máquina.
BASES_DIR = (
    r"\\fs019flslrv\DADOS\ADMINISTRATIVO\GESTÃO E PLANEJAMENTO DE ESTOQUE"
    r"\ALMOXARIFADO - PDL\05. Procedimento\07. Script Atendimento\Bases"
)

MB51_FILENAME = "mb51.xlsx"
MB25_FILENAME = "mb25.xlsx"
ZMM028_FILENAME = "ZMM028.xlsx"

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
