"""Teste de presença dos PDFs de `base_conhecimento/` (TSK-004.3).

O caminho é montado a partir de `Path(__file__)`, e não do diretório de trabalho,
para que o resultado seja o mesmo qualquer que seja a pasta de execução.
"""

from __future__ import annotations

from pathlib import Path

import pytest

NOMES_ESPERADOS: tuple[str, ...] = (
    "Politica_Reembolso.pdf",
    "Politica_Veiculos.pdf",
    "Procedimento_Ferias.pdf",
)

RAIZ_PROJETO = Path(__file__).resolve().parents[2]


def _pasta_base() -> Path:
    """Pasta `base_conhecimento/` na raiz do projeto, independente do diretório atual."""
    return RAIZ_PROJETO / "base_conhecimento"


def _ausentes(pasta: Path) -> tuple[str, ...]:
    """Nomes esperados que não existem como arquivo dentro de `pasta`."""
    return tuple(nome for nome in NOMES_ESPERADOS if not (pasta / nome).is_file())


def test_pdfs_esperados_existem_em_base_conhecimento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(RAIZ_PROJETO.parent)
    ausentes = _ausentes(_pasta_base())
    assert not ausentes, f"Arquivo(s) ausente(s) em base_conhecimento/: {', '.join(ausentes)}"


def test_detecta_pdf_faltante_pelo_nome(tmp_path: Path) -> None:
    (tmp_path / "Politica_Reembolso.pdf").write_bytes(b"")
    (tmp_path / "Politica_Veiculos.pdf").write_bytes(b"")
    assert _ausentes(tmp_path) == ("Procedimento_Ferias.pdf",)
