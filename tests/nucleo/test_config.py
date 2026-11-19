"""Testes da configuração tipada e validada, sem ler `os.environ` nem o `.env` real."""

import os
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

from config import (
    MASCARA_SEGREDO,
    PADRAO_LIMIAR_SIMILARIDADE,
    PADRAO_MODELO_EMBEDDING,
    PADRAO_MODELO_GERACAO,
    PADRAO_PASTA_DOCUMENTOS,
    PADRAO_TAMANHO_MAXIMO_CHUNK,
    PADRAO_TIMEOUT_SEGUNDOS,
    PADRAO_TOP_K,
    RAIZ_PROJETO,
    Configuracao,
    carregar_configuracao,
)
from nucleo.erros import ConfiguracaoInvalida

CHAVE_FALSA = "sk-teste-nao-e-uma-chave-real-1234"
AMBIENTE_MINIMO: Mapping[str, str] = {"OPENAI_API_KEY": CHAVE_FALSA}
CAMINHO_ENV_EXEMPLO = RAIZ_PROJETO / ".env.example"
CHAVES_DO_PROJETO = (
    "OPENAI_API_KEY",
    "MODELO_GERACAO",
    "MODELO_EMBEDDING",
    "LIMIAR_SIMILARIDADE",
    "TOP_K",
    "PASTA_DOCUMENTOS",
    "TAMANHO_MAXIMO_CHUNK",
    "TIMEOUT_SEGUNDOS",
)


def _escrever_env(diretorio: Path, conteudo: str) -> Path:
    caminho = diretorio / ".env"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_carrega_todos_os_valores_do_ambiente_injetado() -> None:
    ambiente = {
        "OPENAI_API_KEY": CHAVE_FALSA,
        "MODELO_GERACAO": "modelo-geracao-teste",
        "MODELO_EMBEDDING": "modelo-embedding-teste",
        "LIMIAR_SIMILARIDADE": "0.5",
        "TOP_K": "7",
        "PASTA_DOCUMENTOS": str(RAIZ_PROJETO / "outra_pasta"),
        "TAMANHO_MAXIMO_CHUNK": "800",
        "TIMEOUT_SEGUNDOS": "12.5",
    }

    configuracao = carregar_configuracao(ambiente)

    assert configuracao == Configuracao(
        chave_openai=CHAVE_FALSA,
        modelo_geracao="modelo-geracao-teste",
        modelo_embedding="modelo-embedding-teste",
        limiar_similaridade=0.5,
        top_k=7,
        pasta_documentos=RAIZ_PROJETO / "outra_pasta",
        tamanho_maximo_chunk=800,
        timeout_segundos=12.5,
    )


def test_usa_valores_padrao_quando_somente_a_chave_e_informada() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    assert configuracao.chave_openai == CHAVE_FALSA
    assert configuracao.modelo_geracao == PADRAO_MODELO_GERACAO
    assert configuracao.modelo_embedding == PADRAO_MODELO_EMBEDDING
    assert configuracao.limiar_similaridade == PADRAO_LIMIAR_SIMILARIDADE
    assert configuracao.top_k == PADRAO_TOP_K
    assert configuracao.tamanho_maximo_chunk == PADRAO_TAMANHO_MAXIMO_CHUNK
    assert configuracao.timeout_segundos == PADRAO_TIMEOUT_SEGUNDOS


def test_pasta_relativa_e_resolvida_a_partir_da_raiz_do_projeto() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    assert configuracao.pasta_documentos == RAIZ_PROJETO / PADRAO_PASTA_DOCUMENTOS


def test_padroes_do_codigo_coincidem_com_env_example() -> None:
    assert CAMINHO_ENV_EXEMPLO.is_file()
    valores_brutos = dotenv_values(CAMINHO_ENV_EXEMPLO)
    faltando = set(CHAVES_DO_PROJETO) - set(valores_brutos)
    assert not faltando, f".env.example sem as chaves: {sorted(faltando)}"
    valores_exemplo: dict[str, str] = {
        chave: valor for chave, valor in valores_brutos.items() if valor
    }

    configuracao_exemplo = carregar_configuracao({**valores_exemplo, **AMBIENTE_MINIMO})

    assert configuracao_exemplo == carregar_configuracao(AMBIENTE_MINIMO)


# Caminho padrão: arquivo .env e os.environ (ambiente=None)


def test_le_o_env_quando_ambiente_nao_e_informado(tmp_path: Path) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\nTOP_K=9\n")

    with patch.dict(os.environ, {}, clear=True):
        configuracao = carregar_configuracao(None, caminho_env=caminho)

    assert configuracao.chave_openai == CHAVE_FALSA
    assert configuracao.top_k == 9


def test_variavel_do_processo_tem_precedencia_sobre_o_env(tmp_path: Path) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\n")

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-do-processo-prevalece"}, clear=True):
        configuracao = carregar_configuracao(None, caminho_env=caminho)

    assert configuracao.chave_openai == "sk-do-processo-prevalece"


def test_env_ausente_nao_quebra_e_sem_chave_lanca_erro(tmp_path: Path) -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"),
    ):
        carregar_configuracao(None, caminho_env=tmp_path / "inexistente.env")


def test_env_com_bytes_invalidos_lanca_erro_sem_expor_conteudo(tmp_path: Path) -> None:
    caminho = tmp_path / ".env"
    caminho.write_bytes(b"OPENAI_API_KEY=\x80segredo-no-arquivo\n")

    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(ConfiguracaoInvalida, match="arquivo de configuração") as excinfo,
    ):
        carregar_configuracao(None, caminho_env=caminho)

    assert excinfo.value.__suppress_context__ is True
    assert "segredo-no-arquivo" not in str(excinfo.value)
    assert str(caminho) in str(excinfo.value)


@pytest.mark.parametrize(
    "erro",
    [OSError("permissao-negada-interna"), UnicodeDecodeError("utf-8", b"\x80", 0, 1, "motivo")],
    ids=["os_error", "unicode_decode_error"],
)
def test_falha_de_leitura_do_env_cita_o_caminho_e_nao_o_erro_original(
    tmp_path: Path, erro: Exception
) -> None:
    caminho = _escrever_env(tmp_path, f"OPENAI_API_KEY={CHAVE_FALSA}\n")

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("config.load_dotenv", side_effect=erro),
        pytest.raises(ConfiguracaoInvalida) as excinfo,
    ):
        carregar_configuracao(None, caminho_env=caminho)

    assert excinfo.value.__suppress_context__ is True
    assert str(caminho) in str(excinfo.value)
    assert "permissao-negada-interna" not in str(excinfo.value)


@pytest.mark.parametrize(
    "ambiente",
    [{}, {"OPENAI_API_KEY": ""}, {"OPENAI_API_KEY": "   "}],
    ids=["ausente", "vazia", "so_espacos"],
)
def test_chave_ausente_ou_vazia_lanca_erro_citando_o_nome(ambiente: Mapping[str, str]) -> None:
    with pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"):
        carregar_configuracao(ambiente)


@pytest.mark.parametrize("limiar", ["1.5", "-0.1", "nan"])
def test_limiar_fora_do_intervalo_lanca_erro(limiar: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match="LIMIAR_SIMILARIDADE"):
        carregar_configuracao({**AMBIENTE_MINIMO, "LIMIAR_SIMILARIDADE": limiar})


@pytest.mark.parametrize("limiar", ["0", "1"])
def test_limiar_nos_limites_do_intervalo_e_aceito(limiar: str) -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, "LIMIAR_SIMILARIDADE": limiar})

    assert configuracao.limiar_similaridade == float(limiar)


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("TOP_K", "abc"),
        ("TOP_K", "2.5"),
        ("TAMANHO_MAXIMO_CHUNK", "mil"),
        ("TIMEOUT_SEGUNDOS", "rapido"),
        ("LIMIAR_SIMILARIDADE", "0,35"),
    ],
)
def test_valor_numerico_invalido_cita_a_variavel(variavel: str, valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match=variavel):
        carregar_configuracao({**AMBIENTE_MINIMO, variavel: valor})


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("TOP_K", "0"),
        ("TAMANHO_MAXIMO_CHUNK", "0"),
        ("TIMEOUT_SEGUNDOS", "0"),
        ("TIMEOUT_SEGUNDOS", "-5"),
    ],
)
def test_valor_abaixo_do_minimo_lanca_erro_citando_a_variavel(variavel: str, valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match=variavel):
        carregar_configuracao({**AMBIENTE_MINIMO, variavel: valor})


@pytest.mark.parametrize("valor", ["nan", "inf"])
def test_timeout_nao_finito_exige_numero_finito(valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida, match="TIMEOUT_SEGUNDOS.*finito"):
        carregar_configuracao({**AMBIENTE_MINIMO, "TIMEOUT_SEGUNDOS": valor})


def test_repr_nao_exibe_a_chave() -> None:
    configuracao = carregar_configuracao(AMBIENTE_MINIMO)

    representacao = repr(configuracao)

    assert CHAVE_FALSA not in representacao
    assert CHAVE_FALSA not in str(configuracao)
    assert f"chave_openai='{MASCARA_SEGREDO}'" in representacao
    assert f"top_k={PADRAO_TOP_K}" in representacao


def test_mensagem_de_erro_nao_expoe_a_chave_nem_o_valor_digitado() -> None:
    valor_errado = "valor-digitado-por-engano"
    ambiente = {"OPENAI_API_KEY": CHAVE_FALSA, "TOP_K": valor_errado}

    with pytest.raises(ConfiguracaoInvalida) as excinfo:
        carregar_configuracao(ambiente)

    mensagem = str(excinfo.value)
    assert CHAVE_FALSA not in mensagem
    assert valor_errado not in mensagem
    assert excinfo.value.__suppress_context__ is True


# Regra (d): valor vazio ou só com espaços usa o padrão; chave vazia é ausente

CAMPOS_COM_PADRAO = (
    "MODELO_GERACAO",
    "MODELO_EMBEDDING",
    "LIMIAR_SIMILARIDADE",
    "TOP_K",
    "PASTA_DOCUMENTOS",
    "TAMANHO_MAXIMO_CHUNK",
    "TIMEOUT_SEGUNDOS",
)


@pytest.mark.parametrize("valor_em_branco", ["", "   "], ids=["vazio", "so_espacos"])
@pytest.mark.parametrize("variavel", CAMPOS_COM_PADRAO)
def test_campo_vazio_ou_so_com_espacos_usa_o_padrao(variavel: str, valor_em_branco: str) -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, variavel: valor_em_branco})

    assert configuracao == carregar_configuracao(AMBIENTE_MINIMO)


@pytest.mark.parametrize("valor_em_branco", ["", "   "], ids=["vazio", "so_espacos"])
def test_chave_vazia_ou_so_com_espacos_continua_sendo_tratada_como_ausente(
    valor_em_branco: str,
) -> None:
    ambiente = {"OPENAI_API_KEY": valor_em_branco, "TOP_K": "", "TIMEOUT_SEGUNDOS": "   "}

    with pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"):
        carregar_configuracao(ambiente)


# Regra (e): com `ambiente` informado, .env e os.environ são ignorados


def test_ambiente_informado_ignora_env_e_os_environ(tmp_path: Path) -> None:
    caminho = _escrever_env(
        tmp_path,
        "OPENAI_API_KEY=sk-do-arquivo-env\nMODELO_GERACAO=modelo-do-arquivo\nTOP_K=9\n",
    )
    ambiente = {"OPENAI_API_KEY": CHAVE_FALSA, "TAMANHO_MAXIMO_CHUNK": "640"}
    do_processo = {
        "OPENAI_API_KEY": "sk-do-processo",
        "MODELO_GERACAO": "modelo-do-processo",
        "TOP_K": "11",
    }

    with patch.dict(os.environ, do_processo, clear=True):
        configuracao = carregar_configuracao(ambiente, caminho_env=caminho)

    assert configuracao.chave_openai == CHAVE_FALSA
    assert configuracao.tamanho_maximo_chunk == 640
    assert configuracao.modelo_geracao == PADRAO_MODELO_GERACAO
    assert configuracao.top_k == PADRAO_TOP_K


def test_ambiente_informado_nao_abre_o_arquivo_env(tmp_path: Path) -> None:
    caminho = _escrever_env(tmp_path, "OPENAI_API_KEY=sk-do-arquivo-env\n")

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("config.load_dotenv") as carregador,
    ):
        carregar_configuracao(AMBIENTE_MINIMO, caminho_env=caminho)

    carregador.assert_not_called()


def test_ambiente_informado_sem_chave_nao_usa_a_chave_do_processo() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": CHAVE_FALSA}, clear=True),
        pytest.raises(ConfiguracaoInvalida, match="OPENAI_API_KEY"),
    ):
        carregar_configuracao({})


# Tetos de segurança para TOP_K e TAMANHO_MAXIMO_CHUNK


@pytest.mark.parametrize("top_k", ["1", "50"], ids=["minimo", "maximo"])
def test_top_k_nos_limites_do_intervalo_e_aceito(top_k: str) -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, "TOP_K": top_k})

    assert configuracao.top_k == int(top_k)


def test_top_k_acima_do_teto_lanca_erro_citando_a_variavel() -> None:
    with pytest.raises(ConfiguracaoInvalida, match="TOP_K"):
        carregar_configuracao({**AMBIENTE_MINIMO, "TOP_K": "51"})


def test_tamanho_chunk_abaixo_do_teto_lanca_erro_citando_a_variavel() -> None:
    with pytest.raises(ConfiguracaoInvalida, match="TAMANHO_MAXIMO_CHUNK"):
        carregar_configuracao({**AMBIENTE_MINIMO, "TAMANHO_MAXIMO_CHUNK": "99"})


def test_tamanho_chunk_no_teto_superior_e_aceito() -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, "TAMANHO_MAXIMO_CHUNK": "10000"})

    assert configuracao.tamanho_maximo_chunk == 10000


# Expansão de `~` em PASTA_DOCUMENTOS


def test_pasta_com_til_expande_para_a_pasta_do_usuario() -> None:
    configuracao = carregar_configuracao({**AMBIENTE_MINIMO, "PASTA_DOCUMENTOS": "~/x"})

    assert configuracao.pasta_documentos == Path.home() / "x"
