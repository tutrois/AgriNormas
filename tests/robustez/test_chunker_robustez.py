"""Casos de borda do chunking por seção pela interface pública `ChunkerPorSecao.dividir`.

Os testes de limitação conhecida fixam o comportamento atual e citam a limitação no nome e na
docstring. Quando a regra mudar, o teste falha e deve ser atualizado de propósito.
"""

from __future__ import annotations

from typing import Final

import pytest

from documentos.chunker_secao import ChunkerPorSecao
from documentos.limpeza import limpar_paginas
from documentos.regras_chunking import TAMANHO_MAXIMO_CHUNK
from nucleo.erros import ConfiguracaoInvalida
from nucleo.modelos import Pagina, Secao

CODIGO: Final[str] = "X-POL-001"
CABECALHO_FAQ: Final[str] = "11. Perguntas frequentes e interpretações"


def _linhas(texto: str, pagina: int = 1) -> list[tuple[int, str]]:
    """Um par `(pagina, linha)` por linha do texto, como `limpar_paginas` faz por parágrafo."""
    return [(pagina, linha) for linha in texto.splitlines()]


def _dividir(texto: str, tamanho_maximo: int = TAMANHO_MAXIMO_CHUNK) -> tuple[Secao, ...]:
    return ChunkerPorSecao(tamanho_maximo=tamanho_maximo).dividir(CODIGO, _linhas(texto))


def test_pergunta_sem_resposta_nao_absorve_a_resposta_da_pergunta_seguinte() -> None:
    texto = f"{CABECALHO_FAQ}\nPergunta um?\nPergunta dois?\nResposta dois."
    secoes = _dividir(texto)
    assert [s.texto for s in secoes] == [
        f"{CABECALHO_FAQ}\nPergunta um?",
        f"{CABECALHO_FAQ}\nPergunta dois?\nResposta dois.",
    ]


def test_limitacao_resposta_que_termina_em_interrogacao_vira_nova_pergunta() -> None:
    """LIMITAÇÃO CONHECIDA (aceita): a regra de FAQ trata todo parágrafo que
    termina em '?' como pergunta. Uma resposta que termina em '?' vira outro par, e o par
    anterior fica sem resposta. Não há ocorrência disso no corpus atual. Este teste fixa o
    comportamento atual; se a regra mudar, ele deve ser atualizado de propósito.
    """
    texto = f"{CABECALHO_FAQ}\nPergunta um?\nResposta que termina em pergunta?"
    secoes = _dividir(texto)
    assert [(s.numero, s.tipo, s.texto) for s in secoes] == [
        ("faq-1", "faq", f"{CABECALHO_FAQ}\nPergunta um?"),
        ("faq-2", "faq", f"{CABECALHO_FAQ}\nResposta que termina em pergunta?"),
    ]


def test_secao_depois_de_paragrafo_que_atravessa_paginas_usa_a_pagina_do_cabecalho() -> None:
    paginas = [
        Pagina(numero=1, texto="palavra " * 13 + "continua"),
        Pagina(numero=2, texto="frase que termina aqui.\n5. Titulo da secao\nCorpo da secao."),
    ]
    secoes = ChunkerPorSecao().dividir(CODIGO, limpar_paginas(paginas))
    secao_5 = [s for s in secoes if s.numero == "5"]
    assert len(secao_5) == 1
    assert secao_5[0].pagina == 2


def test_secao_longa_dividida_mantem_numero_e_titulo_do_pai_em_todos_os_pedacos() -> None:
    texto = "\n".join(["5. Longa", *(["palavra " * 50] * 4)])
    secoes = _dividir(texto, tamanho_maximo=260)
    assert len(secoes) > 1
    assert all(s.numero == "5" for s in secoes)
    assert all(s.titulo == "Longa" for s in secoes)


def test_secao_longa_dividida_usa_a_pagina_de_inicio_em_todos_os_pedacos() -> None:
    pares = [(3, "5. Longa"), *([(4, "palavra " * 50)] * 4)]
    secoes = ChunkerPorSecao(tamanho_maximo=260).dividir(CODIGO, pares)
    assert len(secoes) > 1
    assert all(s.pagina == 3 for s in secoes)


def test_subsecao_que_nao_cabe_no_limite_herda_o_titulo_do_pai_em_cada_pedaco() -> None:
    texto = "\n".join(["1. Pai", "1.1 Filho", *(["palavra " * 50] * 4)])
    secoes = _dividir(texto, tamanho_maximo=260)
    assert len(secoes) > 1
    assert all(s.texto.startswith("1. Pai\n1.1 Filho\n") for s in secoes)


def test_titulo_de_excecao_com_espaco_nao_separavel_apos_o_numero_fica_inteiro() -> None:
    secoes = _dividir("4.\xa0Despesas não elegíveis\nTexto da exceção.")
    assert [(s.numero, s.tipo) for s in secoes] == [("4", "excecao")]


def test_excecao_com_subsecao_fica_inteira_junto_com_a_subsecao() -> None:
    secoes = _dividir("4. Despesas não elegíveis\n4.1 Sub\nSem comprovante fiscal.")
    assert len(secoes) == 1
    assert secoes[0].tipo == "excecao"
    assert "4.1 Sub" in secoes[0].texto
    assert "Sem comprovante fiscal." in secoes[0].texto


def test_titulo_com_mais_de_120_caracteres_nao_vira_secao() -> None:
    linha_longa = "8. " + "B" * 118
    secoes = _dividir(f"1. Objetivo\nCorpo 1.\n{linha_longa}\nCorpo 8.")
    assert [s.numero for s in secoes] == ["1"]
    assert linha_longa in secoes[0].texto


def test_limitacao_numero_sem_espaco_depois_do_ponto_nao_vira_secao() -> None:
    """LIMITAÇÃO CONHECIDA (aceita): '4.Prazo', sem espaço depois do ponto, não é
    cabeçalho de seção. A linha continua no corpo da seção anterior, junto com o texto dela.
    Este teste fixa o comportamento atual; se a regra mudar, ele deve ser atualizado de
    propósito.
    """
    texto = "3. Regras\nCorpo da regra.\n4.Prazo\nTexto do prazo."
    secoes = _dividir(texto)
    assert [s.numero for s in secoes] == ["3"]
    assert secoes[0].texto == "3. Regras\nCorpo da regra.\n4.Prazo\nTexto do prazo."


def test_cabecalho_de_contexto_maior_que_o_limite_nao_estoura_o_tamanho_maximo() -> None:
    texto = "\n".join(["1. Pai", "1.1 " + "Filho " * 15, "corpo " * 30])
    with pytest.raises(ConfiguracaoInvalida, match="50 caracteres"):
        _dividir(texto, tamanho_maximo=50)
