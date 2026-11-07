"""
fmeca_spares — modelo de decisao para estoque de spare parts na Engenharia Clinica.

Implementa a Etapa 2 da estrutura metodologica: a decisao de estoque por
componente, obtida do cruzamento entre a Criticidade do FMECA (S x O) e o lead
time de fornecimento, com o Downtime Cost evitavel como grandeza de apoio. O
lead time vem da coluna "Lead time (dias)" da aba Matriz de componentes.

O modulo nao depende de Streamlit nem de pandas: a interface grafica e apenas
uma das formas de consumi-lo. Dependencia externa unica: openpyxl, para ler o
formulario FMECA em .xlsx.

Uso minimo:

    from fmeca_spares import ler_fmeca, decidir
    from fmeca_spares import ParametrosCusto, ParametrosZona

    fmeca = ler_fmeca("matriz_componentes_ventilador_uti.xlsx")
    decisoes = decidir(fmeca, ParametrosCusto(...), ParametrosZona())
"""

from .parametros import (
    DIARIA_UTI_II_SUS,
    DIARIA_UTI_III_SUS,
    FaixaCriticidade,
    FaixaLeadTime,
    ParametrosCusto,
    ParametrosDeteccao,
    ParametrosOcorrencia,
    ParametrosZona,
    Zona,
)
from .leitura import (
    Componente,
    ModoDeFalha,
    RelatorioValidacao,
    FMECA,
    ler_fmeca,
)
from .modelo import (
    DecisaoComponente,
    decidir,
    escala_do_formulario,
    downtime_cost_evitavel,
    downtime_cost_anual_esperado,
    classificar_zona,
    resumo_por_zona,
    ordenar_para_relatorio,
    MATRIZ_ZONAS,
)

__all__ = [
    "DIARIA_UTI_II_SUS",
    "DIARIA_UTI_III_SUS",
    "FaixaCriticidade",
    "FaixaLeadTime",
    "ParametrosCusto",
    "ParametrosDeteccao",
    "ParametrosOcorrencia",
    "ParametrosZona",
    "Zona",
    "Componente",
    "ModoDeFalha",
    "RelatorioValidacao",
    "FMECA",
    "ler_fmeca",
    "DecisaoComponente",
    "decidir",
    "escala_do_formulario",
    "downtime_cost_evitavel",
    "downtime_cost_anual_esperado",
    "classificar_zona",
    "resumo_por_zona",
    "ordenar_para_relatorio",
    "MATRIZ_ZONAS",
]

__version__ = "0.3.0"
