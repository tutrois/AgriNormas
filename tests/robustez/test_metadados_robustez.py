"""Casos de borda e erros dos metadados (HIST-006), de ponta a ponta com o leitor de PDF.

Usa o texto da primeira página no layout real da tabela de identificação, com uma
variação por teste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from documentos.metadados import extrair_metadados, ler_metadados
from nucleo.erros import ErroDocumento

CAMINHO_FICTICIO = Path("ficticio.pdf")

TEXTO_BASE = (
    "AGRICOPPEL \x7f MATERIAL FICTÍCIO PARA AVALIAÇÃO TÉCNICA\n"
    "Página 1\n"
    " POLÍTICA DE REEMBOLSO\n"
    " Despesas de viagem, deslocamentos e prestação de contas\n"
    "Identificação\n"
    "FIN-POL-001\n"
    "Aplicação\n"
    "Documento simulado\n"
    "Versão 1.0 \x7f Novembro/2026\n"
    "Exercício técnico\n"
    "Corpo do documento.\n"
)


def _extrair(texto: str):
    return extrair_metadados(texto, CAMINHO_FICTICIO)


def test_titulo_com_acento_e_espaco_a_esquerda_e_extraido_sem_espaco() -> None:
    assert _extrair(TEXTO_BASE).titulo == "POLÍTICA DE REEMBOLSO"


def test_titulo_com_cedilha_e_til_e_extraido_integro() -> None:
    texto = TEXTO_BASE.replace("POLÍTICA DE REEMBOLSO", "AÇÕES DE CONTROLE")

    assert _extrair(texto).titulo == "AÇÕES DE CONTROLE"


def test_data_sem_ano_levanta_erro_citando_o_campo_data() -> None:
    texto = TEXTO_BASE.replace("Novembro/2026", "Novembro")

    with pytest.raises(ErroDocumento) as info:
        _extrair(texto)

    assert "'data'" in str(info.value)


def test_data_com_ano_de_dois_digitos_levanta_erro_citando_o_campo_data() -> None:
    texto = TEXTO_BASE.replace("Novembro/2026", "Novembro/26")

    with pytest.raises(ErroDocumento) as info:
        _extrair(texto)

    assert "'data'" in str(info.value)


def test_versao_sem_numero_levanta_erro_citando_o_campo_versao() -> None:
    texto = TEXTO_BASE.replace("Versão 1.0", "Versão")

    with pytest.raises(ErroDocumento) as info:
        _extrair(texto)

    assert "'versao'" in str(info.value)


def test_rotulo_identificacao_inline_em_frase_do_corpo_nao_e_confundido_com_tabela() -> None:
    texto = "Texto introdutório.\nIdentificação de fornecedores é tratada adiante.\n" + TEXTO_BASE

    metadados = _extrair(texto)

    assert metadados.codigo == "FIN-POL-001"
    assert metadados.titulo == "POLÍTICA DE REEMBOLSO"


def test_rotulo_identificacao_depois_da_tabela_nao_altera_o_resultado() -> None:
    texto = TEXTO_BASE + "Identificação\nFRO-POL-002\n"

    assert _extrair(texto).codigo == "FIN-POL-001"


def test_subtitulo_em_caixa_alta_nao_substitui_o_titulo() -> None:
    texto = TEXTO_BASE.replace(
        " Despesas de viagem, deslocamentos e prestação de contas",
        "SUBTÍTULO EM CAIXA ALTA",
    )

    assert _extrair(texto).titulo == "POLÍTICA DE REEMBOLSO"


def test_rotulo_identificacao_solto_no_corpo_antes_do_titulo_nao_derruba_a_extracao() -> None:
    texto = "Identificação\n" + TEXTO_BASE

    assert _extrair(texto).codigo == "FIN-POL-001"


def test_pdf_inexistente_levanta_erro_tratado(tmp_path: Path) -> None:
    with pytest.raises(ErroDocumento) as info:
        ler_metadados(tmp_path / "nao_existe.pdf")

    assert "inexistente" in str(info.value)


def test_pdf_corrompido_levanta_erro_tratado(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"%PDF-1.4\nisto nao e um pdf valido \x00\xff")

    with pytest.raises(ErroDocumento):
        ler_metadados(caminho)
