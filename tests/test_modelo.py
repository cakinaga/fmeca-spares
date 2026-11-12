"""Testes do modelo de decisao: Downtime Cost, faixas e zonas."""

from __future__ import annotations

import pytest
from conftest import construir_fmeca

from fmeca_spares import (
    DIARIA_UTI_II_SUS,
    DIARIA_UTI_III_SUS,
    FaixaCriticidade,
    FaixaLeadTime,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    TETO_CRITICIDADE,
    TETO_LEAD_TIME_DIAS,
    Zona,
    classificar_zona,
    decidir,
    downtime_cost_anual_esperado,
    downtime_cost_evitavel,
    ler_fmeca,
    ordenar_para_relatorio,
    resumo_por_zona,
    separar_limiares,
)
from fmeca_spares.modelo import MATRIZ_ZONAS


# -- validacao dos parametros ----------------------------------------------

def test_limiares_de_criticidade_invertidos_sao_rejeitados():
    with pytest.raises(ValueError):
        ParametrosZona(criticidade_media=50, criticidade_alta=40)


def test_limiares_de_lead_time_invertidos_sao_rejeitados():
    with pytest.raises(ValueError):
        ParametrosZona(lead_time_curto_dias=40, lead_time_longo_dias=10)


def test_custo_negativo_e_rejeitado():
    with pytest.raises(ValueError):
        ParametrosCusto(custo_leito_dia=-1)


def test_frota_menor_que_um_e_rejeitada():
    with pytest.raises(ValueError):
        ParametrosCusto(frota_equipamentos=0)


def test_posicao_na_faixa_fora_do_intervalo_e_rejeitada():
    with pytest.raises(ValueError):
        ParametrosOcorrencia(posicao_na_faixa=1.2)


# -- separacao dos limiares vindos de um controle de dois valores -----------

def test_separar_limiares_mantem_par_valido():
    assert separar_limiares(20, 40, TETO_CRITICIDADE) == (20, 40)


def test_separar_limiares_abre_espaco_para_cima():
    assert separar_limiares(20, 20, TETO_CRITICIDADE) == (20, 21)


def test_separar_limiares_no_teto_abre_espaco_para_baixo():
    """
    Os dois cursores no teto da escala: o limiar de cima nao pode passar do
    teto, senao ParametrosZona recusa o par e a interface quebra.
    """
    assert separar_limiares(100, 100, TETO_CRITICIDADE) == (99, 100)
    assert separar_limiares(180, 180, TETO_LEAD_TIME_DIAS) == (179, 180)


@pytest.mark.parametrize("par", [(1, 1), (20, 20), (99, 99), (100, 100)])
def test_limiares_separados_sao_sempre_aceitos(par):
    media, alta = separar_limiares(*par, TETO_CRITICIDADE)
    ParametrosZona(criticidade_media=media, criticidade_alta=alta)


# -- faixas -----------------------------------------------------------------

def test_faixas_de_criticidade_nos_limites():
    z = ParametrosZona(criticidade_media=20, criticidade_alta=40)
    assert z.faixa_criticidade(19) is FaixaCriticidade.BAIXA
    assert z.faixa_criticidade(20) is FaixaCriticidade.MEDIA
    assert z.faixa_criticidade(39) is FaixaCriticidade.MEDIA
    assert z.faixa_criticidade(40) is FaixaCriticidade.ALTA
    assert z.faixa_criticidade(100) is FaixaCriticidade.ALTA


def test_faixas_de_lead_time_nos_limites():
    z = ParametrosZona(lead_time_curto_dias=7, lead_time_longo_dias=30)
    assert z.faixa_lead_time(0) is FaixaLeadTime.CURTO
    assert z.faixa_lead_time(7) is FaixaLeadTime.CURTO
    assert z.faixa_lead_time(7.5) is FaixaLeadTime.MEDIO
    assert z.faixa_lead_time(30) is FaixaLeadTime.MEDIO
    assert z.faixa_lead_time(31) is FaixaLeadTime.LONGO


# -- Downtime Cost ----------------------------------------------------------

def test_dc_evitavel_depende_so_do_lead_time():
    custo = ParametrosCusto(custo_leito_dia=1000,)
    assert downtime_cost_evitavel(10, custo) == 10_000
    assert downtime_cost_evitavel(0, custo) == 0
    assert downtime_cost_evitavel(None, custo) is None


def test_dc_usa_o_custo_de_leito_bloqueado_como_unico_termo():
    custo = ParametrosCusto(custo_leito_dia=600.0)
    assert downtime_cost_evitavel(5, custo) == 3000.0


def test_diaria_padrao_e_a_do_sus_para_uti_ii():
    assert ParametrosCusto().custo_leito_dia == DIARIA_UTI_II_SUS == 600.0
    assert DIARIA_UTI_III_SUS == 700.0


def test_custo_declarado_e_falso_sem_custo_de_leito():
    assert ParametrosCusto(custo_leito_dia=0).declarado is False
    assert ParametrosCusto(custo_leito_dia=1).declarado is True


# -- escala de ocorrencia ---------------------------------------------------

def test_taxa_anual_no_meio_da_faixa():
    esc = ParametrosOcorrencia(posicao_na_faixa=0.5)
    assert esc.taxa_anual(1) == pytest.approx(0.25)
    assert esc.taxa_anual(2) == pytest.approx(0.25)
    assert esc.taxa_anual(3) == pytest.approx(0.70)
    assert esc.taxa_anual(5) == pytest.approx(1.45)
    assert esc.taxa_anual(7) == pytest.approx(2.95)
    assert esc.taxa_anual(9) == pytest.approx(4.0)
    assert esc.taxa_anual(None) is None


def test_taxa_anual_nos_extremos_da_faixa():
    assert ParametrosOcorrencia(posicao_na_faixa=0.0).taxa_anual(5) == pytest.approx(1.0)
    assert ParametrosOcorrencia(posicao_na_faixa=1.0).taxa_anual(5) == pytest.approx(1.9)


def test_faixa_aberta_em_cima_fica_no_piso():
    for posicao in (0.0, 0.5, 1.0):
        esc = ParametrosOcorrencia(posicao_na_faixa=posicao)
        assert esc.taxa_anual(9) == pytest.approx(4.0)
        assert esc.taxa_anual(10) == pytest.approx(4.0)


def test_faixas_cobrem_toda_a_escala_sem_sobreposicao():
    esc = ParametrosOcorrencia()
    assert all(esc.taxa_anual(o) is not None for o in range(1, 11))
    assert esc.taxa_anual(0) is None
    assert esc.taxa_anual(11) is None
    limites = [(a, b) for a, b, _, _ in esc.faixas]
    for (_, fim), (inicio, _) in zip(limites, limites[1:]):
        assert inicio == fim + 1


def test_dc_anual_multiplica_taxa_e_frota():
    custo = ParametrosCusto(
        custo_leito_dia=1000, frota_equipamentos=10
    )
    esc = ParametrosOcorrencia(posicao_na_faixa=0.5)
    # DC por evento = 10 x 1000 = 10.000; lambda(O=5) = 1,45; frota = 10
    assert downtime_cost_anual_esperado(10, 5, custo, esc) == pytest.approx(145_000)
    assert downtime_cost_anual_esperado(10, None, custo, esc) is None
    assert downtime_cost_anual_esperado(None, 5, custo, esc) is None


# -- zonas ------------------------------------------------------------------

def test_matriz_de_zonas_cobre_as_nove_celulas():
    assert len(MATRIZ_ZONAS) == 9
    for fc in FaixaCriticidade:
        for fl in FaixaLeadTime:
            assert (fc, fl) in MATRIZ_ZONAS


def test_zona_e_monotona_nos_dois_eixos():
    """Subir a Criticidade ou o lead time nunca reduz o compromisso de estoque."""
    ordem_c = [FaixaCriticidade.BAIXA, FaixaCriticidade.MEDIA, FaixaCriticidade.ALTA]
    ordem_l = [FaixaLeadTime.CURTO, FaixaLeadTime.MEDIO, FaixaLeadTime.LONGO]
    for i, fc in enumerate(ordem_c):
        for j, fl in enumerate(ordem_l):
            atual = MATRIZ_ZONAS[(fc, fl)].ordem
            if i + 1 < len(ordem_c):
                assert MATRIZ_ZONAS[(ordem_c[i + 1], fl)].ordem >= atual
            if j + 1 < len(ordem_l):
                assert MATRIZ_ZONAS[(fc, ordem_l[j + 1])].ordem >= atual


def test_classificar_zona_nas_quatro_pontas():
    z = ParametrosZona()
    assert classificar_zona(90, 60, z)[0] is Zona.ESTOQUE_SEGURANCA
    assert classificar_zona(90, 3, z)[0] is Zona.PONTO_PEDIDO
    assert classificar_zona(5, 60, z)[0] is Zona.PONTO_PEDIDO
    assert classificar_zona(5, 3, z)[0] is Zona.SOB_DEMANDA


def test_zona_ausente_sem_criticidade_ou_lead_time():
    z = ParametrosZona()
    assert classificar_zona(None, 10, z)[0] is None
    assert classificar_zona(50, None, z)[0] is None


# -- decisao ----------------------------------------------------------------

_MODOS_SIMPLES = [
    (1, "1.1", "Crítica", "Pneumático", "Modo grave", 6, 10, 8, 480, 60),
    (1, "1.2", "Crítica", "Pneumático", "Modo leve", 2, 5, 3, 30, 10),
    (2, "2.1", "Comum", "Elétrico", "Modo comum", 2, 3, 5, 30, 6),
    (3, "3.1", "Filtro", "Proteção", "Saturação", 2, 3, 4, 24, 6),
]


def _caso_simples(lead_time_comum=3):
    return ler_fmeca(
        construir_fmeca(
            componentes=[
                (1, "Crítica", "Pneumático", "F", "Peça", 480, 60, 45),
                (2, "Comum", "Elétrico", "F", "Peça", 30, 6, lead_time_comum),
                (3, "Filtro", "Proteção", "F", "Consumível", 24, 6, 3),
            ],
            modos=_MODOS_SIMPLES,
        )
    )


def test_decidir_atribui_zonas_esperadas():
    fmeca = _caso_simples()
    decisoes = {d.id: d for d in decidir(fmeca)}
    assert decisoes[1].zona is Zona.ESTOQUE_SEGURANCA
    assert decisoes[2].zona is Zona.SOB_DEMANDA
    assert decisoes[3].zona is Zona.SOB_DEMANDA


def test_lead_time_vem_da_matriz_de_componentes():
    fmeca = _caso_simples()
    decisoes = {d.id: d for d in decidir(fmeca)}
    assert decisoes[1].lead_time_dias == 45
    assert decisoes[2].lead_time_dias == 3


def test_criticidade_usada_e_o_maximo_dos_modos():
    fmeca = _caso_simples()
    decisoes = {d.id: d for d in decidir(fmeca)}
    assert decisoes[1].criticidade == 60
    assert decisoes[1].rpn == 480
    assert decisoes[1].ocorrencia == 6
    assert decisoes[1].severidade == 10


def test_modo_dimensionante_e_o_de_maior_criticidade():
    fmeca = _caso_simples()
    decisoes = {d.id: d for d in decidir(fmeca)}
    assert decisoes[1].modo_dimensionante.sub_id == "1.1"


def test_dc_anual_da_decisao_e_dc_por_evento_vezes_taxa():
    fmeca = _caso_simples()
    custo = ParametrosCusto(
        custo_leito_dia=1000, frota_equipamentos=1
    )
    d = {x.id: x for x in decidir(fmeca, custo)}[1]
    assert d.dc_evitavel == pytest.approx(45 * 1000)
    assert d.dc_anual_esperado == pytest.approx(d.dc_evitavel * d.taxa_falha_anual)


def test_componente_sem_lead_time_fica_sem_zona():
    fmeca = _caso_simples(lead_time_comum=None)
    decisoes = {d.id: d for d in decidir(fmeca)}
    assert decisoes[1].decidido is True
    assert decisoes[2].decidido is False
    assert decisoes[2].zona is None
    assert "em branco na Matriz de componentes" in decisoes[2].justificativa


def test_justificativa_menciona_faixas_e_modo():
    fmeca = _caso_simples()
    d = {x.id: x for x in decidir(fmeca)}[1]
    assert "Criticidade 60" in d.justificativa
    assert "45 dias" in d.justificativa
    assert "1.1" in d.justificativa


def test_resumo_por_zona_soma_e_conta():
    fmeca = _caso_simples()
    custo = ParametrosCusto(
        custo_leito_dia=1000,
    )
    decisoes = decidir(fmeca, custo)
    resumo = resumo_por_zona(decisoes)
    assert resumo[Zona.ESTOQUE_SEGURANCA.rotulo]["componentes"] == 1
    assert resumo[Zona.PONTO_PEDIDO.rotulo]["componentes"] == 0
    assert resumo[Zona.SOB_DEMANDA.rotulo]["componentes"] == 2
    assert resumo["Sem zona atribuída"]["componentes"] == 0
    total = sum(v["dc_anual_total"] for v in resumo.values())
    assert total == pytest.approx(sum(d.dc_anual_esperado or 0 for d in decisoes))


def test_ordenacao_coloca_estoque_de_seguranca_primeiro():
    fmeca = _caso_simples()
    ordenadas = ordenar_para_relatorio(decidir(fmeca))
    assert ordenadas[0].zona is Zona.ESTOQUE_SEGURANCA
    assert ordenadas[-1].zona is Zona.SOB_DEMANDA


def test_lead_time_longo_sustenta_o_estoque_de_seguranca_sozinho():
    """
    Elevar o corte de Criticidade nao tira do estoque de seguranca um
    componente de lead time longo: a celula (media, longo) tambem e estoque de
    seguranca.
    """
    fmeca = _caso_simples()  # componente 1: Criticidade 60, 45 dias
    frouxo = {d.id: d for d in decidir(fmeca, zonas=ParametrosZona(criticidade_alta=80))}
    assert frouxo[1].faixa_criticidade is FaixaCriticidade.MEDIA
    assert frouxo[1].faixa_lead_time is FaixaLeadTime.LONGO
    assert frouxo[1].zona is Zona.ESTOQUE_SEGURANCA


# -- estudo de caso ---------------------------------------------------------

def test_estudo_de_caso_classifica_todos_os_componentes(fmeca_caso):
    decisoes = decidir(fmeca_caso)
    assert len(decisoes) == 23
    assert all(d.decidido for d in decisoes)


def test_estudo_de_caso_zonas_de_referencia(fmeca_caso):
    """Regressao sobre os limiares padrao e os lead times do estudo de caso."""
    decisoes = {d.id: d for d in decidir(fmeca_caso)}
    assert decisoes[19].zona is Zona.ESTOQUE_SEGURANCA  # turbina
    assert decisoes[17].zona is Zona.ESTOQUE_SEGURANCA  # placa de controle
    assert decisoes[7].zona is Zona.ESTOQUE_SEGURANCA   # sensor de fluxo
    assert decisoes[8].zona is Zona.ESTOQUE_SEGURANCA   # valvula expiratoria
    assert decisoes[1].zona is Zona.SOB_DEMANDA         # circuito, consumivel
    assert decisoes[5].zona is Zona.SOB_DEMANDA         # rodizios
    assert decisoes[6].zona is Zona.SOB_DEMANDA         # celula de O2
    assert decisoes[9].zona is Zona.SOB_DEMANDA         # o-rings

    por_zona = {}
    for d in decisoes.values():
        por_zona[d.zona] = por_zona.get(d.zona, 0) + 1
    assert por_zona[Zona.ESTOQUE_SEGURANCA] == 6
    assert por_zona[Zona.PONTO_PEDIDO] == 5
    assert por_zona[Zona.SOB_DEMANDA] == 12


def test_estudo_de_caso_corte_mais_alto_reduz_o_estoque_de_seguranca(
    fmeca_caso
):
    apertado = decidir(fmeca_caso, zonas=ParametrosZona(criticidade_alta=40))
    frouxo = decidir(fmeca_caso, zonas=ParametrosZona(criticidade_alta=80))
    n_apertado = sum(1 for d in apertado if d.zona is Zona.ESTOQUE_SEGURANCA)
    n_frouxo = sum(1 for d in frouxo if d.zona is Zona.ESTOQUE_SEGURANCA)
    assert n_apertado == 6
    assert n_frouxo == 3
    assert n_frouxo < n_apertado


def test_estudo_de_caso_exposicao_cresce_com_a_zona(fmeca_caso):
    """
    A exposicao anual media deve crescer do sob demanda para o estoque de
    seguranca. E a checagem de que o eixo monetario e o eixo de decisao
    apontam na mesma direcao.
    """
    custo = ParametrosCusto(
        custo_leito_dia=2000,
        frota_equipamentos=10,
    )
    decisoes = decidir(fmeca_caso, custo)
    medias = {}
    for zona in (Zona.SOB_DEMANDA, Zona.PONTO_PEDIDO, Zona.ESTOQUE_SEGURANCA):
        itens = [d.dc_anual_esperado for d in decisoes if d.zona is zona]
        medias[zona] = sum(itens) / len(itens)
    assert medias[Zona.SOB_DEMANDA] < medias[Zona.PONTO_PEDIDO]
    assert medias[Zona.PONTO_PEDIDO] < medias[Zona.ESTOQUE_SEGURANCA]


# -- consistencia entre S, O e o modo dimensionante ------------------------

def _caso_notas_cruzadas():
    """
    Componente cujo maximo de Severidade e o maximo de Ocorrencia estao em
    modos diferentes: A tem S alto com O baixo, B o contrario.
    """
    return ler_fmeca(
        construir_fmeca(
            componentes=[(1, "Cruzada", "Pneumático", "F", "Peça", 160, 20, 20)],
            modos=[
                (1, "1.1", "Cruzada", "Pneumático", "Modo grave e raro", 2, 10, 8, 160, 20),
                (1, "1.2", "Cruzada", "Pneumático", "Modo leve e frequente", 9, 2, 5, 90, 18),
            ],
        )
    )


def test_s_e_o_vem_do_modo_dimensionante_e_fecham_com_a_criticidade():
    fmeca = _caso_notas_cruzadas()
    d = decidir(fmeca)[0]
    assert d.modo_dimensionante.sub_id == "1.1"
    assert (d.severidade, d.ocorrencia) == (10, 2)
    assert d.criticidade == d.severidade * d.ocorrencia == 20


def test_aviso_quando_outro_modo_tem_ocorrencia_maior():
    from fmeca_spares.leitura import RelatorioValidacao

    fmeca = _caso_notas_cruzadas()
    rel = RelatorioValidacao()
    decidir(fmeca, validacao=rel)
    assert any("pode estar subestimada" in a for a in rel.avisos)
    assert any("1.2" in a for a in rel.avisos)


def test_sem_aviso_quando_o_modo_dimensionante_tem_a_maior_ocorrencia(fmeca_caso):
    from fmeca_spares.leitura import RelatorioValidacao

    rel = RelatorioValidacao()
    decidir(fmeca_caso, validacao=rel)
    assert not any("pode estar subestimada" in a for a in rel.avisos)


# -- Deteccao (falha oculta) ------------------------------------------------

def test_limiar_de_deteccao_fora_da_escala_e_rejeitado():
    with pytest.raises(ValueError):
        ParametrosDeteccao(limiar_oculta=0)
    with pytest.raises(ValueError):
        ParametrosDeteccao(limiar_oculta=11)


def test_oculta_segue_a_escala_de_deteccao():
    det = ParametrosDeteccao()
    assert det.oculta(None) is False
    assert det.oculta(6) is False
    assert det.oculta(7) is True
    assert det.oculta(10) is True


def _caso_oculto():
    """
    Componente 1: catastrofico, raro e oculto (S10 O3 D8), Criticidade 30,
    lead time medio -> ponto de pedido. E o caso que a Criticidade subestima.
    Componente 2: mesmo modo, mas lead time longo -> estoque de seguranca.
    Componente 3: falha evidente (D2).
    """
    return ler_fmeca(
        construir_fmeca(
            componentes=[
                (1, "Valvula", "Pneumático", "F", "Peça", 240, 30, 15),
                (2, "Diafragma", "Pneumático", "F", "Peça", 240, 30, 60),
                (3, "Display", "Interface", "F", "Peça", 48, 24, 15),
            ],
            modos=[
                (1, "1.1", "Valvula", "Pneumático", "Travamento", 3, 10, 8, 240, 30),
                (2, "2.1", "Diafragma", "Pneumático", "Ruptura", 3, 10, 8, 240, 30),
                (3, "3.1", "Display", "Interface", "Tela apagada", 4, 6, 2, 48, 24),
            ],
        )
    )


def test_deteccao_nao_altera_a_zona():
    fmeca = _caso_oculto()
    padrao = {d.id: d.zona for d in decidir(fmeca)}
    rigido = {d.id: d.zona for d in decidir(fmeca, deteccao=ParametrosDeteccao(limiar_oculta=2))}
    assert padrao == rigido


def test_justificativa_alerta_falha_oculta():
    decisoes = {d.id: d for d in decidir(_caso_oculto())}
    assert [m.sub_id for m in decisoes[1].modos_ocultos] == ["1.1"]
    assert "falha oculta" in decisoes[1].justificativa
    assert "1.1 (D=8)" in decisoes[1].justificativa
    assert decisoes[3].modos_ocultos == ()
    assert "falha oculta" not in decisoes[3].justificativa


def test_estudo_de_caso_modos_ocultos(fmeca_caso):
    """Regressao sobre a escala de Deteccao do formulario: 9 modos com D >= 7."""
    decisoes = decidir(fmeca_caso)
    assert sum(len(d.modos_ocultos) for d in decisoes) == 9
