"""Testes dos metadados da primeira página: PDFs reais e texto sintético no mesmo layout."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from documentos.metadados import MetadadosDocumento, extrair_metadados, ler_metadados
from nucleo.erros import ErroDocumento

PASTA_BASE = Path(__file__).resolve().parents[2] / "base_conhecimento"

VERSAO_ESPERADA = "1.0"
DATA_ESPERADA = "Novembro/2026"

# Texto bruto da primeira página, no mesmo formato que o pypdf devolve para os PDFs reais
# ("\x7f" no lugar de "•"). Serve de base para os casos sintéticos.
TEXTO_PRIMEIRA_PAGINA = (
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
    "Esta política apresenta os critérios para restituição de despesas.\n"
)

CAMINHO_FICTICIO = Path("ficticio.pdf")


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        (
            "Politica_Reembolso.pdf",
            MetadadosDocumento(
                codigo="FIN-POL-001",
                titulo="POLÍTICA DE REEMBOLSO",
                versao=VERSAO_ESPERADA,
                data_emissao=DATA_ESPERADA,
            ),
        ),
        (
            "Politica_Veiculos.pdf",
            MetadadosDocumento(
                codigo="FRO-POL-002",
                titulo="POLÍTICA DE UTILIZAÇÃO DE VEÍCULOS",
                versao=VERSAO_ESPERADA,
                data_emissao=DATA_ESPERADA,
            ),
        ),
        (
            "Procedimento_Ferias.pdf",
            MetadadosDocumento(
                codigo="RH-PRO-003",
                titulo="PROCEDIMENTO DE SOLICITAÇÃO DE FÉRIAS",
                versao=VERSAO_ESPERADA,
                data_emissao=DATA_ESPERADA,
            ),
        ),
    ],
)
def test_pdf_real_devolve_codigo_titulo_versao_e_data(
    nome: str, esperado: MetadadosDocumento
) -> None:
    assert ler_metadados(PASTA_BASE / nome) == esperado


def test_extrai_metadados_do_texto_sintetico_no_layout_real() -> None:
    metadados = extrair_metadados(TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO)

    assert metadados == MetadadosDocumento(
        codigo="FIN-POL-001",
        titulo="POLÍTICA DE REEMBOLSO",
        versao=VERSAO_ESPERADA,
        data_emissao=DATA_ESPERADA,
    )


@pytest.mark.parametrize(
    ("trecho_removido", "campo_esperado"),
    [
        ("FIN-POL-001\n", "codigo"),
        (" POLÍTICA DE REEMBOLSO\n", "titulo"),
        ("Versão 1.0 \x7f Novembro/2026\n", "versao"),
        ("Novembro/2026\n", "data"),
    ],
)
def test_campo_ausente_levanta_erro_citando_caminho_e_campo(
    trecho_removido: str, campo_esperado: str
) -> None:
    texto_incompleto = TEXTO_PRIMEIRA_PAGINA.replace(trecho_removido, "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto_incompleto, CAMINHO_FICTICIO)

    mensagem = str(info.value)
    assert f"'{campo_esperado}'" in mensagem
    assert str(CAMINHO_FICTICIO) in mensagem


def test_erro_de_campo_ausente_nao_inclui_conteudo_do_pdf() -> None:
    texto_sem_codigo = TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001\n", "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto_sem_codigo, CAMINHO_FICTICIO)

    mensagem = str(info.value)
    assert "Despesas de viagem" not in mensagem
    assert "Novembro" not in mensagem
    assert "POLÍTICA DE REEMBOLSO" not in mensagem


def test_texto_sem_tabela_de_identificacao_levanta_erro_com_a_causa() -> None:
    texto_sem_tabela = TEXTO_PRIMEIRA_PAGINA.replace("Identificação\n", "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto_sem_tabela, CAMINHO_FICTICIO)

    assert str(CAMINHO_FICTICIO) in str(info.value)


@pytest.mark.parametrize("codigo_invalido", ["FIN-POL-1", "FIN-POLITICA-001"])
def test_codigo_fora_do_padrao_levanta_erro_citando_o_campo_codigo(codigo_invalido: str) -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001\n", f"{codigo_invalido}\n", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'codigo'" in str(info.value)
    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_sem_titulo_a_linha_acima_do_subtitulo_e_o_numero_da_pagina_e_e_recusada() -> None:
    # Recusada pela checagem de caixa alta (`isupper`), não pelo prefixo AGRICOPPEL.
    texto = TEXTO_PRIMEIRA_PAGINA.replace(" POLÍTICA DE REEMBOLSO\n", "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'titulo'" in str(info.value)


def test_linha_em_caixa_alta_sem_prefixo_agricoppel_e_aceita_como_titulo() -> None:
    # Comportamento atual, explícito: outro cabeçalho em caixa alta sem o prefixo vira título.
    texto = TEXTO_PRIMEIRA_PAGINA.replace(
        " POLÍTICA DE REEMBOLSO\n", " MATERIAL FICTÍCIO PARA AVALIAÇÃO\n", 1
    )

    assert extrair_metadados(texto, CAMINHO_FICTICIO).titulo == "MATERIAL FICTÍCIO PARA AVALIAÇÃO"


def test_subtitulo_em_caixa_alta_usa_a_linha_acima_dele_como_titulo() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace(
        " Despesas de viagem, deslocamentos e prestação de contas",
        " SUBTÍTULO EM CAIXA ALTA",
    )

    assert extrair_metadados(texto, CAMINHO_FICTICIO).titulo == "POLÍTICA DE REEMBOLSO"


@pytest.mark.parametrize("recuo", ["\t  ", "\xa0"])
def test_campos_com_recuo_a_esquerda_sao_extraidos_como_no_texto_sem_recuo(recuo: str) -> None:
    texto_recuado = "".join(f"{recuo}{linha}\n" for linha in TEXTO_PRIMEIRA_PAGINA.splitlines())

    assert extrair_metadados(texto_recuado, CAMINHO_FICTICIO) == extrair_metadados(
        TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO
    )


@pytest.mark.parametrize("data_invalida", ["Novembro", "Novembro/26"])
def test_data_sem_ano_completo_levanta_erro_citando_o_campo_data(data_invalida: str) -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("Novembro/2026", data_invalida)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'data'" in str(info.value)


def test_versao_sem_numero_levanta_erro_citando_o_campo_versao() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("Versão 1.0", "Versão")

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'versao'" in str(info.value)


def test_rotulo_identificacao_depois_da_tabela_nao_altera_o_resultado() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA + "Identificação\nFRO-POL-002\n"

    assert extrair_metadados(texto, CAMINHO_FICTICIO).codigo == "FIN-POL-001"


def test_rotulo_solto_no_corpo_antes_da_tabela_real_e_ignorado() -> None:
    texto = "Identificação\nTexto curto de introdução.\n" + TEXTO_PRIMEIRA_PAGINA

    metadados = extrair_metadados(texto, CAMINHO_FICTICIO)

    assert metadados.codigo == "FIN-POL-001"
    assert metadados.titulo == "POLÍTICA DE REEMBOLSO"


def test_codigo_depois_de_paragrafo_longo_nao_e_lido_como_tabela() -> None:
    texto = (
        TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001\n", "", 1)
        + "Parágrafo de texto corrido, bem mais longo que qualquer linha da tabela.\n"
        + "FRO-POL-002\n"
    )

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'codigo'" in str(info.value)


# Layout sem tabela (PSI-004): a identificação numa linha só, dentro de um parágrafo, e o
# título em duas linhas acima dela, com a faixa "Documento simulado" entre elas.
PDF_PSI_004: Final[str] = "Politica_Seguranca_Informacao.pdf"

TEXTO_PSI_004 = (
    "Documento simulado | Desafio de Engenheiro(a) de IA Júnior\n"
    "Página 1\n"
    "POLÍTICA DE USO DE RECURSOS DE TI E\n"
    "SEGURANÇA DA INFORMAÇÃO\n"
    "Documento simulado para avaliação técnica — Desafio de Engenheiro(a) de IA Júnior\n"
    "Identificação: PSI-004    Versão: 1.0    Vigência fictícia: 01/01/2026\n"
    "Importante: material fictício, criado exclusivamente para o processo seletivo.\n"
    "1. Objetivo e abrangência\n"
    "Estabelecer diretrizes para o uso seguro e responsável dos recursos de tecnologia.\n"
)

PSI_004_ESPERADO = MetadadosDocumento(
    codigo="PSI-004",
    titulo="POLÍTICA DE USO DE RECURSOS DE TI E SEGURANÇA DA INFORMAÇÃO",
    versao=VERSAO_ESPERADA,
    data_emissao="01/01/2026",
)


def test_pdf_psi_004_le_codigo_versao_titulo_em_duas_linhas_e_data_de_vigencia() -> None:
    assert ler_metadados(PASTA_BASE / PDF_PSI_004) == PSI_004_ESPERADO


def test_identificacao_em_linha_unica_e_aceita() -> None:
    assert extrair_metadados(TEXTO_PSI_004, CAMINHO_FICTICIO) == PSI_004_ESPERADO


@pytest.mark.parametrize("codigo", ["PSI-004", "ABC-123", "FIN-POL-001"])
def test_codigo_de_um_ou_dois_segmentos_com_tres_digitos_e_aceito_na_linha_unica(
    codigo: str,
) -> None:
    texto = TEXTO_PSI_004.replace("PSI-004", codigo)

    assert extrair_metadados(texto, CAMINHO_FICTICIO).codigo == codigo


def test_codigo_de_um_segmento_tambem_e_aceito_na_tabela() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001", "ABC-123")

    assert extrair_metadados(texto, CAMINHO_FICTICIO).codigo == "ABC-123"


@pytest.mark.parametrize(
    "codigo_invalido",
    ["PSI-4", "PSI-0004", "PSI-POLITICA-004", "FIN-POL-POL-001", "psi-004"],
)
def test_codigo_fora_dos_dois_formatos_e_rejeitado_na_linha_unica(codigo_invalido: str) -> None:
    texto = TEXTO_PSI_004.replace("PSI-004", codigo_invalido)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'codigo'" in str(info.value)
    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_mensagem_de_codigo_fora_do_padrao_cita_os_dois_formatos() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001\n", "FIN-POL-1\n", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "XXX-000 ou XXX-YYY-000" in str(info.value)


def test_versao_ausente_na_linha_unica_e_rejeitada() -> None:
    texto = TEXTO_PSI_004.replace("Versão: 1.0    ", "")

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'versao'" in str(info.value)
    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_codigo_ausente_na_linha_unica_e_rejeitado() -> None:
    texto = TEXTO_PSI_004.replace("PSI-004", "")

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'codigo'" in str(info.value)


def test_data_ausente_na_linha_unica_e_rejeitada() -> None:
    texto = TEXTO_PSI_004.replace("01/01/2026", "")

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'data'" in str(info.value)


def test_linha_unica_sem_titulo_em_caixa_alta_e_rejeitada() -> None:
    texto = TEXTO_PSI_004.replace("POLÍTICA DE USO DE RECURSOS DE TI E\n", "").replace(
        "SEGURANÇA DA INFORMAÇÃO\n", ""
    )

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'titulo'" in str(info.value)


def test_texto_sem_tabela_nem_linha_de_identificacao_levanta_erro_com_caminho() -> None:
    texto = TEXTO_PSI_004.replace(
        "Identificação: PSI-004    Versão: 1.0    Vigência fictícia: 01/01/2026\n", ""
    )

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_tabela_tem_prioridade_sobre_linha_de_identificacao() -> None:
    texto = (
        TEXTO_PRIMEIRA_PAGINA
        + "Identificação: PSI-004    Versão: 2.0    Vigência fictícia: 01/01/2026\n"
    )

    assert extrair_metadados(texto, CAMINHO_FICTICIO).codigo == "FIN-POL-001"
