"""Contratos (Protocols) entre o núcleo e as implementações concretas.

Regras deste módulo:
- Cada contrato tem poucos métodos (Interface Segregation).
- O núcleo depende só destes contratos (Dependency Inversion).
- Toda implementação deve respeitar o contrato, inclusive em casos vazios e erros
  (Liskov). Retornos vazios são tuplas vazias, nunca `None`.
- Mudança de contrato exige ADR em `docs/decisoes/`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from nucleo.modelos import Pagina, Resposta, Secao, Trecho, Vetor


class LeitorDocumento(Protocol):
    """Lê um documento e devolve o texto bruto, página a página."""

    def ler(self, caminho: Path) -> tuple[Pagina, ...]:
        """Levanta `ErroDocumento` se o arquivo não existir ou não tiver texto."""
        ...


class Chunker(Protocol):
    """Divide o texto limpo de um documento em seções indexáveis."""

    def dividir(self, codigo: str, texto: str) -> tuple[Secao, ...]:
        """Devolve as seções na ordem em que aparecem no documento.

        Texto vazio devolve `()` (ADR-007).
        """
        ...


class ProvedorEmbedding(Protocol):
    """Gera vetores de embedding para uma lista de textos."""

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        """Devolve um vetor por texto, na mesma ordem. Levanta `ErroBusca` em falha.

        Lista vazia devolve `()` sem chamar o provedor externo (ADR-007).
        """
        ...


class Indice(Protocol):
    """Armazena seções com seus vetores e responde a buscas por similaridade."""

    def adicionar(self, secoes: Sequence[Secao], vetores: Sequence[Vetor]) -> None:
        """Associa cada seção ao seu vetor. As duas sequências têm o mesmo tamanho.

        Sequências vazias não fazem nada (ADR-007).
        """
        ...

    def buscar(self, vetor: Vetor, k: int) -> tuple[Trecho, ...]:
        """Devolve até `k` trechos, do mais para o menos similar. Índice vazio devolve `()`."""
        ...


class Buscador(Protocol):
    """Encontra os trechos relevantes para uma pergunta, já aplicando o limiar."""

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        """Devolve somente trechos acima do limiar. Sem resultados devolve `()` (ADR-007)."""
        ...


class GeradorResposta(Protocol):
    """Gera uma resposta fundamentada apenas nos trechos recebidos."""

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        """Levanta `ErroGeracao` em falha.

        Sem evidência nos trechos, ou com `trechos` vazio, devolve
        `Resposta.sem_evidencia()` (ADR-007).
        """
        ...
