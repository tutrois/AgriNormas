"""Testes do `AssistenteRAG` com dublês de `Buscador` e `GeradorResposta`."""

from collections.abc import Sequence

import pytest

from nucleo.assistente import TAMANHO_MAXIMO_PERGUNTA, AssistenteRAG
from nucleo.erros import ErroBusca, ErroGeracao, PerguntaInvalida
from nucleo.modelos import MENSAGEM_SEM_EVIDENCIA, Fonte, Resposta, Secao, Trecho


def _trecho(numero: str = "6.1", documento: str = "FIN-POL-001") -> Trecho:
    secao = Secao(
        documento=documento,
        numero=numero,
        titulo=f"Seção {numero}",
        texto="Conteúdo de exemplo da seção.",
    )
    return Trecho(secao=secao, pontuacao=0.8)


class BuscadorFalso:
    """Dublê de `Buscador`: registra as perguntas recebidas e devolve trechos fixos."""

    def __init__(self, trechos: tuple[Trecho, ...] = (), erro: Exception | None = None) -> None:
        self._trechos = trechos
        self._erro = erro
        self.perguntas: list[str] = []

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        self.perguntas.append(pergunta)
        if self._erro is not None:
            raise self._erro
        return self._trechos


class GeradorFalso:
    """Dublê de `GeradorResposta`: registra as chamadas e devolve uma resposta fixa."""

    def __init__(self, resposta: Resposta | None = None, erro: Exception | None = None) -> None:
        self._resposta = resposta or Resposta(texto="Resposta do modelo.")
        self._erro = erro
        self.chamadas: list[tuple[str, tuple[Trecho, ...]]] = []

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        self.chamadas.append((pergunta, tuple(trechos)))
        if self._erro is not None:
            raise self._erro
        return self._resposta


def _assistente(
    buscador: BuscadorFalso, gerador: GeradorFalso | None = None
) -> tuple[AssistenteRAG, GeradorFalso]:
    gerador_falso = gerador or GeradorFalso()
    return AssistenteRAG(buscador, gerador_falso), gerador_falso


@pytest.mark.parametrize("pergunta", ["", "   ", "\n\t  \n"])
def test_pergunta_vazia_ou_so_com_espacos_recusa_sem_chamar_nada(pergunta: str) -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    assistente, gerador = _assistente(buscador)

    with pytest.raises(PerguntaInvalida):
        assistente.responder(pergunta)

    assert buscador.perguntas == []
    assert gerador.chamadas == []


def test_pergunta_com_501_caracteres_recusa_sem_chamar_nada() -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    assistente, gerador = _assistente(buscador)

    with pytest.raises(PerguntaInvalida):
        assistente.responder("a" * (TAMANHO_MAXIMO_PERGUNTA + 1))

    assert buscador.perguntas == []
    assert gerador.chamadas == []


def test_pergunta_com_500_caracteres_e_aceita() -> None:
    pergunta = "a" * TAMANHO_MAXIMO_PERGUNTA
    trecho = _trecho()
    buscador = BuscadorFalso(trechos=(trecho,))
    gerador = GeradorFalso(
        resposta=Resposta(texto="Resposta.", fontes=(Fonte.de_secao(trecho.secao),))
    )
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder(pergunta)

    assert buscador.perguntas == [pergunta]
    assert len(gerador.chamadas) == 1
    assert resposta.evidencia_suficiente is True


def test_espacos_nas_bordas_sao_aparados_antes_da_busca_e_da_geracao() -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    assistente, gerador = _assistente(buscador)

    assistente.responder("   qual o prazo?  \n")

    assert buscador.perguntas == ["qual o prazo?"]
    assert gerador.chamadas[0][0] == "qual o prazo?"


def test_espacos_nas_bordas_nao_contam_no_limite_de_caracteres() -> None:
    pergunta = "  " + "a" * TAMANHO_MAXIMO_PERGUNTA + "  "
    buscador = BuscadorFalso(trechos=(_trecho(),))
    assistente, _ = _assistente(buscador)

    assistente.responder(pergunta)

    assert buscador.perguntas == ["a" * TAMANHO_MAXIMO_PERGUNTA]


def test_busca_sem_trechos_devolve_sem_evidencia_e_nao_chama_gerador() -> None:
    buscador = BuscadorFalso(trechos=())
    assistente, gerador = _assistente(buscador)

    resposta = assistente.responder("pergunta sem correspondência")

    assert resposta == Resposta.sem_evidencia()
    assert gerador.chamadas == []


def test_fluxo_completo_entrega_texto_do_gerador_com_fontes_citadas() -> None:
    trechos = (_trecho("6.1", "FIN-POL-001"), _trecho("3.2", "FRO-POL-002"))
    buscador = BuscadorFalso(trechos=trechos)
    fontes_citadas = (Fonte.de_secao(trechos[0].secao), Fonte.de_secao(trechos[1].secao))
    gerador = GeradorFalso(resposta=Resposta(texto="Texto fundamentado.", fontes=fontes_citadas))
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("qual o prazo?")

    assert resposta.texto == "Texto fundamentado."
    assert resposta.evidencia_suficiente is True
    assert resposta.fontes == (
        Fonte(documento="FIN-POL-001", secao="6.1", titulo="Seção 6.1"),
        Fonte(documento="FRO-POL-002", secao="3.2", titulo="Seção 3.2"),
    )
    assert gerador.chamadas == [("qual o prazo?", trechos)]


def test_gerador_com_evidencia_e_sem_fontes_devolve_sem_evidencia() -> None:
    buscador = BuscadorFalso(trechos=(_trecho("6.1"),))
    gerador = GeradorFalso(resposta=Resposta(texto="Texto sem fontes.", fontes=()))
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta == Resposta.sem_evidencia()


def test_fonte_que_nao_esta_nos_trechos_e_filtrada() -> None:
    trechos = (_trecho("6.1", "FIN-POL-001"),)
    inventadas = (
        Fonte(documento="FIN-POL-001", secao="6.2", titulo="Seção 6.2"),
        Fonte(documento="FRO-POL-999", secao="6.1", titulo="Seção 6.1"),
        Fonte(documento="FIN-POL-001", secao="6.1", titulo="Título diferente"),
    )
    for inventada in inventadas:
        buscador = BuscadorFalso(trechos=trechos)
        gerador = GeradorFalso(resposta=Resposta(texto="Texto.", fontes=(inventada,)))
        assistente, _ = _assistente(buscador, gerador)

        resposta = assistente.responder("pergunta")

        assert inventada not in resposta.fontes
        assert resposta == Resposta.sem_evidencia()


def test_fontes_mistas_mantem_so_a_valida() -> None:
    trechos = (_trecho("6.1", "FIN-POL-001"),)
    valida = Fonte.de_secao(trechos[0].secao)
    inventada = Fonte(documento="FRO-POL-999", secao="1.1", titulo="Seção 1.1")
    buscador = BuscadorFalso(trechos=trechos)
    gerador = GeradorFalso(resposta=Resposta(texto="Texto.", fontes=(inventada, valida)))
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta.fontes == (valida,)
    assert resposta.evidencia_suficiente is True


def test_gerador_com_evidencia_e_so_fonte_inventada_devolve_sem_evidencia() -> None:
    buscador = BuscadorFalso(trechos=(_trecho("6.1", "FIN-POL-001"),))
    inventada = Fonte(documento="FRO-POL-999", secao="1.1", titulo="Seção 1.1")
    gerador = GeradorFalso(resposta=Resposta(texto="Texto.", fontes=(inventada,)))
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta.fontes == ()
    assert resposta.evidencia_suficiente is False


def test_fontes_repetidas_do_gerador_sao_deduplicadas_na_ordem_do_gerador() -> None:
    trechos = (_trecho("6.1", "FIN-POL-001"), _trecho("3.2", "FRO-POL-002"))
    fonte_61 = Fonte.de_secao(trechos[0].secao)
    fonte_32 = Fonte.de_secao(trechos[1].secao)
    buscador = BuscadorFalso(trechos=trechos)
    gerador = GeradorFalso(
        resposta=Resposta(texto="Texto.", fontes=(fonte_32, fonte_61, fonte_32, fonte_61))
    )
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta.fontes == (fonte_32, fonte_61)


def test_gerador_sem_evidencia_devolve_mensagem_padrao_sem_fontes() -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    gerador = GeradorFalso(resposta=Resposta.sem_evidencia())
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta == Resposta.sem_evidencia()
    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta.fontes == ()
    assert resposta.evidencia_suficiente is False


def test_erro_de_busca_propaga_sem_conversao_e_nao_chama_gerador() -> None:
    erro = ErroBusca("falha simulada na busca")
    buscador = BuscadorFalso(erro=erro)
    assistente, gerador = _assistente(buscador)

    with pytest.raises(ErroBusca) as info:
        assistente.responder("pergunta")

    assert info.value is erro
    assert gerador.chamadas == []


def test_erro_de_geracao_propaga_sem_conversao() -> None:
    erro = ErroGeracao("falha simulada na geração")
    buscador = BuscadorFalso(trechos=(_trecho(),))
    gerador = GeradorFalso(erro=erro)
    assistente, _ = _assistente(buscador, gerador)

    with pytest.raises(ErroGeracao) as info:
        assistente.responder("pergunta")

    assert info.value is erro


def test_fontes_do_gerador_sao_usadas_quando_ele_cita_so_um_dos_trechos() -> None:
    trecho_citado = _trecho("3.2", "FRO-POL-002")
    trechos = (_trecho("6.1", "FIN-POL-001"), trecho_citado)
    fonte_citada = Fonte.de_secao(trecho_citado.secao)
    buscador = BuscadorFalso(trechos=trechos)
    gerador = GeradorFalso(resposta=Resposta(texto="Texto.", fontes=(fonte_citada,)))
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta.fontes == (fonte_citada,)


@pytest.mark.parametrize("texto", ["", "   ", "Não há evidência nos trechos."])
def test_recusa_do_gerador_devolve_sem_evidencia_com_ou_sem_texto(texto: str) -> None:
    trechos = (_trecho("6.1"),)
    buscador = BuscadorFalso(trechos=trechos)
    recusa = Resposta(
        texto=texto,
        fontes=(Fonte.de_secao(trechos[0].secao),),
        evidencia_suficiente=False,
    )
    gerador = GeradorFalso(resposta=recusa)
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta == Resposta.sem_evidencia()
    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta.fontes == ()
    assert resposta.evidencia_suficiente is False


@pytest.mark.parametrize("texto", ["", "   ", "\n\t"])
def test_evidencia_suficiente_com_texto_vazio_devolve_sem_evidencia(texto: str) -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    gerador = GeradorFalso(
        resposta=Resposta(
            texto=texto,
            fontes=(Fonte.de_secao(_trecho().secao),),
            evidencia_suficiente=True,
        )
    )
    assistente, _ = _assistente(buscador, gerador)

    resposta = assistente.responder("pergunta")

    assert resposta == Resposta.sem_evidencia()


@pytest.mark.parametrize("valor", [None, 123, b"pergunta", ["pergunta"]])
def test_pergunta_que_nao_e_texto_lanca_pergunta_invalida_sem_busca(valor: object) -> None:
    buscador = BuscadorFalso(trechos=(_trecho(),))
    assistente, gerador = _assistente(buscador)

    with pytest.raises(PerguntaInvalida):
        assistente.responder(valor)  # type: ignore[arg-type]

    assert buscador.perguntas == []
    assert gerador.chamadas == []
