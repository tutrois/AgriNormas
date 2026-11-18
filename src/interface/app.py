"""Tela de perguntas do AgriNormas (HIST-019, TSK-019.1 a TSK-019.3).

Execute com `streamlit run src/interface/app.py`.

Este módulo só monta a página. O assistente é montado uma vez por processo com
`montar_assistente_do_ambiente` (TSK-019.3) e cada pergunta passa por `AssistenteRAG.responder`.
A página não conhece `config`: a configuração é carregada dentro de `composicao`.
Validação, recusa e fontes ficam no núcleo: não há regra de negócio aqui.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

# `streamlit run` coloca só a pasta deste arquivo no caminho de importação. Os pacotes
# (`composicao`, `config`, `nucleo`) ficam em `src/`, então a pasta é incluída aqui.
_PASTA_SRC: Final[Path] = Path(__file__).resolve().parents[1]
if str(_PASTA_SRC) not in sys.path:
    sys.path.insert(0, str(_PASTA_SRC))

import streamlit as st  # noqa: E402

from composicao import montar_assistente_do_ambiente  # noqa: E402
from nucleo.assistente import AssistenteRAG  # noqa: E402
from nucleo.erros import ErroAssistente  # noqa: E402
from nucleo.modelos import Fonte, Resposta  # noqa: E402

TITULO_PAGINA: Final[str] = "AgriNormas"
TITULO: Final[str] = "Perguntas sobre as normas"
DESCRICAO: Final[str] = (
    "Escreva sua pergunta. A resposta vem apenas dos documentos da base, "
    "e as fontes aparecem logo abaixo."
)
ROTULO_PERGUNTA: Final[str] = "Pergunta"
TEXTO_BOTAO_ENVIAR: Final[str] = "Enviar pergunta"
MENSAGEM_CARREGANDO: Final[str] = (
    "Buscando nos documentos. Na primeira vez, a preparação pode demorar um pouco."
)
ROTULO_FONTES: Final[str] = "Fontes"
MENSAGEM_ERRO_RESPOSTA: Final[str] = (
    "Não foi possível responder. Verifique a pergunta e tente novamente."
)

_CARACTERES_MARKDOWN: Final[dict[int, str]] = str.maketrans(
    {caractere: f"\\{caractere}" for caractere in "\\`*_{}[]()#+-.!|<>~$"}
)


@st.cache_resource(show_spinner=False)
def _assistente() -> AssistenteRAG:
    """Monta o assistente uma vez por processo. Erros não ficam em cache e são tentados de novo."""
    return montar_assistente_do_ambiente()


def _escapar_markdown(texto: str) -> str:
    """Impede que texto vindo dos PDFs (títulos, códigos) vire formatação ou link."""
    return texto.translate(_CARACTERES_MARKDOWN)


def _mostrar_fontes(resposta: Resposta) -> None:
    if not resposta.fontes:
        return
    st.subheader(ROTULO_FONTES)
    for fonte in resposta.fontes:
        st.markdown(f"- {_formatar_fonte(fonte)}")


def _formatar_fonte(fonte: Fonte) -> str:
    return _escapar_markdown(f"{fonte.documento}, seção {fonte.secao}: {fonte.titulo}")


def _mostrar_resposta(pergunta: str) -> None:
    try:
        with st.spinner(MENSAGEM_CARREGANDO):
            resposta = _assistente().responder(pergunta)
    except ErroAssistente:
        st.error(MENSAGEM_ERRO_RESPOSTA)
        return
    # Texto do modelo sai como texto puro: nada de Markdown, links ou imagens.
    st.text(resposta.texto)
    _mostrar_fontes(resposta)


def main() -> None:
    st.set_page_config(page_title=TITULO_PAGINA)
    st.title(TITULO)
    st.write(DESCRICAO)
    with st.form("formulario_pergunta"):
        pergunta = st.text_input(ROTULO_PERGUNTA)
        enviado = st.form_submit_button(TEXTO_BOTAO_ENVIAR)
    if enviado:
        _mostrar_resposta(pergunta)


main()
