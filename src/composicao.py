"""Composição de dependências (HIST-018, TSK-018.1 e TSK-018.2).

É o único módulo que conhece as implementações concretas (OpenAI, numpy, pypdf). Monta as
dependências, carrega e indexa os documentos e devolve o `AssistenteRAG`. Não decide regra
de negócio: a recusa e as fontes ficam em `nucleo/assistente.py` (ADR-001).

A montagem usa o cache de vetores (`busca.cache`) em `CAMINHO_CACHE_VETORES`. Quando o cache
tem dimensão diferente da do provedor (M-29) e não há textos novos, o erro só aparece na
consulta. Nesse caso `_BuscadorComReconstrucao` descarta o cache, reconstrói o índice e
repete a pergunta uma única vez.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from busca.buscador import BuscadorSemantico
from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indexacao import construir_indice, construir_indice_com_cache, entradas_indexaveis
from busca.indice_memoria import MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE
from busca.provedor_openai import ProvedorEmbeddingOpenAI
from config import RAIZ_PROJETO, Configuracao, carregar_configuracao
from documentos.chunker_secao import ChunkerPorSecao
from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import limpar_paginas
from documentos.metadados import extrair_metadados
from geracao.gerador_openai import GeradorOpenAI
from nucleo.assistente import AssistenteRAG
from nucleo.contratos import Chunker, Indice, LeitorDocumento, ProvedorEmbedding
from nucleo.erros import ErroBusca, ErroDocumento
from nucleo.modelos import Secao, Trecho, Vetor

TAMANHO_LOTE_EMBEDDINGS: Final[int] = 100
"""Textos por pedido ao provedor de embeddings (mesmo valor usado na calibração)."""

CAMINHO_CACHE_VETORES: Final[Path] = RAIZ_PROJETO / "dados" / "indice.npz"
"""Cache dos vetores em disco. Fica em `dados/`, fora do git, e pode ser apagado com segurança."""


def montar_assistente(configuracao: Configuracao) -> AssistenteRAG:
    """Monta o `AssistenteRAG` a partir da configuração validada.

    Carrega os PDFs de `configuracao.pasta_documentos`, divide em seções e indexa, reaproveitando
    o cache de `CAMINHO_CACHE_VETORES`. Lança `ErroDocumento` se a pasta não gerar nenhuma seção,
    para que uma base vazia ou um caminho errado não vire recusa silenciosa de todas as perguntas.
    Erros de embedding propagam como `ErroBusca`.
    """
    secoes = carregar_secoes(configuracao.pasta_documentos, configuracao.tamanho_maximo_chunk)
    if not secoes:
        raise ErroDocumento(
            f"Nenhuma seção foi gerada a partir dos PDFs da pasta {configuracao.pasta_documentos}."
        )
    provedor = _provedor_embedding(configuracao)
    repositorio = RepositorioCacheVetores(CAMINHO_CACHE_VETORES)
    indice = construir_indice_com_cache(
        secoes,
        provedor,
        modelo=configuracao.modelo_embedding,
        repositorio=repositorio,
        perguntas_faq=True,
    )
    buscador = _BuscadorComReconstrucao(
        secoes,
        provedor,
        indice,
        repositorio=repositorio,
        modelo=configuracao.modelo_embedding,
        limiar_similaridade=configuracao.limiar_similaridade,
        top_k=configuracao.top_k,
    )
    gerador = GeradorOpenAI(
        chave=configuracao.chave_openai,
        timeout_segundos=configuracao.timeout_segundos,
        modelo=configuracao.modelo_geracao,
    )
    return AssistenteRAG(buscador, gerador)


def montar_assistente_do_ambiente() -> AssistenteRAG:
    """Carrega a configuração do ambiente (`.env` e `os.environ`) e monta o `AssistenteRAG`.

    Ponto de entrada para quem não deve conhecer `config`, como a interface. Erros de configuração
    propagam como `ConfiguracaoInvalida`, sem citar valores secretos.
    """
    return montar_assistente(carregar_configuracao())


def carregar_secoes(pasta: Path, tamanho_maximo: int) -> tuple[Secao, ...]:
    """Lê cada PDF da pasta, em ordem de nome, e devolve as seções de todos os documentos."""
    leitor = LeitorPdf()
    chunker = ChunkerPorSecao(tamanho_maximo=tamanho_maximo)
    secoes: list[Secao] = []
    for caminho in sorted(pasta.glob("*.pdf")):
        secoes.extend(_secoes_do_documento(caminho, leitor, chunker))
    return tuple(secoes)


def _secoes_do_documento(
    caminho: Path, leitor: LeitorDocumento, chunker: Chunker
) -> Sequence[Secao]:
    """Lê o PDF, extrai o código da primeira página, limpa o texto e divide em seções."""
    paginas = leitor.ler(caminho)
    codigo = extrair_metadados(paginas[0].texto, caminho).codigo
    return chunker.dividir(codigo, limpar_paginas(paginas))


def _provedor_embedding(configuracao: Configuracao) -> ProvedorEmbedding:
    return ProvedorEmbeddingOpenAI(
        modelo=configuracao.modelo_embedding,
        chave=configuracao.chave_openai,
        tamanho_lote=TAMANHO_LOTE_EMBEDDINGS,
        timeout_segundos=configuracao.timeout_segundos,
    )


class _BuscadorComReconstrucao:
    """Implementa `Buscador` e recalcula o índice quando o cache tem outra dimensão (M-29).

    Só o erro de dimensão do índice dispara a reconstrução. Ela descarta o cache, monta o índice
    de novo com todas as seções, regrava o cache e troca o índice em uso. A pergunta é repetida
    uma única vez: se falhar de novo, o erro sobe, sem laço.
    """

    def __init__(
        self,
        secoes: Sequence[Secao],
        provedor: ProvedorEmbedding,
        indice: Indice,
        *,
        repositorio: RepositorioCacheVetores,
        modelo: str,
        limiar_similaridade: float,
        top_k: int,
    ) -> None:
        self._secoes = tuple(secoes)
        self._provedor = provedor
        self._repositorio = repositorio
        self._modelo = modelo
        self._limiar_similaridade = limiar_similaridade
        self._top_k = top_k
        self._buscador = self._novo_buscador(indice)

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        try:
            return self._buscador.buscar(pergunta)
        except ErroBusca as erro:
            if not _dimensao_divergente(erro):
                raise
        self._reconstruir()
        return self._buscador.buscar(pergunta)

    def _novo_buscador(self, indice: Indice) -> BuscadorSemantico:
        return BuscadorSemantico(
            self._provedor,
            indice,
            limiar_similaridade=self._limiar_similaridade,
            top_k=self._top_k,
        )

    def _reconstruir(self) -> None:
        """Descarta o cache, recalcula todos os vetores, regrava o cache e troca o índice.

        O cache vazio é gravado antes do pedido ao provedor: se o recálculo falhar, não sobra
        vetor de dimensão antiga no disco. Se o índice não for montado, o atual segue em uso.
        """
        self._repositorio.gravar(())
        capturador = _ProvedorCapturador(self._provedor)
        indice = construir_indice(self._secoes, capturador, perguntas_faq=True)
        self._repositorio.gravar(_entradas_do_cache(self._secoes, capturador.vetores, self._modelo))
        self._buscador = self._novo_buscador(indice)


class _ProvedorCapturador:
    """Repassa os pedidos ao provedor e guarda os vetores devolvidos, para regravar o cache."""

    def __init__(self, provedor: ProvedorEmbedding) -> None:
        self._provedor = provedor
        self.vetores: tuple[Vetor, ...] = ()

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.vetores = self._provedor.gerar(textos)
        return self.vetores


def _dimensao_divergente(erro: ErroBusca) -> bool:
    return str(erro) == MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE


def _entradas_do_cache(
    secoes: Sequence[Secao], vetores: Sequence[Vetor], modelo: str
) -> tuple[EntradaCache, ...]:
    """Uma entrada de cache por vetor, com o hash do texto que foi enviado ao provedor.

    Usa as mesmas entradas de `construir_indice(..., perguntas_faq=True)`, na mesma ordem,
    para que o hash de cada pergunta de FAQ seja o da própria pergunta.
    """
    entradas = entradas_indexaveis(secoes, perguntas_faq=True)
    return tuple(
        EntradaCache(hash_texto=hash_texto(entrada.texto), modelo=modelo, vetor=vetor)
        for entrada, vetor in zip(entradas, vetores, strict=True)
    )
