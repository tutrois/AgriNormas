"""Testes do buscador com limiar de similaridade (HIST-011, TSK-011.1).

Offline: o provedor é falso e devolve vetores controlados. O índice é o real
(`IndiceEmMemoria`), para que a pontuação por cosseno seja a de verdade.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from busca.buscador import MENSAGEM_VETOR_PERGUNTA_INVALIDO, BuscadorSemantico
from busca.indice_memoria import IndiceEmMemoria
from nucleo.contratos import Buscador
from nucleo.erros import ConfiguracaoInvalida, ErroBusca
from nucleo.modelos import Secao, Vetor

PERGUNTA = "pergunta de teste"


class ProvedorFalso:
    """Devolve vetores controlados por texto e conta as chamadas feitas."""

    def __init__(self, vetores: dict[str, Vetor]) -> None:
        self._vetores = vetores
        self.chamadas: list[tuple[str, ...]] = []

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.chamadas.append(tuple(textos))
        return tuple(self._vetores[texto] for texto in textos)


class ProvedorComErro:
    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        raise ErroBusca("falha simulada do provedor")


class ProvedorComQuantidadeErrada:
    """Devolve uma quantidade de vetores diferente de um, como um provedor defeituoso."""

    def __init__(self, vetores: tuple[Vetor, ...]) -> None:
        self._vetores = vetores

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        return self._vetores


def _secao(numero: str) -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Seção {numero}", texto="texto")


def _indice_com_tres_secoes() -> tuple[IndiceEmMemoria, Secao, Secao, Secao]:
    """Pontuações contra a pergunta (1, 0): A = 1.0, B = 0.6, C = 0.0."""
    secao_a = _secao("1")
    secao_b = _secao("2")
    secao_c = _secao("3")
    indice = IndiceEmMemoria()
    indice.adicionar([secao_c, secao_a, secao_b], [(0.0, 1.0), (1.0, 0.0), (0.6, 0.8)])
    return indice, secao_a, secao_b, secao_c


def _buscador(
    indice: IndiceEmMemoria,
    *,
    limiar: float,
    top_k: int = 3,
    vetor_pergunta: Vetor = (1.0, 0.0),
) -> tuple[BuscadorSemantico, ProvedorFalso]:
    provedor = ProvedorFalso({PERGUNTA: vetor_pergunta})
    buscador = BuscadorSemantico(provedor, indice, limiar_similaridade=limiar, top_k=top_k)
    return buscador, provedor


def test_implementa_o_protocolo_buscador() -> None:
    indice, *_ = _indice_com_tres_secoes()
    buscador: Buscador = BuscadorSemantico(
        ProvedorFalso({PERGUNTA: (1.0, 0.0)}),
        indice,
        limiar_similaridade=0.5,
        top_k=3,
    )

    assert buscador.buscar(PERGUNTA) != ()


def test_devolve_trechos_acima_do_limiar_do_mais_para_o_menos_similar() -> None:
    indice, secao_a, secao_b, _ = _indice_com_tres_secoes()
    buscador, _ = _buscador(indice, limiar=0.5)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_a, secao_b]
    assert resultados[0].pontuacao == pytest.approx(1.0)
    assert resultados[1].pontuacao == pytest.approx(0.6)


def test_descarta_trecho_abaixo_do_limiar() -> None:
    indice, _, _, secao_c = _indice_com_tres_secoes()
    buscador, _ = _buscador(indice, limiar=0.5)

    resultados = buscador.buscar(PERGUNTA)

    assert secao_c not in [trecho.secao for trecho in resultados]


def test_trecho_com_pontuacao_igual_ao_limiar_e_mantido() -> None:
    indice, secao_a, _, _ = _indice_com_tres_secoes()
    buscador, _ = _buscador(indice, limiar=1.0)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_a]


def test_sem_trecho_acima_do_limiar_devolve_tupla_vazia() -> None:
    # Pergunta oposta a todos os trechos: as pontuações são negativas ou nulas.
    indice, *_ = _indice_com_tres_secoes()
    buscador, _ = _buscador(indice, limiar=0.5, vetor_pergunta=(-1.0, 0.0))

    resultados = buscador.buscar(PERGUNTA)

    assert resultados == ()


def test_indice_vazio_devolve_tupla_vazia() -> None:
    buscador, _ = _buscador(IndiceEmMemoria(), limiar=0.0)

    assert buscador.buscar(PERGUNTA) == ()


def test_top_k_limita_os_candidatos_antes_do_limiar() -> None:
    indice, secao_a, _, _ = _indice_com_tres_secoes()
    buscador, _ = _buscador(indice, limiar=0.0, top_k=1)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_a]


def test_gera_embedding_da_pergunta_uma_vez_por_busca() -> None:
    indice, *_ = _indice_com_tres_secoes()
    buscador, provedor = _buscador(indice, limiar=0.5)

    buscador.buscar(PERGUNTA)

    assert provedor.chamadas == [(PERGUNTA,)]


def test_erro_do_provedor_propaga_como_erro_de_busca() -> None:
    indice, *_ = _indice_com_tres_secoes()
    buscador = BuscadorSemantico(ProvedorComErro(), indice, limiar_similaridade=0.5, top_k=3)

    with pytest.raises(ErroBusca):
        buscador.buscar(PERGUNTA)


@pytest.mark.parametrize("limiar", [-0.1, 1.1, math.nan, math.inf])
def test_limiar_fora_de_zero_a_um_e_recusado(limiar: float) -> None:
    indice, *_ = _indice_com_tres_secoes()

    with pytest.raises(ConfiguracaoInvalida):
        BuscadorSemantico(ProvedorFalso({}), indice, limiar_similaridade=limiar, top_k=3)


@pytest.mark.parametrize("top_k", [0, -1])
def test_top_k_menor_que_um_e_recusado(top_k: int) -> None:
    indice, *_ = _indice_com_tres_secoes()

    with pytest.raises(ConfiguracaoInvalida):
        BuscadorSemantico(ProvedorFalso({}), indice, limiar_similaridade=0.5, top_k=top_k)


@pytest.mark.parametrize("top_k", [3.0, 2.5, True, False, "3"])
def test_top_k_que_nao_e_inteiro_e_recusado(top_k: object) -> None:
    indice, *_ = _indice_com_tres_secoes()

    with pytest.raises(ConfiguracaoInvalida):
        BuscadorSemantico(
            ProvedorFalso({}),
            indice,
            limiar_similaridade=0.5,
            top_k=top_k,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "vetores",
    [
        (),
        ((1.0, 0.0), (0.0, 1.0)),
    ],
    ids=["lista_vazia", "dois_vetores"],
)
def test_quantidade_de_vetores_diferente_de_um_levanta_erro_de_busca(
    vetores: tuple[Vetor, ...],
) -> None:
    indice, *_ = _indice_com_tres_secoes()
    buscador = BuscadorSemantico(
        ProvedorComQuantidadeErrada(vetores),
        indice,
        limiar_similaridade=0.5,
        top_k=3,
    )

    with pytest.raises(ErroBusca) as erro:
        buscador.buscar(PERGUNTA)

    assert str(erro.value) == MENSAGEM_VETOR_PERGUNTA_INVALIDO
