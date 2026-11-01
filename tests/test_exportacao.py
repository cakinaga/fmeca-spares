"""Testes da exportacao do resultado."""

from __future__ import annotations

import io

import openpyxl

from fmeca_spares import (
    ParametrosCusto,
    ParametrosOcorrencia,
    ParametrosZona,
    decidir,
)
from fmeca_spares.exportacao import COLUNAS, exportar_csv, exportar_xlsx

CUSTO = ParametrosCusto(frota_equipamentos=10)
ZONAS = ParametrosZona()
ESCALA = ParametrosOcorrencia()


def test_xlsx_tem_as_cinco_abas(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    dados = exportar_xlsx(fmeca_caso, decisoes, CUSTO, ZONAS, ESCALA)
    wb = openpyxl.load_workbook(io.BytesIO(dados))
    assert wb.sheetnames == ["Decisão", "Resumo", "Plano de ação", "Parâmetros", "Validação"]


def test_plano_exportado_tem_uma_linha_por_modo_e_alertas_primeiro(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    dados = exportar_xlsx(fmeca_caso, decisoes, CUSTO, ZONAS, ESCALA)
    ws = openpyxl.load_workbook(io.BytesIO(dados))["Plano de ação"]
    assert ws.max_row - 1 == len(fmeca_caso.modos)
    alertas = [ws.cell(r, 1).value for r in range(2, ws.max_row + 1)]
    n = alertas.count("sim")
    assert n > 0
    assert alertas[:n] == ["sim"] * n


def test_xlsx_tem_uma_linha_por_componente(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    dados = exportar_xlsx(fmeca_caso, decisoes, CUSTO, ZONAS, ESCALA)
    ws = openpyxl.load_workbook(io.BytesIO(dados))["Decisão"]
    # cabecalho na linha 4, dados a partir da 5
    ids = [ws.cell(5 + i, 1).value for i in range(len(decisoes))]
    assert sorted(ids) == sorted(d.id for d in decisoes)
    assert ws.max_column == len(COLUNAS)


def test_xlsx_registra_os_parametros(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    dados = exportar_xlsx(fmeca_caso, decisoes, CUSTO, ZONAS, ESCALA)
    ws = openpyxl.load_workbook(io.BytesIO(dados))["Parâmetros"]
    texto = [
        (ws.cell(r, 1).value, ws.cell(r, 2).value)
        for r in range(1, ws.max_row + 1)
    ]
    rotulos = {r for r, _ in texto if r}
    assert any("faixa alta" in r for r in rotulos)
    assert any("leito bloqueado" in r for r in rotulos)
    assert any("frota" in r.lower() for r in rotulos)
    valores = {v for _, v in texto if isinstance(v, (int, float))}
    assert ZONAS.criticidade_alta in valores
    assert CUSTO.custo_leito_dia in valores


def test_csv_tem_cabecalho_e_uma_linha_por_componente(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    texto = exportar_csv(decisoes)
    linhas = texto.strip().splitlines()
    assert len(linhas) == len(decisoes) + 1
    assert linhas[0].split(";")[0] == "ID"
    assert len(linhas[0].split(";")) == len(COLUNAS)


def test_csv_usa_virgula_decimal(fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    texto = exportar_csv(decisoes)
    # valor derivado dos parametros, nao fixado na marra: o componente de
    # maior lead time x o custo de leito bloqueado.
    maior = max(d.dc_evitavel for d in decisoes)
    esperado = f"{maior:.2f}".replace(".", ",")
    assert esperado in texto
    assert "," in esperado


def test_exportacao_grava_em_disco(tmp_path, fmeca_caso):
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    destino = tmp_path / "saida.xlsx"
    dados = exportar_xlsx(fmeca_caso, decisoes, CUSTO, ZONAS, ESCALA, destino=destino)
    assert destino.exists()
    assert destino.read_bytes() == dados


def test_csv_preserva_a_precisao_da_taxa_de_falha(fmeca_caso):
    """
    Regressao: com duas casas decimais, lambda da faixa O 1-2 (0,025) saía
    como 0,03 no CSV, e a exposição anual recalculada a partir da planilha
    não fechava com a do app. A posição 0,05 na faixa reproduz 0,025 com a
    escala atual.
    """
    escala = ParametrosOcorrencia(posicao_na_faixa=0.05)
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=escala)
    texto = exportar_csv(decisoes)
    cabecalho = texto.splitlines()[0].split(";")
    coluna = cabecalho.index("λ (falha/ano/unidade)")
    valores = {
        linha.split(";")[coluna] for linha in texto.strip().splitlines()[1:]
    }
    assert "0,025" in valores
    assert "0,03" not in valores


def test_csv_fecha_a_conta_da_exposicao_anual(fmeca_caso):
    """A planilha exportada tem de permitir refazer DC anual = DC por evento × λ × frota."""
    decisoes = decidir(fmeca_caso, CUSTO, ZONAS, escala_ocorrencia=ESCALA)
    texto = exportar_csv(decisoes)
    cabecalho = texto.splitlines()[0].split(";")
    i_dc = cabecalho.index("DC evitável por evento (R$)")
    i_taxa = cabecalho.index("λ (falha/ano/unidade)")
    i_anual = cabecalho.index("DC anual esperado (R$)")

    def numero(texto_br):
        return float(texto_br.replace(".", "").replace(",", "."))

    for linha in texto.strip().splitlines()[1:]:
        celulas = linha.split(";")
        refeito = numero(celulas[i_dc]) * numero(celulas[i_taxa]) * CUSTO.frota_equipamentos
        assert abs(refeito - numero(celulas[i_anual])) < 0.01, celulas[0]
