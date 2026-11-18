"""Serviço `AssistenteRAG` (HIST-017): valida a pergunta, busca, gera e filtra as fontes.

Depende só dos contratos `Buscador` e `GeradorResposta`, recebidos pelo construtor.
Não sabe o que é OpenAI, numpy nem PDF (ADR-007 para entradas vazias).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from nucleo.contratos import Buscador, GeradorResposta
from nucleo.erros import PerguntaInvalida
from nucleo.modelos import Fonte, Resposta, Trecho

TAMANHO_MAXIMO_PERGUNTA = 500
"""Limite de caracteres da pergunta, depois de aparada nas bordas (TSK-017.4)."""


class AssistenteRAG:
    """Responde perguntas com base nos documentos, ou recusa quando não há evidência."""

    def __init__(self, buscador: Buscador, gerador: GeradorResposta) -> None:
        self._buscador = buscador
        self._gerador = gerador

    def responder(self, pergunta: str) -> Resposta:
        """Devolve a resposta fundamentada, com fontes, ou `Resposta.sem_evidencia()`.

        Lança `PerguntaInvalida` antes de qualquer busca se a pergunta estiver vazia
        ou tiver mais de `TAMANHO_MAXIMO_PERGUNTA` caracteres. Erros de busca e de geração
        (`ErroBusca`, `ErroGeracao`) propagam sem conversão.
        """
        texto = _validar_pergunta(pergunta)
        trechos = self._buscador.buscar(texto)
        if not trechos:
            return Resposta.sem_evidencia()
        resposta = self._gerador.gerar(texto, trechos)
        return _resposta_final(resposta, trechos)


def _validar_pergunta(pergunta: object) -> str:
    """Devolve a pergunta aparada, ou lança `PerguntaInvalida`.

    Aceita `object` de propósito: a fronteira pode receber valores fora do tipo declarado
    (ex.: `None`), e esses viram erro de domínio, não `AttributeError`.
    """
    if not isinstance(pergunta, str):
        raise PerguntaInvalida("A pergunta deve ser um texto.")
    texto = pergunta.strip()
    if not texto:
        raise PerguntaInvalida("A pergunta não pode ser vazia.")
    if len(texto) > TAMANHO_MAXIMO_PERGUNTA:
        raise PerguntaInvalida(
            f"A pergunta deve ter no máximo {TAMANHO_MAXIMO_PERGUNTA} caracteres."
        )
    return texto


def _resposta_final(resposta: Resposta, trechos: Sequence[Trecho]) -> Resposta:
    """Aplica as regras de saída sobre a resposta do gerador.

    - Recusa do gerador (`evidencia_suficiente=False`): devolve `sem_evidencia()`.
    - Texto vazio: não entrega resposta vazia; devolve `sem_evidencia()`.
    - Fontes: mantém só as que correspondem a um dos trechos recuperados, sem repetição
      e na ordem do gerador. Se nenhuma sobrar, devolve `sem_evidencia()`.
    """
    if not resposta.evidencia_suficiente or not resposta.texto.strip():
        return Resposta.sem_evidencia()
    fontes = _filtrar_fontes(resposta.fontes, _fontes_dos_trechos(trechos))
    if not fontes:
        return Resposta.sem_evidencia()
    return replace(resposta, fontes=fontes)


def _fontes_dos_trechos(trechos: Sequence[Trecho]) -> frozenset[Fonte]:
    """Conjunto de fontes que os trechos recuperados sustentam, uma por seção."""
    return frozenset(Fonte.de_secao(trecho.secao) for trecho in trechos)


def _filtrar_fontes(fontes: Sequence[Fonte], permitidas: frozenset[Fonte]) -> tuple[Fonte, ...]:
    """Mantém só as fontes permitidas, sem repetição e na ordem recebida."""
    aceitas = dict.fromkeys(fonte for fonte in fontes if fonte in permitidas)
    return tuple(aceitas)
