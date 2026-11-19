"""Testes do provedor de embeddings da OpenAI, com cliente simulado.

As exceções são as do SDK `openai`, construídas com respostas `httpx2` falsas, para testar a
conversão de verdade.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast

import httpx2
import openai
import pytest

from busca.provedor_openai import (
    MENSAGEM_AUTENTICACAO,
    MENSAGEM_FALHA_API,
    MENSAGEM_TRANSITORIA_ESGOTADA,
    ProvedorEmbeddingOpenAI,
)
from nucleo.erros import ConfiguracaoInvalida, ErroBusca
from nucleo.modelos import Vetor

MODELO = "text-embedding-3-small"
CHAVE_FALSA = "sk-teste-nao-e-uma-chave-real-1234"
TIMEOUT_TESTE_SEGUNDOS = 30.0
URL_FALSA = "https://api.exemplo.invalido/v1/embeddings"


def _resposta_embeddings(vetores: list[Vetor], ordem: list[int] | None = None) -> Any:
    """Imita `CreateEmbeddingResponse`: `data` com `index` e `embedding`."""
    indices = ordem if ordem is not None else list(range(len(vetores)))
    itens = [SimpleNamespace(index=indice, embedding=list(vetores[indice])) for indice in indices]
    return SimpleNamespace(data=itens)


def _erro_status(classe: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    requisicao = httpx2.Request("POST", URL_FALSA)
    resposta = httpx2.Response(status, request=requisicao)
    return classe("falha simulada", response=resposta, body=None)


def _erro_autenticacao() -> openai.AuthenticationError:
    erro = _erro_status(openai.AuthenticationError, 401)
    assert isinstance(erro, openai.AuthenticationError)
    return erro


def _erro_limite_taxa() -> openai.RateLimitError:
    erro = _erro_status(openai.RateLimitError, 429)
    assert isinstance(erro, openai.RateLimitError)
    return erro


def _erro_servidor() -> openai.InternalServerError:
    erro = _erro_status(openai.InternalServerError, 500)
    assert isinstance(erro, openai.InternalServerError)
    return erro


def _erro_conexao() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx2.Request("POST", URL_FALSA))


class ClienteSimulado:
    """Dublê do `openai.OpenAI`: devolve ou levanta o próximo item do roteiro; registra os lotes."""

    def __init__(self, roteiro: list[Any]) -> None:
        self._roteiro = list(roteiro)
        self.lotes_enviados: list[list[str]] = []
        self.embeddings = self

    def create(self, *, model: str, input: list[str]) -> Any:
        self.lotes_enviados.append(list(input))
        item = self._roteiro.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def chamadas(self) -> int:
        return len(self.lotes_enviados)


def _provedor(
    cliente: ClienteSimulado,
    *,
    tamanho_lote: int = 100,
    tentativas: int = 3,
    esperas: list[float] | None = None,
) -> ProvedorEmbeddingOpenAI:
    registro = esperas if esperas is not None else []
    return ProvedorEmbeddingOpenAI(
        modelo=MODELO,
        chave=CHAVE_FALSA,
        tamanho_lote=tamanho_lote,
        timeout_segundos=TIMEOUT_TESTE_SEGUNDOS,
        tentativas=tentativas,
        espera_base_segundos=1.0,
        esperar=registro.append,
        cliente=cast(openai.OpenAI, cliente),
    )


def test_devolve_um_vetor_por_texto_na_mesma_ordem() -> None:
    vetores = [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)]
    cliente = ClienteSimulado([_resposta_embeddings(vetores)])
    provedor = _provedor(cliente)

    resultado = provedor.gerar(["primeiro", "segundo", "terceiro"])

    assert resultado == tuple(vetores)
    assert cliente.lotes_enviados == [["primeiro", "segundo", "terceiro"]]


def test_reordena_pelo_indice_quando_a_api_devolve_fora_de_ordem() -> None:
    vetores = [(1.0, 0.0), (0.0, 1.0)]
    cliente = ClienteSimulado([_resposta_embeddings(vetores, ordem=[1, 0])])
    provedor = _provedor(cliente)

    assert provedor.gerar(["a", "b"]) == ((1.0, 0.0), (0.0, 1.0))


def test_envia_em_lotes_e_preserva_a_ordem_entre_lotes() -> None:
    textos = ["t0", "t1", "t2", "t3", "t4"]
    lote_1 = [(0.0,), (1.0,)]
    lote_2 = [(2.0,), (3.0,)]
    lote_3 = [(4.0,)]
    cliente = ClienteSimulado(
        [
            _resposta_embeddings(lote_1),
            _resposta_embeddings(lote_2),
            _resposta_embeddings(lote_3),
        ]
    )
    provedor = _provedor(cliente, tamanho_lote=2)

    resultado = provedor.gerar(textos)

    assert cliente.lotes_enviados == [["t0", "t1"], ["t2", "t3"], ["t4"]]
    assert resultado == ((0.0,), (1.0,), (2.0,), (3.0,), (4.0,))


def test_lista_vazia_devolve_tupla_vazia_sem_chamar_a_api() -> None:
    cliente = ClienteSimulado([])
    provedor = _provedor(cliente)

    assert provedor.gerar([]) == ()
    assert cliente.chamadas == 0


def test_erro_de_autenticacao_vira_erro_busca_sem_a_chave() -> None:
    cliente = ClienteSimulado([_erro_autenticacao()])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["pergunta sobre reembolso"])

    mensagem = str(info.value)
    assert mensagem == MENSAGEM_AUTENTICACAO
    assert CHAVE_FALSA not in mensagem
    assert "pergunta sobre reembolso" not in mensagem
    assert cliente.chamadas == 1


def test_erro_de_autenticacao_nao_e_retentado() -> None:
    cliente = ClienteSimulado([_erro_autenticacao(), _resposta_embeddings([(1.0,)])])
    esperas: list[float] = []
    provedor = _provedor(cliente, esperas=esperas)

    with pytest.raises(ErroBusca):
        provedor.gerar(["x"])

    assert cliente.chamadas == 1
    assert esperas == []


def test_erro_transitorio_e_retentado_e_depois_tem_sucesso() -> None:
    cliente = ClienteSimulado(
        [_erro_limite_taxa(), _erro_servidor(), _resposta_embeddings([(0.5, 0.5)])]
    )
    esperas: list[float] = []
    provedor = _provedor(cliente, tentativas=3, esperas=esperas)

    resultado = provedor.gerar(["texto"])

    assert resultado == ((0.5, 0.5),)
    assert cliente.chamadas == 3
    assert esperas == [1.0, 2.0]


def test_espera_cresce_a_cada_tentativa_transitoria() -> None:
    cliente = ClienteSimulado(
        [_erro_conexao(), _erro_conexao(), _erro_conexao(), _resposta_embeddings([(1.0,)])]
    )
    esperas: list[float] = []
    provedor = _provedor(cliente, tentativas=4, esperas=esperas)

    provedor.gerar(["texto"])

    assert esperas == [1.0, 2.0, 4.0]


def test_erro_transitorio_que_esgota_as_tentativas_vira_erro_busca() -> None:
    cliente = ClienteSimulado([_erro_limite_taxa(), _erro_servidor(), _erro_conexao()])
    esperas: list[float] = []
    provedor = _provedor(cliente, tentativas=3, esperas=esperas)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert str(info.value) == MENSAGEM_TRANSITORIA_ESGOTADA
    assert cliente.chamadas == 3
    assert esperas == [1.0, 2.0]


def test_erro_do_sdk_nao_transitorio_vira_erro_busca_sem_retentar() -> None:
    cliente = ClienteSimulado([_erro_status(openai.BadRequestError, 400)])
    esperas: list[float] = []
    provedor = _provedor(cliente, esperas=esperas)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert cliente.chamadas == 1
    assert esperas == []
    assert str(info.value) == MENSAGEM_FALHA_API


def test_resposta_com_menos_vetores_que_textos_vira_erro_busca() -> None:
    cliente = ClienteSimulado([_resposta_embeddings([(1.0,)])])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca):
        provedor.gerar(["a", "b"])


def test_mensagens_de_erro_nao_vazam_a_chave_nem_o_conteudo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    cliente = ClienteSimulado([_erro_limite_taxa(), _erro_limite_taxa(), _erro_limite_taxa()])
    provedor = _provedor(cliente, tentativas=3)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["conteudo confidencial do contrato"])

    texto_visivel = str(info.value) + caplog.text
    assert CHAVE_FALSA not in texto_visivel
    assert "conteudo confidencial" not in texto_visivel


@pytest.mark.parametrize("tamanho_lote", [0, -1])
def test_tamanho_de_lote_invalido_e_erro_de_configuracao(tamanho_lote: int) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        ProvedorEmbeddingOpenAI(
            modelo=MODELO,
            chave=CHAVE_FALSA,
            tamanho_lote=tamanho_lote,
            timeout_segundos=TIMEOUT_TESTE_SEGUNDOS,
            cliente=cast(openai.OpenAI, ClienteSimulado([])),
        )


def test_tentativas_invalidas_sao_erro_de_configuracao() -> None:
    with pytest.raises(ConfiguracaoInvalida):
        ProvedorEmbeddingOpenAI(
            modelo=MODELO,
            chave=CHAVE_FALSA,
            tamanho_lote=10,
            timeout_segundos=TIMEOUT_TESTE_SEGUNDOS,
            tentativas=0,
            cliente=cast(openai.OpenAI, ClienteSimulado([])),
        )


def test_chave_vazia_e_erro_de_configuracao_sem_mostrar_valor() -> None:
    with pytest.raises(ConfiguracaoInvalida) as info:
        ProvedorEmbeddingOpenAI(
            modelo=MODELO, chave="   ", tamanho_lote=10, timeout_segundos=TIMEOUT_TESTE_SEGUNDOS
        )

    assert "OPENAI_API_KEY" in str(info.value)


def test_cliente_criado_sem_retentativa_interna_do_sdk() -> None:
    provedor = ProvedorEmbeddingOpenAI(
        modelo=MODELO, chave=CHAVE_FALSA, tamanho_lote=10, timeout_segundos=TIMEOUT_TESTE_SEGUNDOS
    )

    assert provedor._cliente.max_retries == 0
    assert CHAVE_FALSA not in repr(provedor)


def test_timeout_recebido_da_composicao_vai_ao_cliente_do_sdk() -> None:
    provedor = ProvedorEmbeddingOpenAI(
        modelo=MODELO, chave=CHAVE_FALSA, tamanho_lote=10, timeout_segundos=7.5
    )

    assert provedor._cliente.timeout == 7.5


@pytest.mark.parametrize("timeout", [0.0, -1.0])
def test_timeout_nao_positivo_e_erro_de_configuracao(timeout: float) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        ProvedorEmbeddingOpenAI(
            modelo=MODELO, chave=CHAVE_FALSA, tamanho_lote=10, timeout_segundos=timeout
        )


def test_erro_de_autenticacao_nao_guarda_contexto_com_o_cabecalho_authorization() -> None:
    chave_falsa_sem_prefixo = "chave-falsa-para-teste"
    requisicao = httpx2.Request(
        "POST",
        URL_FALSA,
        headers={"Authorization": f"Bearer {chave_falsa_sem_prefixo}"},
    )
    resposta = httpx2.Response(401, request=requisicao)
    erro_sdk = openai.AuthenticationError("falha simulada", response=resposta, body=None)
    cliente = ClienteSimulado([erro_sdk])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert info.value.__context__ is None
    assert info.value.__cause__ is None
    assert chave_falsa_sem_prefixo not in str(info.value)
