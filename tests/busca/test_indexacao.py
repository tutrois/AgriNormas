"""Testes da montagem do índice, com provedor falso que conta as chamadas."""

from __future__ import annotations

from collections.abc import Sequence

from busca.indexacao import (
    construir_indice,
    entradas_indexaveis,
    pergunta_de_faq,
    texto_indexavel,
)
from nucleo.modelos import Secao, TipoSecao, Vetor


class ProvedorContador:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, ...]] = []

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.chamadas.append(tuple(textos))
        # Vetores ortogonais entre si: a primeira seção é a única com pontuação 1 para (1, 0).
        return tuple(
            tuple(1.0 if posicao == indice else 0.0 for posicao in range(len(textos)))
            for indice in range(len(textos))
        )


def _secao(numero: str, texto: str = "corpo da seção") -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Título {numero}", texto=texto)


def _faq(
    numero: str, pergunta: str = "Posso fazer X?", resposta: str = "Sim, com aprovação."
) -> Secao:
    return Secao(
        documento="FIN-POL-001",
        numero=f"faq-{numero}",
        titulo=pergunta,
        texto=f"11. Perguntas frequentes e interpretações\n{pergunta}\n{resposta}",
        tipo="faq",
        pagina=3,
    )


def _secao_com_tipo(numero: str, tipo: TipoSecao, titulo: str) -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=titulo, texto="corpo", tipo=tipo)


def test_texto_indexavel_traz_codigo_numero_e_titulo_antes_do_corpo() -> None:
    texto = texto_indexavel(_secao("6.1", "Prazo de cinco dias"))

    assert texto == "FIN-POL-001 §6.1 Título 6.1\nPrazo de cinco dias"


def test_construir_indice_envia_um_pedido_com_um_texto_por_secao() -> None:
    provedor = ProvedorContador()
    secoes = [_secao("1"), _secao("2")]

    indice = construir_indice(secoes, provedor)

    assert provedor.chamadas == [tuple(texto_indexavel(secao) for secao in secoes)]
    assert indice.buscar((1.0, 0.0), 2)[0].secao == secoes[0]


def test_sem_secoes_nao_chama_o_provedor_e_devolve_indice_vazio() -> None:
    provedor = ProvedorContador()

    indice = construir_indice([], provedor)

    assert provedor.chamadas == []
    assert indice.buscar((1.0, 0.0), 1) == ()


def test_sem_a_opcao_cada_secao_tem_uma_entrada_mesmo_quando_e_faq() -> None:
    secoes = [_secao("1"), _faq("1")]

    entradas = entradas_indexaveis(secoes)

    assert [entrada.texto for entrada in entradas] == [texto_indexavel(s) for s in secoes]


def test_com_a_opcao_faq_ganha_entrada_so_com_a_pergunta_na_mesma_secao() -> None:
    faq = _faq("3", pergunta="Existe um limite fixo?")

    entradas = entradas_indexaveis([faq], perguntas_faq=True)

    assert [entrada.texto for entrada in entradas] == [
        texto_indexavel(faq),
        "Existe um limite fixo?",
    ]
    assert all(entrada.secao is faq for entrada in entradas)


def test_com_a_opcao_secao_que_nao_e_faq_nao_ganha_entrada_extra() -> None:
    secao = _secao("6.1")

    entradas = entradas_indexaveis([secao], perguntas_faq=True)

    assert [entrada.texto for entrada in entradas] == [texto_indexavel(secao)]


def test_com_a_opcao_faq_com_pergunta_vazia_nao_gera_entrada_extra() -> None:
    faq = _faq("1", pergunta="   ")

    entradas = entradas_indexaveis([faq], perguntas_faq=True)

    assert len(entradas) == 1
    assert pergunta_de_faq(faq) is None


def test_pergunta_de_faq_devolve_o_titulo_sem_espacos_nas_pontas() -> None:
    assert pergunta_de_faq(_faq("2", pergunta="  Posso anexar o extrato?  ")) == (
        "Posso anexar o extrato?"
    )


def test_pergunta_de_faq_ignora_secoes_que_nao_sao_faq() -> None:
    assert pergunta_de_faq(_secao_com_tipo("3", "normal", "Pergunta?")) is None
    assert pergunta_de_faq(_secao_com_tipo("4", "excecao", "Pergunta?")) is None


def test_entradas_sem_secoes_devolvem_tupla_vazia() -> None:
    assert entradas_indexaveis([], perguntas_faq=True) == ()


def test_com_a_opcao_faq_o_pedido_ao_provedor_inclui_a_pergunta_logo_apos_a_secao() -> None:
    provedor = ProvedorContador()
    normal = _secao("1")
    faq = _faq("1", pergunta="Posso fazer X?")

    indice = construir_indice([normal, faq], provedor, perguntas_faq=True)

    assert provedor.chamadas == [
        (texto_indexavel(normal), texto_indexavel(faq), "Posso fazer X?"),
    ]
    # Vetor (0, 0, 1) é a pergunta do FAQ: o trecho certo sai na frente.
    melhor = indice.buscar((0.0, 0.0, 1.0), 1)[0]
    assert melhor.secao is faq
    assert melhor.pontuacao == 1.0


def test_sem_a_opcao_faq_o_pedido_ao_provedor_nao_muda() -> None:
    provedor = ProvedorContador()
    secoes = [_secao("1"), _faq("1")]

    construir_indice(secoes, provedor)

    assert provedor.chamadas == [tuple(texto_indexavel(secao) for secao in secoes)]
