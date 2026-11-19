"""Testes do adaptador de busca com formulações (HIST-029, ADR-010).

Offline: o `Buscador` e o `ReescritorConsulta` são dublês. Os testes de equivalência usam o
`BuscadorSemantico` e o `IndiceEmMemoria` reais, com um provedor de embeddings falso.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import pytest

from busca.buscador import BuscadorSemantico
from busca.buscador_formulacoes import BuscadorComFormulacoes
from busca.indice_memoria import IndiceEmMemoria
from nucleo.contratos import Buscador, ReescritorConsulta
from nucleo.erros import ConfiguracaoInvalida, ErroBusca, ErroReescrita
from nucleo.modelos import Secao, Trecho, Vetor

PERGUNTA = "qual o limite de combustível"
CHAVE_FALSA = "sk-chave-falsa-para-teste"
LIMIAR = 0.6
TOP_K = 3


class BuscadorPorTexto:
    """Devolve os trechos configurados para cada texto buscado. Registra as buscas feitas."""

    def __init__(
        self,
        respostas: dict[str, tuple[Trecho, ...]] | None = None,
        textos_com_erro: frozenset[str] = frozenset(),
    ) -> None:
        self._respostas = respostas or {}
        self._textos_com_erro = textos_com_erro
        self.buscas: list[str] = []

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        self.buscas.append(pergunta)
        if pergunta in self._textos_com_erro:
            raise ErroBusca("falha simulada da busca")
        return self._respostas.get(pergunta, ())


class ReescritorFalso:
    """Devolve formulações fixas, ou levanta o erro configurado. Registra as chamadas."""

    def __init__(
        self,
        formulacoes: tuple[str, ...] = (),
        erro: ErroReescrita | None = None,
    ) -> None:
        self._formulacoes = formulacoes
        self._erro = erro
        self.chamadas: list[str] = []

    def reescrever(self, pergunta: str) -> tuple[str, ...]:
        self.chamadas.append(pergunta)
        if self._erro is not None:
            raise self._erro
        return self._formulacoes


class ProvedorPorTexto:
    """Devolve o vetor configurado para cada texto, sem rede."""

    def __init__(self, vetores: dict[str, Vetor]) -> None:
        self._vetores = vetores

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        return tuple(self._vetores[texto] for texto in textos)


def _secao(numero: str) -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Seção {numero}", texto="texto")


def _trecho(numero: str, pontuacao: float) -> Trecho:
    return Trecho(secao=_secao(numero), pontuacao=pontuacao)


def _adaptador(
    buscador: Buscador,
    reescritor: ReescritorConsulta,
    *,
    limiar: float = LIMIAR,
    top_k: int = TOP_K,
) -> BuscadorComFormulacoes:
    return BuscadorComFormulacoes(
        buscador,
        reescritor,
        limiar_similaridade=limiar,
        top_k=top_k,
    )


def test_implementa_o_protocolo_buscador() -> None:
    buscador: Buscador = _adaptador(BuscadorPorTexto(), ReescritorFalso())

    assert buscador.buscar(PERGUNTA) == ()


def test_pergunta_original_e_sempre_buscada_primeiro() -> None:
    buscador = BuscadorPorTexto()
    reescritor = ReescritorFalso(formulacoes=("formulação um", "formulação dois"))

    _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert buscador.buscas == [PERGUNTA, "formulação um", "formulação dois"]
    assert reescritor.chamadas == [PERGUNTA]


def test_pergunta_original_e_buscada_quando_o_reescritor_devolve_vazio() -> None:
    buscador = BuscadorPorTexto()

    _adaptador(buscador, ReescritorFalso(formulacoes=())).buscar(PERGUNTA)

    assert buscador.buscas == [PERGUNTA]


def test_formulacao_amplia_o_resultado_com_secao_que_so_ela_encontra() -> None:
    buscador = BuscadorPorTexto(
        respostas={
            PERGUNTA: (_trecho("4", 0.9),),
            "formulação": (_trecho("6", 0.7),),
        }
    )
    reescritor = ReescritorFalso(formulacoes=("formulação",))

    resultados = _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [_secao("4"), _secao("6")]


@pytest.mark.parametrize(
    ("pontuacao_original", "pontuacao_formulacao", "esperada"),
    [
        (0.65, 0.8, 0.8),  # a formulação é a maior
        (0.9, 0.7, 0.9),  # a original é a maior
    ],
    ids=["vence_a_formulacao", "vence_a_original"],
)
def test_secao_fica_com_a_maior_pontuacao_entre_as_buscas(
    pontuacao_original: float,
    pontuacao_formulacao: float,
    esperada: float,
) -> None:
    buscador = BuscadorPorTexto(
        respostas={
            PERGUNTA: (_trecho("4", pontuacao_original),),
            "formulação": (_trecho("4", pontuacao_formulacao),),
        }
    )
    reescritor = ReescritorFalso(formulacoes=("formulação",))

    resultados = _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert len(resultados) == 1
    assert resultados[0].secao == _secao("4")
    assert resultados[0].pontuacao == pytest.approx(esperada)


def test_secao_encontrada_por_mais_de_uma_busca_aparece_uma_vez() -> None:
    buscador = BuscadorPorTexto(
        respostas={
            PERGUNTA: (_trecho("4", 0.9), _trecho("2", 0.7)),
            "formulação um": (_trecho("4", 0.8),),
            "formulação dois": (_trecho("2", 0.75), _trecho("4", 0.85)),
        }
    )
    reescritor = ReescritorFalso(formulacoes=("formulação um", "formulação dois"))

    resultados = _adaptador(buscador, reescritor).buscar(PERGUNTA)

    secoes = [trecho.secao for trecho in resultados]
    assert len(secoes) == len(set(secoes)) == 2
    assert resultados[0].secao == _secao("4")
    assert resultados[0].pontuacao == pytest.approx(0.9)
    assert resultados[1].pontuacao == pytest.approx(0.75)


def test_resultado_fundido_e_ordenado_e_cortado_em_top_k() -> None:
    buscador = BuscadorPorTexto(
        respostas={
            PERGUNTA: (_trecho("1", 0.7),),
            "formulação": (_trecho("2", 0.95), _trecho("3", 0.8), _trecho("4", 0.75)),
        }
    )
    reescritor = ReescritorFalso(formulacoes=("formulação",))

    resultados = _adaptador(buscador, reescritor, top_k=2).buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [_secao("2"), _secao("3")]


def test_limiar_vale_sobre_a_pontuacao_fundida() -> None:
    # A seção 5 chega abaixo do limiar nas duas buscas, mas a 4 tem 0.7 numa delas.
    buscador = BuscadorPorTexto(
        respostas={
            PERGUNTA: (_trecho("5", 0.59),),
            "formulação": (_trecho("5", 0.58), _trecho("4", 0.7)),
        }
    )
    reescritor = ReescritorFalso(formulacoes=("formulação",))

    resultados = _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [_secao("4")]


def test_trecho_abaixo_do_limiar_nao_volta_mesmo_que_o_buscador_o_devolva() -> None:
    # O limiar é aplicado também aqui: o adaptador não depende só do buscador injetado.
    buscador = BuscadorPorTexto(respostas={PERGUNTA: (_trecho("1", 0.5),)})

    resultados = _adaptador(buscador, ReescritorFalso(), limiar=LIMIAR).buscar(PERGUNTA)

    assert resultados == ()


def test_reescritor_recebe_a_pergunta_original() -> None:
    reescritor = ReescritorFalso()

    _adaptador(BuscadorPorTexto(), reescritor).buscar(PERGUNTA)

    assert reescritor.chamadas == [PERGUNTA]


def test_formulacoes_iguais_a_original_vazias_ou_repetidas_nao_geram_busca_extra() -> None:
    buscador = BuscadorPorTexto()
    reescritor = ReescritorFalso(
        formulacoes=(
            "  Qual o limite de COMBUSTÍVEL  ",
            "",
            "   ",
            "formulação",
            "FORMULAÇÃO ",
        )
    )

    _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert buscador.buscas == [PERGUNTA, "formulação"]


def test_falha_do_reescritor_cai_na_original_e_registra_aviso_sem_a_pergunta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    buscador = BuscadorPorTexto(respostas={PERGUNTA: (_trecho("4", 0.9),)})
    erro = ErroReescrita(f"falha simulada com {PERGUNTA} e chave {CHAVE_FALSA}")
    reescritor = ReescritorFalso(erro=erro)
    caplog.set_level(logging.WARNING)

    resultados = _adaptador(buscador, reescritor).buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [_secao("4")]
    assert buscador.buscas == [PERGUNTA]
    avisos = [registro for registro in caplog.records if registro.levelno == logging.WARNING]
    assert len(avisos) == 1
    assert avisos[0].name == "busca.buscador_formulacoes"
    assert PERGUNTA not in caplog.text
    assert CHAVE_FALSA not in caplog.text


def test_erro_de_busca_da_original_propaga_sem_alteracao() -> None:
    buscador = BuscadorPorTexto(textos_com_erro=frozenset({PERGUNTA}))

    with pytest.raises(ErroBusca) as erro:
        _adaptador(buscador, ReescritorFalso(formulacoes=("formulação",))).buscar(PERGUNTA)

    assert str(erro.value) == "falha simulada da busca"


def test_erro_de_busca_de_formulacao_propaga_sem_alteracao() -> None:
    buscador = BuscadorPorTexto(textos_com_erro=frozenset({"formulação"}))

    with pytest.raises(ErroBusca) as erro:
        _adaptador(buscador, ReescritorFalso(formulacoes=("formulação",))).buscar(PERGUNTA)

    assert str(erro.value) == "falha simulada da busca"


@pytest.mark.parametrize(
    "reescritor",
    [
        ReescritorFalso(formulacoes=()),
        ReescritorFalso(erro=ErroReescrita("falha simulada")),
    ],
    ids=["reescritor_devolve_vazio", "reescritor_falha"],
)
def test_sem_formulacoes_o_resultado_e_igual_ao_da_busca_simples(
    reescritor: ReescritorConsulta,
) -> None:
    indice = IndiceEmMemoria()
    indice.adicionar(
        [_secao("1"), _secao("2"), _secao("3")],
        [(1.0, 0.0), (0.6, 0.8), (0.0, 1.0)],
    )
    provedor = ProvedorPorTexto({PERGUNTA: (1.0, 0.0)})
    simples = BuscadorSemantico(provedor, indice, limiar_similaridade=0.5, top_k=TOP_K)
    ampliado = _adaptador(simples, reescritor, limiar=0.5)

    assert ampliado.buscar(PERGUNTA) == simples.buscar(PERGUNTA)


def test_formulacao_encontra_secao_que_a_pergunta_original_nao_encontra() -> None:
    # Com o índice e os embeddings reais: a formulação aponta para a seção 3, que a original não
    # alcança. A seção 2 aparece nas duas buscas, com a maior pontuação (0.8) na formulação.
    indice = IndiceEmMemoria()
    indice.adicionar(
        [_secao("1"), _secao("2"), _secao("3")],
        [(1.0, 0.0), (0.6, 0.8), (0.0, 1.0)],
    )
    provedor = ProvedorPorTexto({PERGUNTA: (1.0, 0.0), "formulação": (0.0, 1.0)})
    simples = BuscadorSemantico(provedor, indice, limiar_similaridade=0.5, top_k=TOP_K)
    ampliado = _adaptador(simples, ReescritorFalso(formulacoes=("formulação",)), limiar=0.5)

    resultados = ampliado.buscar(PERGUNTA)

    assert [trecho.secao for trecho in resultados] == [_secao("1"), _secao("3"), _secao("2")]
    assert resultados[2].pontuacao == pytest.approx(0.8)


@pytest.mark.parametrize("limiar", [-0.1, 1.1, math.nan, math.inf])
def test_limiar_fora_de_zero_a_um_e_recusado(limiar: float) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        _adaptador(BuscadorPorTexto(), ReescritorFalso(), limiar=limiar)


@pytest.mark.parametrize("top_k", [0, -1, 2.0, True])
def test_top_k_que_nao_e_inteiro_positivo_e_recusado(top_k: object) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        BuscadorComFormulacoes(
            BuscadorPorTexto(),
            ReescritorFalso(),
            limiar_similaridade=LIMIAR,
            top_k=top_k,  # type: ignore[arg-type]
        )
