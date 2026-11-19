"""Reescrita da pergunta em formulações alternativas, com o modelo de linguagem (HIST-029, ADR-010).

Implementa o contrato `ReescritorConsulta`, com o mesmo modelo, temperatura 0, `max_retries=0`
e timeout explícito do `GeradorOpenAI`. A saída é um objeto JSON com a lista de formulações.
Ela passa por validação de formato e pela seleção (descarta vazias, repetidas e a própria
pergunta), e nunca é usada como instrução: é só texto de busca.

Falhas de API ou de formato viram `ErroReescrita`, com mensagem fixa, sem a pergunta, sem a
chave, sem o prompt e sem a resposta bruta.
"""

from __future__ import annotations

import json
import logging
import math
from typing import cast

import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from geracao.gerador_openai import MODELO_PADRAO, TEMPERATURA
from geracao.prompts import (
    CAMPO_FORMULACOES,
    montar_conteudo_reescrita,
    montar_prompt_reescrita,
)
from nucleo.erros import ConfiguracaoInvalida, ErroReescrita

logger = logging.getLogger(__name__)

NUMERO_FORMULACOES_PADRAO = 3

MENSAGEM_REESCRITA_FALHA_API = "A API de geração não conseguiu reescrever a pergunta."
MENSAGEM_REESCRITA_FORMATO = "A reescrita da pergunta veio fora do formato esperado."
MODELO_LOG_FALHA = "Falha na reescrita da pergunta: %s."


class ReescritorOpenAI:
    """Propõe até `numero_formulacoes` formulações da pergunta, com `gpt-4o-mini`."""

    def __init__(
        self,
        *,
        chave: str,
        timeout_segundos: float,
        numero_formulacoes: int = NUMERO_FORMULACOES_PADRAO,
        modelo: str = MODELO_PADRAO,
        cliente: openai.OpenAI | None = None,
    ) -> None:
        """`cliente` existe para testes. Em produção, o cliente é criado com `chave`.

        `numero_formulacoes` é N do contrato: o teto de formulações devolvidas. Com N=0 o
        reescritor devolve `()` sem chamar o modelo.
        """
        _validar_configuracao(chave, modelo, timeout_segundos, numero_formulacoes)
        self._modelo = modelo
        self._numero = numero_formulacoes
        self._prompt_sistema = montar_prompt_reescrita(numero_formulacoes)
        self._cliente = (
            cliente
            if cliente is not None
            else openai.OpenAI(api_key=chave, max_retries=0, timeout=timeout_segundos)
        )

    def reescrever(self, pergunta: str) -> tuple[str, ...]:
        """Devolve até N formulações, sem a original, sem repetição e sem textos vazios.

        Pergunta vazia ou só com espaços, e N=0, devolvem `()` sem chamar a API (ADR-007).
        """
        if self._numero == 0 or not pergunta.strip():
            return ()
        resposta = self._chamar_modelo(pergunta)
        sugeridas = _ler_formulacoes(resposta)
        return _selecionar(sugeridas, pergunta, self._numero)

    def _chamar_modelo(self, pergunta: str) -> ChatCompletion:
        """Chama a API e converte falhas do SDK em `ErroReescrita`.

        O `ErroReescrita` é levantado depois do `try`, para que `__context__` não guarde a
        exceção do SDK (que carrega a requisição com o cabeçalho `Authorization`).
        """
        mensagens: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._prompt_sistema},
            {"role": "user", "content": montar_conteudo_reescrita(pergunta)},
        ]
        falha: str
        try:
            return self._cliente.chat.completions.create(
                model=self._modelo,
                messages=mensagens,
                temperature=TEMPERATURA,
                response_format={"type": "json_object"},
            )
        except openai.OpenAIError:
            falha = MENSAGEM_REESCRITA_FALHA_API
        logger.warning(MODELO_LOG_FALHA, falha)
        raise ErroReescrita(falha) from None


def _ler_formulacoes(resposta: ChatCompletion) -> list[str]:
    """Confere a forma do JSON: objeto com o campo de formulações, cujos itens são textos.

    `RecursionError` é tratado como JSON inválido, pelo mesmo motivo de `validacao_resposta`.
    O `raise` fica fora do `except`, para que o erro do parser não fique em `__context__`.
    """
    if not resposta.choices:
        raise ErroReescrita(MENSAGEM_REESCRITA_FORMATO) from None
    conteudo = resposta.choices[0].message.content or ""

    dados: object
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError, RecursionError:
        dados = None
    if not isinstance(dados, dict):
        raise ErroReescrita(MENSAGEM_REESCRITA_FORMATO) from None

    formulacoes = dados.get(CAMPO_FORMULACOES)
    if not _lista_de_textos(formulacoes):
        raise ErroReescrita(MENSAGEM_REESCRITA_FORMATO) from None
    return cast(list[str], formulacoes)


def _lista_de_textos(valor: object) -> bool:
    return isinstance(valor, list) and all(isinstance(item, str) for item in valor)


def _selecionar(sugeridas: list[str], pergunta: str, limite: int) -> tuple[str, ...]:
    """Mantém a ordem do modelo, descarta vazias, repetidas e a original, e corta em `limite`.

    A comparação ignora caixa e espaços nas bordas. A original entra no conjunto de vistas,
    então uma formulação igual a ela nunca é devolvida.
    """
    vistas: set[str] = {_chave_de_comparacao(pergunta)}
    escolhidas: list[str] = []
    for sugerida in sugeridas:
        if len(escolhidas) == limite:
            break
        texto = sugerida.strip()
        chave = _chave_de_comparacao(texto)
        if not chave or chave in vistas:
            continue
        vistas.add(chave)
        escolhidas.append(texto)
    return tuple(escolhidas)


def _chave_de_comparacao(texto: str) -> str:
    return texto.strip().casefold()


def _validar_configuracao(
    chave: str, modelo: str, timeout_segundos: float, numero_formulacoes: int
) -> None:
    if not chave.strip():
        raise ConfiguracaoInvalida("OPENAI_API_KEY está ausente.")
    if not modelo.strip():
        raise ConfiguracaoInvalida("O nome do modelo de geração está vazio.")
    if not (timeout_segundos > 0 and math.isfinite(timeout_segundos)):
        raise ConfiguracaoInvalida("O timeout das chamadas de geração deve ser positivo e finito.")
    if numero_formulacoes < 0:
        raise ConfiguracaoInvalida("O número de formulações da reescrita não pode ser negativo.")
