"""Buscador semântico: consulta o `Indice` e descarta o que fica abaixo do limiar.

Uma seção pode ter mais de uma entrada no índice (texto e pergunta de FAQ); cada seção é
devolvida uma vez, com a maior pontuação. Sem trecho acima do limiar devolve `()` (ADR-007).
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
"""Entradas do índice por seção, no máximo.

Pedir `top_k * MAXIMO_ENTRADAS_POR_SECAO` candidatos garante `top_k` seções distintas quando
elas existem, pois cada seção ocupa no máximo duas posições do ranking.
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
        """Devolve até `top_k` seções com pontuação >= limiar, da mais similar.

        A pergunta vazia é validada pelo `AssistenteRAG`. Falhas viram `ErroBusca`.
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
    """Uma entrada por seção, a de maior pontuação; empates mantêm a ordem de chegada."""
    melhores: dict[Secao, Trecho] = {}
    for trecho in trechos:
        atual = melhores.get(trecho.secao)
        if atual is None or trecho.pontuacao > atual.pontuacao:
            melhores[trecho.secao] = trecho
    return tuple(sorted(melhores.values(), key=lambda trecho: trecho.pontuacao, reverse=True))
