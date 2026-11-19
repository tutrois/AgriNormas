"""Limpeza do texto extraído dos PDFs: funções puras, uma transformação cada.

Remove cabeçalho e numeração de página e une as quebras de linha do layout no meio das
frases. Hifenização não é tratada: os PDFs de `base_conhecimento/` não têm esse caso.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from nucleo.modelos import Pagina

CABECALHO_PADRAO: Final[re.Pattern[str]] = re.compile(
    r"AGRICOPPEL\s*[\x7f•·]\s*MATERIAL FICTÍCIO.*"
)
"""Linha do cabeçalho institucional. O `•` original sai como `\\x7f` no texto do pypdf."""

RODAPE_PADRAO: Final[re.Pattern[str]] = re.compile(r"Página \d+")

RODAPE_FIM_DO_DOCUMENTO: Final[re.Pattern[str]] = re.compile(
    r"Fim do documento\s*[\x7f•·]\s*Material simulado para avaliação técnica.*"
)

TITULO_NUMERADO: Final[re.Pattern[str]] = re.compile(r"\d+(?:\.\d+)*\.?\s+[A-ZÀ-Ý]")
"""Início de título numerado (`3. Despesas`, `3.1 Transporte`).

Exige maiúscula depois do número para não confundir com corpo (`5 (cinco) dias úteis`).
"""

LARGURA_LINHA_CHEIA: Final[int] = 95
"""Comprimento mínimo (`>=`) de uma linha para ser considerada quebrada pelo layout.

Nos PDFs do corpus, as quebras no meio da frase têm 96 caracteres ou mais, mas fins de
parágrafo também chegam a 96-114. Por isso só se une quando a linha anterior tem esse
tamanho, não termina em pontuação e a seguinte começa com minúscula.

Limites: valor calibrado com o corpus atual; quebra seguida de maiúscula (nome próprio,
sigla) não é unida; fim de parágrafo sem pontuação seguido de minúscula seria unido.
"""

PONTUACAO_FIM_DE_FRASE: Final[tuple[str, ...]] = (".", ";", ":", "?", "!", ")")

_SEPARADOR_DE_BLOCO: Final[str] = " "


def remover_cabecalho(texto: str) -> str:
    """Remove as linhas do cabeçalho institucional."""
    return _remover_linhas(texto, CABECALHO_PADRAO)


def remover_rodape(texto: str) -> str:
    """Remove as linhas de rodapé: numeração de página (`Página N`) e o encerramento."""
    sem_numeracao = _remover_linhas(texto, RODAPE_PADRAO)
    return _remover_linhas(sem_numeracao, RODAPE_FIM_DO_DOCUMENTO)


def normalizar_espacos(texto: str) -> str:
    """Colapsa espaços e tabulações e apaga linhas vazias, preservando as quebras de linha."""
    linhas = (" ".join(linha.split()) for linha in texto.splitlines())
    return "\n".join(linha for linha in linhas if linha)


def unir_quebras_de_linha(texto: str) -> str:
    """Une as linhas quebradas pelo layout; títulos e perguntas ficam em linha própria.

    Limites da regra em `LARGURA_LINHA_CHEIA`.
    """
    linhas = texto.splitlines()
    return "\n".join(
        _SEPARADOR_DE_BLOCO.join(linhas[inicio:fim]) for inicio, fim in _agrupar_linhas(linhas)
    )


def limpar_texto(texto: str) -> str:
    """Aplica as etapas de limpeza, na ordem, a um texto já concatenado."""
    sem_cabecalho = remover_cabecalho(texto)
    sem_rodape = remover_rodape(sem_cabecalho)
    return unir_quebras_de_linha(normalizar_espacos(sem_rodape))


def limpar_paginas(paginas: Sequence[Pagina]) -> tuple[tuple[int, str], ...]:
    """Parágrafos limpos do documento, na ordem, cada um com o número da página em que começa.

    Devolve pares `(numero_da_pagina, texto)`, um por parágrafo; um parágrafo que atravessa
    páginas recebe a página em que começa. Devolve `()` se nenhuma página tiver texto.

    A limpeza é feita por página, mas a união das quebras corre sobre as linhas de todas
    elas, para o parágrafo poder continuar na página seguinte. Juntar os pares com `"\\n"`
    reproduz o resultado de `limpar_texto`.
    """
    linhas_com_pagina = [
        (pagina.numero, linha) for pagina in paginas for linha in _linhas_limpas(pagina.texto)
    ]
    textos = [linha for _, linha in linhas_com_pagina]
    return tuple(
        (linhas_com_pagina[inicio][0], _SEPARADOR_DE_BLOCO.join(textos[inicio:fim]))
        for inicio, fim in _agrupar_linhas(textos)
    )


def _linhas_limpas(texto: str) -> list[str]:
    return normalizar_espacos(remover_rodape(remover_cabecalho(texto))).splitlines()


def _agrupar_linhas(linhas: Sequence[str]) -> list[tuple[int, int]]:
    """Blocos de linhas consecutivas como `(inicio, fim)`, com `fim` exclusivo."""
    grupos: list[tuple[int, int]] = []
    for indice, linha in enumerate(linhas):
        if indice > 0 and _continua_paragrafo(linhas[indice - 1], linha):
            inicio, _ = grupos[-1]
            grupos[-1] = (inicio, indice + 1)
        else:
            grupos.append((indice, indice + 1))
    return grupos


def _remover_linhas(texto: str, padrao: re.Pattern[str]) -> str:
    return "\n".join(
        linha for linha in texto.splitlines() if padrao.fullmatch(linha.strip()) is None
    )


def _continua_paragrafo(anterior: str, linha: str) -> bool:
    """Une só quando a quebra caiu no meio da frase (ver `LARGURA_LINHA_CHEIA`)."""
    if _eh_titulo(anterior) or _eh_pergunta(anterior):
        return False
    if _eh_titulo(linha) or _eh_pergunta(linha):
        return False
    return _quebra_no_meio_da_frase(anterior) and linha.lstrip()[:1].islower()


def _quebra_no_meio_da_frase(anterior: str) -> bool:
    texto = anterior.rstrip()
    return len(texto) >= LARGURA_LINHA_CHEIA and not texto.endswith(PONTUACAO_FIM_DE_FRASE)


def _eh_titulo(linha: str) -> bool:
    return TITULO_NUMERADO.match(linha) is not None


def _eh_pergunta(linha: str) -> bool:
    """Perguntas de FAQ terminam com `?` e ficam em linha própria."""
    return linha.endswith("?")
