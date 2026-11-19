"""Exibição de erros da tela: aviso para o que o usuário pode corrigir, erro para o resto.

Mensagens do núcleo são escapadas antes de virarem Markdown. Exceções inesperadas vão ao log
só com a classe e o local da falha, nunca com a mensagem (ela pode trazer segredo).
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Final

import streamlit as st

from nucleo.erros import ConfiguracaoInvalida, ErroAssistente, PerguntaInvalida

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


MENSAGEM_CONFIGURACAO: Final[str] = (
    "Não foi possível iniciar o assistente por causa da configuração. "
    "Confira o arquivo .env na pasta do projeto e atualize a página."
)
MENSAGEM_SERVICO: Final[str] = (
    "Não foi possível responder agora. O serviço pode estar indisponível. "
    "Tente novamente em instantes."
)
MENSAGEM_INESPERADA: Final[str] = (
    "Ocorreu um erro inesperado. Tente novamente. Se o problema continuar, avise a equipe."
)

_CARACTERES_MARKDOWN: Final[dict[int, str]] = str.maketrans(
    {caractere: f"\\{caractere}" for caractere in "\\`*_{}[]()#+-.!|<>~$"}
)


def escapar_markdown(texto: str) -> str:
    """Impede que texto vindo do núcleo ou dos PDFs (títulos, códigos) vire formatação ou link.

    Usado só onde a página ainda usa Markdown: avisos (`st.warning`) e títulos de fonte.
    Limitação conhecida: o escape não impede o autolink de URL e e-mail do GFM (`http://`,
    `www.`, `fulano@...`). Ressalva aberta na M-59 do backlog. Não é tratada aqui.
    """
    return texto.translate(_CARACTERES_MARKDOWN)


def mostrar_erro(erro: ErroAssistente) -> None:
    """Traduz uma exceção esperada do domínio em aviso ou erro para o usuário."""
    if isinstance(erro, PerguntaInvalida):
        # A mensagem vem do núcleo e descreve a regra (vazia ou longa demais).
        st.warning(escapar_markdown(str(erro)))
    elif isinstance(erro, ConfiguracaoInvalida):
        st.error(MENSAGEM_CONFIGURACAO)
    else:
        st.error(MENSAGEM_SERVICO)


def local_da_falha(erro: BaseException) -> str:
    """Arquivo, linha e função de cada quadro do traceback, sem a mensagem da exceção."""
    quadros = traceback.extract_tb(erro.__traceback__)
    if not quadros:
        return "local desconhecido"
    return " | ".join(f"{quadro.filename}:{quadro.lineno} em {quadro.name}" for quadro in quadros)


def mostrar_erro_inesperado(erro: BaseException) -> None:
    """Registra no log a classe da exceção e o local da falha, e mostra só a mensagem genérica.

    A mensagem da exceção não é gravada: ela pode conter segredos (ex.: chave da API).
    Pelo mesmo motivo não há traceback no log, porque ele exibe a mensagem.
    """
    _LOG.error(
        "Erro inesperado na tela de perguntas: %s. Local: %s",
        type(erro).__name__,
        local_da_falha(erro),
    )
    st.error(MENSAGEM_INESPERADA)


def executar_com_tratamento[T](acao: Callable[[], T], mensagem_carregando: str) -> T | None:
    """Executa `acao` com indicador de progresso. Erros viram aviso ou erro e devolvem None."""
    try:
        with st.spinner(mensagem_carregando):
            return acao()
    except ErroAssistente as erro:
        mostrar_erro(erro)
    except Exception as erro:
        mostrar_erro_inesperado(erro)
    return None
