"""Regras de arquitetura, conferidas pela árvore de imports (`ast`).

`src/nucleo/` só importa biblioteca padrão e ele mesmo, sem `logging` nem `print`. Só
`src/composicao.py` conhece os pacotes `busca`, `documentos` e `geracao` e as bibliotecas
`openai`, `numpy` e `pypdf`.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

PASTA_SRC = Path(__file__).resolve().parents[1] / "src"
PASTA_NUCLEO = PASTA_SRC / "nucleo"
ARQUIVO_COMPOSICAO = PASTA_SRC / "composicao.py"

BIBLIOTECAS_PROIBIDAS_NO_NUCLEO = ("openai", "streamlit", "pypdf", "numpy")
BIBLIOTECAS_DE_IMPLEMENTACAO = ("openai", "numpy", "pypdf")
PACOTES_DE_IMPLEMENTACAO = ("busca", "documentos", "geracao")


def _arquivos_python(pasta: Path) -> list[Path]:
    return sorted(pasta.rglob("*.py"))


def _arvore(arquivo: Path) -> ast.Module:
    return ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))


def _modulos_importados(arquivo: Path) -> list[str]:
    """Nomes absolutos importados pelo arquivo. Imports relativos ficam de fora."""
    nomes: list[str] = []
    for no in ast.walk(_arvore(arquivo)):
        if isinstance(no, ast.Import):
            nomes.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module is not None:
            nomes.append(no.module)
    return nomes


def _raiz(nome: str) -> str:
    return nome.split(".")[0]


def _pertence(nome: str, raizes: tuple[str, ...]) -> bool:
    return _raiz(nome) in raizes


def _chamadas_de_print(arquivo: Path) -> int:
    return sum(
        1
        for no in ast.walk(_arvore(arquivo))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "print"
    )


def _violacoes(arquivos: list[Path], proibido: Callable[[str], bool]) -> list[str]:
    """Lista `arquivo: import` de cada import que o predicado marca como proibido."""
    return [
        f"{arquivo.relative_to(PASTA_SRC.parent)}: {nome}"
        for arquivo in arquivos
        for nome in _modulos_importados(arquivo)
        if proibido(nome)
    ]


def _outros_modulos_de_src() -> Iterator[Path]:
    """Módulos de `src/` que não são a composição nem pertencem aos pacotes de implementação."""
    for arquivo in _arquivos_python(PASTA_SRC):
        if arquivo == ARQUIVO_COMPOSICAO:
            continue
        if arquivo.relative_to(PASTA_SRC).parts[0] in PACOTES_DE_IMPLEMENTACAO:
            continue
        yield arquivo


def _nao_e_biblioteca_padrao_nem_nucleo(nome: str) -> bool:
    return _raiz(nome) != "nucleo" and _raiz(nome) not in sys.stdlib_module_names


def test_regras_encontram_arquivos_para_analisar() -> None:
    """Sem arquivos, os testes abaixo passariam sem verificar nada."""
    assert (PASTA_NUCLEO / "assistente.py") in _arquivos_python(PASTA_NUCLEO)
    assert ARQUIVO_COMPOSICAO.is_file()


@pytest.mark.parametrize("biblioteca", BIBLIOTECAS_PROIBIDAS_NO_NUCLEO)
def test_nucleo_nao_importa_bibliotecas_de_ia_pdf_ou_interface(biblioteca: str) -> None:
    violacoes = _violacoes(
        _arquivos_python(PASTA_NUCLEO),
        lambda nome: _pertence(nome, (biblioteca,)),
    )
    assert violacoes == [], f"o núcleo não pode importar {biblioteca}: {violacoes}"


def test_nucleo_so_importa_biblioteca_padrao_e_ele_mesmo() -> None:
    violacoes = _violacoes(_arquivos_python(PASTA_NUCLEO), _nao_e_biblioteca_padrao_nem_nucleo)
    assert violacoes == [], f"o núcleo não pode ter imports externos: {violacoes}"


def test_nucleo_nao_importa_logging_nem_chama_print() -> None:
    importa_logging = _violacoes(
        _arquivos_python(PASTA_NUCLEO),
        lambda nome: _pertence(nome, ("logging",)),
    )
    chamadas_print = {
        arquivo.name: _chamadas_de_print(arquivo)
        for arquivo in _arquivos_python(PASTA_NUCLEO)
        if _chamadas_de_print(arquivo)
    }
    assert importa_logging == [], f"o núcleo não usa logging: {importa_logging}"
    assert chamadas_print == {}, f"o núcleo não chama print: {chamadas_print}"


@pytest.mark.parametrize("biblioteca", BIBLIOTECAS_DE_IMPLEMENTACAO)
def test_so_composicao_importa_bibliotecas_de_implementacao(biblioteca: str) -> None:
    violacoes = _violacoes(
        list(_outros_modulos_de_src()),
        lambda nome: _pertence(nome, (biblioteca,)),
    )
    assert violacoes == [], f"só src/composicao.py pode importar {biblioteca}: {violacoes}"


def test_so_composicao_importa_pacotes_de_implementacao() -> None:
    violacoes = _violacoes(
        list(_outros_modulos_de_src()),
        lambda nome: _pertence(nome, PACOTES_DE_IMPLEMENTACAO),
    )
    assert violacoes == [], f"só src/composicao.py conhece as implementações concretas: {violacoes}"


def test_detector_acusa_import_proibido_em_arquivo_novo(tmp_path: Path) -> None:
    """Prova que a regra falha quando alguém adiciona um import proibido ao núcleo."""
    arquivo = tmp_path / "vazamento.py"
    arquivo.write_text("import openai\nfrom numpy import array\n", encoding="utf-8")

    assert _modulos_importados(arquivo) == ["openai", "numpy"]
    assert _pertence("openai", ("openai",))
    assert _pertence("numpy.linalg", ("numpy",))


def test_detector_ignora_import_relativo_e_biblioteca_padrao(tmp_path: Path) -> None:
    arquivo = tmp_path / "ok.py"
    arquivo.write_text(
        "from . import irmao\nfrom .modelos import Secao\nimport ast\nfrom pathlib import Path\n",
        encoding="utf-8",
    )

    assert _modulos_importados(arquivo) == ["ast", "pathlib"]
    assert not _nao_e_biblioteca_padrao_nem_nucleo("pathlib")
    assert not _nao_e_biblioteca_padrao_nem_nucleo("nucleo.modelos")
    assert _nao_e_biblioteca_padrao_nem_nucleo("pypdf")
