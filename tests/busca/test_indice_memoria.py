"""Testes do índice vetorial em memória (HIST-010)."""

import math
import warnings

import pytest

from busca.indice_memoria import (
    MENSAGEM_INTEIRO_FORA_DO_LIMITE,
    MENSAGEM_VALOR_NAO_FINITO,
    MENSAGEM_VALOR_NAO_NUMERICO,
    MENSAGEM_VETOR_NAO_UNIDIMENSIONAL,
    IndiceEmMemoria,
)
from nucleo.contratos import Indice
from nucleo.erros import ErroBusca
from nucleo.modelos import Secao


def _secao(numero: str, texto: str = "conteúdo normativo") -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Seção {numero}", texto=texto)


def test_implementa_o_protocolo_indice() -> None:
    indice: Indice = IndiceEmMemoria()

    assert indice.buscar((1.0, 0.0), 1) == ()


def test_busca_devolve_os_dois_mais_proximos_em_ordem_decrescente() -> None:
    # Inseridos fora da ordem de similaridade, para não passar por acaso.
    indice = IndiceEmMemoria()
    secao_ortogonal = _secao("1")
    secao_parcial = _secao("2")
    secao_alinhada = _secao("3")
    indice.adicionar(
        [secao_ortogonal, secao_parcial, secao_alinhada],
        [(0.0, 1.0), (0.6, 0.8), (1.0, 0.0)],
    )

    resultados = indice.buscar((1.0, 0.0), 2)

    assert [trecho.secao for trecho in resultados] == [secao_alinhada, secao_parcial]
    assert resultados[0].pontuacao == pytest.approx(1.0)
    assert resultados[1].pontuacao == pytest.approx(0.6)
    assert resultados[0].pontuacao >= resultados[1].pontuacao


def test_vetor_igual_a_um_item_tem_pontuacao_proxima_de_um() -> None:
    indice = IndiceEmMemoria()
    alvo = _secao("6.1")
    indice.adicionar([_secao("1"), alvo], [(1.0, 2.0, 0.5), (3.0, 4.0, 0.0)])

    # Vetor de norma diferente de 1: a normalização não pode mudar a pontuação.
    resultados = indice.buscar((3.0, 4.0, 0.0), 1)

    assert resultados[0].secao == alvo
    assert resultados[0].pontuacao == pytest.approx(1.0, abs=1e-9)


def test_indice_vazio_devolve_tupla_vazia() -> None:
    assert IndiceEmMemoria().buscar((1.0, 0.0), 3) == ()


def test_adicionar_listas_vazias_nao_faz_nada() -> None:
    indice = IndiceEmMemoria()

    indice.adicionar([], [])

    assert indice.buscar((1.0, 0.0), 3) == ()


def test_k_maior_que_o_numero_de_vetores_devolve_todos() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])

    resultados = indice.buscar((1.0, 0.0), 10)

    assert len(resultados) == 2


@pytest.mark.parametrize("k", [0, -1])
def test_k_nao_positivo_devolve_tupla_vazia(k: int) -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    assert indice.buscar((1.0, 0.0), k) == ()


def test_adicionar_em_varias_chamadas_acumula_os_vetores() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(0.0, 1.0)])
    segunda = _secao("2")
    indice.adicionar([segunda], [(1.0, 0.0)])

    resultados = indice.buscar((1.0, 0.0), 1)

    assert resultados[0].secao == segunda


def test_secao_recuperada_e_a_mesma_que_foi_guardada() -> None:
    indice = IndiceEmMemoria()
    secao = _secao("3.1", texto="Texto integral da seção.")
    indice.adicionar([secao], [(0.5, 0.5)])

    resultado = indice.buscar((0.5, 0.5), 1)[0]

    assert resultado.secao == secao
    assert resultado.secao.texto == "Texto integral da seção."


def test_quantidade_diferente_de_secoes_e_vetores_levanta_erro_sem_conteudo() -> None:
    indice = IndiceEmMemoria()
    secreta = _secao("1", texto="TEXTO-CONFIDENCIAL-DA-SECAO")

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([secreta, _secao("2")], [(1.0, 0.0)])

    assert "TEXTO-CONFIDENCIAL" not in str(excinfo.value)
    assert indice.buscar((1.0, 0.0), 5) == ()


def test_vetores_de_dimensoes_diferentes_no_lote_levantam_erro() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (1.0, 0.0, 0.0)])

    assert indice.buscar((1.0, 0.0), 5) == ()


def test_lote_com_dimensao_divergente_nao_altera_indice_preenchido() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("3"), _secao("4")], [(1.0, 0.0), (1.0, 0.0, 0.0)])

    resultados = indice.buscar((1.0, 0.0), 10)
    assert [trecho.secao for trecho in resultados] == [_secao("1"), _secao("2")]
    assert resultados[0].pontuacao == pytest.approx(1.0)
    assert resultados[1].pontuacao == pytest.approx(0.0, abs=1e-9)


def test_vetor_de_dimensao_diferente_do_indice_levanta_erro_no_adicionar() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("2")], [(1.0, 0.0, 0.0)])


def test_vetor_de_consulta_de_dimensao_diferente_levanta_erro() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca):
        indice.buscar((1.0, 0.0, 0.0), 1)


def test_vetor_vazio_levanta_erro() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("1")], [()])


def test_consulta_de_norma_zero_devolve_pontuacao_zero() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])

    resultados = indice.buscar((0.0, 0.0), 2)

    assert len(resultados) == 2
    assert all(trecho.pontuacao == 0.0 for trecho in resultados)


def test_vetor_armazenado_de_norma_zero_nao_quebra_a_busca() -> None:
    indice = IndiceEmMemoria()
    degenerado = _secao("1")
    indice.adicionar([degenerado, _secao("2")], [(0.0, 0.0), (1.0, 0.0)])

    resultados = indice.buscar((1.0, 0.0), 2)

    assert resultados[0].secao == _secao("2")
    assert resultados[1].secao == degenerado
    assert resultados[1].pontuacao == 0.0


@pytest.mark.parametrize("valor_invalido", [math.nan, math.inf, -math.inf])
def test_vetor_com_nan_ou_infinito_no_adicionar_levanta_erro_sem_alterar_o_indice(
    valor_invalido: float,
) -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("1")], [(valor_invalido, 1.0)])

    assert str(excinfo.value) == MENSAGEM_VALOR_NAO_FINITO
    assert indice.buscar((1.0, 0.0), 5) == ()


def test_nan_em_adicionar_nao_altera_indice_preenchido() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca):
        indice.adicionar([_secao("2")], [(math.nan, 1.0)])

    resultados = indice.buscar((1.0, 0.0), 5)
    assert [trecho.secao for trecho in resultados] == [_secao("1")]
    assert resultados[0].pontuacao == pytest.approx(1.0)


@pytest.mark.parametrize("valor_invalido", [math.nan, math.inf, -math.inf])
def test_consulta_com_nan_ou_infinito_levanta_erro_sem_alterar_o_indice(
    valor_invalido: float,
) -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca) as excinfo:
        indice.buscar((valor_invalido, 0.0), 1)

    assert str(excinfo.value) == MENSAGEM_VALOR_NAO_FINITO
    resultados = indice.buscar((1.0, 0.0), 5)
    assert [trecho.secao for trecho in resultados] == [_secao("1")]


def test_consulta_com_nan_em_indice_vazio_levanta_erro() -> None:
    with pytest.raises(ErroBusca):
        IndiceEmMemoria().buscar((math.nan, 0.0), 1)


@pytest.mark.parametrize(
    "vetor_invalido",
    [("a", "b"), ("1.0", "0.0"), (1.0, None), None],
)
def test_vetor_nao_numerico_levanta_erro_busca(vetor_invalido: object) -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("1")], [vetor_invalido])  # type: ignore[list-item]

    assert str(excinfo.value) == MENSAGEM_VALOR_NAO_NUMERICO
    assert indice.buscar((1.0, 0.0), 5) == ()


def test_consulta_nao_numerica_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca):
        indice.buscar(("a", "b"), 1)  # type: ignore[arg-type]


def test_consulta_none_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca):
        indice.buscar(None, 1)  # type: ignore[arg-type]


def test_normas_zero_nao_emitem_runtime_warning() -> None:
    indice = IndiceEmMemoria()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        indice.adicionar([_secao("1"), _secao("2")], [(0.0, 0.0), (1.0, 0.0)])
        resultados = indice.buscar((0.0, 0.0), 2)

    assert [trecho.pontuacao for trecho in resultados] == [0.0, 0.0]


def test_valores_grandes_nao_estouram_a_normalizacao() -> None:
    # Com norma calculada direto, 1e200 ao quadrado estouraria e o vetor viraria zero.
    indice = IndiceEmMemoria()
    alvo = _secao("1")
    indice.adicionar([alvo], [(1e200, 1e200)])

    resultado = indice.buscar((1.0, 1.0), 1)[0]

    assert resultado.secao == alvo
    assert resultado.pontuacao == pytest.approx(1.0)


MATRIZ_ANINHADA = ((1.0, 2.0), (3.0, 4.0))


def test_adicionar_vetor_aninhado_levanta_erro_busca_sem_alterar_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])
    antes = indice.buscar((1.0, 0.0), 5)

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("2")], [MATRIZ_ANINHADA])

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL
    assert indice.buscar((1.0, 0.0), 5) == antes


def test_adicionar_lote_com_vetor_aninhado_no_meio_nao_altera_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])
    antes = indice.buscar((1.0, 0.0), 5)

    with pytest.raises(ErroBusca):
        indice.adicionar(
            [_secao("2"), _secao("3"), _secao("4")],
            [(0.0, 1.0), MATRIZ_ANINHADA, (1.0, 1.0)],
        )

    assert indice.buscar((1.0, 0.0), 5) == antes


def test_adicionar_no_indice_vazio_com_vetor_aninhado_levanta_erro_busca() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("1")], [MATRIZ_ANINHADA])

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL
    assert indice.buscar((1.0, 0.0), 5) == ()


def test_buscar_com_consulta_aninhada_levanta_erro_busca_sem_alterar_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])
    antes = indice.buscar((1.0, 0.0), 5)

    with pytest.raises(ErroBusca) as excinfo:
        indice.buscar(MATRIZ_ANINHADA, 2)  # type: ignore[arg-type]

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL
    assert indice.buscar((1.0, 0.0), 5) == antes


def test_buscar_com_consulta_aninhada_em_indice_vazio_levanta_erro_busca() -> None:
    with pytest.raises(ErroBusca):
        IndiceEmMemoria().buscar(MATRIZ_ANINHADA, 1)  # type: ignore[arg-type]


def test_buscar_com_forma_irregular_levanta_erro_sem_alterar_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])
    antes = indice.buscar((1.0, 0.0), 5)

    with pytest.raises(ErroBusca) as excinfo:
        indice.buscar(((1.0, 2.0), (3.0,)), 5)  # type: ignore[arg-type]

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL
    assert indice.buscar((1.0, 0.0), 5) == antes


def test_buscar_com_consulta_matriz_identidade_levanta_erro_sem_alterar_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1"), _secao("2")], [(1.0, 0.0), (0.0, 1.0)])
    antes = indice.buscar((1.0, 0.0), 5)

    with pytest.raises(ErroBusca) as excinfo:
        indice.buscar(((1.0, 0.0), (0.0, 1.0)), 5)  # type: ignore[arg-type]

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL
    assert indice.buscar((1.0, 0.0), 5) == antes


def test_vetor_irregular_levanta_erro_busca_de_forma_unidimensional() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("1")], [((1.0, 2.0), (3.0,))])  # type: ignore[list-item]

    assert str(excinfo.value) == MENSAGEM_VETOR_NAO_UNIDIMENSIONAL


def test_inteiro_grande_demais_tem_mensagem_propria_sem_alterar_o_indice() -> None:
    indice = IndiceEmMemoria()
    indice.adicionar([_secao("1")], [(1.0, 0.0)])

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("2")], [(10**400, 1.0)])

    assert str(excinfo.value) == MENSAGEM_INTEIRO_FORA_DO_LIMITE
    assert indice.buscar((1.0, 0.0), 5)[0].pontuacao == pytest.approx(1.0)


def test_inteiro_grande_mas_representavel_em_float_e_aceito() -> None:
    indice = IndiceEmMemoria()
    alvo = _secao("1")

    indice.adicionar([alvo], [(10**20, 1.0)])

    assert indice.buscar((10**20, 1.0), 1)[0].secao == alvo


def test_inteiro_grande_junto_de_texto_continua_sendo_valor_nao_numerico() -> None:
    indice = IndiceEmMemoria()

    with pytest.raises(ErroBusca) as excinfo:
        indice.adicionar([_secao("1")], [(10**400, "a")])  # type: ignore[list-item]

    assert str(excinfo.value) == MENSAGEM_VALOR_NAO_NUMERICO
