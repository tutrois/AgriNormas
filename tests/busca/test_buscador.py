"""Testes do buscador, com provedor falso e `IndiceEmMemoria` real (cosseno verdadeiro)."""

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
    """Vetores controlados por texto, com contagem de chamadas."""

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
    """Provedor defeituoso: devolve quantidade de vetores diferente de um."""

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


def _vetor_com_cosseno(cosseno: float) -> Vetor:
    """Vetor unitário cujo cosseno com a pergunta (1, 0) é `cosseno`."""
    return (cosseno, math.sqrt(1.0 - cosseno * cosseno))


def test_secao_com_duas_entradas_aparece_uma_vez_com_a_maior_pontuacao() -> None:
    # Cada FAQ tem duas entradas: o texto completo (0.4) e a pergunta (0.7).
    secao_faq = _secao("faq-1")
    secao_outra = _secao("2")
    indice = IndiceEmMemoria()
    indice.adicionar(
        [secao_faq, secao_faq, secao_outra],
        [_vetor_com_cosseno(0.4), _vetor_com_cosseno(0.7), _vetor_com_cosseno(0.9)],
    )
    buscador, _ = _buscador(indice, limiar=0.5, top_k=3)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_outra, secao_faq]
    assert resultados[1].pontuacao == pytest.approx(0.7)


def test_pergunta_de_faq_acima_do_limiar_traz_a_secao_mesmo_com_o_texto_abaixo() -> None:
    secao_faq = _secao("faq-1")
    indice = IndiceEmMemoria()
    indice.adicionar(
        [secao_faq, secao_faq],
        [_vetor_com_cosseno(0.4), _vetor_com_cosseno(0.7)],
    )
    buscador, _ = _buscador(indice, limiar=0.6)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_faq]
    assert resultados[0].pontuacao == pytest.approx(0.7)


def test_limiar_nao_traz_secao_cujas_entradas_estao_todas_abaixo_dele() -> None:
    secao_faq = _secao("faq-1")
    indice = IndiceEmMemoria()
    indice.adicionar(
        [secao_faq, secao_faq],
        [_vetor_com_cosseno(0.4), _vetor_com_cosseno(0.5)],
    )
    buscador, _ = _buscador(indice, limiar=0.6)

    assert buscador.buscar(PERGUNTA) == ()


def test_top_k_conta_secoes_distintas_e_nao_entradas() -> None:
    # Sem deduplicar, as duas primeiras posições seriam da mesma seção e o resultado teria só ela.
    secao_a, secao_b, secao_c = _secao("faq-1"), _secao("2"), _secao("3")
    indice = IndiceEmMemoria()
    indice.adicionar(
        [secao_a, secao_a, secao_b, secao_c],
        [
            _vetor_com_cosseno(0.9),
            _vetor_com_cosseno(0.8),
            _vetor_com_cosseno(0.7),
            _vetor_com_cosseno(0.6),
        ],
    )
    buscador, _ = _buscador(indice, limiar=0.0, top_k=2)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [secao_a, secao_b]


def test_top_k_com_muitas_secoes_repetidas_ainda_devolve_top_k_distintas() -> None:
    secoes = [_secao(f"faq-{numero}") for numero in range(1, 4)]
    indice = IndiceEmMemoria()
    entradas = [secao for secao in secoes for _ in range(2)]
    vetores = [_vetor_com_cosseno(0.9 - posicao * 0.05) for posicao in range(len(entradas))]
    indice.adicionar(entradas, vetores)
    buscador, _ = _buscador(indice, limiar=0.0, top_k=3)

    resultados = buscador.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == secoes
