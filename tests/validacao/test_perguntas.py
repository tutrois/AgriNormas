"""Suíte de validação das perguntas de `perguntas.md`, fonte única das perguntas e das fontes.

Offline (padrão): embeddings de `vetores_gravados.npz` e gerador falso que cita todos os trechos
recuperados. Confere recuperação e validação das fontes, não a redação.
Integração (`pytest -m integracao`): API real. O "Deve conter" só é conferido por inspeção.

As fontes usam `ReferenciaTextual` porque `ReferenciaSecao` só aceita número de seção (mudar o
tipo exige ADR) e `ler_perguntas_validacao` descarta `§faq-N`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import composicao
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
    "LIMIAR_SIMILARIDADE": "0.40",
    "TOP_K": "8",
    "TAMANHO_MAXIMO_CHUNK": "1200",
    "PASTA_DOCUMENTOS": str(PASTA_BASE),
}

COLUNAS_PERGUNTA = 4
PADRAO_DOCUMENTO = re.compile(r"[A-Z]{2,3}-[A-Z]{3}-\d{3}")
PADRAO_SECAO_TABELA = re.compile(r"§(\d+|faq-\d+)(?:\s*a\s*§(\d+))?")
PADRAO_CITACAO_ENTRE_COLCHETES = re.compile(r"\[[^\[\]]*\]")
PADRAO_CODIGO_OU_SECAO = re.compile(r"[A-Z]{2,3}-[A-Z]{3}-\d{3}|§(?:\d+(?:\.\d+)*|faq-\d+)")
PADRAO_VALOR_OU_LIMITE = re.compile(r"\d|R\$|%")


@dataclass(frozen=True)
class ReferenciaTextual:
    """Seção esperada como está na tabela: `6`, `2` ou `faq-5`, com o código do documento."""

    documento: str
    secao: str


@dataclass(frozen=True)
class Pergunta:
    numero: int
    texto: str
    deve_conter: str
    fontes: tuple[ReferenciaTextual, ...]
    """Vazio quando a tabela não lista nenhuma seção de apoio."""


def _numeros_do_intervalo(inicio: str, fim: str | None) -> tuple[str, ...]:
    if fim is None:
        return (inicio,)
    return tuple(str(numero) for numero in range(int(inicio), int(fim) + 1))


def _fontes_da_celula(celula: str) -> tuple[ReferenciaTextual, ...]:
    """Lê células como `FIN-POL-001 §4, §5; FRO-POL-002 §faq-5` e `RH-PRO-003 §2 a §4`.

    Uma parte sem código herda o documento da parte anterior. Texto sem `§` não gera nada
    (ex.: `nenhuma`).
    """
    referencias: list[ReferenciaTextual] = []
    documento = ""
    for parte in celula.split(";"):
        codigo = PADRAO_DOCUMENTO.search(parte)
        if codigo is not None:
            documento = codigo.group(0)
        for casamento in PADRAO_SECAO_TABELA.finditer(parte):
            for secao in _numeros_do_intervalo(casamento.group(1), casamento.group(2)):
                referencias.append(ReferenciaTextual(documento, secao))
    return tuple(referencias)


def _ler_tabela() -> tuple[Pergunta, ...]:
    """Lê as linhas numeradas de `perguntas.md`. Cabeçalho e texto corrido são ignorados."""
    perguntas: list[Pergunta] = []
    for linha in CAMINHO_PERGUNTAS.read_text(encoding="utf-8").splitlines():
        celulas = [celula.strip() for celula in linha.strip().strip("|").split("|")]
        if not celulas[0].isdigit():
            continue
        assert len(celulas) == COLUNAS_PERGUNTA, f"Pergunta {celulas[0]} com colunas inesperadas"
        numero, texto, deve_conter, fontes = celulas
        perguntas.append(Pergunta(int(numero), texto, deve_conter, _fontes_da_celula(fontes)))
    return tuple(perguntas)


PERGUNTAS = _ler_tabela()
PERGUNTAS_COM_FONTES = tuple(p for p in PERGUNTAS if p.fontes)
PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO = tuple(
    p for p in PERGUNTAS if len({r.documento for r in p.fontes}) > 1
)

# Perguntas 6 e 7 tratam do mesmo fato (limite de combustível), mas não têm a mesma exigência.
# Nenhuma das duas recusa: ambas citam FRO-POL-002 §faq-5, dizem que o
# documento não estabelece limite mensal de combustível e não informam valor, número, R$ nem
# percentual. Só a pergunta 6 tem período ("por viagem"), então só ela exige a menção a limite por
# viagem. A pergunta 7 não tem período e não deve exigir essa frase.
NUMEROS_LIMITE_COMBUSTIVEL: tuple[int, ...] = (6, 7)
PERGUNTAS_LIMITE_COMBUSTIVEL = tuple(p for p in PERGUNTAS if p.numero in NUMEROS_LIMITE_COMBUSTIVEL)
NUMEROS_EXIGEM_LIMITE_POR_VIAGEM: tuple[int, ...] = (6,)
PERGUNTAS_EXIGEM_LIMITE_POR_VIAGEM = tuple(
    p for p in PERGUNTAS if p.numero in NUMEROS_EXIGEM_LIMITE_POR_VIAGEM
)

# Casos conhecidos que falham hoje, com o bug registrado no relatório de testes. A marca é
# `xfail(strict=True)`: ela só registra a falha conhecida, não altera o critério. Quando o bug
# for corrigido, a suíte acusa (XPASS), e a marca deve sair.
# Offline a busca usa o piso de cosseno 0,40 e TOP_K 8 (ADR-011): entram as 8 seções mais
# próximas, desde que acima do piso. Medido com `vetores_gravados.npz`, BUG-2 deixou de falhar
# (FIN-POL-001 §4 = 0,568, 5ª posição; §5 = 0,618, 3ª). Continuam fora do top 8, embora acima do
# piso, FIN-POL-001 §4 na pergunta 3 (19ª) e RH-PRO-003 §4 na pergunta 4 (22ª).
# As marcas valem por teste: o mesmo bug pode derrubar a citação da seção sem derrubar o teste
# de dois documentos.
BUGS_OFFLINE_FONTES: dict[int, str] = {
    3: "BUG-1: FIN-POL-001 §4 tem cosseno 0,41 e fica na 19ª posição, fora das 8 mais próximas",
    4: "BUG-3: RH-PRO-003 §4 tem cosseno 0,44 e fica na 22ª posição, fora das 8 mais próximas",
}
# Pergunta 3 passa no teste de dois documentos, mas por FIN-POL-001 §3.1 (0,485, 6ª) e §7
# (0,459, 8ª), não pela §4 esperada. A citação da §4 é cobrada pelo teste de fontes acima.
BUGS_OFFLINE_DOIS_DOCUMENTOS: dict[int, str] = {}
# Na integração valem o mesmo piso 0,40 e TOP_K 8, com o prompt 1.9. Medido em 6 execuções
# (2026-11-19): as três marcas abaixo deram XFAIL nas 6.
BUGS_INTEGRACAO: dict[int, str] = {
    2: (
        "BUG-2: FIN-POL-001 §4 e §5 são recuperadas (5ª e 3ª), mas o modelo cita §4 e §7 e "
        "não cita §5 (6 de 6 execuções com prompt 1.9)"
    ),
    3: "BUG-1: FIN-POL-001 §4 tem cosseno 0,41 e fica na 19ª posição, fora das 8 mais próximas",
    4: "BUG-3: RH-PRO-003 §4 tem cosseno 0,44 e fica na 22ª posição, fora das 8 mais próximas",
}
# BUG-4 (pergunta 7 sem 'mensal') saiu: deu XPASS em 3 de 3 execuções com prompt 1.9 e passou
# nas 3 seguintes. O dicionário fica vazio para registrar uma eventual regressão sem mudar a
# parametrização do teste.
BUGS_INTEGRACAO_LIMITE_MENSAL: dict[int, str] = {}


def _pergunta(numero: int) -> Pergunta:
    (pergunta,) = (p for p in PERGUNTAS if p.numero == numero)
    return pergunta


def _casos(perguntas: Sequence[Pergunta], bugs: dict[int, str]) -> list[Any]:
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


def _secao_pertence(secao: str, referencia: str) -> bool:
    """Seção numérica vale com as subseções (`6` cobre `6.1`). FAQ (`faq-5`) só por igualdade."""
    return secao == referencia or secao.startswith(f"{referencia}.")


def _referencias_faltantes(pergunta: Pergunta, resposta: Resposta) -> list[str]:
    return [
        f"{referencia.documento} §{referencia.secao}"
        for referencia in pergunta.fontes
        if not any(
            fonte.documento == referencia.documento
            and _secao_pertence(fonte.secao, referencia.secao)
            for fonte in resposta.fontes
        )
    ]


def _cita_secao_exata(resposta: Resposta, referencia: ReferenciaTextual) -> bool:
    return any(
        fonte.documento == referencia.documento and fonte.secao == referencia.secao
        for fonte in resposta.fontes
    )


def _documentos(resposta: Resposta) -> set[str]:
    return {fonte.documento for fonte in resposta.fontes}


def _tem_valor_ou_limite(texto: str) -> bool:
    """Procura números, R$ e % fora das citações. Códigos de documento e de seção (`FRO-POL-002`,
    `§faq-5`) não contam como valor."""
    sem_citacoes = PADRAO_CITACAO_ENTRE_COLCHETES.sub("", texto)
    sem_codigos = PADRAO_CODIGO_OU_SECAO.sub("", sem_citacoes)
    return PADRAO_VALOR_OU_LIMITE.search(sem_codigos) is not None


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


def test_tabela_tem_as_sete_perguntas_numeradas_de_um_a_sete() -> None:
    assert [p.numero for p in PERGUNTAS] == [1, 2, 3, 4, 5, 6, 7]


def test_tabela_lista_fonte_em_todas_as_perguntas() -> None:
    assert [p.numero for p in PERGUNTAS if not p.fontes] == []


@pytest.mark.parametrize(
    "pergunta", PERGUNTAS_LIMITE_COMBUSTIVEL, ids=lambda p: f"pergunta-{p.numero}"
)
def test_tabela_limite_de_combustivel_aponta_faq_5_de_fro_pol_002(pergunta: Pergunta) -> None:
    assert pergunta.fontes == (ReferenciaTextual("FRO-POL-002", "faq-5"),)


def test_leitor_de_fontes_aceita_secao_de_faq_como_texto() -> None:
    assert _fontes_da_celula("FRO-POL-002 §faq-5") == (ReferenciaTextual("FRO-POL-002", "faq-5"),)


def test_leitor_de_fontes_expande_intervalo_de_secoes_numericas() -> None:
    assert _fontes_da_celula("RH-PRO-003 §2 a §4") == (
        ReferenciaTextual("RH-PRO-003", "2"),
        ReferenciaTextual("RH-PRO-003", "3"),
        ReferenciaTextual("RH-PRO-003", "4"),
    )


def test_leitor_de_fontes_ignora_celula_sem_secao() -> None:
    assert _fontes_da_celula("nenhuma; não apresentar trecho") == ()


def test_verificacao_de_valor_ignora_codigo_de_documento_e_secao() -> None:
    assert _tem_valor_ou_limite("Consulte FRO-POL-002 §faq-5 para o procedimento.") is False


def test_verificacao_de_valor_detecta_numero_fora_das_citacoes() -> None:
    assert _tem_valor_ou_limite("O limite é de 300 litros.") is True


@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_FONTES, BUGS_OFFLINE_FONTES))
def test_offline_resposta_cita_todas_as_fontes_esperadas(
    pergunta: Pergunta, respostas_offline: dict[int, Resposta]
) -> None:
    faltantes = _referencias_faltantes(pergunta, respostas_offline[pergunta.numero])

    assert faltantes == []


@pytest.mark.parametrize("pergunta", PERGUNTAS_COM_FONTES, ids=lambda p: f"pergunta-{p.numero}")
def test_offline_pergunta_com_fonte_nao_recebe_recusa(
    pergunta: Pergunta, respostas_offline: dict[int, Resposta]
) -> None:
    assert respostas_offline[pergunta.numero].evidencia_suficiente is True


def test_offline_pergunta_1_cita_a_secao_6_exata_de_fin_pol_001(
    respostas_offline: dict[int, Resposta],
) -> None:
    referencia = _pergunta(1).fontes[0]

    assert _cita_secao_exata(respostas_offline[1], referencia)


@pytest.mark.parametrize(
    "pergunta", PERGUNTAS_LIMITE_COMBUSTIVEL, ids=lambda p: f"pergunta-{p.numero}"
)
def test_offline_limite_de_combustivel_cita_o_faq_5_de_fro_pol_002(
    pergunta: Pergunta, respostas_offline: dict[int, Resposta]
) -> None:
    assert _cita_secao_exata(respostas_offline[pergunta.numero], pergunta.fontes[0])


@pytest.mark.parametrize(
    "pergunta", _casos(PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO, BUGS_OFFLINE_DOIS_DOCUMENTOS)
)
def test_offline_pergunta_com_dois_documentos_cita_os_dois(
    pergunta: Pergunta, respostas_offline: dict[int, Resposta]
) -> None:
    documentos_esperados = {r.documento for r in pergunta.fontes}

    assert documentos_esperados <= _documentos(respostas_offline[pergunta.numero])


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_FONTES, BUGS_INTEGRACAO))
def test_integracao_resposta_cita_todas_as_fontes_esperadas(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    faltantes = _referencias_faltantes(pergunta, respostas_integracao[pergunta.numero])

    assert faltantes == []


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", PERGUNTAS_COM_FONTES, ids=lambda p: f"pergunta-{p.numero}")
def test_integracao_pergunta_com_fonte_nao_recebe_recusa(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    assert respostas_integracao[pergunta.numero].evidencia_suficiente is True


@pytest.mark.integracao
def test_integracao_pergunta_1_cita_a_secao_6_exata_de_fin_pol_001(
    respostas_integracao: dict[int, Resposta],
) -> None:
    referencia = _pergunta(1).fontes[0]

    assert _cita_secao_exata(respostas_integracao[1], referencia)


@pytest.mark.integracao
@pytest.mark.parametrize(
    "pergunta", PERGUNTAS_LIMITE_COMBUSTIVEL, ids=lambda p: f"pergunta-{p.numero}"
)
def test_integracao_limite_de_combustivel_cita_o_faq_5_de_fro_pol_002(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    assert _cita_secao_exata(respostas_integracao[pergunta.numero], pergunta.fontes[0])


@pytest.mark.integracao
@pytest.mark.parametrize(
    "pergunta", PERGUNTAS_LIMITE_COMBUSTIVEL, ids=lambda p: f"pergunta-{p.numero}"
)
def test_integracao_limite_de_combustivel_nao_traz_valor_ou_limite(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    texto = respostas_integracao[pergunta.numero].texto

    assert _tem_valor_ou_limite(texto) is False


@pytest.mark.integracao
@pytest.mark.parametrize(
    "pergunta", _casos(PERGUNTAS_LIMITE_COMBUSTIVEL, BUGS_INTEGRACAO_LIMITE_MENSAL)
)
def test_integracao_limite_de_combustivel_menciona_que_nao_ha_limite_mensal(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    texto = respostas_integracao[pergunta.numero].texto

    assert "mensal" in texto.casefold(), "termo 'mensal' ausente da resposta"


@pytest.mark.integracao
@pytest.mark.parametrize(
    "pergunta", PERGUNTAS_EXIGEM_LIMITE_POR_VIAGEM, ids=lambda p: f"pergunta-{p.numero}"
)
def test_integracao_limite_de_combustivel_com_periodo_menciona_que_nao_trata_de_limite_por_viagem(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    texto = respostas_integracao[pergunta.numero].texto

    assert "por viagem" in texto.casefold(), "expressão 'por viagem' ausente da resposta"


@pytest.mark.integracao
@pytest.mark.parametrize("pergunta", _casos(PERGUNTAS_COM_MAIS_DE_UM_DOCUMENTO, BUGS_INTEGRACAO))
def test_integracao_pergunta_com_dois_documentos_cita_os_dois(
    pergunta: Pergunta, respostas_integracao: dict[int, Resposta]
) -> None:
    documentos_esperados = {r.documento for r in pergunta.fontes}

    assert documentos_esperados <= _documentos(respostas_integracao[pergunta.numero])
