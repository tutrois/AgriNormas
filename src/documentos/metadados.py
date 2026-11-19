"""Metadados do documento (código, título, versão e data de emissão).

Ficam na primeira página: título em caixa alta, subtítulo em minúsculas e a tabela
"Identificação". Usa o texto bruto do `LeitorPdf`. Mensagens de erro citam o caminho e o
campo ausente, nunca o conteúdo do PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from documentos.leitor_pdf import LeitorPdf
from nucleo.erros import ErroDocumento

ROTULO_TABELA: Final[str] = "Identificação"

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

# Código no formato da base, três dígitos ao final (ex.: FIN-POL-001). É a única forma aceita.
_RE_CODIGO: Final[re.Pattern[str]] = re.compile(r"[A-Z]{2,4}-[A-Z]{2,4}-[0-9]{3}")

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


@dataclass(frozen=True)
class MetadadosDocumento:
    """Identificação de um documento da base de conhecimento."""

    codigo: str
    """Código do documento, ex.: `FIN-POL-001`."""
    titulo: str
    """Título em caixa alta, ex.: `POLÍTICA DE REEMBOLSO`."""
    versao: str
    """Versão, ex.: `1.0`."""
    data_emissao: str
    """Mês e ano de emissão, ex.: `Novembro/2026`."""


def extrair_metadados(texto_primeira_pagina: str, caminho: Path) -> MetadadosDocumento:
    """Extrai os metadados do texto bruto da primeira página. Função pura.

    `caminho` entra só nas mensagens de erro. Levanta `ErroDocumento` se a tabela, o título
    ou algum campo estiver ausente, ou se o código fugir do padrão `AAA-BBB-000`.
    """
    cabecalho, tabela = _separar_tabela(texto_primeira_pagina, caminho)
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


def _separar_tabela(texto: str, caminho: Path) -> tuple[str, str]:
    """Devolve (texto acima do rótulo, texto da tabela). Rótulo solto no corpo é ignorado."""
    linhas = texto.splitlines()
    for indice, linha in enumerate(linhas):
        if linha.strip() != ROTULO_TABELA:
            continue
        bloco = _bloco_da_tabela(linhas, indice + 1)
        if _tem_dados_da_tabela(bloco):
            return "\n".join(linhas[:indice]), "\n".join(bloco)
    raise ErroDocumento(f"Tabela de identificação ausente na primeira página: {caminho}")


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


def _extrair_codigo(tabela: str, caminho: Path) -> str:
    candidato = _casar(_RE_CANDIDATO_CODIGO, tabela, "codigo", caminho)
    if _RE_CODIGO.fullmatch(candidato) is None:
        raise ErroDocumento(f"Campo 'codigo' fora do padrão AAA-BBB-000 em {caminho}")
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
    if not candidato.isupper() or candidato.startswith(PREFIXO_CABECALHO):
        raise _erro_campo_ausente("titulo", caminho)
    return candidato


def _casar(padrao: re.Pattern[str], texto: str, grupo: str, caminho: Path) -> str:
    ocorrencia = padrao.search(texto)
    if ocorrencia is None:
        raise _erro_campo_ausente(grupo, caminho)
    return ocorrencia.group(grupo)


def _erro_campo_ausente(campo: str, caminho: Path) -> ErroDocumento:
    return ErroDocumento(f"Campo '{campo}' ausente na tabela de identificação de {caminho}")
