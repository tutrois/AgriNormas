"""Testes do chunking por seção (HIST-007): PDFs reais e textos sintéticos para as bordas.

Os testes com PDFs usam `LeitorPdf`, `limpar_paginas` e `ler_metadados` de verdade, e o
código do documento vem da própria primeira página, como no fluxo de produção.

Os textos sintéticos passam por `_um_paragrafo_por_linha`, que monta os pares
`(pagina, texto)` no formato de `limpar_paginas`: um par por parágrafo. Um par nunca tem
quebra de linha interna, então um texto com várias linhas vira vários pares.
"""

from __future__ import annotations

from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Final

import pytest

from documentos.chunker_secao import ChunkerPorSecao
from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import limpar_paginas
from documentos.metadados import ler_metadados
from documentos.regras_chunking import TAMANHO_MAXIMO_CHUNK
from nucleo.contratos import Chunker
from nucleo.erros import ConfiguracaoInvalida
from nucleo.modelos import Secao

PASTA_BASE: Final[Path] = Path(__file__).resolve().parents[2] / "base_conhecimento"

POLITICA_REEMBOLSO: Final[str] = "Politica_Reembolso.pdf"
POLITICA_VEICULOS: Final[str] = "Politica_Veiculos.pdf"
PROCEDIMENTO_FERIAS: Final[str] = "Procedimento_Ferias.pdf"

CHUNKER_PADRAO: Final[Chunker] = ChunkerPorSecao()
"""Confirma em tempo de checagem que `ChunkerPorSecao` cumpre o contrato `Chunker`."""

CODIGO_SINTETICO: Final[str] = "X-POL-001"

# Sequências reais (número, tipo) conferidas no texto limpo dos PDFs. Começam na seção 1: o
# texto antes dela (capa, identificação e resumo) não gera chunk. Seção sem corpo
# (ex.: "3. Despesas elegíveis") não gera chunk próprio; só as subseções geram.
SEQUENCIA_REEMBOLSO: Final[tuple[tuple[str, str], ...]] = (
    ("1", "normal"),
    ("2", "normal"),
    ("3.1", "normal"),
    ("3.2", "normal"),
    ("3.3", "normal"),
    ("3.4", "normal"),
    ("4", "excecao"),
    ("5", "normal"),
    ("6", "normal"),
    ("6.1", "normal"),
    ("7", "normal"),
    ("8", "normal"),
    ("9", "normal"),
    ("10", "normal"),
    ("faq-1", "faq"),
    ("faq-2", "faq"),
    ("faq-3", "faq"),
    ("faq-4", "faq"),
)

SEQUENCIA_VEICULOS: Final[tuple[tuple[str, str], ...]] = (
    ("1", "normal"),
    ("2", "normal"),
    ("3", "normal"),
    ("3.1", "normal"),
    ("4", "normal"),
    ("5", "normal"),
    ("5.1", "normal"),
    ("6", "excecao"),
    ("7", "normal"),
    ("7.1", "normal"),
    ("8", "normal"),
    ("9", "normal"),
    ("10", "normal"),
    ("11", "normal"),
    ("faq-1", "faq"),
    ("faq-2", "faq"),
    ("faq-3", "faq"),
    ("faq-4", "faq"),
    ("faq-5", "faq"),
)

SEQUENCIA_FERIAS: Final[tuple[tuple[str, str], ...]] = (
    ("1", "normal"),
    ("2", "normal"),
    ("2.1", "normal"),
    ("3", "normal"),
    ("4", "normal"),
    ("4.1", "normal"),
    ("5", "normal"),
    ("6", "normal"),
    ("7", "normal"),
    ("8", "normal"),
    ("9", "normal"),
    ("10", "normal"),
    ("11", "normal"),
    ("faq-1", "faq"),
    ("faq-2", "faq"),
    ("faq-3", "faq"),
    ("faq-4", "faq"),
    ("faq-5", "faq"),
)

SEQUENCIAS_POR_PDF: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    POLITICA_REEMBOLSO: SEQUENCIA_REEMBOLSO,
    POLITICA_VEICULOS: SEQUENCIA_VEICULOS,
    PROCEDIMENTO_FERIAS: SEQUENCIA_FERIAS,
}


@cache
def _pares(nome: str) -> tuple[tuple[int, str], ...]:
    """Parágrafos limpos do PDF, com a página de cada um."""
    return limpar_paginas(LeitorPdf().ler(PASTA_BASE / nome))


@cache
def _codigo(nome: str) -> str:
    return ler_metadados(PASTA_BASE / nome).codigo


@cache
def _secoes(nome: str) -> tuple[Secao, ...]:
    return ChunkerPorSecao().dividir(_codigo(nome), _pares(nome))


def _separar_preambulo(nome: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Divide os parágrafos limpos do PDF em (preâmbulo, a partir da seção 1).

    O preâmbulo é a capa, a tabela de identificação e o resumo, antes do primeiro "1. ".
    Por decisão de HIST-007 esse texto não vira chunk. Os campos de identificação (código,
    versão, data e título) são lidos por `ler_metadados`, não pelo chunker.
    """
    textos = tuple(texto for _, texto in _pares(nome))
    inicio = next(i for i, texto in enumerate(textos) if texto.startswith("1. "))
    return textos[:inicio], textos[inicio:]


def _um_paragrafo_por_linha(texto: str, pagina: int = 1) -> list[tuple[int, str]]:
    """Monta pares `(pagina, texto)` com uma linha do texto por par, na mesma página."""
    return [(pagina, linha) for linha in texto.splitlines()]


def _secao_por_numero(secoes: tuple[Secao, ...], numero: str) -> Secao:
    encontradas = [secao for secao in secoes if secao.numero == numero]
    assert len(encontradas) == 1, f"seção {numero} deveria aparecer uma vez"
    return encontradas[0]


def _cobre_em_ordem(paragrafos: tuple[str, ...], chunks: tuple[Secao, ...]) -> bool:
    """Diz se cada parágrafo aparece, em ordem, como sequência de palavras nos chunks."""
    fluxo = [palavra for chunk in chunks for palavra in chunk.texto.split()]
    cursor = 0
    for paragrafo in paragrafos:
        palavras = paragrafo.split()
        posicao = _posicao_da_sequencia(fluxo, palavras, cursor)
        if posicao is None:
            return False
        cursor = posicao + len(palavras)
    return True


def _posicao_da_sequencia(fluxo: list[str], palavras: list[str], inicio: int) -> int | None:
    tamanho = len(palavras)
    for posicao in range(inicio, len(fluxo) - tamanho + 1):
        if fluxo[posicao : posicao + tamanho] == palavras:
            return posicao
    return None


# --- PDFs reais -------------------------------------------------------------------------


@pytest.mark.parametrize(("nome", "sequencia"), SEQUENCIAS_POR_PDF.items())
def test_sequencia_de_secoes_bate_com_o_texto_real(
    nome: str, sequencia: tuple[tuple[str, str], ...]
) -> None:
    obtida = tuple((secao.numero, secao.tipo) for secao in _secoes(nome))
    assert obtida == sequencia


def test_6_1_exemplo_de_contagem_do_prazo_e_um_chunk_com_a_regra_de_dias_uteis() -> None:
    secao = _secao_por_numero(_secoes(POLITICA_REEMBOLSO), "6.1")
    assert secao.titulo == "Exemplo de contagem do prazo"
    assert "dias úteis" in secao.texto
    assert "Sábado, domingo e feriados não são considerados dias úteis" in secao.texto


def test_secao_4_de_fin_pol_001_fica_inteira_com_comprovante_e_autorizacao_no_mesmo_chunk() -> None:
    secao = _secao_por_numero(_secoes(POLITICA_REEMBOLSO), "4")
    assert secao.titulo == "Despesas não elegíveis"
    assert secao.tipo == "excecao"
    assert "sem comprovante fiscal" in secao.texto
    assert "autorização formal da diretoria" in secao.texto


def test_secao_6_de_fro_pol_002_multas_e_infracoes_fica_inteira() -> None:
    secao = _secao_por_numero(_secoes(POLITICA_VEICULOS), "6")
    assert secao.titulo == "Multas e infrações"
    assert secao.tipo == "excecao"
    assert "Não é permitido solicitar reembolso de multas" in secao.texto


def test_subsecao_6_1_herda_o_titulo_da_secao_pai_no_proprio_texto() -> None:
    secao = _secao_por_numero(_secoes(POLITICA_REEMBOLSO), "6.1")
    assert secao.texto.splitlines()[:2] == [
        "6. Prazo e fluxo de solicitação",
        "6.1 Exemplo de contagem do prazo",
    ]


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_todo_chunk_tem_codigo_numero_e_titulo(nome: str) -> None:
    for secao in _secoes(nome):
        assert secao.documento == _codigo(nome)
        assert secao.numero
        assert secao.titulo


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_nenhum_chunk_esta_vazio(nome: str) -> None:
    assert all(secao.texto.strip() for secao in _secoes(nome))


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_texto_dos_chunks_cobre_o_texto_limpo_a_partir_da_secao_1_em_ordem(nome: str) -> None:
    """A cobertura começa na seção 1: o preâmbulo fica fora dos chunks por decisão."""
    _, a_partir_da_secao_1 = _separar_preambulo(nome)
    assert _cobre_em_ordem(a_partir_da_secao_1, _secoes(nome))


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_preambulo_real_existe_e_nao_aparece_em_nenhum_chunk(nome: str) -> None:
    """Confirma que o preâmbulo (capa, identificação, resumo) é de fato excluído dos chunks."""
    preambulo, _ = _separar_preambulo(nome)
    assert preambulo, "o PDF deveria ter texto antes da seção 1"
    textos_dos_chunks = [secao.texto for secao in _secoes(nome)]
    for paragrafo in preambulo:
        assert not any(paragrafo in texto for texto in textos_dos_chunks), paragrafo


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_chunks_normais_respeitam_o_tamanho_maximo_padrao(nome: str) -> None:
    for secao in _secoes(nome):
        if secao.tipo == "normal":
            assert len(secao.texto) <= TAMANHO_MAXIMO_CHUNK


@pytest.mark.parametrize("nome", SEQUENCIAS_POR_PDF)
def test_todo_chunk_real_tem_pagina_vinda_dos_pares(nome: str) -> None:
    paginas_do_documento = {pagina for pagina, _ in _pares(nome)}
    assert all(secao.pagina in paginas_do_documento for secao in _secoes(nome))


def test_pagina_de_inicio_vem_dos_pares_de_limpar_paginas() -> None:
    reembolso = _secoes(POLITICA_REEMBOLSO)
    assert _secao_por_numero(reembolso, "1").pagina == 1
    assert _secao_por_numero(reembolso, "4").pagina == 2
    assert _secao_por_numero(reembolso, "6.1").pagina == 2
    assert _secao_por_numero(reembolso, "faq-1").pagina == 3
    assert _secao_por_numero(_secoes(PROCEDIMENTO_FERIAS), "4.1").pagina == 2


def test_pagina_nao_depende_do_texto_quando_todas_as_paginas_sao_iguais() -> None:
    nome = POLITICA_REEMBOLSO
    pagina_unica = [(1, texto) for _, texto in _pares(nome)]
    sem_paginas_reais = ChunkerPorSecao().dividir(_codigo(nome), pagina_unica)
    assert tuple(replace(secao, pagina=1) for secao in _secoes(nome)) == tuple(
        replace(secao, pagina=1) for secao in sem_paginas_reais
    )


def test_chunking_e_determinista_para_o_mesmo_pdf() -> None:
    nome = PROCEDIMENTO_FERIAS
    primeira = ChunkerPorSecao().dividir(_codigo(nome), _pares(nome))
    segunda = ChunkerPorSecao().dividir(_codigo(nome), _pares(nome))
    assert primeira == segunda


# --- Textos sintéticos: bordas ----------------------------------------------------------


def test_texto_vazio_devolve_tupla_vazia() -> None:
    assert ChunkerPorSecao().dividir(CODIGO_SINTETICO, ()) == ()


def test_texto_so_com_espacos_devolve_tupla_vazia() -> None:
    assert ChunkerPorSecao().dividir(CODIGO_SINTETICO, [(1, "   "), (2, "\n\t"), (2, "  ")]) == ()


def test_pagina_com_texto_vazio_devolve_tupla_vazia() -> None:
    assert ChunkerPorSecao().dividir(CODIGO_SINTETICO, [(1, "")]) == ()


def test_pares_vazios_sao_ignorados_e_a_pagina_vem_do_primeiro_par_com_texto() -> None:
    pares = [(1, ""), (2, "1. Objetivo"), (3, "  "), (3, "Corpo da seção.")]
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, pares)
    assert [(s.numero, s.pagina) for s in secoes] == [("1", 2)]


def test_secao_que_comeca_em_uma_pagina_e_continua_na_seguinte_usa_a_pagina_inicial() -> None:
    pares = [(4, "2. Prazos"), (5, "Corpo que continua na página seguinte.")]
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, pares)
    assert [(s.numero, s.pagina) for s in secoes] == [("2", 4)]


def test_secao_sem_corpo_nao_gera_chunk_mas_a_seguinte_gera() -> None:
    texto = "1. Vazia\n2. Com corpo\nTexto do corpo."
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert [s.numero for s in secoes] == ["2"]


def test_secao_sem_corpo_com_subsecao_gera_so_a_subsecao_com_contexto_do_pai() -> None:
    texto = "1. Pai\n1.1 Filho\nCorpo do filho."
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert [s.numero for s in secoes] == ["1.1"]
    assert secoes[0].texto == "1. Pai\n1.1 Filho\nCorpo do filho."


def test_subsecao_sem_secao_pai_vira_chunk_sem_linha_de_contexto() -> None:
    texto = "2.1 Solta\nCorpo solto."
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert len(secoes) == 1
    assert secoes[0].numero == "2.1"
    assert secoes[0].titulo == "Solta"
    assert secoes[0].texto == "2.1 Solta\nCorpo solto."


def test_texto_antes_da_primeira_secao_nao_gera_chunk() -> None:
    texto = "Capa do documento.\n1. Objetivo\nCorpo da seção."
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert [(s.numero, s.texto) for s in secoes] == [("1", "1. Objetivo\nCorpo da seção.")]


def test_texto_antes_da_primeira_secao_nao_gera_chunk_mesmo_em_pagina_propria() -> None:
    pares = [(2, "Capa do documento."), (2, "Resumo."), (3, "1. Objetivo"), (3, "Corpo.")]
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, pares)
    assert [(s.numero, s.pagina) for s in secoes] == [("1", 3)]


def test_documento_sem_nenhuma_secao_devolve_tupla_vazia() -> None:
    pares = [(1, "Capa do documento."), (1, "Resumo sem seção numerada.")]
    assert ChunkerPorSecao().dividir(CODIGO_SINTETICO, pares) == ()


def test_excecao_nao_e_dividida_mesmo_acima_do_tamanho() -> None:
    paragrafos = ["Parágrafo longo " * 8] * 30
    texto = "\n".join(["4. Despesas não elegíveis", *paragrafos])
    secoes = ChunkerPorSecao(tamanho_maximo=300).dividir(
        CODIGO_SINTETICO, _um_paragrafo_por_linha(texto)
    )
    assert len(secoes) == 1
    assert secoes[0].tipo == "excecao"
    assert len(secoes[0].texto) > 300


def test_titulo_de_excecao_ignora_caixa_e_espacos() -> None:
    texto = "4.   DESPESAS  NÃO ELEGÍVEIS\nTexto da exceção."
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert secoes[0].tipo == "excecao"


def test_secao_longa_e_dividida_por_paragrafo_sem_cortar_paragrafo() -> None:
    paragrafos = [f"Parágrafo {i} " + " ".join(["palavra"] * 60) for i in range(5)]
    texto = "\n".join(["5. Longa", *paragrafos])
    secoes = ChunkerPorSecao(tamanho_maximo=600).dividir(
        CODIGO_SINTETICO, _um_paragrafo_por_linha(texto)
    )
    assert len(secoes) > 1
    assert all(s.numero == "5" and s.tipo == "normal" for s in secoes)
    assert all(len(s.texto) <= 600 for s in secoes)
    for paragrafo in paragrafos:
        assert sum(paragrafo in s.texto for s in secoes) == 1


def test_paragrafo_maior_que_o_limite_e_quebrado_em_palavras() -> None:
    longo = " ".join(f"termo{i}" for i in range(400))
    texto = "\n".join(["5. Longa", longo])
    secoes = ChunkerPorSecao(tamanho_maximo=200).dividir(
        CODIGO_SINTETICO, _um_paragrafo_por_linha(texto)
    )
    assert all(len(s.texto) <= 200 for s in secoes)
    assert " ".join(palavra for s in secoes for palavra in s.texto.split()[2:]) == longo


def test_chunks_divididos_repetem_o_titulo_da_secao_pai() -> None:
    paragrafos = ["palavra " * 50 for _ in range(4)]
    texto = "\n".join(["1. Pai", "1.1 Filho", *paragrafos])
    secoes = ChunkerPorSecao(tamanho_maximo=260).dividir(
        CODIGO_SINTETICO, _um_paragrafo_por_linha(texto)
    )
    assert len(secoes) > 1
    assert all(s.texto.startswith("1. Pai\n1.1 Filho\n") for s in secoes)


def test_tamanho_maximo_nao_positivo_e_configuracao_invalida() -> None:
    with pytest.raises(ConfiguracaoInvalida):
        ChunkerPorSecao(tamanho_maximo=0)


def test_faq_gera_um_chunk_por_par_sem_separar_pergunta_e_resposta() -> None:
    texto = "\n".join(
        [
            "11. Perguntas frequentes e interpretações",
            "Pergunta um?",
            "Resposta da primeira linha.",
            "Resposta da segunda linha.",
            "Pergunta dois?",
            "Resposta dois.",
        ]
    )
    secoes = ChunkerPorSecao().dividir(CODIGO_SINTETICO, _um_paragrafo_por_linha(texto))
    assert [(s.numero, s.tipo) for s in secoes] == [("faq-1", "faq"), ("faq-2", "faq")]
    assert secoes[0].titulo == "Pergunta um?"
    assert secoes[0].texto == (
        "11. Perguntas frequentes e interpretações\n"
        "Pergunta um?\nResposta da primeira linha.\nResposta da segunda linha."
    )
    assert secoes[1].texto == (
        "11. Perguntas frequentes e interpretações\nPergunta dois?\nResposta dois."
    )


def test_faq_com_pergunta_longa_nao_e_dividida_por_tamanho() -> None:
    resposta = "resposta " * 300
    texto = "\n".join(["11. Perguntas frequentes e interpretações", "Pergunta?", resposta])
    secoes = ChunkerPorSecao(tamanho_maximo=200).dividir(
        CODIGO_SINTETICO, _um_paragrafo_por_linha(texto)
    )
    assert len(secoes) == 1
    assert "Pergunta?" in secoes[0].texto
    assert resposta.strip() in secoes[0].texto


def test_mesma_entrada_gera_mesma_lista_de_secoes() -> None:
    texto = "1. A\nCorpo A.\n1.1 B\nCorpo B.\n4. Despesas não elegíveis\nExceção."
    pares = _um_paragrafo_por_linha(texto)
    assert ChunkerPorSecao().dividir(CODIGO_SINTETICO, pares) == ChunkerPorSecao().dividir(
        CODIGO_SINTETICO, pares
    )
