"""Tela de perguntas do AgriNormas (HIST-019 e HIST-020).

Execute com `streamlit run src/interface/app.py`.

Este módulo só monta a página. O assistente é montado uma vez por processo com
`montar_assistente_do_ambiente` e cada pergunta passa por `AssistenteRAG.responder`.
A página não conhece `config`: a configuração é carregada dentro de `composicao`.
Validação, recusa e fontes ficam no núcleo: não há regra de negócio aqui. Em especial,
o limite de tamanho da pergunta é decidido pelo núcleo (`PerguntaInvalida`), não aqui.

Estados da tela (TSK-020.2):
- inicial: só o campo de pergunta;
- carregando: indicador enquanto a base é preparada e enquanto a pergunta é respondida;
- com evidência: título "Resposta", texto puro da resposta (quebra de linha no próprio texto,
  sem fonte monoespaçada) e fontes em um expansor;
- sem evidência: aviso informativo (`st.info`), sem fontes;
- pergunta inválida: aviso (`st.warning`) com a mensagem do núcleo;
- erro de configuração: orienta a conferir o `.env`, sem valores nem detalhes;
- erro de serviço e erro inesperado: mensagem genérica, sem rastreamento.
"""

from __future__ import annotations

import html
import logging
import sys
import traceback
from collections.abc import Callable
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
from nucleo.erros import ConfiguracaoInvalida, ErroAssistente, PerguntaInvalida  # noqa: E402
from nucleo.modelos import Fonte, Resposta  # noqa: E402

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

TITULO_PAGINA: Final[str] = "AgriNormas"
TITULO: Final[str] = "Perguntas sobre as normas"
DESCRICAO: Final[str] = (
    "Escreva sua pergunta. A resposta vem apenas dos documentos da base, "
    "e as fontes aparecem logo abaixo."
)
ROTULO_PERGUNTA: Final[str] = "Pergunta"
AJUDA_PERGUNTA: Final[str] = (
    "Escreva a pergunta em uma frase. A resposta vem só dos documentos da base."
)
TITULO_RESPOSTA: Final[str] = "Resposta"
CLASSE_RESPOSTA: Final[str] = "agrinormas-resposta"
# Layout: margem lateral de 16 px em tela estreita e quebra de linha do texto da resposta e
# do conteúdo das fontes (título ou código longo não pode criar rolagem horizontal).
# O CSS só ajusta a apresentação, sem recursos externos (sem `url(` nem `@import`).
# O conteúdo continua sendo texto escapado.
ESTILO_PAGINA: Final[str] = f"""
<style>
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"] {{
    padding-left: 16px;
    padding-right: 16px;
  }}
}}
.{CLASSE_RESPOSTA} {{
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {{
  overflow-wrap: anywhere;
}}
</style>
"""
TEXTO_BOTAO_ENVIAR: Final[str] = "Enviar pergunta"
MENSAGEM_PREPARANDO: Final[str] = (
    "Preparando a base de documentos. Na primeira vez, pode demorar um pouco."
)
MENSAGEM_BUSCANDO: Final[str] = "Buscando nos documentos..."
ROTULO_FONTES: Final[str] = "Ver fontes desta resposta"
ROTULO_CAMPO_CODIGO: Final[str] = "Código do documento"
ROTULO_CAMPO_SECAO: Final[str] = "Seção"
ROTULO_CAMPO_TITULO: Final[str] = "Título"
MENSAGEM_CONFIGURACAO: Final[str] = (
    "Não foi possível iniciar o assistente por causa da configuração. "
    "Confira o arquivo .env na pasta do projeto e atualize a página."
)
MENSAGEM_SERVICO: Final[str] = (
    "Não foi possível responder agora. O serviço pode estar indisponível. "
    "Tente novamente em instantes."
)
MENSAGEM_INESPERADA: Final[str] = (
    "Ocorreu um erro inesperado. Tente novamente. Se o problema continuar, avise a equipe."
)

_CARACTERES_MARKDOWN: Final[dict[int, str]] = str.maketrans(
    {caractere: f"\\{caractere}" for caractere in "\\`*_{}[]()#+-.!|<>~$"}
)


@st.cache_resource(show_spinner=False)
def _assistente() -> AssistenteRAG:
    """Monta o assistente uma vez por processo. Erros não ficam em cache e são tentados de novo."""
    return montar_assistente_do_ambiente()


def _escapar_markdown(texto: str) -> str:
    """Impede que texto vindo do núcleo ou dos PDFs (títulos, códigos) vire formatação ou link.

    Limitação conhecida: o escape não impede o autolink de URL e e-mail do GFM (`http://`,
    `www.`, `fulano@...`). Nesse caso a barra invertida aparece no texto do link. Ressalva
    aberta na M-59 do backlog. Não é tratada aqui.
    """
    return texto.translate(_CARACTERES_MARKDOWN)


def _mostrar_erro(erro: ErroAssistente) -> None:
    """Traduz uma exceção esperada do domínio em aviso ou erro para o usuário."""
    if isinstance(erro, PerguntaInvalida):
        # A mensagem vem do núcleo e descreve a regra (vazia ou longa demais).
        # O escape não impede autolink de URL e e-mail (M-59 do backlog).
        st.warning(_escapar_markdown(str(erro)))
    elif isinstance(erro, ConfiguracaoInvalida):
        st.error(MENSAGEM_CONFIGURACAO)
    else:
        st.error(MENSAGEM_SERVICO)


def _local_da_falha(erro: BaseException) -> str:
    """Arquivo, linha e função de cada quadro do traceback, sem a mensagem da exceção."""
    quadros = traceback.extract_tb(erro.__traceback__)
    if not quadros:
        return "local desconhecido"
    return " | ".join(f"{quadro.filename}:{quadro.lineno} em {quadro.name}" for quadro in quadros)


def _mostrar_erro_inesperado(erro: BaseException) -> None:
    """Registra no log a classe da exceção e o local da falha, e mostra só a mensagem genérica.

    A mensagem da exceção não é gravada: ela pode conter segredos (ex.: chave da API).
    Pelo mesmo motivo não há traceback no log, porque ele exibe a mensagem.
    """
    _LOG.error(
        "Erro inesperado na tela de perguntas: %s. Local: %s",
        type(erro).__name__,
        _local_da_falha(erro),
    )
    st.error(MENSAGEM_INESPERADA)


def _executar_com_tratamento[T](acao: Callable[[], T], mensagem_carregando: str) -> T | None:
    """Executa `acao` com indicador de progresso. Erros viram aviso ou erro e devolvem None."""
    try:
        with st.spinner(mensagem_carregando):
            return acao()
    except ErroAssistente as erro:
        _mostrar_erro(erro)
    except Exception as erro:
        _mostrar_erro_inesperado(erro)
    return None


def _formatar_fonte(fonte: Fonte) -> str:
    campos = (
        f"**{ROTULO_CAMPO_CODIGO}:** {_escapar_markdown(fonte.documento)}",
        f"**{ROTULO_CAMPO_SECAO}:** {_escapar_markdown(fonte.secao)}",
        f"**{ROTULO_CAMPO_TITULO}:** {_escapar_markdown(fonte.titulo)}",
    )
    return "- " + " · ".join(campos)


def _mostrar_fontes(fontes: tuple[Fonte, ...]) -> None:
    """Fontes ficam recolhidas em um expansor: um clique para abrir."""
    if not fontes:
        return
    with st.expander(ROTULO_FONTES):
        for fonte in fontes:
            st.markdown(_formatar_fonte(fonte))


def _mostrar_texto_puro(texto: str) -> None:
    """Mostra o texto literal: escapado em HTML, sem Markdown, links ou imagens.

    `st.text` usaria fonte monoespaçada e não quebraria linha em tela estreita.
    Escapar o HTML faz o texto virar só texto: nenhum elemento `<a>` ou `<img>` é criado.
    """
    st.html(f'<div class="{CLASSE_RESPOSTA}">{html.escape(texto)}</div>')


def _mostrar_resultado(resposta: Resposta) -> None:
    # `st.header` é h2: a página tem h1 (título) e não pula nível.
    st.header(TITULO_RESPOSTA)
    if not resposta.evidencia_suficiente:
        # Recusa do núcleo: aviso informativo, sem fontes e sem o formato de resposta normal.
        # O escape não impede autolink de URL e e-mail (M-59 do backlog).
        st.info(_escapar_markdown(resposta.texto))
        return
    _mostrar_texto_puro(resposta.texto)
    _mostrar_fontes(resposta.fontes)


def _mostrar_resposta(assistente: AssistenteRAG, pergunta: str) -> None:
    resposta = _executar_com_tratamento(lambda: assistente.responder(pergunta), MENSAGEM_BUSCANDO)
    if resposta is not None:
        _mostrar_resultado(resposta)


def main() -> None:
    st.set_page_config(page_title=TITULO_PAGINA)
    st.html(ESTILO_PAGINA)
    st.title(TITULO)
    st.write(DESCRICAO)
    assistente = _executar_com_tratamento(_assistente, MENSAGEM_PREPARANDO)
    if assistente is None:
        # Sem assistente não há o que perguntar: o erro já foi mostrado acima.
        return
    with st.form("formulario_pergunta"):
        pergunta = st.text_input(ROTULO_PERGUNTA, help=AJUDA_PERGUNTA)
        enviado = st.form_submit_button(TEXTO_BOTAO_ENVIAR)
    if enviado:
        _mostrar_resposta(assistente, pergunta)


main()
