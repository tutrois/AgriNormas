"""Marcação HTML dos blocos da tela: topo, barra lateral, boas-vindas e balões (HIST-030).

Todo texto que vem do usuário ou do núcleo passa por `html.escape`, então vira texto: nenhum
elemento `<a>` (exceto o link fixo "Nova conversa" e os links `#agri-sec-N` do índice do
documento, com destino gerado aqui), `<img>` ou `<script>` é criado a partir dele. Este módulo
só organiza o que a página recebe. Não decide nada sobre a pergunta nem sobre a resposta.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Sequence
from typing import Final, Protocol

from interface.estilo import TEXTO_MARCA

CLASSE_RESPOSTA: Final[str] = "agrinormas-resposta"
ROTULO_NOVA_CONVERSA: Final[str] = "Nova conversa"
DESTINO_NOVA_CONVERSA: Final[str] = "./"
ROTULO_CHIPS_LEITOR: Final[str] = "Fontes:"
TIPO_FAQ: Final[str] = "faq"
PREFIXO_ID_SECAO: Final[str] = "agri-sec-"


class SecaoLida(Protocol):
    """O que a tela precisa de cada seção (satisfeito por `SecaoDoDocumento`)."""

    @property
    def numero(self) -> str: ...
    @property
    def titulo(self) -> str: ...
    @property
    def texto(self) -> str: ...
    @property
    def tipo(self) -> str: ...


class ConteudoLido(Protocol):
    """O que a tela precisa de um documento lido (satisfeito por `ConteudoDoDocumento`)."""

    @property
    def arquivo(self) -> str: ...
    @property
    def codigo(self) -> str: ...
    @property
    def titulo(self) -> str: ...
    @property
    def versao(self) -> str: ...
    @property
    def secoes(self) -> Sequence[SecaoLida]: ...


# Citação do núcleo: `[FIN-POL-001 §3.1]`, `[FIN-POL-001 §faq-5]`. Outros colchetes não casam.
_CITACAO: Final[str] = r"\[[A-Za-z0-9][A-Za-z0-9_-]*\s*§\s*[A-Za-z0-9][A-Za-z0-9._-]*\]"
_SEQUENCIA_CITACOES: Final[re.Pattern[str]] = re.compile(rf"[ \t]*(?:{_CITACAO}[ \t]*)+")
_ESPACOS_REPETIDOS: Final[re.Pattern[str]] = re.compile(r"(?<=\S)[ \t]{2,}")
_ESPACO_NO_FIM_DA_LINHA: Final[re.Pattern[str]] = re.compile(r"[ \t]+$", re.MULTILINE)


def remover_citacoes(texto: str) -> str:
    """Tira do texto as citações `[CÓDIGO §SEÇÃO]`, só para exibição.

    Os chips de fontes são a referência visível. Cuida do espaçamento: sem espaço duplo, sem
    espaço antes de pontuação e sem espaço sobrando no fim. Se nada sobrar, devolve o original.
    """

    def _substituir(achado: re.Match[str]) -> str:
        depois = texto[achado.end() : achado.end() + 1]
        antes = texto[: achado.start()]
        if not antes.strip() or not depois or depois in ".,;:!?)" or depois.isspace():
            return ""
        return " "

    limpo = _SEQUENCIA_CITACOES.sub(_substituir, texto)
    limpo = _ESPACOS_REPETIDOS.sub(" ", limpo)
    limpo = _ESPACO_NO_FIM_DA_LINHA.sub("", limpo).strip()
    return limpo or texto


def _avatar(variante: str) -> str:
    """Avatar decorativo, desenhado em CSS. O autor já aparece em texto para leitores de tela."""
    return f'<span class="agri-avatar agri-avatar-{variante}" aria-hidden="true"></span>'


def _rotulo_so_leitor(rotulo: str) -> str:
    """Rótulo do autor: fica fora da tela, mas continua no texto lido por leitores de tela."""
    return f'<span class="agri-autor agri-so-leitor">{html.escape(rotulo)}</span>'


def barra_lateral_html() -> str:
    """Marca e ação "Nova conversa" no topo da barra lateral.

    O link é uma ação real e precisa ser alcançável por teclado, por isso não fica oculto.
    Ao abrir o link, a página recarrega e a conversa começa de novo.
    """
    return (
        '<div class="agri-marca-bloco">'
        f'<span class="agri-marca" aria-hidden="true">{html.escape(TEXTO_MARCA)}</span>'
        "<span>AgriNormas</span></div>"
        f'<a class="agri-nova" href="{DESTINO_NOVA_CONVERSA}">'
        f"{html.escape(ROTULO_NOVA_CONVERSA)}</a>"
    )


def titulo_legivel(titulo: str) -> str:
    """Títulos todo em caixa alta (ex.: "POLÍTICA DE REEMBOLSO") viram caixa de frase.

    Títulos que já têm minúsculas ficam como estão, para não estragar siglas e nomes próprios.
    """
    limpo = " ".join(titulo.split())
    if limpo.isupper():
        limpo = limpo.lower()
    return limpo[:1].upper() + limpo[1:]


def meta_do_documento(codigo: str, versao: str) -> str:
    """ "CÓDIGO · v1.0" em texto puro. A versão ganha o prefixo "v"; partes vazias somem."""
    return " · ".join(p for p in (codigo, f"v{versao}" if versao else "") if p)


def contagem_de_secoes(quantidade: int) -> str:
    return "1 seção" if quantidade == 1 else f"{quantidade} seções"


def aviso_base_html(texto: str) -> str:
    """Aviso discreto (lista vazia, lista indisponível, documento indisponível)."""
    return f'<p class="agri-base-aviso">{html.escape(texto)}</p>'


def rotulo_lista_html(texto: str) -> str:
    """Rótulo cinza pequeno da barra lateral (ex.: "Recentes")."""
    return f'<p class="agri-lista-rotulo">{html.escape(texto)}</p>'


def cabecalho_da_base_html(titulo: str, subtitulo: str) -> str:
    """Título e subtítulo da tela "Base de conhecimento"."""
    return (
        '<header class="agri-tela-cabecalho">'
        f"<h2>{html.escape(titulo)}</h2>"
        f"<p>{html.escape(subtitulo)}</p></header>"
    )


def _paragrafos(texto: str) -> str:
    """Texto do documento como parágrafos: linha em branco separa parágrafos, "\n" vira <br>.

    O texto é dado, não marcação: tudo passa por `html.escape` e nada além de `<p>` e `<br>`
    é criado a partir dele.
    """
    blocos = re.split(r"\n\s*\n", texto.replace("\r\n", "\n").replace("\r", "\n"))
    saida = []
    for bloco in blocos:
        limpo = bloco.strip()
        if limpo:
            saida.append(f"<p>{html.escape(limpo).replace(chr(10), '<br>')}</p>")
    return "".join(saida)


def _rotulo_da_secao(secao: SecaoLida) -> str:
    return " ".join(parte for parte in (secao.numero.strip(), secao.titulo.strip()) if parte)


def _bloco_da_secao(indice: int, secao: SecaoLida, rotulo_faq: str) -> str:
    # O `id` vem do índice da seção, nunca do texto do documento.
    titulo = _rotulo_da_secao(secao)
    cabecalho = f"<h3>{html.escape(titulo)}</h3>" if titulo else ""
    if secao.tipo == TIPO_FAQ:
        marca = f'<span class="agri-doc-faq-rotulo">{html.escape(rotulo_faq)}</span>'
        classe = "agri-doc-secao agri-doc-faq"
    else:
        marca = ""
        classe = "agri-doc-secao"
    return (
        f'<section class="{classe}" id="{PREFIXO_ID_SECAO}{indice}">'
        f"{marca}{cabecalho}{_paragrafos(secao.texto)}</section>"
    )


def _indice_html(secoes: Sequence[SecaoLida], rotulo: str) -> str:
    itens = "".join(
        f'<li><a href="#{PREFIXO_ID_SECAO}{i}">'
        f"{html.escape(_rotulo_da_secao(secao) or str(i + 1))}</a></li>"
        for i, secao in enumerate(secoes)
    )
    return (
        f'<nav class="agri-doc-indice" aria-label="{html.escape(rotulo)}">'
        f"<details><summary>{html.escape(rotulo)}</summary><ol>{itens}</ol></details></nav>"
    )


def documento_html(
    conteudo: ConteudoLido, rotulo_indice: str, rotulo_faq: str, texto_sem_secoes: str
) -> str:
    """Cabeçalho e seções de um documento, em texto escapado e sem links criados pelo texto.

    Os únicos `<a>` são os do índice, com destino `#agri-sec-N` gerado aqui (não vem do texto).
    """
    titulo = titulo_legivel(conteudo.titulo) or conteudo.arquivo
    meta = meta_do_documento(conteudo.codigo, conteudo.versao)
    linhas = [f"<h2>{html.escape(titulo)}</h2>"]
    if meta:
        linhas.append(f'<p class="agri-doc-meta">{html.escape(meta)}</p>')
    if conteudo.arquivo:
        linhas.append(f'<p class="agri-doc-arquivo">{html.escape(conteudo.arquivo)}</p>')
    cabecalho = f'<header class="agri-tela-cabecalho">{"".join(linhas)}</header>'
    if not conteudo.secoes:
        return f'<article class="agri-doc">{cabecalho}{aviso_base_html(texto_sem_secoes)}</article>'
    indice = _indice_html(conteudo.secoes, rotulo_indice)
    corpo = "".join(
        _bloco_da_secao(i, secao, rotulo_faq) for i, secao in enumerate(conteudo.secoes)
    )
    return f'<article class="agri-doc">{cabecalho}{indice}{corpo}</article>'


def resumir(texto: str, limite: int = 40) -> str:
    """Corta o texto em `limite` caracteres, com reticências, sem quebrar a escape depois."""
    limpo = " ".join(texto.split())
    if len(limpo) <= limite:
        return limpo
    return limpo[: limite - 1].rstrip() + "…"


def titulo_para_leitor_html(titulo: str) -> str:
    """Título da página fora da tela: leitores de tela leem, o visual não mostra."""
    return f'<h1 class="agri-so-leitor">{html.escape(titulo)}</h1>'


def rotulo_sugestoes_html(texto: str) -> str:
    """Rótulo acima dos cartões de perguntas frequentes."""
    return f'<p class="agri-rotulo-sugestoes">{html.escape(texto)}</p>'


def ajuda_html(texto: str) -> str:
    """Texto de ajuda visível abaixo do campo de pergunta."""
    return f'<p class="agri-ajuda">{html.escape(texto)}</p>'


def boas_vindas_html(titulo: str, subtitulo: str) -> str:
    return (
        '<div class="agri-boas-vindas">'
        f"<h2>{html.escape(titulo)}</h2>"
        f"<p>{html.escape(subtitulo)}</p>"
        "</div>"
    )


def balao_usuario_html(rotulo: str, pergunta: str) -> str:
    return (
        '<div class="agri-linha agri-linha-usuario"><div class="agri-coluna">'
        f"{_rotulo_so_leitor(rotulo)}"
        f'<div class="agri-balao agri-balao-usuario">{html.escape(pergunta)}</div>'
        "</div>"
        f"{_avatar('usuario')}"
        "</div>"
    )


def balao_assistente_html(
    rotulo: str,
    texto: str,
    selo: str | None = None,
    chips: Iterable[str] = (),
) -> str:
    """Balão da resposta.

    `selo` (ex.: "Sem evidência") aparece antes do texto, em texto. `chips` são as fontes
    resumidas (documento · seção), dentro do balão. Todo o conteúdo é escapado.
    """
    marca = f'<span class="agri-selo-sem-evidencia">{html.escape(selo)}</span>' if selo else ""
    lista = "".join(f'<span class="agri-chip">{html.escape(chip)}</span>' for chip in chips)
    rotulo_fontes = f'<span class="agri-so-leitor">{html.escape(ROTULO_CHIPS_LEITOR)}</span>'
    fontes = f'<div class="agri-chips">{rotulo_fontes}{lista}</div>' if lista else ""
    return (
        '<div class="agri-linha agri-linha-assistente">'
        f"{_avatar('assistente')}"
        '<div class="agri-coluna">'
        f"{_rotulo_so_leitor(rotulo)}"
        f'<div class="agri-balao agri-balao-assistente">{marca}'
        f'<div class="{CLASSE_RESPOSTA}">{html.escape(texto)}</div>'
        f"{fontes}</div></div></div>"
    )
