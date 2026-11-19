"""Medição da recuperação com a API real (HIST-029): busca simples (N=0) ou com reformulações (N>0).

Não é teste automatizado: consome créditos da API e não roda na suíte offline. Usa a configuração
do `.env`, com `NUMERO_REFORMULACOES` definido pela linha de comando. Para cada pergunta de
`tests/validacao/perguntas.md` imprime uma linha com as seções recuperadas (as que chegam ao
gerador), as seções citadas, se cada seção esperada foi recuperada, se houve recusa e a melhor
pontuação entre as seções esperadas. Não imprime chave nem texto das respostas.

Uso, a partir da raiz do projeto:

    .venv/Scripts/python.exe tests/validacao/medir_recuperacao.py --formulacoes 0 --execucao 1
    .venv/Scripts/python.exe tests/validacao/medir_recuperacao.py --formulacoes 3 --execucao 1

O pipeline espelha `composicao.montar_assistente`. Se a composição mudar, este script precisa
acompanhar. A diferença: o buscador é envolvido para guardar a busca completa (fusão e
pontuação de todas as seções, sem limiar e sem corte). Depois o limiar e o `top_k` reais são
aplicados com a mesma regra da produção: a resposta e a medição saem da mesma busca.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_PROJETO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_perguntas import PERGUNTAS, Pergunta, ReferenciaTextual  # noqa: E402

import composicao  # noqa: E402
from busca.buscador import BuscadorSemantico  # noqa: E402
from busca.buscador_formulacoes import BuscadorComFormulacoes  # noqa: E402
from busca.cache import RepositorioCacheVetores  # noqa: E402
from busca.indexacao import construir_indice_com_cache, entradas_indexaveis  # noqa: E402
from busca.provedor_openai import ProvedorEmbeddingOpenAI  # noqa: E402
from config import Configuracao, carregar_configuracao  # noqa: E402
from geracao.gerador_openai import GeradorOpenAI  # noqa: E402
from geracao.reescritor_consulta import ReescritorOpenAI  # noqa: E402
from nucleo.assistente import AssistenteRAG  # noqa: E402
from nucleo.contratos import Buscador  # noqa: E402
from nucleo.erros import ErroBusca, ErroGeracao  # noqa: E402
from nucleo.modelos import Secao, Trecho  # noqa: E402


class _BuscadorMedido:
    """Implementa `Buscador`: guarda a busca completa e devolve o que a produção devolveria."""

    def __init__(self, bruto: Buscador, limiar: float, top_k: int) -> None:
        self._bruto = bruto
        self._limiar = limiar
        self._top_k = top_k
        self.busca_completa: tuple[Trecho, ...] = ()
        self.recuperadas: tuple[Trecho, ...] = ()

    def buscar(self, pergunta: str) -> tuple[Trecho, ...]:
        self.busca_completa = self._bruto.buscar(pergunta)
        acima_do_limiar = tuple(t for t in self.busca_completa if t.pontuacao >= self._limiar)
        self.recuperadas = acima_do_limiar[: self._top_k]
        return self.recuperadas


def _montar(configuracao: Configuracao, formulacoes: int) -> tuple[AssistenteRAG, _BuscadorMedido]:
    secoes = composicao.carregar_secoes(
        configuracao.pasta_documentos, configuracao.tamanho_maximo_chunk
    )
    provedor = ProvedorEmbeddingOpenAI(
        modelo=configuracao.modelo_embedding,
        chave=configuracao.chave_openai,
        tamanho_lote=composicao.TAMANHO_LOTE_EMBEDDINGS,
        timeout_segundos=configuracao.timeout_segundos,
    )
    repositorio = RepositorioCacheVetores(composicao.CAMINHO_CACHE_VETORES)
    indice = construir_indice_com_cache(
        secoes,
        provedor,
        modelo=configuracao.modelo_embedding,
        repositorio=repositorio,
        perguntas_faq=True,
    )
    # Limiar 0 e top_k com todas as entradas: a busca devolve tudo, ordenado pela pontuação.
    total_entradas = len(entradas_indexaveis(secoes, perguntas_faq=True))
    semantico = BuscadorSemantico(provedor, indice, limiar_similaridade=0.0, top_k=total_entradas)
    bruto: Buscador = semantico
    if formulacoes > 0:
        reescritor = ReescritorOpenAI(
            chave=configuracao.chave_openai,
            timeout_segundos=configuracao.timeout_segundos,
            numero_formulacoes=formulacoes,
            modelo=configuracao.modelo_geracao,
        )
        bruto = BuscadorComFormulacoes(
            semantico, reescritor, limiar_similaridade=0.0, top_k=total_entradas
        )
    medido = _BuscadorMedido(bruto, configuracao.limiar_similaridade, configuracao.top_k)
    gerador = GeradorOpenAI(
        chave=configuracao.chave_openai,
        timeout_segundos=configuracao.timeout_segundos,
        modelo=configuracao.modelo_geracao,
    )
    return AssistenteRAG(medido, gerador), medido


def _rotulo(secao: Secao) -> str:
    return f"{secao.documento} §{secao.numero}"


def _secao_pertence(numero: str, referencia: str) -> bool:
    """Seção numérica vale com as subseções (`6` cobre `6.1`). FAQ (`faq-5`) só por igualdade."""
    return numero == referencia or numero.startswith(f"{referencia}.")


def _casa(trecho: Trecho, referencia: ReferenciaTextual) -> bool:
    return trecho.secao.documento == referencia.documento and _secao_pertence(
        trecho.secao.numero, referencia.secao
    )


def _melhor_esperada(
    busca: Sequence[Trecho], esperadas: Sequence[ReferenciaTextual]
) -> tuple[str, float] | None:
    candidatos = [
        (_rotulo(trecho.secao), trecho.pontuacao)
        for trecho in busca
        if any(_casa(trecho, referencia) for referencia in esperadas)
    ]
    return max(candidatos, key=lambda candidato: candidato[1], default=None)


def _esperadas_recuperadas(
    recuperadas: Sequence[Trecho], esperadas: Sequence[ReferenciaTextual]
) -> int:
    return sum(
        1 for referencia in esperadas if any(_casa(trecho, referencia) for trecho in recuperadas)
    )


def _pontuacao_por_esperada(busca: Sequence[Trecho], esperadas: Sequence[ReferenciaTextual]) -> str:
    """Melhor pontuação de cada seção esperada na busca completa (ou `ausente`)."""
    partes: list[str] = []
    for referencia in esperadas:
        pontuacoes = [trecho.pontuacao for trecho in busca if _casa(trecho, referencia)]
        rotulo = f"{referencia.documento} §{referencia.secao}"
        partes.append(f"{rotulo}={max(pontuacoes):.3f}" if pontuacoes else f"{rotulo}=ausente")
    return "; ".join(partes)


def _linha(pergunta: Pergunta, assistente: AssistenteRAG, medido: _BuscadorMedido) -> str:
    try:
        resposta = assistente.responder(pergunta.texto)
    except (ErroBusca, ErroGeracao) as erro:
        return f"P{pergunta.numero} | erro: {type(erro).__name__}"
    recuperadas = [_rotulo(trecho.secao) for trecho in medido.recuperadas]
    citadas = [f"{fonte.documento} §{fonte.secao}" for fonte in resposta.fontes]
    recusa = "sim" if not resposta.evidencia_suficiente else "não"
    melhor = _melhor_esperada(medido.busca_completa, pergunta.fontes)
    melhor_texto = (
        "sem seção esperada na busca" if melhor is None else f"{melhor[0]} = {melhor[1]:.3f}"
    )
    contagem = _esperadas_recuperadas(medido.recuperadas, pergunta.fontes)
    por_esperada = _pontuacao_por_esperada(medido.busca_completa, pergunta.fontes)
    return (
        f"P{pergunta.numero} | recuperadas: {recuperadas} | citadas: {citadas} | "
        f"esperadas recuperadas: {contagem}/{len(pergunta.fontes)} | recusa: {recusa} | "
        f"melhor esperada: {melhor_texto} | por esperada: {por_esperada}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede a recuperação com a API real.")
    parser.add_argument("--formulacoes", type=int, required=True, help="N: 0 ou mais")
    parser.add_argument("--execucao", type=int, default=1, help="rótulo da execução")
    args = parser.parse_args()
    if args.formulacoes < 0:
        parser.error("--formulacoes não pode ser negativo")

    configuracao = carregar_configuracao()
    assistente, medido = _montar(configuracao, args.formulacoes)
    print(
        f"## N={args.formulacoes} execucao={args.execucao} "
        f"limiar={configuracao.limiar_similaridade} top_k={configuracao.top_k}"
    )
    for pergunta in PERGUNTAS:
        print(_linha(pergunta, assistente, medido))


if __name__ == "__main__":
    main()
