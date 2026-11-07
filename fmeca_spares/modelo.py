"""
Modelo de decisao da Etapa 2: Criticidade do FMECA x lead time de fornecimento.

A decisao de estoque de cada componente sai do cruzamento de dois eixos:

  eixo de exposicao    Criticidade = S x O, o maior valor entre os modos de
                       falha do componente. A Deteccao fica fora deste eixo
                       de proposito: ela governa a prioridade de acao sobre o
                       modo de falha (e por isso entra no RPN), nao a decisao
                       de ter ou nao a peca na prateleira.

  eixo de reposicao    lead time, em dias, do fornecimento da peca, lido da
                       coluna "Lead time (dias)" da aba Matriz de componentes.
                       E o tempo que o equipamento fica parado a mais por nao
                       haver a peca em estoque.

O Downtime Cost evitavel e a traducao monetaria do segundo eixo: quanto custa,
por evento de falha, o tempo de espera pela peca. Ele nao reclassifica o
componente; serve para ordenar dentro de cada zona.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Sequence

from .leitura import FMECA, Componente, ModoDeFalha, RelatorioValidacao
from .parametros import (
    FaixaCriticidade,
    FaixaLeadTime,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    Zona,
)

# Matriz de zonas. Linha = faixa de Criticidade, coluna = faixa de lead time.
MATRIZ_ZONAS: dict[tuple[FaixaCriticidade, FaixaLeadTime], Zona] = {
    (FaixaCriticidade.ALTA, FaixaLeadTime.CURTO): Zona.PONTO_PEDIDO,
    (FaixaCriticidade.ALTA, FaixaLeadTime.MEDIO): Zona.ESTOQUE_SEGURANCA,
    (FaixaCriticidade.ALTA, FaixaLeadTime.LONGO): Zona.ESTOQUE_SEGURANCA,
    (FaixaCriticidade.MEDIA, FaixaLeadTime.CURTO): Zona.SOB_DEMANDA,
    (FaixaCriticidade.MEDIA, FaixaLeadTime.MEDIO): Zona.PONTO_PEDIDO,
    (FaixaCriticidade.MEDIA, FaixaLeadTime.LONGO): Zona.ESTOQUE_SEGURANCA,
    (FaixaCriticidade.BAIXA, FaixaLeadTime.CURTO): Zona.SOB_DEMANDA,
    (FaixaCriticidade.BAIXA, FaixaLeadTime.MEDIO): Zona.SOB_DEMANDA,
    (FaixaCriticidade.BAIXA, FaixaLeadTime.LONGO): Zona.PONTO_PEDIDO,
}


# --------------------------------------------------------------------------
# Downtime Cost
# --------------------------------------------------------------------------

def downtime_cost_evitavel(
    lead_time_dias: float | None, custo: ParametrosCusto
) -> float | None:
    """
    Custo de indisponibilidade que se evita por manter a peca em estoque, em
    um evento de falha: os dias de espera pela peca cobrados ao custo do
    leito bloqueado.

        DC_evitavel = lead_time_dias x custo_leito_dia
    """
    if lead_time_dias is None:
        return None
    return lead_time_dias * custo.custo_leito_dia


def downtime_cost_anual_esperado(
    lead_time_dias: float | None,
    ocorrencia: int | None,
    custo: ParametrosCusto,
    escala: ParametrosOcorrencia,
) -> float | None:
    """
    Exposicao anual da unidade ao custo de espera por peca, em reais por ano.

        DC_anual = DC_evitavel x lambda(O) x frota
    """
    dc = downtime_cost_evitavel(lead_time_dias, custo)
    taxa = escala.taxa_anual(ocorrencia)
    if dc is None or taxa is None:
        return None
    return dc * taxa * custo.frota_equipamentos


# --------------------------------------------------------------------------
# zonas
# --------------------------------------------------------------------------

def classificar_zona(
    criticidade: float | None,
    lead_time_dias: float | None,
    zonas: ParametrosZona,
) -> tuple[Zona | None, FaixaCriticidade | None, FaixaLeadTime | None]:
    """
    Classifica um componente em uma zona de estoque.

    Devolve a zona e as duas faixas. Zona None quando falta Criticidade ou
    lead time.
    """
    if criticidade is None or lead_time_dias is None:
        return None, None, None

    faixa_c = zonas.faixa_criticidade(criticidade)
    faixa_l = zonas.faixa_lead_time(lead_time_dias)
    return MATRIZ_ZONAS[(faixa_c, faixa_l)], faixa_c, faixa_l


# --------------------------------------------------------------------------
# resultado por componente
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisaoComponente:
    componente: Componente
    criticidade: int | None
    rpn: int | None
    ocorrencia: int | None
    severidade: int | None
    modo_dimensionante: ModoDeFalha | None
    lead_time_dias: float | None
    faixa_criticidade: FaixaCriticidade | None
    faixa_lead_time: FaixaLeadTime | None
    zona: Zona | None
    dc_evitavel: float | None
    taxa_falha_anual: float | None
    dc_anual_esperado: float | None
    justificativa: str
    # modos com Deteccao a partir do limiar de falha oculta, por RPN decrescente
    modos_ocultos: tuple[ModoDeFalha, ...] = ()

    @property
    def id(self) -> int:
        return self.componente.id

    @property
    def nome(self) -> str:
        return self.componente.nome

    @property
    def decidido(self) -> bool:
        return self.zona is not None


def _modo_dimensionante(modos: Sequence[ModoDeFalha]) -> ModoDeFalha | None:
    """
    O modo que fixa a Criticidade do componente: maior S x O. Empates sao
    resolvidos pelo maior RPN e, depois, pela ordem do Sub ID, para que o
    resultado seja estavel entre execucoes.
    """
    candidatos = [m for m in modos if m.criticidade_calculada is not None]
    if not candidatos:
        return None
    return max(
        candidatos,
        key=lambda m: (
            m.criticidade_calculada or 0,
            m.rpn_calculado or 0,
            # Sub ID decrescente, para que o menor vença o empate
            tuple(-int(p) for p in m.sub_id.split(".") if p.isdigit()),
        ),
    )


def _justificar(
    criticidade: int | None,
    lead_time: float | None,
    faixa_c: FaixaCriticidade | None,
    faixa_l: FaixaLeadTime | None,
    zona: Zona | None,
    modo: ModoDeFalha | None,
    modos_ocultos: Sequence[ModoDeFalha] = (),
) -> str:
    if zona is None:
        faltantes = []
        if criticidade is None:
            faltantes.append("Criticidade (sem modo de falha pontuado)")
        if lead_time is None:
            faltantes.append("lead time (em branco na Matriz de componentes)")
        return "Sem zona atribuída: falta " + " e ".join(faltantes) + "."

    partes = [
        f"Criticidade {criticidade} ({faixa_c.rotulo.lower()}) "
        f"e lead time de {_fmt_dias(lead_time)} ({faixa_l.rotulo.lower()}) "
        f"situam o componente em «{zona.rotulo}»."
    ]
    if modo is not None and modo.modo:
        partes.append(
            f"A Criticidade é fixada pelo modo {modo.sub_id} — {modo.modo} "
            f"(S={modo.severidade}, O={modo.ocorrencia})."
        )
    if modos_ocultos:
        partes.append(_alerta_oculta(modos_ocultos))
    return " ".join(partes)


def _alerta_oculta(modos: Sequence[ModoDeFalha]) -> str:
    refs = [f"{m.sub_id} (D={m.deteccao_nota})" for m in modos]
    if len(refs) == 1:
        lista = f"o modo {refs[0]} é de falha oculta"
    else:
        lista = f"os modos {', '.join(refs[:-1])} e {refs[-1]} são de falha oculta"
    return (
        f"Atenção: {lista}. A peça em estoque encurta o reparo, mas não "
        "antecipa a descoberta da falha, que só aparece no uso crítico; "
        "inclua teste funcional na manutenção preventiva."
    )


def _fmt_dias(dias: float | None) -> str:
    if dias is None:
        return "—"
    if float(dias).is_integer():
        return f"{int(dias)} dias"
    return f"{dias:.1f} dias".replace(".", ",")


def escala_do_formulario(
    fmeca: FMECA, escala: ParametrosOcorrencia | None = None
) -> ParametrosOcorrencia:
    """
    A escala de Ocorrencia a usar: as faixas lidas da aba Tabela do formulario,
    quando houver, com a posicao na faixa de `escala`. Sem faixas lidas, fica a
    escala padrao.
    """
    escala = escala or ParametrosOcorrencia()
    if fmeca.escala_ocorrencia is None:
        return escala
    return replace(escala, faixas=fmeca.escala_ocorrencia)


def decidir(
    fmeca: FMECA,
    custo: ParametrosCusto | None = None,
    zonas: ParametrosZona | None = None,
    validacao: RelatorioValidacao | None = None,
    escala_ocorrencia: ParametrosOcorrencia | None = None,
    deteccao: ParametrosDeteccao | None = None,
) -> list[DecisaoComponente]:
    """
    Aplica o modelo a todos os componentes do formulario.

    A Criticidade usada e o maximo de S x O entre os modos do componente,
    recalculado a partir das notas; o valor declarado na aba de matriz serve
    apenas de recurso quando o componente nao tem modos pontuados. A
    divergencia entre os dois, se houver, e reportada na validacao da leitura.

    `deteccao` nao altera a zona: so marca os modos de falha oculta, que
    entram na justificativa como alerta.

    Sem `escala_ocorrencia`, a taxa de falha usa a escala lida da aba Tabela
    (ver escala_do_formulario). Uma escala informada e usada como esta.
    """
    custo = custo or ParametrosCusto()
    zonas = zonas or ParametrosZona()
    escala_ocorrencia = escala_ocorrencia or escala_do_formulario(fmeca)
    deteccao = deteccao or ParametrosDeteccao()

    decisoes: list[DecisaoComponente] = []
    for comp in fmeca.componentes:
        modos = fmeca.modos_de(comp.id)
        modo = _modo_dimensionante(modos)

        criticidades = [
            m.criticidade_calculada for m in modos if m.criticidade_calculada is not None
        ]
        rpns = [m.rpn_calculado for m in modos if m.rpn_calculado is not None]
        criticidade = max(criticidades) if criticidades else comp.criticidade
        rpn = max(rpns) if rpns else comp.rpn

        # S e O vem do modo dimensionante, e nao do maximo de cada nota, para
        # que S x O exibidos fechem com a Criticidade usada.
        severidade = modo.severidade if modo else None
        ocorrencia = modo.ocorrencia if modo else None

        ocorrencias = [m.ocorrencia for m in modos if m.ocorrencia is not None]
        if validacao is not None and ocorrencia is not None and ocorrencias:
            if max(ocorrencias) > ocorrencia:
                outro = max(
                    (m for m in modos if m.ocorrencia == max(ocorrencias)),
                    key=lambda m: m.criticidade_calculada or 0,
                )
                validacao.aviso(
                    f"componente {comp.id} ({comp.nome}): o modo dimensionante "
                    f"{modo.sub_id} tem Ocorrência {ocorrencia}, mas o modo "
                    f"{outro.sub_id} tem {outro.ocorrencia}. A exposição anual usa "
                    f"a Ocorrência do modo dimensionante e pode estar subestimada"
                )

        lead = comp.lead_time_dias
        zona, faixa_c, faixa_l = classificar_zona(criticidade, lead, zonas)
        dc = downtime_cost_evitavel(lead, custo)
        taxa = escala_ocorrencia.taxa_anual(ocorrencia)
        dc_anual = downtime_cost_anual_esperado(lead, ocorrencia, custo, escala_ocorrencia)
        ocultos = tuple(
            sorted(
                (m for m in modos if deteccao.oculta(m.deteccao_nota)),
                key=lambda m: -(m.rpn_calculado or 0),
            )
        )

        decisoes.append(
            DecisaoComponente(
                componente=comp,
                criticidade=criticidade,
                rpn=rpn,
                ocorrencia=ocorrencia,
                severidade=severidade,
                modo_dimensionante=modo,
                lead_time_dias=lead,
                faixa_criticidade=faixa_c,
                faixa_lead_time=faixa_l,
                zona=zona,
                dc_evitavel=dc,
                taxa_falha_anual=taxa,
                dc_anual_esperado=dc_anual,
                justificativa=_justificar(
                    criticidade, lead, faixa_c, faixa_l, zona, modo, ocultos,
                ),
                modos_ocultos=ocultos,
            )
        )

    return decisoes


# --------------------------------------------------------------------------
# agregados
# --------------------------------------------------------------------------

def resumo_por_zona(decisoes: Sequence[DecisaoComponente]) -> dict[str, dict[str, Any]]:
    """Contagem e exposicao somada por zona."""
    resumo: dict[str, dict[str, Any]] = {}
    for zona in (Zona.ESTOQUE_SEGURANCA, Zona.PONTO_PEDIDO, Zona.SOB_DEMANDA):
        itens = [d for d in decisoes if d.zona is zona]
        resumo[zona.rotulo] = {
            "componentes": len(itens),
            "ids": [d.id for d in itens],
            "dc_evitavel_total": sum(d.dc_evitavel or 0.0 for d in itens),
            "dc_anual_total": sum(d.dc_anual_esperado or 0.0 for d in itens),
        }
    sem_zona = [d for d in decisoes if d.zona is None]
    resumo["Sem zona atribuída"] = {
        "componentes": len(sem_zona),
        "ids": [d.id for d in sem_zona],
        "dc_evitavel_total": 0.0,
        "dc_anual_total": 0.0,
    }
    return resumo


def ordenar_para_relatorio(
    decisoes: Sequence[DecisaoComponente],
) -> list[DecisaoComponente]:
    """
    Ordena por compromisso de estoque decrescente, depois pela exposicao anual
    esperada, depois por Criticidade. Componentes sem zona vao para o fim.
    """
    return sorted(
        decisoes,
        key=lambda d: (
            -(d.zona.ordem if d.zona else -1),
            -(d.dc_anual_esperado or 0.0),
            -(d.criticidade or 0),
            d.id,
        ),
    )
