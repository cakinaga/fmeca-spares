"""
Leitura e validacao do formulario FMECA.

O lead time de cada componente vem da propria aba "Matriz de componentes",
na coluna "Lead time (dias)": o formulario e a unica entrada do modelo.

As colunas sao localizadas pelo texto do cabecalho, nao pela posicao, para que
insercoes ou remocoes de coluna nao quebrem a leitura.

A escala de Ocorrencia, que traduz cada nota em taxa de falha anual, e lida
da aba "Tabela". Sem ela, ou se o texto nao puder ser lido, o modelo usa a
escala padrao de ParametrosOcorrencia e a conferencia registra um aviso.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Sequence

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fmeca_spares depende de openpyxl para ler o formulário FMECA. "
        "Instale com: pip install openpyxl"
    ) from exc


ABA_COMPONENTES = "Matriz de componentes"
ABA_MODOS = "Modos de falha"
ABA_TABELA = "Tabela"

# (nota minima, nota maxima, lambda piso, lambda teto), em falha/ano por unidade
FaixaOcorrencia = tuple[int, int, float, float]

# Valores canonicos da coluna Natureza, ja na forma em que sao exibidos.
NATUREZA_CONSUMIVEL = "Consumível"
NATUREZA_PECA = "Peça"


# --------------------------------------------------------------------------
# normalizacao de texto
# --------------------------------------------------------------------------

def normalizar(texto: Any) -> str:
    """Minusculas, sem acento, espacos colapsados. Usado para casar cabecalhos."""
    if texto is None:
        return ""
    s = str(texto)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def _numero(valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s:
        return None
    # aceita "1.234,56" e "1234.56"
    s = s.replace("R$", "").replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _inteiro(valor: Any) -> int | None:
    n = _numero(valor)
    if n is None:
        return None
    return int(round(n))


def classificar_natureza(valor: Any) -> str | None:
    """Reduz o texto da coluna Natureza a 'Consumivel' ou 'Peca'."""
    n = normalizar(valor)
    if not n:
        return None
    if n.startswith("consum"):
        return NATUREZA_CONSUMIVEL
    if n.startswith("peca") or n.startswith("peça"):
        return NATUREZA_PECA
    return None


# --------------------------------------------------------------------------
# estruturas de dados
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ModoDeFalha:
    id_componente: int
    sub_id: str
    componente: str | None
    subsistema: str | None
    modo: str | None
    causa: str | None
    efeito_local: str | None
    efeito_equipamento: str | None
    efeito_paciente: str | None
    deteccao: str | None
    ocorrencia: int | None
    severidade: int | None
    deteccao_nota: int | None
    rpn: int | None
    criticidade: int | None
    linha: int = 0

    @property
    def rpn_calculado(self) -> int | None:
        if None in (self.ocorrencia, self.severidade, self.deteccao_nota):
            return None
        return self.ocorrencia * self.severidade * self.deteccao_nota

    @property
    def criticidade_calculada(self) -> int | None:
        if None in (self.ocorrencia, self.severidade):
            return None
        return self.ocorrencia * self.severidade


@dataclass(frozen=True)
class Componente:
    id: int
    nome: str
    subsistema: str | None
    funcao: str | None
    natureza: str | None
    rpn: int | None
    criticidade: int | None
    lead_time_dias: float | None = None
    linha: int = 0

    @property
    def consumivel(self) -> bool:
        return self.natureza == NATUREZA_CONSUMIVEL


@dataclass
class RelatorioValidacao:
    """
    Resultado da conferencia do arquivo lido.

    `erros` impedem o calculo; `avisos` nao impedem, mas sinalizam
    inconsistencias que o usuario precisa ver.
    """

    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros

    def erro(self, msg: str) -> None:
        self.erros.append(msg)

    def aviso(self, msg: str) -> None:
        self.avisos.append(msg)

    def estender(self, outro: "RelatorioValidacao") -> None:
        self.erros.extend(outro.erros)
        self.avisos.extend(outro.avisos)


@dataclass
class FMECA:
    """Formulario FMECA lido: cabecalho, componentes, modos e validacao."""

    equipamento: str | None
    modelo: str | None
    fabricante: str | None
    setor: str | None
    data_analise: Any
    componentes: list[Componente]
    modos: list[ModoDeFalha]
    validacao: RelatorioValidacao
    # escala de Ocorrencia lida da aba Tabela; None quando nao foi possivel ler
    escala_ocorrencia: tuple[FaixaOcorrencia, ...] | None = None

    def modos_de(self, id_componente: int) -> list[ModoDeFalha]:
        return [m for m in self.modos if m.id_componente == id_componente]

    def componente(self, id_componente: int) -> Componente | None:
        for c in self.componentes:
            if c.id == id_componente:
                return c
        return None

    @property
    def identificacao(self) -> str:
        partes = [p for p in (self.equipamento, self.modelo, self.fabricante) if p]
        return " — ".join(partes) if partes else "equipamento não identificado"


# --------------------------------------------------------------------------
# localizacao de cabecalhos
# --------------------------------------------------------------------------

def _linhas(ws) -> list[list[Any]]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _achar_cabecalho(linhas: Sequence[Sequence[Any]], limite: int = 20) -> int | None:
    """Indice (0-based) da linha de cabecalho: a primeira cujo texto seja 'id'."""
    for i, linha in enumerate(linhas[:limite]):
        for cel in linha[:3]:
            if normalizar(cel) == "id":
                return i
    return None


def _mapear_colunas(
    cabecalho: Sequence[Any],
    alvos: dict[str, tuple[str, ...]],
    exatos: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """
    Casa cada chave de `alvos` com o indice da coluna cujo cabecalho normalizado
    comeca por um dos prefixos informados. A primeira coluna livre que casar
    vence, o que evita que "Criticidade" roube a coluna de "RPN".

    As chaves listadas em `exatos` exigem igualdade, nao prefixo. Isso protege
    os cabecalhos de uma letra so — O, S e D: por prefixo, "Observacoes"
    casaria com "o" e roubaria a coluna da Ocorrencia, que entao seria lida
    como vazia.
    """
    normalizados = [normalizar(c) for c in cabecalho]
    usados: set[int] = set()
    mapa: dict[str, int] = {}
    for chave, prefixos in alvos.items():
        exige_igualdade = chave in exatos
        for idx, texto in enumerate(normalizados):
            if idx in usados or not texto:
                continue
            if exige_igualdade:
                casou = texto in prefixos
            else:
                casou = any(texto.startswith(p) for p in prefixos)
            if casou:
                mapa[chave] = idx
                usados.add(idx)
                break
    return mapa


def _valor(linha: Sequence[Any], mapa: dict[str, int], chave: str) -> Any:
    idx = mapa.get(chave)
    if idx is None or idx >= len(linha):
        return None
    return linha[idx]


# --------------------------------------------------------------------------
# leitura do FMECA
# --------------------------------------------------------------------------

_COLS_COMPONENTES = {
    "id": ("id",),
    "nome": ("componente", "peca", "peça"),
    "subsistema": ("subsistema",),
    "funcao": ("funcao",),
    "natureza": ("natureza",),
    "rpn": ("rpn",),
    "criticidade": ("criticidade",),
    "lead_time_dias": ("lead time", "leadtime", "prazo"),
}

_COLS_MODOS = {
    "id": ("id",),
    "sub_id": ("sub id", "subid", "sub-id"),
    "componente": ("componente",),
    "subsistema": ("subsistema",),
    "modo": ("modo de falha", "modo"),
    "causa": ("causa",),
    "efeito_local": ("efeito local",),
    "efeito_equipamento": ("efeito no equipamento",),
    "efeito_paciente": ("efeito no paciente",),
    "deteccao": ("deteccao atual",),
    "ocorrencia": ("o", "ocorrencia"),
    "severidade": ("s", "severidade"),
    "deteccao_nota": ("d", "deteccao"),
    "rpn": ("rpn",),
    "criticidade": ("criticidade",),
}

# cabecalhos de uma letra exigem igualdade (ver _mapear_colunas)
_MODOS_EXATOS = frozenset({"ocorrencia", "severidade", "deteccao_nota"})


def _ler_cabecalho_identificacao(linhas: Sequence[Sequence[Any]]) -> dict[str, Any]:
    """
    Le os rotulos 'Equipamento:', 'Modelo:', 'Fabricante:', 'Setor...',
    'Data de analise:' nas primeiras linhas, qualquer que seja a coluna em que
    o rotulo e o valor estejam.
    """
    alvos = {
        "equipamento": "equipamento:",
        "modelo": "modelo:",
        "fabricante": "fabricante:",
        "setor": "setor",
        "data_analise": "data de analise",
    }
    achados: dict[str, Any] = {k: None for k in alvos}
    for linha in linhas[:8]:
        for idx, cel in enumerate(linha):
            n = normalizar(cel)
            if not n:
                continue
            for chave, prefixo in alvos.items():
                if achados[chave] is not None or not n.startswith(prefixo):
                    continue
                for seguinte in linha[idx + 1 :]:
                    if seguinte is not None and str(seguinte).strip():
                        achados[chave] = (
                            seguinte
                            if chave == "data_analise"
                            else _texto(seguinte)
                        )
                        break
    return achados


def ler_fmeca(origem: str | Path | BinaryIO) -> FMECA:
    """
    Le o formulario FMECA em .xlsx e devolve componentes, modos e validacao.

    `origem` aceita caminho ou objeto binario (o upload do Streamlit, por
    exemplo).
    """
    wb = openpyxl.load_workbook(origem, data_only=True, read_only=False)
    rel = RelatorioValidacao()

    nomes = {normalizar(n): n for n in wb.sheetnames}
    nome_comp = nomes.get(normalizar(ABA_COMPONENTES))
    nome_modos = nomes.get(normalizar(ABA_MODOS))
    if nome_comp is None:
        rel.erro(f'aba "{ABA_COMPONENTES}" não encontrada no arquivo')
    if nome_modos is None:
        rel.erro(f'aba "{ABA_MODOS}" não encontrada no arquivo')
    if not rel.ok:
        return FMECA(None, None, None, None, None, [], [], rel)

    linhas_comp = _linhas(wb[nome_comp])
    linhas_modos = _linhas(wb[nome_modos])

    ident = _ler_cabecalho_identificacao(linhas_modos)
    if not any(ident.values()):
        ident = _ler_cabecalho_identificacao(linhas_comp)

    componentes = _ler_componentes(linhas_comp, rel)
    modos = _ler_modos(linhas_modos, rel)
    _validar_cruzado(componentes, modos, rel)

    nome_tabela = nomes.get(normalizar(ABA_TABELA))
    if nome_tabela is None:
        escala = None
        rel.aviso(
            f'aba "{ABA_TABELA}" não encontrada; a taxa de falha usa a escala '
            "de Ocorrência padrão do modelo"
        )
    else:
        escala = ler_escala_ocorrencia(_linhas(wb[nome_tabela]), rel)

    return FMECA(
        equipamento=ident["equipamento"],
        modelo=ident["modelo"],
        fabricante=ident["fabricante"],
        setor=ident["setor"],
        data_analise=ident["data_analise"],
        componentes=componentes,
        modos=modos,
        validacao=rel,
        escala_ocorrencia=escala,
    )


# --------------------------------------------------------------------------
# escala de Ocorrencia (aba Tabela)
# --------------------------------------------------------------------------

_NOTAS = re.compile(r"^(\d{1,2})(?:\s*(?:[-–—]|a|ate)\s*(\d{1,2}))?$")
_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
# palavras inteiras, para que "ate" nao case dentro de "material"
_ACIMA = re.compile(r"\b(?:acima|maior|superior|mais de)\b|>")
_ABAIXO = re.compile(r"\b(?:abaixo|menor|inferior|menos de|ate)\b|<")


def _faixa_de_notas(valor: Any) -> tuple[int, int] | None:
    """'1–2', '1-2', '1 a 2' ou 9 -> (minimo, maximo)."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        n = int(valor)
        return (n, n) if n == valor else None
    casou = _NOTAS.match(normalizar(valor))
    if casou is None:
        return None
    minimo = int(casou.group(1))
    return minimo, int(casou.group(2) or minimo)


def _taxa_do_texto(texto: str) -> tuple[float, float] | None:
    """
    Le o intervalo de lambda na descricao de uma nota: "entre 0,5 e 1,0" da
    (0,5; 1,0), "abaixo de 0,5" da (0; 0,5) e "acima de 3,0" da (3,0; 3,0).
    """
    n = normalizar(texto)
    numeros = [float(x.replace(",", ".")) for x in _NUMERO.findall(n)]
    if len(numeros) >= 2:
        return numeros[0], numeros[1]
    if len(numeros) == 1:
        if _ACIMA.search(n):
            return numeros[0], numeros[0]
        if _ABAIXO.search(n):
            return 0.0, numeros[0]
    return None


def ler_escala_ocorrencia(
    linhas: Sequence[Sequence[Any]], rel: RelatorioValidacao
) -> tuple[FaixaOcorrencia, ...] | None:
    """
    Le a secao de Ocorrencia da aba Tabela: a linha cujo primeiro texto comeca
    por "Ocorrencia", seguida de uma linha por faixa de notas (nota na
    primeira celula preenchida, descricao com a taxa de falha na segunda). A
    secao termina na primeira linha que nao seja de faixa de notas, depois de
    ao menos uma lida.

    Devolve None, com aviso, quando a secao nao existe, quando alguma taxa nao
    pode ser lida ou quando as faixas nao cobrem as notas de 1 a 10 sem
    lacunas e em ordem crescente de taxa.
    """
    padrao = "a taxa de falha usa a escala de Ocorrência padrão do modelo"
    faixas: list[FaixaOcorrencia] = []
    na_secao = False
    for linha in linhas:
        celulas = [c for c in linha if c is not None and str(c).strip()]
        if not celulas:
            continue
        if not na_secao:
            na_secao = normalizar(celulas[0]).startswith("ocorrencia")
            continue
        notas = _faixa_de_notas(celulas[0])
        if notas is None:
            if faixas:
                break
            continue  # linha de cabecalho da secao ("Nota", "Descricao")
        taxa = _taxa_do_texto(str(celulas[1])) if len(celulas) > 1 else None
        if taxa is None:
            rel.aviso(
                f'aba {ABA_TABELA}: não consegui ler a taxa de falha da nota '
                f"{notas[0]}–{notas[1]} da escala de Ocorrência; {padrao}"
            )
            return None
        faixas.append((notas[0], notas[1], taxa[0], taxa[1]))

    if not na_secao or not faixas:
        rel.aviso(f"aba {ABA_TABELA}: seção de Ocorrência não encontrada; {padrao}")
        return None

    faixas.sort()
    esperado = 1
    for minimo, maximo, piso, teto in faixas:
        if minimo != esperado or maximo < minimo or teto < piso:
            rel.aviso(
                f"aba {ABA_TABELA}: a escala de Ocorrência precisa cobrir as "
                f"notas de 1 a 10, sem lacunas nem sobreposições, com piso de λ "
                f"menor ou igual ao teto; {padrao}"
            )
            return None
        esperado = maximo + 1
    if esperado != 11 or any(
        faixas[i + 1][2] < faixas[i][2] for i in range(len(faixas) - 1)
    ):
        rel.aviso(
            f"aba {ABA_TABELA}: a escala de Ocorrência precisa cobrir as notas "
            f"de 1 a 10, com taxa de falha crescente com a nota; {padrao}"
        )
        return None
    return tuple(faixas)


def _ler_componentes(
    linhas: Sequence[Sequence[Any]], rel: RelatorioValidacao
) -> list[Componente]:
    i = _achar_cabecalho(linhas)
    if i is None:
        rel.erro(f'não localizei a linha de cabeçalho da aba "{ABA_COMPONENTES}"')
        return []
    mapa = _mapear_colunas(linhas[i], _COLS_COMPONENTES)
    for obrigatoria, rotulo in (
        ("id", "ID"),
        ("nome", "Componente / peça"),
        ("lead_time_dias", "Lead time (dias)"),
    ):
        if obrigatoria not in mapa:
            rel.erro(f'coluna "{rotulo}" não encontrada na aba "{ABA_COMPONENTES}"')
            return []

    componentes: list[Componente] = []
    vistos: set[int] = set()
    for offset, linha in enumerate(linhas[i + 1 :], start=i + 2):
        ident = _inteiro(_valor(linha, mapa, "id"))
        nome = _texto(_valor(linha, mapa, "nome"))
        if ident is None or nome is None:
            continue
        if ident in vistos:
            rel.aviso(
                f"aba {ABA_COMPONENTES}, linha {offset}: ID {ident} repetido; "
                "a segunda ocorrência foi ignorada"
            )
            continue
        vistos.add(ident)

        natureza_bruta = _valor(linha, mapa, "natureza")
        natureza = classificar_natureza(natureza_bruta)
        if natureza_bruta is not None and natureza is None:
            rel.aviso(
                f"aba {ABA_COMPONENTES}, linha {offset}: natureza "
                f'"{_texto(natureza_bruta)}" não reconhecida; esperado '
                '"Consumível" ou "Peça"'
            )

        lead = _numero(_valor(linha, mapa, "lead_time_dias"))
        if lead is None:
            rel.aviso(
                f"aba {ABA_COMPONENTES}, linha {offset} (ID {ident}): lead time "
                "em branco; o componente fica sem zona atribuída"
            )
        elif lead < 0:
            rel.erro(
                f"aba {ABA_COMPONENTES}, linha {offset} (ID {ident}): lead time "
                f"negativo ({lead:g})"
            )
            lead = None

        componentes.append(
            Componente(
                id=ident,
                nome=nome,
                subsistema=_texto(_valor(linha, mapa, "subsistema")),
                funcao=_texto(_valor(linha, mapa, "funcao")),
                natureza=natureza,
                rpn=_inteiro(_valor(linha, mapa, "rpn")),
                criticidade=_inteiro(_valor(linha, mapa, "criticidade")),
                lead_time_dias=lead,
                linha=offset,
            )
        )

    if not componentes:
        rel.erro(f'nenhum componente lido na aba "{ABA_COMPONENTES}"')
    return componentes


def _ler_modos(
    linhas: Sequence[Sequence[Any]], rel: RelatorioValidacao
) -> list[ModoDeFalha]:
    i = _achar_cabecalho(linhas)
    if i is None:
        rel.erro(f'não localizei a linha de cabeçalho da aba "{ABA_MODOS}"')
        return []
    mapa = _mapear_colunas(linhas[i], _COLS_MODOS, _MODOS_EXATOS)
    for obrigatoria in ("id", "sub_id"):
        if obrigatoria not in mapa:
            rel.erro(f'coluna "{obrigatoria}" não encontrada na aba "{ABA_MODOS}"')
            return []

    faltantes = [
        rotulo
        for chave, rotulo in (("ocorrencia", "O"), ("severidade", "S"), ("deteccao_nota", "D"))
        if chave not in mapa
    ]
    if faltantes:
        rel.erro(
            f'não encontrei a coluna de nota {", ".join(faltantes)} na aba '
            f'"{ABA_MODOS}"; o cabeçalho dessas colunas precisa ser exatamente '
            "O, S e D (ou Ocorrência, Severidade e Detecção)"
        )
        return []

    modos: list[ModoDeFalha] = []
    sub_ids: set[str] = set()
    for offset, linha in enumerate(linhas[i + 1 :], start=i + 2):
        ident = _inteiro(_valor(linha, mapa, "id"))
        sub_id = _texto(_valor(linha, mapa, "sub_id"))
        if ident is None or sub_id is None:
            continue
        if sub_id in sub_ids:
            rel.aviso(f"aba {ABA_MODOS}, linha {offset}: Sub ID {sub_id} repetido")
        sub_ids.add(sub_id)

        modo = ModoDeFalha(
            id_componente=ident,
            sub_id=sub_id,
            componente=_texto(_valor(linha, mapa, "componente")),
            subsistema=_texto(_valor(linha, mapa, "subsistema")),
            modo=_texto(_valor(linha, mapa, "modo")),
            causa=_texto(_valor(linha, mapa, "causa")),
            efeito_local=_texto(_valor(linha, mapa, "efeito_local")),
            efeito_equipamento=_texto(_valor(linha, mapa, "efeito_equipamento")),
            efeito_paciente=_texto(_valor(linha, mapa, "efeito_paciente")),
            deteccao=_texto(_valor(linha, mapa, "deteccao")),
            ocorrencia=_inteiro(_valor(linha, mapa, "ocorrencia")),
            severidade=_inteiro(_valor(linha, mapa, "severidade")),
            deteccao_nota=_inteiro(_valor(linha, mapa, "deteccao_nota")),
            rpn=_inteiro(_valor(linha, mapa, "rpn")),
            criticidade=_inteiro(_valor(linha, mapa, "criticidade")),
            linha=offset,
        )
        _validar_modo(modo, rel)
        modos.append(modo)

    if not modos:
        rel.erro(f'nenhum modo de falha lido na aba "{ABA_MODOS}"')
    return modos


def _validar_modo(modo: ModoDeFalha, rel: RelatorioValidacao) -> None:
    ref = f"modo {modo.sub_id}"
    for nome, valor in (
        ("Ocorrencia", modo.ocorrencia),
        ("Severidade", modo.severidade),
        ("Deteccao", modo.deteccao_nota),
    ):
        if valor is None:
            rel.aviso(f"{ref}: {nome} não informada")
        elif not 1 <= valor <= 10:
            rel.erro(f"{ref}: {nome} = {valor} fora da escala de 1 a 10")

    esperado_rpn = modo.rpn_calculado
    if esperado_rpn is not None and modo.rpn is not None and modo.rpn != esperado_rpn:
        rel.aviso(
            f"{ref}: RPN declarado {modo.rpn} difere de S x O x D = {esperado_rpn}; "
            "o cálculo usa o produto"
        )
    esperado_crit = modo.criticidade_calculada
    if (
        esperado_crit is not None
        and modo.criticidade is not None
        and modo.criticidade != esperado_crit
    ):
        rel.aviso(
            f"{ref}: Criticidade declarada {modo.criticidade} difere de "
            f"S x O = {esperado_crit}; o cálculo usa o produto"
        )


def _validar_cruzado(
    componentes: Sequence[Componente],
    modos: Sequence[ModoDeFalha],
    rel: RelatorioValidacao,
) -> None:
    ids_comp = {c.id for c in componentes}
    ids_modos = {m.id_componente for m in modos}

    for ident in sorted(ids_comp - ids_modos):
        rel.aviso(
            f"componente {ident} não tem nenhum modo de falha na aba "
            f'"{ABA_MODOS}"; ficará sem Criticidade calculada'
        )
    for ident in sorted(ids_modos - ids_comp):
        rel.erro(
            f'a aba "{ABA_MODOS}" tem modos do componente {ident}, ausente da '
            f'aba "{ABA_COMPONENTES}"'
        )

    for comp in componentes:
        seus = [m for m in modos if m.id_componente == comp.id]
        if not seus:
            continue
        crits = [m.criticidade_calculada for m in seus if m.criticidade_calculada]
        rpns = [m.rpn_calculado for m in seus if m.rpn_calculado]
        if crits and comp.criticidade is not None and comp.criticidade != max(crits):
            rel.aviso(
                f"componente {comp.id} ({comp.nome}): Criticidade {comp.criticidade} "
                f"na matriz difere do máximo dos modos ({max(crits)})"
            )
        if rpns and comp.rpn is not None and comp.rpn != max(rpns):
            rel.aviso(
                f"componente {comp.id} ({comp.nome}): RPN {comp.rpn} na matriz "
                f"difere do máximo dos modos ({max(rpns)})"
            )
        nomes = {m.componente for m in seus if m.componente}
        if nomes and comp.nome not in nomes:
            rel.aviso(
                f"componente {comp.id}: nome \"{comp.nome}\" na matriz não casa "
                f"com o usado nos modos ({sorted(nomes)[0]!r})"
            )
        subs = {m.subsistema for m in seus if m.subsistema}
        if comp.subsistema and subs and comp.subsistema not in subs:
            rel.aviso(
                f"componente {comp.id}: subsistema \"{comp.subsistema}\" na matriz "
                f"não casa com o usado nos modos ({sorted(subs)[0]!r})"
            )
