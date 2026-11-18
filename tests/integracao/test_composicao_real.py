"""Teste de integração da montagem do assistente com a API real da OpenAI (HIST-018, critério 1).

Não substitui `carregar_secoes`, não usa dublês: lê os PDFs de `base_conhecimento/` e chama a
API com a chave do `.env`. Consome créditos. Só roda com `pytest -m integracao`.

A pergunta vem de `tests/validacao/perguntas.md`, a fonte única das perguntas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from busca.calibracao import PerguntaValidacao, ler_perguntas_validacao
from composicao import montar_assistente
from config import NOME_CHAVE_OPENAI, Configuracao, carregar_configuracao
from nucleo.assistente import AssistenteRAG
from nucleo.erros import ConfiguracaoInvalida
from nucleo.modelos import Resposta

pytestmark = pytest.mark.integracao

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
CAMINHO_PERGUNTAS = RAIZ_PROJETO / "tests" / "validacao" / "perguntas.md"
NUMERO_PERGUNTA_PRAZO_REEMBOLSO = 1
DOCUMENTO_ESPERADO = "FIN-POL-001"


def _pergunta_1() -> PerguntaValidacao:
    (pergunta,) = (
        p
        for p in ler_perguntas_validacao(CAMINHO_PERGUNTAS)
        if p.numero == NUMERO_PERGUNTA_PRAZO_REEMBOLSO
    )
    return pergunta


@pytest.fixture(scope="module")
def resposta_pergunta_1() -> Resposta:
    configuracao = carregar_configuracao()
    assistente: AssistenteRAG = montar_assistente(configuracao)
    return assistente.responder(_pergunta_1().texto)


def test_resposta_da_pergunta_1_tem_texto_nao_vazio(resposta_pergunta_1: Resposta) -> None:
    assert resposta_pergunta_1.texto.strip() != ""


def test_resposta_da_pergunta_1_tem_evidencia_suficiente(resposta_pergunta_1: Resposta) -> None:
    assert resposta_pergunta_1.evidencia_suficiente is True


def test_resposta_da_pergunta_1_cita_fin_pol_001(resposta_pergunta_1: Resposta) -> None:
    documentos = {fonte.documento for fonte in resposta_pergunta_1.fontes}
    assert DOCUMENTO_ESPERADO in documentos, documentos


def test_chave_nao_aparece_no_repr_da_configuracao() -> None:
    configuracao: Configuracao = carregar_configuracao()
    chave = configuracao.chave_openai

    representacao = repr(configuracao)

    assert chave, "a chave deve estar carregada do .env"
    assert (chave in representacao) is False


def test_chave_nao_aparece_em_mensagem_de_erro_de_configuracao() -> None:
    chave = carregar_configuracao().chave_openai
    ambiente_com_valor_invalido = {NOME_CHAVE_OPENAI: chave, "TOP_K": "0"}

    with pytest.raises(ConfiguracaoInvalida) as erro:
        carregar_configuracao(ambiente=ambiente_com_valor_invalido)

    vazou = chave in str(erro.value)
    assert vazou is False
