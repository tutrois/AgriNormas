"""Chunking por seção numerada: implementa `Chunker` sobre o texto limpo (ADR-008).

Seção (`6.`) e subseção (`6.1`) são detectadas pelo parágrafo inteiro. O chunk de subseção
começa com a linha da seção-pai, para que o título dela entre no texto indexado. Seções de
`TITULOS_EXCECAO` ficam inteiras; em FAQ, cada pergunta e suas respostas formam um chunk;
as demais são divididas por parágrafo até `tamanho_maximo`. Texto antes da primeira seção
numerada não vira chunk. `dividir` é puro e determinista; sem texto devolve `()` (ADR-007).
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
    """Seção de primeiro nível. `cabecalho` é `None` no grupo sem seção."""

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
    contador_faq = count(1)
    chunks: list[Secao] = []
    for secao in _agrupar_em_secoes(paragrafos):
        chunks.extend(_chunks_da_secao(secao, codigo, tamanho_maximo, contador_faq))
    return tuple(chunks)


def _agrupar_em_secoes(paragrafos: Sequence[_Paragrafo]) -> tuple[_Secao, ...]:
    """A primeira entrada é o grupo sem cabeçalho: texto inicial e subseções sem seção-pai."""
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
    limpo = texto.strip()
    if len(limpo) > MAXIMO_CARACTERES_TITULO:
        return None
    return padrao.fullmatch(limpo)


def _chunks_da_secao(
    secao: _Secao, codigo: str, tamanho_maximo: int, contador_faq: Iterator[int]
) -> list[Secao]:
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
    """Grupo sem cabeçalho (texto antes da primeira seção) não gera chunk."""
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
    """Texto antes da primeira pergunta vira corpo comum; cada par leva a linha da seção."""
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
    paragrafos = list(secao.corpo)
    for subsecao in secao.subsecoes:
        paragrafos.append(subsecao.cabecalho)
        paragrafos.extend(subsecao.corpo)
    return paragrafos


def _empacotar(cabecalho: Sequence[str], corpo: Sequence[str], tamanho_maximo: int) -> list[str]:
    """Junta parágrafos em pedaços de até `tamanho_maximo`, cada um com o cabeçalho.

    Só quebra em palavras um parágrafo maior que o espaço disponível. Cabeçalho sem espaço
    para o corpo é configuração inválida; a mensagem cita o limite, não o documento.
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
    if len(paragrafo) <= orcamento:
        return [paragrafo]
    return textwrap.wrap(paragrafo, width=orcamento, break_long_words=True, break_on_hyphens=False)


def _e_excecao(secao: _Secao) -> bool:
    return _normalizar_titulo(secao.titulo) in {_normalizar_titulo(t) for t in TITULOS_EXCECAO}


def _e_faq(secao: _Secao) -> bool:
    return _normalizar_titulo(secao.titulo) == _normalizar_titulo(TITULO_FAQ)


def _normalizar_titulo(titulo: str) -> str:
    return " ".join(titulo.split()).casefold()
