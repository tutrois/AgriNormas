"""Testes do `LeitorPdf`. Só `LimitReachedError` é provocada por mock; o resto usa PDFs reais."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import LimitReachedError

from documentos.leitor_pdf import LeitorPdf
from nucleo.erros import ErroDocumento

PASTA_BASE = Path(__file__).resolve().parents[2] / "base_conhecimento"

PDFS_REAIS = (
    "Politica_Reembolso.pdf",
    "Politica_Veiculos.pdf",
    "Procedimento_Ferias.pdf",
)

DIMENSAO_PAGINA_A4 = (595, 842)


def _criar_pdf_em_branco(caminho: Path, paginas: int) -> Path:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(*DIMENSAO_PAGINA_A4)
    with caminho.open("wb") as arquivo:
        escritor.write(arquivo)
    return caminho


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_pdf_real_devolve_paginas_com_texto(nome: str) -> None:
    paginas = LeitorPdf().ler(PASTA_BASE / nome)

    assert len(paginas) >= 1
    assert all(pagina.texto.strip() for pagina in paginas)


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_numeracao_das_paginas_comeca_em_1_e_segue_a_ordem(nome: str) -> None:
    paginas = LeitorPdf().ler(PASTA_BASE / nome)

    numeros = [pagina.numero for pagina in paginas]
    assert numeros == list(range(1, len(paginas) + 1))


def test_pagina_vazia_no_meio_nao_quebra_e_mantem_numeracao(tmp_path: Path) -> None:
    escritor = PdfWriter()
    with (PASTA_BASE / "Politica_Reembolso.pdf").open("rb") as origem:
        escritor.append(PdfReader(origem))
    escritor.add_blank_page(*DIMENSAO_PAGINA_A4)
    caminho = tmp_path / "com_pagina_vazia.pdf"
    with caminho.open("wb") as arquivo:
        escritor.write(arquivo)

    paginas = LeitorPdf().ler(caminho)

    assert [pagina.numero for pagina in paginas] == [1, 2, 3, 4]
    assert paginas[-1].texto.strip() == ""
    assert paginas[0].texto.strip() != ""


def test_caminho_inexistente_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = tmp_path / "nao_existe.pdf"

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_diretorio_no_lugar_do_pdf_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    pasta = tmp_path / "pasta_com_nome_de_pdf.pdf"
    pasta.mkdir()

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(pasta)

    assert str(pasta) in str(info.value)


def test_permissao_negada_levanta_erro_citando_o_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "bloqueado.pdf", paginas=1)
    abertura_original = Path.open

    def abrir_negando_acesso(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == caminho:
            raise PermissionError(13, "Permissão negada", str(self))
        return abertura_original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", abrir_negando_acesso)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_pdf_corrompido_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"isto nao e um pdf valido")

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_pdf_sem_paginas_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "sem_paginas.pdf", paginas=0)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_pdf_sem_texto_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "sem_texto.pdf", paginas=2)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_pdf_criptografado_sem_senha_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    escritor = PdfWriter()
    escritor.append(PdfReader(PASTA_BASE / "Politica_Reembolso.pdf"))
    escritor.encrypt("senha-de-teste")
    caminho = tmp_path / "criptografado.pdf"
    with caminho.open("wb") as arquivo:
        escritor.write(arquivo)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_erro_inesperado_do_pypdf_durante_extracao_vira_erro_documento(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = tmp_path / "stream_malformado.pdf"
    caminho.write_bytes((PASTA_BASE / "Politica_Reembolso.pdf").read_bytes())

    def extrair_com_falha(self: PageObject, *args: object, **kwargs: object) -> str:
        raise ValueError("stream malformado")

    monkeypatch.setattr(PageObject, "extract_text", extrair_com_falha)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_limite_do_pypdf_levanta_erro_citando_o_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "limite.pdf", paginas=1)

    def leitor_estourando_limite(*args: Any, **kwargs: Any) -> None:
        raise LimitReachedError("limite de recursos do pypdf atingido")

    monkeypatch.setattr("documentos.leitor_pdf.PdfReader", leitor_estourando_limite)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_erro_original_vai_para_log_em_debug_sem_conteudo_do_pdf(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"conteudo-secreto-do-documento")

    with (
        caplog.at_level(logging.DEBUG, logger="documentos.leitor_pdf"),
        pytest.raises(ErroDocumento),
    ):
        LeitorPdf().ler(caminho)

    registros = [r for r in caplog.records if r.name == "documentos.leitor_pdf"]
    assert len(registros) == 1
    assert registros[0].levelno == logging.DEBUG
    assert registros[0].exc_info is not None
    assert "conteudo-secreto-do-documento" not in caplog.text
