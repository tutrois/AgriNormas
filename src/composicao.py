"""Composição de dependências: único módulo que conhece as implementações concretas.

É o único módulo que conhece as implementações concretas (OpenAI, numpy, pypdf). Monta as
dependências, carrega e indexa os documentos e devolve o `AssistenteRAG`. Não decide regra
de negócio: a recusa e as fontes ficam em `nucleo/assistente.py` (ADR-001).

Com `NUMERO_REFORMULACOES` maior que zero, a busca semântica é envolvida por
`BuscadorComFormulacoes`, com o `ReescritorOpenAI` (ADR-010). Com zero, a busca é só a semântica.

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
from busca.buscador_formulacoes import BuscadorComFormulacoes
from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indexacao import construir_indice, construir_indice_com_cache, entradas_indexaveis
from busca.provedor_openai import ProvedorEmbeddingOpenAI
from config import (
    RAIZ_PROJETO,
    Configuracao,
    carregar_configuracao,
    configuracao_dos_documentos,
)
from documentos.acesso_base import ler_documento_da_base, listar_documentos_da_base
from documentos.chunker_secao import ChunkerPorSecao
from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import limpar_paginas
from documentos.metadados import extrair_metadados
from geracao.gerador_openai import GeradorOpenAI
from geracao.reescritor_consulta import ReescritorOpenAI
from nucleo.assistente import AssistenteRAG
from nucleo.contratos import (
    Buscador,
    Chunker,
    Indice,
    LeitorDocumento,
    ProvedorEmbedding,
    ReescritorConsulta,
)
from nucleo.erros import ErroDimensaoIndice, ErroDocumento
from nucleo.modelos import ConteudoDoDocumento, DocumentoDaBase, Secao, Trecho, Vetor

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
        reescritor=_reescritor(configuracao),
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


def listar_documentos_do_ambiente() -> tuple[DocumentoDaBase, ...]:
    """Lista os documentos da pasta configurada em `PASTA_DOCUMENTOS`, sem exigir a chave da API.

    Usa o mesmo ambiente (`.env` e `os.environ`) e a mesma resolução de pasta de
    `carregar_configuracao`, mas não valida a chave. Pasta com valor inválido propaga
    `ConfiguracaoInvalida`.
    """
    return listar_documentos_da_base(configuracao_dos_documentos()[0])


def ler_documento_do_ambiente(arquivo: str) -> ConteudoDoDocumento | None:
    """Lê um documento da pasta configurada em `PASTA_DOCUMENTOS`, sem exigir a chave da API.

    Usa o mesmo ambiente e a mesma resolução de pasta e de tamanho de chunk de
    `carregar_configuracao`. Veja `ler_documento_da_base` para as regras de `arquivo`.
    """
    pasta, tamanho_maximo = configuracao_dos_documentos()
    return ler_documento_da_base(pasta, arquivo, tamanho_maximo=tamanho_maximo)


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


def _reescritor(configuracao: Configuracao) -> ReescritorConsulta | None:
    """Reescritor com N formulações, ou None quando N é 0 (ADR-010): sem reescrita, sem fusão."""
    if configuracao.numero_reformulacoes == 0:
        return None
    return ReescritorOpenAI(
        chave=configuracao.chave_openai,
        timeout_segundos=configuracao.timeout_segundos,
        numero_formulacoes=configuracao.numero_reformulacoes,
        modelo=configuracao.modelo_geracao,
    )


class _BuscadorComReconstrucao:
    """Implementa `Buscador` e reconstrói o índice se o cache tiver outra dimensão.

    Só o erro de dimensão do índice dispara a reconstrução. Ela descarta o cache, monta o índice
    de novo com todas as seções, regrava o cache e troca o índice em uso. A pergunta é repetida
    uma única vez: se falhar de novo, o erro sobe, sem laço.

    Com `reescritor`, o buscador em uso é o `BuscadorComFormulacoes` (ADR-010). Sem ele, é só o
    `BuscadorSemantico`. Nos dois casos a reconstrução recria o buscador do mesmo jeito.
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
        reescritor: ReescritorConsulta | None,
    ) -> None:
        self._secoes = tuple(secoes)
        self._provedor = provedor
        self._repositorio = repositorio
        self._modelo = modelo
        self._limiar_similaridade = limiar_similaridade
        self._top_k = top_k
        self._reescritor = reescritor
        self._buscador = self._novo_buscador(indice)

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        try:
            return self._buscador.buscar(pergunta)
        except ErroDimensaoIndice:
            pass
        self._reconstruir()
        return self._buscador.buscar(pergunta)

    def _novo_buscador(self, indice: Indice) -> Buscador:
        semantico = BuscadorSemantico(
            self._provedor,
            indice,
            limiar_similaridade=self._limiar_similaridade,
            top_k=self._top_k,
        )
        if self._reescritor is None:
            return semantico
        return BuscadorComFormulacoes(
            semantico,
            self._reescritor,
            limiar_similaridade=self._limiar_similaridade,
            top_k=self._top_k,
        )

    def _reconstruir(self) -> None:
        """Recalcula os vetores e troca o índice.

        O cache vazio é gravado antes: se o recálculo falhar, não sobra vetor de dimensão antiga.
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


def _entradas_do_cache(
    secoes: Sequence[Secao], vetores: Sequence[Vetor], modelo: str
) -> tuple[EntradaCache, ...]:
    """Uma entrada por vetor, na mesma ordem de `construir_indice(..., perguntas_faq=True)`."""
    entradas = entradas_indexaveis(secoes, perguntas_faq=True)
    return tuple(
        EntradaCache(hash_texto=hash_texto(entrada.texto), modelo=modelo, vetor=vetor)
        for entrada, vetor in zip(entradas, vetores, strict=True)
    )
