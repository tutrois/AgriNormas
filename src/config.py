"""Configuração tipada e validada do AgriNormas (HIST-002).

Lê as variáveis de ambiente, completadas pelo arquivo `.env` quando ele existe.
Não importa nenhuma biblioteca de IA e não tem efeito colateral no import.
Erros de configuração são `ConfiguracaoInvalida`, citam o nome da variável e nunca o valor.
"""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from dotenv import load_dotenv

from nucleo.erros import ConfiguracaoInvalida

RAIZ_PROJETO = Path(__file__).parent.parent
CAMINHO_ENV_PADRAO = RAIZ_PROJETO / ".env"

NOME_CHAVE_OPENAI = "OPENAI_API_KEY"
MASCARA_SEGREDO = "***"
_CAMPOS_SECRETOS = frozenset({"chave_openai"})

PADRAO_MODELO_GERACAO = "gpt-4o-mini"
PADRAO_MODELO_EMBEDDING = "text-embedding-3-small"
PADRAO_LIMIAR_SIMILARIDADE = 0.60
PADRAO_TOP_K = 4
PADRAO_PASTA_DOCUMENTOS = "base_conhecimento"
PADRAO_TAMANHO_MAXIMO_CHUNK = 1200
PADRAO_TIMEOUT_SEGUNDOS = 30.0
PADRAO_NUMERO_REFORMULACOES = 3

TOP_K_MINIMO = 1
TOP_K_MAXIMO = 50
TAMANHO_CHUNK_MINIMO = 100
TAMANHO_CHUNK_MAXIMO = 10000
NUMERO_REFORMULACOES_MINIMO = 0
NUMERO_REFORMULACOES_MAXIMO = 5


@dataclass(frozen=True, repr=False)
class Configuracao:
    """Valores de execução já validados. A chave da API nunca aparece em `repr`."""

    chave_openai: str
    modelo_geracao: str
    modelo_embedding: str
    limiar_similaridade: float
    top_k: int
    numero_reformulacoes: int
    pasta_documentos: Path
    tamanho_maximo_chunk: int
    timeout_segundos: float

    def __repr__(self) -> str:
        partes = [
            f"{campo.name}={_valor_exibido(campo.name, getattr(self, campo.name))!r}"
            for campo in fields(self)
        ]
        return f"Configuracao({', '.join(partes)})"


def carregar_configuracao(
    ambiente: Mapping[str, str] | None = None,
    caminho_env: Path | None = None,
) -> Configuracao:
    """Monta a `Configuracao` a partir de `ambiente` ou, se for None, do `.env` e de `os.environ`.

    Quando `ambiente` é informado, o `.env` e `os.environ` são ignorados.
    Lança `ConfiguracaoInvalida` se algum valor estiver ausente ou fora do esperado.
    """
    valores = _ambiente_do_processo(caminho_env) if ambiente is None else ambiente
    return Configuracao(
        chave_openai=_chave_openai(valores),
        modelo_geracao=_texto(valores, "MODELO_GERACAO", PADRAO_MODELO_GERACAO),
        modelo_embedding=_texto(valores, "MODELO_EMBEDDING", PADRAO_MODELO_EMBEDDING),
        limiar_similaridade=_limiar(valores),
        top_k=_inteiro_entre(valores, "TOP_K", PADRAO_TOP_K, TOP_K_MINIMO, TOP_K_MAXIMO),
        numero_reformulacoes=_inteiro_entre(
            valores,
            "NUMERO_REFORMULACOES",
            PADRAO_NUMERO_REFORMULACOES,
            NUMERO_REFORMULACOES_MINIMO,
            NUMERO_REFORMULACOES_MAXIMO,
        ),
        pasta_documentos=_pasta_documentos(valores),
        tamanho_maximo_chunk=_inteiro_entre(
            valores,
            "TAMANHO_MAXIMO_CHUNK",
            PADRAO_TAMANHO_MAXIMO_CHUNK,
            TAMANHO_CHUNK_MINIMO,
            TAMANHO_CHUNK_MAXIMO,
        ),
        timeout_segundos=_decimal_positivo(valores, "TIMEOUT_SEGUNDOS", PADRAO_TIMEOUT_SEGUNDOS),
    )


def _valor_exibido(nome: str, valor: object) -> object:
    return MASCARA_SEGREDO if nome in _CAMPOS_SECRETOS else valor


def _ambiente_do_processo(caminho_env: Path | None) -> Mapping[str, str]:
    caminho = CAMINHO_ENV_PADRAO if caminho_env is None else caminho_env
    if caminho.is_file():
        _carregar_arquivo_env(caminho)
    return os.environ


def _carregar_arquivo_env(caminho: Path) -> None:
    """Lê o `.env` sem expor o conteúdo: erros de leitura citam apenas o caminho."""
    try:
        load_dotenv(caminho, override=False)
    except OSError, UnicodeDecodeError:
        raise ConfiguracaoInvalida(
            f"Não foi possível ler o arquivo de configuração {caminho}. "
            "Verifique se ele existe e está codificado em UTF-8."
        ) from None


def _bruto(valores: Mapping[str, str], nome: str) -> str | None:
    """Devolve o valor sem espaços nas bordas, ou None se estiver ausente, for None ou vazio."""
    return (valores.get(nome) or "").strip() or None


def _texto(valores: Mapping[str, str], nome: str, padrao: str) -> str:
    return _bruto(valores, nome) or padrao


def _chave_openai(valores: Mapping[str, str]) -> str:
    chave = _bruto(valores, NOME_CHAVE_OPENAI)
    if chave is None:
        raise ConfiguracaoInvalida(
            f"A variável {NOME_CHAVE_OPENAI} é obrigatória e está ausente ou vazia. "
            "Defina-a no arquivo .env."
        )
    return chave


def _inteiro_entre(
    valores: Mapping[str, str], nome: str, padrao: int, minimo: int, maximo: int
) -> int:
    bruto = _bruto(valores, nome)
    if bruto is None:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ConfiguracaoInvalida(f"{nome} deve ser um número inteiro.") from None
    if not minimo <= valor <= maximo:
        raise ConfiguracaoInvalida(f"{nome} deve estar entre {minimo} e {maximo}.")
    return valor


def _decimal(valores: Mapping[str, str], nome: str, padrao: float) -> float:
    bruto = _bruto(valores, nome)
    if bruto is None:
        return padrao
    try:
        return float(bruto)
    except ValueError:
        raise ConfiguracaoInvalida(
            f"{nome} deve ser um número decimal, com ponto como separador."
        ) from None


def _limiar(valores: Mapping[str, str]) -> float:
    valor = _decimal(valores, "LIMIAR_SIMILARIDADE", PADRAO_LIMIAR_SIMILARIDADE)
    if not 0.0 <= valor <= 1.0:
        raise ConfiguracaoInvalida("LIMIAR_SIMILARIDADE deve estar entre 0 e 1.")
    return valor


def _decimal_positivo(valores: Mapping[str, str], nome: str, padrao: float) -> float:
    valor = _decimal(valores, nome, padrao)
    if not (math.isfinite(valor) and valor > 0):
        raise ConfiguracaoInvalida(f"{nome} deve ser um número finito maior que zero.")
    return valor


def _pasta_documentos(valores: Mapping[str, str]) -> Path:
    """Expande `~`. Caminho relativo é resolvido a partir da raiz do projeto."""
    caminho = Path(_texto(valores, "PASTA_DOCUMENTOS", PADRAO_PASTA_DOCUMENTOS)).expanduser()
    return caminho if caminho.is_absolute() else RAIZ_PROJETO / caminho
