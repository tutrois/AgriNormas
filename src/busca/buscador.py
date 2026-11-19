"""Buscador semântico com limiar de similaridade (HIST-011, TSK-011.1).

Implementa o contrato `Buscador`. Gera o embedding da pergunta, pede ao `Indice` os trechos
mais próximos e descarta os que ficam abaixo de `limiar_similaridade`.

Uma seção pode ter mais de uma entrada no índice (ex.: o texto completo e a pergunta de um
FAQ). O buscador devolve cada seção uma vez, com a maior pontuação entre as suas entradas, e
limita o resultado a `top_k` seções distintas.

O buscador não conhece a OpenAI nem o formato interno do índice: as dependências entram
pelo construtor (princípio D). Sem trecho acima do limiar devolve `()`, nunca `None` (ADR-007).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from nucleo.contratos import Indice, ProvedorEmbedding
from nucleo.erros import ConfiguracaoInvalida, ErroBusca
from nucleo.modelos import Secao, Trecho

MENSAGEM_VETOR_PERGUNTA_INVALIDO = "O provedor de embeddings devolveu um vetor inesperado."

MAXIMO_ENTRADAS_POR_SECAO: Final[int] = 2
"""Entradas do índice por seção, no máximo (texto completo e pergunta de FAQ).

Pedir `top_k * MAXIMO_ENTRADAS_POR_SECAO` candidatos garante `top_k` seções distintas quando elas
existem: em qualquer prefixo do ranking, cada seção ocupa no máximo duas posições.
"""


class BuscadorSemantico:
    """Implementa `Buscador`: top-k seções por cosseno, filtradas pelo limiar de similaridade."""

    def __init__(
        self,
        provedor: ProvedorEmbedding,
        indice: Indice,
        *,
        limiar_similaridade: float,
        top_k: int,
    ) -> None:
        if not (math.isfinite(limiar_similaridade) and 0.0 <= limiar_similaridade <= 1.0):
            raise ConfiguracaoInvalida("O limiar de similaridade deve estar entre 0 e 1.")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ConfiguracaoInvalida(
                "O número de trechos recuperados deve ser um inteiro de pelo menos 1."
            )
        self._provedor = provedor
        self._indice = indice
        self._limiar_similaridade = limiar_similaridade
        self._top_k = top_k

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        """Devolve até `top_k` seções com pontuação maior ou igual ao limiar, da mais similar.

        Cada seção aparece uma vez, com a maior pontuação entre as suas entradas.
        A pergunta vazia não chega aqui: a validação é do `AssistenteRAG` (TSK-017.2).
        Falhas do provedor ou do índice propagam como `ErroBusca`.
        """
        vetores = self._provedor.gerar((pergunta,))
        if len(vetores) != 1:
            raise ErroBusca(MENSAGEM_VETOR_PERGUNTA_INVALIDO)
        (vetor_pergunta,) = vetores
        candidatos = self._indice.buscar(vetor_pergunta, self._top_k * MAXIMO_ENTRADAS_POR_SECAO)
        acima_do_limiar = tuple(
            trecho
            for trecho in _maior_pontuacao_por_secao(candidatos)
            if trecho.pontuacao >= self._limiar_similaridade
        )
        return acima_do_limiar[: self._top_k]


def _maior_pontuacao_por_secao(trechos: Sequence[Trecho]) -> tuple[Trecho, ...]:
    """Uma entrada por seção, a de maior pontuação, do mais para o menos similar.

    Empates mantêm a ordem em que os trechos chegaram.
    """
    melhores: dict[Secao, Trecho] = {}
    for trecho in trechos:
        atual = melhores.get(trecho.secao)
        if atual is None or trecho.pontuacao > atual.pontuacao:
            melhores[trecho.secao] = trecho
    return tuple(sorted(melhores.values(), key=lambda trecho: trecho.pontuacao, reverse=True))
