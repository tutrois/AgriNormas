"""Metadados do documento (código, título, versão e data de emissão).

Dois layouts de primeira página são aceitos:

- Tabela: título em caixa alta, subtítulo em minúsculas e a tabela "Identificação". É o layout
  de FIN-POL-001, FRO-POL-002 e RH-PRO-003.
- Linha única: sem tabela, a identificação numa linha só, "Identificação: PSI-004    Versão: 1.0
  Vigência fictícia: 01/01/2026". É o layout de PSI-004.

A tabela tem prioridade: a linha única só é lida quando não há tabela com dados. Usa o texto
bruto do `LeitorPdf`. Mensagens de erro citam o caminho e o campo ausente, nunca o conteúdo do PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from documentos.leitor_pdf import LeitorPdf
from nucleo.erros import ErroDocumento

ROTULO_TABELA: Final[str] = "Identificação"

PREFIXO_LINHA_UNICA: Final[str] = "Identificação:"
"""Início da linha de identificação do layout sem tabela (note os dois pontos)."""

PREFIXO_CABECALHO: Final[str] = "AGRICOPPEL"
"""Início do cabeçalho de página. Ele pode estar em caixa alta, mas nunca é título."""

TAMANHO_MAXIMO_LINHA_DA_TABELA: Final[int] = 60
"""Linha mais longa que isso é parágrafo de texto corrido e encerra a tabela.

Heurística que vale para os PDFs do corpus: os valores da tabela são curtos (ex.:
"Versão 1.0 • Novembro/2026") e o primeiro parágrafo do corpo passa do limite. Se o
layout mudar, reveja este valor. Dois modos de falha conhecidos:

(a) Uma linha da própria tabela com mais de 60 caracteres encerra o bloco antes do
    código. Se o código e a versão ficarem depois dela, a mensagem sai como
    "Tabela de identificação ausente", embora a tabela exista.
(b) Se a tabela não trouxer o código, uma linha curta do corpo logo após ela pode ser
    lida como código.
"""

# Código da base: `XXX-000` (ex.: PSI-004) ou `XXX-YYY-000` (ex.: FIN-POL-001). Os segmentos
# alfabéticos têm de 2 a 4 letras maiúsculas e o número termina com três dígitos. Qualquer outra
# forma é rejeitada.
_RE_CODIGO: Final[re.Pattern[str]] = re.compile(r"[A-Z]{2,4}-(?:[A-Z]{2,4}-)?[0-9]{3}")

# `[^\S\n]` é um espaço em branco que não é quebra de linha (inclui `\t` e `\xa0`). É a mesma
# regra que `str.strip()` aplica a cada linha, então recuo de qualquer um desses caracteres
# não impede a extração.

# Linha com cara de código: letras maiúsculas e dígitos separados por hífen, sozinha na linha.
# Acha a linha do código mesmo quando ele está fora do formato, e então `_RE_CODIGO` rejeita
# o valor com erro em vez de ignorar a linha e reportar o campo como ausente.
_RE_CANDIDATO_CODIGO: Final[re.Pattern[str]] = re.compile(
    r"^[^\S\n]*(?P<codigo>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)[^\S\n]*$", re.MULTILINE
)

# Versão, ex.: "Versão 1.0". Aceita um ou mais componentes numéricos separados por ponto.
_RE_VERSAO: Final[re.Pattern[str]] = re.compile(
    r"^[^\S\n]*Versão[^\S\n]+(?P<versao>[0-9]+(?:\.[0-9]+)*)", re.MULTILINE
)

# Data de emissão, ex.: "Novembro/2026", na mesma linha da versão. Entre as duas há um
# separador que não é letra nem dígito: "•" no PDF original e "\x7f" no texto do pypdf.
_RE_DATA_EMISSAO: Final[re.Pattern[str]] = re.compile(
    r"^[^\S\n]*Versão[^\n]*?(?P<data>[^\W\d_]+/[0-9]{4})[^\S\n]*$", re.MULTILINE
)

# Layout de linha única: código logo depois do rótulo, ex.: "Identificação: PSI-004".
_RE_CODIGO_NA_LINHA: Final[re.Pattern[str]] = re.compile(
    r"Identificação:[^\S\n]*(?P<codigo>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)"
)

# Versão na mesma linha, ex.: "Versão: 1.0". Diferente da tabela, aqui o rótulo leva dois pontos.
_RE_VERSAO_NA_LINHA: Final[re.Pattern[str]] = re.compile(
    r"Versão:[^\S\n]*(?P<versao>[0-9]+(?:\.[0-9]+)*)"
)

# Data `dd/mm/aaaa` na mesma linha, ex.: a data de vigência "01/01/2026".
_RE_DATA_NA_LINHA: Final[re.Pattern[str]] = re.compile(r"(?P<data>[0-9]{2}/[0-9]{2}/[0-9]{4})")


@dataclass(frozen=True)
class MetadadosDocumento:
    """Identificação de um documento da base de conhecimento."""

    codigo: str
    """Código do documento, ex.: `FIN-POL-001` ou `PSI-004`."""
    titulo: str
    """Título em caixa alta, ex.: `POLÍTICA DE REEMBOLSO`."""
    versao: str
    """Versão, ex.: `1.0`."""
    data_emissao: str
    """Data de emissão. Na tabela, mês e ano (`Novembro/2026`); na linha única, a data de
    vigência `dd/mm/aaaa` (`01/01/2026`)."""


def extrair_metadados(texto_primeira_pagina: str, caminho: Path) -> MetadadosDocumento:
    """Extrai os metadados do texto bruto da primeira página. Função pura.

    Lê a tabela "Identificação" quando ela existe com dados; senão, lê a linha
    "Identificação: CÓDIGO ... Versão: V ...". `caminho` entra só nas mensagens de erro.
    Levanta `ErroDocumento` se a identificação, o título ou algum campo estiver ausente, ou
    se o código fugir dos padrões `XXX-000` e `XXX-YYY-000`.

    Na linha única, `data_emissao` recebe a data de vigência `dd/mm/aaaa` dessa mesma linha.
    O modelo exige uma data e esse layout não traz "Mês/AAAA"; a escolha da vigência em vez
    de outra data é documentada aqui. Sem data na linha, levanta erro citando o campo `data`.
    A linha só é aceita com código e versão; sem um dos dois, levanta erro.
    """
    separada = _separar_tabela(texto_primeira_pagina)
    if separada is None:
        return _metadados_da_linha_unica(texto_primeira_pagina, caminho)
    cabecalho, tabela = separada
    return MetadadosDocumento(
        codigo=_extrair_codigo(tabela, caminho),
        titulo=_extrair_titulo(cabecalho, caminho),
        versao=_casar(_RE_VERSAO, tabela, "versao", caminho),
        data_emissao=_casar(_RE_DATA_EMISSAO, tabela, "data", caminho),
    )


def ler_metadados(caminho: Path) -> MetadadosDocumento:
    """Lê o PDF e extrai os metadados da primeira página; erros de leitura vêm do `LeitorPdf`."""
    # `LeitorPdf.ler` sempre devolve ao menos uma página (ou levanta erro): o índice 0 é seguro.
    primeira_pagina = LeitorPdf().ler(caminho)[0]
    return extrair_metadados(primeira_pagina.texto, caminho)


def _separar_tabela(texto: str) -> tuple[str, str] | None:
    """Devolve (texto acima do rótulo, texto da tabela), ou `None` sem tabela com dados.

    Rótulo solto no corpo é ignorado.
    """
    linhas = texto.splitlines()
    for indice, linha in enumerate(linhas):
        if linha.strip() != ROTULO_TABELA:
            continue
        bloco = _bloco_da_tabela(linhas, indice + 1)
        if _tem_dados_da_tabela(bloco):
            return "\n".join(linhas[:indice]), "\n".join(bloco)
    return None


def _bloco_da_tabela(linhas: list[str], inicio: int) -> list[str]:
    bloco: list[str] = []
    for linha in linhas[inicio:]:
        conteudo = linha.strip()
        if conteudo == ROTULO_TABELA or len(conteudo) > TAMANHO_MAXIMO_LINHA_DA_TABELA:
            break
        bloco.append(linha)
    return bloco


def _tem_dados_da_tabela(bloco: list[str]) -> bool:
    texto = "\n".join(bloco)
    return _RE_CANDIDATO_CODIGO.search(texto) is not None or _RE_VERSAO.search(texto) is not None


def _metadados_da_linha_unica(texto: str, caminho: Path) -> MetadadosDocumento:
    """Layout sem tabela: usa a primeira linha que começa com "Identificação:".

    Título: o bloco em caixa alta acima dessa linha (ver `_extrair_titulo_em_bloco`).
    """
    linhas = texto.splitlines()
    indice = _indice_da_linha_unica(linhas)
    if indice is None:
        raise ErroDocumento(f"Tabela de identificação ausente na primeira página: {caminho}")
    linha = linhas[indice].strip()
    codigo = _casar(_RE_CODIGO_NA_LINHA, linha, "codigo", caminho)
    return MetadadosDocumento(
        codigo=_validar_codigo(codigo, caminho),
        titulo=_extrair_titulo_em_bloco("\n".join(linhas[:indice]), caminho),
        versao=_casar(_RE_VERSAO_NA_LINHA, linha, "versao", caminho),
        data_emissao=_casar(_RE_DATA_NA_LINHA, linha, "data", caminho),
    )


def _indice_da_linha_unica(linhas: list[str]) -> int | None:
    for indice, linha in enumerate(linhas):
        if linha.strip().startswith(PREFIXO_LINHA_UNICA):
            return indice
    return None


def _extrair_codigo(tabela: str, caminho: Path) -> str:
    candidato = _casar(_RE_CANDIDATO_CODIGO, tabela, "codigo", caminho)
    return _validar_codigo(candidato, caminho)


def _validar_codigo(candidato: str, caminho: Path) -> str:
    if _RE_CODIGO.fullmatch(candidato) is None:
        raise ErroDocumento(f"Campo 'codigo' fora do padrão XXX-000 ou XXX-YYY-000 em {caminho}")
    return candidato


def _extrair_titulo(cabecalho: str, caminho: Path) -> str:
    """O título é a linha não vazia antes do subtítulo (a última antes do rótulo).

    Só é aceito em caixa alta e sem começar com `PREFIXO_CABECALHO`. Premissa: o subtítulo
    está em minúsculas, mas isso não é verificado; em caixa alta, a linha acima dele ainda
    é tomada como título.
    """
    linhas = [linha.strip() for linha in cabecalho.splitlines() if linha.strip()]
    if len(linhas) < 2:
        raise _erro_campo_ausente("titulo", caminho)
    candidato = linhas[-2]
    if not _e_linha_de_titulo(candidato):
        raise _erro_campo_ausente("titulo", caminho)
    return candidato


def _extrair_titulo_em_bloco(cabecalho: str, caminho: Path) -> str:
    """Título do layout sem tabela: o primeiro bloco de linhas em caixa alta do cabeçalho.

    O título pode ocupar mais de uma linha, e elas são juntadas com espaço: no PSI-004,
    "POLÍTICA DE USO DE RECURSOS DE TI E" e "SEGURANÇA DA INFORMAÇÃO" viram uma só. Linhas
    fora de caixa alta antes do bloco, como "Página 1" e a faixa "Documento simulado | ...",
    são ignoradas. O bloco termina na primeira linha que não está em caixa alta.
    """
    bloco: list[str] = []
    for linha in (linha.strip() for linha in cabecalho.splitlines()):
        if _e_linha_de_titulo(linha):
            bloco.append(linha)
        elif bloco:
            break
    if not bloco:
        raise _erro_campo_ausente("titulo", caminho)
    return " ".join(bloco)


def _e_linha_de_titulo(linha: str) -> bool:
    """Caixa alta e sem o prefixo do cabeçalho institucional. Linha vazia não é título."""
    return linha.isupper() and not linha.startswith(PREFIXO_CABECALHO)


def _casar(padrao: re.Pattern[str], texto: str, grupo: str, caminho: Path) -> str:
    ocorrencia = padrao.search(texto)
    if ocorrencia is None:
        raise _erro_campo_ausente(grupo, caminho)
    return ocorrencia.group(grupo)


def _erro_campo_ausente(campo: str, caminho: Path) -> ErroDocumento:
    return ErroDocumento(f"Campo '{campo}' ausente na tabela de identificação de {caminho}")
