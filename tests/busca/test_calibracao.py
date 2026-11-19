"""Testes da calibração do limiar, com uma tabela temporária no formato de `perguntas.md`."""

from __future__ import annotations

from pathlib import Path

import pytest
from calibracao import (
    PerguntaValidacao,
    ReferenciaSecao,
    ler_perguntas_validacao,
    pontuar_perguntas,
)

from busca.indice_memoria import IndiceEmMemoria
from nucleo.modelos import Secao, Vetor

TABELA = """# Validação

| # | Pergunta | Deve conter | Fontes que devem aparecer |
|---|---|---|---|
| 1 | Pergunta um? | algo | FIN-POL-001 §6 |
| 2 | Pergunta dois? | outra coisa | FIN-POL-001 §4, §5 |
| 3 | Pergunta três? | mais | FRO-POL-002 §6; FIN-POL-001 §4 |
| 4 | Pergunta quatro? | férias | RH-PRO-003 §2 a §4 |
| 5 | Pergunta cinco? | veículo | FRO-POL-002 §2 |
| 6 | Pergunta seis? | não há evidência nos documentos | nenhuma; não apresentar trecho |
"""


def _tabela_em_arquivo(tmp_path: Path) -> Path:
    caminho = tmp_path / "perguntas.md"
    caminho.write_text(TABELA, encoding="utf-8")
    return caminho


def test_le_seis_perguntas_e_ignora_cabecalho_e_separador(tmp_path: Path) -> None:
    perguntas = ler_perguntas_validacao(_tabela_em_arquivo(tmp_path))

    assert [pergunta.numero for pergunta in perguntas] == [1, 2, 3, 4, 5, 6]
    assert perguntas[0].texto == "Pergunta um?"


def test_le_secoes_com_lista_intervalo_e_documento_herdado(tmp_path: Path) -> None:
    perguntas = ler_perguntas_validacao(_tabela_em_arquivo(tmp_path))

    assert perguntas[0].fontes_esperadas == (ReferenciaSecao("FIN-POL-001", 6),)
    assert perguntas[1].fontes_esperadas == (
        ReferenciaSecao("FIN-POL-001", 4),
        ReferenciaSecao("FIN-POL-001", 5),
    )
    assert perguntas[2].fontes_esperadas == (
        ReferenciaSecao("FRO-POL-002", 6),
        ReferenciaSecao("FIN-POL-001", 4),
    )
    assert perguntas[3].fontes_esperadas == (
        ReferenciaSecao("RH-PRO-003", 2),
        ReferenciaSecao("RH-PRO-003", 3),
        ReferenciaSecao("RH-PRO-003", 4),
    )


def test_pergunta_sem_fonte_tem_lista_vazia(tmp_path: Path) -> None:
    perguntas = ler_perguntas_validacao(_tabela_em_arquivo(tmp_path))

    assert perguntas[5].fontes_esperadas == ()


def test_referencia_corresponde_a_secao_e_subsecoes() -> None:
    referencia = ReferenciaSecao("FIN-POL-001", 6)

    assert referencia.corresponde(_secao("FIN-POL-001", "6"))
    assert referencia.corresponde(_secao("FIN-POL-001", "6.1"))
    assert not referencia.corresponde(_secao("FIN-POL-001", "60"))
    assert not referencia.corresponde(_secao("FRO-POL-002", "6"))


def test_pontuar_separa_melhor_esperado_do_melhor_geral() -> None:
    # O melhor trecho geral é de outro documento; o esperado fica em segundo lugar.
    secao_geral = _secao("FRO-POL-002", "6")
    secao_esperada = _secao("FIN-POL-001", "6")
    indice = IndiceEmMemoria()
    indice.adicionar([secao_geral, secao_esperada], [(1.0, 0.0), (0.6, 0.8)])
    pergunta = PerguntaValidacao(
        numero=1,
        texto="pergunta",
        fontes_esperadas=(ReferenciaSecao("FIN-POL-001", 6),),
    )
    vetor_pergunta: Vetor = (1.0, 0.0)

    (resultado,) = pontuar_perguntas((pergunta,), (vetor_pergunta,), indice, total_secoes=2)

    assert resultado.melhor_geral is not None
    assert resultado.melhor_geral.secao == secao_geral
    assert resultado.melhor_geral.pontuacao == 1.0
    assert resultado.melhor_esperado is not None
    assert resultado.melhor_esperado.secao == secao_esperada
    assert resultado.melhor_esperado.pontuacao == pytest.approx(0.6)
    assert resultado.posicao_melhor_esperado == 2


def test_posicao_do_esperado_conta_secoes_distintas() -> None:
    # A seção geral tem duas entradas (texto e pergunta de FAQ); o esperado é a 2ª seção.
    secao_geral = _secao("FRO-POL-002", "faq-1")
    secao_esperada = _secao("FIN-POL-001", "6")
    indice = IndiceEmMemoria()
    indice.adicionar(
        [secao_geral, secao_geral, secao_esperada], [(1.0, 0.0), (0.9, 0.436), (0.6, 0.8)]
    )
    pergunta = PerguntaValidacao(
        numero=1, texto="pergunta", fontes_esperadas=(ReferenciaSecao("FIN-POL-001", 6),)
    )

    (resultado,) = pontuar_perguntas((pergunta,), ((1.0, 0.0),), indice, total_secoes=3)

    assert resultado.posicao_melhor_esperado == 2


def test_pergunta_sem_fonte_esperada_nao_tem_melhor_esperado() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("FIN-POL-001", "1")], [(1.0, 0.0)])
    pergunta = PerguntaValidacao(numero=6, texto="pergunta", fontes_esperadas=())

    (resultado,) = pontuar_perguntas((pergunta,), ((1.0, 0.0),), indice, total_secoes=1)

    assert resultado.melhor_esperado is None
    assert resultado.posicao_melhor_esperado is None
    assert resultado.melhor_geral is not None


def test_indice_vazio_devolve_pontuacoes_sem_trecho() -> None:
    pergunta = PerguntaValidacao(numero=1, texto="pergunta", fontes_esperadas=())

    (resultado,) = pontuar_perguntas((pergunta,), ((1.0, 0.0),), IndiceEmMemoria(), total_secoes=0)

    assert resultado.melhor_geral is None
    assert resultado.melhor_esperado is None


def _secao(documento: str, numero: str) -> Secao:
    return Secao(documento=documento, numero=numero, titulo=f"Seção {numero}", texto="texto")
