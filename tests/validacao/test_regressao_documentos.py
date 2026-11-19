"""Regressão de integração: perguntas sobre documentos necessários e perguntas fora da base.

Origem: "Quais documentos preciso para solicitar reembolso" era recusada e "Quais documentos
preciso para solicitar férias?" recebia uma frase de ausência inventada. A correção trocou o
limiar por um piso de cosseno 0,40 com TOP_K 8 (ADR-011), passou o prompt para 1.9 e fez o
validador recusar texto sem citação e ausência sem sustentação nos trechos citados.

Estas perguntas não fazem parte de `perguntas.md` (a tabela do `po` com as sete perguntas de
aceite). São casos de regressão do `tester`, por isso o texto fica neste arquivo.

Todos os testes usam a composição real (`montar_assistente_do_ambiente` e `responder`) e só rodam
com `pytest -m integracao`, com a chave do `.env`.
"""

from __future__ import annotations

import pytest

import composicao
from nucleo.modelos import Resposta

PERGUNTA_DOCUMENTOS_REEMBOLSO = "Quais documentos preciso para solicitar reembolso"
PERGUNTA_DOCUMENTOS_FERIAS = "Quais documentos preciso para solicitar férias?"
PERGUNTAS_FORA_DA_BASE: tuple[str, ...] = (
    "Qual a política de home office da empresa?",
    "Quantos dias de licença maternidade eu tenho?",
    "Qual é o horário de funcionamento do refeitório?",
    "Qual é a capital da França?",
)

pytestmark = pytest.mark.integracao


@pytest.fixture(scope="module")
def respostas() -> dict[str, Resposta]:
    assistente = composicao.montar_assistente_do_ambiente()
    perguntas = (PERGUNTA_DOCUMENTOS_REEMBOLSO, PERGUNTA_DOCUMENTOS_FERIAS, *PERGUNTAS_FORA_DA_BASE)
    return {pergunta: assistente.responder(pergunta) for pergunta in perguntas}


def _cita(resposta: Resposta, documento: str, secao: str) -> bool:
    return any(f.documento == documento and f.secao == secao for f in resposta.fontes)


# Documentos para reembolso


def test_documentos_para_reembolso_nao_recebe_recusa(respostas: dict[str, Resposta]) -> None:
    assert respostas[PERGUNTA_DOCUMENTOS_REEMBOLSO].evidencia_suficiente is True


def test_documentos_para_reembolso_cita_a_secao_5_de_fin_pol_001(
    respostas: dict[str, Resposta],
) -> None:
    assert _cita(respostas[PERGUNTA_DOCUMENTOS_REEMBOLSO], "FIN-POL-001", "5")


def test_documentos_para_reembolso_menciona_comprovante_fiscal(
    respostas: dict[str, Resposta],
) -> None:
    texto = respostas[PERGUNTA_DOCUMENTOS_REEMBOLSO].texto.casefold()

    assert "comprovante fiscal" in texto


# Documentos para férias


def test_documentos_para_ferias_nao_recebe_recusa(respostas: dict[str, Resposta]) -> None:
    assert respostas[PERGUNTA_DOCUMENTOS_FERIAS].evidencia_suficiente is True


def test_documentos_para_ferias_cita_a_secao_3_de_rh_pro_003(
    respostas: dict[str, Resposta],
) -> None:
    assert _cita(respostas[PERGUNTA_DOCUMENTOS_FERIAS], "RH-PRO-003", "3")


def test_documentos_para_ferias_menciona_periodo(respostas: dict[str, Resposta]) -> None:
    assert "período" in respostas[PERGUNTA_DOCUMENTOS_FERIAS].texto.casefold()


def test_documentos_para_ferias_menciona_dias(respostas: dict[str, Resposta]) -> None:
    assert "dias" in respostas[PERGUNTA_DOCUMENTOS_FERIAS].texto.casefold()


@pytest.mark.parametrize(
    "frase_de_ausencia", ["não define", "não estabelece", "não traz", "não especifica"]
)
def test_documentos_para_ferias_nao_afirma_ausencia_no_documento(
    frase_de_ausencia: str, respostas: dict[str, Resposta]
) -> None:
    assert frase_de_ausencia not in respostas[PERGUNTA_DOCUMENTOS_FERIAS].texto.casefold()


# Fora da base


@pytest.mark.parametrize("pergunta", PERGUNTAS_FORA_DA_BASE)
def test_pergunta_fora_da_base_recebe_recusa(pergunta: str, respostas: dict[str, Resposta]) -> None:
    assert respostas[pergunta].evidencia_suficiente is False


@pytest.mark.parametrize("pergunta", PERGUNTAS_FORA_DA_BASE)
def test_pergunta_fora_da_base_nao_cita_fonte(
    pergunta: str, respostas: dict[str, Resposta]
) -> None:
    assert respostas[pergunta].fontes == ()
