"""Provedor de embeddings da OpenAI (HIST-009).

Implementa o contrato `ProvedorEmbedding`. Envia os textos em lotes e repete a chamada
com espera crescente quando o erro é transitório (limite de taxa, 5xx ou conexão).
Erros do SDK viram `ErroBusca`, sem a chave nem o conteúdo enviado na mensagem.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence

import openai
from openai.types import CreateEmbeddingResponse

from nucleo.erros import ConfiguracaoInvalida, ErroBusca
from nucleo.modelos import Vetor

logger = logging.getLogger(__name__)

TENTATIVAS_PADRAO = 3
ESPERA_BASE_PADRAO_SEGUNDOS = 1.0

_EXCECOES_TRANSITORIAS = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
)

MENSAGEM_AUTENTICACAO = "Chave da OpenAI recusada. Verifique OPENAI_API_KEY no arquivo .env."
MENSAGEM_TRANSITORIA_ESGOTADA = "A API de embeddings continua indisponível após as tentativas."
MENSAGEM_FALHA_API = "A API de embeddings devolveu um erro ao gerar os vetores."
MENSAGEM_RESPOSTA_INCONSISTENTE = (
    "A API de embeddings devolveu uma resposta inconsistente com os textos enviados."
)


class ProvedorEmbeddingOpenAI:
    """Gera embeddings com a API da OpenAI, em lotes, com retentativa para erros transitórios."""

    def __init__(
        self,
        *,
        modelo: str,
        chave: str,
        tamanho_lote: int,
        timeout_segundos: float,
        tentativas: int = TENTATIVAS_PADRAO,
        espera_base_segundos: float = ESPERA_BASE_PADRAO_SEGUNDOS,
        esperar: Callable[[float], None] = time.sleep,
        cliente: openai.OpenAI | None = None,
    ) -> None:
        """`cliente` existe para testes. Em produção, o cliente é criado com `chave`.

        `timeout_segundos` vem da composição (`Configuracao.timeout_segundos`).
        `max_retries=0` desliga a retentativa interna do SDK, para que `tentativas`
        seja o número real de chamadas.
        """
        _validar_configuracao(modelo, chave, tamanho_lote, tentativas, timeout_segundos)
        self._modelo = modelo
        self._tamanho_lote = tamanho_lote
        self._tentativas = tentativas
        self._espera_base_segundos = espera_base_segundos
        self._esperar = esperar
        self._cliente = (
            cliente
            if cliente is not None
            else openai.OpenAI(api_key=chave, max_retries=0, timeout=timeout_segundos)
        )

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        """Devolve um vetor por texto, na mesma ordem. Lista vazia devolve `()` sem chamar a API."""
        if not textos:
            return ()
        vetores: list[Vetor] = []
        for inicio in range(0, len(textos), self._tamanho_lote):
            lote = list(textos[inicio : inicio + self._tamanho_lote])
            vetores.extend(self._gerar_lote(lote))
        return tuple(vetores)

    def _gerar_lote(self, lote: list[str]) -> list[Vetor]:
        resposta = self._chamar_api(lote)
        indices = sorted(item.index for item in resposta.data)
        if indices != list(range(len(lote))):
            raise ErroBusca(MENSAGEM_RESPOSTA_INCONSISTENTE)
        itens = sorted(resposta.data, key=lambda item: item.index)
        return [tuple(float(valor) for valor in item.embedding) for item in itens]

    def _chamar_api(self, lote: list[str]) -> CreateEmbeddingResponse:
        """Chama a API com retentativa. Converte falhas fora dos blocos `except`.

        `ErroBusca` é levantado depois do `try`, para que `__context__` não guarde a
        exceção do SDK (que carrega a requisição com o cabeçalho `Authorization`).
        """
        for tentativa in range(1, self._tentativas + 1):
            try:
                return self._cliente.embeddings.create(model=self._modelo, input=lote)
            except openai.AuthenticationError:
                falha = MENSAGEM_AUTENTICACAO
            except _EXCECOES_TRANSITORIAS:
                if tentativa < self._tentativas:
                    self._aguardar_retentativa(tentativa)
                    continue
                falha = MENSAGEM_TRANSITORIA_ESGOTADA
            except openai.APIError:
                falha = MENSAGEM_FALHA_API
            raise ErroBusca(falha)
        raise ErroBusca(MENSAGEM_TRANSITORIA_ESGOTADA)

    def _aguardar_retentativa(self, tentativa: int) -> None:
        espera_segundos = self._espera_base_segundos * 2 ** (tentativa - 1)
        logger.warning(
            "Erro transitório na API de embeddings; nova tentativa em %.1fs (%d de %d).",
            espera_segundos,
            tentativa + 1,
            self._tentativas,
        )
        self._esperar(espera_segundos)


def _validar_configuracao(
    modelo: str, chave: str, tamanho_lote: int, tentativas: int, timeout_segundos: float
) -> None:
    if not modelo.strip():
        raise ConfiguracaoInvalida("O nome do modelo de embedding está vazio.")
    if not chave.strip():
        raise ConfiguracaoInvalida("OPENAI_API_KEY está ausente.")
    if tamanho_lote < 1:
        raise ConfiguracaoInvalida("O tamanho do lote de embeddings deve ser pelo menos 1.")
    if tentativas < 1:
        raise ConfiguracaoInvalida("O número de tentativas de embeddings deve ser pelo menos 1.")
    if not timeout_segundos > 0:
        raise ConfiguracaoInvalida("O timeout das chamadas de embedding deve ser positivo.")
