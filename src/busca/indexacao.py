"""Monta o índice a partir dos chunks (HIST-011, apoio à calibração e ao assistente).

`texto_indexavel` define o que é enviado ao provedor de embeddings para cada seção. Usar o
mesmo texto na calibração, nos testes e na composição mantém as pontuações comparáveis.
"""

from __future__ import annotations

from collections.abc import Sequence

from busca.indice_memoria import IndiceEmMemoria
from nucleo.contratos import ProvedorEmbedding
from nucleo.modelos import Secao


def texto_indexavel(secao: Secao) -> str:
    """Código do documento, número e título antes do corpo.

    Assim o código (ex.: `FIN-POL-001`) e o assunto entram no vetor, e uma pergunta que os
    cita se aproxima do trecho certo.
    """
    return f"{secao.documento} §{secao.numero} {secao.titulo}\n{secao.texto}"


def construir_indice(secoes: Sequence[Secao], provedor: ProvedorEmbedding) -> IndiceEmMemoria:
    """Gera um vetor por seção, em um único pedido ao provedor, e carrega o índice.

    Sem seções, devolve o índice vazio sem chamar o provedor (ADR-007).
    """
    indice = IndiceEmMemoria()
    if not secoes:
        return indice
    vetores = provedor.gerar(tuple(texto_indexavel(secao) for secao in secoes))
    indice.adicionar(secoes, vetores)
    return indice
