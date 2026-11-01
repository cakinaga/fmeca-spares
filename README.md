# fmeca-spares

**Interface online:** <https://fmeca-spares.streamlit.app> — abre no navegador,
sem instalação, com o estudo de caso de demonstração carregado.

Modelo de decisão para estoque de peças de reposição na Engenharia Clínica,
baseado em FMECA e Downtime Cost. Implementa a **Etapa 2** da estrutura
metodológica: a decisão de estoque componente a componente, a partir do
cruzamento entre a Criticidade do FMECA e o lead time de fornecimento.

O repositório tem duas partes independentes:

- `fmeca_spares/` — módulo de cálculo em Python. Depende apenas de `openpyxl`.
  É o que pode ser importado em um script, em um notebook ou em outra
  interface, e é o que recebe o DOI.
- `app.py` — interface em Streamlit sobre esse módulo. Coleta parâmetros,
  exibe e exporta; não contém regra de cálculo.

---

## Execução

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O app abre com o estudo de caso de demonstração carregado. Para usar dados
próprios, desmarque **Usar o estudo de caso de demonstração** na barra lateral
e envie o formulário FMECA, com o lead time preenchido na aba «Matriz de
componentes».

Sem a interface, o módulo basta:

```python
from fmeca_spares import (
    ler_fmeca, decidir,
    ParametrosCusto, ParametrosZona, ParametrosOcorrencia,
    ordenar_para_relatorio,
)

fmeca = ler_fmeca("dados/matriz_componentes_ventilador_uti.xlsx")

decisoes = decidir(
    fmeca,
    ParametrosCusto(
        # o padrão já é a diária de UTI II adulto do SUS (R$ 600,00)
        frota_equipamentos=10,
    ),
    ParametrosZona(),
    escala_ocorrencia=ParametrosOcorrencia(),
)

for d in ordenar_para_relatorio(decisoes):
    print(d.id, d.nome, d.zona.rotulo, d.dc_anual_esperado)
```

---

## Como o modelo decide

A decisão sai de dois eixos.

**Eixo de exposição — Criticidade (S × O).** O maior produto entre Severidade
e Ocorrência entre os modos de falha do componente. A Detecção fica fora deste
eixo de propósito: ela governa a prioridade de ação sobre o modo de falha, e
por isso entra no RPN, mas não altera a decisão de ter ou não a peça na
prateleira. Um modo de falha facilmente detectável continua exigindo a peça
para voltar à operação.

**Eixo de reposição — lead time, em dias.** O tempo que o equipamento fica
parado *a mais* por não haver a peça em estoque. Vem da coluna `Lead time
(dias)` da aba «Matriz de componentes».

O cruzamento das duas faixas produz a matriz de zonas:

|                       | Lead time curto | Lead time médio | Lead time longo |
| --------------------- | --------------- | --------------- | --------------- |
| **Criticidade alta**  | Ponto de pedido | Estoque de segurança | Estoque de segurança |
| **Criticidade média** | Compra sob demanda | Ponto de pedido | Estoque de segurança |
| **Criticidade baixa** | Compra sob demanda | Compra sob demanda | Ponto de pedido |

A matriz é monótona nos dois eixos: subir a Criticidade ou o lead time nunca
reduz o compromisso de estoque. Duas leituras da diagonal merecem registro:
criticidade alta com fornecimento em menos de uma semana não exige peça
parada, apenas ressuprimento programado; e lead time longo sustenta o estoque
de segurança sozinho a partir da faixa média de Criticidade, porque mais de um
mês de equipamento indisponível não se recupera com pedido de compra.

**Piso de demanda programada.** Componentes com `Natureza` = Consumível na
«Matriz de componentes» nunca caem em compra sob demanda. A demanda deles é
determinada pelo calendário de troca, não pela ocorrência de falha, e por isso
eles pontuam Ocorrência baixa em qualquer base de notificação de falha. Sem
esse piso, o modelo os subdimensionaria. O piso pode ser desligado em
`ParametrosZona(piso_ponto_pedido_demanda_programada=False)`. Peças trocadas
por intervalo da manutenção preventiva (célula de O₂, o-rings) só recebem o
piso se forem marcadas como Consumível no formulário.

---

## Downtime Cost

O Downtime Cost traduz o eixo de reposição em dinheiro. Ele **não reclassifica**
o componente: serve para ordenar dentro de cada zona.

**Custo de leito bloqueado.** O custo de indisponibilidade tem um parâmetro
só: o custo de um dia de leito bloqueado por falta do equipamento.

**Custo evitável por evento.** Manter a peça em estoque evita os dias de espera
pelo fornecimento. O custo evitável é esse tempo cobrado ao custo do leito
bloqueado:

```
DC_evitável = lead_time_dias × custo_leito_dia
```

Toda a carga empírica está num único número: `custo_leito_dia`.

### Procedência do custo de leito bloqueado

O padrão é a **diária de UTI II adulto da tabela do SUS**, procedimento SIGTAP
`08.02.01.008-3`, fixada em **R$ 600,00** (R$ 510,00 de Serviço Hospitalar mais
R$ 90,00 de Serviço Profissional) pela **Portaria GM/MS nº 160, de 25 de
fevereiro de 2022**. Para UTI III adulto, procedimento `08.02.01.009-1`, a
diária é de R$ 700,00 (`DIARIA_UTI_III_SUS`).

A leitura é de custo de oportunidade: é o valor que a unidade deixa de faturar
por cada dia em que o leito não pode ser ocupado por falta do equipamento.

Duas ressalvas de uso, que valem estar no texto do trabalho:

1. **Os valores são de 2022.** Confira a tabela SIGTAP vigente antes de citar.
2. **A diária do SUS fica abaixo do custo operacional efetivo de um leito de
   UTI.** Guimarães, Dallora e Favaro (*Revista Qualidade HC*, n. 57) apuraram
   R$ 1.114,10 por paciente-dia nas UTIs COVID do HC-FMRP no primeiro semestre
   de 2021 contando **apenas materiais e medicamentos**, sem recursos humanos,
   exames nem rateio. Adotar a diária do SUS é, portanto, a escolha
   conservadora: subestima o custo e, com ele, o benefício de manter a peça em
   estoque.

Hospitais privados e instituições com custo apurado pela controladoria devem
informar o próprio valor, caso em que a aba «Parâmetros» da planilha exportada
registra que o número foi informado pelo usuário e pede a fonte no relatório.

**Exposição anual.** O custo por evento depende só do lead time e, por isso,
ordena mal: um componente de lead time longo e falha rara aparece acima de um
componente crítico de falha frequente. A grandeza comparável ao custo de
manter a peça em estoque é a exposição anual:

```
DC_anual = DC_evitável × λ(O) × frota_equipamentos
```

### Escala de Ocorrência → taxa de falha

λ não é estimado a partir dos dados: ele é lido da própria escala de Ocorrência
que o analista usou para pontuar, declarada na aba «Tabela» do formulário
FMECA.

| Nota de Ocorrência | λ declarado na escala (falha/ano por unidade) |
| --- | --- |
| 1–2 | abaixo de 0,5 |
| 3–4 | 0,5 a 1,0 |
| 5–6 | 1,0 a 1,5 |
| 7–8 | 1,5 a 3,0 |
| 9–10 | acima de 3,0 |

A faixa aberta embaixo recebe piso 0, limite natural de uma taxa. A faixa
aberta em cima (O 9–10) não tem teto na escala e é tomada no próprio piso,
λ = 3,0: a leitura conservadora, que subestima a exposição desses componentes
em vez de supor um teto que a escala não declara. Os valores estão em
`ParametrosOcorrencia.faixas`. O parâmetro `posicao_na_faixa` escolhe onde,
dentro das faixas fechadas, o valor é tomado — 0 no piso, 0,5 no meio, 1 no
teto. Rodar o modelo nos dois extremos dá o intervalo de custo compatível com
a *mesma* pontuação de FMECA, o que é mais honesto do que apresentar um número
único.

---

## Plano de ação (Detecção e RPN)

A Detecção fica fora da decisão de estoque, mas não fica fora do app. O plano
de ação responde a outra pergunta — *além de estocar, o que fazer?* — e não
reclassifica nenhum componente.

Cada modo de falha recebe uma ação pela nota D, conforme a escala de Detecção
da aba «Tabela» do formulário:

| D | Leitura da escala | Ação recomendada |
| --- | --- | --- |
| 1–4 | alarme automático ou checagem de rotina | Detecção adequada |
| 5–6 | depende de inspeção periódica ou preventiva | Manter o intervalo da preventiva |
| 7–10 | falha oculta até o uso crítico, ou só percebida pela consequência | Incluir teste funcional na preventiva |

**Por que a falha oculta pede teste, não só estoque.** A peça na prateleira
encurta o reparo, mas não antecipa a descoberta da falha: com D alto, ela só
aparece no uso crítico, com o paciente conectado. A justificativa de cada
componente com modo de falha oculta traz esse alerta.

**Alerta.** Um modo com Severidade a partir de 9 e Detecção oculta, num
componente fora do estoque de segurança, é sinalizado. É o caso que a
Criticidade subestima: falha catastrófica, rara e oculta, que a Ocorrência
baixa deixa na faixa média de S × O. No estudo de caso, são os modos 20.1 e
22.1 (S = 10, O = 3, D = 7 e 8, Criticidade 30, ponto de pedido).

O app mostra o plano numa aba própria, com os modos ordenados por alerta e por
RPN e a coluna «Detecção atual» do formulário, e num gráfico Criticidade ×
Detecção com a faixa das falhas ocultas destacada. A planilha exportada traz a
aba «Plano de ação». Os três limiares (D oculta = 7, D preventiva = 5,
S de alerta = 9) são ajustáveis na interface e em `ParametrosDeteccao`.

---

## Calibração dos limiares

Os valores padrão e sua justificativa. Todos são ajustáveis na interface e em
`ParametrosZona`.

| Limiar | Padrão | Por quê |
| --- | --- | --- |
| Piso da Criticidade alta | 40 | Menor produto S × O que combina perda de função crítica com ocorrência ao menos ocasional: S = 8 (equipamento retirado de uso, risco potencial ao paciente) com O = 5 (falha ocasional), ou S = 10 com O = 4. |
| Piso da Criticidade média | 20 | Faixa em que a exposição vem de um eixo isoladamente: severidade crítica com ocorrência rara (S = 10, O = 2) ou severidade moderada com ocorrência frequente (S = 4, O = 5). |
| Teto do lead time curto | 7 dias | Fornecimento que devolve o equipamento à operação na mesma semana, compatível com peça nacional ou pronta entrega. |
| Piso do lead time longo | 30 dias | Acima de um mês de equipamento parado por falta de peça; faixa típica de importação sem representação consolidada no país. |

---

## Entradas

### Formulário FMECA (`.xlsx`)

Duas abas obrigatórias.

**«Matriz de componentes»** — uma linha por componente, com as colunas `ID`,
`Componente / peça`, `Subsistema`, `Função`, `Natureza` (Consumível ou Peça),
`RPN`, `Criticidade` e `Lead time (dias)`.

**«Modos de falha»** — uma linha por modo, com `ID` (do componente),
`Sub ID`, `Componente`, `Subsistema`, `Modo de falha`, `Causa`, os três campos
de efeito, `Detecção atual`, `Família de problema (FDA/IMDRF)` e as notas
`O`, `S`, `D` com `RPN` e `Criticidade`.

As colunas são localizadas pelo texto do cabeçalho, não pela posição: inserir
ou remover uma coluna não quebra a leitura. A Criticidade usada no cálculo é
sempre recalculada de S × O a partir das notas; o valor declarado na aba de
matriz só é usado como recurso quando o componente não tem modo pontuado, e
qualquer divergência entre os dois aparece na aba «Validação» do resultado.

### Lead time

O lead time é o único dado de fornecimento que o modelo usa. Fica na coluna
`Lead time (dias)` da «Matriz de componentes»: o prazo entre a emissão do
pedido e a peça disponível para instalação, em dias de calendário.

- Sem a coluna, a leitura para com erro.
- Com a célula em branco, o componente fica sem zona atribuída e a
  conferência registra um aviso.
- Valor negativo é erro.

O cabeçalho também é reconhecido como `Leadtime` ou `Prazo`. Os lead times do
estudo de caso são ilustrativos: substitua-os pelos prazos dos contratos do
hospital antes de usar o resultado em decisão de compra.

---

## Protocolo mínimo de dados

Para recalibrar o modelo com dados próprios, um hospital precisa de três
conjuntos. Nenhum deles exige instrumentação nova: todos existem, em alguma
forma, no sistema de gestão da manutenção e no setor de compras.

1. **Ordens de serviço corretivas por componente**, com data de abertura e de
   encerramento, no maior período disponível. Dividir o número de eventos de
   cada componente pelo número de equipamentos-ano da frota dá λ direto, e o
   modelo passa a dispensar a tradução a partir da nota de Ocorrência.
2. **Lead time realizado por item**, do histórico de compras: a diferença
   entre a data do pedido e a data de disponibilidade da peça, não o prazo
   prometido em contrato.
3. **Custo de leito bloqueado**, apurado com a controladoria, que precisa
   acordar o que se conta como perda; na falta dele, a diária do SUS.

Enquanto esses dados não existirem, o resultado demonstra o método e não
constitui recomendação de compra. O app e as planilhas de demonstração dizem
isso de forma explícita.

---

## Estrutura

```
fmeca_spares/
  parametros.py    faixas, limiares, custo de leito bloqueado e Detecção, com validação
  leitura.py       leitura e conferência do formulário FMECA
  modelo.py        Downtime Cost, matriz de zonas, decisão por componente e plano de ação
  exportacao.py    planilha de resultado, resumo, plano de ação, parâmetros e validação
app.py             interface Streamlit
dados/             formulário FMECA do estudo de caso
tests/             suíte pytest
```

## Testes

```bash
pip install pytest
pytest
```

A suíte cobre os utilitários de leitura, a aritmética do FMECA, os limites das
faixas, o cálculo do Downtime Cost, as nove células da
matriz de zonas, a monotonicidade da matriz, o piso de demanda programada e a
exportação. Inclui testes de regressão sobre o estudo de caso: se os limiares
padrão ou a planilha de demonstração mudarem, eles falham, o que obriga a
mudança a ser deliberada.

## Limitações

- **O modelo decide o quê estocar, não quanto.** As zonas dizem se a peça deve
  estar na prateleira, ser ressuprida por ponto de pedido ou comprada sob
  demanda. O dimensionamento da quantidade e do ponto de reposição exige a
  distribuição da demanda, que o modelo não estima.
- **A Ocorrência do estudo de caso vem de notificações, não de histórico de
  manutenção.** Sem o tamanho da frota notificante, não há denominador para
  uma taxa de falha por unidade-ano; a nota é um ordenamento relativo entre
  componentes, e a tradução para λ é a da escala declarada no formulário.
- **A Ocorrência é atribuída por componente, não por modo de falha.** Todos os
  modos de um mesmo componente compartilham a nota, de modo que o RPN varia
  entre eles apenas por Severidade e Detecção.
- **O preço da peça não é considerado.** A decisão não pesa a exposição anual
  contra o capital imobilizado em estoque.
- **Não houve validação em campo.** Os limiares padrão são argumentados a
  partir da própria escala de pontuação, não aferidos contra decisões de
  estoque reais.

## Citação

Os metadados estão em `CITATION.cff`. Preencher o DOI e o ORCID após o
depósito no Zenodo.

## Referências dos parâmetros de custo

BRASIL. Ministério da Saúde. **Portaria GM/MS nº 160, de 25 de fevereiro de
2022** (republicada). Altera os valores das diárias de Unidade de Terapia
Intensiva na Tabela de Procedimentos, Medicamentos, Órteses, Próteses e
Materiais Especiais do SUS. Procedimentos 08.02.01.008-3 (UTI II adulto,
R$ 600,00) e 08.02.01.009-1 (UTI III adulto, R$ 700,00). Disponível em:
https://bvsms.saude.gov.br/bvs/saudelegis/gm/2022/prt0160_25_02_2022_rep.html

GUIMARÃES, G. R.; DALLORA, M. E. L. do V.; FAVARO, M. A. **Custo médio da
diária em UTI COVID-19**. Revista Qualidade HC, n. 57, p. 57-61. Apura
R$ 1.114,10 por paciente-dia nas UTIs COVID do HC-FMRP no primeiro semestre de
2021, considerando apenas materiais e medicamentos. Disponível em:
https://hcrp.usp.br/revistaqualidade/uploads/Artigos/432/432.pdf

## Licença

MIT, em `LICENSE`.
