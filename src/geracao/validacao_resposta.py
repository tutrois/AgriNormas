"""Validação da saída do modelo e das citações.

Função pura, sem rede nem SDK. É a última barreira contra citação inventada e não depende do
modelo: toda fonte citada precisa existir entre os trechos recuperados. Saída inválida vira
`Resposta.sem_evidencia()`, com motivo fixo em log; o conteúdo do modelo nunca entra no log.

A conferência de afirmações de ausência ("o documento não define X") fica em `ausencia.py`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from geracao.ausencia import ausencias_sustentadas, diz_nao_ha_evidencia
from geracao.prompts import (
    CAMPO_EVIDENCIA,
    CAMPO_FONTES,
    CAMPO_RESPOSTA,
    identificador_trecho,
)
from nucleo.modelos import Fonte, Resposta, Trecho

logger = logging.getLogger(__name__)

MOTIVO_JSON_INVALIDO = "a saída não é um objeto JSON"
MOTIVO_CAMPO_AUSENTE = "campo obrigatório ausente"
MOTIVO_CAMPO_INVALIDO = "campo obrigatório com tipo inválido"
MOTIVO_FONTE_NAO_RECUPERADA = "fonte citada que não está entre os trechos recuperados"
MOTIVO_SEM_FONTE = "evidência afirmada sem fonte citada"
MOTIVO_SEM_CITACAO_NO_TEXTO = "texto da resposta sem citação entre colchetes"
MOTIVO_TEXTO_VAZIO = "texto da resposta vazio"
MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA = "texto diz não haver evidência, com a flag de evidência verdadeira"
MOTIVO_AUSENCIA_SEM_SUSTENTACAO = "afirmação de ausência que os trechos citados não sustentam"

MODELO_LOG_RECUSA = "Saída do modelo recusada: %s."

PADRAO_CITACAO_NO_TEXTO = re.compile(r"\[([^\[\]]*§[^\[\]]*)\]")
PADRAO_SEPARADOR_SECAO = re.compile(r"\s*§\s*")


@dataclass(frozen=True)
class _SaidaModelo:
    texto: str
    fontes_citadas: tuple[str, ...]
    evidencia_suficiente: bool


class _SaidaInvalida(Exception):
    """Motivo fixo pelo qual a saída não pode ser usada. Não carrega conteúdo do modelo."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def validar_saida(saida: str, trechos: Sequence[Trecho]) -> Resposta:
    """Devolve a `Resposta` validada, ou `sem_evidencia()` quando a saída não se sustenta."""
    try:
        bruta = _ler_saida(saida)
        return _validar(bruta, trechos)
    except _SaidaInvalida as erro:
        logger.warning(MODELO_LOG_RECUSA, erro.motivo)
        return Resposta.sem_evidencia()


def _validar(bruta: _SaidaModelo, trechos: Sequence[Trecho]) -> Resposta:
    if not bruta.evidencia_suficiente:
        return Resposta.sem_evidencia()

    if diz_nao_ha_evidencia(bruta.texto):
        logger.info(MODELO_LOG_RECUSA, MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA)
        return Resposta.sem_evidencia()
    if not bruta.texto:
        raise _SaidaInvalida(MOTIVO_TEXTO_VAZIO)
    if not bruta.fontes_citadas:
        raise _SaidaInvalida(MOTIVO_SEM_FONTE)

    recuperados = _indexar_trechos(trechos)
    citacoes_no_texto = _citacoes_no_texto(bruta.texto)
    if not citacoes_no_texto:
        raise _SaidaInvalida(MOTIVO_SEM_CITACAO_NO_TEXTO)
    identificadores = _sem_repeticao((*bruta.fontes_citadas, *citacoes_no_texto))
    if any(identificador not in recuperados for identificador in identificadores):
        raise _SaidaInvalida(MOTIVO_FONTE_NAO_RECUPERADA)
    citados = [recuperados[identificador] for identificador in identificadores]
    if not ausencias_sustentadas(bruta.texto, citados):
        raise _SaidaInvalida(MOTIVO_AUSENCIA_SEM_SUSTENTACAO)

    fontes = tuple(Fonte.de_secao(trecho.secao) for trecho in citados)
    return Resposta(texto=bruta.texto, fontes=fontes, evidencia_suficiente=True)


def _ler_saida(saida: str) -> _SaidaModelo:
    """`RecursionError` conta como JSON inválido: aninhamento extremo esgota a pilha do parser."""
    dados: object
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError, RecursionError:
        dados = None
    if not isinstance(dados, dict):
        raise _SaidaInvalida(MOTIVO_JSON_INVALIDO)

    for campo in (CAMPO_RESPOSTA, CAMPO_FONTES, CAMPO_EVIDENCIA):
        if campo not in dados:
            raise _SaidaInvalida(MOTIVO_CAMPO_AUSENTE)

    texto = dados[CAMPO_RESPOSTA]
    fontes = dados[CAMPO_FONTES]
    evidencia = dados[CAMPO_EVIDENCIA]
    if (
        not isinstance(texto, str)
        or not isinstance(evidencia, bool)
        or not _lista_de_textos(fontes)
    ):
        raise _SaidaInvalida(MOTIVO_CAMPO_INVALIDO)

    return _SaidaModelo(
        texto=texto.strip(),
        fontes_citadas=tuple(_normalizar_identificador(item) for item in cast(list[str], fontes)),
        evidencia_suficiente=evidencia,
    )


def _lista_de_textos(valor: object) -> bool:
    return isinstance(valor, list) and all(isinstance(item, str) for item in valor)


def _indexar_trechos(trechos: Sequence[Trecho]) -> dict[str, Trecho]:
    """Mapeia cada identificador do contexto ao primeiro trecho que o recebeu."""
    indice: dict[str, Trecho] = {}
    for trecho in trechos:
        indice.setdefault(_normalizar_identificador(identificador_trecho(trecho)), trecho)
    return indice


def _citacoes_no_texto(texto: str) -> list[str]:
    return [
        _normalizar_identificador(citacao) for citacao in PADRAO_CITACAO_NO_TEXTO.findall(texto)
    ]


def _sem_repeticao(identificadores: Sequence[str]) -> tuple[str, ...]:
    """Remove repetições mantendo a ordem da primeira ocorrência."""
    return tuple(dict.fromkeys(identificadores))


def _normalizar_identificador(texto: str) -> str:
    """Espaços simples e `§` colado ao número: `FIN-POL-001  §  6` vira `FIN-POL-001 §6`."""
    com_secao = PADRAO_SEPARADOR_SECAO.sub(" §", texto)
    return " ".join(com_secao.split())
