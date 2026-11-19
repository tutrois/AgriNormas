"""Marcação HTML dos blocos da tela: topo, barra lateral, boas-vindas e balões (HIST-030).

Todo texto que vem do usuário ou do núcleo passa por `html.escape`, então vira texto: nenhum
elemento `<a>` (exceto o link fixo "Nova conversa"), `<img>` ou `<script>` é criado a partir
dele. Este módulo só organiza o que a página recebe. Não decide nada sobre a pergunta nem
sobre a resposta.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Final

from interface.estilo import TEXTO_MARCA

CLASSE_RESPOSTA: Final[str] = "agrinormas-resposta"
ROTULO_NOVA_CONVERSA: Final[str] = "Nova conversa"
DESTINO_NOVA_CONVERSA: Final[str] = "./"


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


def lista_conversas_html(perguntas: Sequence[str], rotulo: str) -> str:
    """Lista "Recentes" com as perguntas da sessão, da mais recente para a mais antiga.

    Cada pergunta é cortada em tamanho fixo e escapada. A última pergunta fica destacada.
    Não são links: a sessão não guarda conversas anteriores.
    """
    if not perguntas:
        return ""
    itens = []
    recentes = list(reversed(perguntas))
    for posicao, pergunta in enumerate(recentes):
        classe = (
            "agri-item-conversa agri-item-conversa-atual" if posicao == 0 else "agri-item-conversa"
        )
        itens.append(f'<div class="{classe}">{html.escape(_resumir(pergunta))}</div>')
    return f'<p class="agri-lista-rotulo">{html.escape(rotulo)}</p>{"".join(itens)}'


def _resumir(texto: str, limite: int = 40) -> str:
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
    fontes = f'<div class="agri-chips">{lista}</div>' if lista else ""
    return (
        '<div class="agri-linha agri-linha-assistente">'
        f"{_avatar('assistente')}"
        '<div class="agri-coluna">'
        f"{_rotulo_so_leitor(rotulo)}"
        f'<div class="agri-balao agri-balao-assistente">{marca}'
        f'<div class="{CLASSE_RESPOSTA}">{html.escape(texto)}</div>'
        f"{fontes}</div></div></div>"
    )
