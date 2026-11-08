"""Fixtures e utilitarios dos testes."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DADOS = RAIZ / "dados"
FMECA_CASO = DADOS / "matriz_componentes_ventilador_uti.xlsx"


CABECALHO_COMPONENTES = [
    "ID",
    "Componente / peça",
    "Subsistema",
    "Função",
    "Natureza",
    "RPN\n(S × O × D)",
    "Criticidade\n(S × O)",
    "Lead time (dias)",
]

CABECALHO_MODOS = [
    "ID",
    "Sub ID",
    "Componente",
    "Subsistema",
    "Modo de falha",
    "Causa",
    "Efeito local",
    "Efeito no equipamento",
    "Efeito no paciente",
    "Forma de detecção",
    "O",
    "S",
    "D",
    "RPN / (S × O × D)",
    "Criticidade / (S × O)",
]


# Secao de Ocorrencia da aba Tabela, no formato do formulario do estudo de caso.
TABELA_OCORRENCIA = [
    ("Ocorrência (O) — frequência da falha",),
    ("Nota", "Descrição / faixa - Taxa de falha por unidade"),
    ("1–2", "Falha muito rara: λ abaixo de 0,5 falha/ano por unidade"),
    ("3–4", "Falha rara: λ entre 0,5 e 0,9 falha/ano por unidade"),
    ("5–6", "Falha ocasional: λ entre 1,0 e 1,9 falha/ano por unidade"),
    ("7–8", "Falha frequente: λ entre 2,0 e 3,9 falha/ano por unidade"),
    ("9–10", "Falha muito frequente: λ acima de 4,0 falha/ano por unidade"),
    ("Detecção (D) — capacidade de detectar antes do efeito",),
    ("Nota", "Descrição / faixa"),
    ("1–2", "Detecção quase certa."),
]


def construir_fmeca(
    componentes, modos, com_titulo: bool = True, tabela=TABELA_OCORRENCIA
) -> io.BytesIO:
    """
    Monta um formulario FMECA minimo em memoria.

    `componentes`: lista de tuplas
        (id, nome, subsistema, funcao, natureza, rpn, crit, lead_time)
    `modos`: lista de tuplas (id, sub_id, componente, subsistema, modo, O, S, D, rpn, crit)
    `tabela`: linhas da aba Tabela, a partir da coluna B; None omite a aba.
    """
    wb = Workbook()

    ws = wb.active
    ws.title = "Matriz de componentes"
    linha = 1
    if com_titulo:
        ws.cell(1, 2, "Matriz de componentes e peças de reposição")
        ws.cell(2, 2, "Equipamento:")
        ws.cell(2, 3, "Equipamento de teste")
        ws.cell(3, 2, "Modelo:")
        ws.cell(3, 3, "Modelo X")
        linha = 5
    for col, titulo in enumerate(CABECALHO_COMPONENTES, start=1):
        ws.cell(linha, col, titulo)
    for i, dados in enumerate(componentes, start=linha + 1):
        for col, valor in enumerate(dados, start=1):
            ws.cell(i, col, valor)

    wm = wb.create_sheet("Modos de falha")
    linha = 1
    if com_titulo:
        wm.cell(1, 1, "Formulário de FMECA")
        wm.cell(2, 1, "Equipamento:")
        wm.cell(2, 3, "Equipamento de teste")
        linha = 4
    for col, titulo in enumerate(CABECALHO_MODOS, start=1):
        wm.cell(linha, col, titulo)
    for i, dados in enumerate(modos, start=linha + 1):
        ident, sub_id, comp, sub, modo, o, s, d, rpn, crit = dados
        valores = [ident, sub_id, comp, sub, modo, None, None, None, None, None, o, s, d, rpn, crit]
        for col, valor in enumerate(valores, start=1):
            wm.cell(i, col, valor)

    if tabela is not None:
        wt = wb.create_sheet("Tabela")
        for i, dados in enumerate(tabela, start=2):
            for col, valor in enumerate(dados, start=2):
                wt.cell(i, col, valor)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


@pytest.fixture(scope="session")
def fmeca_caso():
    from fmeca_spares import ler_fmeca

    if not FMECA_CASO.exists():
        pytest.skip(f"formulario do estudo de caso ausente em {FMECA_CASO}")
    return ler_fmeca(FMECA_CASO)
