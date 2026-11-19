"""Casos de borda de `ProvedorEmbeddingOpenAI.gerar`, com cliente simulado e sem chamada à API."""

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
from nucleo.erros import ErroBusca

MODELO = "text-embedding-3-small"
CHAVE_FALSA = "sk-teste-robustez-nao-e-real-5678"
URL_FALSA = "https://api.exemplo.invalido/v1/embeddings"
CONTEUDO_SIGILOSO = "cláusula sigilosa do contrato de fornecimento"
TIMEOUT_TESTE_SEGUNDOS = 30.0


def _resposta(vetores: list[tuple[float, ...]], indices: list[int] | None = None) -> Any:
    """Imita `CreateEmbeddingResponse`. Por padrão, os índices são 0..n-1 na ordem dos vetores."""
    indices_usados = indices if indices is not None else list(range(len(vetores)))
    itens = [
        SimpleNamespace(index=indice, embedding=list(vetor))
        for indice, vetor in zip(indices_usados, vetores, strict=True)
    ]
    return SimpleNamespace(data=itens)


def _erro_status(classe: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    requisicao = httpx2.Request("POST", URL_FALSA)
    resposta = httpx2.Response(status, request=requisicao)
    return classe("falha simulada", response=resposta, body=None)


def _erro_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx2.Request("POST", URL_FALSA))


def _erro_servidor() -> openai.InternalServerError:
    erro = _erro_status(openai.InternalServerError, 503)
    assert isinstance(erro, openai.InternalServerError)
    return erro


def _erro_autenticacao() -> openai.AuthenticationError:
    erro = _erro_status(openai.AuthenticationError, 401)
    assert isinstance(erro, openai.AuthenticationError)
    return erro


class ClienteSimulado:
    """Dublê do `openai.OpenAI`: devolve ou levanta o próximo item do roteiro."""

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


def test_lote_com_um_so_texto_devolve_um_vetor() -> None:
    cliente = ClienteSimulado([_resposta([(0.3, 0.7)])])

    resultado = _provedor(cliente).gerar(["único"])

    assert resultado == ((0.3, 0.7),)
    assert cliente.lotes_enviados == [["único"]]


def test_erro_5xx_no_segundo_lote_e_retentado_sem_perder_a_ordem() -> None:
    cliente = ClienteSimulado(
        [
            _resposta([(0.0,), (1.0,)]),
            _erro_servidor(),
            _resposta([(2.0,)]),
        ]
    )
    esperas: list[float] = []
    provedor = _provedor(cliente, tamanho_lote=2, tentativas=3, esperas=esperas)

    resultado = provedor.gerar(["t0", "t1", "t2"])

    assert resultado == ((0.0,), (1.0,), (2.0,))
    assert cliente.lotes_enviados == [["t0", "t1"], ["t2"], ["t2"]]
    assert esperas == [1.0]


def test_autenticacao_recusada_no_segundo_lote_descarta_o_primeiro_e_nao_retenta() -> None:
    cliente = ClienteSimulado(
        [
            _resposta([(0.0,), (1.0,)]),
            _erro_autenticacao(),
            _resposta([(2.0,)]),
        ]
    )
    esperas: list[float] = []
    provedor = _provedor(cliente, tamanho_lote=2, esperas=esperas)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["t0", "t1", "t2"])

    assert str(info.value) == MENSAGEM_AUTENTICACAO
    assert cliente.chamadas == 2
    assert esperas == []


def test_timeout_e_tratado_como_erro_transitorio_e_retentado() -> None:
    cliente = ClienteSimulado([_erro_timeout(), _resposta([(0.9,)])])
    esperas: list[float] = []
    provedor = _provedor(cliente, tentativas=3, esperas=esperas)

    resultado = provedor.gerar(["texto"])

    assert resultado == ((0.9,),)
    assert cliente.chamadas == 2
    assert esperas == [1.0]


def test_timeout_repetido_esgota_as_tentativas_com_mensagem_transitoria() -> None:
    cliente = ClienteSimulado([_erro_timeout(), _erro_timeout()])
    provedor = _provedor(cliente, tentativas=2)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert str(info.value) == MENSAGEM_TRANSITORIA_ESGOTADA


def test_erro_de_autenticacao_nao_carrega_a_excecao_original_como_causa() -> None:
    cliente = ClienteSimulado([_erro_autenticacao()])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_erro_de_api_generico_vira_erro_busca_com_mensagem_fixa() -> None:
    erro_generico = openai.APIError(
        "detalhe da API que cita o conteúdo enviado",
        httpx2.Request("POST", URL_FALSA),
        body=None,
    )
    cliente = ClienteSimulado([erro_generico])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar(["texto"])

    assert str(info.value) == MENSAGEM_FALHA_API
    assert "detalhe da API" not in str(info.value)


def test_erro_de_autenticacao_nao_expoe_conteudo_nem_chave_no_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cliente = ClienteSimulado([_erro_autenticacao()])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca) as info:
        provedor.gerar([CONTEUDO_SIGILOSO])

    visivel = str(info.value) + caplog.text
    assert CHAVE_FALSA not in visivel
    assert CONTEUDO_SIGILOSO not in visivel


def test_indice_duplicado_na_resposta_vira_erro_busca() -> None:
    cliente = ClienteSimulado([_resposta([(1.0,), (2.0,)], indices=[0, 0])])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca):
        provedor.gerar(["a", "b"])


def test_lacuna_de_indices_na_resposta_vira_erro_busca() -> None:
    cliente = ClienteSimulado([_resposta([(1.0,), (2.0,)], indices=[0, 2])])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca):
        provedor.gerar(["a", "b"])


def test_indice_fora_do_intervalo_vira_erro_busca() -> None:
    cliente = ClienteSimulado([_resposta([(1.0,)], indices=[5])])
    provedor = _provedor(cliente)

    with pytest.raises(ErroBusca):
        provedor.gerar(["a"])
