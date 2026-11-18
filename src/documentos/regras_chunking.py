"""Regras de chunking como dados (HIST-007): títulos de exceção, FAQ e tamanho máximo.

Este módulo só guarda constantes. A lógica que as usa fica em `chunker_secao.py`, para que
ajustar uma regra (ex.: incluir uma nova seção que não pode ser dividida) não exija mexer
no algoritmo.
"""

from __future__ import annotations

import re
from typing import Final

RE_CABECALHO_SECAO: Final[re.Pattern[str]] = re.compile(
    r"(?P<numero>\d+)\.\s+(?P<titulo>[A-ZÀ-Ý].*)"
)
"""Seção de primeiro nível, ex.: `6. Prazo e fluxo de solicitação`.

Exige o ponto logo depois do número e um espaço, então não casa com `6.1 Exemplo`.
"""

RE_CABECALHO_SUBSECAO: Final[re.Pattern[str]] = re.compile(
    r"(?P<numero>\d+(?:\.\d+)+)\s+(?P<titulo>[A-ZÀ-Ý].*)"
)
"""Subseção, ex.: `6.1 Exemplo de contagem do prazo`. Aceita mais de um nível (`3.1.2`)."""

TERMINADOR_PERGUNTA: Final[str] = "?"
"""Parágrafo que termina com este caractere é a pergunta de um par de FAQ."""

PREFIXO_NUMERO_FAQ: Final[str] = "faq-"
"""Prefixo do número de cada par de FAQ, ex.: `faq-1`."""

TAMANHO_MAXIMO_CHUNK: Final[int] = 1200
"""Tamanho máximo, em caracteres, de um chunk dividido por parágrafo. Padrão do construtor."""

TITULOS_EXCECAO: Final[tuple[str, ...]] = (
    "Despesas não elegíveis",
    "Multas e infrações",
)
"""Seções que ficam inteiras, sem divisão por tamanho.

A comparação ignora maiúsculas e minúsculas. FIN-POL-001 tem a seção 4 e FRO-POL-002 tem a
seção 6. Cada uma é uma regra de negócio que não pode ser cortada no meio.
"""

TITULO_FAQ: Final[str] = "Perguntas frequentes e interpretações"
"""Seção cujo corpo é uma sequência de pares pergunta e resposta (seções 11 e 12 do corpus)."""

MAXIMO_CARACTERES_TITULO: Final[int] = 120
"""Linha com mais caracteres que isso não é título de seção, mesmo que comece com número.

Evita tratar como cabeçalho um parágrafo de corpo que comece com `2. ` ou `3.1 `.
"""
