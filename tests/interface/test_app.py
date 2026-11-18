"""Testes da tela de perguntas (HIST-019 e HIST-020) com `streamlit.testing.v1.AppTest`.

Não chamam a API. `composicao.montar_assistente_do_ambiente` é trocada por um dublê antes de cada
execução da página. A página importa essa função a cada execução, então a troca vale para o script
inteiro. A página não usa `config` nem `montar_assistente` diretamente.

Nos testes de pergunta (vazia, 500 e 501 caracteres), o assistente é o `AssistenteRAG` real do
núcleo, com um buscador espião: assim a regra de tamanho é checada no núcleo, sem API.

O cache do assistente (`st.cache_resource`) é global ao processo, por isso é limpo antes e
depois de cada teste. Assim o contador de montagens conta só o que o teste fez.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import composicao
from nucleo.assistente import AssistenteRAG
from nucleo.erros import ConfiguracaoInvalida, ErroBusca, ErroDocumento
from nucleo.modelos import MENSAGEM_SEM_EVIDENCIA, Fonte, Resposta, Trecho

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
APP = RAIZ_PROJETO / "src" / "interface" / "app.py"
TIMEOUT_SEGUNDOS = 15

ROTULO_PERGUNTA = "Pergunta"
TEXTO_BOTAO = "Enviar pergunta"
ROTULO_EXPANSOR = "Ver fontes desta resposta"
FONTE = Fonte(documento="FIN-POL-001", secao="3.1", titulo="Prazo de entrega")
TEXTO_COM_MARKDOWN = (
    "Veja [x](http://exemplo.invalido) e a imagem ![](http://exemplo.invalido/i.png)."
)
CHAVE_DE_TESTE = "sk-teste-chave-nao-real-0123456789"
MENSAGEM_PERGUNTA_VAZIA = "A pergunta não pode ser vazia."
MENSAGEM_PERGUNTA_LONGA = "A pergunta deve ter no máximo 500 caracteres."
MENSAGEM_SERVICO = (
    "Não foi possível responder agora. O serviço pode estar indisponível. "
    "Tente novamente em instantes."
)
MENSAGEM_CONFIGURACAO = (
    "Não foi possível iniciar o assistente por causa da configuração. "
    "Confira o arquivo .env na pasta do projeto e atualize a página."
)
MENSAGEM_INESPERADA = (
    "Ocorreu um erro inesperado. Tente novamente. Se o problema continuar, avise a equipe."
)
LIMITE_PERGUNTA = 500
CLASSE_RESPOSTA = "agrinormas-resposta"
TITULO_RESPOSTA = "Resposta"
# Texto do núcleo passa por escape de Markdown antes de st.info e st.warning: cada "." vira "\."
MENSAGEM_SEM_EVIDENCIA_ESCAPADA = MENSAGEM_SEM_EVIDENCIA.replace(".", "\\.")
MENSAGEM_PERGUNTA_VAZIA_ESCAPADA = MENSAGEM_PERGUNTA_VAZIA.replace(".", "\\.")
MENSAGEM_PERGUNTA_LONGA_ESCAPADA = MENSAGEM_PERGUNTA_LONGA.replace(".", "\\.")


class AssistenteFalso:
    """Dublê de `AssistenteRAG`: registra as perguntas e devolve uma resposta controlada."""

    def __init__(self) -> None:
        self.perguntas: list[str] = []
        self.erro: Exception | None = None
        self.texto: str | None = None
        self.resposta: Resposta | None = None
        self.fontes: tuple[Fonte, ...] = (FONTE,)

    def responder(self, pergunta: str) -> Resposta:
        self.perguntas.append(pergunta)
        if self.erro is not None:
            raise self.erro
        if self.resposta is not None:
            return self.resposta
        texto = self.texto if self.texto is not None else f"Resposta para: {pergunta}"
        return Resposta(texto=texto, fontes=self.fontes)


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


def _valores(elementos: Any) -> list[str]:
    return [str(elemento.value) for elemento in elementos]


def _respostas_em_html(at: AppTest) -> list[str]:
    """Blocos HTML que contêm a resposta (texto puro). Não inclui o CSS da página."""
    return [
        valor for valor in _valores(at.html) if valor.startswith(f'<div class="{CLASSE_RESPOSTA}"')
    ]


def _css_da_pagina(at: AppTest) -> str:
    return "\n".join(valor for valor in _valores(at.html) if "<style>" in valor)


def _conteudo_da_arvore(no: Any) -> str:
    """Todo o conteúdo renderizado por um nó e pelos filhos, para checar ausências (ex.: a chave).

    Usa o `proto` de cada elemento, que carrega o texto completo, inclusive o que não aparece
    em `.value`.
    """
    partes: list[str] = []
    filhos = getattr(no, "children", None)
    if filhos:
        partes.extend(_conteudo_da_arvore(filho) for filho in filhos.values())
    proto = getattr(no, "proto", None)
    if proto is not None:
        partes.append(str(proto))
    return "\n".join(partes)


def _conteudo_da_pagina(at: AppTest) -> str:
    """Conteúdo de todas as áreas da página, inclusive barra lateral e exceções do script."""
    excecoes = [str(elemento.proto) for elemento in at.exception]
    return "\n".join([_conteudo_da_arvore(at.main), _conteudo_da_arvore(at.sidebar), *excecoes])


def test_abre_pagina_com_campo_de_pergunta_e_botao(montagens: Montagens) -> None:
    at = _abrir()

    assert not at.exception
    assert [campo.label for campo in at.text_input] == [ROTULO_PERGUNTA]
    assert [botao.label for botao in at.button] == [TEXTO_BOTAO]


def test_estado_inicial_nao_mostra_resposta_nem_aviso(montagens: Montagens) -> None:
    at = _abrir()

    assert not at.exception
    assert len(at.info) == 0
    assert len(at.warning) == 0
    assert len(at.error) == 0
    assert len(at.expander) == 0
    assert len(at.text) == 0
    assert _respostas_em_html(at) == []
    assert len(at.header) == 0


def test_campo_de_pergunta_tem_rotulo_e_texto_de_ajuda(montagens: Montagens) -> None:
    at = _abrir()

    assert at.text_input[0].label == ROTULO_PERGUNTA
    assert at.text_input[0].proto.help.strip() != ""


def test_enviar_pergunta_mostra_resposta_e_fontes(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert _valores(at.header) == [TITULO_RESPOSTA]
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">Resposta para: Qual é o prazo de entrega?</div>'
    ]
    assert [expansor.label for expansor in at.expander] == [ROTULO_EXPANSOR]
    # Os caracteres de formatação do Markdown são escapados (os códigos vêm dos PDFs).
    corpo_esperado = (
        "- **Código do documento:** FIN\\-POL\\-001 · **Seção:** 3\\.1 "
        "· **Título:** Prazo de entrega"
    )
    assert _valores(at.expander[0].markdown) == [corpo_esperado]


def test_fontes_ficam_recolhidas_e_a_um_clique(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert len(at.expander) == 1
    assert at.expander[0].proto.expanded is False


def test_titulo_da_fonte_com_markdown_e_escapado(montagens: Montagens) -> None:
    montagens.assistente.fontes = (
        Fonte(documento="RH-PRO-003", secao="2", titulo="[clique](http://exemplo.invalido)"),
    )

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    corpo = " ".join(_valores(at.expander[0].markdown))
    assert "\\[clique\\]\\(http://exemplo\\.invalido\\)" in corpo
    assert "[clique](http://exemplo.invalido)" not in corpo


def test_texto_da_resposta_nao_vira_link_nem_imagem(montagens: Montagens) -> None:
    montagens.assistente.texto = TEXTO_COM_MARKDOWN

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    # O texto aparece literal, escapado em HTML: os colchetes e parênteses continuam texto.
    respostas = _respostas_em_html(at)
    assert respostas == [
        f'<div class="{CLASSE_RESPOSTA}">'
        "Veja [x](http://exemplo.invalido) e a imagem ![](http://exemplo.invalido/i.png)."
        "</div>"
    ]
    # Nenhum elemento de link ou imagem é criado pela resposta.
    assert not any("<a " in bloco or "<img" in bloco for bloco in _valores(at.html))
    # Os blocos Markdown da página são a descrição e a fonte, nunca o texto da resposta.
    blocos_markdown = _valores(at.markdown)
    assert not any("exemplo.invalido" in bloco for bloco in blocos_markdown)
    assert not any("](" in bloco or "![" in bloco for bloco in blocos_markdown)


def test_recusa_com_markdown_do_nucleo_recebe_escape(montagens: Montagens) -> None:
    # AppTest não renderiza Markdown. Este teste prova só o escape do texto passado a `st.info`:
    # a forma renderizada (link, imagem, autolink) não é verificada aqui. O autolink de URL e
    # e-mail continua aberto na M-59 do backlog e é medido no navegador (ver o checklist).
    montagens.assistente.resposta = Resposta(texto=TEXTO_COM_MARKDOWN, evidencia_suficiente=False)

    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    assert not at.exception
    valores = _valores(at.info)
    assert len(valores) == 1
    # O texto passado a `st.info` tem os colchetes, parênteses e o `!` escapados.
    assert "\\[x\\]\\(http://exemplo\\.invalido\\)" in valores[0]
    assert "](" not in valores[0]
    assert "![" not in valores[0]


def test_resposta_com_html_vira_texto_escapado(montagens: Montagens) -> None:
    montagens.assistente.texto = '<img src="x" onerror="alert(1)"><b>negrito</b> & "aspas"'

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">'
        "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;"
        "&lt;b&gt;negrito&lt;/b&gt; &amp; &quot;aspas&quot;"
        "</div>"
    ]
    assert not any("<img" in bloco or "<b>" in bloco for bloco in _valores(at.html))


def test_resposta_preserva_quebras_de_linha(montagens: Montagens) -> None:
    montagens.assistente.texto = "Primeira linha.\nSegunda linha."

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">Primeira linha.\nSegunda linha.</div>'
    ]
    assert "white-space: pre-wrap" in _css_da_pagina(at)


def test_layout_estreito_tem_margem_de_16_pixels_e_quebra_de_linha(
    montagens: Montagens,
) -> None:
    at = _abrir()

    css = _css_da_pagina(at)
    assert "@media (max-width: 640px)" in css
    assert "padding-left: 16px" in css
    assert "padding-right: 16px" in css
    assert "overflow-wrap: anywhere" in css


def test_conteudo_das_fontes_quebra_palavras_longas_no_expansor(montagens: Montagens) -> None:
    css = _css_da_pagina(_abrir())

    seletor = '[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {'
    assert seletor in css
    bloco = css.split(seletor)[1].split("}")[0]
    assert "overflow-wrap: anywhere" in bloco


def test_css_da_pagina_nao_carrega_recursos_externos(montagens: Montagens) -> None:
    css = _css_da_pagina(_abrir())

    assert "<style>" in css
    assert "url(" not in css
    assert "@import" not in css


def test_titulo_da_resposta_e_nivel_2_sem_pular_do_titulo_da_pagina(
    montagens: Montagens,
) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert len(at.title) == 1
    assert _valores(at.header) == [TITULO_RESPOSTA]
    assert len(at.subheader) == 0


def test_sem_evidencia_mostra_aviso_informativo_sem_fontes(montagens: Montagens) -> None:
    montagens.assistente.resposta = Resposta.sem_evidencia()

    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    assert not at.exception
    assert _valores(at.header) == [TITULO_RESPOSTA]
    assert _valores(at.info) == [MENSAGEM_SEM_EVIDENCIA_ESCAPADA]
    assert len(at.expander) == 0
    assert len(at.text) == 0
    assert _respostas_em_html(at) == []
    assert len(at.warning) == 0
    assert len(at.error) == 0


def test_pergunta_vazia_mostra_aviso_de_pergunta_invalida(montagens: Montagens) -> None:
    buscador = BuscadorEspiao()
    montagens.assistente = AssistenteRAG(buscador, GeradorQueNaoDeveRodar())

    at = _perguntar(_abrir(), "   ")

    assert not at.exception
    assert _valores(at.warning) == [MENSAGEM_PERGUNTA_VAZIA_ESCAPADA]
    assert len(at.info) == 0
    assert len(at.error) == 0
    assert len(at.header) == 0
    assert buscador.perguntas == []


def test_pergunta_com_500_caracteres_e_aceita(montagens: Montagens) -> None:
    buscador = BuscadorEspiao()
    montagens.assistente = AssistenteRAG(buscador, GeradorQueNaoDeveRodar())
    pergunta = "a" * LIMITE_PERGUNTA

    at = _perguntar(_abrir(), pergunta)

    assert not at.exception
    assert len(at.warning) == 0
    assert len(at.error) == 0
    # O buscador espião não encontra nada: a recusa esperada é a de falta de evidência.
    assert _valores(at.info) == [MENSAGEM_SEM_EVIDENCIA_ESCAPADA]
    assert buscador.perguntas == [pergunta]


def test_pergunta_com_501_caracteres_e_recusada_sem_chamar_a_busca(
    montagens: Montagens,
) -> None:
    buscador = BuscadorEspiao()
    montagens.assistente = AssistenteRAG(buscador, GeradorQueNaoDeveRodar())

    at = _perguntar(_abrir(), "a" * (LIMITE_PERGUNTA + 1))

    assert not at.exception
    assert _valores(at.warning) == [MENSAGEM_PERGUNTA_LONGA_ESCAPADA]
    assert len(at.info) == 0
    assert len(at.error) == 0
    assert buscador.perguntas == []


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


def test_erro_de_servico_mostra_mensagem_generica_sem_detalhes(montagens: Montagens) -> None:
    montagens.assistente.erro = ErroBusca(f"falha no provedor com a chave {CHAVE_DE_TESTE}")

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert _valores(at.error) == [MENSAGEM_SERVICO]
    assert len(at.warning) == 0
    assert CHAVE_DE_TESTE not in _conteudo_da_pagina(at)


def test_erro_de_configuracao_na_abertura_orienta_o_env_sem_valores(
    montagens: Montagens,
) -> None:
    montagens.erro_na_montagem = ConfiguracaoInvalida(f"OPENAI_API_KEY inválida: {CHAVE_DE_TESTE}")

    at = _abrir()

    assert not at.exception
    assert _valores(at.error) == [MENSAGEM_CONFIGURACAO]
    assert ".env" in MENSAGEM_CONFIGURACAO
    assert len(at.text_input) == 0
    assert CHAVE_DE_TESTE not in _conteudo_da_pagina(at)


def test_erro_de_configuracao_nao_mostra_rastreamento(montagens: Montagens) -> None:
    montagens.erro_na_montagem = ConfiguracaoInvalida("OPENAI_API_KEY ausente")

    at = _abrir()

    assert not at.exception
    assert "Traceback" not in _conteudo_da_pagina(at)
    assert "OPENAI_API_KEY" not in _conteudo_da_pagina(at)


def test_falha_de_montagem_com_erro_de_documentos_mostra_mensagem_generica(
    montagens: Montagens,
) -> None:
    montagens.erro_na_montagem = ErroDocumento("pasta sem PDFs")

    at = _abrir()

    assert not at.exception
    assert _valores(at.error) == [MENSAGEM_SERVICO]
    assert "pasta sem PDFs" not in _conteudo_da_pagina(at)


def test_nova_tentativa_depois_de_falha_de_montagem(montagens: Montagens) -> None:
    montagens.erro_na_montagem = ConfiguracaoInvalida("ausente")
    at = _abrir()
    assert _valores(at.error) == [MENSAGEM_CONFIGURACAO]

    # O erro não fica em cache: ao atualizar a página, a montagem é tentada de novo.
    montagens.erro_na_montagem = None
    at.run()
    at = _perguntar(at, "Qual é o prazo de entrega?")

    assert not at.exception
    assert montagens.chamadas == 2
    assert len(at.error) == 0
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">Resposta para: Qual é o prazo de entrega?</div>'
    ]


def test_erro_inesperado_mostra_mensagem_generica_e_registra_no_log(
    montagens: Montagens, caplog: pytest.LogCaptureFixture
) -> None:
    montagens.assistente.erro = RuntimeError(f"segredo interno {CHAVE_DE_TESTE}")

    with caplog.at_level(logging.ERROR):
        at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert _valores(at.error) == [MENSAGEM_INESPERADA]
    assert "segredo interno" not in _conteudo_da_pagina(at)
    assert CHAVE_DE_TESTE not in _conteudo_da_pagina(at)
    # O log nunca contém a mensagem da exceção (pode ter a chave da API).
    assert CHAVE_DE_TESTE not in caplog.text
    assert "segredo interno" not in caplog.text
    # O log contém a classe da exceção e o local da falha (nome da função que lançou).
    assert "RuntimeError" in caplog.text
    assert "responder" in caplog.text
    registros = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert registros
    # Sem traceback: `exc_info` exibiria a mensagem da exceção.
    assert registros[0].exc_info is None


def test_pagina_nunca_exibe_a_chave_da_api_em_nenhum_elemento(montagens: Montagens) -> None:
    montagens.assistente.erro = ErroBusca(f"falha com a chave {CHAVE_DE_TESTE}")
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert CHAVE_DE_TESTE not in _conteudo_da_pagina(at)
    assert "sk-" not in _conteudo_da_pagina(at)
