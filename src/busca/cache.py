"""Cache dos vetores do índice em disco, chaveado pelo hash do texto e pelo modelo.

Lido com `allow_pickle=False`, para que um arquivo adulterado não execute código. Falha de
leitura ou de gravação vira só um aviso no log, sem conteúdo: o índice já está em memória e o
cache é recalculado depois.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from nucleo.modelos import Vetor

logger = logging.getLogger(__name__)

MENSAGEM_CACHE_ILEGIVEL = (
    "Cache de vetores ilegível ou inconsistente; os vetores serão recalculados."
)
MENSAGEM_CACHE_NAO_GRAVADO = "Não foi possível gravar o cache de vetores; ele será recalculado."

_CHAVE_HASHES = "hashes"
_CHAVE_MODELOS = "modelos"
_CHAVE_VETORES = "vetores"
_CHAVES_OBRIGATORIAS = (_CHAVE_HASHES, _CHAVE_MODELOS, _CHAVE_VETORES)
_SUFIXO_TEMPORARIO = ".tmp"
_ERROS_DE_LEITURA = (OSError, ValueError, EOFError, zipfile.BadZipFile)


class _ConteudoInvalido(Exception):
    """O arquivo abriu, mas as colunas ou os valores não fecham."""


@dataclass(frozen=True)
class EntradaCache:
    """Vetor de uma entrada do índice, identificado pelo hash do texto e pelo modelo."""

    hash_texto: str
    modelo: str
    vetor: Vetor


def hash_texto(texto: str) -> str:
    """SHA-256 hexadecimal do texto em UTF-8, estável entre execuções."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class RepositorioCacheVetores:
    """Lê e grava o arquivo de cache no caminho recebido."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho

    def ler(self, modelo: str) -> dict[str, Vetor]:
        """Devolve `{hash_texto: vetor}` das linhas do `modelo` dado.

        Arquivo ausente devolve `{}` em silêncio; ilegível ou inconsistente, `{}` com aviso.
        """
        try:
            arquivo = np.load(self._caminho, allow_pickle=False)
        except FileNotFoundError:
            return {}
        except _ERROS_DE_LEITURA:
            logger.warning(MENSAGEM_CACHE_ILEGIVEL)
            return {}

        try:
            if not isinstance(arquivo, np.lib.npyio.NpzFile):
                raise _ConteudoInvalido
            with arquivo:
                return _extrair_vetores(arquivo, modelo)
        except (*_ERROS_DE_LEITURA, _ConteudoInvalido):
            logger.warning(MENSAGEM_CACHE_ILEGIVEL)
            return {}

    def gravar(self, entradas: Sequence[EntradaCache]) -> None:
        """Substitui o arquivo pelas `entradas` atuais, de forma atômica.

        Sequência vazia grava cache vazio. Falha de escrita vira aviso, sem exceção.
        """
        temporario = self._caminho.with_name(self._caminho.name + _SUFIXO_TEMPORARIO)
        try:
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            hashes, modelos, vetores = _montar_colunas(entradas)
            with temporario.open("wb") as destino:
                np.savez(destino, hashes=hashes, modelos=modelos, vetores=vetores)
            os.replace(temporario, self._caminho)
        except OSError:
            logger.warning(MENSAGEM_CACHE_NAO_GRAVADO)
            with contextlib.suppress(OSError):
                temporario.unlink(missing_ok=True)


def _montar_colunas(
    entradas: Sequence[EntradaCache],
) -> tuple[NDArray[np.str_], NDArray[np.str_], NDArray[np.float64]]:
    """Hashes, modelos e vetores em colunas paralelas."""
    if not entradas:
        return (
            np.array([], dtype=str),
            np.array([], dtype=str),
            np.zeros((0, 0), dtype=np.float64),
        )
    return (
        np.array([entrada.hash_texto for entrada in entradas], dtype=str),
        np.array([entrada.modelo for entrada in entradas], dtype=str),
        np.array([entrada.vetor for entrada in entradas], dtype=np.float64),
    )


def _extrair_vetores(arquivo: np.lib.npyio.NpzFile, modelo: str) -> dict[str, Vetor]:
    if not all(chave in arquivo.files for chave in _CHAVES_OBRIGATORIAS):
        raise _ConteudoInvalido

    hashes = arquivo[_CHAVE_HASHES]
    modelos = arquivo[_CHAVE_MODELOS]
    vetores = arquivo[_CHAVE_VETORES]

    if hashes.dtype.kind != "U" or modelos.dtype.kind != "U":
        raise _ConteudoInvalido
    if vetores.dtype.kind != "f" or vetores.ndim != 2:
        raise _ConteudoInvalido
    if not len(hashes) == len(modelos) == vetores.shape[0]:
        raise _ConteudoInvalido
    if not np.isfinite(vetores).all():
        raise _ConteudoInvalido

    linhas = zip(hashes.tolist(), modelos.tolist(), vetores.tolist(), strict=True)
    return {
        hash_: tuple(vetor) for hash_, modelo_da_linha, vetor in linhas if modelo_da_linha == modelo
    }
