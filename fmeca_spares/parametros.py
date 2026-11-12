"""Parametros do modelo: faixas, limiares e custo de leito bloqueado."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# Rotulo do componente que nao recebe zona, por faltar Criticidade ou lead
# time. Unico, porque e tambem chave do resumo por zona.
SEM_ZONA = "Sem zona atribuída"

# Teto das escalas de onde vem cada par de limiares, para separar_limiares.
TETO_CRITICIDADE = 100
TETO_LEAD_TIME_DIAS = 180


def separar_limiares(baixo: int, alto: int, teto: int) -> tuple[int, int]:
    """
    Garante baixo < alto em um par de limiares vindo de um controle de dois
    valores, cujos cursores podem parar no mesmo ponto.

    Abre espaco para cima; com o par ja no teto da escala, abre para baixo, do
    contrario o limiar de cima estouraria o teto e ParametrosZona recusaria o
    par.
    """
    if baixo < alto:
        return baixo, alto
    if alto >= teto:
        return alto - 1, alto
    return baixo, baixo + 1


class Zona(str, Enum):
    """Zonas de decisao de estoque da Etapa 2."""

    ESTOQUE_SEGURANCA = "Estoque de seguranca local"
    PONTO_PEDIDO = "Ponto de pedido"
    SOB_DEMANDA = "Compra sob demanda"

    @property
    def rotulo(self) -> str:
        """Rotulo acentuado, para exibicao."""
        return {
            Zona.ESTOQUE_SEGURANCA: "Estoque de segurança local",
            Zona.PONTO_PEDIDO: "Ponto de pedido",
            Zona.SOB_DEMANDA: "Compra sob demanda",
        }[self]

    @property
    def ordem(self) -> int:
        """Ordem crescente de compromisso de estoque (0 = menor)."""
        return {
            Zona.SOB_DEMANDA: 0,
            Zona.PONTO_PEDIDO: 1,
            Zona.ESTOQUE_SEGURANCA: 2,
        }[self]


class FaixaCriticidade(str, Enum):
    BAIXA = "Baixa"
    MEDIA = "Media"
    ALTA = "Alta"

    @property
    def rotulo(self) -> str:
        return {
            FaixaCriticidade.BAIXA: "Baixa",
            FaixaCriticidade.MEDIA: "Média",
            FaixaCriticidade.ALTA: "Alta",
        }[self]


class FaixaLeadTime(str, Enum):
    CURTO = "Curto"
    MEDIO = "Medio"
    LONGO = "Longo"

    @property
    def rotulo(self) -> str:
        return {
            FaixaLeadTime.CURTO: "Curto",
            FaixaLeadTime.MEDIO: "Médio",
            FaixaLeadTime.LONGO: "Longo",
        }[self]


@dataclass(frozen=True)
class ParametrosZona:
    """
    Limiares que delimitam as faixas de Criticidade e de lead time.

    criticidade_alta = 40      S 8 x O 5 ou S 10 x O 4
    criticidade_media = 20     S 10 x O 2 ou S 4 x O 5
    lead_time_curto_dias = 7   teto da faixa curta (fornecedor nacional)
    lead_time_longo_dias = 30  teto da faixa media (importacao)

    O limiar de Criticidade pertence a faixa de cima; o de lead time, a de
    baixo.
    """

    criticidade_alta: int = 40
    criticidade_media: int = 20
    lead_time_curto_dias: float = 7.0
    lead_time_longo_dias: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.criticidade_media < self.criticidade_alta <= 100:
            raise ValueError(
                "limiares de criticidade invalidos: exige-se "
                "1 <= criticidade_media < criticidade_alta <= 100 "
                f"(recebido media={self.criticidade_media}, "
                f"alta={self.criticidade_alta})"
            )
        if not 0 < self.lead_time_curto_dias < self.lead_time_longo_dias:
            raise ValueError(
                "limiares de lead time invalidos: exige-se "
                "0 < lead_time_curto_dias < lead_time_longo_dias "
                f"(recebido curto={self.lead_time_curto_dias}, "
                f"longo={self.lead_time_longo_dias})"
            )

    def faixa_criticidade(self, criticidade: float) -> FaixaCriticidade:
        if criticidade >= self.criticidade_alta:
            return FaixaCriticidade.ALTA
        if criticidade >= self.criticidade_media:
            return FaixaCriticidade.MEDIA
        return FaixaCriticidade.BAIXA

    def faixa_lead_time(self, lead_time_dias: float) -> FaixaLeadTime:
        if lead_time_dias > self.lead_time_longo_dias:
            return FaixaLeadTime.LONGO
        if lead_time_dias > self.lead_time_curto_dias:
            return FaixaLeadTime.MEDIO
        return FaixaLeadTime.CURTO


@dataclass(frozen=True)
class ParametrosOcorrencia:
    """
    Traducao da nota de Ocorrencia em taxa de falha anual por unidade.

    `faixas` sao (nota minima, nota maxima, lambda piso, lambda teto). O
    padrao abaixo vale quando a escala da aba "Tabela" nao pode ser lida (ver
    leitura.ler_escala_ocorrencia). A faixa aberta de baixo tem piso 0; a de
    cima, sem teto declarado, e fixada no proprio piso.

    `posicao_na_faixa` escolhe o ponto do intervalo: 0 no piso, 0,5 no meio,
    1 no teto.
    """

    faixas: tuple[tuple[int, int, float, float], ...] = (
        (1, 2, 0.0, 0.5),
        (3, 4, 0.5, 0.9),
        (5, 6, 1.0, 1.9),
        (7, 8, 2.0, 3.9),
        (9, 10, 4.0, 4.0),
    )
    posicao_na_faixa: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.posicao_na_faixa <= 1.0:
            raise ValueError(
                "posicao_na_faixa deve estar entre 0 e 1 "
                f"(recebido {self.posicao_na_faixa})"
            )

    def taxa_anual(self, ocorrencia: int | None) -> float | None:
        """Taxa de falha anual por unidade correspondente a nota informada."""
        if ocorrencia is None:
            return None
        for minimo, maximo, piso, teto in self.faixas:
            if minimo <= ocorrencia <= maximo:
                return piso + (teto - piso) * self.posicao_na_faixa
        return None

    def faixa_texto(self, ocorrencia: int | None) -> str | None:
        if ocorrencia is None:
            return None
        for minimo, maximo, piso, teto in self.faixas:
            if minimo <= ocorrencia <= maximo:
                if piso == teto:
                    return f"O {minimo}–{maximo}: λ fixado em {piso:g} falha/ano (piso da faixa aberta)"
                return f"O {minimo}–{maximo}: λ de {piso:g} a {teto:g} falha/ano"
        return None


@dataclass(frozen=True)
class ParametrosDeteccao:
    """
    Limiar de falha oculta, lido da nota de Deteccao de cada modo de falha.

    Nao altera a zona de estoque: so marca, na justificativa, os modos com D
    a partir de `limiar_oculta` (padrao 7, falha oculta ate o uso critico na
    escala de Deteccao do formulario).
    """

    limiar_oculta: int = 7

    def __post_init__(self) -> None:
        if not 1 <= self.limiar_oculta <= 10:
            raise ValueError(
                "limiar_oculta deve estar entre 1 e 10 "
                f"(recebido {self.limiar_oculta})"
            )

    def oculta(self, deteccao: int | None) -> bool:
        return deteccao is not None and deteccao >= self.limiar_oculta


# Diarias de UTI adulto na tabela do SUS (SIGTAP 08.02.01.008-3 e
# 08.02.01.009-1), Portaria GM/MS no 160, de 25 de fevereiro de 2022.
DIARIA_UTI_II_SUS = 600.0
DIARIA_UTI_III_SUS = 700.0


@dataclass(frozen=True)
class ParametrosCusto:
    """
    Parametros do Downtime Cost.

    O custo de indisponibilidade tem um coeficiente so: o custo do leito
    bloqueado, cobrado por dia de espera pela peca.

        DC_evitavel = lead_time_dias x custo_leito_dia

    custo_leito_dia
        Custo de um dia de leito bloqueado. O padrao e a diaria de UTI II
        adulto da tabela do SUS (ver DIARIA_UTI_II_SUS). Para UTI III, use
        DIARIA_UTI_III_SUS; para um custo apurado pela controladoria do
        hospital, informe o valor proprio.

    frota_equipamentos
        Numero de equipamentos da tecnologia em operacao na unidade.
        Multiplica a taxa de falha por unidade para chegar a exposicao anual
        da unidade.
    """

    custo_leito_dia: float = DIARIA_UTI_II_SUS
    frota_equipamentos: int = 1

    def __post_init__(self) -> None:
        if self.frota_equipamentos < 1:
            raise ValueError(
                "frota_equipamentos deve ser ao menos 1 "
                f"(recebido {self.frota_equipamentos})"
            )
        if self.custo_leito_dia < 0:
            raise ValueError("custo_leito_dia nao pode ser negativo")

    @property
    def declarado(self) -> bool:
        """True quando ha custo de leito bloqueado informado."""
        return self.custo_leito_dia > 0
