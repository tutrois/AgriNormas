"""Testes da tela de perguntas (HIST-019, HIST-020 e HIST-030) com `streamlit.testing.v1.AppTest`.

Não chamam a API. `composicao.montar_assistente_do_ambiente` é trocada por um dublê antes de cada
execução da página. A página importa essa função a cada execução, então a troca vale para o script
inteiro. A página não usa `config` nem `montar_assistente` diretamente.

Nos testes de pergunta (vazia, 500 e 501 caracteres), o assistente é o `AssistenteRAG` real do
núcleo, com um buscador espião: assim a regra de tamanho é checada no núcleo, sem API.

O cache do assistente (`st.cache_resource`) é global ao processo, por isso é limpo antes e
depois de cada teste. Assim o contador de montagens conta só o que o teste fez.

HIST-030: a resposta e a recusa ficam em balões (HTML com texto escapado). Por isso os testes de
resposta leem o `<div class="agrinormas-resposta">` dentro do HTML, e não mais `st.info`.
"""

from __future__ import annotations

import logging
import re
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
ROTULO_USUARIO = "Você"
ROTULO_ASSISTENTE = "Assistente"
ROTULO_SEM_EVIDENCIA = "Sem evidência"
TITULO_BOAS_VINDAS = "Consulte as normas da empresa"
TEXTO_AJUDA = "Escreva a pergunta em uma frase. A resposta vem só dos documentos da base."
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
# Texto de aviso do núcleo passa por escape de Markdown antes de st.warning: cada "." vira "\."
MENSAGEM_PERGUNTA_VAZIA_ESCAPADA = MENSAGEM_PERGUNTA_VAZIA.replace(".", "\\.")
MENSAGEM_PERGUNTA_LONGA_ESCAPADA = MENSAGEM_PERGUNTA_LONGA.replace(".", "\\.")

PADRAO_RESPOSTA = re.compile(rf'<div class="{CLASSE_RESPOSTA}">.*?</div>', re.DOTALL)
PADRAO_AUTOR = re.compile(r'<span class="agri-autor[^"]*">([^<]*)</span>')
PADRAO_SELO = re.compile(r'<span class="agri-selo-sem-evidencia">([^<]*)</span>')


def _cria_link_ou_imagem(bloco: str) -> bool:
    """Link ou imagem criados pela página. A página não tem link fixo: a barra usa botões."""
    if "<img" in bloco:
        return True
    return "<a " in bloco


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
    st.cache_data.clear()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()


DOCUMENTOS = (
    composicao.DocumentoDaBase(
        "Politica_Reembolso.pdf", "FIN-POL-001", "POLÍTICA DE REEMBOLSO", "1.0"
    ),
    composicao.DocumentoDaBase(
        "Politica_Veiculos.pdf", "FRO-POL-002", "POLÍTICA DE VEÍCULOS", "2.1"
    ),
    composicao.DocumentoDaBase(
        "Procedimento_Ferias.pdf", "RH-PRC-003", "PROCEDIMENTO DE FÉRIAS", ""
    ),
)
MENSAGEM_BASE_VAZIA = "Nenhum documento encontrado na base."
MENSAGEM_BASE_ERRO = "Não foi possível listar os documentos."
TEXTO_DOCUMENTO_ERRO = "Não foi possível abrir este documento."


class ListagemFalsa:
    """Dublê de `listar_documentos_do_ambiente`: conta as chamadas e pode falhar."""

    def __init__(self) -> None:
        self.chamadas = 0
        self.documentos: tuple[Any, ...] = DOCUMENTOS
        self.erro: Exception | None = None

    def __call__(self) -> tuple[Any, ...]:
        self.chamadas += 1
        if self.erro is not None:
            raise self.erro
        return self.documentos


@pytest.fixture
def listagem(monkeypatch: pytest.MonkeyPatch) -> ListagemFalsa:
    registro = ListagemFalsa()
    monkeypatch.setattr(composicao, "listar_documentos_do_ambiente", registro, raising=False)
    return registro


def _conteudo(
    arquivo: str, codigo: str, secoes: tuple[Any, ...] | None = None, titulo: str | None = None
) -> composicao.ConteudoDoDocumento:
    """Documento falso: uma seção normal, uma com quebra de linha e uma pergunta frequente."""
    if secoes is None:
        secoes = (
            composicao.SecaoDoDocumento("1", "Objetivo", "Primeira linha\nSegunda linha", "norma"),
            composicao.SecaoDoDocumento("2", "Prazo", "Texto do prazo.", "norma"),
            composicao.SecaoDoDocumento("faq-1", "Como pedir?", "Pelo sistema.", "faq"),
        )
    return composicao.ConteudoDoDocumento(arquivo, codigo, titulo or arquivo, "1.0", secoes)


class LeituraFalsa:
    """Dublê de `ler_documento_do_ambiente`: registra os arquivos pedidos e pode falhar."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []
        self.conteudos: dict[str, Any] = {
            documento.arquivo: _conteudo(
                documento.arquivo, documento.codigo, None, documento.titulo
            )
            for documento in DOCUMENTOS
        }
        self.erro: Exception | None = None

    def __call__(self, arquivo: str) -> Any:
        self.chamadas.append(arquivo)
        if self.erro is not None:
            raise self.erro
        return self.conteudos.get(arquivo)


@pytest.fixture
def leitura(monkeypatch: pytest.MonkeyPatch) -> LeituraFalsa:
    registro = LeituraFalsa()
    monkeypatch.setattr(composicao, "ler_documento_do_ambiente", registro)
    return registro


@pytest.fixture
def montagens(
    monkeypatch: pytest.MonkeyPatch, listagem: ListagemFalsa, leitura: LeituraFalsa
) -> Montagens:
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
    """Blocos de texto da resposta (`<div class="agrinormas-resposta">`), em texto puro."""
    return [m.group(0) for valor in _valores(at.html) for m in PADRAO_RESPOSTA.finditer(valor)]


def _autores(at: AppTest) -> list[str]:
    """Rótulos de autor exibidos como texto, na ordem da conversa."""
    return [m for valor in _valores(at.html) for m in PADRAO_AUTOR.findall(valor)]


def _selos(at: AppTest) -> list[str]:
    """Selos "Sem evidência" exibidos nos balões."""
    return [m for valor in _valores(at.html) for m in PADRAO_SELO.findall(valor)]


def _html_da_pagina(at: AppTest) -> str:
    """Todo o HTML renderizado pela página (estilo, topo, balões e boas-vindas)."""
    return "\n".join(_valores(at.html))


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
    # O botão de envio vem primeiro; depois, um botão por cartão de sugestão.
    assert [botao.label for botao in at.button][0] == TEXTO_BOTAO
    # Um botão de envio, três cartões (Reembolso, Veículos e Férias) e os três botões da barra:
    # "Nova conversa", "Perguntar" e "Base de conhecimento".
    assert len(at.button) == 7


def test_cartao_de_sugestao_envia_pergunta_pronta_e_some_depois(montagens: Montagens) -> None:
    at = _abrir()
    cartao_reembolso = at.button[1]
    assert "Reembolso" in cartao_reembolso.label

    cartao_reembolso.click()
    at.run()

    assert not at.exception
    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE]
    assert "Como funciona o reembolso de despesas?" in _html_da_pagina(at)
    # Com conversa, os cartões saem da tela.
    assert not any("Reembolso" in botao.label for botao in at.button)
    assert [botao.label for botao in at.button][0] == TEXTO_BOTAO


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
    assert _autores(at) == []
    assert TITULO_BOAS_VINDAS in _html_da_pagina(at)


def test_campo_de_pergunta_tem_rotulo_e_texto_de_ajuda(montagens: Montagens) -> None:
    at = _abrir()

    assert at.text_input[0].label == ROTULO_PERGUNTA
    # Com o rótulo oculto, a ajuda aparece como texto visível no rodapé da barra (HIST-030).
    assert TEXTO_AJUDA in _html_da_pagina(at)


def test_enviar_pergunta_mostra_resposta_e_fontes(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    # Os dois balões aparecem na ordem da conversa, com rótulo em texto.
    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE]
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
    assert not any(_cria_link_ou_imagem(bloco) for bloco in _valores(at.html))
    # Os blocos Markdown da página são a descrição e a fonte, nunca o texto da resposta.
    blocos_markdown = _valores(at.markdown)
    assert not any("exemplo.invalido" in bloco for bloco in blocos_markdown)
    assert not any("](" in bloco or "![" in bloco for bloco in blocos_markdown)


def test_resposta_nao_mostra_citacoes_inline_e_mantem_os_chips(montagens: Montagens) -> None:
    montagens.assistente.texto = (
        "Vale para atividade profissional [FIN-POL-001 §1]. "
        "Exige nota [FIN-POL-001 §3.1][FIN-POL-001 §3.2]."
    )

    at = _perguntar(_abrir(), "Como funciona o reembolso de despesas?")

    assert not at.exception
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">Vale para atividade profissional. Exige nota.</div>'
    ]
    pagina = _html_da_pagina(at)
    assert "§" not in "".join(_respostas_em_html(at))
    assert '<span class="agri-chip">FIN-POL-001 · 3.1</span>' in pagina
    assert [expansor.label for expansor in at.expander] == [ROTULO_EXPANSOR]


def test_recusa_mostra_o_texto_do_nucleo_literal_e_sem_markdown(montagens: Montagens) -> None:
    # A recusa vai para um balão de texto puro (HTML escapado), e não para `st.info` com Markdown.
    # Por isso o texto chega como foi escrito: nada é interpretado, nem escapado com barra.
    montagens.assistente.resposta = Resposta(texto=TEXTO_COM_MARKDOWN, evidencia_suficiente=False)

    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    assert not at.exception
    assert _respostas_em_html(at) == [f'<div class="{CLASSE_RESPOSTA}">{TEXTO_COM_MARKDOWN}</div>']
    assert _selos(at) == [ROTULO_SEM_EVIDENCIA]
    assert len(at.info) == 0
    assert not any(_cria_link_ou_imagem(bloco) for bloco in _valores(at.html))


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


def test_pergunta_do_usuario_aparece_escapada_no_balao(montagens: Montagens) -> None:
    pergunta = '<img src=x onerror=alert(1)> & "q"'

    at = _perguntar(_abrir(), pergunta)

    assert not at.exception
    assert (
        '<div class="agri-balao agri-balao-usuario">'
        "&lt;img src=x onerror=alert(1)&gt; &amp; &quot;q&quot;</div>"
    ) in _html_da_pagina(at)
    assert "<img" not in _html_da_pagina(at)


def _bloco_da_conversa(at: AppTest) -> Any:
    """Bloco da área de conversa (chave "conversa"), achado pelo id que o Streamlit gera."""
    protos = [getattr(no, "proto", None) for no in at.main.children.values()]
    achados = [
        p for p in protos if p is not None and str(getattr(p, "id", "")).endswith("-conversa")
    ]
    assert len(achados) == 1
    return achados[0]


def test_conversa_liga_rolagem_automatica_ate_a_ultima_mensagem(montagens: Montagens) -> None:
    # A área rola sozinha a cada envio (autoscroll do Streamlit). Sem isso, a última resposta
    # fica abaixo da área visível. A altura real vem do CSS, não deste bloco.
    at = _abrir()
    assert _bloco_da_conversa(at).autoscroll is True

    at = _perguntar(at, "Qual é o prazo de entrega?")

    assert _bloco_da_conversa(at).autoscroll is True


def test_conversa_nao_tem_borda_de_contorno_do_streamlit(montagens: Montagens) -> None:
    # Contêiner de altura fixa ganha borda por padrão; a área de conversa não deve ter.
    assert _bloco_da_conversa(_abrir()).flex_container.border is False


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


def test_html_da_pagina_nao_carrega_recursos_externos(montagens: Montagens) -> None:
    montagens.assistente.resposta = Resposta.sem_evidencia()
    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    html_da_pagina = _html_da_pagina(at)
    assert "url(" not in html_da_pagina
    assert "@import" not in html_da_pagina
    assert "<link" not in html_da_pagina
    assert "<script" not in html_da_pagina
    assert not re.search(r'(src|href)="https?:', html_da_pagina)


def test_pagina_tem_um_unico_titulo_h1_e_nenhum_cabecalho_do_streamlit(
    montagens: Montagens,
) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert _html_da_pagina(at).count("<h1") == 1
    assert len(at.header) == 0
    assert len(at.subheader) == 0
    assert len(at.title) == 0


def test_avatares_sao_decorativos_com_aria_hidden_e_iniciais_em_texto(
    montagens: Montagens,
) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    avatares = re.findall(r'<span class="agri-avatar[^"]*"[^>]*></span>', _html_da_pagina(at))
    assert len(avatares) == 2
    assert all('aria-hidden="true"' in tag for tag in avatares)
    assert "agri-avatar-usuario" in avatares[0]
    assert "agri-avatar-assistente" in avatares[1]
    # Nenhum ícone de fonte na tela: a página não depende de fonte de ícones externa.
    assert "agri-icone" not in _html_da_pagina(at)


def test_barra_lateral_mostra_marca_sem_link_e_nova_conversa_como_botao(
    montagens: Montagens,
) -> None:
    at = _abrir()

    assert '<span class="agri-marca" aria-hidden="true">RH</span>' in _html_da_pagina(at)
    # A marca não é link e "Nova conversa" é botão do Streamlit, não um `<a href>` que recarrega.
    assert "<a " not in _html_da_barra(at)
    assert 'href="./"' not in _html_da_pagina(at)
    assert at.button(key="nova_conversa").label == "Nova conversa"


def test_pagina_nao_mostra_titulo_no_topo(montagens: Montagens) -> None:
    # A referência aprovada não tem título no topo da área principal. A marca fica na barra.
    at = _abrir()

    assert "<h1>" not in _html_da_pagina(at)
    assert "reprodu" not in _html_da_pagina(at)


def test_autores_aparecem_como_texto_voce_e_assistente(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE]
    assert 'aria-label="' not in _html_da_pagina(at)


def test_sem_evidencia_mostra_selo_em_texto_em_vez_de_erro(montagens: Montagens) -> None:
    montagens.assistente.resposta = Resposta.sem_evidencia()

    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    assert not at.exception
    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE]
    assert _selos(at) == [ROTULO_SEM_EVIDENCIA]
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">{MENSAGEM_SEM_EVIDENCIA}</div>'
    ]
    assert len(at.expander) == 0
    assert len(at.info) == 0
    assert len(at.text) == 0
    assert len(at.warning) == 0
    assert len(at.error) == 0


def test_sem_evidencia_nao_tem_fontes_mesmo_que_o_nucleo_as_devolva(montagens: Montagens) -> None:
    montagens.assistente.resposta = Resposta(
        texto=MENSAGEM_SEM_EVIDENCIA, fontes=(FONTE,), evidencia_suficiente=False
    )

    at = _perguntar(_abrir(), "Qual é a cor do uniforme?")

    assert _selos(at) == [ROTULO_SEM_EVIDENCIA]
    assert len(at.expander) == 0


def test_pergunta_vazia_mostra_aviso_de_pergunta_invalida(montagens: Montagens) -> None:
    buscador = BuscadorEspiao()
    montagens.assistente = AssistenteRAG(buscador, GeradorQueNaoDeveRodar())

    at = _perguntar(_abrir(), "   ")

    assert not at.exception
    assert _valores(at.warning) == [MENSAGEM_PERGUNTA_VAZIA_ESCAPADA]
    assert len(at.info) == 0
    assert len(at.error) == 0
    assert len(at.header) == 0
    assert _selos(at) == []
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
    assert _selos(at) == [ROTULO_SEM_EVIDENCIA]
    assert _respostas_em_html(at) == [
        f'<div class="{CLASSE_RESPOSTA}">{MENSAGEM_SEM_EVIDENCIA}</div>'
    ]
    assert len(at.info) == 0
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


NAV_CHAVES = ["nova_conversa", "destino_perguntar", "destino_base"]


def _botoes_da_barra(at: AppTest) -> list[str]:
    """Chaves dos botões da barra, na ordem em que aparecem (sem as perguntas recentes)."""
    return [str(b.key) for b in at.sidebar.button if not str(b.key).startswith("recente_")]


def _recentes(at: AppTest) -> list[str]:
    return [str(b.key) for b in at.sidebar.button if str(b.key).startswith("recente_")]


def _html_da_barra(at: AppTest) -> str:
    return "\n".join(_valores(at.sidebar.html))


def _clicar(at: AppTest, chave: str) -> AppTest:
    at.button(key=chave).click()
    at.run()
    assert not at.exception
    return at


def test_barra_tem_acao_e_dois_destinos_sem_recentes_nem_documentos(montagens: Montagens) -> None:
    at = _abrir()

    assert not at.exception
    assert _botoes_da_barra(at) == NAV_CHAVES
    assert at.button(key="nova_conversa").label == "Nova conversa"
    assert at.button(key="destino_perguntar").label == "Perguntar"
    assert at.button(key="destino_base").label == "Base de conhecimento"
    # Sem conversa, "Perguntas recentes" não aparece: nem o rótulo nem a lista.
    assert "Perguntas recentes" not in _html_da_barra(at)
    assert _recentes(at) == []
    # A contagem e os documentos ficam só na tela da base.
    assert "documentos" not in _html_da_barra(at)
    assert not any(str(b.key).startswith("menu_documento_") for b in at.button)


def test_icones_da_acao_e_dos_destinos_sao_os_do_material(montagens: Montagens) -> None:
    at = _abrir()

    assert at.button(key="nova_conversa").proto.icon == ":material/add:"
    assert at.button(key="destino_perguntar").proto.icon == ":material/chat:"
    assert at.button(key="destino_base").proto.icon == ":material/menu_book:"


def test_rotulos_da_barra_nao_tem_sufixo_aberto(montagens: Montagens) -> None:
    at = _clicar(_abrir(), "destino_base")

    rotulos = [str(b.label) for b in at.sidebar.button]
    assert rotulos == ["Nova conversa", "Perguntar", "Base de conhecimento"]
    assert not any("aberto" in rotulo for rotulo in rotulos)


def test_recentes_fica_depois_da_base_com_divisor_e_rotulo(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert "Perguntas recentes" in _html_da_barra(at)
    assert "agri-divisor" in _html_da_barra(at)
    assert [str(b.key) for b in at.sidebar.button] == [*NAV_CHAVES, "recente_0"]


def test_clicar_em_base_abre_a_lista_no_lugar_do_chat(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    _clicar(at, "destino_base")

    html_pagina = _html_da_pagina(at)
    assert "Base de conhecimento" in html_pagina
    assert "3 documentos oficiais que respondem às perguntas" in html_pagina
    # Chat, perguntas frequentes e respostas não aparecem; os três cartões sim.
    assert _autores(at) == []
    assert not any(str(b.key).startswith("sugestao_") for b in at.button)
    assert [b.key for b in at.button if str(b.key).startswith("cartao_")] == [
        "cartao_0",
        "cartao_1",
        "cartao_2",
    ]
    cartao = at.button(key="cartao_0").label
    assert "**Política de reembolso**" in cartao
    assert "FIN\\-POL\\-001 · v1\\.0" in cartao
    assert "Politica\\_Reembolso\\.pdf" in cartao
    assert "3 seções" in cartao
    # Destino ativo: só "Base de conhecimento", com destaque (primary).
    assert at.button(key="destino_base").proto.type == "primary"
    assert at.button(key="destino_perguntar").proto.type == "secondary"
    assert at.button(key="recente_0").proto.type == "secondary"


def test_perguntar_volta_ao_chat_e_preserva_a_conversa_e_o_rascunho(
    montagens: Montagens,
) -> None:
    at = _abrir()
    _perguntar(at, "Primeira pergunta?")
    _perguntar(at, "Segunda pergunta?")
    antes = _respostas_em_html(at)

    _clicar(at, "destino_base")
    _clicar(at, "cartao_1")
    _clicar(at, "destino_perguntar")

    assert _respostas_em_html(at) == antes
    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE] * 2
    assert montagens.assistente.perguntas == ["Primeira pergunta?", "Segunda pergunta?"]
    assert montagens.chamadas == 1
    assert at.text_input[0].label == ROTULO_PERGUNTA
    assert at.button(key="destino_perguntar").proto.type == "primary"
    assert at.button(key="destino_base").proto.type == "secondary"


def test_destino_ativo_e_sempre_um_so(montagens: Montagens) -> None:
    at = _abrir()
    assert at.button(key="destino_perguntar").proto.type == "primary"
    assert at.button(key="destino_base").proto.type == "secondary"

    _clicar(at, "destino_base")
    _clicar(at, "cartao_0")

    assert at.button(key="destino_perguntar").proto.type == "secondary"
    assert at.button(key="destino_base").proto.type == "primary"


def test_recente_volta_ao_chat_sem_perder_a_conversa(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")
    _clicar(at, "destino_base")

    _clicar(at, "recente_0")

    assert len(_respostas_em_html(at)) == 1
    assert _autores(at) == [ROTULO_USUARIO, ROTULO_ASSISTENTE]
    # Nenhum recente fica destacado; o destino ativo é "Perguntar".
    assert at.button(key="recente_0").proto.type == "secondary"
    assert at.button(key="destino_perguntar").proto.type == "primary"


def test_recentes_mostram_pergunta_completa_escapada_com_dica(montagens: Montagens) -> None:
    at = _abrir()
    _perguntar(at, "primeira")
    _perguntar(at, "<b>" + "x" * 80)

    rotulo = at.button(key="recente_1").label
    assert rotulo == "\\<b\\>" + "x" * 80
    assert "…" not in rotulo
    assert at.button(key="recente_1").help == rotulo
    assert at.button(key="recente_0").label == "primeira"
    assert at.button(key="recente_1").proto.type == "secondary"
    assert at.button(key="recente_0").proto.type == "secondary"


def test_recentes_mostram_so_as_dez_ultimas_e_a_conversa_guarda_todas(
    montagens: Montagens,
) -> None:
    at = _abrir()
    for numero in range(12):
        _perguntar(at, f"pergunta {numero}")

    assert _recentes(at) == [f"recente_{i}" for i in range(11, 1, -1)]
    assert len(_respostas_em_html(at)) == 12
    assert montagens.assistente.perguntas[-1] == "pergunta 11"


def test_nova_conversa_zera_a_conversa_o_campo_e_volta_ao_chat(montagens: Montagens) -> None:
    at = _perguntar(_abrir(), "Primeira?")
    _clicar(at, "destino_base")
    at.text_input[0].input("rascunho")

    _clicar(at, "nova_conversa")

    assert TITULO_BOAS_VINDAS in _html_da_pagina(at)
    assert _respostas_em_html(at) == []
    assert _recentes(at) == []
    assert "Perguntas recentes" not in _html_da_barra(at)
    assert at.text_input[0].value == ""
    assert any(str(b.key).startswith("sugestao_") for b in at.button)
    assert at.button(key="destino_perguntar").proto.type == "primary"
    assert at.button(key="destino_base").proto.type == "secondary"
    # Sem recarga: o assistente não é montado de novo.
    assert montagens.chamadas == 1


def test_nova_conversa_e_botao_sem_destaque_e_sem_link(montagens: Montagens) -> None:
    at = _abrir()

    assert at.button(key="nova_conversa").proto.type == "secondary"
    assert "<a " not in _html_da_barra(at)


def test_clicar_num_documento_mostra_cabecalho_e_secoes_em_ordem(montagens: Montagens) -> None:
    at = _abrir()

    at = _clicar(_clicar(_abrir(), "destino_base"), "cartao_1")

    html_pagina = _html_da_pagina(at)
    assert "<h2>Política de veículos</h2>" in html_pagina
    assert "FRO-POL-002 · v1.0" in html_pagina
    assert "Politica_Veiculos.pdf" in html_pagina
    assert "<h3>1 Objetivo</h3>" in html_pagina
    assert "<h3>2 Prazo</h3>" in html_pagina
    assert html_pagina.index("Objetivo") < html_pagina.index("Prazo")
    assert "<p>Primeira linha<br>Segunda linha</p>" in html_pagina
    assert ">Pergunta frequente<" in html_pagina
    assert "Voltar à lista" in [b.label for b in at.button]
    assert "Voltar ao chat" in [b.label for b in at.button]
    # A barra continua com a seção "Base de conhecimento" destacada, sem itens por documento.
    assert at.button(key="destino_base").proto.type == "primary"
    assert "(aberto)" not in _html_da_barra(at)
    assert _botoes_da_barra(at) == NAV_CHAVES
    assert _autores(at) == []


def test_voltar_a_lista_e_do_documento_e_da_lista_ao_chat(montagens: Montagens) -> None:
    at = _abrir()
    _clicar(at, "destino_base")
    _clicar(at, "cartao_0")

    _clicar(at, "voltar_lista")
    assert "3 documentos oficiais" in _html_da_pagina(at)
    assert "<h3>" not in _html_da_pagina(at)

    _clicar(at, "voltar_chat")
    assert TITULO_BOAS_VINDAS in _html_da_pagina(at)
    assert any(str(b.key).startswith("sugestao_") for b in at.button)


def test_a_entrada_continua_montada_na_tela_da_base_para_nao_perder_o_texto(
    montagens: Montagens,
) -> None:
    at = _clicar(_abrir(), "destino_base")

    assert [campo.label for campo in at.text_input] == [ROTULO_PERGUNTA]
    assert "tela_base" in _css_da_pagina(at)
    assert ":has(.st-key-tela_base) .st-key-entrada" in _css_da_pagina(at)


def test_texto_hostil_do_documento_e_escapado_na_visualizacao(
    montagens: Montagens, leitura: LeituraFalsa
) -> None:
    hostil = '<img src=x onerror="alert(1)"> <script>x</script> [a](http://exemplo.invalido)'
    leitura.conteudos["Politica_Reembolso.pdf"] = _conteudo(
        "Politica_Reembolso.pdf",
        hostil,
        (composicao.SecaoDoDocumento(hostil, hostil, hostil + "\n\n" + hostil, "faq"),),
    )

    at = _clicar(_clicar(_abrir(), "destino_base"), "cartao_0")

    html_pagina = _html_da_pagina(at)
    assert "<img" not in html_pagina
    assert "<script>x" not in html_pagina
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html_pagina
    assert "<a " not in re.sub(r'<a href="#agri-sec-\d+">', "", html_pagina)


@pytest.mark.parametrize("falha", ["none", "erro"])
def test_documento_indisponivel_mostra_mensagem_fixa_sem_detalhes(
    montagens: Montagens, leitura: LeituraFalsa, falha: str
) -> None:
    if falha == "none":
        leitura.conteudos["Politica_Reembolso.pdf"] = None
    else:
        leitura.erro = RuntimeError(f"/segredo/{CHAVE_DE_TESTE}.pdf Traceback")

    at = _clicar(_clicar(_abrir(), "destino_base"), "cartao_0")

    texto = _conteudo_da_pagina(at)
    assert TEXTO_DOCUMENTO_ERRO in _html_da_pagina(at)
    assert "/segredo" not in texto
    assert CHAVE_DE_TESTE not in texto
    assert "Traceback" not in texto
    assert len(at.error) == 0
    assert "Voltar à lista" in [b.label for b in at.button]


def test_documento_indisponivel_nao_fica_em_cache(
    montagens: Montagens, leitura: LeituraFalsa
) -> None:
    arquivo = "Politica_Reembolso.pdf"
    leitura.conteudos[arquivo] = None
    at = _clicar(_clicar(_abrir(), "destino_base"), "cartao_0")
    assert TEXTO_DOCUMENTO_ERRO in _html_da_pagina(at)

    leitura.conteudos[arquivo] = _conteudo(arquivo, "FIN-POL-001")
    _clicar(at, "voltar_lista")
    at = _clicar(at, "cartao_0")

    assert TEXTO_DOCUMENTO_ERRO not in _html_da_pagina(at)
    assert "<h3>1 Objetivo</h3>" in _html_da_pagina(at)


def test_arquivo_fora_da_lista_nunca_e_lido(montagens: Montagens, leitura: LeituraFalsa) -> None:
    at = _abrir()
    at.session_state["tela_atual"] = "documento"
    at.session_state["documento_aberto"] = "../../segredo.pdf"

    at.run()

    assert not at.exception
    assert TEXTO_DOCUMENTO_ERRO in _html_da_pagina(at)
    assert "../../segredo.pdf" not in _conteudo_da_pagina(at).replace("\\", "")
    assert "../../segredo.pdf" not in leitura.chamadas


def test_estado_de_tela_invalido_cai_no_chat(montagens: Montagens) -> None:
    at = _abrir()
    at.session_state["tela_atual"] = "qualquer coisa"

    at.run()

    assert not at.exception
    assert TITULO_BOAS_VINDAS in _html_da_pagina(at)


def test_cada_documento_e_lido_uma_vez_apesar_dos_reruns(
    montagens: Montagens, leitura: LeituraFalsa
) -> None:
    at = _clicar(_abrir(), "destino_base")
    _clicar(at, "cartao_0")
    _clicar(at, "voltar_lista")
    _clicar(at, "cartao_0")
    _clicar(at, "voltar_chat")
    _perguntar(at, "Outra pergunta?")

    assert sorted(leitura.chamadas) == sorted(d.arquivo for d in DOCUMENTOS)


def test_lista_vazia_mostra_aviso_so_na_tela_da_base(
    montagens: Montagens, listagem: ListagemFalsa
) -> None:
    listagem.documentos = ()
    at = _abrir()
    assert MENSAGEM_BASE_VAZIA not in _html_da_barra(at)
    assert _botoes_da_barra(at) == NAV_CHAVES

    _clicar(at, "destino_base")

    assert MENSAGEM_BASE_VAZIA in _html_da_pagina(at)
    assert not any(str(b.key).startswith("cartao_") for b in at.button)


@pytest.mark.parametrize(
    "erro", [ConfiguracaoInvalida("/segredo/.env sk-123"), RuntimeError("/x/y")]
)
def test_erro_ao_listar_nao_derruba_a_tela_nem_vaza_detalhes(
    montagens: Montagens, listagem: ListagemFalsa, erro: Exception
) -> None:
    listagem.erro = erro

    at = _perguntar(_abrir(), "Qual é o prazo de entrega?")

    assert not at.exception
    assert len(at.error) == 0
    assert MENSAGEM_BASE_ERRO not in _html_da_barra(at)
    assert "/segredo" not in _conteudo_da_pagina(at)
    assert "sk-123" not in _conteudo_da_pagina(at)
    assert len(_respostas_em_html(at)) == 1
    _clicar(at, "destino_base")
    assert MENSAGEM_BASE_ERRO in _html_da_pagina(at)


def test_menu_escapa_markdown_do_titulo_hostil(
    montagens: Montagens, listagem: ListagemFalsa
) -> None:
    listagem.documentos = (
        composicao.DocumentoDaBase("a.pdf", "[x](http://exemplo.invalido)", "<img src=x>", "*1*"),
    )

    at = _clicar(_abrir(), "destino_base")

    rotulo = at.button(key="cartao_0").label
    assert "\\<img src=x\\>" in rotulo
    assert "\\[x\\]\\(http://exemplo\\.invalido\\)" in rotulo
    assert not at.exception


def test_lista_da_base_e_lida_uma_vez_apesar_dos_reruns(
    montagens: Montagens, listagem: ListagemFalsa
) -> None:
    at = _abrir()
    _perguntar(at, "Primeira pergunta?")
    _perguntar(at, "Segunda pergunta?")
    _clicar(at, "destino_base")

    assert listagem.chamadas == 1
    assert "3 documentos oficiais" in _html_da_pagina(at)


def test_base_a_partir_de_um_documento_volta_a_lista(montagens: Montagens) -> None:
    # Base é a raiz da seção: estando num documento, o destino leva à lista, não ao chat.
    at = _clicar(_clicar(_abrir(), "destino_base"), "cartao_0")
    assert "<h3>1 Objetivo</h3>" in _html_da_pagina(at)

    _clicar(at, "destino_base")

    assert "3 documentos oficiais" in _html_da_pagina(at)
    assert "<h3>" not in _html_da_pagina(at)
    assert at.button(key="destino_base").proto.type == "primary"
    assert at.button(key="destino_perguntar").proto.type == "secondary"
