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
    "Detecção atual",
    "O",
    "S",
    "D",
    "RPN / (S × O × D)",
    "Criticidade / (S × O)",
]


def construir_fmeca(componentes, modos, com_titulo: bool = True) -> io.BytesIO:
    """
    Monta um formulario FMECA minimo em memoria.

    `componentes`: lista de tuplas
        (id, nome, subsistema, funcao, natureza, rpn, crit, lead_time)
    `modos`: lista de tuplas (id, sub_id, componente, subsistema, modo, O, S, D, rpn, crit)
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
