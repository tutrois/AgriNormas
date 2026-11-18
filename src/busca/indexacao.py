"""Monta o índice a partir dos chunks (HIST-011, apoio à calibração e ao assistente).

`texto_indexavel` define o que é enviado ao provedor de embeddings para cada seção. Usar o
mesmo texto na calibração, nos testes e na composição mantém as pontuações comparáveis.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indice_memoria import IndiceEmMemoria
from nucleo.contratos import ProvedorEmbedding
from nucleo.erros import ErroBusca
from nucleo.modelos import Secao, Vetor

logger = logging.getLogger(__name__)

MENSAGEM_QUANTIDADE_VETORES_DIVERGENTE = (
    "O provedor de embeddings devolveu uma quantidade de vetores diferente da pedida."
)
MENSAGEM_DIMENSAO_DIVERGENTE_NOVOS = (
    "O provedor de embeddings devolveu vetores de dimensões diferentes; o cache não foi gravado."
)
MENSAGEM_CACHE_DIMENSAO_DIVERGENTE = (
    "Vetores do cache têm dimensão diferente da do provedor; o cache será recalculado."
)


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


def construir_indice_com_cache(
    secoes: Sequence[Secao],
    provedor: ProvedorEmbedding,
    *,
    modelo: str,
    repositorio: RepositorioCacheVetores,
) -> IndiceEmMemoria:
    """Monta o índice reaproveitando os vetores do cache (HIST-012, TSK-012.2).

    Só os textos cujo hash não está no cache, para o `modelo` atual, vão ao provedor, em um
    único pedido. Ao final o cache é regravado com os chunks atuais, então vetores de
    documentos removidos ou alterados saem do disco.

    Se os vetores novos têm dimensão diferente da do cache (M-29), o cache é descartado e
    todos os chunks são recalculados em um segundo pedido, e a regravação substitui o cache
    antigo. Se esse segundo pedido também falhar, o cache antigo fica intacto.

    Limite conhecido: `construir_indice_com_cache` não compara a dimensão quando não há
    textos novos. Sem textos novos o cache é usado como está, sem chamar o provedor (critério
    da HIST-012). Nesse caso, uma divergência de dimensão entre o cache e o provedor não é
    detectada aqui e aparece na consulta como `ErroBusca`. A composição trata essa situação
    descartando e reconstruindo o índice (ver `src/composicao.py`, `_BuscadorComReconstrucao`).

    Sem seções, devolve o índice vazio e grava cache vazio, sem chamar o provedor (ADR-007).
    """
    if not secoes:
        repositorio.gravar(())
        return IndiceEmMemoria()

    textos = tuple(texto_indexavel(secao) for secao in secoes)
    hashes = tuple(hash_texto(texto) for texto in textos)
    hashes_unicos = tuple(dict.fromkeys(hashes))
    textos_por_hash = dict(zip(hashes, textos, strict=True))
    vetores_conhecidos = repositorio.ler(modelo)

    faltantes = tuple(hash_ for hash_ in hashes_unicos if hash_ not in vetores_conhecidos)
    vetores_por_hash: dict[str, Vetor] = dict(vetores_conhecidos)
    if faltantes:
        gerados = _gerar_validado(provedor, faltantes, textos_por_hash)
        if vetores_conhecidos and _dimensao(gerados) != _dimensao(vetores_conhecidos):
            logger.warning(MENSAGEM_CACHE_DIMENSAO_DIVERGENTE)
            vetores_por_hash = {}
            gerados = _gerar_validado(provedor, hashes_unicos, textos_por_hash)
        vetores_por_hash.update(gerados)

    vetores = [vetores_por_hash[hash_] for hash_ in hashes]
    indice = IndiceEmMemoria()
    indice.adicionar(secoes, vetores)
    repositorio.gravar(
        tuple(
            EntradaCache(hash_texto=hash_, modelo=modelo, vetor=vetor)
            for hash_, vetor in zip(hashes, vetores, strict=True)
        )
    )
    return indice


def _gerar_validado(
    provedor: ProvedorEmbedding,
    hashes: Sequence[str],
    textos_por_hash: Mapping[str, str],
) -> dict[str, Vetor]:
    """Pede ao provedor os textos dos `hashes`, em um pedido, e valida a resposta.

    Recusa quantidade diferente da pedida e vetores de dimensões diferentes entre si.
    """
    novos = provedor.gerar(tuple(textos_por_hash[hash_] for hash_ in hashes))
    if len(novos) != len(hashes):
        raise ErroBusca(MENSAGEM_QUANTIDADE_VETORES_DIVERGENTE)
    if len({len(vetor) for vetor in novos}) > 1:
        raise ErroBusca(MENSAGEM_DIMENSAO_DIVERGENTE_NOVOS)
    return dict(zip(hashes, novos, strict=True))


def _dimensao(vetores_por_hash: Mapping[str, Vetor]) -> int:
    """Dimensão comum dos vetores. Só chamada com mapa não vazio e de dimensão homogênea."""
    return len(next(iter(vetores_por_hash.values())))
