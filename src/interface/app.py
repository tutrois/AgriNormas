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
from typing import Final, Literal

# `streamlit run` coloca só a pasta deste arquivo no caminho de importação. Os pacotes
# (`composicao`, `config`, `nucleo`, `interface`) ficam em `src/`, então a pasta é incluída aqui.
_PASTA_SRC: Final[Path] = Path(__file__).resolve().parents[1]
if str(_PASTA_SRC) not in sys.path:
    sys.path.insert(0, str(_PASTA_SRC))

import streamlit as st  # noqa: E402
from streamlit.delta_generator import DeltaGenerator  # noqa: E402

from composicao import (  # noqa: E402
    ConteudoDoDocumento,
    DocumentoDaBase,
    ler_documento_do_ambiente,
    listar_documentos_do_ambiente,
    montar_assistente_do_ambiente,
)
from interface.estilo import CSS_PAGINA  # noqa: E402
from interface.marcacao import (  # noqa: E402
    ajuda_html,
    aviso_base_html,
    balao_assistente_html,
    balao_usuario_html,
    barra_lateral_html,
    boas_vindas_html,
    cabecalho_da_base_html,
    contagem_de_secoes,
    documento_html,
    meta_do_documento,
    remover_citacoes,
    resumir,
    rotulo_lista_html,
    rotulo_sugestoes_html,
    titulo_legivel,
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
# Altura passada ao Streamlit só para ligar a rolagem automática. A altura real é do CSS.
ALTURA_CONVERSA_PARA_ROLAGEM: Final[int] = 400
ROTULO_SUGESTOES: Final[str] = "Perguntas frequentes"
TITULO_PAGINA_LEITOR: Final[str] = "Perguntas sobre as normas"
ROTULO_RECENTES: Final[str] = "Recentes"
ROTULO_BASE: Final[str] = "Base de conhecimento"
TEXTO_BASE_VAZIA: Final[str] = "Nenhum documento encontrado na base."
TEXTO_BASE_ERRO: Final[str] = "Não foi possível listar os documentos."
TEXTO_DOCUMENTO_ERRO: Final[str] = "Não foi possível abrir este documento."
TEXTO_DOCUMENTO_SEM_SECOES: Final[str] = "Este documento não tem seções para mostrar."
SUBTITULO_BASE_UM: Final[str] = "1 documento oficial que responde às perguntas"
SUBTITULO_BASE_VARIOS: Final[str] = "{quantidade} documentos oficiais que respondem às perguntas"
ROTULO_VOLTAR_CHAT: Final[str] = "Voltar ao chat"
ROTULO_VOLTAR_LISTA: Final[str] = "Voltar à lista"
ROTULO_INDICE: Final[str] = "Seções deste documento"
ROTULO_FAQ: Final[str] = "Pergunta frequente"
# O Streamlit não deixa pôr `aria-current` num botão. O estado atual vai no rótulo (lido por
# leitores de tela) e no destaque visual do botão ativo (`type="primary"`).
SUFIXO_ATIVO: Final[str] = " (aberto)"
TELA_CHAT: Final[str] = "chat"
TELA_BASE: Final[str] = "base"
TELA_DOCUMENTO: Final[str] = "documento"
CHAVE_TELA: Final[str] = "tela_atual"
CHAVE_DOCUMENTO: Final[str] = "documento_aberto"
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
MENSAGEM_ABRINDO_BASE: Final[str] = "Abrindo os documentos..."
# Quebra de linha do Markdown (dois espaços e \n) nos rótulos de botão.
QUEBRA_DE_LINHA: Final[str] = "  \n"
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


@st.cache_data(show_spinner=False)
def _documentos_da_base() -> tuple[DocumentoDaBase, ...]:
    """Lê a lista de documentos uma vez por processo. Erros não ficam em cache."""
    return listar_documentos_do_ambiente()


class _DocumentoIndisponivel(Exception):
    """Interna: faz o `st.cache_data` não guardar o resultado vazio (exceção não entra no cache)."""


@st.cache_data(show_spinner=False)
def _conteudo_do_documento(arquivo: str) -> ConteudoDoDocumento:
    """Lê um documento uma vez por arquivo. Indisponível (None) e erros não ficam em cache."""
    conteudo = ler_documento_do_ambiente(arquivo)
    if conteudo is None:
        raise _DocumentoIndisponivel
    return conteudo


def _conteudo_ou_none(arquivo: str) -> ConteudoDoDocumento | None:
    """Conteúdo para a tela. Qualquer falha vira None e não derruba a página."""
    try:
        return _conteudo_do_documento(arquivo)
    except _DocumentoIndisponivel:
        return None
    except Exception as erro:
        # Só a classe vai ao log: a mensagem pode conter caminho ou segredo.
        _LOG.warning("Não foi possível ler o documento: %s", type(erro).__name__)
        return None


def _documentos_ou_none() -> tuple[DocumentoDaBase, ...] | None:
    """Lista da base para as telas da base. Qualquer falha vira None e não derruba a página."""
    try:
        return _documentos_da_base()
    except Exception as erro:
        # Só a classe vai ao log: a mensagem pode conter caminho ou segredo.
        _LOG.warning("Não foi possível listar os documentos: %s", type(erro).__name__)
        return None


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
    st.html(balao_assistente_html(ROTULO_ASSISTENTE, remover_citacoes(resposta.texto), chips=chips))
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


def _ir_para_chat() -> None:
    """Callback: volta ao chat. A conversa fica no `session_state` e não é perdida."""
    st.session_state[CHAVE_TELA] = TELA_CHAT


def _ir_para_base() -> None:
    """Callback: abre a lista de documentos no lugar do chat."""
    st.session_state[CHAVE_TELA] = TELA_BASE
    st.session_state.pop(CHAVE_DOCUMENTO, None)


def _ir_para_documento(arquivo: str) -> None:
    """Callback: abre um documento. O nome vem sempre da lista da base, nunca de texto digitado."""
    st.session_state[CHAVE_TELA] = TELA_DOCUMENTO
    st.session_state[CHAVE_DOCUMENTO] = arquivo


def _tipo_do_botao(ativo: bool) -> Literal["primary", "secondary"]:
    return "primary" if ativo else "secondary"


def _mostrar_menu_base(tela: str) -> None:
    """Item "Base de conhecimento" da barra lateral: um botão que abre a lista de documentos.

    Botões do Streamlit mudam só o `session_state`, então a conversa não se perde. É um
    elemento nativo, alcançável por teclado. Fica destacado (`type="primary"`) enquanto a
    tela da base estiver aberta, inclusive quando um documento está aberto nela.
    """
    with st.container(key="menu_base"):
        ativa = tela in (TELA_BASE, TELA_DOCUMENTO)
        rotulo = _escapar_markdown(ROTULO_BASE + (SUFIXO_ATIVO if ativa else ""))
        st.button(
            rotulo,
            key="menu_base_titulo",
            type=_tipo_do_botao(ativa),
            width="stretch",
            on_click=_ir_para_base,
        )


def _mostrar_recentes(turnos: list[tuple[str, Resposta]], em_chat: bool) -> None:
    """Seção "Recentes" da barra lateral. Sem perguntas, não mostra rótulo nem lista.

    Cada pergunta é um botão que volta ao chat. A última fica destacada, só no chat.
    """
    if not turnos:
        return
    with st.sidebar, st.container(key="lista_conversas"):
        st.html(rotulo_lista_html(ROTULO_RECENTES))
        ultima = len(turnos) - 1
        for indice in range(ultima, -1, -1):
            st.button(
                _escapar_markdown(resumir(turnos[indice][0])),
                key=f"recente_{indice}",
                type=_tipo_do_botao(em_chat and indice == ultima),
                width="stretch",
                on_click=_ir_para_chat,
            )


def _botoes_de_volta(*, com_lista: bool) -> None:
    """Botões de volta no topo da tela da base. Na tela de documento, inclui "Voltar à lista"."""
    with st.container(key="voltar_base", horizontal=True, wrap=True, gap="small"):
        if com_lista:
            st.button(
                ROTULO_VOLTAR_LISTA,
                key="voltar_lista",
                icon=":material/arrow_back:",
                on_click=_ir_para_base,
            )
        st.button(
            ROTULO_VOLTAR_CHAT,
            key="voltar_chat",
            icon=":material/chat:" if com_lista else ":material/arrow_back:",
            on_click=_ir_para_chat,
        )


def _rotulo_do_cartao(documento: DocumentoDaBase) -> str:
    """Cartão da lista: título, código · versão, arquivo e número de seções (se o PDF abrir)."""
    titulo = titulo_legivel(documento.titulo) or documento.arquivo
    linhas = [f"**{_escapar_markdown(titulo)}**"]
    meta = meta_do_documento(documento.codigo, documento.versao)
    if meta:
        linhas.append(_escapar_markdown(meta))
    if documento.arquivo:
        linhas.append(_escapar_markdown(documento.arquivo))
    conteudo = _conteudo_ou_none(documento.arquivo)
    if conteudo is not None:
        linhas.append(_escapar_markdown(contagem_de_secoes(len(conteudo.secoes))))
    return QUEBRA_DE_LINHA.join(linhas)


def _mostrar_lista_da_base(documentos: tuple[DocumentoDaBase, ...] | None) -> None:
    _botoes_de_volta(com_lista=False)
    quantidade = len(documentos or ())
    if quantidade == 0:
        st.html(cabecalho_da_base_html(ROTULO_BASE, ""))
        st.html(aviso_base_html(TEXTO_BASE_VAZIA if documentos is not None else TEXTO_BASE_ERRO))
        return
    subtitulo = (
        SUBTITULO_BASE_UM
        if quantidade == 1
        else SUBTITULO_BASE_VARIOS.format(quantidade=quantidade)
    )
    st.html(cabecalho_da_base_html(ROTULO_BASE, subtitulo))
    with st.container(key="grade_base", horizontal=True, wrap=True, gap="small"):
        for indice, documento in enumerate(documentos or ()):
            st.button(
                _rotulo_do_cartao(documento),
                key=f"cartao_{indice}",
                width="stretch",
                on_click=_ir_para_documento,
                args=(documento.arquivo,),
            )


def _mostrar_documento(documentos: tuple[DocumentoDaBase, ...] | None, arquivo: str | None) -> None:
    """Tela de um documento. Só abre arquivos que estão na lista da base."""
    _botoes_de_volta(com_lista=True)
    permitido = arquivo is not None and any(d.arquivo == arquivo for d in documentos or ())
    conteudo = _conteudo_ou_none(arquivo) if permitido and arquivo is not None else None
    if conteudo is None:
        st.html(aviso_base_html(TEXTO_DOCUMENTO_ERRO))
        return
    st.html(documento_html(conteudo, ROTULO_INDICE, ROTULO_FAQ, TEXTO_DOCUMENTO_SEM_SECOES))


def _mostrar_tela_da_base(
    tela: str, documentos: tuple[DocumentoDaBase, ...] | None, aberto: str | None
) -> None:
    with st.spinner(MENSAGEM_ABRINDO_BASE):
        if tela == TELA_DOCUMENTO:
            _mostrar_documento(documentos, aberto)
        else:
            _mostrar_lista_da_base(documentos)


def _mostrar_chat(
    assistente: AssistenteRAG,
    turnos: list[tuple[str, Resposta]],
    area_conversa: DeltaGenerator,
    pergunta: str,
    enviado: bool,
    sugerida: str | None,
) -> None:
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


def _tela_atual() -> str:
    """Tela guardada na sessão. Valor desconhecido ou documento ausente volta para a tela segura."""
    tela = st.session_state.get(CHAVE_TELA, TELA_CHAT)
    if tela == TELA_DOCUMENTO and not st.session_state.get(CHAVE_DOCUMENTO):
        return TELA_BASE
    return tela if tela in (TELA_CHAT, TELA_BASE, TELA_DOCUMENTO) else TELA_CHAT


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
    tela = _tela_atual()
    aberto: str | None = st.session_state.get(CHAVE_DOCUMENTO)
    em_chat = tela == TELA_CHAT
    documentos = _documentos_ou_none()
    # A conversa é preenchida depois do envio, porque o campo e os cartões só são lidos depois
    # de desenhados. Por isso o bloco é criado antes.
    # `autoscroll` faz a área rolar até a última mensagem a cada envio. Com altura fixa, o
    # Streamlit só liga essa rolagem; a altura que vale é a do CSS (`estilo.py`), que ocupa o
    # espaço que sobra. Por isso o valor de `height` aqui é só o que liga a rolagem.
    # Nas telas da base, o mesmo lugar recebe a tela (`tela_base`) no lugar do chat.
    area_principal = (
        st.container(
            key="conversa", height=ALTURA_CONVERSA_PARA_ROLAGEM, autoscroll=True, border=False
        )
        if em_chat
        else st.container(key="tela_base")
    )
    # Ordem da barra: marca, "Nova conversa", "Base de conhecimento" e, por último, "Recentes"
    # (esta última é desenhada depois do envio, em `_mostrar_recentes`, e vai para o fim).
    with st.sidebar:
        st.html(barra_lateral_html())
        _mostrar_menu_base(tela)
    # A entrada (campo e ajuda) é um bloco só, que fica fixo na base depois da primeira pergunta.
    # Nas telas da base ela continua desenhada, mas escondida pelo CSS: assim o campo não é
    # desmontado e o texto já digitado não se perde ao ir e voltar.
    with st.container(key="entrada"):
        with (
            st.form("formulario_pergunta", border=False, clear_on_submit=True),
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
    if em_chat:
        _mostrar_chat(assistente, turnos, area_principal, pergunta, enviado, sugerida)
    else:
        with area_principal:
            _mostrar_tela_da_base(tela, documentos, aberto)
    _mostrar_recentes(turnos, em_chat)


main()
