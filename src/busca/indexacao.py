"""Monta o índice a partir dos chunks (HIST-011, apoio à calibração e ao assistente).

`texto_indexavel` define o que é enviado ao provedor de embeddings para cada seção. Usar o
mesmo texto na calibração, nos testes e na composição mantém as pontuações comparáveis.

Com `perguntas_faq=True`, cada par de FAQ ganha uma segunda entrada no índice, com só a
pergunta, apontando para a mesma `Secao`. Assim, uma pergunta do usuário parecida com a do FAQ
se aproxima desse vetor, sem competir com a resposta inteira. O padrão é `False`, para que
quem não conhece a opção continue com uma entrada por seção.
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
    """Um texto que vai ao provedor e a seção à qual o vetor resultante pertence.

    Com `perguntas_faq`, uma seção de FAQ gera duas entradas, ambas com a mesma `Secao`.
    """

    secao: Secao
    texto: str


def texto_indexavel(secao: Secao) -> str:
    """Código do documento, número e título antes do corpo.

    Assim o código (ex.: `FIN-POL-001`) e o assunto entram no vetor, e uma pergunta que os
    cita se aproxima do trecho certo.
    """
    return f"{secao.documento} §{secao.numero} {secao.titulo}\n{secao.texto}"


def pergunta_de_faq(secao: Secao) -> str | None:
    """Devolve a pergunta de um par de FAQ, que é o título da seção, sem espaços nas pontas.

    Devolve `None` para seções que não são de FAQ e para pergunta vazia.
    """
    if secao.tipo != "faq":
        return None
    return secao.titulo.strip() or None


def entradas_indexaveis(
    secoes: Sequence[Secao], *, perguntas_faq: bool = False
) -> tuple[EntradaIndexavel, ...]:
    """Um texto por seção, na ordem das seções. Com `perguntas_faq`, a pergunta de cada FAQ
    vem logo depois do texto da sua seção.

    Com `perguntas_faq=False`, a saída tem exatamente uma entrada por seção. Sem seções, `()`.
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
    """Gera um vetor por entrada, em um único pedido ao provedor, e carrega o índice.

    Sem seções, devolve o índice vazio sem chamar o provedor (ADR-007).
    """
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
    """Monta o índice reaproveitando os vetores do cache (HIST-012, TSK-012.2).

    Só os textos cujo hash não está no cache, para o `modelo` atual, vão ao provedor, em um
    único pedido. Ao final o cache é regravado com as entradas atuais, então vetores de
    documentos removidos ou alterados saem do disco. Com `perguntas_faq`, as perguntas de FAQ
    também entram no cache, cada uma pelo próprio hash.

    Se os vetores novos têm dimensão diferente da do cache (M-29), o cache é descartado e
    todas as entradas são recalculadas em um segundo pedido, e a regravação substitui o cache
    antigo. Se esse segundo pedido também falhar, o cache antigo fica intacto.

    Limite conhecido: `construir_indice_com_cache` não compara a dimensão quando não há
    textos novos. Sem textos novos o cache é usado como está, sem chamar o provedor (critério
    da HIST-012). Nesse caso, uma divergência de dimensão entre o cache e o provedor não é
    detectada aqui e aparece na consulta como `ErroBusca`. A composição trata essa situação
    descartando e reconstruindo o índice (ver `src/composicao.py`, `_BuscadorComReconstrucao`).

    Sem seções, devolve o índice vazio e grava cache vazio, sem chamar o provedor (ADR-007).
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
