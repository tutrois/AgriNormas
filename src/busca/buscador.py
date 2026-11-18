"""Buscador semântico com limiar de similaridade (HIST-011, TSK-011.1).

Implementa o contrato `Buscador`. Gera o embedding da pergunta, pede ao `Indice` os `top_k`
trechos mais próximos e descarta os que ficam abaixo de `limiar_similaridade`.

O buscador não conhece a OpenAI nem o formato interno do índice: as dependências entram
pelo construtor (princípio D). Sem trecho acima do limiar devolve `()`, nunca `None` (ADR-007).
"""

from __future__ import annotations

import math

from nucleo.contratos import Indice, ProvedorEmbedding
from nucleo.erros import ConfiguracaoInvalida, ErroBusca
from nucleo.modelos import Trecho

MENSAGEM_VETOR_PERGUNTA_INVALIDO = "O provedor de embeddings devolveu um vetor inesperado."


class BuscadorSemantico:
    """Implementa `Buscador`: top-k por cosseno, filtrado pelo limiar de similaridade."""

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
        """Devolve até `top_k` trechos com pontuação maior ou igual ao limiar, do mais similar.

        A pergunta vazia não chega aqui: a validação é do `AssistenteRAG` (TSK-017.2).
        Falhas do provedor ou do índice propagam como `ErroBusca`.
        """
        vetores = self._provedor.gerar((pergunta,))
        if len(vetores) != 1:
            raise ErroBusca(MENSAGEM_VETOR_PERGUNTA_INVALIDO)
        (vetor_pergunta,) = vetores
        candidatos = self._indice.buscar(vetor_pergunta, self._top_k)
        return tuple(
            trecho for trecho in candidatos if trecho.pontuacao >= self._limiar_similaridade
        )
