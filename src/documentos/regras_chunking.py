"""Regras de chunking como dados: títulos de exceção, FAQ e tamanho máximo.

Só constantes; a lógica fica em `chunker_secao.py`.
"""

from __future__ import annotations

import re
from typing import Final

RE_CABECALHO_SECAO: Final[re.Pattern[str]] = re.compile(
    r"(?P<numero>\d+)\.\s+(?P<titulo>[A-ZÀ-Ý].*)"
)
"""Seção de primeiro nível (`6. Prazo e fluxo`). Exige o ponto, então não casa `6.1 Exemplo`."""

RE_CABECALHO_SUBSECAO: Final[re.Pattern[str]] = re.compile(
    r"(?P<numero>\d+(?:\.\d+)+)\s+(?P<titulo>[A-ZÀ-Ý].*)"
)
"""Subseção (`6.1 Exemplo`), com um ou mais níveis (`3.1.2`)."""

TERMINADOR_PERGUNTA: Final[str] = "?"
"""Parágrafo que termina com este caractere é a pergunta de um par de FAQ."""

PREFIXO_NUMERO_FAQ: Final[str] = "faq-"

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
