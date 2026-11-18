"""Monta o índice a partir dos chunks (HIST-011, apoio à calibração e ao assistente).

`texto_indexavel` define o que é enviado ao provedor de embeddings para cada seção. Usar o
mesmo texto na calibração, nos testes e na composição mantém as pontuações comparáveis.
"""

from __future__ import annotations

from collections.abc import Sequence

from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indice_memoria import IndiceEmMemoria
from nucleo.contratos import ProvedorEmbedding
from nucleo.erros import ErroBusca
from nucleo.modelos import Secao, Vetor

MENSAGEM_QUANTIDADE_VETORES_DIVERGENTE = (
    "O provedor de embeddings devolveu uma quantidade de vetores diferente da pedida."
)
MENSAGEM_DIMENSAO_DIVERGENTE_NOVOS = (
    "O provedor de embeddings devolveu vetores de dimensões diferentes; o cache não foi gravado."
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

    Sem seções, devolve o índice vazio e grava cache vazio, sem chamar o provedor (ADR-007).
    """
    if not secoes:
        repositorio.gravar(())
        return IndiceEmMemoria()

    textos = tuple(texto_indexavel(secao) for secao in secoes)
    hashes = tuple(hash_texto(texto) for texto in textos)
    vetores_conhecidos = repositorio.ler(modelo)

    textos_por_hash = dict(zip(hashes, textos, strict=True))
    hashes_novos = tuple(
        hash_ for hash_ in dict.fromkeys(hashes) if hash_ not in vetores_conhecidos
    )
    vetores_por_hash: dict[str, Vetor] = dict(vetores_conhecidos)
    if hashes_novos:
        novos = provedor.gerar(tuple(textos_por_hash[hash_] for hash_ in hashes_novos))
        if len(novos) != len(hashes_novos):
            raise ErroBusca(MENSAGEM_QUANTIDADE_VETORES_DIVERGENTE)
        if len({len(vetor) for vetor in novos}) > 1:
            raise ErroBusca(MENSAGEM_DIMENSAO_DIVERGENTE_NOVOS)
        vetores_por_hash.update(zip(hashes_novos, novos, strict=True))

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
