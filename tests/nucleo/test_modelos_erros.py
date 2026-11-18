"""Testes dos modelos e da hierarquia de erros do núcleo (HIST-003)."""

import dataclasses

import pytest

from nucleo.erros import (
    ConfiguracaoInvalida,
    ErroAssistente,
    ErroBusca,
    ErroDocumento,
    ErroGeracao,
    PerguntaInvalida,
)
from nucleo.modelos import MENSAGEM_SEM_EVIDENCIA, Fonte, Resposta, Secao


def _secao() -> Secao:
    return Secao(
        documento="FIN-POL-001",
        numero="6.1",
        titulo="Exemplo de contagem do prazo",
        texto="Sábado, domingo e feriados não são considerados dias úteis.",
    )


def test_resposta_sem_evidencia_usa_mensagem_padrao_e_nao_cita_fontes() -> None:
    resposta = Resposta.sem_evidencia()

    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta.fontes == ()
    assert resposta.evidencia_suficiente is False


def test_fonte_de_secao_copia_documento_numero_e_titulo() -> None:
    fonte = Fonte.de_secao(_secao())

    assert fonte == Fonte(
        documento="FIN-POL-001",
        secao="6.1",
        titulo="Exemplo de contagem do prazo",
    )


def test_secao_e_imutavel() -> None:
    secao = _secao()

    with pytest.raises(dataclasses.FrozenInstanceError):
        secao.texto = "alterado"  # type: ignore[misc]


@pytest.mark.parametrize(
    "erro",
    [ErroDocumento, ErroBusca, ErroGeracao, ConfiguracaoInvalida, PerguntaInvalida],
)
def test_todos_os_erros_herdam_de_erro_assistente(erro: type[ErroAssistente]) -> None:
    assert issubclass(erro, ErroAssistente)
