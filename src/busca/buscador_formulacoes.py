"""Busca ampliada por formulações alternativas da pergunta (HIST-029, ADR-010).

Implementa o contrato `Buscador`. Busca a pergunta original e cada formulação devolvida pelo
`ReescritorConsulta`, funde os resultados (cada seção fica com a maior pontuação entre as buscas
em que apareceu), aplica o limiar sobre a pontuação fundida e corta em `top_k`.

O adaptador não conhece o provedor de embeddings, o índice nem o modelo de linguagem. O
`Buscador` e o `ReescritorConsulta` entram pelo construtor (princípio D). O `Buscador` injetado
deve ser configurado com o mesmo `limiar_similaridade` e o mesmo `top_k` passados aqui: a
composição é quem garante isso.

Falha do reescritor (`ErroReescrita`) cai na pergunta original, com aviso em log. `ErroBusca`
propaga sem alteração. Sem resultados devolve `()`, nunca `None` (ADR-007).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from typing import Final

from nucleo.contratos import Buscador, ReescritorConsulta
from nucleo.erros import ConfiguracaoInvalida, ErroReescrita
from nucleo.modelos import Secao, Trecho

logger = logging.getLogger(__name__)

MENSAGEM_AVISO_REESCRITA: Final[str] = (
    "Reescrita da pergunta indisponível (%s); a busca segue só com a pergunta original."
)
"""Aviso em log. Recebe só o nome da classe da exceção: nunca a pergunta, a chave ou a resposta."""


class BuscadorComFormulacoes:
    """Implementa `Buscador`: fusão pelo máximo das buscas da pergunta e de suas formulações."""

    def __init__(
        self,
        buscador: Buscador,
        reescritor: ReescritorConsulta,
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
        self._buscador = buscador
        self._reescritor = reescritor
        self._limiar_similaridade = limiar_similaridade
        self._top_k = top_k

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        """Devolve até `top_k` seções com pontuação fundida maior ou igual ao limiar.

        A pergunta original é buscada sempre, primeiro. Depois vem cada formulação que o
        reescritor devolveu. Falhas de busca (`ErroBusca`) propagam.
        """
        resultados: list[Iterable[Trecho]] = [self._buscador.buscar(pergunta)]
        for formulacao in self._formulacoes(pergunta):
            resultados.append(self._buscador.buscar(formulacao))

        fundidos = _maior_pontuacao_por_secao(
            trecho for resultado in resultados for trecho in resultado
        )
        acima_do_limiar = tuple(
            trecho for trecho in fundidos if trecho.pontuacao >= self._limiar_similaridade
        )
        return acima_do_limiar[: self._top_k]

    def _formulacoes(self, pergunta: str) -> tuple[str, ...]:
        """Formulações úteis para a busca. Falha do reescritor vira lista vazia, com aviso."""
        try:
            propostas = self._reescritor.reescrever(pergunta)
        except ErroReescrita as erro:
            logger.warning(MENSAGEM_AVISO_REESCRITA, type(erro).__name__)
            return ()
        return _formulacoes_distintas(propostas, pergunta)


def _formulacoes_distintas(propostas: Sequence[str], pergunta: str) -> tuple[str, ...]:
    """Descarta vazias e repetidas, sem diferenciar espaços nas pontas ou caixa da letra.

    A pergunta original não entra: ela já é buscada sempre (regra 5 do ADR-010).
    """
    vistas: set[str] = {_chave(pergunta)}
    novas: list[str] = []
    for proposta in propostas:
        texto = proposta.strip()
        chave = _chave(texto)
        if not texto or chave in vistas:
            continue
        vistas.add(chave)
        novas.append(texto)
    return tuple(novas)


def _chave(texto: str) -> str:
    return texto.strip().casefold()


def _maior_pontuacao_por_secao(trechos: Iterable[Trecho]) -> tuple[Trecho, ...]:
    """Uma entrada por seção, a de maior pontuação, do mais para o menos similar.

    Empates mantêm a ordem em que os trechos chegaram: a pergunta original vem antes.
    """
    melhores: dict[Secao, Trecho] = {}
    for trecho in trechos:
        atual = melhores.get(trecho.secao)
        if atual is None or trecho.pontuacao > atual.pontuacao:
            melhores[trecho.secao] = trecho
    return tuple(sorted(melhores.values(), key=lambda trecho: trecho.pontuacao, reverse=True))
