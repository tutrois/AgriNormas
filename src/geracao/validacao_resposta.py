"""Validação da saída do modelo e das citações (HIST-015).

Função pura: recebe o texto devolvido pelo modelo e os trechos recuperados, e devolve uma
`Resposta`. Não sabe de rede nem do SDK. É a última barreira contra citação inventada, e não
depende do modelo: toda fonte citada precisa existir entre os trechos recuperados.

Quando a saída não serve, a função devolve `Resposta.sem_evidencia()` e registra o motivo em
log, com mensagem fixa. O conteúdo do modelo nunca entra no log.

Regras de decisão, em ordem:
1. `evidencia_suficiente` falso: recusa.
2. Texto que nega evidência (ex.: "não há evidência") é recusado, mesmo que cite trecho
   recuperado. A negação é tratada como recusa inteira, sem exceção por citação no texto.
3. Texto vazio, lista `fontes_citadas` vazia, ou qualquer citação (na lista ou no texto) que não
   esteja entre os trechos recuperados: a saída é inválida e vira recusa.
4. Caso contrário, devolve a resposta com as fontes: primeiro as de `fontes_citadas`, depois as
   citações do texto que não estavam na lista, sem repetição.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

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
MOTIVO_TEXTO_VAZIO = "texto da resposta vazio"
MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA = "texto diz não haver evidência, com a flag de evidência verdadeira"

MODELO_LOG_RECUSA = "Saída do modelo recusada: %s."

FRASE_SEM_EVIDENCIA = "nao ha evidencia"
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
    """Aplica as regras de decisão descritas no módulo."""
    if not bruta.evidencia_suficiente:
        return Resposta.sem_evidencia()

    if _diz_nao_ha_evidencia(bruta.texto):
        logger.info(MODELO_LOG_RECUSA, MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA)
        return Resposta.sem_evidencia()
    if not bruta.texto:
        raise _SaidaInvalida(MOTIVO_TEXTO_VAZIO)
    if not bruta.fontes_citadas:
        raise _SaidaInvalida(MOTIVO_SEM_FONTE)

    recuperados = _indexar_trechos(trechos)
    citacoes_no_texto = _citacoes_no_texto(bruta.texto)
    identificadores = _sem_repeticao((*bruta.fontes_citadas, *citacoes_no_texto))
    if any(identificador not in recuperados for identificador in identificadores):
        raise _SaidaInvalida(MOTIVO_FONTE_NAO_RECUPERADA)

    fontes = tuple(
        Fonte.de_secao(recuperados[identificador].secao) for identificador in identificadores
    )
    return Resposta(texto=bruta.texto, fontes=fontes, evidencia_suficiente=True)


def _ler_saida(saida: str) -> _SaidaModelo:
    """Confere a forma do JSON.

    `RecursionError` é tratado como JSON inválido: um texto com aninhamento extremo esgota a
    pilha do parser. O `raise` fica fora do `except`, para que o erro do parser não fique em
    `__context__`.
    """
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


def _diz_nao_ha_evidencia(texto: str) -> bool:
    return FRASE_SEM_EVIDENCIA in _normalizar(texto)


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples, para comparar a frase de recusa."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(
        caractere for caractere in decomposto if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acento.split())
