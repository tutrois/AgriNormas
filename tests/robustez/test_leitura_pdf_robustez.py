"""Robustez de ponta a ponta da leitura de PDFs (HIST-004).

Cada caso de erro termina em `ErroDocumento` com o caminho citado, nunca em exceção
não tratada. Os casos de permissão e de exceção inesperada da biblioteca usam
`monkeypatch` porque o sistema operacional e o pypdf não permitem reproduzi-los
de forma portátil com arquivos reais.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pypdf import PageObject, PdfReader, PdfWriter

from documentos.leitor_pdf import LeitorPdf
from nucleo.erros import ErroDocumento

PASTA_BASE = Path(__file__).resolve().parents[2] / "base_conhecimento"
PDF_REAL = PASTA_BASE / "Politica_Reembolso.pdf"
DIMENSAO_PAGINA_A4 = (595, 842)


def _gravar_pdf(caminho: Path, escritor: PdfWriter) -> Path:
    with caminho.open("wb") as arquivo:
        escritor.write(arquivo)
    return caminho


def test_permissao_negada_levanta_erro_citando_o_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = tmp_path / "bloqueado.pdf"
    caminho.write_bytes(PDF_REAL.read_bytes())
    abertura_original: Callable[..., Any] = Path.open

    def abrir_negando_acesso(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == caminho:
            raise PermissionError(13, "Permissão negada", str(self))
        return abertura_original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", abrir_negando_acesso)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_diretorio_no_lugar_do_pdf_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    pasta = tmp_path / "pasta_com_nome_de_pdf.pdf"
    pasta.mkdir()

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(pasta)

    assert str(pasta) in str(info.value)


def test_pdf_criptografado_sem_senha_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    escritor = PdfWriter()
    escritor.append(PdfReader(PDF_REAL))
    escritor.encrypt("senha-de-teste")
    caminho = _gravar_pdf(tmp_path / "criptografado.pdf", escritor)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_cabecalho_sem_estrutura_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = tmp_path / "so_cabecalho.pdf"
    caminho.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_pagina_vazia_no_inicio_e_texto_depois_mantem_numeracao_e_conteudo(
    tmp_path: Path,
) -> None:
    escritor = PdfWriter()
    escritor.add_blank_page(*DIMENSAO_PAGINA_A4)
    escritor.append(PdfReader(PDF_REAL))
    caminho = _gravar_pdf(tmp_path / "vazia_no_inicio.pdf", escritor)

    paginas = LeitorPdf().ler(caminho)

    assert [pagina.numero for pagina in paginas] == [1, 2, 3, 4]
    assert paginas[0].texto.strip() == ""
    assert all(pagina.texto.strip() for pagina in paginas[1:])


def test_paginas_mistas_vazias_e_com_texto_nao_descartam_as_vazias(tmp_path: Path) -> None:
    escritor = PdfWriter()
    escritor.add_blank_page(*DIMENSAO_PAGINA_A4)
    escritor.append(PdfReader(PDF_REAL))
    escritor.add_blank_page(*DIMENSAO_PAGINA_A4)
    caminho = _gravar_pdf(tmp_path / "mistas.pdf", escritor)

    paginas = LeitorPdf().ler(caminho)

    assert len(paginas) == 5
    assert [pagina.texto.strip() == "" for pagina in paginas] == [
        True,
        False,
        False,
        False,
        True,
    ]


def test_erro_inesperado_do_pypdf_durante_extracao_vira_erro_documento(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = tmp_path / "stream_malformado.pdf"
    caminho.write_bytes(PDF_REAL.read_bytes())

    def extrair_com_falha(self: PageObject, *args: object, **kwargs: object) -> str:
        raise ValueError("stream malformado")

    monkeypatch.setattr(PageObject, "extract_text", extrair_com_falha)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)
