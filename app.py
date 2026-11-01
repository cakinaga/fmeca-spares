"""
Interface do modelo de decisao de estoque de spare parts (Etapa 2).

Rodar com:
    streamlit run app.py

Todo o calculo vive no pacote fmeca_spares; esta tela apenas coleta
parametros, exibe e exporta. Isso mantem o modulo de calculo utilizavel sem
Streamlit, por quem quiser importa-lo em um script ou em outra interface.
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from fmeca_spares import (
    DIARIA_UTI_II_SUS,
    DIARIA_UTI_III_SUS,
    AcaoDeteccao,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    Zona,
    decidir,
    ler_fmeca,
    ordenar_para_relatorio,
    plano_de_acao,
    resumo_por_zona,
)
from fmeca_spares.leitura import RelatorioValidacao
from fmeca_spares.exportacao import exportar_csv, exportar_xlsx
from fmeca_spares.modelo import MATRIZ_ZONAS
from fmeca_spares.parametros import FaixaCriticidade, FaixaLeadTime

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
FMECA_EXEMPLO = DADOS / "matriz_componentes_ventilador_uti.xlsx"

COR_ZONA = {
    Zona.ESTOQUE_SEGURANCA: "#c0392b",
    Zona.PONTO_PEDIDO: "#d4a017",
    Zona.SOB_DEMANDA: "#4a7c59",
}
COR_SEM_ZONA = "#888888"
SEM_ZONA = "Sem zona atribuída"

st.set_page_config(
    page_title="Estoque de spare parts — FMECA e Downtime Cost",
    page_icon="🔧",
    layout="wide",
)


# --------------------------------------------------------------------------
# entrada de dados
# --------------------------------------------------------------------------

def _carregar_entradas():
    st.sidebar.header("Dados de entrada")

    usar_exemplo = st.sidebar.checkbox(
        "Usar o estudo de caso de demonstração",
        value=True,
        help=(
            "Formulário FMECA do ventilador pulmonar, com lead times ilustrativos "
            "na aba «Matriz de componentes». Desmarque para enviar o seu arquivo."
        ),
    )

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
            max_value=100,
            value=(20, 40),
            help=(
                "Primeiro valor: piso da faixa média. Segundo: piso da faixa alta. "
                "O padrão 40 é o menor S × O que combina perda de função crítica "
                "(S = 8) com falha ao menos ocasional (O = 5)."
            ),
        )
    with st.sidebar.expander("Lead time (dias)", expanded=False):
        curto, longo = st.slider(
            "Faixas de lead time",
            min_value=1,
            max_value=180,
            value=(7, 30),
            help=(
                "Primeiro valor: teto da faixa curta. Segundo: piso da faixa longa. "
                "O padrão 7 corresponde a fornecimento nacional; acima de 30 dias, "
                "a importação sem representação consolidada."
            ),
        )
        piso = st.checkbox(
            "Piso de ponto de pedido para demanda programada",
            value=True,
            help=(
                "Consumíveis não caem em compra sob demanda: a demanda deles vem "
                "do intervalo de troca, não da falha."
            ),
        )

    if media >= alta:
        alta = media + 1
    if curto >= longo:
        longo = curto + 1

    return ParametrosZona(
        criticidade_alta=int(alta),
        criticidade_media=int(media),
        lead_time_curto_dias=float(curto),
        lead_time_longo_dias=float(longo),
        piso_ponto_pedido_demanda_programada=piso,
    )


def _parametros_deteccao() -> ParametrosDeteccao:
    st.sidebar.header("Plano de ação")
    with st.sidebar.expander("Detecção (D)", expanded=False):
        preventiva, oculta = st.slider(
            "Faixas de Detecção",
            min_value=1,
            max_value=10,
            value=(5, 7),
            help=(
                "Primeiro valor: D a partir da qual a detecção depende da "
                "preventiva. Segundo: D a partir da qual a falha é oculta até o "
                "uso crítico. Os padrões seguem a escala de Detecção da aba "
                "«Tabela». Não alteram a zona de estoque."
            ),
        )
        severidade = st.slider(
            "Severidade que torna a falha oculta um alerta",
            min_value=1,
            max_value=10,
            value=9,
            help=(
                "Falha oculta com S a partir deste valor recebe alerta quando o "
                "componente não está em estoque de segurança: o risco que a "
                "Criticidade (S × O) subestima, por ignorar a Detecção."
            ),
        )

    if preventiva >= oculta:
        if oculta < 10:
            oculta = preventiva + 1
        else:
            preventiva = oculta - 1

    return ParametrosDeteccao(
        limiar_oculta=int(oculta),
        limiar_preventiva=int(preventiva),
        severidade_alerta=int(severidade),
    )


def _parametros_custo() -> tuple[ParametrosCusto, ParametrosOcorrencia]:
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
        st.caption(
            "Valores de 2022: confira a tabela SIGTAP vigente antes de citar. A "
            "diária do SUS fica abaixo do custo operacional efetivo de um leito "
            "de UTI, então é a escolha conservadora."
        )

    st.sidebar.header("Frota")
    with st.sidebar.expander("Equipamentos em operação", expanded=False):
        frota = st.number_input(
            "Equipamentos na frota da unidade", min_value=1, value=10, step=1
        )

    st.sidebar.header("Escala de Ocorrência")
    with st.sidebar.expander("Taxa de falha por nota", expanded=False):
        posicao = st.slider(
            "Posição tomada dentro da faixa de λ",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help=(
                "A escala de Ocorrência do formulário define cada par de notas por "
                "um intervalo de taxa de falha anual. 0 toma o piso do intervalo, "
                "1 o teto. Rodar nos dois extremos dá o intervalo de custo "
                "compatível com a mesma pontuação de FMECA."
            ),
        )

    custo = ParametrosCusto(
        custo_leito_dia=float(leito),
        frota_equipamentos=int(frota),
    )
    return custo, ParametrosOcorrencia(posicao_na_faixa=float(posicao))


# --------------------------------------------------------------------------
# exibicao
# --------------------------------------------------------------------------

def _reais(valor: float | None) -> str:
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")


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
    else:
        st.success("Conferência dos dados sem nenhuma inconsistência.")


def _painel_resumo(decisoes, custo: ParametrosCusto) -> None:
    resumo = resumo_por_zona(decisoes)
    colunas = st.columns(4)
    ordem = [
        Zona.ESTOQUE_SEGURANCA.rotulo,
        Zona.PONTO_PEDIDO.rotulo,
        Zona.SOB_DEMANDA.rotulo,
    ]
    for col, zona in zip(colunas, ordem):
        dados = resumo[zona]
        col.metric(
            zona,
            f"{dados['componentes']} componentes",
            _reais(dados["dc_anual_total"]) if custo.declarado else None,
            delta_color="off",
        )
    sem_zona = resumo["Sem zona atribuída"]["componentes"]
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
            ajustados = [d for d in itens if d.piso_demanda_programada_aplicado]
            nota = (
                f"<br><span style='font-size:0.72rem;opacity:.75'>"
                f"{len(ajustados)} com piso de demanda programada</span>"
                if ajustados
                else ""
            )
            col.markdown(
                f"""<div style="border-left:4px solid {COR_ZONA[zona]};
                        background:rgba(128,128,128,.07);
                        padding:.55rem .7rem;border-radius:4px;min-height:5.2rem">
                <div style="font-weight:600;font-size:.82rem">{zona.rotulo}</div>
                <div style="font-size:.78rem;opacity:.85;margin-top:.25rem">
                IDs {ids}</div>{nota}</div>""",
                unsafe_allow_html=True,
            )


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
        domain=[z.rotulo for z in (Zona.ESTOQUE_SEGURANCA, Zona.PONTO_PEDIDO, Zona.SOB_DEMANDA)],
        range=[COR_ZONA[Zona.ESTOQUE_SEGURANCA], COR_ZONA[Zona.PONTO_PEDIDO], COR_ZONA[Zona.SOB_DEMANDA]],
    )
    pontos = (
        alt.Chart(df)
        .mark_circle(opacity=0.85, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Criticidade:Q", title="Criticidade (S × O)", scale=alt.Scale(nice=True)),
            y=alt.Y("LeadTime:Q", title="Lead time (dias)"),
            color=alt.Color("Zona:N", scale=escala, legend=alt.Legend(title="Zona de estoque", orient="bottom")),
            size=alt.Size(
                "ExposicaoAnual:Q",
                legend=alt.Legend(title="Exposição anual (R$)", orient="bottom"),
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
                alt.Tooltip("ExposicaoAnual:Q", title="Exposição anual (R$)", format=",.0f"),
            ],
        )
    )
    corte_c = alt.Chart(
        pd.DataFrame({"c": [zonas.criticidade_media, zonas.criticidade_alta]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(x="c:Q")
    corte_l = alt.Chart(
        pd.DataFrame({"l": [zonas.lead_time_curto_dias, zonas.lead_time_longo_dias]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(y="l:Q")

    grafico = (pontos + corte_c + corte_l).properties(height=420, width="container")
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
                "Zona": d.zona.rotulo if d.zona else "Sem zona atribuída",
                "λ (falha/ano)": d.taxa_falha_anual,
                "DC por evento (R$)": d.dc_evitavel,
                "DC anual (R$)": d.dc_anual_esperado,
            }
        )
    df = pd.DataFrame(linhas)
    if not custo.declarado:
        df = df.drop(columns=["DC por evento (R$)", "DC anual (R$)"])
    st.dataframe(df, hide_index=True)


def _plano(fmeca, decisoes, deteccao: ParametrosDeteccao) -> None:
    st.subheader("Plano de ação")
    st.caption(
        "Além de estocar, o que fazer? A zona de estoque vem da Criticidade "
        "(S × O); esta aba lê a Detecção e o RPN de cada modo de falha para "
        "recomendar a ação de manutenção que o estoque não substitui."
    )
    plano = plano_de_acao(fmeca, decisoes, deteccao)
    ocultos = [a for a in plano if a.acao is AcaoDeteccao.TESTE_FUNCIONAL]
    alertas = [a for a in plano if a.alerta]

    c1, c2, c3 = st.columns(3)
    c1.metric("Modos de falha oculta", f"{len(ocultos)} de {len(plano)}",
              f"D ≥ {deteccao.limiar_oculta}", delta_color="off")
    c2.metric("Componentes afetados",
              len({a.modo.id_componente for a in ocultos}), delta_color="off")
    c3.metric("Alertas", len(alertas),
              f"S ≥ {deteccao.severidade_alerta}, fora do estoque de segurança",
              delta_color="off")

    if alertas:
        itens = "\n".join(
            f"- **{a.modo.sub_id} — {a.modo.modo}** "
            f"({a.componente.nome if a.componente else a.modo.componente}): "
            f"S={a.modo.severidade}, D={a.modo.deteccao_nota}, RPN {a.rpn}, "
            f"Criticidade {a.criticidade} · {a.zona.rotulo if a.zona else SEM_ZONA}"
            for a in alertas
        )
        st.warning(
            "**Falha catastrófica e oculta fora do estoque de segurança.** A "
            "Criticidade subestima estes modos porque a Ocorrência é baixa e a "
            "Detecção não entra no S × O. Reveja a decisão de estoque e inclua "
            "teste funcional na preventiva.\n\n" + itens
        )

    df = pd.DataFrame(
        [
            {
                "Alerta": "⚠️" if a.alerta else "",
                "Sub ID": a.modo.sub_id,
                "Componente": a.componente.nome if a.componente else a.modo.componente,
                "Modo de falha": a.modo.modo,
                "S": a.modo.severidade,
                "O": a.modo.ocorrencia,
                "D": a.modo.deteccao_nota,
                "RPN": a.rpn,
                "Criticidade": a.criticidade,
                "Zona do componente": a.zona.rotulo if a.zona else SEM_ZONA,
                "Detecção atual": a.modo.deteccao,
                "Ação recomendada": a.acao.rotulo if a.acao else "—",
            }
            for a in plano
        ]
    )
    st.dataframe(df, hide_index=True)


def _criticidade_deteccao(fmeca, decisoes, zonas: ParametrosZona,
                          deteccao: ParametrosDeteccao) -> None:
    st.subheader("Criticidade × Detecção")
    st.caption(
        "Um ponto por modo de falha. A faixa sombreada reúne as falhas ocultas "
        f"(D ≥ {deteccao.limiar_oculta}): nelas o estoque encurta o reparo, mas "
        "não antecipa a descoberta da falha. Pontos com contorno preto são "
        "alertas. O tamanho é o RPN."
    )
    linhas = [
        {
            "SubID": a.modo.sub_id,
            "Modo": a.modo.modo or "—",
            "Componente": a.componente.nome if a.componente else (a.modo.componente or "—"),
            "Criticidade": a.criticidade,
            "D": a.modo.deteccao_nota,
            "S": a.modo.severidade,
            "O": a.modo.ocorrencia,
            "RPN": a.rpn,
            "Zona": a.zona.rotulo if a.zona else SEM_ZONA,
            "Acao": a.acao.rotulo if a.acao else "—",
            "Alerta": "sim" if a.alerta else "não",
        }
        for a in plano_de_acao(fmeca, decisoes, deteccao)
        if a.criticidade is not None and a.modo.deteccao_nota is not None
    ]
    if not linhas:
        st.info("Nenhum modo de falha tem S, O e D pontuados.")
        return
    df = pd.DataFrame(linhas)

    zonas_ord = (Zona.ESTOQUE_SEGURANCA, Zona.PONTO_PEDIDO, Zona.SOB_DEMANDA)
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
        .mark_circle(opacity=0.85)
        .encode(
            x=alt.X("Criticidade:Q", title="Criticidade (S × O)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("D:Q", title="Detecção (D)", scale=alt.Scale(domain=[0.5, 10.5]),
                    axis=alt.Axis(values=list(range(1, 11)))),
            color=alt.Color("Zona:N", scale=escala,
                            legend=alt.Legend(title="Zona do componente", orient="bottom")),
            size=alt.Size("RPN:Q", scale=alt.Scale(range=[40, 700]),
                          legend=alt.Legend(title="RPN", orient="bottom")),
            stroke=alt.condition(alt.datum.Alerta == "sim", alt.value("black"), alt.value("white")),
            strokeWidth=alt.condition(alt.datum.Alerta == "sim", alt.value(2.5), alt.value(1)),
            tooltip=[
                alt.Tooltip("SubID:N", title="Sub ID"),
                alt.Tooltip("Modo:N", title="Modo de falha"),
                alt.Tooltip("Componente:N"),
                alt.Tooltip("S:Q"), alt.Tooltip("O:Q"), alt.Tooltip("D:Q"),
                alt.Tooltip("Criticidade:Q"), alt.Tooltip("RPN:Q"),
                alt.Tooltip("Zona:N"),
                alt.Tooltip("Acao:N", title="Ação recomendada"),
                alt.Tooltip("Alerta:N"),
            ],
        )
    )
    corte_c = alt.Chart(
        pd.DataFrame({"c": [zonas.criticidade_media, zonas.criticidade_alta]})
    ).mark_rule(strokeDash=[4, 4], color="#999").encode(x="c:Q")

    grafico = (faixa + corte_c + pontos + rotulo).properties(height=440, width="container")
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
    st.title("Estoque de spare parts na Engenharia Clínica")
    st.caption(
        "Etapa 2 da estrutura metodológica: decisão de estoque por componente, "
        "do cruzamento entre a Criticidade do FMECA e o lead time de fornecimento, "
        "com o Downtime Cost como grandeza de apoio."
    )

    arquivo_fmeca = _carregar_entradas()
    zonas = _parametros_zona()
    custo, escala = _parametros_custo()
    deteccao = _parametros_deteccao()

    if arquivo_fmeca is None:
        st.info("Envie o formulário FMECA na barra lateral para começar.")
        return

    try:
        fmeca = ler_fmeca(arquivo_fmeca)
    except Exception as exc:  # pragma: no cover
        st.error(f"Não consegui ler o formulário FMECA: {exc}")
        return

    validacao = RelatorioValidacao()
    validacao.estender(fmeca.validacao)

    st.markdown(f"**{fmeca.identificacao}** · {fmeca.setor or 'setor não informado'}")

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

    aba_matriz, aba_grafico, aba_tabela, aba_plano, aba_deteccao = st.tabs(
        ["Matriz de zonas", "Dispersão", "Tabela de decisão",
         "Plano de ação", "Criticidade × Detecção"]
    )
    with aba_matriz:
        _grade_zonas(decisoes, zonas)
    with aba_grafico:
        _dispersao(decisoes, zonas, custo)
    with aba_tabela:
        _tabela(decisoes, custo)
    with aba_plano:
        _plano(fmeca, decisoes, deteccao)
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


if __name__ == "__main__":
    main()
