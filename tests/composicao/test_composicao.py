"""Testes da composição (HIST-018) com dublês: sem API real e sem gravar em `dados/`.

O cache de vetores é apontado para `tmp_path`, os PDFs são substituídos por seções fixas e o
provedor de embeddings e o gerador são dublês. O índice, o buscador e o `AssistenteRAG` são
os de verdade, então o teste percorre o caminho que a aplicação usa.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

import composicao
from busca.cache import RepositorioCacheVetores
from busca.indexacao import texto_indexavel
from busca.indice_memoria import MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE
from config import Configuracao, carregar_configuracao
from nucleo.assistente import AssistenteRAG
from nucleo.erros import ErroBusca, ErroDocumento
from nucleo.modelos import Fonte, Resposta, Secao, Trecho, Vetor

PERGUNTA = "Qual é o prazo de entrega?"
CONFIGURACAO: Configuracao = carregar_configuracao(ambiente={"OPENAI_API_KEY": "sk-teste-000"})
MODELO = CONFIGURACAO.modelo_embedding
SECOES = (
    Secao(documento="FIN-POL-001", numero="1", titulo="Prazo", texto="Entrega em cinco dias."),
    Secao(documento="FRO-POL-002", numero="2", titulo="Frete", texto="Frete por conta do cliente."),
)
TEXTOS_INDEXAVEIS = tuple(texto_indexavel(secao) for secao in SECOES)


class ProvedorPorDimensao:
    """Dublê de `ProvedorEmbedding`: a dimensão de cada pedido segue a lista recebida.

    Quando a lista acaba, a última dimensão vale para os pedidos seguintes. Guarda cada pedido.
    """

    def __init__(self, dimensoes: Sequence[int]) -> None:
        self._dimensoes = list(dimensoes)
        self.pedidos: list[tuple[str, ...]] = []

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.pedidos.append(tuple(textos))
        dimensao = self._dimensoes.pop(0) if len(self._dimensoes) > 1 else self._dimensoes[0]
        return tuple(tuple(float(indice + 1) for indice in range(dimensao)) for _ in textos)


class ProvedorComFalhaNaConsulta(ProvedorPorDimensao):
    """Dublê que falha com um erro que não é de dimensão quando recebe só a pergunta."""

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        if len(textos) == 1:
            self.pedidos.append(tuple(textos))
            raise ErroBusca("Falha de rede ao consultar o provedor.")
        return super().gerar(textos)


class GeradorFalso:
    """Dublê de `GeradorResposta`: cita todas as seções recebidas e conta as chamadas."""

    def __init__(self) -> None:
        self.chamadas = 0

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        self.chamadas += 1
        fontes = tuple(Fonte.de_secao(trecho.secao) for trecho in trechos)
        return Resposta(texto="Resposta de teste.", fontes=fontes, evidencia_suficiente=True)


@pytest.fixture(autouse=True)
def caminho_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / "dados" / "indice.npz"
    monkeypatch.setattr(composicao, "CAMINHO_CACHE_VETORES", caminho)
    monkeypatch.setattr(composicao, "carregar_secoes", lambda _pasta, _tamanho: SECOES)
    return caminho


@pytest.fixture(autouse=True)
def gerador(monkeypatch: pytest.MonkeyPatch) -> GeradorFalso:
    instancia = GeradorFalso()
    monkeypatch.setattr(composicao, "GeradorOpenAI", lambda **_kwargs: instancia)
    return instancia


def _montar(monkeypatch: pytest.MonkeyPatch, provedor: ProvedorPorDimensao) -> AssistenteRAG:
    monkeypatch.setattr(composicao, "_provedor_embedding", lambda _configuracao: provedor)
    return composicao.montar_assistente(CONFIGURACAO)


# Caminho feliz


def test_cache_valido_nao_chama_o_provedor_de_novo_na_montagem(
    monkeypatch: pytest.MonkeyPatch, gerador: GeradorFalso
) -> None:
    primeiro = ProvedorPorDimensao([3])
    _montar(monkeypatch, primeiro)
    segundo = ProvedorPorDimensao([3])

    assistente = _montar(monkeypatch, segundo)

    assert primeiro.pedidos == [TEXTOS_INDEXAVEIS]
    assert segundo.pedidos == []
    resposta = assistente.responder(PERGUNTA)
    assert segundo.pedidos == [(PERGUNTA,)]
    assert gerador.chamadas == 1
    assert set(resposta.fontes) == {Fonte.de_secao(secao) for secao in SECOES}


# Cache de outra dimensão na consulta (M-29, cenário 2)


def test_cache_de_outra_dimensao_na_consulta_reconstroi_o_indice_e_responde(
    monkeypatch: pytest.MonkeyPatch, caminho_cache: Path
) -> None:
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    provedor = ProvedorPorDimensao([5])
    assistente = _montar(monkeypatch, provedor)
    assert provedor.pedidos == []

    resposta = assistente.responder(PERGUNTA)

    assert resposta.evidencia_suficiente
    assert resposta.fontes
    assert provedor.pedidos == [(PERGUNTA,), TEXTOS_INDEXAVEIS, (PERGUNTA,)]
    lidos = RepositorioCacheVetores(caminho_cache).ler(MODELO)
    assert len(lidos) == len(SECOES)
    assert {len(vetor) for vetor in lidos.values()} == {5}


def test_depois_da_reconstrucao_a_montagem_seguinte_usa_o_cache_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    _montar(monkeypatch, ProvedorPorDimensao([5])).responder(PERGUNTA)
    provedor = ProvedorPorDimensao([5])

    assistente = _montar(monkeypatch, provedor)
    assistente.responder(PERGUNTA)

    assert provedor.pedidos == [(PERGUNTA,)]


def test_segunda_falha_de_dimensao_levanta_erro_sem_novo_laco(
    monkeypatch: pytest.MonkeyPatch, caminho_cache: Path, gerador: GeradorFalso
) -> None:
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    chamadas_do_gerador_antes = gerador.chamadas
    # Consulta com dimensão 5, reconstrução com 5 e nova consulta com 7: a repetição falha.
    provedor = ProvedorPorDimensao([5, 5, 7])
    assistente = _montar(monkeypatch, provedor)

    with pytest.raises(ErroBusca) as excinfo:
        assistente.responder(PERGUNTA)

    assert str(excinfo.value) == MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE
    assert len(provedor.pedidos) == 3
    assert gerador.chamadas == chamadas_do_gerador_antes
    lidos = RepositorioCacheVetores(caminho_cache).ler(MODELO)
    assert {len(vetor) for vetor in lidos.values()} == {5}


def test_erro_que_nao_e_de_dimensao_propaga_sem_reconstruir(
    monkeypatch: pytest.MonkeyPatch, caminho_cache: Path
) -> None:
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    provedor = ProvedorComFalhaNaConsulta([3])
    assistente = _montar(monkeypatch, provedor)

    with pytest.raises(ErroBusca, match="Falha de rede"):
        assistente.responder(PERGUNTA)

    assert provedor.pedidos == [(PERGUNTA,)]
    lidos = RepositorioCacheVetores(caminho_cache).ler(MODELO)
    assert {len(vetor) for vetor in lidos.values()} == {3}


# Entrada inválida


def test_base_sem_secoes_levanta_erro_documento_sem_chamar_o_provedor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composicao, "carregar_secoes", lambda _pasta, _tamanho: ())
    provedor = ProvedorPorDimensao([3])

    with pytest.raises(ErroDocumento):
        _montar(monkeypatch, provedor)

    assert provedor.pedidos == []
