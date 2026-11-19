"""Tela de perguntas do AgriNormas (HIST-019, HIST-020 e HIST-030).

Execute com `streamlit run src/interface/app.py`.

Este módulo só monta a página. O assistente é montado uma vez por processo com
`montar_assistente_do_ambiente` e cada pergunta passa por `AssistenteRAG.responder`.
A página não conhece `config`: a configuração é carregada dentro de `composicao`.
Validação, recusa e fontes ficam no núcleo: não há regra de negócio aqui. Em especial,
o limite de tamanho da pergunta é decidido pelo núcleo (`PerguntaInvalida`), não aqui.

Estilo (HIST-030, mockups aprovados): fica em `estilo.py`, e a marcação dos balões em
`marcacao.py`. Os dois são só apresentação.

Estados da tela:
- inicial: título de boas-vindas e o campo de pergunta;
- carregando: indicador enquanto a base é preparada e enquanto a pergunta é respondida;
- com evidência: balão da pergunta, balão da resposta (texto puro) e fontes em um expansor;
- sem evidência: balão da resposta com o selo "Sem evidência" (texto, sem cor de erro) e sem
  fontes;
- pergunta inválida: aviso (`st.warning`) com a mensagem do núcleo;
- erro de configuração: orienta a conferir o `.env`, sem valores nem detalhes;
- erro de serviço e erro inesperado: mensagem genérica, sem rastreamento.
"""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Final

# `streamlit run` coloca só a pasta deste arquivo no caminho de importação. Os pacotes
# (`composicao`, `config`, `nucleo`, `interface`) ficam em `src/`, então a pasta é incluída aqui.
_PASTA_SRC: Final[Path] = Path(__file__).resolve().parents[1]
if str(_PASTA_SRC) not in sys.path:
    sys.path.insert(0, str(_PASTA_SRC))

import streamlit as st  # noqa: E402

from composicao import montar_assistente_do_ambiente  # noqa: E402
from interface.estilo import CSS_PAGINA  # noqa: E402
from interface.marcacao import (  # noqa: E402
    ajuda_html,
    balao_assistente_html,
    balao_usuario_html,
    barra_lateral_html,
    boas_vindas_html,
    lista_conversas_html,
    rotulo_sugestoes_html,
    titulo_para_leitor_html,
)
from nucleo.assistente import AssistenteRAG  # noqa: E402
from nucleo.erros import ConfiguracaoInvalida, ErroAssistente, PerguntaInvalida  # noqa: E402
from nucleo.modelos import Fonte, Resposta  # noqa: E402

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

TITULO_PAGINA: Final[str] = "AgriNormas"
TITULO_BOAS_VINDAS: Final[str] = "Consulte as normas da empresa"
SUBTITULO_BOAS_VINDAS: Final[str] = "Respostas com fonte, vindas só dos documentos oficiais."
ROTULO_PERGUNTA: Final[str] = "Pergunta"
PLACEHOLDER_PERGUNTA: Final[str] = "Pergunte sobre as normas"
AJUDA_PERGUNTA: Final[str] = (
    "Escreva a pergunta em uma frase. A resposta vem só dos documentos da base."
)
CHAVE_TURNOS: Final[str] = "turnos_conversa"
CHAVE_SUGESTAO: Final[str] = "pergunta_sugerida"
ROTULO_SUGESTOES: Final[str] = "Perguntas frequentes"
TITULO_PAGINA_LEITOR: Final[str] = "Perguntas sobre as normas"
ROTULO_RECENTES: Final[str] = "Recentes"
# Cartões do estado inicial: (título, descrição, pergunta enviada ao clicar). Os títulos e as
# descrições são os nomes dos três documentos da base; a pergunta é só uma pergunta de partida.
SUGESTOES: Final[tuple[tuple[str, str, str], ...]] = (
    ("Reembolso", "Política de reembolso", "Como funciona o reembolso de despesas?"),
    ("Veículos", "Política de veículos", "Quais são as regras para uso de veículos?"),
    ("Férias", "Procedimento de férias", "Como funciona o procedimento de férias?"),
)
ROTULO_USUARIO: Final[str] = "Você"
ROTULO_ASSISTENTE: Final[str] = "Assistente"
ROTULO_SEM_EVIDENCIA: Final[str] = "Sem evidência"
# Ícone do Streamlit (fonte local). O texto do botão fica oculto na tela, mas continua no DOM.
ICONE_ENVIAR: Final[str] = ":material/arrow_upward:"
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

    Usado só onde a página ainda usa Markdown: avisos (`st.warning`) e títulos de fonte.
    Limitação conhecida: o escape não impede o autolink de URL e e-mail do GFM (`http://`,
    `www.`, `fulano@...`). Ressalva aberta na M-59 do backlog. Não é tratada aqui.
    """
    return texto.translate(_CARACTERES_MARKDOWN)


def _mostrar_erro(erro: ErroAssistente) -> None:
    """Traduz uma exceção esperada do domínio em aviso ou erro para o usuário."""
    if isinstance(erro, PerguntaInvalida):
        # A mensagem vem do núcleo e descreve a regra (vazia ou longa demais).
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


def _mostrar_fontes(fontes: tuple[Fonte, ...], indice: int) -> None:
    """Detalhes das fontes ficam recolhidos em um expansor, um por resposta (chave única)."""
    if not fontes:
        return
    with st.container(key=f"fontes_{indice}"), st.expander(ROTULO_FONTES):
        for fonte in fontes:
            st.markdown(_formatar_fonte(fonte))


def _mostrar_conversa(indice: int, pergunta: str, resposta: Resposta) -> None:
    """Balão da pergunta e balão da resposta. Sem evidência: selo no balão e nenhuma fonte."""
    st.html(balao_usuario_html(ROTULO_USUARIO, pergunta))
    if not resposta.evidencia_suficiente:
        # Recusa do núcleo: o texto é mostrado como veio, com o selo "Sem evidência" em texto.
        st.html(balao_assistente_html(ROTULO_ASSISTENTE, resposta.texto, ROTULO_SEM_EVIDENCIA))
        return
    chips = tuple(_resumo_fonte(fonte) for fonte in resposta.fontes)
    st.html(balao_assistente_html(ROTULO_ASSISTENTE, resposta.texto, chips=chips))
    _mostrar_fontes(resposta.fontes, indice)


def _resumo_fonte(fonte: Fonte) -> str:
    """Chip do balão: documento · seção, como no mockup."""
    return f"{fonte.documento} · {fonte.secao}"


def _escolher_sugestao(pergunta_pronta: str) -> None:
    """Callback do cartão: guarda a pergunta para a próxima execução da página."""
    st.session_state[CHAVE_SUGESTAO] = pergunta_pronta


def _mostrar_sugestoes() -> None:
    """Cartões do estado inicial. Cada um é um botão que envia a pergunta pronta.

    Os botões são alcançáveis por teclado e o nome do botão inclui a descrição, então leitores
    de tela leem o cartão inteiro. O clique só guarda a pergunta; ela é respondida depois.
    """
    # Rótulo e cartões no mesmo bloco, para ficarem alinhados e próximos.
    with st.container(key="bloco_sugestoes"):
        st.html(rotulo_sugestoes_html(ROTULO_SUGESTOES))
        _mostrar_cartoes()


def _mostrar_cartoes() -> None:
    with st.container(key="sugestoes", horizontal=True, wrap=False, gap="small"):
        for indice, (titulo, descricao, pergunta_pronta) in enumerate(SUGESTOES):
            rotulo = f"**{_escapar_markdown(titulo)}**  \n{_escapar_markdown(descricao)}"
            st.button(
                rotulo,
                key=f"sugestao_{indice}",
                width="stretch",
                on_click=_escolher_sugestao,
                args=(pergunta_pronta,),
            )


def _responder_e_guardar(
    assistente: AssistenteRAG, pergunta: str, turnos: list[tuple[str, Resposta]]
) -> None:
    """Responde a pergunta e guarda o par na conversa. Erros não entram na conversa."""
    resposta = _executar_com_tratamento(lambda: assistente.responder(pergunta), MENSAGEM_BUSCANDO)
    if resposta is not None:
        turnos.append((pergunta, resposta))


def main() -> None:
    st.set_page_config(page_title=TITULO_PAGINA)
    st.html(CSS_PAGINA)
    st.html(titulo_para_leitor_html(TITULO_PAGINA_LEITOR))
    assistente = _executar_com_tratamento(_assistente, MENSAGEM_PREPARANDO)
    if assistente is None:
        # Sem assistente não há o que perguntar: o erro já foi mostrado acima.
        return
    if CHAVE_TURNOS not in st.session_state:
        st.session_state[CHAVE_TURNOS] = []
    turnos: list[tuple[str, Resposta]] = st.session_state[CHAVE_TURNOS]
    # Pergunta de um cartão clicado na execução anterior (guardada pelo callback), se houver.
    sugerida: str | None = st.session_state.pop(CHAVE_SUGESTAO, None)
    # A conversa e a lista "Recentes" são preenchidas depois do envio, porque o campo e os
    # cartões só são lidos depois de desenhados. Por isso os blocos são criados antes.
    # `autoscroll` faz a área rolar até a última mensagem a cada envio. Com altura fixa, o
    # Streamlit só liga essa rolagem; a altura que vale é a do CSS (`estilo.py`), que ocupa o
    # espaço que sobra. Por isso o valor de `height` aqui é só o que liga a rolagem.
    area_conversa = st.container(key="conversa", height=ALTURA_CONVERSA_PARA_ROLAGEM, autoscroll=True)
    with st.sidebar:
        st.html(barra_lateral_html())
        area_lista = st.container(key="lista_conversas")
    # A entrada (campo e ajuda) é um bloco só, que fica fixo na base depois da primeira pergunta.
    with st.container(key="entrada"):
        with (
            st.form("formulario_pergunta", border=False),
            st.container(
                key="composer",
                horizontal=True,
                wrap=False,
                vertical_alignment="center",
                gap="small",
            ),
        ):
            pergunta = st.text_input(
                ROTULO_PERGUNTA,
                placeholder=PLACEHOLDER_PERGUNTA,
                label_visibility="collapsed",
            )
            enviado = st.form_submit_button(TEXTO_BOTAO_ENVIAR, icon=ICONE_ENVIAR)
        # A ajuda fica abaixo da caixa de pergunta. Com o rótulo do campo oculto, o Streamlit
        # também oculta o botão de ajuda do campo; por isso a ajuda é texto fixo, lido pelo leitor.
        with st.container(key="ajuda"):
            st.html(ajuda_html(AJUDA_PERGUNTA))
    # Os cartões só aparecem sem conversa e sem envio nesta execução. Um clique num cartão
    # chega pelo callback e é respondido abaixo, junto com o envio do campo.
    if not turnos and not enviado and sugerida is None:
        _mostrar_sugestoes()
    with area_conversa:
        if enviado:
            _responder_e_guardar(assistente, pergunta, turnos)
        elif sugerida is not None:
            _responder_e_guardar(assistente, sugerida, turnos)
        if not turnos and not enviado:
            st.html(boas_vindas_html(TITULO_BOAS_VINDAS, SUBTITULO_BOAS_VINDAS))
        for indice, (pergunta_anterior, resposta_anterior) in enumerate(turnos):
            _mostrar_conversa(indice, pergunta_anterior, resposta_anterior)
    if turnos:
        with area_lista:
            st.html(lista_conversas_html([pergunta for pergunta, _ in turnos], ROTULO_RECENTES))


main()
