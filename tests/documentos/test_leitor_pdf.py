"""Testes do `LeitorPdf`. Só `LimitReachedError` é provocada por mock; o resto usa PDFs reais."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError

from documentos.leitor_pdf import LeitorPdf
from nucleo.contratos import LeitorDocumento
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


def test_implementa_o_contrato_leitor_documento() -> None:
    leitor: LeitorDocumento = LeitorPdf()
    assert callable(leitor.ler)


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


@pytest.mark.parametrize("nome", PDFS_REAIS)
def test_leitura_e_deterministica(nome: str) -> None:
    caminho = PASTA_BASE / nome

    assert LeitorPdf().ler(caminho) == LeitorPdf().ler(caminho)


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


def test_mensagem_de_arquivo_inexistente_usa_a_palavra_inexistente(tmp_path: Path) -> None:
    caminho = tmp_path / "nao_existe.pdf"

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert "inexistente" in str(info.value)
    assert "Não foi possível abrir" not in str(info.value)


def test_mensagem_de_arquivo_existente_que_nao_abre_nao_diz_inexistente(
    tmp_path: Path,
) -> None:
    pasta = tmp_path / "pasta_com_nome_de_pdf.pdf"
    pasta.mkdir()

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(pasta)

    assert "Não foi possível abrir" in str(info.value)
    assert "inexistente" not in str(info.value)


def test_permissao_negada_usa_mensagem_de_nao_foi_possivel_abrir(
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

    assert "Não foi possível abrir" in str(info.value)
    assert "inexistente" not in str(info.value)


def test_pdf_corrompido_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"isto nao e um pdf valido")

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)


def test_arquivo_vazio_levanta_erro(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.pdf"
    caminho.write_bytes(b"")

    with pytest.raises(ErroDocumento):
        LeitorPdf().ler(caminho)


def test_pdf_sem_paginas_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "sem_paginas.pdf", paginas=0)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)
    assert "sem páginas" in str(info.value)


def test_pdf_sem_texto_levanta_erro_citando_o_caminho(tmp_path: Path) -> None:
    caminho = _criar_pdf_em_branco(tmp_path / "sem_texto.pdf", paginas=2)

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert str(caminho) in str(info.value)
    assert "sem texto extraível" in str(info.value)


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


def test_erro_nao_encadeia_excecao_da_biblioteca(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"lixo")

    with pytest.raises(ErroDocumento) as info:
        LeitorPdf().ler(caminho)

    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


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
