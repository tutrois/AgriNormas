"""Testes dos metadados (código, título, versão e data) da primeira página.

Os PDFs reais são lidos de `base_conhecimento/`. Os casos de borda usam texto sintético,
no mesmo layout da tabela de identificação, e PDFs criados em `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

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


def _pdf_com_texto_sem_tabela(caminho: Path) -> Path:
    """Grava um PDF de uma página com texto simples, sem tabela de identificação.

    O `PdfWriter` não grava texto, então o conteúdo da página é escrito diretamente.
    Só texto ASCII, para não depender de codificação de fonte.
    """
    linhas = ("Texto de teste sem tabela de identificacao",)
    conteudo = "BT /F1 12 Tf 72 780 Td " + " ".join(f"({linha}) Tj 0 -14 Td" for linha in linhas)
    conteudo += " ET"
    objetos = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    partes = [b"%PDF-1.4\n"]
    posicoes: list[int] = []
    posicao = len(partes[0])
    for numero, corpo in enumerate(objetos, start=1):
        bloco = f"{numero} 0 obj\n".encode("ascii") + corpo + b"\nendobj\n"
        posicoes.append(posicao)
        partes.append(bloco)
        posicao += len(bloco)
    posicao_xref = posicao
    xref = f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n"
    xref += "".join(f"{pos:010d} 00000 n \n" for pos in posicoes)
    trailer = (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{posicao_xref}\n%%EOF\n"
    )
    partes.append((xref + trailer).encode("ascii"))
    caminho.write_bytes(b"".join(partes))
    return caminho


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


def test_extracao_sobre_o_mesmo_texto_e_idempotente() -> None:
    primeira = extrair_metadados(TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO)
    segunda = extrair_metadados(TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO)

    assert primeira == segunda


def test_extrai_metadados_do_texto_sintetico_no_layout_real() -> None:
    metadados = extrair_metadados(TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO)

    assert metadados == MetadadosDocumento(
        codigo="FIN-POL-001",
        titulo="POLÍTICA DE REEMBOLSO",
        versao=VERSAO_ESPERADA,
        data_emissao=DATA_ESPERADA,
    )


def test_metadados_sao_imutaveis() -> None:
    metadados = extrair_metadados(TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO)

    with pytest.raises(AttributeError):
        metadados.codigo = "OUTRO"  # type: ignore[misc]


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

    assert "Tabela de identificação ausente" in str(info.value)
    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_pdf_com_texto_sem_tabela_levanta_erro_com_a_causa(tmp_path: Path) -> None:
    caminho = _pdf_com_texto_sem_tabela(tmp_path / "sem_tabela.pdf")

    with pytest.raises(ErroDocumento) as info:
        ler_metadados(caminho)

    assert "Tabela de identificação ausente" in str(info.value)
    assert str(caminho) in str(info.value)


def test_pdf_sem_texto_levanta_erro_do_leitor(tmp_path: Path) -> None:
    caminho = tmp_path / "em_branco.pdf"
    escritor = PdfWriter()
    escritor.add_blank_page(595, 842)
    with caminho.open("wb") as arquivo:
        escritor.write(arquivo)

    with pytest.raises(ErroDocumento) as info:
        ler_metadados(caminho)

    assert "sem texto extraível" in str(info.value)
    assert str(caminho) in str(info.value)


@pytest.mark.parametrize("codigo_invalido", ["FIN-POL-1", "FIN-POL-0001", "FIN-POLITICA-001"])
def test_codigo_fora_do_padrao_levanta_erro_citando_o_campo_codigo(codigo_invalido: str) -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("FIN-POL-001\n", f"{codigo_invalido}\n", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'codigo'" in str(info.value)
    assert str(CAMINHO_FICTICIO) in str(info.value)


def test_sem_titulo_a_linha_acima_do_subtitulo_e_o_numero_da_pagina_e_e_recusada() -> None:
    """Sem a linha do título, a linha acima do subtítulo é "Página 1".

    Ela é recusada porque não está em caixa alta (`isupper` falha), não pelo filtro de
    cabeçalho. Por isso o teste exercita a checagem de caixa alta, não o prefixo AGRICOPPEL.
    """
    texto = TEXTO_PRIMEIRA_PAGINA.replace(" POLÍTICA DE REEMBOLSO\n", "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'titulo'" in str(info.value)


def test_linha_em_caixa_alta_sem_prefixo_agricoppel_e_aceita_como_titulo() -> None:
    """O filtro de cabeçalho só exclui linhas que começam com `AGRICOPPEL`.

    Outra linha em caixa alta acima do subtítulo é aceita como título, mesmo que seja um
    cabeçalho que não começa com esse prefixo. Esse é o comportamento atual e fica explícito
    aqui: se um cabeçalho novo aparecer nesse formato, ele vira título.
    """
    texto = TEXTO_PRIMEIRA_PAGINA.replace(
        " POLÍTICA DE REEMBOLSO\n", " MATERIAL FICTÍCIO PARA AVALIAÇÃO\n", 1
    )

    assert extrair_metadados(texto, CAMINHO_FICTICIO).titulo == "MATERIAL FICTÍCIO PARA AVALIAÇÃO"


def test_cabecalho_em_caixa_alta_colado_ao_subtitulo_nao_vira_titulo() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace("Página 1\n POLÍTICA DE REEMBOLSO\n", "", 1)

    with pytest.raises(ErroDocumento) as info:
        extrair_metadados(texto, CAMINHO_FICTICIO)

    assert "'titulo'" in str(info.value)


def test_subtitulo_em_caixa_alta_usa_a_linha_acima_dele_como_titulo() -> None:
    texto = TEXTO_PRIMEIRA_PAGINA.replace(
        " Despesas de viagem, deslocamentos e prestação de contas",
        " SUBTÍTULO EM CAIXA ALTA",
    )

    assert extrair_metadados(texto, CAMINHO_FICTICIO).titulo == "POLÍTICA DE REEMBOLSO"


@pytest.mark.parametrize("recuo", ["\t  ", "\xa0", " \xa0\t"])
def test_campos_com_recuo_a_esquerda_sao_extraidos_como_no_texto_sem_recuo(recuo: str) -> None:
    texto_recuado = "".join(f"{recuo}{linha}\n" for linha in TEXTO_PRIMEIRA_PAGINA.splitlines())

    assert extrair_metadados(texto_recuado, CAMINHO_FICTICIO) == extrair_metadados(
        TEXTO_PRIMEIRA_PAGINA, CAMINHO_FICTICIO
    )


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
