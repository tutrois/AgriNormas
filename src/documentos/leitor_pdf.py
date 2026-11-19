"""Leitor de PDF com pypdf: extrai o texto bruto de cada página, sem limpá-lo."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from nucleo.erros import ErroDocumento
from nucleo.modelos import Pagina

PRIMEIRA_PAGINA: Final[int] = 1

# Exceções que o pypdf levanta sem herdar de `PyPdfError`: `NotImplementedError` para
# filtro de stream não suportado e `ValueError` para cmap malformado. São tratadas
# explicitamente, em vez de `except Exception`, para que bugs do próprio código
# continuem aparecendo como falhas reais.
ERROS_NAO_ENCAPSULADOS_DO_PYPDF: Final[tuple[type[Exception], ...]] = (
    NotImplementedError,
    ValueError,
)

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class LeitorPdf:
    """Implementa `LeitorDocumento` para PDFs com texto selecionável."""

    def ler(self, caminho: Path) -> tuple[Pagina, ...]:
        """Devolve uma `Pagina` por página do PDF, numeradas a partir de 1.

        Levanta `ErroDocumento` se o arquivo não puder ser aberto, se não for um PDF
        legível, se não tiver páginas ou se nenhuma página tiver texto extraível.
        Páginas individualmente vazias (ex.: capa sem texto) são mantidas, para
        preservar a numeração.
        """
        textos = _extrair_textos(caminho)
        if not textos:
            raise ErroDocumento(f"PDF sem páginas: {caminho}")
        if not any(texto.strip() for texto in textos):
            raise ErroDocumento(f"PDF sem texto extraível: {caminho}")
        return tuple(
            Pagina(numero=numero, texto=texto)
            for numero, texto in enumerate(textos, start=PRIMEIRA_PAGINA)
        )


def _extrair_textos(caminho: Path) -> tuple[str, ...]:
    """Converte erros de arquivo e do pypdf em `ErroDocumento` (`from None`, sem traceback).

    O erro original vai para o log em DEBUG, sem conteúdo do documento.
    """
    try:
        with caminho.open("rb") as arquivo:
            leitor = PdfReader(arquivo)
            return tuple(pagina.extract_text() for pagina in leitor.pages)
    except FileNotFoundError:
        LOGGER.debug("Arquivo não encontrado: %s", caminho, exc_info=True)
        raise ErroDocumento(f"Arquivo inexistente: {caminho}") from None
    except OSError:
        LOGGER.debug("Falha de E/S ao abrir o arquivo: %s", caminho, exc_info=True)
        raise ErroDocumento(f"Não foi possível abrir o arquivo: {caminho}") from None
    except PyPdfError:
        LOGGER.debug("PDF rejeitado pelo pypdf: %s", caminho, exc_info=True)
        raise ErroDocumento(f"PDF corrompido ou ilegível: {caminho}") from None
    except ERROS_NAO_ENCAPSULADOS_DO_PYPDF:
        LOGGER.debug("Erro não encapsulado do pypdf: %s", caminho, exc_info=True)
        raise ErroDocumento(f"PDF corrompido ou ilegível: {caminho}") from None
