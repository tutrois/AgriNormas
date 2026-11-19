"""Robustez da configuração: casos de borda e erros de entrada.

Exercita o caminho padrão de `carregar_configuracao` (sem `ambiente` injetado), que lê
`os.environ` e o `.env`. Cada teste isola o ambiente com `monkeypatch` e `tmp_path`.
"""

import pprint
from collections.abc import Mapping
from pathlib import Path

import pytest

from config import MASCARA_SEGREDO, carregar_configuracao
from nucleo.erros import ConfiguracaoInvalida

CHAVE_FALSA = "sk-teste-robustez-nao-e-real-5678"
AMBIENTE_MINIMO: Mapping[str, str] = {"OPENAI_API_KEY": CHAVE_FALSA}
VARIAVEIS_DO_PROJETO = (
    "OPENAI_API_KEY",
    "MODELO_GERACAO",
    "MODELO_EMBEDDING",
    "LIMIAR_SIMILARIDADE",
    "TOP_K",
    "PASTA_DOCUMENTOS",
    "TAMANHO_MAXIMO_CHUNK",
    "TIMEOUT_SEGUNDOS",
)


@pytest.fixture
def processo_sem_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove as variáveis do projeto do processo. O `monkeypatch` restaura o estado ao final."""
    for nome in VARIAVEIS_DO_PROJETO:
        monkeypatch.setenv(nome, "")
        monkeypatch.delenv(nome)


def _escrever_env(diretorio: Path, conteudo: str) -> Path:
    caminho = diretorio / ".env"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_sem_chave_no_processo_nem_no_env_lanca_erro_citando_a_variavel(
    processo_sem_configuracao: None, tmp_path: Path
) -> None:
    with pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"):
        carregar_configuracao(caminho_env=tmp_path / "inexistente.env")


def test_chave_definida_somente_no_env_e_carregada(
    processo_sem_configuracao: None, tmp_path: Path
) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\n")

    configuracao = carregar_configuracao(caminho_env=caminho)

    assert configuracao.chave_openai == CHAVE_FALSA


def test_variavel_do_processo_prevalece_sobre_o_env(
    processo_sem_configuracao: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-do-processo-prevalece")

    configuracao = carregar_configuracao(caminho_env=caminho)

    assert configuracao.chave_openai == "sk-do-processo-prevalece"


def test_valor_none_para_a_chave_e_tratado_como_ausente() -> None:
    with pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"):
        carregar_configuracao({"OPENAI_API_KEY": None})  # type: ignore[dict-item]


def test_chave_com_espacos_nas_bordas_e_normalizada() -> None:
    configuracao = carregar_configuracao({"OPENAI_API_KEY": f"  {CHAVE_FALSA}  "})

    assert configuracao.chave_openai == CHAVE_FALSA


def test_valor_invalido_no_env_cita_a_variavel(
    processo_sem_configuracao: None, tmp_path: Path
) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\nTOP_K=0\n")

    with pytest.raises(ConfiguracaoInvalida, match="TOP_K"):
        carregar_configuracao(caminho_env=caminho)


@pytest.mark.parametrize("limiar", ["inf", "-inf", "1e400"])
def test_limiar_infinito_fora_do_intervalo_lanca_erro(limiar: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match="LIMIAR_SIMILARIDADE"):
        carregar_configuracao({**AMBIENTE_MINIMO, "LIMIAR_SIMILARIDADE": limiar})


def test_limiar_com_espacos_nas_bordas_e_aceito() -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, "LIMIAR_SIMILARIDADE": " 0.5 "})

    assert configuracao.limiar_similaridade == 0.5


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("TOP_K", "-1"),
        ("TAMANHO_MAXIMO_CHUNK", "-1"),
        ("TIMEOUT_SEGUNDOS", "nan"),
        ("TIMEOUT_SEGUNDOS", "inf"),
        ("TIMEOUT_SEGUNDOS", "1e400"),
        ("TOP_K", "1e3"),
        ("TOP_K", "4.0"),
    ],
)
def test_valor_numerico_fora_da_regra_cita_a_variavel(variavel: str, valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match=variavel):
        carregar_configuracao({**AMBIENTE_MINIMO, variavel: valor})


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("TOP_K", "-424242"),
        ("TAMANHO_MAXIMO_CHUNK", "-424242"),
        ("TIMEOUT_SEGUNDOS", "-424242"),
        ("LIMIAR_SIMILARIDADE", "-424242"),
        ("TOP_K", "424242x"),
        ("TIMEOUT_SEGUNDOS", "424242x"),
        ("LIMIAR_SIMILARIDADE", "424242x"),
    ],
)
def test_mensagem_de_erro_nao_repete_o_valor_digitado(variavel: str, valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida) as excinfo:
        carregar_configuracao({**AMBIENTE_MINIMO, variavel: valor})

    assert "424242" not in str(excinfo.value)


def test_pprint_nao_exibe_a_chave() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    assert CHAVE_FALSA not in pprint.pformat(configuracao)


def test_f_string_nao_exibe_a_chave() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    assert CHAVE_FALSA not in f"{configuracao!r} {configuracao}"


def test_repr_mantem_a_mascara_em_vez_do_valor() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    assert f"chave_openai='{MASCARA_SEGREDO}'" in repr(configuracao)
