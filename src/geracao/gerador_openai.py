"""Cliente da OpenAI que implementa `GeradorResposta`.

Erros do SDK viram `ErroGeracao` com mensagem fixa, sem a chave, o prompt ou a resposta bruta.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from geracao.prompts import PROMPT_SISTEMA, montar_conteudo_usuario
from geracao.validacao_resposta import validar_saida
from nucleo.erros import ConfiguracaoInvalida, ErroGeracao
from nucleo.modelos import Resposta, Trecho

logger = logging.getLogger(__name__)

MODELO_PADRAO = "gpt-4o-mini"
TEMPERATURA = 0.0

MENSAGEM_AUTENTICACAO = "Chave da OpenAI recusada. Verifique OPENAI_API_KEY no arquivo .env."
MENSAGEM_LIMITE_TAXA = (
    "A API de geração recusou a chamada por limite de taxa. Tente de novo em instantes."
)
MENSAGEM_TIMEOUT = "A API de geração não respondeu dentro do tempo limite."
MENSAGEM_CONEXAO = "Não foi possível conectar à API de geração."
MENSAGEM_FALHA_API = "A API de geração devolveu um erro ao gerar a resposta."
MENSAGEM_RESPOSTA_INCONSISTENTE = "A API de geração devolveu uma resposta sem conteúdo."


class GeradorOpenAI:
    """Gera a resposta com `gpt-4o-mini`, usando somente os trechos recebidos."""

    def __init__(
        self,
        *,
        chave: str,
        timeout_segundos: float,
        modelo: str = MODELO_PADRAO,
        cliente: openai.OpenAI | None = None,
    ) -> None:
        """`cliente` existe para testes. `max_retries=0` faz a falha chegar como `ErroGeracao`."""
        _validar_configuracao(chave, modelo, timeout_segundos)
        self._modelo = modelo
        self._cliente = (
            cliente
            if cliente is not None
            else openai.OpenAI(api_key=chave, max_retries=0, timeout=timeout_segundos)
        )

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        """Devolve a resposta do modelo. Sem trechos, devolve `sem_evidencia()` sem chamar a API."""
        if not trechos:
            return Resposta.sem_evidencia()
        mensagens = _montar_mensagens(pergunta, trechos)
        resposta = self._chamar_modelo(mensagens)
        return _interpretar(resposta, trechos)

    def _chamar_modelo(self, mensagens: list[ChatCompletionMessageParam]) -> ChatCompletion:
        """Converte falhas do SDK em `ErroGeracao`, levantado fora do `except`.

        Assim `__context__` não guarda a exceção do SDK, que carrega o cabeçalho `Authorization`.
        """
        falha: str
        try:
            return self._cliente.chat.completions.create(
                model=self._modelo,
                messages=mensagens,
                temperature=TEMPERATURA,
                response_format={"type": "json_object"},
            )
        except openai.AuthenticationError:
            falha = MENSAGEM_AUTENTICACAO
        except openai.RateLimitError:
            falha = MENSAGEM_LIMITE_TAXA
        except openai.APITimeoutError:
            falha = MENSAGEM_TIMEOUT
        except openai.APIConnectionError:
            falha = MENSAGEM_CONEXAO
        except openai.APIError:
            falha = MENSAGEM_FALHA_API
        logger.warning("Falha na chamada ao modelo de geração: %s", falha)
        raise ErroGeracao(falha) from None


def _montar_mensagens(pergunta: str, trechos: Sequence[Trecho]) -> list[ChatCompletionMessageParam]:
    return [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": montar_conteudo_usuario(pergunta, trechos)},
    ]


def _interpretar(resposta: ChatCompletion, trechos: Sequence[Trecho]) -> Resposta:
    if not resposta.choices:
        raise ErroGeracao(MENSAGEM_RESPOSTA_INCONSISTENTE) from None
    texto = (resposta.choices[0].message.content or "").strip()
    if not texto:
        return Resposta.sem_evidencia()
    return validar_saida(texto, trechos)


def _validar_configuracao(chave: str, modelo: str, timeout_segundos: float) -> None:
    if not chave.strip():
        raise ConfiguracaoInvalida("OPENAI_API_KEY está ausente.")
    if not modelo.strip():
        raise ConfiguracaoInvalida("O nome do modelo de geração está vazio.")
    if not (timeout_segundos > 0 and math.isfinite(timeout_segundos)):
        raise ConfiguracaoInvalida("O timeout das chamadas de geração deve ser positivo e finito.")
