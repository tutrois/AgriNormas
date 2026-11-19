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

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from busca.buscador import BuscadorSemantico
from busca.buscador_formulacoes import BuscadorComFormulacoes
from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indexacao import construir_indice, construir_indice_com_cache, entradas_indexaveis
from busca.indice_memoria import MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE
from busca.provedor_openai import ProvedorEmbeddingOpenAI
from config import (
    PADRAO_TAMANHO_MAXIMO_CHUNK,
    RAIZ_PROJETO,
    TAMANHO_CHUNK_MAXIMO,
    TAMANHO_CHUNK_MINIMO,
    Configuracao,
    _ambiente_do_processo,
    _inteiro_entre,
    _pasta_documentos,
    carregar_configuracao,
)
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
from nucleo.erros import ErroBusca, ErroDocumento
from nucleo.modelos import Secao, Trecho, Vetor

TAMANHO_LOTE_EMBEDDINGS: Final[int] = 100
"""Textos por pedido ao provedor de embeddings (mesmo valor usado na calibração)."""

CAMINHO_CACHE_VETORES: Final[Path] = RAIZ_PROJETO / "dados" / "indice.npz"
"""Cache dos vetores em disco. Fica em `dados/`, fora do git, e pode ser apagado com segurança."""

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentoDaBase:
    """Documento da base de conhecimento, como a interface o exibe."""

    arquivo: str
    """Nome do arquivo, ex.: `Politica_Reembolso.pdf`."""
    codigo: str
    """Código do documento, ex.: `FIN-POL-001`. Vazio se o PDF não pôde ser lido."""
    titulo: str
    """Título extraído do PDF ou, se ilegível, o nome do arquivo sem extensão."""
    versao: str
    """Versão, ex.: `1.0`. Vazia se o PDF não pôde ser lido."""


@dataclass(frozen=True)
class SecaoDoDocumento:
    """Seção de um documento, pronta para exibição."""

    numero: str
    """Número da seção, ex.: `6`, `3.1` ou `faq-5`."""
    titulo: str
    """Título da seção; para FAQ, a pergunta."""
    texto: str
    """Corpo da seção, sem as linhas de título que o chunker inclui no começo."""
    tipo: str
    """Tipo da seção no chunker, ex.: `normal`, `excecao` ou `faq`."""


@dataclass(frozen=True)
class ConteudoDoDocumento:
    """Documento da base com o conteúdo dividido em seções."""

    arquivo: str
    codigo: str
    titulo: str
    versao: str
    secoes: tuple[SecaoDoDocumento, ...]


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
    return listar_documentos_da_base(_pasta_documentos(_ambiente_do_processo(None)))


def listar_documentos_da_base(pasta: Path) -> tuple[DocumentoDaBase, ...]:
    """Lê a primeira página de cada PDF da pasta, em ordem de nome, e devolve a identificação.

    Pasta inexistente ou vazia devolve `()`. PDF com erro de leitura ou de metadados entra com
    o nome do arquivo como título e código e versão vazios; o aviso no log não cita conteúdo.
    """
    leitor = LeitorPdf()
    return tuple(_documento_da_base(caminho, leitor) for caminho in sorted(pasta.glob("*.pdf")))


def ler_documento_do_ambiente(arquivo: str) -> ConteudoDoDocumento | None:
    """Lê um documento da pasta configurada em `PASTA_DOCUMENTOS`, sem exigir a chave da API.

    Usa o mesmo ambiente e a mesma resolução de pasta e de tamanho de chunk de
    `carregar_configuracao`. Veja `ler_documento_da_base` para as regras de `arquivo`.
    """
    valores = _ambiente_do_processo(None)
    return ler_documento_da_base(
        _pasta_documentos(valores),
        arquivo,
        tamanho_maximo=_inteiro_entre(
            valores,
            "TAMANHO_MAXIMO_CHUNK",
            PADRAO_TAMANHO_MAXIMO_CHUNK,
            TAMANHO_CHUNK_MINIMO,
            TAMANHO_CHUNK_MAXIMO,
        ),
    )


def ler_documento_da_base(
    pasta: Path, arquivo: str, *, tamanho_maximo: int = PADRAO_TAMANHO_MAXIMO_CHUNK
) -> ConteudoDoDocumento | None:
    """Devolve o conteúdo do PDF `arquivo` da pasta, dividido nas mesmas seções da busca.

    `arquivo` não é confiável: só é aceito se for exatamente o nome de um `*.pdf` listado
    diretamente em `pasta`. O caminho lido é o do glob, nunca montado a partir de `arquivo`.
    Nome inválido, PDF ilegível ou sem seções devolve `None`; o log não cita conteúdo nem caminho.
    """
    if not isinstance(arquivo, str):
        return None
    caminho = next((c for c in pasta.glob("*.pdf") if c.name == arquivo), None)
    if caminho is None:
        return None
    try:
        paginas = LeitorPdf().ler(caminho)
        metadados = extrair_metadados(paginas[0].texto, caminho)
        secoes = ChunkerPorSecao(tamanho_maximo=tamanho_maximo).dividir(
            metadados.codigo, limpar_paginas(paginas)
        )
    except ErroDocumento, IndexError:
        _LOG.warning("Não foi possível ler o conteúdo de um documento da base.")
        return None
    if not secoes:
        _LOG.warning("Um documento da base não gerou seções.")
        return None
    return ConteudoDoDocumento(
        arquivo=caminho.name,
        codigo=metadados.codigo,
        titulo=metadados.titulo,
        versao=metadados.versao,
        secoes=tuple(_secao_do_documento(secao) for secao in secoes),
    )


_CABECALHO_NUMERADO = re.compile(r"^\d+(?:\.\d+)*\.?\s+(?P<resto>\S.*)$")


def _secao_do_documento(secao: Secao) -> SecaoDoDocumento:
    return SecaoDoDocumento(
        numero=secao.numero,
        titulo=secao.titulo,
        texto=_corpo_sem_titulo(secao),
        tipo=secao.tipo,
    )


def _corpo_sem_titulo(secao: Secao) -> str:
    """Tira o cabeçalho que o chunker prefixa (seção pai e título); sem essa linha, não altera."""
    linhas = secao.texto.split("\n")
    for indice, linha in enumerate(linhas[:3]):
        if _repete_titulo(linha, secao.titulo):
            return "\n".join(linhas[indice + 1 :]).strip()
        if not _CABECALHO_NUMERADO.match(linha):
            break
    return secao.texto


def _repete_titulo(linha: str, titulo: str) -> bool:
    casamento = _CABECALHO_NUMERADO.match(linha)
    candidato = casamento.group("resto") if casamento else linha
    return candidato.strip() == titulo.strip()


def _documento_da_base(caminho: Path, leitor: LeitorDocumento) -> DocumentoDaBase:
    try:
        paginas = leitor.ler(caminho)
        metadados = extrair_metadados(paginas[0].texto, caminho)
    except ErroDocumento, IndexError:
        _LOG.warning("Não foi possível ler os metadados de um documento da base.")
        return DocumentoDaBase(arquivo=caminho.name, codigo="", titulo=caminho.stem, versao="")
    return DocumentoDaBase(
        arquivo=caminho.name,
        codigo=metadados.codigo,
        titulo=metadados.titulo,
        versao=metadados.versao,
    )


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
        except ErroBusca as erro:
            if not _dimensao_divergente(erro):
                raise
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


def _dimensao_divergente(erro: ErroBusca) -> bool:
    return str(erro) == MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE


def _entradas_do_cache(
    secoes: Sequence[Secao], vetores: Sequence[Vetor], modelo: str
) -> tuple[EntradaCache, ...]:
    """Uma entrada por vetor, na mesma ordem de `construir_indice(..., perguntas_faq=True)`."""
    entradas = entradas_indexaveis(secoes, perguntas_faq=True)
    return tuple(
        EntradaCache(hash_texto=hash_texto(entrada.texto), modelo=modelo, vetor=vetor)
        for entrada, vetor in zip(entradas, vetores, strict=True)
    )
