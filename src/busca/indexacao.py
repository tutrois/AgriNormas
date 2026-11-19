"""Monta o índice a partir das seções, com ou sem cache de vetores.

`texto_indexavel` define o texto enviado ao provedor; usá-lo na calibração, nos testes e na
composição mantém as pontuações comparáveis.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True)
class EntradaIndexavel:
    """Um texto que vai ao provedor e a seção à qual o vetor pertence."""

    secao: Secao
    texto: str


def texto_indexavel(secao: Secao) -> str:
    """Código, número e título antes do corpo, para perguntas com `FIN-POL-001` acharem o trecho."""
    return f"{secao.documento} §{secao.numero} {secao.titulo}\n{secao.texto}"


def pergunta_de_faq(secao: Secao) -> str | None:
    """Título da seção de FAQ sem espaços nas pontas; `None` se não for FAQ ou estiver vazio."""
    if secao.tipo != "faq":
        return None
    return secao.titulo.strip() or None


def entradas_indexaveis(
    secoes: Sequence[Secao], *, perguntas_faq: bool = False
) -> tuple[EntradaIndexavel, ...]:
    """Um texto por seção; com `perguntas_faq`, a pergunta de cada FAQ vira uma segunda entrada.

    A entrada extra aproxima uma pergunta parecida com a do FAQ sem competir com a resposta
    inteira. Sem seções, devolve `()`.
    """
    entradas: list[EntradaIndexavel] = []
    for secao in secoes:
        entradas.append(EntradaIndexavel(secao=secao, texto=texto_indexavel(secao)))
        pergunta = pergunta_de_faq(secao) if perguntas_faq else None
        if pergunta is not None:
            entradas.append(EntradaIndexavel(secao=secao, texto=pergunta))
    return tuple(entradas)


def construir_indice(
    secoes: Sequence[Secao],
    provedor: ProvedorEmbedding,
    *,
    perguntas_faq: bool = False,
) -> IndiceEmMemoria:
    """Gera um vetor por entrada em um único pedido. Sem seções, não chama o provedor (ADR-007)."""
    entradas = entradas_indexaveis(secoes, perguntas_faq=perguntas_faq)
    indice = IndiceEmMemoria()
    if not entradas:
        return indice
    vetores = provedor.gerar(tuple(entrada.texto for entrada in entradas))
    indice.adicionar([entrada.secao for entrada in entradas], vetores)
    return indice


def construir_indice_com_cache(
    secoes: Sequence[Secao],
    provedor: ProvedorEmbedding,
    *,
    modelo: str,
    repositorio: RepositorioCacheVetores,
    perguntas_faq: bool = False,
) -> IndiceEmMemoria:
    """Monta o índice enviando ao provedor só os textos cujo hash não está no cache do `modelo`.

    O cache é regravado com as entradas atuais, então vetores de textos removidos saem do disco.
    Se os vetores novos têm dimensão diferente da do cache, o cache é descartado e tudo é
    recalculado; se isso falhar, o cache antigo fica intacto.

    Limite conhecido: sem textos novos o provedor não é chamado e a dimensão não é comparada;
    a divergência aparece na consulta como `ErroBusca` e a composição reconstrói o índice.

    Sem seções, grava cache vazio e devolve o índice vazio sem chamar o provedor (ADR-007).
    """
    entradas = entradas_indexaveis(secoes, perguntas_faq=perguntas_faq)
    if not entradas:
        repositorio.gravar(())
        return IndiceEmMemoria()

    textos = tuple(entrada.texto for entrada in entradas)
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
    indice.adicionar([entrada.secao for entrada in entradas], vetores)
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
    """Gera os textos dos `hashes` em um pedido; recusa quantidade ou dimensões divergentes."""
    novos = provedor.gerar(tuple(textos_por_hash[hash_] for hash_ in hashes))
    if len(novos) != len(hashes):
        raise ErroBusca(MENSAGEM_QUANTIDADE_VETORES_DIVERGENTE)
    if len({len(vetor) for vetor in novos}) > 1:
        raise ErroBusca(MENSAGEM_DIMENSAO_DIVERGENTE_NOVOS)
    return dict(zip(hashes, novos, strict=True))


def _dimensao(vetores_por_hash: Mapping[str, Vetor]) -> int:
    """Dimensão comum dos vetores; exige mapa não vazio e homogêneo."""
    return len(next(iter(vetores_por_hash.values())))
