"""Calibração do limiar: pontua o melhor trecho esperado e o melhor geral de cada pergunta.

As perguntas e as fontes esperadas vêm de `tests/validacao/perguntas.md`. Não grava arquivos.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from nucleo.contratos import Indice
from nucleo.modelos import Secao, Trecho, Vetor

RE_CODIGO_DOCUMENTO = re.compile(r"[A-Z]{2,3}-[A-Z]{3}-\d{3}")
RE_REFERENCIA_SECAO = re.compile(r"§(\d+)(?:\s*a\s*§(\d+))?")
RE_LINHA_PERGUNTA = re.compile(r"^\s*\|\s*(\d+)\s*\|")
COLUNAS_PERGUNTA = 4


@dataclass(frozen=True)
class ReferenciaSecao:
    """Uma seção esperada, ex.: `FIN-POL-001 §6`; vale também para suas subseções."""

    documento: str
    numero_secao: int

    def corresponde(self, secao: Secao) -> bool:
        if secao.documento != self.documento:
            return False
        return secao.numero == str(self.numero_secao) or secao.numero.startswith(
            f"{self.numero_secao}."
        )


@dataclass(frozen=True)
class PerguntaValidacao:
    numero: int
    texto: str
    fontes_esperadas: tuple[ReferenciaSecao, ...]
    """Vazio quando a tabela não lista seção numérica (ex.: só `§faq-N`, perguntas 6 e 7)."""


@dataclass(frozen=True)
class PontuacaoPergunta:
    """Melhores trechos de uma pergunta. `None` quando não há trecho que se encaixe."""

    pergunta: PerguntaValidacao
    melhor_esperado: Trecho | None
    melhor_geral: Trecho | None
    posicao_melhor_esperado: int | None = None
    """Posição (a partir de 1) do melhor trecho esperado entre as seções distintas do ranking.

    Conta seções, não entradas, porque o `BuscadorSemantico` corta o `TOP_K` depois de juntar
    as entradas da mesma seção. O que leva a seção à geração é estar entre as `TOP_K`
    primeiras e acima do piso, não a pontuação absoluta.
    """


def ler_perguntas_validacao(caminho: Path) -> tuple[PerguntaValidacao, ...]:
    """Lê as linhas numeradas da tabela de perguntas, ignorando cabeçalho e separador."""
    perguntas: list[PerguntaValidacao] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not RE_LINHA_PERGUNTA.match(linha):
            continue
        celulas = [celula.strip() for celula in linha.strip().strip("|").split("|")]
        if len(celulas) != COLUNAS_PERGUNTA:
            raise ValueError(f"Linha de pergunta com colunas inesperadas: {celulas[0]}")
        numero, texto, _deve_conter, fontes = celulas
        perguntas.append(
            PerguntaValidacao(
                numero=int(numero),
                texto=texto,
                fontes_esperadas=_referencias(fontes),
            )
        )
    return tuple(perguntas)


def _referencias(celula: str) -> tuple[ReferenciaSecao, ...]:
    """Lê células como `FIN-POL-001 §4, §5; FRO-POL-002 §6` e `RH-PRO-003 §2 a §4`.

    Uma parte sem código herda o documento da anterior. Texto sem `§` não gera nada.
    """
    referencias: list[ReferenciaSecao] = []
    documento = ""
    for parte in celula.split(";"):
        codigo = RE_CODIGO_DOCUMENTO.search(parte)
        if codigo is not None:
            documento = codigo.group(0)
        for casamento in RE_REFERENCIA_SECAO.finditer(parte):
            inicio = int(casamento.group(1))
            fim = int(casamento.group(2) or casamento.group(1))
            referencias.extend(
                ReferenciaSecao(documento, numero) for numero in range(inicio, fim + 1)
            )
    return tuple(referencias)


def pontuar_perguntas(
    perguntas: Sequence[PerguntaValidacao],
    vetores_perguntas: Sequence[Vetor],
    indice: Indice,
    total_secoes: int,
) -> tuple[PontuacaoPergunta, ...]:
    """Separa o melhor trecho geral do melhor esperado de cada pergunta.

    `vetores_perguntas` segue a ordem de `perguntas`. `total_secoes` é usado como `k` para obter
    o ranking completo e deve ser o número de entradas do índice, que com perguntas de FAQ é
    maior que o de seções (use `len(entradas_indexaveis(...))`).
    """
    resultados: list[PontuacaoPergunta] = []
    for pergunta, vetor in zip(perguntas, vetores_perguntas, strict=True):
        ranking = indice.buscar(vetor, total_secoes)
        melhor_geral = ranking[0] if ranking else None
        posicao, melhor_esperado = next(
            (
                (posicao, trecho)
                for posicao, trecho in enumerate(_uma_entrada_por_secao(ranking), start=1)
                if any(
                    referencia.corresponde(trecho.secao) for referencia in pergunta.fontes_esperadas
                )
            ),
            (None, None),
        )
        resultados.append(
            PontuacaoPergunta(
                pergunta=pergunta,
                melhor_esperado=melhor_esperado,
                melhor_geral=melhor_geral,
                posicao_melhor_esperado=posicao,
            )
        )
    return tuple(resultados)


def _uma_entrada_por_secao(ranking: Sequence[Trecho]) -> tuple[Trecho, ...]:
    """Mantém a primeira entrada de cada seção, a de maior pontuação (como no buscador)."""
    vistas: set[Secao] = set()
    distintas: list[Trecho] = []
    for trecho in ranking:
        if trecho.secao not in vistas:
            vistas.add(trecho.secao)
            distintas.append(trecho)
    return tuple(distintas)
