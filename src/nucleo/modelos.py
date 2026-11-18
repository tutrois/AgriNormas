"""Modelos de domínio do assistente.

Este módulo não importa nenhuma biblioteca externa. Os objetos são imutáveis
(`frozen=True`), para que possam ser compartilhados entre camadas sem efeitos colaterais.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vetor = tuple[float, ...]
"""Vetor de embedding. Tupla de floats, sem depender de numpy no núcleo."""

TipoSecao = Literal["normal", "excecao", "faq"]

MENSAGEM_SEM_EVIDENCIA = "Não há evidência nos documentos para responder a esta pergunta."


@dataclass(frozen=True)
class Pagina:
    """Texto bruto de uma página de um PDF, antes da limpeza."""

    numero: int
    texto: str


@dataclass(frozen=True)
class Secao:
    """Unidade de conteúdo indexável: uma seção numerada (ou um par de FAQ) de um documento."""

    documento: str
    """Código do documento, ex.: `FIN-POL-001`."""
    numero: str
    """Número da seção, ex.: `3.1`, `6.1` ou `faq-1`."""
    titulo: str
    texto: str
    tipo: TipoSecao = "normal"
    pagina: int | None = None


@dataclass(frozen=True)
class Trecho:
    """Uma seção recuperada, com a pontuação de similaridade em relação à pergunta."""

    secao: Secao
    pontuacao: float


@dataclass(frozen=True)
class Fonte:
    """Citação exibida ao usuário: documento e seção de onde veio a informação."""

    documento: str
    secao: str
    titulo: str

    @classmethod
    def de_secao(cls, secao: Secao) -> Fonte:
        return cls(documento=secao.documento, secao=secao.numero, titulo=secao.titulo)


@dataclass(frozen=True)
class Resposta:
    """Resposta final do assistente, com as fontes que a sustentam."""

    texto: str
    fontes: tuple[Fonte, ...] = ()
    evidencia_suficiente: bool = True

    @classmethod
    def sem_evidencia(cls) -> Resposta:
        """Resposta padrão para quando os documentos não sustentam uma resposta."""
        return cls(texto=MENSAGEM_SEM_EVIDENCIA, fontes=(), evidencia_suficiente=False)
