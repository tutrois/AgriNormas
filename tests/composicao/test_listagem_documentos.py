"""Testes da listagem dos documentos da base (menu lateral da interface)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

import composicao
from composicao import DocumentoDaBase, listar_documentos_da_base, listar_documentos_do_ambiente
from config import RAIZ_PROJETO

BASE = RAIZ_PROJETO / "base_conhecimento"


@pytest.fixture
def pasta_com_pdfs(tmp_path: Path) -> Path:
    for pdf in BASE.glob("*.pdf"):
        shutil.copy(pdf, tmp_path / pdf.name)
    return tmp_path


def test_lista_os_tres_documentos_em_ordem_de_nome(pasta_com_pdfs: Path) -> None:
    documentos = listar_documentos_da_base(pasta_com_pdfs)

    assert [d.arquivo for d in documentos] == [
        "Politica_Reembolso.pdf",
        "Politica_Veiculos.pdf",
        "Procedimento_Ferias.pdf",
    ]
    assert [d.codigo for d in documentos] == ["FIN-POL-001", "FRO-POL-002", "RH-PRO-003"]
    assert documentos[0].titulo == "POLÍTICA DE REEMBOLSO"
    assert all(d.versao for d in documentos)


def test_pdf_corrompido_nao_derruba_a_lista(
    pasta_com_pdfs: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (pasta_com_pdfs / "Aaa_Quebrado.pdf").write_bytes(b"SEGREDO-NO-ARQUIVO nao e pdf")

    with caplog.at_level(logging.WARNING):
        documentos = listar_documentos_da_base(pasta_com_pdfs)

    assert len(documentos) == 4
    assert documentos[0] == DocumentoDaBase("Aaa_Quebrado.pdf", "", "Aaa_Quebrado", "")
    assert documentos[1].codigo == "FIN-POL-001"
    assert caplog.records
    assert "SEGREDO-NO-ARQUIVO" not in caplog.text


def test_pasta_inexistente_ou_vazia_devolve_tupla_vazia(tmp_path: Path) -> None:
    assert listar_documentos_da_base(tmp_path / "nao_existe") == ()
    assert listar_documentos_da_base(tmp_path) == ()


def test_do_ambiente_usa_pasta_configurada_sem_exigir_chave(
    monkeypatch: pytest.MonkeyPatch, pasta_com_pdfs: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PASTA_DOCUMENTOS", str(pasta_com_pdfs))
    monkeypatch.setattr(
        composicao, "_ambiente_do_processo", lambda _caminho: __import__("os").environ
    )

    documentos = listar_documentos_do_ambiente()

    assert [d.codigo for d in documentos] == ["FIN-POL-001", "FRO-POL-002", "RH-PRO-003"]
