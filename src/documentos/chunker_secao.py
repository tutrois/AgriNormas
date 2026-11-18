"""Chunking por seção numerada (HIST-007): implementa `Chunker` sobre o texto limpo.

Regras de divisão:

- Seção numerada (`6.`) e subseção (`6.1`) são detectadas pelo início do parágrafo. Só
  vale o parágrafo inteiro que casa com o padrão e tem até `MAXIMO_CARACTERES_TITULO`
  caracteres.
- O corpo de uma seção vira um chunk. Cada subseção vira um chunk próprio.
- O texto de um chunk de subseção começa com a linha da seção-pai (ex.: `6. Prazo e fluxo
  de solicitação`) e depois com a própria linha da subseção. Assim, o título da seção-pai
  vai no texto que será indexado, sem mudar o modelo `Secao`. O campo `titulo` continua
  sendo só o título da subseção.
- Seções cujo título está em `TITULOS_EXCECAO` ficam inteiras, com as subseções, sem
  divisão por tamanho.
- Em seções de FAQ, cada pergunta com as respostas que a seguem vira um chunk do tipo
  `faq`. Pergunta e resposta nunca são separadas.
- As demais seções longas são divididas por parágrafo, até `tamanho_maximo` caracteres.
  Um parágrafo maior que o limite é quebrado em palavras.
- Texto que vem antes da primeira seção numerada (capa, identificação e resumo) não vira
  chunk. Os campos de identificação são lidos por `ler_metadados`. Subseções sem seção-pai
  ainda viram chunk, sem linha de contexto.

`dividir(codigo, paginas)` segue o contrato de ADR-008. Recebe os pares
`(numero_da_pagina, texto)` de `limpar_paginas`, um par por parágrafo, e preenche `pagina`
com a página em que a seção (ou o par de FAQ) começa. O método é puro e determinista.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from itertools import count

from documentos.regras_chunking import (
    MAXIMO_CARACTERES_TITULO,
    PREFIXO_NUMERO_FAQ,
    RE_CABECALHO_SECAO,
    RE_CABECALHO_SUBSECAO,
    TAMANHO_MAXIMO_CHUNK,
    TERMINADOR_PERGUNTA,
    TITULO_FAQ,
    TITULOS_EXCECAO,
)
from nucleo.erros import ConfiguracaoInvalida
from nucleo.modelos import Secao


@dataclass(frozen=True)
class _Paragrafo:
    """Um parágrafo limpo, com o número da página em que começa."""

    pagina: int
    texto: str


@dataclass
class _Subsecao:
    numero: str
    titulo: str
    cabecalho: _Paragrafo
    corpo: list[_Paragrafo] = field(default_factory=list)


@dataclass
class _Secao:
    """Seção de primeiro nível agrupada.

    `cabecalho` é `None` no grupo sem seção (texto antes da primeira seção e subseções sem
    seção-pai). O corpo desse grupo não vira chunk; só as subseções viram.
    """

    numero: str
    titulo: str
    cabecalho: _Paragrafo | None
    corpo: list[_Paragrafo] = field(default_factory=list)
    subsecoes: list[_Subsecao] = field(default_factory=list)


class ChunkerPorSecao:
    """Implementa `Chunker` dividindo o texto limpo pelas seções numeradas."""

    def __init__(self, tamanho_maximo: int = TAMANHO_MAXIMO_CHUNK) -> None:
        if tamanho_maximo < 1:
            raise ConfiguracaoInvalida("O tamanho máximo do chunk deve ser um inteiro positivo.")
        self._tamanho_maximo = tamanho_maximo

    def dividir(self, codigo: str, paginas: Sequence[tuple[int, str]]) -> tuple[Secao, ...]:
        """Divide os pares `(numero_da_pagina, texto)` de `limpar_paginas`, na ordem do documento.

        Cada `Secao` recebe em `pagina` a página em que começa. Pares com texto vazio são
        ignorados. Sem texto para dividir devolve `()` (ADR-007 e ADR-008).
        """
        paragrafos = tuple(
            _Paragrafo(pagina=numero, texto=texto.strip())
            for numero, texto in paginas
            if texto.strip()
        )
        return _montar_secoes(codigo, paragrafos, self._tamanho_maximo)


def _montar_secoes(
    codigo: str, paragrafos: Sequence[_Paragrafo], tamanho_maximo: int
) -> tuple[Secao, ...]:
    """Agrupa os parágrafos em seções e converte cada uma em chunks, na ordem do documento."""
    contador_faq = count(1)
    chunks: list[Secao] = []
    for secao in _agrupar_em_secoes(paragrafos):
        chunks.extend(_chunks_da_secao(secao, codigo, tamanho_maximo, contador_faq))
    return tuple(chunks)


def _agrupar_em_secoes(paragrafos: Sequence[_Paragrafo]) -> tuple[_Secao, ...]:
    """Separa os parágrafos em seções de primeiro nível e subseções. Função pura.

    A primeira entrada é o grupo sem cabeçalho, que recebe o texto antes do primeiro
    cabeçalho. Uma subseção sem seção-pai (ex.: `2.1` antes de qualquer `2.`) entra nesse
    grupo, sem linha de contexto.
    """
    secoes = [_Secao(numero="", titulo="", cabecalho=None)]
    subsecao_atual: _Subsecao | None = None
    for paragrafo in paragrafos:
        cabecalho_secao = _casar_cabecalho(RE_CABECALHO_SECAO, paragrafo.texto)
        cabecalho_subsecao = _casar_cabecalho(RE_CABECALHO_SUBSECAO, paragrafo.texto)
        if cabecalho_secao is not None:
            secoes.append(
                _Secao(
                    numero=cabecalho_secao.group("numero"),
                    titulo=cabecalho_secao.group("titulo").strip(),
                    cabecalho=paragrafo,
                )
            )
            subsecao_atual = None
        elif cabecalho_subsecao is not None:
            subsecao_atual = _Subsecao(
                numero=cabecalho_subsecao.group("numero"),
                titulo=cabecalho_subsecao.group("titulo").strip(),
                cabecalho=paragrafo,
            )
            secoes[-1].subsecoes.append(subsecao_atual)
        elif subsecao_atual is not None:
            subsecao_atual.corpo.append(paragrafo)
        else:
            secoes[-1].corpo.append(paragrafo)
    return tuple(secoes)


def _casar_cabecalho(padrao: re.Pattern[str], texto: str) -> re.Match[str] | None:
    """Casa o padrão com o parágrafo inteiro, desde que não seja longo demais para título."""
    limpo = texto.strip()
    if len(limpo) > MAXIMO_CARACTERES_TITULO:
        return None
    return padrao.fullmatch(limpo)


def _chunks_da_secao(
    secao: _Secao, codigo: str, tamanho_maximo: int, contador_faq: Iterator[int]
) -> list[Secao]:
    """Converte uma seção de primeiro nível nos seus chunks. Ordem: corpo, depois subseções."""
    if _e_excecao(secao):
        return _chunk_inteiro(secao, codigo)
    if _e_faq(secao):
        return _chunks_faq(secao, codigo, tamanho_maximo, contador_faq)
    chunks = _chunks_do_corpo(secao, codigo, tamanho_maximo)
    for subsecao in secao.subsecoes:
        chunks.extend(_chunks_da_subsecao(secao, subsecao, codigo, tamanho_maximo))
    return chunks


def _chunk_inteiro(secao: _Secao, codigo: str) -> list[Secao]:
    """Seção de exceção: um único chunk com tudo, sem divisão. Seção sem corpo não gera chunk."""
    paragrafos = _paragrafos_do_corpo(secao)
    if not paragrafos or secao.cabecalho is None:
        return []
    texto = "\n".join([secao.cabecalho.texto, *(p.texto for p in paragrafos)])
    return [
        Secao(
            documento=codigo,
            numero=secao.numero,
            titulo=secao.titulo,
            texto=texto,
            tipo="excecao",
            pagina=secao.cabecalho.pagina,
        )
    ]


def _chunks_do_corpo(secao: _Secao, codigo: str, tamanho_maximo: int) -> list[Secao]:
    """Chunks do corpo de uma seção, com a linha da própria seção como contexto.

    Grupo sem cabeçalho (texto antes da primeira seção) não gera chunk: fica fora do índice.
    """
    if secao.cabecalho is None or not secao.corpo:
        return []
    cabecalho = [secao.cabecalho.texto]
    pagina = secao.cabecalho.pagina
    return [
        Secao(
            documento=codigo,
            numero=secao.numero,
            titulo=secao.titulo,
            texto=texto,
            tipo="normal",
            pagina=pagina,
        )
        for texto in _empacotar(cabecalho, [p.texto for p in secao.corpo], tamanho_maximo)
    ]


def _chunks_da_subsecao(
    secao: _Secao, subsecao: _Subsecao, codigo: str, tamanho_maximo: int
) -> list[Secao]:
    """Chunks de uma subseção, com a linha da seção-pai (se houver) e a da própria subseção."""
    if not subsecao.corpo:
        return []
    cabecalho = [
        *([secao.cabecalho.texto] if secao.cabecalho is not None else []),
        subsecao.cabecalho.texto,
    ]
    return [
        Secao(
            documento=codigo,
            numero=subsecao.numero,
            titulo=subsecao.titulo,
            texto=texto,
            tipo="normal",
            pagina=subsecao.cabecalho.pagina,
        )
        for texto in _empacotar(cabecalho, [p.texto for p in subsecao.corpo], tamanho_maximo)
    ]


def _chunks_faq(
    secao: _Secao, codigo: str, tamanho_maximo: int, contador_faq: Iterator[int]
) -> list[Secao]:
    """Um chunk por par pergunta e resposta. Texto antes da primeira pergunta vira corpo comum.

    Cada par leva a linha da seção (`11. Perguntas frequentes…`) como contexto, como as
    subseções. Pergunta e resposta ficam juntas no mesmo chunk.
    """
    antes, pares = _separar_pares(_paragrafos_do_corpo(secao))
    chunks = _chunks_do_corpo(
        _Secao(numero=secao.numero, titulo=secao.titulo, cabecalho=secao.cabecalho, corpo=antes),
        codigo,
        tamanho_maximo,
    )
    contexto = [secao.cabecalho.texto] if secao.cabecalho is not None else []
    for pergunta, respostas in pares:
        texto = "\n".join([*contexto, pergunta.texto, *(resposta.texto for resposta in respostas)])
        chunks.append(
            Secao(
                documento=codigo,
                numero=f"{PREFIXO_NUMERO_FAQ}{next(contador_faq)}",
                titulo=pergunta.texto,
                texto=texto,
                tipo="faq",
                pagina=pergunta.pagina,
            )
        )
    return chunks


def _separar_pares(
    paragrafos: Sequence[_Paragrafo],
) -> tuple[list[_Paragrafo], list[tuple[_Paragrafo, list[_Paragrafo]]]]:
    """Separa o texto anterior à primeira pergunta dos pares (pergunta, respostas). Função pura."""
    antes: list[_Paragrafo] = []
    pares: list[tuple[_Paragrafo, list[_Paragrafo]]] = []
    for paragrafo in paragrafos:
        if paragrafo.texto.endswith(TERMINADOR_PERGUNTA):
            pares.append((paragrafo, []))
        elif pares:
            pares[-1][1].append(paragrafo)
        else:
            antes.append(paragrafo)
    return antes, pares


def _paragrafos_do_corpo(secao: _Secao) -> list[_Paragrafo]:
    """Corpo da seção seguido de cada subseção (cabeçalho e corpo), na ordem do documento."""
    paragrafos = list(secao.corpo)
    for subsecao in secao.subsecoes:
        paragrafos.append(subsecao.cabecalho)
        paragrafos.extend(subsecao.corpo)
    return paragrafos


def _empacotar(cabecalho: Sequence[str], corpo: Sequence[str], tamanho_maximo: int) -> list[str]:
    """Junta parágrafos em pedaços de até `tamanho_maximo` caracteres, cada um com o cabeçalho.

    Os parágrafos não são cortados, a menos que um deles seja maior que o espaço disponível.
    Nesse caso, ele é quebrado em palavras. O cabeçalho conta no tamanho. Se o cabeçalho
    não deixar nem 1 caractere para o corpo, a configuração é inválida: nenhum chunk
    respeitaria o limite. A mensagem cita o limite, não o conteúdo do documento.
    """
    orcamento = tamanho_maximo - sum(len(linha) + 1 for linha in cabecalho)
    if orcamento < 1:
        raise ConfiguracaoInvalida(
            "O cabeçalho de contexto de uma seção não cabe no tamanho máximo de "
            f"{tamanho_maximo} caracteres. Aumente o limite."
        )
    segmentos = [segmento for paragrafo in corpo for segmento in _segmentar(paragrafo, orcamento)]
    grupos: list[list[str]] = []
    atual: list[str] = []
    tamanho_atual = 0
    for segmento in segmentos:
        if atual and tamanho_atual + 1 + len(segmento) > orcamento:
            grupos.append(atual)
            atual, tamanho_atual = [], 0
        tamanho_atual += len(segmento) + (1 if atual else 0)
        atual.append(segmento)
    if atual:
        grupos.append(atual)
    return ["\n".join([*cabecalho, *grupo]) for grupo in grupos]


def _segmentar(paragrafo: str, orcamento: int) -> list[str]:
    """Devolve o parágrafo inteiro se couber no orçamento, ou o quebra em palavras."""
    if len(paragrafo) <= orcamento:
        return [paragrafo]
    return textwrap.wrap(paragrafo, width=orcamento, break_long_words=True, break_on_hyphens=False)


def _e_excecao(secao: _Secao) -> bool:
    return _normalizar_titulo(secao.titulo) in {_normalizar_titulo(t) for t in TITULOS_EXCECAO}


def _e_faq(secao: _Secao) -> bool:
    return _normalizar_titulo(secao.titulo) == _normalizar_titulo(TITULO_FAQ)


def _normalizar_titulo(titulo: str) -> str:
    """Compara títulos sem diferença de espaços, maiúsculas ou minúsculas."""
    return " ".join(titulo.split()).casefold()
