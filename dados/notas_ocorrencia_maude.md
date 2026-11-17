# Notas de Ocorrência a partir das notificações do MAUDE

Registro de como foram atribuídas as notas de Ocorrência (O) dos componentes
no formulário FMECA do estudo de caso
(`matriz_componentes_ventilador_uti.xlsx`).

## Fonte

Notificações de eventos adversos da base MAUDE (*Manufacturer and User
Facility Device Experience*, FDA), obtidas com os filtros de busca:

| Campo do MAUDE | Valor |
|---|---|
| Brand Name | Hamilton-C6 |
| Manufacturer | Hamilton |
| Date Report Received by FDA | de 01/01/2025 a 31/12/2025 |

A busca retornou **146 notificações**, todas analisadas. Cada notificação foi
atribuída ao componente envolvido na falha. Das 146, 102 correspondem a componentes da matriz; as
demais 44 não correspondem a nenhum deles.

## Critério

A nota O de cada componente segue a proporção das notificações a ele
atribuídas em relação ao total de 146:

| Nota O | Proporção das notificações |
|:---:|---|
| 1–2 | menos de 1% |
| 3–4 | de 1% a 3% |
| 5–6 | de 3% a 10% |
| 7–8 | de 10% a 20% |
| 9–10 | 20% ou mais |

Dentro de cada faixa, a escolha entre a nota menor e a maior foi feita na
análise, componente a componente. Componentes sem nenhuma notificação
receberam O = 1. Nenhum componente ficou com as notas 4, 8 ou 10.

## Distribuição e notas atribuídas

| ID | Componente | Notificações | Proporção (de 146) | Faixa | Nota O |
|:---:|---|:---:|:---:|:---:|:---:|
| 19 | Turbina / blower | 34 | 23,3% | 9–10 | 9 |
| 4 | Placa de controle (IP) | 18 | 12,3% | 7–8 | 7 |
| 17 | Placa principal / placa de controle VU (ventilation unit) | 11 | 7,5% | 5–6 | 6 |
| 8 | Válvula expiratória | 11 | 7,5% | 5–6 | 6 |
| 18 | Válvula misturadora de O2 | 6 | 4,1% | 5–6 | 5 |
| 7 | Sensor de fluxo | 5 | 3,4% | 5–6 | 5 |
| 13 | Bateria interna recarregável | 3 | 2,1% | 3–4 | 3 |
| 14 | Sensor de pressão | 3 | 2,1% | 3–4 | 3 |
| 9 | Conjunto de entrada de ar / Válvula ambiente | 3 | 2,1% | 3–4 | 3 |
| 15 | Cabo VU–IP | 2 | 1,4% | 3–4 | 3 |
| 16 | Fonte de alimentação interna | 2 | 1,4% | 3–4 | 3 |
| 20 | Válvula inspiratória | 2 | 1,4% | 3–4 | 3 |
| 12 | Ventoinha de resfriamento | 1 | 0,7% | 1–2 | 2 |
| 6 | Sensor / célula de oxigênio (galvânica) | 1 | 0,7% | 1–2 | 2 |
| 2 | Filtro bacteriano / viral | 0 | 0,0% | 1–2 | 1 |
| 3 | Filtro HME (trocador de calor e umidade) | 0 | 0,0% | 1–2 | 1 |
| 10 | Filtro de entrada ar (HEPA) | 0 | 0,0% | 1–2 | 1 |
| 5 | Rodízios, travas e estrutura do pedestal | 0 | 0,0% | 1–2 | 1 |
| 1 | Circuito respiratório descartável | 0 | 0,0% | 1–2 | 1 |
| 11 | Display / tela | 0 | 0,0% | 1–2 | 1 |
| | **Total atribuído à matriz** | **102** | **69,9%** | | |

A nota de cada componente é a mesma em todos os seus modos de falha na aba
«Modos de falha».

## Relação com a taxa de falha usada no aplicativo

A proporção de notificações mede a frequência **relativa** de cada componente
entre as falhas notificadas; ela define a nota O. O aplicativo, para estimar o
Downtime Cost, converte cada nota O em uma taxa de falha anual por equipamento
(λ) pela escala da aba «Tabela» do formulário:

| Nota O | λ (falha/ano por equipamento) |
|:---:|---|
| 1–2 | λ < 0,5 |
| 3–4 | 0,5 ≤ λ < 1,0 |
| 5–6 | 1,0 ≤ λ < 2,0 |
| 7–8 | 2,0 ≤ λ < 4,0 |
| 9–10 | λ ≥ 4,0 |

São duas etapas distintas: a proporção no MAUDE ordena e pontua os
componentes; a escala de λ traduz essa pontuação em frequência anual. O MAUDE
não informa o número de equipamentos em uso, por isso não permite calcular λ
diretamente.
