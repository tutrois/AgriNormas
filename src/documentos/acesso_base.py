"""Lista e lê os documentos da base de conhecimento para a interface.

Não sabe de configuração nem de ambiente: recebe a pasta e o tamanho do chunk. Quem
resolve o `.env` é `composicao.py`. Só aceita nomes de arquivo listados na pasta.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from documentos.chunker_secao import ChunkerPorSecao
from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import limpar_paginas
from documentos.metadados import extrair_metadados
from documentos.regras_chunking import TAMANHO_MAXIMO_CHUNK
from nucleo.contratos import LeitorDocumento
from nucleo.erros import ErroDocumento
from nucleo.modelos import ConteudoDoDocumento, DocumentoDaBase, Secao, SecaoDoDocumento

_LOG = logging.getLogger(__name__)


def listar_documentos_da_base(pasta: Path) -> tuple[DocumentoDaBase, ...]:
    """Lê a primeira página de cada PDF da pasta, em ordem de nome, e devolve a identificação.

    Pasta inexistente ou vazia devolve `()`. PDF com erro de leitura ou de metadados entra com
    o nome do arquivo como título e código e versão vazios; o aviso no log não cita conteúdo.
    """
    leitor = LeitorPdf()
    return tuple(_documento_da_base(caminho, leitor) for caminho in sorted(pasta.glob("*.pdf")))


def ler_documento_da_base(
    pasta: Path, arquivo: str, *, tamanho_maximo: int = TAMANHO_MAXIMO_CHUNK
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
