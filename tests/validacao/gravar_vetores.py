"""Grava os embeddings reais do modo offline da suíte de validação em `vetores_gravados.npz`.

Consome créditos da API. Regrave quando mudar `perguntas.md`, a base ou o modelo de embedding.
Uso: `.venv\Scripts\python.exe tests\validacao\gravar_vetores.py`.
A chave é o SHA-256 do texto enviado ao provedor, igual ao que `montar_assistente` envia.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import numpy as np

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_PROJETO / "src"))
sys.path.insert(0, str(RAIZ_PROJETO / "scripts"))

from calibracao import ler_perguntas_validacao  # noqa: E402

from busca.indexacao import entradas_indexaveis  # noqa: E402
from busca.provedor_openai import ProvedorEmbeddingOpenAI  # noqa: E402
from composicao import carregar_secoes  # noqa: E402
from config import carregar_configuracao  # noqa: E402

logger = logging.getLogger(__name__)

CAMINHO_PERGUNTAS = Path(__file__).resolve().parent / "perguntas.md"
CAMINHO_SAIDA = Path(__file__).resolve().parent / "vetores_gravados.npz"
PASTA_DOCUMENTOS = RAIZ_PROJETO / "base_conhecimento"
MODELO_EMBEDDING = "text-embedding-3-small"
TAMANHO_MAXIMO_CHUNK = 1200
TAMANHO_LOTE = 100


def chave_do_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    configuracao = carregar_configuracao()
    secoes = carregar_secoes(PASTA_DOCUMENTOS, TAMANHO_MAXIMO_CHUNK)
    perguntas = ler_perguntas_validacao(CAMINHO_PERGUNTAS)
    textos = [e.texto for e in entradas_indexaveis(secoes, perguntas_faq=True)] + [
        p.texto for p in perguntas
    ]

    provedor = ProvedorEmbeddingOpenAI(
        modelo=MODELO_EMBEDDING,
        chave=configuracao.chave_openai,
        tamanho_lote=TAMANHO_LOTE,
        timeout_segundos=configuracao.timeout_segundos,
    )
    vetores = provedor.gerar(textos)

    np.savez_compressed(
        CAMINHO_SAIDA,
        chaves=np.array([chave_do_texto(texto) for texto in textos]),
        vetores=np.array(vetores, dtype=np.float32),
        modelo=np.array(MODELO_EMBEDDING),
    )
    logger.info(
        "Gravados %d vetores (%d entradas de seção, com títulos de FAQ, e %d perguntas).",
        len(textos),
        len(textos) - len(perguntas),
        len(perguntas),
    )


if __name__ == "__main__":
    main()
