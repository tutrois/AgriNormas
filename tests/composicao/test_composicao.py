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
from busca.cache import RepositorioCacheVetores, hash_texto
from busca.indexacao import entradas_indexaveis
from busca.indice_memoria import MENSAGEM_DIMENSAO_DIFERENTE_DO_INDICE
from config import Configuracao, carregar_configuracao
from nucleo.assistente import AssistenteRAG
from nucleo.erros import ErroBusca, ErroDocumento, ErroReescrita
from nucleo.modelos import Fonte, Resposta, Secao, Trecho, Vetor

PERGUNTA = "Qual é o prazo de entrega?"
FORMULACAO = "Em quantos dias os pedidos chegam?"
CONFIGURACAO: Configuracao = carregar_configuracao(ambiente={"OPENAI_API_KEY": "sk-teste-000"})
CONFIGURACAO_SEM_REFORMULACAO: Configuracao = carregar_configuracao(
    ambiente={"OPENAI_API_KEY": "sk-teste-000", "NUMERO_REFORMULACOES": "0"}
)
MODELO = CONFIGURACAO.modelo_embedding
SECOES = (
    Secao(documento="FIN-POL-001", numero="1", titulo="Prazo", texto="Entrega em cinco dias."),
    Secao(documento="FRO-POL-002", numero="2", titulo="Frete", texto="Frete por conta do cliente."),
)
SECOES_COM_FAQ = (
    *SECOES,
    Secao(
        documento="FIN-FAQ-003",
        numero="3",
        titulo="Qual é o prazo de entrega?",
        texto="Pedidos são entregues em até cinco dias úteis.",
        tipo="faq",
    ),
)
TEXTOS_INDEXAVEIS = tuple(
    entrada.texto for entrada in entradas_indexaveis(SECOES, perguntas_faq=True)
)


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
    """Dublê de `GeradorResposta`: cita todas as seções recebidas e guarda as perguntas."""

    def __init__(self) -> None:
        self.chamadas = 0
        self.perguntas: list[str] = []

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        self.chamadas += 1
        self.perguntas.append(pergunta)
        fontes = tuple(Fonte.de_secao(trecho.secao) for trecho in trechos)
        return Resposta(texto="Resposta de teste.", fontes=fontes, evidencia_suficiente=True)


class ReescritorFalso:
    """Dublê de `ReescritorConsulta`: devolve as formulações dadas ou falha, e guarda perguntas."""

    def __init__(self, formulacoes: Sequence[str] = (), erro: Exception | None = None) -> None:
        self._formulacoes = tuple(formulacoes)
        self._erro = erro
        self.perguntas: list[str] = []

    def reescrever(self, pergunta: str) -> tuple[str, ...]:
        self.perguntas.append(pergunta)
        if self._erro is not None:
            raise self._erro
        return self._formulacoes


class FabricaReescritorFalso:
    """Substitui `ReescritorOpenAI`: guarda os argumentos da criação e devolve o dublê."""

    def __init__(self) -> None:
        self.argumentos: list[dict[str, object]] = []
        self.reescritor = ReescritorFalso()

    def __call__(self, **kwargs: object) -> ReescritorFalso:
        self.argumentos.append(kwargs)
        return self.reescritor


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


@pytest.fixture(autouse=True)
def fabrica_reescritor(monkeypatch: pytest.MonkeyPatch) -> FabricaReescritorFalso:
    """Nenhum teste desta suíte chama a API: o reescritor real nunca é criado de verdade."""
    fabrica = FabricaReescritorFalso()
    monkeypatch.setattr(composicao, "ReescritorOpenAI", fabrica)
    return fabrica


def _montar(
    monkeypatch: pytest.MonkeyPatch,
    provedor: ProvedorPorDimensao,
    configuracao: Configuracao = CONFIGURACAO,
) -> AssistenteRAG:
    monkeypatch.setattr(composicao, "_provedor_embedding", lambda _configuracao: provedor)
    return composicao.montar_assistente(configuracao)


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
    assert len(lidos) == len(entradas_indexaveis(SECOES, perguntas_faq=True))
    assert {len(vetor) for vetor in lidos.values()} == {5}


# Perguntas de FAQ (HIST com perguntas_faq ligado na composição)


def test_faq_gera_uma_entrada_extra_com_a_pergunta_no_pedido_inicial(
    monkeypatch: pytest.MonkeyPatch, caminho_cache: Path
) -> None:
    monkeypatch.setattr(composicao, "carregar_secoes", lambda _pasta, _tamanho: SECOES_COM_FAQ)
    entradas = entradas_indexaveis(SECOES_COM_FAQ, perguntas_faq=True)
    provedor = ProvedorPorDimensao([3])

    _montar(monkeypatch, provedor)

    assert provedor.pedidos == [tuple(entrada.texto for entrada in entradas)]
    assert len(entradas) == len(SECOES_COM_FAQ) + 1
    lidos = RepositorioCacheVetores(caminho_cache).ler(MODELO)
    assert set(lidos) == {hash_texto(entrada.texto) for entrada in entradas}


def test_reconstrucao_com_faq_regrava_o_cache_com_o_hash_de_cada_texto_enviado(
    monkeypatch: pytest.MonkeyPatch, caminho_cache: Path
) -> None:
    monkeypatch.setattr(composicao, "carregar_secoes", lambda _pasta, _tamanho: SECOES_COM_FAQ)
    entradas = entradas_indexaveis(SECOES_COM_FAQ, perguntas_faq=True)
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    provedor = ProvedorPorDimensao([5])
    assistente = _montar(monkeypatch, provedor)

    resposta = assistente.responder(PERGUNTA)

    assert resposta.evidencia_suficiente
    assert provedor.pedidos[1] == tuple(entrada.texto for entrada in entradas)
    lidos = RepositorioCacheVetores(caminho_cache).ler(MODELO)
    assert set(lidos) == {hash_texto(entrada.texto) for entrada in entradas}
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


# Reescrita da pergunta (ADR-010): ligação do adaptador na composição


def test_com_zero_formulacoes_nao_cria_o_reescritor_nem_envolve_a_busca(
    monkeypatch: pytest.MonkeyPatch, fabrica_reescritor: FabricaReescritorFalso
) -> None:
    def nao_deveria_ser_criado(**_kwargs: object) -> None:
        pytest.fail("com NUMERO_REFORMULACOES=0 a busca não é envolvida pelo adaptador")

    monkeypatch.setattr(composicao, "BuscadorComFormulacoes", nao_deveria_ser_criado)
    provedor = ProvedorPorDimensao([3])
    assistente = _montar(monkeypatch, provedor, CONFIGURACAO_SEM_REFORMULACAO)

    resposta = assistente.responder(PERGUNTA)

    assert fabrica_reescritor.argumentos == []
    assert provedor.pedidos == [TEXTOS_INDEXAVEIS, (PERGUNTA,)]
    assert resposta.evidencia_suficiente


def test_com_formulacoes_a_montagem_cria_o_reescritor_com_a_configuracao_do_gerador(
    monkeypatch: pytest.MonkeyPatch, fabrica_reescritor: FabricaReescritorFalso
) -> None:
    _montar(monkeypatch, ProvedorPorDimensao([3]))

    assert fabrica_reescritor.argumentos == [
        {
            "chave": CONFIGURACAO.chave_openai,
            "timeout_segundos": CONFIGURACAO.timeout_segundos,
            "numero_formulacoes": 3,
            "modelo": CONFIGURACAO.modelo_geracao,
        }
    ]


def test_com_formulacoes_a_busca_consulta_a_original_e_depois_cada_formulacao(
    monkeypatch: pytest.MonkeyPatch, fabrica_reescritor: FabricaReescritorFalso
) -> None:
    fabrica_reescritor.reescritor = ReescritorFalso((FORMULACAO,))
    provedor = ProvedorPorDimensao([3])
    assistente = _montar(monkeypatch, provedor)

    assistente.responder(PERGUNTA)

    assert provedor.pedidos == [TEXTOS_INDEXAVEIS, (PERGUNTA,), (FORMULACAO,)]


def test_o_gerador_recebe_a_pergunta_original_mesmo_com_formulacoes(
    monkeypatch: pytest.MonkeyPatch,
    gerador: GeradorFalso,
    fabrica_reescritor: FabricaReescritorFalso,
) -> None:
    fabrica_reescritor.reescritor = ReescritorFalso((FORMULACAO,))
    assistente = _montar(monkeypatch, ProvedorPorDimensao([3]))

    assistente.responder(PERGUNTA)

    assert gerador.perguntas == [PERGUNTA]
    assert fabrica_reescritor.reescritor.perguntas == [PERGUNTA]


def test_falha_do_reescritor_nao_quebra_a_resposta_e_segue_com_a_original(
    monkeypatch: pytest.MonkeyPatch,
    gerador: GeradorFalso,
    fabrica_reescritor: FabricaReescritorFalso,
) -> None:
    fabrica_reescritor.reescritor = ReescritorFalso(erro=ErroReescrita("Falha simulada."))
    provedor = ProvedorPorDimensao([3])
    assistente = _montar(monkeypatch, provedor)

    resposta = assistente.responder(PERGUNTA)

    assert provedor.pedidos == [TEXTOS_INDEXAVEIS, (PERGUNTA,)]
    assert gerador.perguntas == [PERGUNTA]
    assert set(resposta.fontes) == {Fonte.de_secao(secao) for secao in SECOES}


def test_reconstrucao_do_cache_mantem_a_busca_com_formulacoes(
    monkeypatch: pytest.MonkeyPatch, fabrica_reescritor: FabricaReescritorFalso
) -> None:
    fabrica_reescritor.reescritor = ReescritorFalso((FORMULACAO,))
    _montar(monkeypatch, ProvedorPorDimensao([3])).responder(PERGUNTA)
    fabrica_reescritor.reescritor = ReescritorFalso((FORMULACAO,))
    provedor = ProvedorPorDimensao([5])
    assistente = _montar(monkeypatch, provedor)

    resposta = assistente.responder(PERGUNTA)

    assert resposta.evidencia_suficiente
    # Dimensão errada falha antes do adaptador: o reescritor roda só depois da reconstrução.
    assert provedor.pedidos == [(PERGUNTA,), TEXTOS_INDEXAVEIS, (PERGUNTA,), (FORMULACAO,)]
    assert fabrica_reescritor.reescritor.perguntas == [PERGUNTA]


# Montagem a partir do ambiente


def test_montar_do_ambiente_usa_a_configuracao_carregada_do_ambiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuracao_do_ambiente = Configuracao(
        chave_openai="sk-ambiente-111",
        modelo_geracao=CONFIGURACAO.modelo_geracao,
        modelo_embedding=CONFIGURACAO.modelo_embedding,
        limiar_similaridade=CONFIGURACAO.limiar_similaridade,
        top_k=CONFIGURACAO.top_k,
        numero_reformulacoes=CONFIGURACAO.numero_reformulacoes,
        pasta_documentos=CONFIGURACAO.pasta_documentos,
        tamanho_maximo_chunk=CONFIGURACAO.tamanho_maximo_chunk,
        timeout_segundos=CONFIGURACAO.timeout_segundos,
    )
    chamadas_de_carregamento: list[tuple[object, ...]] = []
    configuracoes_recebidas: list[Configuracao] = []

    def carregar_falso(*args: object, **kwargs: object) -> Configuracao:
        chamadas_de_carregamento.append((args, kwargs))
        return configuracao_do_ambiente

    def provedor_falso(configuracao: Configuracao) -> ProvedorPorDimensao:
        configuracoes_recebidas.append(configuracao)
        return ProvedorPorDimensao([3])

    monkeypatch.setattr(composicao, "carregar_configuracao", carregar_falso)
    monkeypatch.setattr(composicao, "_provedor_embedding", provedor_falso)

    assistente = composicao.montar_assistente_do_ambiente()

    assert isinstance(assistente, AssistenteRAG)
    assert chamadas_de_carregamento == [((), {})]
    assert configuracoes_recebidas == [configuracao_do_ambiente]
