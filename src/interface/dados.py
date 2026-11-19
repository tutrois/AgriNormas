"""Acesso aos dados da tela (assistente, lista e conteúdo dos documentos), com cache.

Erros não ficam em cache e viram `None` ou são propagados para `tratamento`. Usa `composicao`
pelo módulo, e não pelo nome, para que a troca feita em testes valha a cada execução da página.
"""

from __future__ import annotations

import logging
from typing import Final

import streamlit as st

import composicao
from nucleo.assistente import AssistenteRAG
from nucleo.modelos import ConteudoDoDocumento, DocumentoDaBase

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


@st.cache_resource(show_spinner=False)
def obter_assistente() -> AssistenteRAG:
    """Monta o assistente uma vez por processo. Erros não ficam em cache e são tentados de novo."""
    return composicao.montar_assistente_do_ambiente()


@st.cache_data(show_spinner=False)
def documentos_da_base() -> tuple[DocumentoDaBase, ...]:
    """Lê a lista de documentos uma vez por processo. Erros não ficam em cache."""
    return composicao.listar_documentos_do_ambiente()


class _DocumentoIndisponivel(Exception):
    """Interna: faz o `st.cache_data` não guardar o resultado vazio (exceção não entra no cache)."""


@st.cache_data(show_spinner=False)
def conteudo_do_documento(arquivo: str) -> ConteudoDoDocumento:
    """Lê um documento uma vez por arquivo. Indisponível (None) e erros não ficam em cache."""
    conteudo = composicao.ler_documento_do_ambiente(arquivo)
    if conteudo is None:
        raise _DocumentoIndisponivel
    return conteudo


def conteudo_ou_none(arquivo: str) -> ConteudoDoDocumento | None:
    """Conteúdo para a tela. Qualquer falha vira None e não derruba a página."""
    try:
        return conteudo_do_documento(arquivo)
    except _DocumentoIndisponivel:
        return None
    except Exception as erro:
        # Só a classe vai ao log: a mensagem pode conter caminho ou segredo.
        _LOG.warning("Não foi possível ler o documento: %s", type(erro).__name__)
        return None


def documentos_ou_none() -> tuple[DocumentoDaBase, ...] | None:
    """Lista da base para as telas da base. Qualquer falha vira None e não derruba a página."""
    try:
        return documentos_da_base()
    except Exception as erro:
        # Só a classe vai ao log: a mensagem pode conter caminho ou segredo.
        _LOG.warning("Não foi possível listar os documentos: %s", type(erro).__name__)
        return None
