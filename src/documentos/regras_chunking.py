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

TITULOS_FAQ: Final[tuple[str, ...]] = (
    "Perguntas frequentes e interpretações",
    "Perguntas frequentes",
)
"""Seções cujo corpo é uma sequência de pares pergunta e resposta.

A primeira forma é das seções 11 e 12 do corpus de políticas; a segunda é da seção 14 do
PSI-004. A comparação ignora maiúsculas e minúsculas, como em `TITULOS_EXCECAO`.
"""

MAXIMO_CARACTERES_TITULO: Final[int] = 120
"""Linha com mais caracteres que isso não é título de seção, mesmo que comece com número.

Evita tratar como cabeçalho um parágrafo de corpo que comece com `2. ` ou `3.1 `.
"""
