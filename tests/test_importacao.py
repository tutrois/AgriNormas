"""Teste de fumaça: todos os pacotes de src/ podem ser importados (HIST-001)."""

import importlib

import pytest

PACOTES = ["nucleo", "documentos", "busca", "geracao", "interface"]


@pytest.mark.parametrize("nome", PACOTES)
def test_pacote_importa_e_tem_documentacao(nome: str) -> None:
    modulo = importlib.import_module(nome)

    assert modulo.__doc__, f"o pacote {nome} precisa de uma docstring"
