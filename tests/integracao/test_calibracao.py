"""Integração do buscador com a API real: só roda com `pytest -m integracao` e consome créditos.

Desde o ADR-011, `LIMIAR_SIMILARIDADE` é só um piso (0,40). O critério de recuperação é o melhor
trecho esperado entre as `TOP_K` primeiras e acima do piso, que é o que leva a seção ao modelo.
As perguntas 6 e 7 só listam `§faq-5`, que `ReferenciaSecao` não lê; para elas só se confere que
a pontuação foi registrada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from calibracao import (
    PerguntaValidacao,
    PontuacaoPergunta,
    ler_perguntas_validacao,
    pontuar_perguntas,
)

from busca.buscador import BuscadorSemantico
from busca.indexacao import construir_indice, entradas_indexaveis
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
TOTAL_PERGUNTAS = 7
# Piso e top-k do ADR-011, fixos para o teste não depender do `.env`.
PISO_ADR_011 = 0.40
TOP_K_ADR_011 = 10
# Mesma configuração de `src/composicao.py` (FAQ como entrada própria). A linha de base do ADR-002
# foi medida com False; para reproduzi-la, troque aqui e em `scripts/calibrar_limiar.py`.
PERGUNTAS_FAQ = True


@dataclass(frozen=True)
class _Ambiente:
    configuracao: Configuracao
    provedor: ProvedorEmbeddingOpenAI
    indice: IndiceEmMemoria
    pontuacoes: tuple[PontuacaoPergunta, ...]


def _secoes_do_corpus(pasta: Path, tamanho_maximo: int) -> tuple[Secao, ...]:
    """Mesmo fluxo de `scripts/calibrar_limiar.py`."""
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
    indice = construir_indice(secoes, provedor, perguntas_faq=PERGUNTAS_FAQ)
    total_entradas = len(entradas_indexaveis(secoes, perguntas_faq=PERGUNTAS_FAQ))
    perguntas = ler_perguntas_validacao(CAMINHO_PERGUNTAS)
    vetores = provedor.gerar(tuple(pergunta.texto for pergunta in perguntas))
    pontuacoes = pontuar_perguntas(perguntas, vetores, indice, total_secoes=total_entradas)
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


def _com_secao_numerica(ambiente: _Ambiente) -> tuple[PontuacaoPergunta, ...]:
    return tuple(p for p in ambiente.pontuacoes if p.pergunta.fontes_esperadas)


def test_calibracao_registra_pontuacao_das_sete_perguntas(ambiente: _Ambiente) -> None:
    assert len(ambiente.pontuacoes) == TOTAL_PERGUNTAS
    assert all(resultado.melhor_geral is not None for resultado in ambiente.pontuacoes)


def test_perguntas_so_com_faq_tem_pontuacao_registrada(ambiente: _Ambiente) -> None:
    so_faq = [p for p in ambiente.pontuacoes if not p.pergunta.fontes_esperadas]

    assert [p.pergunta.numero for p in so_faq] == [6, 7]
    for resultado in so_faq:
        assert resultado.melhor_geral is not None
        assert -1.0 <= resultado.melhor_geral.pontuacao <= 1.0


def test_perguntas_com_secao_numerica_tem_trecho_esperado_acima_do_piso(
    ambiente: _Ambiente,
) -> None:
    for resultado in _com_secao_numerica(ambiente):
        assert resultado.melhor_esperado is not None, resultado.pergunta.numero
        assert resultado.melhor_esperado.pontuacao >= PISO_ADR_011, resultado.pergunta.numero


def test_perguntas_com_secao_numerica_tem_trecho_esperado_no_top_k(ambiente: _Ambiente) -> None:
    """Seções esperadas adicionais fora do top-k (ex.: FIN-POL-001 §4 na pergunta 3) são cobradas
    em `tests/validacao/`."""
    for resultado in _com_secao_numerica(ambiente):
        posicao = resultado.posicao_melhor_esperado
        assert posicao is not None, resultado.pergunta.numero
        assert posicao <= TOP_K_ADR_011, (resultado.pergunta.numero, posicao)
