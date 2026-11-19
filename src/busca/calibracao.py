"""Calibração do limiar de similaridade (HIST-011, TSK-011.2).

Lê a tabela de `tests/validacao/perguntas.md` (fonte única das perguntas), extrai as fontes
esperadas de cada uma e calcula, para cada pergunta, a pontuação do melhor trecho esperado
e a do melhor trecho geral. Não grava arquivos: quem chama decide o que fazer com o resultado.
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
    """Uma seção esperada, ex.: `FIN-POL-001 §6`. Vale para a seção e suas subseções."""

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
    """Vazio para a pergunta sem resposta nos documentos (pergunta 6)."""


@dataclass(frozen=True)
class PontuacaoPergunta:
    """Melhores trechos de uma pergunta. `None` quando não há trecho que se encaixe."""

    pergunta: PerguntaValidacao
    melhor_esperado: Trecho | None
    melhor_geral: Trecho | None


def ler_perguntas_validacao(caminho: Path) -> tuple[PerguntaValidacao, ...]:
    """Lê as linhas numeradas da tabela de perguntas. Cabeçalho e separador são ignorados."""
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

    Uma parte sem código herda o documento da parte anterior. Texto sem `§` não gera nada
    (ex.: `nenhuma`).
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
    """Ordena o índice inteiro para cada pergunta e separa o melhor geral do melhor esperado.

    `vetores_perguntas` segue a ordem de `perguntas`. Usa `total_secoes` como `k` para ter
    o ranking completo, já que a calibração precisa da pontuação do melhor trecho esperado,
    mesmo que ele não esteja entre os primeiros.

    `total_secoes` deve ser o número de entradas do índice. Com perguntas de FAQ, há mais
    entradas que seções: passe `len(entradas_indexaveis(secoes, perguntas_faq=True))`.
    """
    resultados: list[PontuacaoPergunta] = []
    for pergunta, vetor in zip(perguntas, vetores_perguntas, strict=True):
        ranking = indice.buscar(vetor, total_secoes)
        melhor_geral = ranking[0] if ranking else None
        melhor_esperado = next(
            (
                trecho
                for trecho in ranking
                if any(
                    referencia.corresponde(trecho.secao) for referencia in pergunta.fontes_esperadas
                )
            ),
            None,
        )
        resultados.append(
            PontuacaoPergunta(
                pergunta=pergunta,
                melhor_esperado=melhor_esperado,
                melhor_geral=melhor_geral,
            )
        )
    return tuple(resultados)
