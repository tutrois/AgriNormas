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

    Devolve uma tupla de pares `(numero_da_pagina, texto)`, um par por parágrafo unido.
    Um parágrafo que atravessa páginas recebe a página em que começa. Páginas sem texto
    útil não geram pares. Devolve `()` se nenhuma página tiver texto.

    Contrato novo (HIST-007, M-18): antes, esta função devolvia uma única `str`, e o
    número da página se perdia. `Secao.pagina` precisa dele. A limpeza de cada linha
    (cabeçalho, rodapé e espaços) é feita por página, e a união das quebras é feita
    sobre a sequência de linhas de todas as páginas, o que permite que um parágrafo
    continue na página seguinte. A junção dos pares com `"\\n"` reproduz o texto que
    `limpar_texto` devolveria para o documento concatenado.
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
    """Linhas de uma página, sem cabeçalho, rodapé nem espaços sobrando."""
    return normalizar_espacos(remover_rodape(remover_cabecalho(texto))).splitlines()


def _agrupar_linhas(linhas: Sequence[str]) -> list[tuple[int, int]]:
    """Agrupa linhas consecutivas em blocos, devolvendo `(inicio, fim)` de cada bloco.

    `fim` é exclusivo. Uma linha só entra no bloco da anterior quando
    `_continua_paragrafo` diz que é continuação.
    """
    grupos: list[tuple[int, int]] = []
    for indice, linha in enumerate(linhas):
        if indice > 0 and _continua_paragrafo(linhas[indice - 1], linha):
            inicio, _ = grupos[-1]
            grupos[-1] = (inicio, indice + 1)
        else:
            grupos.append((indice, indice + 1))
    return grupos


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
