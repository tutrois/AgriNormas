"""Suíte de validação das seis perguntas de `perguntas.md` (HIST-022).

Fonte única: as perguntas, as fontes esperadas e a frase de recusa vêm de `perguntas.md`.
Nenhum texto de pergunta é copiado para este arquivo.

Dois modos, ambos pela composição real (`montar_assistente_do_ambiente` e `responder`):

- offline (padrão, sem marcador): embeddings de `vetores_gravados.npz`, gravados uma vez por
  `gravar_vetores.py` a partir de uma execução real. Gerador falso determinístico que cita todos
  os trechos recuperados. Não chama a API e não depende do `.env` local.
- integração (`pytest -m integracao`): API real, com a chave e a configuração do `.env`.

Limite do modo offline: o gerador falso não lê o texto, então o teste verifica a recuperação e a
validação das fontes, não a redação. O conteúdo da coluna "Deve conter" só é conferido na
integração, e mesmo assim por inspeção, porque a tabela descreve o conteúdo em paráfrase.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import composicao
from busca.calibracao import PerguntaValidacao, ReferenciaSecao, ler_perguntas_validacao
from nucleo.modelos import Fonte, Resposta, Trecho, Vetor

PASTA_VALIDACAO = Path(__file__).resolve().parent
CAMINHO_PERGUNTAS = PASTA_VALIDACAO / "perguntas.md"
CAMINHO_VETORES = PASTA_VALIDACAO / "vetores_gravados.npz"
PASTA_BASE = PASTA_VALIDACAO.parents[1] / "base_conhecimento"
MODELO_GRAVADO = "text-embedding-3-small"

# O modo offline fixa a configuração: os valores calibrados (ADR-002) e os padrões do projeto.
# O `.env` local não entra aqui, para que o resultado não mude de máquina para máquina.
CONFIGURACAO_OFFLINE = {
    "OPENAI_API_KEY": "chave-ficticia-do-modo-offline",
    "MODELO_EMBEDDING": MODELO_GRAVADO,
    "MODELO_GERACAO": "gpt-4o-mini",
    "LIMIAR_SIMILARIDADE": "0.60",
    "TOP_K": "4",
    "TAMANHO_MAXIMO_CHUNK": "1200",
    "PASTA_DOCUMENTOS": str(PASTA_BASE),
}

PADRAO_VALOR_OU_LIMITE = re.compile(r"\d|R\$|%")
PADRAO_CITACAO_ENTRE_COLCHETES = re.compile(r"\[[^\[\]]*\]")


def _perguntas() -> tuple[PerguntaValidacao, ...]:
    return ler_perguntas_validacao(CAMINHO_PERGUNTAS)


def _coluna_deve_conter() -> dict[int, str]:
    """Lê a terceira coluna de `perguntas.md`, que o parser de produção descarta."""
    colunas: dict[int, str] = {}
    for linha in CAMINHO_PERGUNTAS.read_text(encoding="utf-8").splitlines():
        celulas = [celula.strip() for celula in linha.strip().strip("|").split("|")]
        if len(celulas) == 4 and celulas[0].isdigit():
            colunas[int(celulas[0])] = celulas[2]
    return colunas


PERGUNTAS = _perguntas()
DEVE_CONTER = _coluna_deve_conter()
PERGUNTAS_COM_FONTES = tuple(p for p in PERGUNTAS if p.fontes_esperadas)
PERGUNTAS_SEM_EVIDENCIA = tuple(p for p in PERGUNTAS if not p.fontes_esperadas)
PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO = tuple(
    p for p in PERGUNTAS if len({r.documento for r in p.fontes_esperadas}) > 1
)

# Casos conhecidos que falham hoje, com o bug registrado no relatório da HIST-022. A marca é
# `xfail(strict=True)`: ela só registra a falha conhecida, não altera o critério. Quando o bug
# for corrigido, a suíte acusa (XPASS), e a marca deve sair.
# A pergunta 6 não tem marca: a falha dela é intermitente, e uma marca estrita ficaria instável.
# A busca usa só cosseno: um trecho entra apenas se a similaridade chegar ao limiar 0,60.
# Offline o TOP_K é fixo em 4, então a pergunta 4 também perde RH-PRO-003 §3 por corte de top-k
# (com TOP_K 6, como no `.env`, §3 entra). Na integração só resta o §4 abaixo do limiar.
BUGS_OFFLINE: dict[int, str] = {
    2: "BUG-2: FIN-POL-001 §4 tem cosseno 0,568, abaixo do limiar 0,60, e não é recuperada",
    3: "BUG-1: FIN-POL-001 §4 tem cosseno 0,41, abaixo do limiar 0,60, e não é recuperada",
    4: "BUG-3: RH-PRO-003 §4 tem cosseno 0,44, abaixo do limiar 0,60; §3 cai pelo TOP_K 4 offline",
}
BUGS_INTEGRACAO: dict[int, str] = {
    2: "BUG-2: FIN-POL-001 §4 tem cosseno 0,568, abaixo do limiar 0,60, e não é recuperada",
    3: "BUG-1: FIN-POL-001 §4 tem cosseno 0,41, abaixo do limiar 0,60, e não é recuperada",
    4: "BUG-3: RH-PRO-003 §4 tem cosseno 0,44, abaixo do limiar 0,60, e não é recuperada",
}


def _pergunta(numero: int) -> PerguntaValidacao:
    (pergunta,) = (p for p in PERGUNTAS if p.numero == numero)
    return pergunta


def _casos(perguntas: Sequence[PerguntaValidacao], bugs: dict[int, str]) -> list[Any]:
    return [
        pytest.param(
            pergunta,
            id=f"pergunta-{pergunta.numero}",
            marks=pytest.mark.xfail(strict=True, reason=bugs[pergunta.numero])
            if pergunta.numero in bugs
            else (),
        )
        for pergunta in perguntas
    ]


def _secao_pertence(secao: str, numero: int) -> bool:
    """Vale para a seção e suas subseções, como `ReferenciaSecao.corresponde` (ex.: `6.1` é `6`)."""
    return secao == str(numero) or secao.startswith(f"{numero}.")


def _referencias_faltantes(pergunta: PerguntaValidacao, resposta: Resposta) -> list[str]:
    return [
        f"{referencia.documento} §{referencia.numero_secao}"
        for referencia in pergunta.fontes_esperadas
        if not any(
            fonte.documento == referencia.documento
            and _secao_pertence(fonte.secao, referencia.numero_secao)
            for fonte in resposta.fontes
        )
    ]


def _cita_secao_exata(resposta: Resposta, referencia: ReferenciaSecao) -> bool:
    return any(
        fonte.documento == referencia.documento and fonte.secao == str(referencia.numero_secao)
        for fonte in resposta.fontes
    )


def _documentos(resposta: Resposta) -> set[str]:
    return {fonte.documento for fonte in resposta.fontes}


def _frase_sem_evidencia(pergunta: PerguntaValidacao) -> str:
    return DEVE_CONTER[pergunta.numero]


def _tem_valor_ou_limite(texto: str) -> bool:
    """Procura números, R$ e % fora das citações, que trazem códigos como `FRO-POL-002`."""
    sem_citacoes = PADRAO_CITACAO_ENTRE_COLCHETES.sub("", texto)
    return PADRAO_VALOR_OU_LIMITE.search(sem_citacoes) is not None


class ProvedorGravado:
    """Dublê de `ProvedorEmbedding` com os vetores gravados da execução real. Não usa rede.

    Um texto que não foi gravado falha com a instrução de regravar, em vez de inventar um vetor.
    """

    def __init__(self, **_kwargs: object) -> None:
        arquivo = np.load(CAMINHO_VETORES, allow_pickle=False)
        assert str(arquivo["modelo"]) == MODELO_GRAVADO, "vetores gravados de outro modelo"
        self._vetores = dict(zip(arquivo["chaves"].tolist(), arquivo["vetores"], strict=True))

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        return tuple(self._vetor(texto) for texto in textos)

    def _vetor(self, texto: str) -> Vetor:
        chave = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        if chave not in self._vetores:
            raise AssertionError(
                "Texto sem vetor gravado. Regrave com tests/validacao/gravar_vetores.py "
                "(perguntas.md, base ou modelo mudaram)."
            )
        return tuple(float(valor) for valor in self._vetores[chave])


class GeradorCitaTodosOsTrechos:
    """Gerador falso e determinístico: cita todos os trechos recebidos e não lê o texto."""

    def __init__(self, **_kwargs: object) -> None:
        pass

    def gerar(self, pergunta: str, trechos: Sequence[Trecho]) -> Resposta:
        fontes = tuple(Fonte.de_secao(trecho.secao) for trecho in trechos)
        return Resposta(
            texto="Resposta do gerador falso do modo offline.",
            fontes=fontes,
            evidencia_suficiente=True,
        )


@pytest.fixture(scope="module")
def respostas_offline(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Resposta]:
    cache = tmp_path_factory.mktemp("cache_offline") / "indice.npz"
    with pytest.MonkeyPatch.context() as mp:
        for nome, valor in CONFIGURACAO_OFFLINE.items():
            mp.setenv(nome, valor)
        mp.setattr(composicao, "ProvedorEmbeddingOpenAI", ProvedorGravado)
        mp.setattr(composicao, "GeradorOpenAI", GeradorCitaTodosOsTrechos)
        mp.setattr(composicao, "CAMINHO_CACHE_VETORES", cache)
        assistente = composicao.montar_assistente_do_ambiente()
        return {p.numero: assistente.responder(p.texto) for p in PERGUNTAS}


@pytest.fixture(scope="module")
def respostas_integracao() -> dict[int, Resposta]:
    assistente = composicao.montar_assistente_do_ambiente()
    return {p.numero: assistente.responder(p.texto) for p in PERGUNTAS}


# Tabela


def test_tabela_tem_as_seis_perguntas_numeradas_de_um_a_seis() -> None:
    assert [p.numero for p in PERGUNTAS] == [1, 2, 3, 4, 5, 6]


def test_tabela_tem_recusa_esperada_apenas_na_pergunta_6() -> None:
    assert [p.numero for p in PERGUNTAS_SEM_EVIDENCIA] == [6]


# Offline


@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_FONTES, BUGS_OFFLINE))
def test_offline_resposta_cita_todas_as_fontes_esperadas(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    faltantes = _referencias_faltantes(pergunta, respostas_offline[pergunta.numero])

    assert faltantes == []


def test_offline_pergunta_1_cita_a_secao_6_exata_de_fin_pol_001(
    respostas_offline: dict[int, Resposta],
) -> None:
    referencia = _pergunta(1).fontes_esperadas[0]

    assert _cita_secao_exata(respostas_offline[1], referencia)


@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO, BUGS_OFFLINE))
def test_offline_pergunta_com_dois_documentos_cita_os_dois(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    documentos_esperados = {r.documento for r in pergunta.fontes_esperadas}

    assert documentos_esperados <= _documentos(respostas_offline[pergunta.numero])


@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_offline_pergunta_sem_evidencia_recebe_recusa(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    assert respostas_offline[pergunta.numero].evidencia_suficiente is False


@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_offline_pergunta_sem_evidencia_nao_cita_nenhum_trecho(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    assert respostas_offline[pergunta.numero].fontes == ()


@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_offline_pergunta_sem_evidencia_diz_que_nao_ha_evidencia(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    texto = respostas_offline[pergunta.numero].texto

    assert _frase_sem_evidencia(pergunta).casefold() in texto.casefold()


@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_offline_pergunta_sem_evidencia_nao_traz_valor_ou_limite(
    pergunta: PerguntaValidacao, respostas_offline: dict[int, Resposta]
) -> None:
    texto = respostas_offline[pergunta.numero].texto

    assert _tem_valor_ou_limite(texto) is False


# Integração (API real)


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_FONTES, BUGS_INTEGRACAO))
def test_integracao_resposta_cita_todas_as_fontes_esperadas(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    faltantes = _referencias_faltantes(pergunta, respostas_integracao[pergunta.numero])

    assert faltantes == []


@pytest.mark.integracao
def test_integracao_pergunta_1_cita_a_secao_6_exata_de_fin_pol_001(
    respostas_integracao: dict[int, Resposta],
) -> None:
    referencia = _pergunta(1).fontes_esperadas[0]

    assert _cita_secao_exata(respostas_integracao[1], referencia)


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO, BUGS_INTEGRACAO))
def test_integracao_pergunta_com_dois_documentos_cita_os_dois(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    documentos_esperados = {r.documento for r in pergunta.fontes_esperadas}

    assert documentos_esperados <= _documentos(respostas_integracao[pergunta.numero])


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_integracao_pergunta_sem_evidencia_recebe_recusa(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    assert respostas_integracao[pergunta.numero].evidencia_suficiente is False


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_integracao_pergunta_sem_evidencia_nao_cita_nenhum_trecho(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    assert respostas_integracao[pergunta.numero].fontes == ()


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_integracao_pergunta_sem_evidencia_diz_que_nao_ha_evidencia(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    texto = respostas_integracao[pergunta.numero].texto

    assert _frase_sem_evidencia(pergunta).casefold() in texto.casefold()


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", PERGUNTAS_SEM_EVIDENCIA, ids=lambda p: f"pergunta-{p.numero}")
def test_integracao_pergunta_sem_evidencia_nao_traz_valor_ou_limite(
    pergunta: PerguntaValidacao, respostas_integracao: dict[int, Resposta]
) -> None:
    texto = respostas_integracao[pergunta.numero].texto

    assert _tem_valor_ou_limite(texto) is False
