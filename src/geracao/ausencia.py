"""Afirmações de ausência e de recusa na resposta do modelo.

Heurística, sem rede nem SDK. Reconhece só sujeito explícito com verbo ativo ("o documento
não define X"); voz passiva e sinônimos do objeto passam sem conferência. Os textos são
comparados sem acento e em minúsculas.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from nucleo.modelos import Trecho

# Frases já normalizadas (sem acento, minúsculas, espaços simples), comparadas com o texto
# normalizado. Se qualquer uma aparecer com a flag de evidência verdadeira, a resposta é recusada.
FRASES_NEGACAO_EVIDENCIA: tuple[str, ...] = (
    "nao ha evidencia",
    "nao encontrei evidencia",
    "nao existe evidencia",
    "nao foi encontrada evidencia",
    "nao ha informacao",
    "nao encontrei informacao",
    "nao existe informacao",
    "nao foi encontrada informacao",
)

# Aplicados ao texto normalizado (sem acento, minúsculas). O objeto da ausência vai até a primeira
# pontuação, colchete ou conector " e "/" ou ", para não conferir o complemento "e não trata de".
# Aceita sujeito e verbo no plural ("documentos não definem") e "também" antes do "não". Vírgulas
# logo depois do verbo são puladas, para que um aposto não deixe o objeto vazio.
PADRAO_AFIRMACAO_AUSENCIA = re.compile(
    r"\b(?:documento|norma|politica|procedimento|trecho)s?\s+(?:tambem\s+)?nao\s+"
    r"(?:define|estabelece|traz|especifica|preve|determina|fixa)m?[\s,]+([^.,;:\[\]]*)"
)
PADRAO_FIM_OBJETO = re.compile(r"\s(?:e|ou|nem)\s")
PADRAO_PALAVRA = re.compile(r"\w+")
TAMANHO_MINIMO_PALAVRA_CONTEUDO = 4
TAMANHO_RADICAL = 6
# Terminações de plural, já sem acento, testadas nesta ordem; só a primeira que casar é trocada.
TROCAS_PLURAL: tuple[tuple[str, str], ...] = (
    ("oes", "ao"),
    ("aes", "ao"),
    ("aos", "ao"),
    ("ais", "al"),
    ("eis", "el"),
    ("ns", "m"),
    ("es", ""),
    ("s", ""),
)
# Vogal final de gênero ou de tema, retirada depois do plural: `diario`/`diaria`, `limite`/`limit`.
VOGAIS_FINAIS = ("a", "e", "o")
PALAVRAS_GENERICAS_AUSENCIA = frozenset(
    {
        "valor",
        "valores",
        "informacao",
        "informacoes",
        "quantidade",
        "numero",
        "dados",
        "regra",
        "regras",
        "propria",
        "proprio",
        "especifico",
        "especifica",
        "especificos",
        "especificas",
        "esse",
        "essa",
        "esses",
        "essas",
        "este",
        "esta",
        "assunto",
        "sobre",
        "para",
        "pela",
        "pelo",
        "pelas",
        "pelos",
        "qual",
        "quais",
    }
)


def ausencias_sustentadas(texto: str, citados: Sequence[Trecho]) -> bool:
    """Confere se cada afirmação de ausência do texto fala de algo presente nos trechos citados."""
    palavras_citadas = {
        _radical(palavra)
        for trecho in citados
        for palavra in PADRAO_PALAVRA.findall(
            _normalizar(f"{trecho.secao.titulo} {trecho.secao.texto}")
        )
    }
    for objeto in PADRAO_AFIRMACAO_AUSENCIA.findall(_normalizar(texto)):
        objeto_sem_complemento = PADRAO_FIM_OBJETO.split(objeto, maxsplit=1)[0]
        if any(
            _radical(palavra) not in palavras_citadas
            for palavra in _palavras_de_conteudo(objeto_sem_complemento)
        ):
            return False
    return True


def _palavras_de_conteudo(texto: str) -> list[str]:
    return [
        palavra
        for palavra in PADRAO_PALAVRA.findall(texto)
        if len(palavra) >= TAMANHO_MINIMO_PALAVRA_CONTEUDO
        and palavra not in PALAVRAS_GENERICAS_AUSENCIA
    ]


def _radical(palavra: str) -> str:
    """Radical grosseiro (plural, vogal final, truncamento) para tolerar flexão."""
    singular = _singular(palavra)
    if len(singular) > TAMANHO_MINIMO_PALAVRA_CONTEUDO and singular.endswith(VOGAIS_FINAIS):
        singular = singular[:-1]
    return singular[:TAMANHO_RADICAL]


def _singular(palavra: str) -> str:
    for terminacao, troca in TROCAS_PLURAL:
        if palavra.endswith(terminacao):
            return palavra[: -len(terminacao)] + troca
    return palavra


def diz_nao_ha_evidencia(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return any(frase in normalizado for frase in FRASES_NEGACAO_EVIDENCIA)


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples, para comparar a frase de recusa."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(
        caractere for caractere in decomposto if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acento.split())
