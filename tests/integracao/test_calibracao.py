"""Testes de integração do buscador com a API real da OpenAI (HIST-011).

Rodam só com `pytest -m integracao`, com OPENAI_API_KEY no `.env`. Consomem créditos:
os chunks são embedados uma vez por módulo, as seis perguntas em um pedido, e as perguntas
1 e 4 uma vez cada pelo `BuscadorSemantico`.

A pergunta 6 não tem resposta nos documentos. O teste só confere que as pontuações foram
registradas, sem afirmar se passa ou não do limiar: essa decisão fica no ADR-002.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from busca.buscador import BuscadorSemantico
from busca.calibracao import (
    PerguntaValidacao,
    PontuacaoPergunta,
    ler_perguntas_validacao,
    pontuar_perguntas,
)
from busca.indexacao import construir_indice
from busca.indice_memoria import IndiceEmMemoria
from busca.provedor_openai import ProvedorEmbeddingOpenAI
from config import Configuracao, carregar_configuracao
from documentos.chunker_secao import ChunkerPorSecao
from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import limpar_paginas
from documentos.metadados import extrair_metadados
from nucleo.modelos import Secao

pytestmark = pytest.mark.integracao

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
CAMINHO_PERGUNTAS = RAIZ_PROJETO / "tests" / "validacao" / "perguntas.md"
TAMANHO_LOTE = 100
NUMERO_PERGUNTA_SEM_RESPOSTA = 6
# Limiar escolhido e registrado no ADR-002 (docs/decisoes/ADR-002-limiar-de-similaridade.md).
# Constante de propósito: o teste de calibração não depende do valor de `.env`.
LIMIAR_ADR_002 = 0.60


@dataclass(frozen=True)
class _Ambiente:
    configuracao: Configuracao
    provedor: ProvedorEmbeddingOpenAI
    indice: IndiceEmMemoria
    pontuacoes: tuple[PontuacaoPergunta, ...]


def _secoes_do_corpus(pasta: Path, tamanho_maximo: int) -> tuple[Secao, ...]:
    """Mesmo fluxo de `scripts/calibrar_limiar.py`: leitura, metadados, limpeza e chunking."""
    secoes: list[Secao] = []
    for caminho in sorted(pasta.glob("*.pdf")):
        paginas = LeitorPdf().ler(caminho)
        codigo = extrair_metadados(paginas[0].texto, caminho).codigo
        secoes.extend(
            ChunkerPorSecao(tamanho_maximo=tamanho_maximo).dividir(codigo, limpar_paginas(paginas))
        )
    return tuple(secoes)


@pytest.fixture(scope="module")
def ambiente() -> _Ambiente:
    configuracao = carregar_configuracao()
    secoes = _secoes_do_corpus(configuracao.pasta_documentos, configuracao.tamanho_maximo_chunk)
    provedor = ProvedorEmbeddingOpenAI(
        modelo=configuracao.modelo_embedding,
        chave=configuracao.chave_openai,
        tamanho_lote=TAMANHO_LOTE,
        timeout_segundos=configuracao.timeout_segundos,
    )
    indice = construir_indice(secoes, provedor)
    perguntas = ler_perguntas_validacao(CAMINHO_PERGUNTAS)
    vetores = provedor.gerar(tuple(pergunta.texto for pergunta in perguntas))
    pontuacoes = pontuar_perguntas(perguntas, vetores, indice, total_secoes=len(secoes))
    return _Ambiente(configuracao, provedor, indice, pontuacoes)


def _buscador(ambiente: _Ambiente) -> BuscadorSemantico:
    return BuscadorSemantico(
        ambiente.provedor,
        ambiente.indice,
        limiar_similaridade=ambiente.configuracao.limiar_similaridade,
        top_k=ambiente.configuracao.top_k,
    )


def _pergunta(ambiente: _Ambiente, numero: int) -> PerguntaValidacao:
    (pergunta,) = (p.pergunta for p in ambiente.pontuacoes if p.pergunta.numero == numero)
    return pergunta


def _documentos_e_secoes(trechos: Sequence[Secao]) -> set[tuple[str, str]]:
    return {(secao.documento, secao.numero) for secao in trechos}


def _contem_secao(secoes: set[tuple[str, str]], documento: str, numero: int) -> bool:
    """Confere a seção e suas subseções (ex.: `6` e `6.1` para §6)."""
    return any(
        doc == documento and (secao == str(numero) or secao.startswith(f"{numero}."))
        for doc, secao in secoes
    )


def test_pergunta_1_traz_trecho_de_fin_pol_001_secao_6(ambiente: _Ambiente) -> None:
    pergunta = _pergunta(ambiente, 1)

    trechos = _buscador(ambiente).buscar(pergunta.texto)

    secoes = _documentos_e_secoes([trecho.secao for trecho in trechos])
    assert _contem_secao(secoes, "FIN-POL-001", 6), secoes


def test_pergunta_4_traz_trecho_de_rh_pro_003(ambiente: _Ambiente) -> None:
    pergunta = _pergunta(ambiente, 4)

    trechos = _buscador(ambiente).buscar(pergunta.texto)

    secoes = _documentos_e_secoes([trecho.secao for trecho in trechos])
    assert any(documento == "RH-PRO-003" for documento, _ in secoes), secoes


def test_calibracao_registra_pontuacao_das_seis_perguntas(ambiente: _Ambiente) -> None:
    assert len(ambiente.pontuacoes) == 6
    assert all(resultado.melhor_geral is not None for resultado in ambiente.pontuacoes)


def test_pergunta_6_tem_pontuacao_registrada_sem_decisao_de_limiar(ambiente: _Ambiente) -> None:
    resultado = next(
        p for p in ambiente.pontuacoes if p.pergunta.numero == NUMERO_PERGUNTA_SEM_RESPOSTA
    )

    assert resultado.melhor_geral is not None
    assert -1.0 <= resultado.melhor_geral.pontuacao <= 1.0


def test_perguntas_1_a_5_tem_trecho_esperado_acima_do_limiar(ambiente: _Ambiente) -> None:
    """Confirma a escolha do limiar registrada no ADR-002 (perguntas 1 a 5)."""
    limiar = LIMIAR_ADR_002
    for resultado in ambiente.pontuacoes:
        if resultado.pergunta.numero == NUMERO_PERGUNTA_SEM_RESPOSTA:
            continue
        assert resultado.melhor_esperado is not None, resultado.pergunta.numero
        assert resultado.melhor_esperado.pontuacao >= limiar, resultado.pergunta.numero
