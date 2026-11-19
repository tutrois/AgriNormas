"""Testes da leitura do conteúdo de um documento da base (tela "Base de conhecimento")."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

import composicao
from composicao import (
    ConteudoDoDocumento,
    ler_documento_da_base,
    ler_documento_do_ambiente,
)
from config import PADRAO_TAMANHO_MAXIMO_CHUNK, RAIZ_PROJETO

BASE = RAIZ_PROJETO / "base_conhecimento"


@pytest.fixture
def pasta_com_pdfs(tmp_path: Path) -> Path:
    for pdf in BASE.glob("*.pdf"):
        shutil.copy(pdf, tmp_path / pdf.name)
    return tmp_path


def _reembolso(pasta: Path) -> ConteudoDoDocumento:
    conteudo = ler_documento_da_base(pasta, "Politica_Reembolso.pdf")
    assert conteudo is not None
    return conteudo


def test_devolve_identificacao_e_secoes_do_reembolso(pasta_com_pdfs: Path) -> None:
    conteudo = _reembolso(pasta_com_pdfs)

    assert conteudo.arquivo == "Politica_Reembolso.pdf"
    assert conteudo.codigo == "FIN-POL-001"
    assert conteudo.titulo == "POLÍTICA DE REEMBOLSO"
    assert conteudo.versao
    secao_5 = next(s for s in conteudo.secoes if s.numero == "5")
    assert secao_5.titulo == "Comprovantes e informações obrigatórias"
    assert "comprovante fiscal legível" in secao_5.texto
    assert secao_5.tipo == "normal"


def test_secoes_faq_tem_tipo_faq_e_a_pergunta_como_titulo(pasta_com_pdfs: Path) -> None:
    faqs = [s for s in _reembolso(pasta_com_pdfs).secoes if s.tipo == "faq"]

    assert [s.numero for s in faqs] == ["faq-1", "faq-2", "faq-3", "faq-4"]
    assert faqs[0].titulo.endswith("?")
    assert faqs[0].texto.startswith("O prazo regular")


def test_corpo_nao_repete_o_titulo_nem_o_cabecalho_do_pai(pasta_com_pdfs: Path) -> None:
    secoes = {s.numero: s for s in _reembolso(pasta_com_pdfs).secoes}

    assert secoes["5"].texto.startswith("Cada lançamento")
    assert secoes["3.1"].texto.startswith("Podem ser solicitados")
    assert secoes["6.1"].texto.startswith("Se uma viagem")
    assert all(not s.texto.startswith(s.titulo) for s in secoes.values())


def test_mesmas_secoes_da_busca_na_ordem_do_documento(pasta_com_pdfs: Path) -> None:
    conteudo = _reembolso(pasta_com_pdfs)
    da_busca = [
        s
        for s in composicao.carregar_secoes(pasta_com_pdfs, PADRAO_TAMANHO_MAXIMO_CHUNK)
        if s.documento == "FIN-POL-001"
    ]

    assert [(s.numero, s.titulo, s.tipo) for s in conteudo.secoes] == [
        (s.numero, s.titulo, s.tipo) for s in da_busca
    ]
    assert all(s.texto.endswith(c.texto) for s, c in zip(da_busca, conteudo.secoes, strict=True))
    numeros = [s.numero for s in conteudo.secoes]
    assert numeros[:3] == ["1", "2", "3.1"]


def test_respeita_o_tamanho_maximo_da_busca(pasta_com_pdfs: Path) -> None:
    conteudo = ler_documento_da_base(pasta_com_pdfs, "Politica_Reembolso.pdf", tamanho_maximo=300)
    da_busca = [
        s for s in composicao.carregar_secoes(pasta_com_pdfs, 300) if s.documento == "FIN-POL-001"
    ]

    assert conteudo is not None
    assert [s.numero for s in conteudo.secoes] == [s.numero for s in da_busca]


@pytest.mark.parametrize(
    "nome",
    [
        "../.env",
        "..\\x.pdf",
        "/etc/passwd",
        "C:\\x.pdf",
        "Politica_Reembolso.pdf/",
        "./Politica_Reembolso.pdf",
        "subpasta/Politica_Reembolso.pdf",
        "politica_reembolso.pdf",
        "Inexistente.pdf",
        "Politica_Reembolso",
        "",
        None,
        42,
    ],
)
def test_nomes_invalidos_devolvem_none(pasta_com_pdfs: Path, nome: object) -> None:
    assert ler_documento_da_base(pasta_com_pdfs, nome) is None  # type: ignore[arg-type]


def test_nome_de_pdf_fora_da_pasta_devolve_none(pasta_com_pdfs: Path, tmp_path: Path) -> None:
    pasta = tmp_path / "interna"
    pasta.mkdir()

    assert ler_documento_da_base(pasta, str(pasta_com_pdfs / "Politica_Reembolso.pdf")) is None


def test_pasta_inexistente_devolve_none(tmp_path: Path) -> None:
    assert ler_documento_da_base(tmp_path / "nao_existe", "Politica_Reembolso.pdf") is None


def test_pdf_corrompido_devolve_none_sem_vazar_conteudo(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "Quebrado.pdf").write_bytes(b"SEGREDO-NO-ARQUIVO nao e pdf")

    with caplog.at_level(logging.WARNING, logger="composicao"):
        resultado = ler_documento_da_base(tmp_path, "Quebrado.pdf")

    mensagens = [r.getMessage() for r in caplog.records if r.name == "composicao"]
    assert resultado is None
    assert mensagens
    assert all(
        "SEGREDO" not in m and "Quebrado" not in m and str(tmp_path) not in m for m in mensagens
    )
    assert all(r.exc_info is None for r in caplog.records if r.name == "composicao")


def test_leitura_bem_sucedida_nao_loga_conteudo(
    pasta_com_pdfs: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        _reembolso(pasta_com_pdfs)

    assert "comprovante fiscal" not in caplog.text


def test_ambiente_le_da_pasta_configurada_sem_chave(
    pasta_com_pdfs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PASTA_DOCUMENTOS", str(pasta_com_pdfs))

    conteudo = ler_documento_do_ambiente("Procedimento_Ferias.pdf")

    assert conteudo is not None
    assert conteudo.codigo == "RH-PRO-003"
    assert ler_documento_do_ambiente("../.env") is None
