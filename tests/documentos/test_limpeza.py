"""Testes da limpeza do texto: funções puras com textos sintéticos e com os PDFs reais.

Os testes com PDFs usam `LeitorPdf` de verdade, para validar a limpeza sobre o texto
bruto que o pypdf devolve, e não sobre um texto idealizado.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import (
    LARGURA_LINHA_CHEIA,
    PONTUACAO_FIM_DE_FRASE,
    limpar_paginas,
    limpar_texto,
    normalizar_espacos,
    remover_cabecalho,
    remover_rodape,
    unir_quebras_de_linha,
)
from nucleo.modelos import Pagina

PASTA_BASE: Final[Path] = Path(__file__).resolve().parents[2] / "base_conhecimento"

PDFS_REAIS: Final[tuple[str, ...]] = (
    "Politica_Reembolso.pdf",
    "Politica_Veiculos.pdf",
    "Procedimento_Ferias.pdf",
)

CABECALHO_BRUTO: Final[str] = "AGRICOPPEL \x7f MATERIAL FICTÍCIO PARA AVALIAÇÃO TÉCNICA"
"""Cabeçalho exatamente como o pypdf o devolve."""

TOKENS_POR_CABECALHO: Final[int] = len(CABECALHO_BRUTO.split())
TOKENS_POR_RODAPE: Final[int] = 2
"""`Página` e o número da página."""

FIM_DO_DOCUMENTO_BRUTO: Final[str] = (
    "Fim do documento \x7f Material simulado para avaliação técnica de processamento "
    "documental, recuperação de informações e RAG."
)
"""Rodapé de encerramento, presente uma vez em cada PDF, na última página."""

TOKENS_POR_FIM_DO_DOCUMENTO: Final[int] = len(FIM_DO_DOCUMENTO_BRUTO.split())

PADRAO_TITULO_NA_LINHA: Final[re.Pattern[str]] = re.compile(r"^\d+(?:\.\d+)*\.? [A-ZÀ-Ý].*$", re.M)

FRASE_QUEBRADA_NO_PDF: Final[str] = (
    "a profissionais terceiros que estejam executando atividades em nome da empresa."
)
"""Frase do Reembolso que o layout quebra entre duas linhas ("estejam" / "executando")."""

FRASE_96_TERMINADA_EM_PONTO: Final[str] = (
    "Toda viagem a serviço da empresa depende da aprovação prévia "
    "da chefia imediata, antes da saída."
)
"""Frase sintética de 96 caracteres que termina o parágrafo: não pode ser unida à seguinte."""

FRASE_96_QUEBRADA_NO_MEIO: Final[str] = (
    "O colaborador deve apresentar os comprovantes de todas as despesas "
    "realizadas durante a viagem e"
)
"""Frase sintética de 96 caracteres cortada no meio: a linha seguinte começa em minúscula."""


def _ler_paginas(nome: str) -> tuple[Pagina, ...]:
    return LeitorPdf().ler(PASTA_BASE / nome)


def _texto_limpo(nome: str) -> str:
    return limpar_paginas(_ler_paginas(nome))


def _tokens(texto: str) -> list[str]:
    return texto.split()


# --- funções puras, com textos sintéticos -----------------------------------------------


@pytest.mark.parametrize(
    "linha_cabecalho",
    [
        "AGRICOPPEL • MATERIAL FICTÍCIO PARA AVALIAÇÃO TÉCNICA",
        "AGRICOPPEL \x7f MATERIAL FICTÍCIO PARA AVALIAÇÃO TÉCNICA",
    ],
)
def test_remove_linha_de_cabecalho_com_qualquer_separador(linha_cabecalho: str) -> None:
    texto = f"{linha_cabecalho}\n1. Objetivo"

    assert remover_cabecalho(texto) == "1. Objetivo"


def test_cabecalho_nao_remove_linha_que_apenas_cita_o_material() -> None:
    texto = "Este documento cita o MATERIAL FICTÍCIO no meio da frase."

    assert remover_cabecalho(texto) == texto


def test_remove_rodape_de_pagina_de_qualquer_numero() -> None:
    texto = "Página 1\nCorpo\nPágina 12"

    assert remover_rodape(texto) == "Corpo"


def test_rodape_nao_remove_pagina_citada_no_meio_do_texto() -> None:
    texto = "Consulte a Página 3 do anexo."

    assert remover_rodape(texto) == texto


def test_normalizar_espacos_colapsa_espacos_e_apaga_linhas_vazias() -> None:
    texto = "  a   b\t c  \n\n   d \n"

    assert normalizar_espacos(texto) == "a b c\nd"


def test_une_linha_cheia_com_a_seguinte() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\ncontinua aqui."

    assert unir_quebras_de_linha(texto) == f"{cheia} continua aqui."


def test_linha_curta_termina_o_paragrafo() -> None:
    texto = "Frase curta.\nNovo parágrafo."

    assert unir_quebras_de_linha(texto) == "Frase curta.\nNovo parágrafo."


def test_titulo_numerado_fica_em_linha_propria_mesmo_apos_linha_cheia() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\n3.1 Transporte\nCorpo da seção."

    assert unir_quebras_de_linha(texto) == f"{cheia}\n3.1 Transporte\nCorpo da seção."


def test_titulo_numerado_nao_se_junta_ao_corpo_que_vem_depois() -> None:
    texto = "6.1 Exemplo de contagem do prazo\nSe uma viagem terminar na sexta-feira."

    assert unir_quebras_de_linha(texto).split("\n")[0] == "6.1 Exemplo de contagem do prazo"


def test_pergunta_de_faq_fica_em_linha_propria() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\nPosso enviar depois de 5 dias úteis?\nSim, com justificativa."

    assert unir_quebras_de_linha(texto).split("\n") == [
        f"{cheia}",
        "Posso enviar depois de 5 dias úteis?",
        "Sim, com justificativa.",
    ]


def test_linha_que_comeca_com_numero_nao_se_une_ao_paragrafo() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\n5 (cinco) dias úteis após o encerramento."

    assert unir_quebras_de_linha(texto) == texto


@pytest.mark.parametrize("fim_de_frase", PONTUACAO_FIM_DE_FRASE)
def test_linha_cheia_terminada_em_pontuacao_de_fim_de_frase_nao_se_une(fim_de_frase: str) -> None:
    anterior = "x" * (LARGURA_LINHA_CHEIA - 1) + fim_de_frase
    texto = f"{anterior}\ncontinua aqui."

    assert unir_quebras_de_linha(texto) == texto


def test_linha_cheia_sem_pontuacao_une_com_proxima_que_comeca_em_minuscula() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\nfinal do parágrafo."

    assert unir_quebras_de_linha(texto) == f"{cheia} final do parágrafo."


def test_linha_cheia_nao_se_une_com_proxima_que_comeca_em_maiuscula() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\nNova frase começa aqui."

    assert unir_quebras_de_linha(texto) == texto


def test_frases_de_96_caracteres_e_fim_de_frase_real_ficam_em_linhas_separadas() -> None:
    assert len(FRASE_96_TERMINADA_EM_PONTO) == 96
    texto = f"{FRASE_96_TERMINADA_EM_PONTO}\nA chefia responde em até dois dias úteis."

    assert unir_quebras_de_linha(texto).split("\n") == [
        FRASE_96_TERMINADA_EM_PONTO,
        "A chefia responde em até dois dias úteis.",
    ]


def test_quebra_de_meio_de_frase_com_96_caracteres_se_une_com_minuscula() -> None:
    assert len(FRASE_96_QUEBRADA_NO_MEIO) == 96
    texto = f"{FRASE_96_QUEBRADA_NO_MEIO}\na conferência do gestor."

    assert unir_quebras_de_linha(texto) == f"{FRASE_96_QUEBRADA_NO_MEIO} a conferência do gestor."


def test_texto_vazio_devolve_vazio_em_todas_as_etapas() -> None:
    assert limpar_texto("") == ""
    assert unir_quebras_de_linha("") == ""
    assert limpar_paginas(()) == ""


def test_pagina_so_com_cabecalho_e_rodape_devolve_vazio() -> None:
    paginas = (Pagina(numero=1, texto=f"{CABECALHO_BRUTO}\nPágina 1\n"),)

    assert limpar_paginas(paginas) == ""


def test_limpeza_e_deterministica_em_texto_sintetico() -> None:
    texto = f"{CABECALHO_BRUTO}\nPágina 1\n1. Objetivo\nCorpo do texto."

    assert limpar_texto(texto) == limpar_texto(texto)


def test_paragrafo_continua_na_pagina_seguinte() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    paginas = (
        Pagina(numero=1, texto=f"{CABECALHO_BRUTO}\nPágina 1\n{cheia}"),
        Pagina(numero=2, texto=f"{CABECALHO_BRUTO}\nPágina 2\nfinal da frase."),
    )

    assert limpar_paginas(paginas) == f"{cheia} final da frase."


# --- PDFs reais -------------------------------------------------------------------------


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_texto_limpo_nao_tem_material_ficticio(nome: str) -> None:
    assert "MATERIAL FICTÍCIO" not in _texto_limpo(nome)


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_texto_limpo_nao_tem_numeracao_de_pagina(nome: str) -> None:
    assert re.search(r"Página\s+\d+", _texto_limpo(nome)) is None


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_texto_limpo_nao_tem_linha_vazia_nem_espaco_duplicado(nome: str) -> None:
    texto = _texto_limpo(nome)

    assert all(linha and linha == linha.strip() for linha in texto.split("\n"))
    assert "  " not in texto


def test_titulo_3_1_transporte_comeca_uma_linha_no_reembolso() -> None:
    texto = _texto_limpo("Politica_Reembolso.pdf")

    assert re.search(r"^3\.1 Transporte$", texto, re.M) is not None


def test_titulo_6_1_fica_sozinho_em_sua_linha_no_reembolso() -> None:
    linhas = _texto_limpo("Politica_Reembolso.pdf").split("\n")

    assert "6.1 Exemplo de contagem do prazo" in linhas


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_todos_os_titulos_numerados_sobrevivem_intactos(nome: str) -> None:
    paginas = _ler_paginas(nome)
    bruto = "\n".join(pagina.texto for pagina in paginas)
    titulos_brutos = [
        linha.strip() for linha in bruto.splitlines() if PADRAO_TITULO_NA_LINHA.match(linha.strip())
    ]
    linhas_limpas = set(limpar_paginas(paginas).split("\n"))

    assert titulos_brutos
    assert all(titulo in linhas_limpas for titulo in titulos_brutos)


def test_frase_quebrada_pelo_layout_fica_contigua_no_reembolso() -> None:
    assert FRASE_QUEBRADA_NO_PDF in _texto_limpo("Politica_Reembolso.pdf")


def test_fim_de_paragrafo_longo_nao_se_une_a_proxima_frase_no_reembolso() -> None:
    linhas = _texto_limpo("Politica_Reembolso.pdf").split("\n")
    indice = next(i for i, linha in enumerate(linhas) if linha.endswith("desafio de seleção."))

    assert linhas[indice + 1].startswith("Não representa política oficial")


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_contagem_de_palavras_difere_so_pelo_cabecalho_rodape_e_encerramento(nome: str) -> None:
    paginas = _ler_paginas(nome)
    bruto = " ".join(pagina.texto for pagina in paginas)
    limpo = _texto_limpo(nome)

    removidas = len(_tokens(bruto)) - len(_tokens(limpo))

    esperadas = (
        len(paginas) * (TOKENS_POR_CABECALHO + TOKENS_POR_RODAPE) + TOKENS_POR_FIM_DO_DOCUMENTO
    )
    assert removidas == esperadas


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_palavras_do_corpo_sao_preservadas_na_mesma_ordem(nome: str) -> None:
    paginas = _ler_paginas(nome)
    assert all(pagina.texto.startswith(CABECALHO_BRUTO) for pagina in paginas)

    corpo_esperado: list[str] = []
    for pagina in paginas:
        sem_encerramento = pagina.texto.replace(FIM_DO_DOCUMENTO_BRUTO, "")
        corpo_esperado.extend(_tokens(sem_encerramento)[TOKENS_POR_CABECALHO + TOKENS_POR_RODAPE :])

    assert _tokens(_texto_limpo(nome)) == corpo_esperado


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_limpeza_dos_pdfs_e_deterministica(nome: str) -> None:
    assert _texto_limpo(nome) == _texto_limpo(nome)


def test_pergunta_frequente_do_reembolso_fica_em_linha_propria() -> None:
    linhas = _texto_limpo("Politica_Reembolso.pdf").split("\n")

    assert "Posso enviar a prestação de contas depois de 5 dias úteis?" in linhas
