"""
Parametros do modelo: faixas, limiares e custo de leito bloqueado.

Todos os parametros monetarios nascem em zero. A escolha e deliberada: o modulo
nao embute valores de custo hospitalar, porque nao ha fonte publica brasileira
que os sustente de forma generica. Quem aplica o modelo informa os proprios
valores, e o app oferece um cenario ilustrativo explicitamente rotulado como
tal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


class AcaoDeteccao(str, Enum):
    """Acao de manutencao recomendada pela nota de Deteccao de um modo de falha."""

    TESTE_FUNCIONAL = "Incluir teste funcional na preventiva"
    MANTER_PREVENTIVA = "Manter o intervalo da preventiva"
    ADEQUADA = "Deteccao adequada"

    @property
    def rotulo(self) -> str:
        return {
            AcaoDeteccao.TESTE_FUNCIONAL: "Incluir teste funcional na preventiva",
            AcaoDeteccao.MANTER_PREVENTIVA: "Manter o intervalo da preventiva",
            AcaoDeteccao.ADEQUADA: "Detecção adequada",
        }[self]

    @property
    def ordem(self) -> int:
        """Ordem crescente de urgencia (0 = menor)."""
        return {
            AcaoDeteccao.ADEQUADA: 0,
            AcaoDeteccao.MANTER_PREVENTIVA: 1,
            AcaoDeteccao.TESTE_FUNCIONAL: 2,
        }[self]


@dataclass(frozen=True)
class ParametrosZona:
    """
    Limiares que delimitam as faixas de Criticidade e de lead time.

    Defaults e sua justificativa (ver README, secao "Calibracao dos limiares"):

    criticidade_alta = 40
        Menor produto S x O que combina perda de funcao critica com ocorrencia
        ao menos ocasional: S=8 (equipamento retirado de uso, risco potencial
        ao paciente) com O=5 (falha ocasional), ou S=10 com O=4.

    criticidade_media = 20
        Piso da faixa em que a exposicao vem de um dos dois eixos isoladamente:
        severidade critica com ocorrencia rara (S=10, O=2) ou severidade
        moderada com ocorrencia frequente (S=4, O=5).

    lead_time_curto_dias = 7
        Fornecimento que devolve o equipamento a operacao na mesma semana,
        compativel com peca nacional ou pronta entrega.

    lead_time_longo_dias = 30
        Acima de um mes de equipamento parado por falta de peca; faixa tipica
        de importacao sem representacao consolidada no pais.
    """

    criticidade_alta: int = 40
    criticidade_media: int = 20
    lead_time_curto_dias: float = 7.0
    lead_time_longo_dias: float = 30.0

    # Consumiveis (Natureza = Consumivel na Matriz de componentes) tem demanda
    # determinada pelo intervalo de troca, nao pela ocorrencia de falha.
    # Quando verdadeiro, nenhum deles e classificado como compra sob demanda:
    # o piso e o ponto de pedido. E a correcao de um vies conhecido do modelo:
    # um item trocado por calendario pontua Ocorrencia baixa nas notificacoes
    # de falha e, sem este piso, seria subdimensionado.
    piso_ponto_pedido_demanda_programada: bool = True

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

    As faixas vem da propria escala de Ocorrencia do formulario FMECA (aba
    "Tabela"), que define cada par de notas por um intervalo de lambda:

        O 1-2   lambda < 0,5 falha/ano por unidade
        O 3-4   0,5 a 1,0
        O 5-6   1,0 a 1,5
        O 7-8   1,5 a 3,0
        O 9-10  lambda > 3,0

    O modelo nao estima lambda a partir dos dados: ele apenas le a escala que
    o analista declarou ao pontuar. A faixa aberta embaixo recebe piso 0, que
    e o limite natural de uma taxa. A faixa aberta em cima nao tem teto na
    escala e e tomada no proprio piso (3,0), com piso = teto: e a leitura
    conservadora, que subestima a exposicao em vez de supor um teto que a
    escala nao declara.

    `posicao_na_faixa` escolhe onde, dentro da faixa, o valor e tomado: 0,0 no
    piso, 0,5 no meio, 1,0 no teto. Serve de alavanca de sensibilidade: rodar
    o modelo em 0,0 e em 1,0 produz o intervalo de custo compativel com a
    mesma pontuacao de FMECA. Nao afeta a faixa O 9-10, fixada no piso.
    """

    faixas: tuple[tuple[int, int, float, float], ...] = (
        (1, 2, 0.0, 0.5),
        (3, 4, 0.5, 1.0),
        (5, 6, 1.0, 1.5),
        (7, 8, 1.5, 3.0),
        (9, 10, 3.0, 3.0),
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
    Limiares do plano de acao, que le a nota de Deteccao de cada modo de falha.

    A Deteccao fica fora da decisao de estoque (ver modelo.py): uma falha
    facil de detectar continua exigindo a peca. Ela orienta, em vez disso, a
    manutencao. Os defaults vem da escala de Deteccao do formulario FMECA (aba
    "Tabela"):

        D 1-4   alarme automatico ou checagem de rotina: deteccao adequada
        D 5-6   depende de inspecao periodica ou preventiva
        D 7-8   falha oculta ate o uso critico do equipamento
        D 9-10  sem mecanismo de alerta; so percebida pela consequencia

    limiar_oculta = 7
        A partir daqui a falha so aparece no uso critico. A peca em estoque
        encurta o reparo, mas nao antecipa a descoberta da falha: a acao que
        reduz o risco e o teste funcional na manutencao preventiva.

    limiar_preventiva = 5
        A partir daqui a deteccao depende da preventiva, cujo intervalo deve
        ser mantido.

    severidade_alerta = 9
        Modo de falha com Severidade a partir deste valor e Deteccao oculta
        recebe alerta quando o componente nao esta em estoque de seguranca. E
        o caso que a Criticidade (S x O) subestima: falha catastrofica, rara e
        oculta, que cai na faixa media pela Ocorrencia baixa.
    """

    limiar_oculta: int = 7
    limiar_preventiva: int = 5
    severidade_alerta: int = 9

    def __post_init__(self) -> None:
        if not 1 <= self.limiar_preventiva < self.limiar_oculta <= 10:
            raise ValueError(
                "limiares de deteccao invalidos: exige-se "
                "1 <= limiar_preventiva < limiar_oculta <= 10 "
                f"(recebido preventiva={self.limiar_preventiva}, "
                f"oculta={self.limiar_oculta})"
            )
        if not 1 <= self.severidade_alerta <= 10:
            raise ValueError(
                "severidade_alerta deve estar entre 1 e 10 "
                f"(recebido {self.severidade_alerta})"
            )

    def acao(self, deteccao: int | None) -> AcaoDeteccao | None:
        """Acao recomendada para a nota de Deteccao informada."""
        if deteccao is None:
            return None
        if deteccao >= self.limiar_oculta:
            return AcaoDeteccao.TESTE_FUNCIONAL
        if deteccao >= self.limiar_preventiva:
            return AcaoDeteccao.MANTER_PREVENTIVA
        return AcaoDeteccao.ADEQUADA

    def oculta(self, deteccao: int | None) -> bool:
        return deteccao is not None and deteccao >= self.limiar_oculta


# Diaria de UTI II adulto na tabela do SUS, procedimento SIGTAP
# 08.02.01.008-3, fixada pela Portaria GM/MS no 160, de 25 de fevereiro de
# 2022 (republicada): R$ 510,00 de Servico Hospitalar mais R$ 90,00 de
# Servico Profissional. E o valor que a unidade deixa de faturar por cada dia
# em que o leito nao pode ser ocupado, e por isso serve de custo de
# oportunidade do leito bloqueado.
#
# Dois avisos de uso. Primeiro, o valor e de 2022: confira a tabela SIGTAP
# vigente antes de citar. Segundo, a diaria do SUS esta abaixo do custo
# operacional efetivo de um leito de UTI — Guimaraes, Dallora e Favaro
# (Revista Qualidade HC, n. 57) apuraram R$ 1.114,10 por paciente-dia nas UTIs
# COVID do HC-FMRP no primeiro semestre de 2021 contando apenas materiais e
# medicamentos. Adotar a diaria do SUS e, portanto, a escolha conservadora.
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
