"""Calibra o piso de similaridade com as perguntas de `tests/validacao/perguntas.md` (ADR-011).

Indexa a base pelo fluxo de produção com o provedor real e imprime, por pergunta, as
pontuações, a posição do melhor trecho esperado e se ele chega à geração. Faz chamadas à API
(uma para as seções, outra para as perguntas) e não grava arquivos.

Uso, na raiz do projeto, com OPENAI_API_KEY no `.env`:

    .venv\\Scripts\\python.exe scripts\\calibrar_limiar.py

`src/` só entra em `sys.path` na execução direta, então importar o módulo não tem efeitos.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from busca.calibracao import PontuacaoPergunta
    from nucleo.modelos import Secao, Trecho

RAIZ_PROJETO: Final[Path] = Path(__file__).resolve().parents[1]
PASTA_SRC: Final[Path] = RAIZ_PROJETO / "src"
CAMINHO_PERGUNTAS: Final[Path] = RAIZ_PROJETO / "tests" / "validacao" / "perguntas.md"

TAMANHO_LOTE_EMBEDDINGS: Final[int] = 100
PERGUNTAS_FAQ: Final[bool] = True
"""Mesma configuração de `src/composicao.py`. Índice e contagem usam este valor, para que
`total_secoes` bata com o número de vetores.

A linha de base do ADR-002 foi medida com `False`; para reproduzi-la, troque aqui e em
`tests/integracao/test_calibracao.py`.
"""
CODIGO_SAIDA_OK: Final[int] = 0
CODIGO_SAIDA_FALHA: Final[int] = 1
SEPARADOR: Final[str] = "=" * 78


def _preparar_caminho() -> None:
    """Coloca `src/` no caminho de importação (só na execução direta)."""
    caminho = str(PASTA_SRC)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)


def _escrever(texto: str) -> None:
    sys.stdout.write(texto)


def _secoes_do_corpus(pasta: Path, tamanho_maximo: int) -> tuple[Secao, ...]:
    """Lê cada PDF da pasta e divide em seções, com o chunker de produção."""
    from documentos.chunker_secao import ChunkerPorSecao
    from documentos.leitor_pdf import LeitorPdf
    from documentos.limpeza import limpar_paginas
    from documentos.metadados import extrair_metadados

    secoes: list[Secao] = []
    for caminho in sorted(pasta.glob("*.pdf")):
        paginas = LeitorPdf().ler(caminho)
        codigo = extrair_metadados(paginas[0].texto, caminho).codigo
        chunker = ChunkerPorSecao(tamanho_maximo=tamanho_maximo)
        secoes.extend(chunker.dividir(codigo, limpar_paginas(paginas)))
    return tuple(secoes)


def _formatar_trecho(trecho: Trecho | None) -> str:
    if trecho is None:
        return "-"
    return f"{trecho.secao.documento} §{trecho.secao.numero}"


def _formatar_pontuacao(trecho: Trecho | None) -> str:
    return "-" if trecho is None else f"{trecho.pontuacao:.4f}"


def _chega_a_geracao(resultado: PontuacaoPergunta, piso: float, top_k: int) -> str:
    """`sim` quando o melhor trecho esperado fica no top-k e acima do piso; `-` sem esperado."""
    esperado = resultado.melhor_esperado
    posicao = resultado.posicao_melhor_esperado
    if esperado is None or posicao is None:
        return "-"
    return "sim" if posicao <= top_k and esperado.pontuacao >= piso else "não"


def _linha_tabela(resultado: PontuacaoPergunta, piso: float, top_k: int) -> str:
    melhor_esperado = resultado.melhor_esperado
    melhor_geral = resultado.melhor_geral
    posicao = resultado.posicao_melhor_esperado
    acima_piso = "sim" if melhor_geral is not None and melhor_geral.pontuacao >= piso else "não"
    return (
        f"  {resultado.pergunta.numero:<3}"
        f"{_formatar_pontuacao(melhor_esperado):>10}  "
        f"{_formatar_trecho(melhor_esperado):<18}"
        f"{'-' if posicao is None else posicao:>5}"
        f"{_formatar_pontuacao(melhor_geral):>10}  "
        f"{_formatar_trecho(melhor_geral):<20}"
        f"{acima_piso:>6}"
        f"{_chega_a_geracao(resultado, piso, top_k):>8}"
    )


def main() -> int:
    """Imprime a tabela de pontuações e devolve o código de saída."""
    from busca.calibracao import ler_perguntas_validacao, pontuar_perguntas
    from busca.indexacao import construir_indice, entradas_indexaveis
    from busca.provedor_openai import ProvedorEmbeddingOpenAI
    from config import carregar_configuracao
    from nucleo.erros import ErroAssistente

    configuracao = carregar_configuracao()
    try:
        secoes = _secoes_do_corpus(configuracao.pasta_documentos, configuracao.tamanho_maximo_chunk)
        if not secoes:
            _escrever("Nenhum chunk gerado a partir da base de conhecimento.\n")
            return CODIGO_SAIDA_FALHA

        provedor = ProvedorEmbeddingOpenAI(
            modelo=configuracao.modelo_embedding,
            chave=configuracao.chave_openai,
            tamanho_lote=TAMANHO_LOTE_EMBEDDINGS,
            timeout_segundos=configuracao.timeout_segundos,
        )
        indice = construir_indice(secoes, provedor, perguntas_faq=PERGUNTAS_FAQ)
        total_entradas = len(entradas_indexaveis(secoes, perguntas_faq=PERGUNTAS_FAQ))
        perguntas = ler_perguntas_validacao(CAMINHO_PERGUNTAS)
        vetores = provedor.gerar(tuple(pergunta.texto for pergunta in perguntas))
        resultados = pontuar_perguntas(perguntas, vetores, indice, total_entradas)
    except ErroAssistente as erro:
        _escrever(f"Falha na calibração: {erro}\n")
        return CODIGO_SAIDA_FALHA

    piso = configuracao.limiar_similaridade
    top_k = configuracao.top_k
    _escrever(f"{SEPARADOR}\nCalibração do piso de similaridade (ADR-011)\n")
    _escrever(f"Seções: {len(secoes)}. Entradas no índice: {total_entradas}\n")
    faq = "sim" if PERGUNTAS_FAQ else "não"
    _escrever(f"Perguntas de FAQ indexadas como entrada própria: {faq}\n")
    _escrever(f"Piso configurado (LIMIAR_SIMILARIDADE): {piso:.4f}. TOP_K: {top_k}\n")
    _escrever(f"Modelo de embedding: {configuracao.modelo_embedding}\n{SEPARADOR}\n")
    _escrever(
        f"  {'#':<3}{'Esperado':>10}  {'Trecho esperado':<18}{'Pos.':>5}"
        f"{'Geral':>10}  {'Trecho geral':<20}{'Piso?':>6}{'Top-k?':>8}\n"
    )
    for resultado in resultados:
        _escrever(_linha_tabela(resultado, piso, top_k) + "\n")
    _escrever(
        f"{SEPARADOR}\n"
        "Piso?: melhor trecho geral acima do piso. Top-k?: melhor trecho esperado entre as\n"
        "TOP_K primeiras e acima do piso, isto é, enviado à geração. Perguntas só com §faq-N\n"
        "aparecem sem trecho esperado.\n"
    )
    return CODIGO_SAIDA_OK


if __name__ == "__main__":
    _preparar_caminho()
    raise SystemExit(main())
