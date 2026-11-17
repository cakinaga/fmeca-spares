"""
Interface do modelo de prioridade de estoque de spare parts (Etapa 2).

Rodar com:
    streamlit run app.py

Todo o calculo vive no pacote fmeca_spares; esta tela apenas coleta
parametros, exibe e exporta.
"""

from __future__ import annotations

import html
import importlib
import math
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


def _recarregar_pacote_alterado() -> None:
    """
    Recarrega o pacote fmeca_spares quando o codigo dele muda no disco.

    O Streamlit reexecuta app.py a cada interacao, mas nao reimporta os
    modulos ja carregados. Depois de uma publicacao, o processo continuaria
    com o pacote antigo na memoria e app.py novo quebraria ao usar um nome
    novo. Modulos em ordem de dependencia; o __init__ por ultimo.
    """
    nomes = ["fmeca_spares.parametros", "fmeca_spares.leitura",
             "fmeca_spares.modelo", "fmeca_spares.exportacao", "fmeca_spares"]
    carregados = [sys.modules[n] for n in nomes if n in sys.modules]
    if not carregados:
        return

    def mtime(mod) -> float | None:
        try:
            return os.path.getmtime(mod.__file__)
        except (OSError, TypeError):
            return None

    if all(getattr(m, "_mtime_carga", None) == mtime(m) for m in carregados):
        return
    for nome in nomes:
        if nome in sys.modules:
            mod = importlib.reload(sys.modules[nome])
            mod._mtime_carga = mtime(mod)


_recarregar_pacote_alterado()

from fmeca_spares import (  # noqa: E402
    DIARIA_UTI_II_SUS,
    DIARIA_UTI_III_SUS,
    SEM_ZONA,
    TETO_CRITICIDADE,
    TETO_LEAD_TIME_DIAS,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    Zona,
    agrupar_por_posicao,
    decidir,
    escala_do_formulario,
    ler_fmeca,
    ordenar_para_relatorio,
    resumo_por_zona,
)
from fmeca_spares.leitura import RelatorioValidacao
from fmeca_spares.exportacao import exportar_csv, exportar_xlsx, modelo_em_branco
from fmeca_spares.modelo import MATRIZ_ZONAS
from fmeca_spares.parametros import (
    FaixaCriticidade,
    FaixaLeadTime,
    separar_limiares,
)

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
FMECA_EXEMPLO = DADOS / "matriz_componentes_ventilador_uti.xlsx"

COR_ZONA = {
    Zona.PRIORIDADE_ALTA: "#c0392b",
    Zona.PRIORIDADE_MEDIA: "#d4a017",
    Zona.PRIORIDADE_BAIXA: "#4a7c59",
}
# Tamanhos de fonte que o tema (.streamlit/config.toml) nao permite definir:
# texto da barra lateral e valores do painel-resumo.
CSS_BARRA_LATERAL = """<style>
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] :is(p, li, td, th),
[data-testid="stSidebar"] input {
    font-size: 13px;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] :is(p, li) {
    font-size: calc(0.875rem - 5px);
}
[data-testid="stMetricValue"] > * {
    font-size: calc(1em - 1px);
}
</style>"""

COR_SEM_ZONA = "#888888"
COR_EQUIPAMENTO = "#2e6da4"

# Posicao na faixa de lambda oferecida na interface: media ou teto do intervalo
POSICOES_LAMBDA = {0.5: "Média da faixa", 1.0: "Teto da faixa"}

st.set_page_config(
    page_title="Estoque de spare parts — FMECA e lead time",
    page_icon="🔧",
    layout="wide",
)


# --------------------------------------------------------------------------
# entrada de dados
# --------------------------------------------------------------------------

@st.cache_data
def _modelo_em_branco() -> bytes:
    return modelo_em_branco(FMECA_EXEMPLO)


def _botao_modelo() -> None:
    if not FMECA_EXEMPLO.exists():
        return
    try:
        modelo = _modelo_em_branco()
    except OSError:
        # arquivo bloqueado, por exemplo aberto no Excel
        st.sidebar.caption(
            "Formulário em branco indisponível: o arquivo do estudo de caso "
            "está aberto em outro programa."
        )
        return
    st.sidebar.download_button(
        "Baixar formulário FMECA em branco (.xlsx)",
        data=modelo,
        file_name="formulario_fmeca_em_branco.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        help=(
            "Modelo para preencher com outro equipamento: identificação, "
            "«Matriz de componentes» com o lead time de cada peça, «Modos de "
            "falha» com as notas S, O e D, e a aba «Tabela» com as escalas. "
            "RPN e Criticidade são calculados pelas fórmulas da planilha. Para "
            "mais linhas, insira-as dentro da tabela, para que as fórmulas "
            "acompanhem."
        ),
    )


def _carregar_entradas():
    st.sidebar.header("Dados de entrada")

    usar_exemplo = st.sidebar.checkbox(
        "Usar o estudo de caso de demonstração",
        value=True,
        help=(
            "Formulário FMECA do ventilador pulmonar, com o lead time de cada "
            "componente atribuído pelo subsistema na aba «Matriz de componentes». "
            "Desmarque para enviar o seu arquivo."
        ),
    )

    _botao_modelo()

    if usar_exemplo:
        if not FMECA_EXEMPLO.exists():
            st.sidebar.error(
                f"Arquivo de exemplo não encontrado em {FMECA_EXEMPLO.name}."
            )
            return None
        return FMECA_EXEMPLO

    return st.sidebar.file_uploader(
        "Formulário FMECA (.xlsx)",
        type=["xlsx"],
        help=(
            "Precisa conter as abas «Matriz de componentes» e «Modos de falha». "
            "A «Matriz de componentes» precisa da coluna «Lead time (dias)»."
        ),
    )


def _parametros_zona() -> ParametrosZona:
    st.sidebar.header("Limiares das zonas")
    with st.sidebar.expander("Criticidade (S × O)", expanded=False):
        media, alta = st.slider(
            "Faixas de Criticidade",
            min_value=1,
            max_value=TETO_CRITICIDADE,
            value=(20, 40),
            help=(
                "**Primeiro valor: piso da faixa média.** A falha pesa em um dos "
                "critérios: é grave, ainda que rara, ou ocasional, ainda que de "
                "efeito leve. Padrão 20 = S 10 × O 2 ou S 4 × O 5.\n\n"
                "**Segundo valor: piso da faixa alta.** A falha pesa nos dois "
                "critérios: compromete função essencial e é pelo menos ocasional. "
                "Padrão 40 = S 8 × O 5 ou S 10 × O 4.\n\n"
                "Use o produto das notas S e O que marcam o início de cada faixa "
                "nas escalas do formulário."
            ),
        )
        media, alta = separar_limiares(media, alta, TETO_CRITICIDADE)
        st.caption(
            f"Baixa: abaixo de {media}  ·  Média: de {media} a {alta - 1}"
            f"  ·  Alta: a partir de {alta}"
        )
    with st.sidebar.expander("Lead time (dias)", expanded=False):
        curto, longo = st.slider(
            "Faixas de lead time",
            min_value=1,
            max_value=TETO_LEAD_TIME_DIAS,
            value=(7, 30),
            help=(
                "**Primeiro valor: teto da faixa curta.** Até ele, a peça chega a "
                "tempo de o equipamento voltar logo à operação. Padrão de 7 dias: "
                "fornecedor nacional ou pronta entrega.\n\n"
                "**Segundo valor: teto da faixa média.** Acima dele, a espera é "
                "longa demais para comprar só depois da falha. Padrão de 30 dias: "
                "importação sem representação no país.\n\n"
                "Use os prazos reais de entrega dos fornecedores, do pedido até a "
                "peça disponível."
            ),
        )
        curto, longo = separar_limiares(curto, longo, TETO_LEAD_TIME_DIAS)
        st.caption(
            f"Curto: até {curto} dias  ·  Médio: acima de {curto} até "
            f"{longo} dias  ·  Longo: acima de {longo} dias"
        )

    return ParametrosZona(
        criticidade_alta=int(alta),
        criticidade_media=int(media),
        lead_time_curto_dias=float(curto),
        lead_time_longo_dias=float(longo),
    )


def _parametros_deteccao() -> ParametrosDeteccao:
    st.sidebar.header("Detecção")
    with st.sidebar.expander("Falha oculta (D)", expanded=False):
        oculta = st.slider(
            "D a partir da qual a falha é oculta",
            min_value=1,
            max_value=10,
            value=7,
            help=(
                "A partir deste valor a falha só aparece no uso crítico, e o "
                "modo é sinalizado na justificativa do componente. O padrão "
                "segue a escala de Detecção da aba «Tabela». Não altera a zona "
                "de prioridade."
            ),
        )

    return ParametrosDeteccao(limiar_oculta=int(oculta))


def _parametros_custo():
    """
    Devolve o custo, a escala de Ocorrência (só com a posição na faixa) e o
    espaço da barra lateral onde a tabela de λ é desenhada depois da leitura
    do formulário, de onde vêm as faixas.
    """
    st.sidebar.header("Custo de indisponibilidade")
    with st.sidebar.expander("Custo de leito bloqueado", expanded=False):
        leito = st.number_input(
            "Custo de leito bloqueado (R$/dia)",
            min_value=0.0,
            value=float(DIARIA_UTI_II_SUS),
            step=50.0,
            help=(
                f"O padrão é a diária de UTI II adulto do SUS (R$ "
                f"{DIARIA_UTI_II_SUS:.2f}, SIGTAP 08.02.01.008-3); a de UTI III é "
                f"R$ {DIARIA_UTI_III_SUS:.2f} (SIGTAP 08.02.01.009-1). Portaria "
                "GM/MS nº 160, de 25 de fevereiro de 2022. É o valor que a unidade "
                "deixa de faturar por dia de leito bloqueado."
            ),
        )

    st.sidebar.header("Frota")
    with st.sidebar.expander("Equipamentos em operação", expanded=False):
        frota = st.number_input(
            "Equipamentos na frota da unidade",
            min_value=1,
            value=10,
            step=1,
            help=(
                "Equipamentos da mesma tecnologia em operação na unidade. "
                "Multiplica a taxa de falha por unidade (λ) para chegar à "
                "exposição anual da unidade; não altera as zonas. No estudo de "
                "caso são 10: um ventilador por leito na UTI de dez leitos, sem "
                "equipamento reserva."
            ),
        )

    st.sidebar.header("Escala de Ocorrência")
    with st.sidebar.expander("Taxa de falha (λ)", expanded=False):
        posicao = st.radio(
            "Valor de λ tomado em cada faixa",
            options=list(POSICOES_LAMBDA),
            format_func=POSICOES_LAMBDA.get,
            horizontal=True,
            help=(
                "Cada nota de Ocorrência corresponde a um intervalo de taxa de "
                "falha anual na aba «Tabela» do formulário. O cálculo precisa de "
                "um valor só: a média ou o teto do intervalo."
            ),
        )
        st.caption(
            "**Média**: ponto central da faixa, estimativa típica.  \n"
            "**Teto**: limite superior da faixa, cenário mais desfavorável, "
            "que dá a maior exposição anual compatível com as notas do FMECA."
        )
        area_escala = st.container()

    custo = ParametrosCusto(
        custo_leito_dia=float(leito),
        frota_equipamentos=int(frota),
    )
    return custo, ParametrosOcorrencia(posicao_na_faixa=float(posicao)), area_escala


# --------------------------------------------------------------------------
# exibicao
# --------------------------------------------------------------------------

def _reais(valor: float | None) -> str:
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")


def _num(valor: float, casas: int | None = None) -> str:
    """Decimal com virgula. Sem `casas`: ate duas, e ao menos uma."""
    if casas is not None:
        return f"{valor:.{casas}f}".replace(".", ",")
    texto = f"{valor:.2f}".rstrip("0")
    return (texto + "0" if texto.endswith(".") else texto).replace(".", ",")


def _tabela_escala(area, fmeca, escala: ParametrosOcorrencia) -> None:
    """Tabela da escala de Ocorrência -> λ na barra lateral."""
    lida = fmeca is not None and fmeca.escala_ocorrencia is not None
    linhas = [
        "| Nota O | Faixa | λ usado |",
        "|:---:|:---:|:---:|",
    ]
    for minimo, maximo, piso, teto in escala.faixas:
        faixa = f"≥ {_num(piso)}" if piso == teto else f"{_num(piso)} a {_num(teto)}"
        usado = escala.taxa_anual(minimo)
        linhas.append(f"| {minimo}–{maximo} | {faixa} | {_num(usado, 2)} |")

    with area:
        if fmeca is not None and not lida:
            st.warning(
                "A escala da aba «Tabela» não pôde ser usada; vale a escala "
                "padrão. O motivo está nos avisos da conferência."
            )
        st.markdown("\n".join(linhas))
        st.caption(
            "Falhas por ano por equipamento. "
            + ("Escala lida da aba «Tabela» do formulário. " if lida else "Escala padrão do modelo. ")
            + "A faixa aberta (≥) é fixada no piso."
        )


def _cartao_equipamento(fmeca) -> None:
    """Identificação do equipamento analisado, em destaque acima do resultado."""
    data = fmeca.data_analise
    if hasattr(data, "strftime"):
        data = data.strftime("%d/%m/%Y")
    campos = [
        ("Modelo", fmeca.modelo),
        ("Fabricante", fmeca.fabricante),
        ("Setor", fmeca.setor),
        ("Data da análise", data),
    ]
    itens = "".join(
        f"""<div style="margin-right:2.2rem">
            <div style="font-size:.72rem;text-transform:uppercase;
                        letter-spacing:.04em;opacity:.65">{rotulo}</div>
            <div style="font-size:1rem;font-weight:600">{html.escape(str(valor))}</div>
        </div>"""
        for rotulo, valor in campos
        if valor
    )
    nome = html.escape(fmeca.equipamento or fmeca.identificacao)
    st.markdown(
        f"""<div style="border-left:5px solid {COR_EQUIPAMENTO};
                background:rgba(128,128,128,.08);border-radius:6px;
                padding:.9rem 1.2rem;margin:.4rem 0 1rem;
                width:fit-content;max-width:100%">
            <div style="font-size:.72rem;text-transform:uppercase;
                        letter-spacing:.04em;opacity:.65">Equipamento analisado</div>
            <div style="font-size:24px;font-weight:700;margin:.1rem 0 .6rem">{nome}</div>
            <div style="display:flex;flex-wrap:wrap;row-gap:.6rem">{itens}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _mostrar_erros(validacao: RelatorioValidacao) -> bool:
    """Exibe os erros bloqueantes. Devolve True quando é possível seguir."""
    if not validacao.erros:
        return True
    st.error("A leitura dos dados encontrou erros que impedem o cálculo:")
    for msg in validacao.erros:
        st.markdown(f"- {msg}")
    return False


def _mostrar_avisos(validacao: RelatorioValidacao) -> None:
    """
    Exibe os avisos. Chamada depois de `decidir`, porque parte deles — o de
    Ocorrência subestimada pelo modo dimensionante — só existe após o cálculo.
    """
    if validacao.avisos:
        with st.expander(
            f"⚠️ {len(validacao.avisos)} aviso(s) na conferência dos dados", expanded=False
        ):
            for msg in validacao.avisos:
                st.markdown(f"- {msg}")


def _rodape(validacao: RelatorioValidacao) -> None:
    st.divider()
    if not validacao.avisos:
        st.caption(
            ":green[:material/check_circle:] Conferência dos dados sem nenhuma "
            "inconsistência."
        )


def _painel_resumo(decisoes, custo: ParametrosCusto) -> None:
    resumo = resumo_por_zona(decisoes)
    colunas = st.columns(4)
    ordem = [Zona.PRIORIDADE_ALTA, Zona.PRIORIDADE_MEDIA, Zona.PRIORIDADE_BAIXA]
    for col, zona in zip(colunas, ordem):
        dados = resumo[zona.rotulo]
        col.metric(
            zona.rotulo,
            f"{dados['componentes']} componentes",
            _reais(dados["dc_anual_total"]) if custo.declarado else None,
            delta_color="off",
            help=f"Recomendação: {_minuscula_inicial(zona.recomendacao)}.",
        )
    sem_zona = resumo[SEM_ZONA]["componentes"]
    total_anual = sum(
        d.dc_anual_esperado or 0.0 for d in decisoes
    )
    colunas[3].metric(
        "Exposição anual total",
        _reais(total_anual) if custo.declarado else "—",
        f"{sem_zona} sem zona atribuída" if sem_zona else "todos classificados",
        delta_color="off",
    )
    if not custo.declarado:
        st.info(
            "Nenhum custo de leito bloqueado foi informado, então o Downtime Cost sai "
            "zerado. As zonas continuam válidas: elas dependem da Criticidade e do "
            "lead time, não do custo."
        )


def _grade_zonas(decisoes, zonas: ParametrosZona) -> None:
    st.subheader("Matriz de zonas")
    st.caption(
        f"Criticidade: baixa < {zonas.criticidade_media} ≤ média < "
        f"{zonas.criticidade_alta} ≤ alta  ·  lead time: curto ≤ "
        f"{zonas.lead_time_curto_dias:g} < médio ≤ {zonas.lead_time_longo_dias:g} < longo"
    )

    faixas_c = [FaixaCriticidade.ALTA, FaixaCriticidade.MEDIA, FaixaCriticidade.BAIXA]
    faixas_l = [FaixaLeadTime.CURTO, FaixaLeadTime.MEDIO, FaixaLeadTime.LONGO]

    cabecalho = st.columns([1.1, 2, 2, 2])
    cabecalho[0].markdown("&nbsp;", unsafe_allow_html=True)
    for col, fl in zip(cabecalho[1:], faixas_l):
        col.markdown(f"**Lead time {fl.rotulo.lower()}**")

    for fc in faixas_c:
        linha = st.columns([1.1, 2, 2, 2])
        linha[0].markdown(f"**Criticidade {fc.rotulo.lower()}**")
        for col, fl in zip(linha[1:], faixas_l):
            zona = MATRIZ_ZONAS[(fc, fl)]
            itens = [
                d
                for d in decisoes
                if d.faixa_criticidade is fc and d.faixa_lead_time is fl
            ]
            ids = ", ".join(str(d.id) for d in sorted(itens, key=lambda x: x.id)) or "—"
            col.markdown(
                f"""<div style="border-left:4px solid {COR_ZONA[zona]};
                        background:rgba(128,128,128,.07);
                        padding:.55rem .7rem;border-radius:4px;min-height:5.2rem">
                <div style="font-weight:600;font-size:.82rem">{zona.rotulo}</div>
                <div style="font-size:.78rem;opacity:.85;margin-top:.25rem">
                IDs {ids}</div></div>""",
                unsafe_allow_html=True,
            )

    _legenda_zonas()


def _legenda_zonas() -> None:
    """O que cada zona afirma e a recomendacao de estoque correspondente."""
    st.markdown("**O que cada zona significa**")
    for zona in (Zona.PRIORIDADE_ALTA, Zona.PRIORIDADE_MEDIA, Zona.PRIORIDADE_BAIXA):
        st.markdown(
            f"""<div style="border-left:4px solid {COR_ZONA[zona]};
                    padding:.3rem .7rem;margin-bottom:.5rem">
            <div style="font-weight:600;font-size:.88rem">{zona.rotulo}</div>
            <div style="font-size:.84rem">{zona.descricao}.
            <strong>Recomendação:</strong> {_minuscula_inicial(zona.recomendacao)}.</div>
            </div>""",
            unsafe_allow_html=True,
        )
    st.caption(
        "A recomendação é uma leitura da prioridade, não a saída do modelo: "
        "definir níveis de reposição exigiria taxa de consumo e custo de "
        "posse, que o modelo não tem. Na prioridade média, a entrada efetiva "
        "em estoque depende do custo de posse do item."
    )


def _minuscula_inicial(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def _dispersao(decisoes, zonas: ParametrosZona, custo: ParametrosCusto) -> None:
    linhas = [
        {
            "ID": d.id,
            "Componente": d.nome,
            "Criticidade": d.criticidade,
            # Nomes de campo sem parêntese nem espaço duplo: o atalho de
            # codificação do Vega-Lite é sensível a pontuação no nome.
            "LeadTime": d.lead_time_dias,
            "Zona": d.zona.rotulo,
            "ExposicaoAnual": d.dc_anual_esperado or 0.0,
            "ExposicaoAnualReais": _reais(d.dc_anual_esperado or 0.0),
            "Natureza": d.componente.natureza or "—",
        }
        for d in decisoes
        if d.decidido
    ]
    if not linhas:
        st.info(
            "A dispersão precisa de componentes com zona atribuída, isto é, com "
            "Criticidade e lead time informados."
        )
        return
    df = pd.DataFrame(linhas)

    escala = alt.Scale(
        domain=[z.rotulo for z in (Zona.PRIORIDADE_ALTA, Zona.PRIORIDADE_MEDIA, Zona.PRIORIDADE_BAIXA)],
        range=[COR_ZONA[Zona.PRIORIDADE_ALTA], COR_ZONA[Zona.PRIORIDADE_MEDIA], COR_ZONA[Zona.PRIORIDADE_BAIXA]],
    )
    # dominios fixos, para que o sombreado chegue a borda do grafico
    teto_y = math.ceil(max(df["LeadTime"].max(), zonas.lead_time_longo_dias) * 1.1 / 10) * 10
    eixo_x = alt.Scale(domain=[0, TETO_CRITICIDADE], nice=False)
    eixo_y = alt.Scale(domain=[0, teto_y], nice=False)

    # celulas de prioridade alta: Alta x (Medio, Longo) e Media x Longo
    regioes = pd.DataFrame(
        {
            "x": [zonas.criticidade_alta, zonas.criticidade_media],
            "x2": [TETO_CRITICIDADE, zonas.criticidade_alta],
            "y": [zonas.lead_time_curto_dias, zonas.lead_time_longo_dias],
            "y2": [teto_y, teto_y],
        }
    )
    sombreado = (
        alt.Chart(regioes)
        .mark_rect(color=COR_ZONA[Zona.PRIORIDADE_ALTA], opacity=0.08)
        .encode(
            x=alt.X("x:Q", scale=eixo_x), x2="x2:Q",
            y=alt.Y("y:Q", scale=eixo_y), y2="y2:Q",
        )
    )
    rotulo = (
        alt.Chart(pd.DataFrame({"x": [TETO_CRITICIDADE], "y": [teto_y],
                                "t": [Zona.PRIORIDADE_ALTA.rotulo.lower()]}))
        .mark_text(align="right", baseline="top", dx=-4, dy=4, fontSize=11,
                   color=COR_ZONA[Zona.PRIORIDADE_ALTA])
        .encode(x=alt.X("x:Q", scale=eixo_x), y=alt.Y("y:Q", scale=eixo_y), text="t:N")
    )
    pontos = (
        alt.Chart(df)
        .mark_circle(opacity=0.85, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Criticidade:Q", title="Criticidade (S × O)", scale=eixo_x),
            y=alt.Y("LeadTime:Q", title="Lead time (dias)", scale=eixo_y),
            color=alt.Color("Zona:N", scale=escala, legend=alt.Legend(title="Zona de prioridade", orient="bottom")),
            size=alt.Size(
                "ExposicaoAnual:Q",
                # formato brasileiro: o Vega-Lite separa milhar com virgula
                legend=alt.Legend(
                    title="Exposição anual (R$)", orient="bottom",
                    labelExpr="replace(format(datum.value, ',.0f'), /,/g, '.')",
                ),
                scale=alt.Scale(range=[60, 900]),
            )
            if custo.declarado
            else alt.value(160),
            tooltip=[
                alt.Tooltip("ID:Q"),
                alt.Tooltip("Componente:N"),
                alt.Tooltip("Natureza:N"),
                alt.Tooltip("Criticidade:Q"),
                alt.Tooltip("LeadTime:Q", title="Lead time (dias)"),
                alt.Tooltip("Zona:N"),
                alt.Tooltip("ExposicaoAnualReais:N", title="Exposição anual"),
            ],
        )
    )
    corte_c = alt.Chart(
        pd.DataFrame({"c": [zonas.criticidade_media, zonas.criticidade_alta]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(x=alt.X("c:Q", scale=eixo_x))
    corte_l = alt.Chart(
        pd.DataFrame({"l": [zonas.lead_time_curto_dias, zonas.lead_time_longo_dias]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(y=alt.Y("l:Q", scale=eixo_y))

    grafico = (sombreado + corte_c + corte_l + pontos + rotulo).properties(
        height=420, width="container"
    )
    st.altair_chart(grafico)


def _tabela(decisoes, custo: ParametrosCusto) -> None:
    linhas = []
    for d in ordenar_para_relatorio(decisoes):
        linhas.append(
            {
                "ID": d.id,
                "Componente": d.nome,
                "Natureza": d.componente.natureza or "—",
                "S": d.severidade,
                "O": d.ocorrencia,
                "Criticidade": d.criticidade,
                "RPN": d.rpn,
                "Lead time (dias)": d.lead_time_dias,
                "Zona": d.zona.rotulo if d.zona else SEM_ZONA,
                "Recomendação": d.zona.recomendacao if d.zona else "—",
                "λ (falha/ano)": d.taxa_falha_anual,
                "DC por evento (R$)": d.dc_evitavel,
                "DC anual (R$)": d.dc_anual_esperado,
            }
        )
    df = pd.DataFrame(linhas)
    if not custo.declarado:
        df = df.drop(columns=["DC por evento (R$)", "DC anual (R$)"])
    frota = custo.frota_equipamentos
    ajuda_evento = (
        "Custo da espera pela peça em uma falha.\n\n"
        "**Lead time (dias) × custo de leito bloqueado** "
        f"({_reais(custo.custo_leito_dia)}/dia)."
    )
    ajuda_anual = (
        "Exposição anual da unidade à falta da peça.\n\n"
        "**DC por evento × λ (falha/ano) × frota** "
        f"({frota} equipamento{'s' if frota != 1 else ''})."
    )
    if custo.declarado:
        with st.container(horizontal=True, gap="large"):
            st.caption("**DC por evento (R$)**", help=ajuda_evento, width="content")
            st.caption("**DC anual (R$)**", help=ajuda_anual, width="content")
    # Formato brasileiro via Styler; a ordenação segue o valor numérico. Toda
    # coluna numérica precisa de formato, senão o Styler mostra seis casas.
    formatos = {
        "S": "{:.0f}",
        "O": "{:.0f}",
        "Criticidade": "{:.0f}",
        "RPN": "{:.0f}",
        "Lead time (dias)": lambda v: f"{v:g}".replace(".", ","),
        "λ (falha/ano)": lambda v: _num(v, 2),
        "DC por evento (R$)": _reais,
        "DC anual (R$)": _reais,
    }
    tabela = df.style.format(
        {c: f for c, f in formatos.items() if c in df.columns}, na_rep="—"
    )
    st.dataframe(tabela, hide_index=True)


def _criticidade_deteccao(fmeca, decisoes, zonas: ParametrosZona,
                          deteccao: ParametrosDeteccao) -> None:
    st.subheader("Criticidade × Detecção")
    st.caption(
        "Um ponto por modo de falha. A faixa sombreada reúne as falhas ocultas "
        f"(D ≥ {deteccao.limiar_oculta}): nelas o estoque encurta o reparo, mas "
        "não antecipa a descoberta da falha. O tamanho é o RPN. Modos com a "
        "mesma Criticidade e a mesma Detecção ocupam o mesmo ponto; o numeral "
        "ao lado indica quantos são."
    )
    zona_de = {d.id: d.zona for d in decisoes}
    linhas = []
    for m in fmeca.modos:
        if m.criticidade_calculada is None or m.deteccao_nota is None:
            continue
        comp = fmeca.componente(m.id_componente)
        zona = zona_de.get(m.id_componente)
        linhas.append(
            {
                "SubID": m.sub_id,
                "Modo": m.modo or "—",
                "Componente": comp.nome if comp else (m.componente or "—"),
                "Criticidade": m.criticidade_calculada,
                "D": m.deteccao_nota,
                "S": m.severidade,
                "O": m.ocorrencia,
                "RPN": m.rpn_calculado,
                "Zona": zona.rotulo if zona else SEM_ZONA,
            }
        )
    if not linhas:
        st.info("Nenhum modo de falha tem S, O e D pontuados.")
        return
    df = pd.DataFrame(linhas)

    # modos na mesma posicao tem o mesmo RPN, logo o mesmo tamanho: um cobre o outro
    grupos = agrupar_por_posicao(fmeca.modos)
    posicao = list(zip(df["Criticidade"], df["D"]))
    df["Modos na posicao"] = [len(grupos[p]) for p in posicao]
    df["Coincidentes"] = [
        ", ".join(grupos[p]) if len(grupos[p]) > 1 else "" for p in posicao
    ]
    # uma linha por posicao coincidente, para o numeral nao se repetir sobre si
    sobrepostos = pd.DataFrame(
        [
            {"Criticidade": c, "D": d, "Quantidade": str(len(ids))}
            for (c, d), ids in grupos.items()
            if len(ids) > 1
        ],
        columns=["Criticidade", "D", "Quantidade"],
    )

    zonas_ord = (Zona.PRIORIDADE_ALTA, Zona.PRIORIDADE_MEDIA, Zona.PRIORIDADE_BAIXA)
    escala = alt.Scale(
        domain=[z.rotulo for z in zonas_ord] + [SEM_ZONA],
        range=[COR_ZONA[z] for z in zonas_ord] + [COR_SEM_ZONA],
    )
    faixa = (
        alt.Chart(pd.DataFrame({"y": [deteccao.limiar_oculta - 0.5], "y2": [10.5]}))
        .mark_rect(color="#c0392b", opacity=0.08)
        .encode(y="y:Q", y2="y2:Q")
    )
    rotulo = (
        alt.Chart(pd.DataFrame({"x": [0], "y": [10.3], "t": ["falha oculta"]}))
        .mark_text(align="left", baseline="top", dx=4, fontSize=11, color="#c0392b")
        .encode(x="x:Q", y="y:Q", text="t:N")
    )
    pontos = (
        alt.Chart(df)
        .mark_circle(opacity=0.85, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Criticidade:Q", title="Criticidade (S × O)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("D:Q", title="Detecção (D)", scale=alt.Scale(domain=[0.5, 10.5]),
                    axis=alt.Axis(values=list(range(1, 11)))),
            color=alt.Color("Zona:N", scale=escala,
                            legend=alt.Legend(title="Zona do componente", orient="bottom")),
            size=alt.Size("RPN:Q", scale=alt.Scale(range=[40, 700]),
                          legend=alt.Legend(title="RPN", orient="bottom")),
            tooltip=[
                alt.Tooltip("SubID:N", title="Sub ID"),
                alt.Tooltip("Modo:N", title="Modo de falha"),
                alt.Tooltip("Componente:N"),
                alt.Tooltip("S:Q"), alt.Tooltip("O:Q"), alt.Tooltip("D:Q"),
                alt.Tooltip("Criticidade:Q"), alt.Tooltip("RPN:Q"),
                alt.Tooltip("Zona:N"),
                alt.Tooltip("Modos na posicao:Q", title="Modos nesta posição"),
                alt.Tooltip("Coincidentes:N", title="Sub IDs sobrepostos"),
            ],
        )
    )
    contagem = (
        alt.Chart(sobrepostos)
        .mark_text(align="left", baseline="bottom", dx=6, dy=-6, fontSize=9, color="#999")
        .encode(x="Criticidade:Q", y="D:Q", text="Quantidade:N")
    )
    corte_c = alt.Chart(
        pd.DataFrame({"c": [zonas.criticidade_media, zonas.criticidade_alta]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(x="c:Q")

    grafico = (faixa + corte_c + pontos + contagem + rotulo).properties(
        height=440, width="container"
    )
    st.altair_chart(grafico)


def _detalhe(decisoes) -> None:
    with st.expander("Justificativa componente a componente", expanded=False):
        for d in ordenar_para_relatorio(decisoes):
            cor = COR_ZONA.get(d.zona, COR_SEM_ZONA)
            marca = " ⚠️" if d.modos_ocultos else ""
            st.markdown(
                f"<div style='border-left:3px solid {cor};padding:.1rem .7rem;"
                f"margin-bottom:.7rem'><strong>{d.id}. {d.nome}{marca}</strong><br>"
                f"<span style='font-size:.86rem'>{d.justificativa}</span></div>",
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------
# principal
# --------------------------------------------------------------------------

def main() -> None:
    st.html(CSS_BARRA_LATERAL)
    st.title("Estoque de spare parts na Engenharia Clínica")
    st.caption(
        "Prioridade de estoque de peças de reposição a partir do FMECA do "
        "equipamento: para cada componente, o cruzamento entre a Criticidade "
        "(S × O) e o prazo de fornecimento (lead time) atribui prioridade "
        "alta, média ou baixa, conforme os dois eixos, apenas um ou nenhum "
        "sustentem a posse antecipada da peça. Cada zona traz a recomendação "
        "de estoque correspondente. O custo de indisponibilidade (Downtime "
        "Cost) estima a exposição anual esperada da unidade e ordena os "
        "componentes dentro de cada zona, sem alterar a zona."
    )

    arquivo_fmeca = _carregar_entradas()
    zonas = _parametros_zona()
    custo, escala, area_escala = _parametros_custo()
    deteccao = _parametros_deteccao()

    if arquivo_fmeca is None:
        _tabela_escala(area_escala, None, escala)
        st.info("Envie o formulário FMECA na barra lateral para começar.")
        return

    try:
        fmeca = ler_fmeca(arquivo_fmeca)
    except PermissionError:
        _tabela_escala(area_escala, None, escala)
        st.error(
            "O formulário FMECA está aberto em outro programa, provavelmente o "
            "Excel, que bloqueia a leitura. Feche o arquivo e recarregue a página."
        )
        return
    except Exception as exc:  # pragma: no cover
        _tabela_escala(area_escala, None, escala)
        st.error(f"Não consegui ler o formulário FMECA: {exc}")
        return

    validacao = RelatorioValidacao()
    validacao.estender(fmeca.validacao)
    escala = escala_do_formulario(fmeca, escala)
    _tabela_escala(area_escala, fmeca, escala)

    _cartao_equipamento(fmeca)

    if not _mostrar_erros(validacao):
        return

    decisoes = decidir(fmeca, custo, zonas, validacao, escala, deteccao)
    _mostrar_avisos(validacao)

    if not any(d.decidido for d in decisoes):
        st.warning(
            "Nenhum componente recebeu zona: não há lead time utilizável na aba "
            "«Matriz de componentes». Confira a coluna «Lead time (dias)» — os "
            "avisos acima apontam linha por linha."
        )

    _painel_resumo(decisoes, custo)
    st.divider()

    aba_matriz, aba_grafico, aba_tabela, aba_deteccao = st.tabs(
        ["Matriz de zonas", "Dispersão", "Tabela de decisão",
         "Criticidade × Detecção"]
    )
    with aba_matriz:
        _grade_zonas(decisoes, zonas)
    with aba_grafico:
        _dispersao(decisoes, zonas, custo)
    with aba_tabela:
        _tabela(decisoes, custo)
    with aba_deteccao:
        _criticidade_deteccao(fmeca, decisoes, zonas, deteccao)

    _detalhe(decisoes)

    st.divider()
    st.subheader("Exportar")
    col1, col2 = st.columns(2)
    col1.download_button(
        "Planilha de resultado (.xlsx)",
        data=exportar_xlsx(fmeca, decisoes, custo, zonas, escala, validacao,
                           deteccao=deteccao),
        file_name="decisao_estoque_spare_parts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    col2.download_button(
        "Tabela de decisão (.csv)",
        data=exportar_csv(decisoes).encode("utf-8-sig"),
        file_name="decisao_estoque_spare_parts.csv",
        mime="text/csv",
    )
    st.caption(
        "A planilha exportada carrega os limiares e o custo de leito bloqueado em "
        "aba própria, para que o resultado possa ser conferido e repetido."
    )
    _rodape(validacao)


if __name__ == "__main__":
    main()
