"""Limpeza do texto extraído dos PDFs (HIST-005).

Cada função faz uma transformação e é pura: recebe texto e devolve texto, sem efeitos
colaterais. `limpar_paginas` compõe as etapas na ordem correta.

Os PDFs reais trazem três tipos de ruído que estas funções tratam:

- cabeçalho institucional repetido no topo de cada página;
- numeração de página (`Página N`), também repetida;
- quebras de linha do layout no meio das frases, que precisam virar espaço.

Não há palavras partidas por hífen na quebra de linha nos PDFs de `base_conhecimento/`,
então a correção de hifenização (TSK-005.3) não foi implementada: não há caso real.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from nucleo.modelos import Pagina

CABECALHO_PADRAO: Final[re.Pattern[str]] = re.compile(
    r"AGRICOPPEL\s*[\x7f•·]\s*MATERIAL FICTÍCIO.*"
)
"""Linha inteira do cabeçalho institucional.

O separador aparece como `\\x7f` no texto extraído pelo pypdf (o `•` original).
"""

RODAPE_PADRAO: Final[re.Pattern[str]] = re.compile(r"Página \d+")
"""Linha inteira com a numeração da página, ex.: `Página 2`."""

RODAPE_FIM_DO_DOCUMENTO: Final[re.Pattern[str]] = re.compile(
    r"Fim do documento\s*[\x7f•·]\s*Material simulado para avaliação técnica.*"
)
"""Linha inteira do rodapé de encerramento, presente no fim do Procedimento_Ferias.pdf."""

TITULO_NUMERADO: Final[re.Pattern[str]] = re.compile(r"\d+(?:\.\d+)*\.?\s+[A-ZÀ-Ý]")
"""Início de um título numerado, ex.: `3. Despesas`, `3.1 Transporte` ou `6.1 Exemplo`.

Exige letra maiúscula depois do número, para não confundir com linha de corpo que
começa com número (ex.: `5 (cinco) dias úteis`).
"""

LARGURA_LINHA_CHEIA: Final[int] = 95
"""Comprimento mínimo (`>=`) de uma linha para ser considerada quebrada pelo layout.

Nos três PDFs, as quebras de layout no meio da frase têm 96 caracteres ou mais. Este
valor sozinho não basta: fins de parágrafo também chegam a 96-114 caracteres no corpus.
Por isso `unir_quebras_de_linha` só une duas linhas quando a anterior tem esse tamanho,
não termina em pontuação de fim de frase e a seguinte começa com letra minúscula.

Limites da regra: o valor foi calibrado com o corpus atual e pode precisar de ajuste em
outro layout; uma quebra no meio da frase seguida de maiúscula (nome próprio, sigla ou
início de frase) não é unida; e um fim de parágrafo sem pontuação, seguido de linha que
começa com minúscula, seria unido indevidamente.
"""

PONTUACAO_FIM_DE_FRASE: Final[tuple[str, ...]] = (".", ";", ":", "?", "!", ")")
"""Caracteres que, no fim de uma linha, indicam que a frase terminou."""

_SEPARADOR_DE_BLOCO: Final[str] = " "


def remover_cabecalho(texto: str) -> str:
    """Remove as linhas do cabeçalho institucional."""
    return _remover_linhas(texto, CABECALHO_PADRAO)


def remover_rodape(texto: str) -> str:
    """Remove as linhas de rodapé: numeração de página (`Página N`) e o encerramento."""
    sem_numeracao = _remover_linhas(texto, RODAPE_PADRAO)
    return _remover_linhas(sem_numeracao, RODAPE_FIM_DO_DOCUMENTO)


def normalizar_espacos(texto: str) -> str:
    """Colapsa espaços e tabulações em um único espaço e apaga linhas vazias.

    Quebras de linha são preservadas aqui; quem decide quais viram espaço é
    `unir_quebras_de_linha`.
    """
    linhas = (" ".join(linha.split()) for linha in texto.splitlines())
    return "\n".join(linha for linha in linhas if linha)


def unir_quebras_de_linha(texto: str) -> str:
    """Une as linhas quebradas pelo layout e mantém títulos e perguntas em linha própria.

    Cada bloco de saída é um parágrafo, um título numerado ou uma pergunta de FAQ. A
    regra de união está em `_continua_paragrafo`, com seus limites descritos em
    `LARGURA_LINHA_CHEIA`.
    """
    linhas = texto.splitlines()
    if not linhas:
        return ""
    blocos = [linhas[0]]
    for anterior, linha in zip(linhas, linhas[1:], strict=False):
        if _continua_paragrafo(anterior, linha):
            blocos[-1] = f"{blocos[-1]}{_SEPARADOR_DE_BLOCO}{linha}"
        else:
            blocos.append(linha)
    return "\n".join(blocos)


def limpar_texto(texto: str) -> str:
    """Aplica as etapas de limpeza, na ordem, a um texto já concatenado."""
    sem_cabecalho = remover_cabecalho(texto)
    sem_rodape = remover_rodape(sem_cabecalho)
    return unir_quebras_de_linha(normalizar_espacos(sem_rodape))


def limpar_paginas(paginas: Sequence[Pagina]) -> str:
    """Texto limpo do documento inteiro, na ordem das páginas.

    Devolve `""` se nenhuma página tiver texto. Concatenar antes de unir as quebras
    permite que um parágrafo continue na página seguinte.
    """
    return limpar_texto("\n".join(pagina.texto for pagina in paginas))


def _remover_linhas(texto: str, padrao: re.Pattern[str]) -> str:
    """Mantém só as linhas que não casam inteiras com `padrao`."""
    return "\n".join(
        linha for linha in texto.splitlines() if padrao.fullmatch(linha.strip()) is None
    )


def _continua_paragrafo(anterior: str, linha: str) -> bool:
    """Diz se `linha` é a continuação do parágrafo que termina em `anterior`.

    Une só quando a quebra caiu no meio da frase: `anterior` é cheia e não termina em
    pontuação de fim de frase, e `linha` começa com letra minúscula.
    """
    if _eh_titulo(anterior) or _eh_pergunta(anterior):
        return False
    if _eh_titulo(linha) or _eh_pergunta(linha):
        return False
    return _quebra_no_meio_da_frase(anterior) and linha.lstrip()[:1].islower()


def _quebra_no_meio_da_frase(anterior: str) -> bool:
    """Linha com largura de quebra do layout que não termina a frase."""
    texto = anterior.rstrip()
    return len(texto) >= LARGURA_LINHA_CHEIA and not texto.endswith(PONTUACAO_FIM_DE_FRASE)


def _eh_titulo(linha: str) -> bool:
    return TITULO_NUMERADO.match(linha) is not None


def _eh_pergunta(linha: str) -> bool:
    """Perguntas de FAQ terminam com `?` e ficam em linha própria."""
    return linha.endswith("?")
