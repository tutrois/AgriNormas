"""Índice vetorial em memória, com busca por similaridade cosseno.

Os vetores são normalizados na entrada, então a busca é uma única multiplicação
matriz-vetor (ver ADR-007 para entradas vazias). Vetor de norma zero pontua `0.0` em vez de
quebrar a busca. Toda validação ocorre antes de alterar o índice, e as mensagens de erro
são fixas, sem citar conteúdo.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from nucleo.erros import ErroBusca
from nucleo.modelos import Secao, Trecho, Vetor

MENSAGEM_QUANTIDADE_DIVERGENTE = "A quantidade de seções e de vetores não é igual."
MENSAGEM_VETOR_VAZIO = "Vetor de embedding sem dimensão."
MENSAGEM_DIMENSAO_DIVERGENTE_NO_LOTE = "Os vetores do lote têm dimensões diferentes."
MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE = "A dimensão do vetor não é igual à do índice."
MENSAGEM_VALOR_NAO_NUMERICO = "Vetor de embedding contém valor que não é número."
MENSAGEM_VALOR_NAO_FINITO = "Vetor de embedding contém valor NaN ou infinito."
MENSAGEM_VETOR_NAO_UNIDIMENSIONAL = "Vetor de embedding não é uma sequência simples de números."
MENSAGEM_INTEIRO_FORA_DO_LIMITE = "Vetor de embedding contém inteiro grande demais para real."


class IndiceEmMemoria:
    """Guarda cada seção junto ao seu vetor normalizado e responde a buscas por cosseno."""

    def __init__(self) -> None:
        self._secoes: list[Secao] = []
        self._matriz_normalizada: NDArray[np.float64] | None = None

    def adicionar(self, secoes: Sequence[Secao], vetores: Sequence[Vetor]) -> None:
        """Associa cada seção ao seu vetor. Sequências vazias não fazem nada (ADR-007)."""
        if len(secoes) != len(vetores):
            raise ErroBusca(MENSAGEM_QUANTIDADE_DIVERGENTE)
        if not secoes:
            return

        novos_vetores = _normalizar_lote(vetores)
        if (
            self._matriz_normalizada is not None
            and novos_vetores.shape[1] != self._matriz_normalizada.shape[1]
        ):
            raise ErroBusca(MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE)

        self._matriz_normalizada = (
            novos_vetores
            if self._matriz_normalizada is None
            else np.vstack((self._matriz_normalizada, novos_vetores))
        )
        self._secoes.extend(secoes)

    def buscar(self, vetor: Vetor, k: int) -> tuple[Trecho, ...]:
        """Devolve até `k` trechos, do mais para o menos similar. Índice vazio devolve `()`."""
        consulta = _normalizar_lote((vetor,))[0]
        if self._matriz_normalizada is None:
            return ()
        if consulta.shape[0] != self._matriz_normalizada.shape[1]:
            raise ErroBusca(MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE)
        if k <= 0:
            return ()

        pontuacoes_cosseno: NDArray[np.float64] = self._matriz_normalizada @ consulta
        ordem = np.argsort(-pontuacoes_cosseno, kind="stable")[:k]

        return tuple(
            Trecho(secao=self._secoes[indice], pontuacao=float(pontuacoes_cosseno[indice]))
            for indice in ordem.tolist()
        )


def _normalizar_lote(vetores: Sequence[Vetor]) -> NDArray[np.float64]:
    """Valida e converte os vetores em uma matriz de linhas com norma 1 (norma zero fica zero)."""
    convertidos = [_converter_para_real(vetor) for vetor in vetores]
    _validar_dimensoes(convertidos)
    matriz = np.vstack(convertidos)
    _validar_finitos(matriz)
    return _normalizar(matriz)


def _validar_dimensoes(convertidos: Sequence[NDArray[np.float64]]) -> None:
    dimensoes = {vetor.shape[0] for vetor in convertidos}
    if dimensoes == {0}:
        raise ErroBusca(MENSAGEM_VETOR_VAZIO)
    if len(dimensoes) != 1:
        raise ErroBusca(MENSAGEM_DIMENSAO_DIVERGENTE_NO_LOTE)


def _converter_para_real(vetor: Vetor) -> NDArray[np.float64]:
    """Converte um único vetor em array 1-D de float64, ou recusa com `ErroBusca`."""
    try:
        bruto = np.asarray(vetor)
    except TypeError:
        raise ErroBusca(MENSAGEM_VALOR_NAO_NUMERICO) from None
    except ValueError:
        # Forma irregular (ex.: ((1.0, 2.0), (3.0,))): o numpy recusa montar o array.
        raise ErroBusca(MENSAGEM_VETOR_NAO_UNIDIMENSIONAL) from None

    if bruto.dtype == np.object_:
        convertido = _converter_objetos_numericos(bruto)
    elif np.issubdtype(bruto.dtype, np.integer) or np.issubdtype(bruto.dtype, np.floating):
        convertido = bruto.astype(np.float64)
    else:
        raise ErroBusca(MENSAGEM_VALOR_NAO_NUMERICO)

    if convertido.ndim != 1:
        raise ErroBusca(MENSAGEM_VETOR_NAO_UNIDIMENSIONAL)
    return convertido


def _converter_objetos_numericos(bruto: NDArray[np.object_]) -> NDArray[np.float64]:
    """Trata arrays de objetos (inteiros grandes demais para int64); só int e float, sem bool.

    Inteiro que não cabe em float64 tem mensagem própria, distinta de valor não numérico.
    """
    elementos = bruto.ravel().tolist()
    if not all(_e_numero_real(elemento) for elemento in elementos):
        raise ErroBusca(MENSAGEM_VALOR_NAO_NUMERICO)
    try:
        return bruto.astype(np.float64)
    except OverflowError:
        raise ErroBusca(MENSAGEM_INTEIRO_FORA_DO_LIMITE) from None


def _e_numero_real(elemento: object) -> bool:
    return isinstance(elemento, (int, float)) and not isinstance(elemento, bool)


def _validar_finitos(matriz: NDArray[np.float64]) -> None:
    if not np.isfinite(matriz).all():
        raise ErroBusca(MENSAGEM_VALOR_NAO_FINITO)


def _normalizar(matriz: NDArray[np.float64]) -> NDArray[np.float64]:
    # Divide primeiro pelo maior valor absoluto de cada linha: a norma de 1e200 estouraria
    # para infinito e apagaria o vetor. Depois da escala, a norma é no máximo sqrt(dimensão).
    maiores_absolutos: NDArray[np.float64] = np.max(np.abs(matriz), axis=1, keepdims=True)
    escalados = np.zeros_like(matriz)
    np.divide(matriz, maiores_absolutos, out=escalados, where=maiores_absolutos > 0.0)

    normas: NDArray[np.float64] = np.linalg.norm(escalados, axis=1, keepdims=True)
    normalizados = np.zeros_like(matriz)
    np.divide(escalados, normas, out=normalizados, where=normas > 0.0)
    return normalizados
