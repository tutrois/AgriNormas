"""Testes do cliente de geração da OpenAI (HIST-013).

Usam cliente simulado: nenhuma chamada real à API. As exceções são as do SDK `openai`,
construídas com respostas `httpx2` falsas, para que a conversão seja testada de verdade.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast

import httpx2
import openai
import pytest

from geracao.gerador_openai import (
    MENSAGEM_AUTENTICACAO,
    MENSAGEM_CONEXAO,
    MENSAGEM_FALHA_API,
    MENSAGEM_LIMITE_TAXA,
    MENSAGEM_TIMEOUT,
    MODELO_PADRAO,
    GeradorOpenAI,
)
from nucleo.erros import ConfiguracaoInvalida, ErroGeracao
from nucleo.modelos import Resposta, Secao, Trecho

CHAVE_FALSA = "sk-teste-nao-e-uma-chave-real-1234"
TIMEOUT_TESTE_SEGUNDOS = 30.0
URL_FALSA = "https://api.exemplo.invalido/v1/chat/completions"
PERGUNTA = "Qual o prazo de reembolso de despesas?"
TEXTO_TRECHO = "O reembolso é pago em até 30 dias após a aprovação."


def _trecho() -> Trecho:
    secao = Secao(
        documento="FIN-POL-001",
        numero="6",
        titulo="Reembolso",
        texto=TEXTO_TRECHO,
    )
    return Trecho(secao=secao, pontuacao=0.8)


def _resposta_chat(conteudo: str | None, escolhas: int = 1) -> Any:
    """Imita `ChatCompletion`: `choices[0].message.content`."""
    escolha = SimpleNamespace(message=SimpleNamespace(content=conteudo))
    return SimpleNamespace(choices=[escolha] * escolhas)


def _erro_status(classe: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    requisicao = httpx2.Request("POST", URL_FALSA)
    resposta = httpx2.Response(status, request=requisicao)
    return classe("falha simulada", response=resposta, body=None)


def _erro_autenticacao(cabecalho: dict[str, str] | None = None) -> openai.AuthenticationError:
    requisicao = httpx2.Request("POST", URL_FALSA, headers=cabecalho or {})
    resposta = httpx2.Response(401, request=requisicao)
    return openai.AuthenticationError("falha simulada", response=resposta, body=None)


def _erro_limite_taxa() -> openai.RateLimitError:
    erro = _erro_status(openai.RateLimitError, 429)
    assert isinstance(erro, openai.RateLimitError)
    return erro


def _erro_conexao() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx2.Request("POST", URL_FALSA))


def _erro_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx2.Request("POST", URL_FALSA))


class ClienteSimulado:
    """Dublê do `openai.OpenAI`: devolve ou levanta o próximo item do roteiro.

    Registra as chamadas, para verificar se a API foi chamada e com quais argumentos.
    """

    def __init__(self, roteiro: list[Any] | None = None) -> None:
        self._roteiro = list(roteiro or [])
        self.chamadas: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **argumentos: Any) -> Any:
        self.chamadas.append(argumentos)
        item = self._roteiro.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def quantidade_chamadas(self) -> int:
        return len(self.chamadas)


def _gerador(cliente: ClienteSimulado) -> GeradorOpenAI:
    return GeradorOpenAI(
        chave=CHAVE_FALSA,
        timeout_segundos=TIMEOUT_TESTE_SEGUNDOS,
        cliente=cast(openai.OpenAI, cliente),
    )


def test_resposta_valida_vira_resposta_do_contrato() -> None:
    cliente = ClienteSimulado([_resposta_chat("  O prazo é de 30 dias. [FIN-POL-001 §6]  ")])

    resposta = _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert isinstance(resposta, Resposta)
    assert resposta.texto == "O prazo é de 30 dias. [FIN-POL-001 §6]"
    assert resposta.evidencia_suficiente is True
    assert cliente.quantidade_chamadas == 1


def test_chamada_usa_modelo_padrao_temperatura_zero_e_trechos_identificados() -> None:
    cliente = ClienteSimulado([_resposta_chat("Resposta.")])

    _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    chamada = cliente.chamadas[0]
    assert chamada["model"] == MODELO_PADRAO == "gpt-4o-mini"
    assert chamada["temperature"] == 0.0
    conteudo_usuario = chamada["messages"][1]["content"]
    assert "[FIN-POL-001 §6]" in conteudo_usuario
    assert TEXTO_TRECHO in conteudo_usuario
    assert PERGUNTA in conteudo_usuario


def test_conteudo_vazio_do_modelo_devolve_sem_evidencia() -> None:
    cliente = ClienteSimulado([_resposta_chat("   ")])

    assert _gerador(cliente).gerar(PERGUNTA, [_trecho()]) == Resposta.sem_evidencia()


def test_resposta_sem_escolhas_vira_erro_de_geracao() -> None:
    cliente = ClienteSimulado([_resposta_chat("x", escolhas=0)])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert str(info.value) == "A API de geração devolveu uma resposta sem conteúdo."


def test_erro_de_conexao_vira_erro_de_geracao() -> None:
    cliente = ClienteSimulado([_erro_conexao()])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert str(info.value) == MENSAGEM_CONEXAO
    assert cliente.quantidade_chamadas == 1


def test_erro_de_timeout_vira_erro_de_geracao_com_mensagem_propria() -> None:
    cliente = ClienteSimulado([_erro_timeout()])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert str(info.value) == MENSAGEM_TIMEOUT


def test_erro_de_autenticacao_vira_erro_de_geracao_sem_a_chave() -> None:
    cliente = ClienteSimulado([_erro_autenticacao({"Authorization": f"Bearer {CHAVE_FALSA}"})])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert str(info.value) == MENSAGEM_AUTENTICACAO
    assert CHAVE_FALSA not in str(info.value)
    assert CHAVE_FALSA not in repr(info.value)


def test_limite_de_taxa_vira_erro_de_geracao_sem_a_chave_nem_o_prompt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cliente = ClienteSimulado([_erro_limite_taxa()])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    visivel = str(info.value) + caplog.text
    assert str(info.value) == MENSAGEM_LIMITE_TAXA
    assert CHAVE_FALSA not in visivel
    assert PERGUNTA not in visivel
    assert TEXTO_TRECHO not in visivel


def test_erro_do_sdk_sem_categoria_propria_vira_falha_generica() -> None:
    cliente = ClienteSimulado([_erro_status(openai.BadRequestError, 400)])

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert str(info.value) == MENSAGEM_FALHA_API


def test_erro_de_autenticacao_nao_guarda_contexto_com_o_cabecalho_authorization() -> None:
    chave_sem_prefixo = "chave-falsa-para-teste"
    cliente = ClienteSimulado(
        [_erro_autenticacao({"Authorization": f"Bearer {chave_sem_prefixo}"})]
    )

    with pytest.raises(ErroGeracao) as info:
        _gerador(cliente).gerar(PERGUNTA, [_trecho()])

    assert info.value.__context__ is None
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True
    assert chave_sem_prefixo not in str(info.value)


def test_trechos_vazios_devolvem_sem_evidencia_sem_chamar_o_cliente() -> None:
    cliente = ClienteSimulado([])

    resposta = _gerador(cliente).gerar(PERGUNTA, [])

    assert resposta == Resposta.sem_evidencia()
    assert cliente.quantidade_chamadas == 0


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_timeout_invalido_e_erro_de_configuracao(timeout: float) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        GeradorOpenAI(chave=CHAVE_FALSA, timeout_segundos=timeout)


def test_chave_vazia_e_erro_de_configuracao_sem_mostrar_valor() -> None:
    with pytest.raises(ConfiguracaoInvalida) as info:
        GeradorOpenAI(chave="   ", timeout_segundos=TIMEOUT_TESTE_SEGUNDOS)

    assert "OPENAI_API_KEY" in str(info.value)


def test_modelo_vazio_e_erro_de_configuracao() -> None:
    with pytest.raises(ConfiguracaoInvalida):
        GeradorOpenAI(chave=CHAVE_FALSA, timeout_segundos=TIMEOUT_TESTE_SEGUNDOS, modelo=" ")


def test_cliente_criado_sem_retentativa_interna_e_com_timeout_recebido() -> None:
    gerador = GeradorOpenAI(chave=CHAVE_FALSA, timeout_segundos=7.5)

    assert gerador._cliente.max_retries == 0
    assert gerador._cliente.timeout == 7.5
    assert CHAVE_FALSA not in repr(gerador)
