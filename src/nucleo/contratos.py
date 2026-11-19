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

    def dividir(self, codigo: str, paginas: Sequence[tuple[int, str]]) -> tuple[Secao, ...]:
        """Devolve as seções na ordem em que aparecem no documento.

        `paginas` são os pares `(numero_da_pagina, texto)` produzidos por `limpar_paginas`,
        na ordem do documento. Cada `Secao` recebe em `pagina` o número da página em que a
        seção começa. Pares com texto vazio são ignorados.

        Sem texto para dividir (sequência vazia ou só com textos vazios) devolve `()` (ADR-007).
        Ver ADR-008 para a escolha desta assinatura.
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


class ReescritorConsulta(Protocol):
    """Propõe formulações alternativas de uma pergunta, para ampliar a recuperação (ADR-010)."""

    def reescrever(self, pergunta: str) -> tuple[str, ...]:
        """Devolve até N formulações alternativas da pergunta.

        - No máximo N formulações, sem repetição entre si e sem textos vazios. N é definido
          pela implementação (ex.: no construtor). Com N=0 devolve `()`.
        - A pergunta original não entra no retorno. Quem busca a inclui sempre (regra de
          fusão do ADR-010), e nenhuma implementação pode substituí-la por ela mesma.
        - Pergunta vazia ou só com espaços devolve `()` sem chamar o modelo (ADR-007).
        - Levanta `ErroReescrita` em falha.
        """
        ...


class GeradorResposta(Protocol):
    """Gera uma resposta fundamentada apenas nos trechos recebidos."""

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        """Levanta `ErroGeracao` em falha.

        Sem evidência nos trechos, ou com `trechos` vazio, devolve
        `Resposta.sem_evidencia()` (ADR-007).
        """
        ...
