"""Calibração do limiar de similaridade com as perguntas de validação (HIST-011, TSK-011.2).

Lê os PDFs de `base_conhecimento/` pelo fluxo da produção (leitura, metadados, limpeza e
chunking), gera os embeddings com o provedor real e pontua as seis perguntas de
`tests/validacao/perguntas.md`. A saída vai para o terminal. Não grava cache nem arquivos.

Chamadas à API: uma para os chunks (em um lote) e uma para as perguntas. Use com moderação.

Uso, a partir da raiz do projeto, com OPENAI_API_KEY no `.env`:

    .venv\\Scripts\\python.exe scripts\\calibrar_limiar.py

Importar este módulo não tem efeitos colaterais: `src/` só entra em `sys.path` quando o
script é executado diretamente.
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
"""Mesma configuração de `src/composicao.py`: cada par de FAQ ganha uma entrada com a pergunta.

Índice e contagem usam este valor, para que `total_secoes` bata com o número de vetores.
A linha de base de ADR-002 (55 entradas, uma por seção, sem perguntas de FAQ) foi medida com
`False`. Para reproduzi-la, troque para `False` aqui e em `tests/integracao/test_calibracao.py`.
"""
CODIGO_SAIDA_OK: Final[int] = 0
CODIGO_SAIDA_FALHA: Final[int] = 1
SEPARADOR: Final[str] = "=" * 78


def _preparar_caminho() -> None:
    """Coloca `src/` no caminho de importação. Chamada só pela execução direta do script."""
    caminho = str(PASTA_SRC)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)


def _escrever(texto: str) -> None:
    sys.stdout.write(texto)


def _secoes_do_corpus(pasta: Path, tamanho_maximo: int) -> tuple[Secao, ...]:
    """Lê cada PDF e divide em seções, pelo mesmo fluxo de `scripts/relatorio_corpus.py`."""
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


def _linha_tabela(resultado: PontuacaoPergunta, limiar: float) -> str:
    melhor_esperado = resultado.melhor_esperado
    melhor_geral = resultado.melhor_geral
    acima = "sim" if melhor_geral is not None and melhor_geral.pontuacao >= limiar else "não"
    return (
        f"  {resultado.pergunta.numero:<3}"
        f"{_formatar_pontuacao(melhor_esperado):>10}  "
        f"{_formatar_trecho(melhor_esperado):<18}"
        f"{_formatar_pontuacao(melhor_geral):>10}  "
        f"{_formatar_trecho(melhor_geral):<18}"
        f"{acima:>8}"
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

    limiar = configuracao.limiar_similaridade
    _escrever(f"{SEPARADOR}\nCalibração do limiar de similaridade\n")
    _escrever(f"Seções: {len(secoes)}. Entradas no índice: {total_entradas}\n")
    faq = "sim" if PERGUNTAS_FAQ else "não"
    _escrever(f"Perguntas de FAQ indexadas como entrada própria: {faq}\n")
    _escrever(f"Limiar configurado (LIMIAR_SIMILARIDADE): {limiar:.4f}\n")
    _escrever(f"Modelo de embedding: {configuracao.modelo_embedding}\n{SEPARADOR}\n")
    _escrever(
        f"  {'#':<3}{'Esperado':>10}  {'Trecho esperado':<18}"
        f"{'Geral':>10}  {'Trecho geral':<18}{'Acima?':>8}\n"
    )
    for resultado in resultados:
        _escrever(_linha_tabela(resultado, limiar) + "\n")
    _escrever(f"{SEPARADOR}\n")
    return CODIGO_SAIDA_OK


if __name__ == "__main__":
    _preparar_caminho()
    raise SystemExit(main())
