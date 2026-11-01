"""Testes da leitura e da validacao das planilhas."""

from __future__ import annotations

import io

from conftest import construir_fmeca

from fmeca_spares import ler_fmeca
from fmeca_spares.leitura import (
    NATUREZA_CONSUMIVEL,
    NATUREZA_PECA,
    classificar_natureza,
    normalizar,
    _numero,
)


# -- utilitarios ------------------------------------------------------------

def test_normalizar_remove_acento_e_colapsa_espaco():
    assert normalizar("  Válvula   EXPIRATÓRIA ") == "valvula expiratoria"
    assert normalizar("RPN\n(S × O × D)") == "rpn (s × o × d)"
    assert normalizar(None) == ""


def test_classificar_natureza():
    assert classificar_natureza("Consumível") == NATUREZA_CONSUMIVEL
    assert classificar_natureza("consumivel") == NATUREZA_CONSUMIVEL
    assert classificar_natureza("Peça") == NATUREZA_PECA
    assert classificar_natureza("Peca ") == NATUREZA_PECA
    assert classificar_natureza("acessório") is None
    assert classificar_natureza(None) is None


def test_numero_aceita_formatos_brasileiro_e_ingles():
    assert _numero("1.234,56") == 1234.56
    assert _numero("1234.56") == 1234.56
    assert _numero("30") == 30.0
    assert _numero("R$ 1.200,00") == 1200.0
    assert _numero("") is None
    assert _numero("trinta") is None


# -- formulario FMECA -------------------------------------------------------

def test_le_formulario_minimo():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[
                (1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, 30),
                (2, "Filtro B", "Proteção", "Função B", "Consumível", 24, 12, 5),
            ],
            modos=[
                (1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20),
                (2, "2.1", "Filtro B", "Proteção", "Modo B1", 3, 4, 2, 24, 12),
            ],
        )
    )
    assert fmeca.validacao.ok
    assert fmeca.validacao.avisos == []
    assert [c.id for c in fmeca.componentes] == [1, 2]
    assert fmeca.componentes[1].consumivel is True
    assert fmeca.componentes[0].consumivel is False
    assert len(fmeca.modos) == 2
    assert fmeca.modos[0].criticidade_calculada == 20
    assert fmeca.modos[0].rpn_calculado == 60
    assert [c.lead_time_dias for c in fmeca.componentes] == [30, 5]
    assert fmeca.equipamento == "Equipamento de teste"


def test_colunas_localizadas_por_nome_nao_por_posicao():
    """Uma coluna extra no meio nao deve deslocar a leitura."""
    wb_bytes = construir_fmeca(
        componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, 15)],
        modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
    )
    # insere uma coluna "Fontes" antes de RPN, como na versao antiga do formulario
    import openpyxl

    wb = openpyxl.load_workbook(wb_bytes)
    ws = wb["Matriz de componentes"]
    ws.insert_cols(6)
    ws.cell(5, 6, "Fontes")
    ws.cell(6, 6, "ECRI; MEG")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    fmeca = ler_fmeca(buffer)
    assert fmeca.validacao.ok
    assert fmeca.componentes[0].rpn == 60
    assert fmeca.componentes[0].criticidade == 20
    assert fmeca.componentes[0].lead_time_dias == 15


def test_nota_fora_da_escala_e_erro():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20)],
            modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 11, 3, 132, 44)],
        )
    )
    assert not fmeca.validacao.ok
    assert any("fora da escala" in e for e in fmeca.validacao.erros)


def test_rpn_declarado_divergente_gera_aviso():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 99, 20)],
            modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 99, 20)],
        )
    )
    assert fmeca.validacao.ok
    assert any("difere de S x O x D" in a for a in fmeca.validacao.avisos)


def test_criticidade_da_matriz_divergente_do_maximo_dos_modos():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 99)],
            modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
        )
    )
    assert any("máximo dos modos" in a for a in fmeca.validacao.avisos)


def test_modo_sem_componente_correspondente_e_erro():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20)],
            modos=[(9, "9.1", "Fantasma", "Pneumático", "Modo X", 4, 5, 3, 60, 20)],
        )
    )
    assert not fmeca.validacao.ok


def test_componente_sem_modo_gera_aviso():
    fmeca = ler_fmeca(
        componentes_sem_modo := construir_fmeca(
            componentes=[
                (1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20),
                (2, "Peça B", "Pneumático", "Função B", "Peça", None, None),
            ],
            modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
        )
    )
    assert fmeca.validacao.ok
    assert any("não tem nenhum modo" in a for a in fmeca.validacao.avisos)
    assert componentes_sem_modo is not None


def test_aba_ausente_e_erro():
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Outra coisa"
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    fmeca = ler_fmeca(buffer)
    assert not fmeca.validacao.ok
    assert len(fmeca.validacao.erros) >= 2


# -- lead time na matriz de componentes ------------------------------------

_MODO_A1 = [(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)]


def test_lead_time_aceita_texto_com_virgula_decimal():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, "12,5")],
            modos=_MODO_A1,
        )
    )
    assert fmeca.validacao.ok
    assert fmeca.componentes[0].lead_time_dias == 12.5


def test_lead_time_em_branco_gera_aviso():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, None)],
            modos=_MODO_A1,
        )
    )
    assert fmeca.validacao.ok
    assert fmeca.componentes[0].lead_time_dias is None
    assert any("lead time em branco" in a for a in fmeca.validacao.avisos)


def test_lead_time_negativo_e_erro():
    fmeca = ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, -3)],
            modos=_MODO_A1,
        )
    )
    assert not fmeca.validacao.ok
    assert any("lead time negativo" in e for e in fmeca.validacao.erros)
    assert fmeca.componentes[0].lead_time_dias is None


def test_falta_da_coluna_de_lead_time_e_erro_bloqueante():
    import openpyxl

    buffer = construir_fmeca(
        componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20, 15)],
        modos=_MODO_A1,
    )
    wb = openpyxl.load_workbook(buffer)
    wb["Matriz de componentes"].cell(5, 8, "Outra coisa")
    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    fmeca = ler_fmeca(saida)
    assert not fmeca.validacao.ok
    assert any("Lead time (dias)" in e for e in fmeca.validacao.erros)


# -- estudo de caso ---------------------------------------------------------

def test_estudo_de_caso_le_sem_inconsistencia(fmeca_caso):
    assert fmeca_caso.validacao.ok
    assert fmeca_caso.validacao.avisos == []
    assert len(fmeca_caso.componentes) == 23
    assert len(fmeca_caso.modos) == 52
    assert fmeca_caso.equipamento == "Ventilador pulmonar"
    assert fmeca_caso.modelo == "Hamilton C6"
    assert fmeca_caso.setor == "UTI"


def test_estudo_de_caso_aritmetica_de_todos_os_modos(fmeca_caso):
    for modo in fmeca_caso.modos:
        assert modo.rpn == modo.rpn_calculado, modo.sub_id
        assert modo.criticidade == modo.criticidade_calculada, modo.sub_id


def test_estudo_de_caso_matriz_igual_ao_maximo_dos_modos(fmeca_caso):
    for comp in fmeca_caso.componentes:
        modos = fmeca_caso.modos_de(comp.id)
        assert modos, comp.id
        assert comp.criticidade == max(m.criticidade_calculada for m in modos)
        assert comp.rpn == max(m.rpn_calculado for m in modos)


def test_estudo_de_caso_tem_lead_time_em_todos_os_componentes(fmeca_caso):
    assert all(c.lead_time_dias is not None for c in fmeca_caso.componentes)


# -- robustez do mapeamento de colunas -------------------------------------

def _com_coluna_extra(titulo: str, antes_de: int):
    """Insere uma coluna na aba de modos, antes do indice informado (1-based)."""
    import openpyxl

    buffer = construir_fmeca(
        componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20)],
        modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
    )
    wb = openpyxl.load_workbook(buffer)
    ws = wb["Modos de falha"]
    ws.insert_cols(antes_de)
    ws.cell(4, antes_de, titulo)
    ws.cell(5, antes_de, "conteúdo qualquer")
    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    return saida


def test_coluna_que_comeca_com_o_nao_rouba_a_nota_de_ocorrencia():
    """
    Regressao: por prefixo, "Observações" casava com o alvo "o" e levava a
    coluna da Ocorrencia, que passava a ser lida como vazia — sem erro, so um
    aviso, e o componente seguia sem taxa de falha nem exposicao anual.
    """
    fmeca = ler_fmeca(_com_coluna_extra("Observações", 12))
    assert fmeca.validacao.ok
    modo = fmeca.modos[0]
    assert (modo.ocorrencia, modo.severidade, modo.deteccao_nota) == (4, 5, 3)


def test_colunas_que_comecam_com_s_e_d_nao_roubam_as_notas():
    for titulo in ("Situação", "Data da revisão", "Observações"):
        fmeca = ler_fmeca(_com_coluna_extra(titulo, 12))
        modo = fmeca.modos[0]
        assert (modo.ocorrencia, modo.severidade, modo.deteccao_nota) == (4, 5, 3), titulo


def test_cabecalho_de_nota_por_extenso_tambem_e_aceito():
    import openpyxl

    buffer = construir_fmeca(
        componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20)],
        modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
    )
    wb = openpyxl.load_workbook(buffer)
    ws = wb["Modos de falha"]
    ws.cell(4, 12, "Ocorrência")
    ws.cell(4, 13, "Severidade")
    ws.cell(4, 14, "Detecção")
    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    fmeca = ler_fmeca(saida)
    assert fmeca.validacao.ok
    assert fmeca.modos[0].ocorrencia == 4


def test_falta_de_coluna_de_nota_e_erro_bloqueante():
    import openpyxl

    buffer = construir_fmeca(
        componentes=[(1, "Peça A", "Pneumático", "Função A", "Peça", 60, 20)],
        modos=[(1, "1.1", "Peça A", "Pneumático", "Modo A1", 4, 5, 3, 60, 20)],
    )
    wb = openpyxl.load_workbook(buffer)
    ws = wb["Modos de falha"]
    ws.cell(4, 12, "Outra coisa")  # sobrescreve o cabecalho "O"
    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    fmeca = ler_fmeca(saida)
    assert not fmeca.validacao.ok
    assert any("coluna de nota O" in e for e in fmeca.validacao.erros)
