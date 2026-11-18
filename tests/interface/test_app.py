"""Testes da tela de perguntas (HIST-019) com `streamlit.testing.v1.AppTest`.

Não chamam a API. `composicao.montar_assistente_do_ambiente` é trocada por um dublê antes de cada
execução da página. A página importa essa função a cada execução, então a troca vale para o script
inteiro. A página não usa `config` nem `montar_assistente` diretamente.

O cache do assistente (`st.cache_resource`) é global ao processo, por isso é limpo antes e
depois de cada teste. Assim o contador de montagens conta só o que o teste fez.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import composicao
from nucleo.assistente import AssistenteRAG
from nucleo.erros import ErroBusca, ErroDocumento
from nucleo.modelos import Fonte, Resposta, Trecho

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
APP = RAIZ_PROJETO / "src" / "interface" / "app.py"
TIMEOUT_SEGUNDOS = 15

ROTULO_PERGUNTA = "Pergunta"
TEXTO_BOTAO = "Enviar pergunta"
MENSAGEM_ERRO = "Não foi possível responder. Verifique a pergunta e tente novamente."
FONTE = Fonte(documento="FIN-POL-001", secao="3.1", titulo="Prazo de entrega")
TEXTO_COM_MARKDOWN = (
    "Veja [x](http://exemplo.invalido) e a imagem ![](http://exemplo.invalido/i.png)."
)


class AssistenteFalso:
    """Dublê de `AssistenteRAG`: registra as perguntas e devolve uma resposta fixa com fonte."""

    def __init__(self) -> None:
        self.perguntas: list[str] = []
        self.erro: Exception | None = None
        self.texto: str | None = None

    def responder(self, pergunta: str) -> Resposta:
        self.perguntas.append(pergunta)
        if self.erro is not None:
            raise self.erro
        texto = self.texto if self.texto is not None else f"Resposta para: {pergunta}"
        return Resposta(texto=texto, fontes=(FONTE,))


class Montagens:
    """Dublê de `montar_assistente_do_ambiente`: conta as chamadas e devolve o mesmo assistente."""

    def __init__(self) -> None:
        self.chamadas = 0
        self.assistente: Any = AssistenteFalso()
        self.erro_na_montagem: Exception | None = None

    def __call__(self) -> Any:
        self.chamadas += 1
        if self.erro_na_montagem is not None:
            raise self.erro_na_montagem
        return self.assistente


class BuscadorEspiao:
    """Dublê de `Buscador` que não encontra nada e registra as perguntas recebidas."""

    def __init__(self) -> None:
        self.perguntas: list[str] = []

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        self.perguntas.append(pergunta)
        return ()


class GeradorQueNaoDeveRodar:
    def gerar(self, pergunta: str, trechos: Any) -> Resposta:
        raise AssertionError("o gerador não deveria ser chamado")


@pytest.fixture(autouse=True)
def cache_limpo() -> Any:
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def montagens(monkeypatch: pytest.MonkeyPatch) -> Montagens:
    registro = Montagens()
    monkeypatch.setattr(composicao, "montar_assistente_do_ambiente", registro)
    return registro


def _abrir() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=TIMEOUT_SEGUNDOS)
    at.run()
    return at


def _perguntar(at: AppTest, pergunta: str) -> AppTest:
    at.text_input[0].input(pergunta)
    at.button[0].click()
    at.run()
    return at


def _textos_da_pagina(at: AppTest) -> list[str]:
    """Todo o texto visível que a página mostra, para checar ausências (ex.: a chave)."""
    elementos = [*at.markdown, *at.subheader, *at.error, *at.text_input, *at.title, *at.text]
    return [str(elemento.value) for elemento in elementos]


def test_abre_pagina_com_campo_de_pergunta_e_botao(montagens: Montagens) -> None:
    at = _abrir()

    assert not at.exception
    assert [campo.label for campo in at.text_input] == [ROTULO_PERGUNTA]
    assert [botao.label for botao in at.button] == [TEXTO_BOTAO]


def test_enviar_pergunta_mostra_resposta_e_fontes(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    textos = _textos_da_pagina(at)
    assert "Resposta para: Qual é o prazo de entrega?" in textos
    assert "Fontes" in [subtitulo.value for subtitulo in at.subheader]
    # Os caracteres de formatação do Markdown são escapados (o título vem dos PDFs).
    assert "- FIN\\-POL\\-001, seção 3\\.1: Prazo de entrega" in textos


def test_texto_da_resposta_nao_vira_link_nem_imagem(montagens: Montagens) -> None:
    montagens.assistente.texto = TEXTO_COM_MARKDOWN

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    # O texto aparece literal, como texto puro.
    assert TEXTO_COM_MARKDOWN in [str(texto.value) for texto in at.text]
    # Nenhum bloco Markdown da página contém o link ou a imagem da resposta.
    blocos_markdown = [str(bloco.value) for bloco in at.markdown]
    assert not any("exemplo.invalido" in bloco for bloco in blocos_markdown)
    assert not any("](" in bloco or "![" in bloco for bloco in blocos_markdown)


def test_assistente_e_montado_uma_vez_com_varias_perguntas(montagens: Montagens) -> None:
    at = _abrir()
    for pergunta in ("Primeira pergunta?", "Segunda pergunta?", "Terceira pergunta?"):
        at = _perguntar(at, pergunta)

    assert not at.exception
    assert montagens.chamadas == 1
    assert montagens.assistente.perguntas == [
        "Primeira pergunta?",
        "Segunda pergunta?",
        "Terceira pergunta?",
    ]


def test_pergunta_vazia_mostra_aviso_sem_quebrar_a_pagina(montagens: Montagens) -> None:
    buscador = BuscadorEspiao()
    montagens.assistente = AssistenteRAG(buscador, GeradorQueNaoDeveRodar())

    at = _perguntar(_abrir(), "   ")

    assert not at.exception
    assert [erro.value for erro in at.error] == [MENSAGEM_ERRO]
    assert buscador.perguntas == []


def test_erro_de_servico_mostra_mensagem_generica_sem_detalhes(montagens: Montagens) -> None:
    montagens.assistente.erro = ErroBusca("detalhe interno do provedor 503")

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert [erro.value for erro in at.error] == [MENSAGEM_ERRO]
    assert not any("detalhe interno" in texto for texto in _textos_da_pagina(at))


def test_falha_ao_montar_assistente_mostra_mensagem_generica(montagens: Montagens) -> None:
    montagens.erro_na_montagem = ErroDocumento("pasta sem PDFs")

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert [erro.value for erro in at.error] == [MENSAGEM_ERRO]
    assert not any("pasta sem PDFs" in texto for texto in _textos_da_pagina(at))


def test_nova_tentativa_depois_de_falha_de_montagem(montagens: Montagens) -> None:
    montagens.erro_na_montagem = ErroDocumento("pasta sem PDFs")
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")
    assert [erro.value for erro in at.error] == [MENSAGEM_ERRO]

    montagens.erro_na_montagem = None
    at = _perguntar(at, "Qual é o prazo de entrega?")

    assert not at.exception
    assert montagens.chamadas == 2
    assert [erro.value for erro in at.error] == []
    assert "Resposta para: Qual é o prazo de entrega?" in _textos_da_pagina(at)


def test_pagina_nunca_exibe_a_chave_da_api(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not any("sk-" in texto for texto in _textos_da_pagina(at))
