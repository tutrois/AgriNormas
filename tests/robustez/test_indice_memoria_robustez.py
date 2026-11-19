"""Casos de borda e de erro de `IndiceEmMemoria.adicionar` e `IndiceEmMemoria.buscar`."""

from __future__ import annotations

import math

import pytest

from busca.indice_memoria import IndiceEmMemoria
from nucleo.erros import ErroBusca
from nucleo.modelos import Secao


def _secao(numero: str) -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Seção {numero}", texto="texto")


def _indice_com(*pares: tuple[str, tuple[float, ...]]) -> IndiceEmMemoria:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao(numero) for numero, _ in pares], [vetor for _, vetor in pares])
    return indice


def test_indice_com_um_unico_vetor_devolve_esse_item_com_pontuacao_um() -> None:
    unico = _secao("1")
    indice = IndiceEmMemoria()
    indice.adicionar([unico], [(0.3, 0.4)])

    resultados = indice.buscar((0.3, 0.4), 5)

    assert len(resultados) == 1
    assert resultados[0].secao == unico
    assert resultados[0].pontuacao == pytest.approx(1.0)


def test_empates_de_pontuacao_devolvem_ambos_em_ordem_nao_crescente() -> None:
    indice = _indice_com(("1", (1.0, 0.0)), ("2", (2.0, 0.0)), ("3", (0.0, 1.0)))

    resultados = indice.buscar((1.0, 0.0), 2)

    numeros = {trecho.secao.numero for trecho in resultados}
    assert numeros == {"1", "2"}
    assert resultados[0].pontuacao == pytest.approx(1.0)
    assert resultados[1].pontuacao == pytest.approx(1.0)


def test_pontuacoes_saem_em_ordem_nao_crescente_para_todo_k() -> None:
    indice = _indice_com(
        ("1", (0.0, 1.0)),
        ("2", (0.6, 0.8)),
        ("3", (1.0, 0.0)),
        ("4", (0.8, 0.6)),
    )

    pontuacoes = [trecho.pontuacao for trecho in indice.buscar((1.0, 0.0), 4)]

    assert pontuacoes == sorted(pontuacoes, reverse=True)


def test_resultados_sao_do_tipo_trecho_com_pontuacao_float_nativa() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    resultado = indice.buscar((1.0, 0.0), 1)[0]

    assert type(resultado.pontuacao) is float
    assert type(resultado.secao) is Secao


def test_consulta_com_dimensao_diferente_do_indice_nao_vazio_levanta_erro_busca() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    with pytest.raises(ErroBusca):
        indice.buscar((1.0, 0.0, 0.0), 1)


def test_consulta_de_norma_zero_em_indice_unico_devolve_pontuacao_zero() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    resultados = indice.buscar((0.0, 0.0), 1)

    assert resultados[0].pontuacao == 0.0
    assert math.isfinite(resultados[0].pontuacao)


def test_adicionar_recusado_por_dimensao_nao_altera_um_indice_preenchido() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("2"), _secao("3")], [(0.0, 1.0), (1.0, 0.0, 0.0)])

    numeros = [trecho.secao.numero for trecho in indice.buscar((1.0, 0.0), 10)]
    assert numeros == ["1"]


def test_adicionar_com_quantidades_diferentes_nao_altera_um_indice_preenchido() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("2"), _secao("3")], [(0.0, 1.0)])

    numeros = [trecho.secao.numero for trecho in indice.buscar((1.0, 0.0), 10)]
    assert numeros == ["1"]


def test_vetor_com_nan_no_adicionar_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1")], [(math.nan, 1.0)])


def test_vetor_com_infinito_no_adicionar_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1")], [(math.inf, 1.0)])


def test_consulta_com_nan_levanta_erro_busca() -> None:
    indice = _indice_com(("1", (1.0, 0.0)))

    with pytest.raises(ErroBusca):
        indice.buscar((math.nan, 0.0), 1)


def test_nan_recusado_no_lote_nao_deixa_vetor_invalido_no_indice() -> None:
    # Cobre a regra de atomicidade: mesmo que o NaN passe, o lote recusado não entra.
    indice = _indice_com(("1", (1.0, 0.0)))

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("2"), _secao("3")], [(math.nan, 1.0), (1.0, 0.0, 0.0)])

    numeros = [trecho.secao.numero for trecho in indice.buscar((1.0, 0.0), 10)]
    assert numeros == ["1"]


def test_vetor_com_texto_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1")], [("a", "b")])  # type: ignore[list-item]


def test_vetor_none_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1")], [None])  # type: ignore[list-item]
