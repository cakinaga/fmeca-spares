"""
Exportacao do resultado: planilha de decisao, resumo, parametros e validacao.

A aba de parametros registra os limiares e custos usados, para que o resultado
possa ser conferido e repetido.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .leitura import FMECA, RelatorioValidacao
from .modelo import (
    DecisaoComponente,
    ordenar_para_relatorio,
    resumo_por_zona,
)
from .parametros import (
    DIARIA_UTI_II_SUS,
    DIARIA_UTI_III_SUS,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    Zona,
)

FONTE_DIARIA_SUS = (
    "Diária de UTI {tipo} adulto da tabela do SUS, procedimento SIGTAP "
    "{codigo}, Portaria GM/MS nº 160, de 25 de fevereiro de 2022."
)


def _origem_custo(custo: ParametrosCusto) -> str:
    """Nota de procedencia do custo de leito bloqueado, para a aba de parametros."""
    if custo.custo_leito_dia == DIARIA_UTI_II_SUS:
        return FONTE_DIARIA_SUS.format(tipo="II", codigo="08.02.01.008-3")
    if custo.custo_leito_dia == DIARIA_UTI_III_SUS:
        return FONTE_DIARIA_SUS.format(tipo="III", codigo="08.02.01.009-1")
    if custo.custo_leito_dia == 0:
        return "Não informado: o Downtime Cost sai zerado; as zonas não dependem dele."
    return "Valor informado pelo usuário; registre a fonte no relatório."

AZUL = "1F3864"
FINA = Side(style="thin", color="BFBFBF")

COR_ZONA = {
    Zona.ESTOQUE_SEGURANCA: "F4CCCC",
    Zona.PONTO_PEDIDO: "FFF2CC",
    Zona.SOB_DEMANDA: "D9EAD3",
}

COLUNAS = [
    ("ID", 6, "id"),
    ("Componente / peça", 42, "nome"),
    ("Subsistema", 22, "subsistema"),
    ("Natureza", 13, "natureza"),
    ("S", 5, "severidade"),
    ("O", 5, "ocorrencia"),
    ("Criticidade (S × O)", 13, "criticidade"),
    ("RPN", 8, "rpn"),
    ("Modo dimensionante", 34, "modo"),
    ("Lead time (dias)", 12, "lead_time"),
    ("Faixa de criticidade", 14, "faixa_c"),
    ("Faixa de lead time", 13, "faixa_l"),
    ("Zona de estoque", 24, "zona"),
    ("λ (falha/ano/unidade)", 14, "taxa"),
    ("DC evitável por evento (R$)", 16, "dc"),
    ("DC anual esperado (R$)", 16, "dc_anual"),
    ("Justificativa", 70, "justificativa"),
]


def _celula_valor(d: DecisaoComponente, chave: str):
    c = d.componente
    if chave == "id":
        return d.id
    if chave == "nome":
        return d.nome
    if chave == "subsistema":
        return c.subsistema
    if chave == "natureza":
        return c.natureza
    if chave == "severidade":
        return d.severidade
    if chave == "ocorrencia":
        return d.ocorrencia
    if chave == "criticidade":
        return d.criticidade
    if chave == "rpn":
        return d.rpn
    if chave == "modo":
        m = d.modo_dimensionante
        return f"{m.sub_id} — {m.modo}" if m and m.modo else None
    if chave == "lead_time":
        return d.lead_time_dias
    if chave == "faixa_c":
        return d.faixa_criticidade.rotulo if d.faixa_criticidade else None
    if chave == "faixa_l":
        return d.faixa_lead_time.rotulo if d.faixa_lead_time else None
    if chave == "zona":
        return d.zona.rotulo if d.zona else "Sem zona atribuída"
    if chave == "taxa":
        return d.taxa_falha_anual
    if chave == "dc":
        return d.dc_evitavel
    if chave == "dc_anual":
        return d.dc_anual_esperado
    if chave == "justificativa":
        return d.justificativa
    return None


def _cabecalho(ws, linha: int, colunas: Sequence[tuple[str, int, str]]) -> None:
    for col, (titulo, largura, _) in enumerate(colunas, start=1):
        cel = ws.cell(linha, col, titulo)
        cel.font = Font(bold=True, color="FFFFFF", size=9)
        cel.fill = PatternFill("solid", fgColor=AZUL)
        cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = largura
    ws.row_dimensions[linha].height = 34


def _aba_decisao(wb: Workbook, fmeca: FMECA, decisoes: Sequence[DecisaoComponente]) -> None:
    ws = wb.active
    ws.title = "Decisão"

    t = ws.cell(1, 1, "Decisão de estoque de spare parts — Etapa 2")
    t.font = Font(bold=True, size=13, color=AZUL)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUNAS))

    s = ws.cell(
        2,
        1,
        f"{fmeca.identificacao} · {fmeca.setor or '—'} · "
        f"gerado em {datetime.now(timezone.utc).astimezone():%d/%m/%Y %H:%M}",
    )
    s.font = Font(size=9, italic=True, color="7F7F7F")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(COLUNAS))

    _cabecalho(ws, 4, COLUNAS)
    for i, d in enumerate(ordenar_para_relatorio(decisoes)):
        linha = 5 + i
        for col, (_, _, chave) in enumerate(COLUNAS, start=1):
            cel = ws.cell(linha, col, _celula_valor(d, chave))
            cel.font = Font(size=9)
            cel.border = Border(bottom=FINA)
            if chave in {"id", "severidade", "ocorrencia", "criticidade", "rpn",
                         "lead_time", "faixa_c", "faixa_l"}:
                cel.alignment = Alignment(horizontal="center")
            elif chave in {"nome", "subsistema", "modo", "justificativa"}:
                cel.alignment = Alignment(wrap_text=True, vertical="top")
            if chave in {"dc", "dc_anual"}:
                cel.number_format = "#,##0.00"
            if chave == "taxa":
                cel.number_format = "0.0000"
            if chave == "zona" and d.zona is not None:
                cel.fill = PatternFill("solid", fgColor=COR_ZONA[d.zona])
                cel.font = Font(size=9, bold=True)
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(COLUNAS))}{4 + len(decisoes)}"


def _aba_resumo(wb: Workbook, decisoes: Sequence[DecisaoComponente]) -> None:
    ws = wb.create_sheet("Resumo")
    for col, (titulo, largura) in enumerate(
        [("Zona", 28), ("Componentes", 13), ("DC anual esperado (R$)", 20),
         ("DC evitável por evento (R$)", 22), ("IDs", 34)],
        start=1,
    ):
        cel = ws.cell(1, col, titulo)
        cel.font = Font(bold=True, color="FFFFFF", size=10)
        cel.fill = PatternFill("solid", fgColor=AZUL)
        cel.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = largura
    ws.row_dimensions[1].height = 30

    for i, (zona, dados) in enumerate(resumo_por_zona(decisoes).items(), start=2):
        ws.cell(i, 1, zona).font = Font(size=10, bold=True)
        ws.cell(i, 2, dados["componentes"]).alignment = Alignment(horizontal="center")
        ws.cell(i, 3, dados["dc_anual_total"]).number_format = "#,##0.00"
        ws.cell(i, 4, dados["dc_evitavel_total"]).number_format = "#,##0.00"
        ws.cell(i, 5, ", ".join(str(x) for x in dados["ids"]))


def _aba_parametros(
    wb: Workbook,
    custo: ParametrosCusto,
    zonas: ParametrosZona,
    escala: ParametrosOcorrencia,
    deteccao: ParametrosDeteccao,
    escala_lida: tuple | None = None,
) -> None:
    ws = wb.create_sheet("Parâmetros")
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 70

    linha = [1]

    def secao(titulo: str) -> None:
        cel = ws.cell(linha[0], 1, titulo)
        cel.font = Font(bold=True, size=11, color=AZUL)
        linha[0] += 1

    def item(rotulo: str, valor, nota: str = "") -> None:
        ws.cell(linha[0], 1, rotulo).font = Font(size=10)
        v = ws.cell(linha[0], 2, valor)
        v.font = Font(size=10, bold=True)
        v.alignment = Alignment(horizontal="center")
        n = ws.cell(linha[0], 3, nota)
        n.font = Font(size=9, italic=True, color="7F7F7F")
        n.alignment = Alignment(wrap_text=True, vertical="top")
        linha[0] += 1

    secao("Limiares das zonas")
    item("Criticidade — piso da faixa alta", zonas.criticidade_alta,
         "A partir deste S × O, a falha compromete uma função essencial e "
         "acontece com frequência pelo menos ocasional.")
    item("Criticidade — piso da faixa média", zonas.criticidade_media,
         "A partir deste S × O, a falha é grave, ainda que rara, ou ocasional, "
         "ainda que de efeito leve.")
    item("Lead time — teto da faixa curta (dias)", zonas.lead_time_curto_dias,
         "Até este prazo, a peça chega rápido o bastante para o equipamento "
         "voltar a operar logo depois da falha.")
    item("Lead time — teto da faixa média (dias)", zonas.lead_time_longo_dias,
         "Acima deste prazo, a espera deixa o equipamento parado por tempo "
         "demais para ser coberta por uma compra feita só depois da falha.")
    linha[0] += 1

    secao("Custo de indisponibilidade")
    item("Custo de leito bloqueado (R$/dia)", custo.custo_leito_dia, _origem_custo(custo))
    item("Equipamentos na frota da unidade", custo.frota_equipamentos)
    linha[0] += 1

    secao("Escala de Ocorrência → taxa de falha")
    item("Origem da escala",
         "aba «Tabela»" if escala.faixas == escala_lida else "padrão do modelo",
         "Faixas de λ lidas da escala de Ocorrência do formulário."
         if escala.faixas == escala_lida
         else "A escala da aba «Tabela» não foi usada; ver a aba Validação.")
    item("Posição tomada dentro da faixa", escala.posicao_na_faixa,
         "0,5 = média da faixa; 1 = teto da faixa, cenário mais desfavorável.")
    for minimo, maximo, piso, teto in escala.faixas:
        item(f"O {minimo}–{maximo} → λ", piso + (teto - piso) * escala.posicao_na_faixa,
             f"faixa declarada na escala: {piso:g} a {teto:g} falha/ano por unidade")
    linha[0] += 1

    secao("Detecção")
    item("D a partir da qual a falha é oculta", deteccao.limiar_oculta,
         "Marca o modo na justificativa. Não altera a zona de estoque.")


def _aba_validacao(wb: Workbook, validacao: RelatorioValidacao) -> None:
    ws = wb.create_sheet("Validação")
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 120
    for col, titulo in enumerate(["Tipo", "Mensagem"], start=1):
        cel = ws.cell(1, col, titulo)
        cel.font = Font(bold=True, color="FFFFFF", size=10)
        cel.fill = PatternFill("solid", fgColor=AZUL)

    linha = 2
    if not validacao.erros and not validacao.avisos:
        ws.cell(linha, 1, "—")
        ws.cell(linha, 2, "Nenhuma inconsistência encontrada na leitura dos dados.")
        return
    for tipo, mensagens in (("Erro", validacao.erros), ("Aviso", validacao.avisos)):
        for msg in mensagens:
            ws.cell(linha, 1, tipo).font = Font(size=10, bold=(tipo == "Erro"))
            cel = ws.cell(linha, 2, msg)
            cel.font = Font(size=10)
            cel.alignment = Alignment(wrap_text=True, vertical="top")
            linha += 1


def construir_planilha(
    fmeca: FMECA,
    decisoes: Sequence[DecisaoComponente],
    custo: ParametrosCusto,
    zonas: ParametrosZona,
    escala: ParametrosOcorrencia,
    validacao: RelatorioValidacao | None = None,
    deteccao: ParametrosDeteccao | None = None,
) -> Workbook:
    deteccao = deteccao or ParametrosDeteccao()
    wb = Workbook()
    _aba_decisao(wb, fmeca, decisoes)
    _aba_resumo(wb, decisoes)
    _aba_parametros(wb, custo, zonas, escala, deteccao, fmeca.escala_ocorrencia)
    _aba_validacao(wb, validacao or fmeca.validacao)
    return wb


def exportar_xlsx(
    fmeca: FMECA,
    decisoes: Sequence[DecisaoComponente],
    custo: ParametrosCusto,
    zonas: ParametrosZona,
    escala: ParametrosOcorrencia,
    validacao: RelatorioValidacao | None = None,
    destino: str | Path | None = None,
    deteccao: ParametrosDeteccao | None = None,
) -> bytes:
    """Gera a planilha de resultado. Devolve os bytes e, se pedido, grava em disco."""
    wb = construir_planilha(fmeca, decisoes, custo, zonas, escala, validacao, deteccao)
    buffer = io.BytesIO()
    wb.save(buffer)
    dados = buffer.getvalue()
    if destino is not None:
        Path(destino).write_bytes(dados)
    return dados


# casas decimais por coluna no CSV; as demais colunas usam duas
DECIMAIS_CSV = {"taxa": 4, "lead_time": 1}


def exportar_csv(decisoes: Sequence[DecisaoComponente]) -> str:
    """Tabela de decisao em CSV com separador ponto e virgula e decimal virgula."""
    import csv

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\n")
    escritor.writerow([titulo for titulo, _, _ in COLUNAS])
    for d in ordenar_para_relatorio(decisoes):
        linha = []
        for _, _, chave in COLUNAS:
            valor = _celula_valor(d, chave)
            if isinstance(valor, float):
                casas = DECIMAIS_CSV.get(chave, 2)
                texto = f"{valor:.{casas}f}"
                if chave in DECIMAIS_CSV:
                    # remove zeros a direita, mantendo ao menos uma casa
                    texto = texto.rstrip("0").rstrip(".") or "0"
                    if "." not in texto:
                        texto += ".0"
                linha.append(texto.replace(".", ","))
            else:
                linha.append("" if valor is None else str(valor))
        escritor.writerow(linha)
    return buffer.getvalue()
