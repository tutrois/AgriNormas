"""Testes da validação de citações da saída do modelo (HIST-015).

Função pura, sem rede: nenhuma chamada à API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from geracao.prompts import CAMPO_EVIDENCIA, CAMPO_FONTES, CAMPO_RESPOSTA
from geracao.validacao_resposta import (
    MOTIVO_AUSENCIA_SEM_SUSTENTACAO,
    MOTIVO_FONTE_NAO_RECUPERADA,
    MOTIVO_SEM_CITACAO_NO_TEXTO,
    MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA,
    validar_saida,
)
from nucleo.modelos import MENSAGEM_SEM_EVIDENCIA, Fonte, Resposta, Secao, Trecho

TEXTO_RESPOSTA = "O reembolso é pago em até 30 dias após a aprovação. [FIN-POL-001 §6]"
TEXTO_ESTOQUE = "O estoque mínimo é mantido por 60 dias."
TEXTO_REEMBOLSO = "O reembolso é pago em até 30 dias após a aprovação."
FONTE_REEMBOLSO = Fonte(documento="FIN-POL-001", secao="6", titulo="Reembolso")
TEXTO_FAQ_COMBUSTIVEL = (
    "Qual é o limite mensal de combustível por veículo? Este documento não estabelece limite "
    "mensal de combustível. A informação, quando aplicável, deve ser consultada nos controles "
    "ou parâmetros vigentes da área responsável pela frota."
)
TEXTO_FAQ_LIMITES_MONETARIOS = (
    "Existe um limite monetário fixo para alimentação ou hospedagem? Os limites monetários "
    "específicos não são definidos neste documento."
)


def _trecho(documento: str, numero: str, titulo: str = "Título", texto: str = "Texto") -> Trecho:
    secao = Secao(documento=documento, numero=numero, titulo=titulo, texto=texto)
    return Trecho(secao=secao, pontuacao=0.8)


def _trechos_recuperados() -> list[Trecho]:
    return [_trecho("FIN-POL-001", "6", "Reembolso", TEXTO_REEMBOLSO)]


def _saida(
    resposta: Any = TEXTO_RESPOSTA,
    fontes: Any = ("FIN-POL-001 §6",),
    evidencia: Any = True,
) -> str:
    dados = {CAMPO_RESPOSTA: resposta, CAMPO_FONTES: list(fontes), CAMPO_EVIDENCIA: evidencia}
    return json.dumps(dados, ensure_ascii=False)


def _avisos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [registro for registro in caplog.records if registro.levelno >= logging.WARNING]


@pytest.fixture(autouse=True)
def _registrar_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="geracao.validacao_resposta")


def test_json_valido_com_fontes_existentes_devolve_resposta_com_fontes() -> None:
    resposta = validar_saida(_saida(), _trechos_recuperados())

    assert resposta.texto == TEXTO_RESPOSTA
    assert resposta.evidencia_suficiente is True
    assert resposta.fontes == (FONTE_REEMBOLSO,)


def test_fonte_com_espacos_nas_bordas_e_aceita() -> None:
    resposta = validar_saida(_saida(fontes=["  FIN-POL-001 §6  "]), _trechos_recuperados())

    assert resposta.fontes == (FONTE_REEMBOLSO,)


def test_fontes_de_dois_documentos_sao_todas_devolvidas() -> None:
    trechos = [
        _trecho("FIN-POL-001", "6", "Reembolso", TEXTO_REEMBOLSO),
        _trecho("EST-NRM-002", "3.1", "Estoque", TEXTO_ESTOQUE),
    ]
    saida = _saida(fontes=["FIN-POL-001 §6", "EST-NRM-002 §3.1"])

    resposta = validar_saida(saida, trechos)

    assert resposta.fontes == (
        FONTE_REEMBOLSO,
        Fonte(documento="EST-NRM-002", secao="3.1", titulo="Estoque"),
    )


def test_fontes_repetidas_viram_uma_so_fonte_na_ordem_da_primeira_ocorrencia() -> None:
    saida = _saida(fontes=["FIN-POL-001 §6", "FIN-POL-001 §6"])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta.fontes == (FONTE_REEMBOLSO,)


def test_secao_citada_que_nao_foi_recuperada_vira_nao_ha_evidencia(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(fontes=["FIN-POL-001 §7"])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)
    assert "§7" not in caplog.text


def test_documento_citado_que_nao_foi_recuperado_vira_nao_ha_evidencia() -> None:
    saida = _saida(fontes=["EST-NRM-002 §6"])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()


def test_uma_fonte_valida_e_uma_inexistente_recusam_a_resposta_inteira() -> None:
    saida = _saida(fontes=["FIN-POL-001 §6", "FIN-POL-001 §9"])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()


def test_citacao_no_texto_de_fonte_nao_recuperada_vira_nao_ha_evidencia(
    caplog: pytest.LogCaptureFixture,
) -> None:
    texto = "O prazo é de 30 dias. [FIN-POL-001 §6] Também vale [FIN-POL-999 §1]."
    saida = _saida(resposta=texto)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert "FIN-POL-999" not in caplog.text


@pytest.mark.parametrize(
    "saida_malformada",
    [
        "",
        "texto livre sem nenhum JSON",
        '{"resposta": "O prazo é 30 dias.", "fontes_citadas": ["FIN-POL-001 §6"]',
        "[1, 2, 3]",
        '"apenas uma string"',
        "null",
    ],
)
def test_json_malformado_vira_nao_ha_evidencia_e_registra_log_sem_conteudo(
    saida_malformada: str, caplog: pytest.LogCaptureFixture
) -> None:
    resposta = validar_saida(saida_malformada, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)
    conteudo = saida_malformada.strip()
    if conteudo:
        assert conteudo not in caplog.text


@pytest.mark.parametrize("campo", [CAMPO_RESPOSTA, CAMPO_FONTES, CAMPO_EVIDENCIA])
def test_campo_obrigatorio_faltando_vira_nao_ha_evidencia(
    campo: str, caplog: pytest.LogCaptureFixture
) -> None:
    dados = {
        CAMPO_RESPOSTA: TEXTO_RESPOSTA,
        CAMPO_FONTES: ["FIN-POL-001 §6"],
        CAMPO_EVIDENCIA: True,
    }
    del dados[campo]

    resposta = validar_saida(json.dumps(dados), _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        (CAMPO_EVIDENCIA, "true"),
        (CAMPO_EVIDENCIA, 1),
        (CAMPO_FONTES, "FIN-POL-001 §6"),
        (CAMPO_FONTES, [6]),
        (CAMPO_RESPOSTA, ["texto"]),
        (CAMPO_RESPOSTA, None),
    ],
)
def test_campo_com_tipo_errado_vira_nao_ha_evidencia(campo: str, valor: Any) -> None:
    dados: dict[str, Any] = {
        CAMPO_RESPOSTA: TEXTO_RESPOSTA,
        CAMPO_FONTES: ["FIN-POL-001 §6"],
        CAMPO_EVIDENCIA: True,
    }
    dados[campo] = valor

    resposta = validar_saida(json.dumps(dados), _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()


def test_evidencia_falsa_vira_nao_ha_evidencia_mesmo_com_fontes_existentes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(evidencia=False)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert resposta.evidencia_suficiente is False


@pytest.mark.parametrize(
    "texto_de_recusa",
    [
        "Não há evidência nos documentos para responder a esta pergunta.",
        "Nao ha evidencia nos documentos.",
        "NÃO HÁ EVIDÊNCIA.",
        "Não há evidência   nos documentos.",
    ],
)
def test_texto_que_nega_evidencia_com_flag_verdadeira_vira_nao_ha_evidencia(
    texto_de_recusa: str,
) -> None:
    saida = _saida(resposta=texto_de_recusa, fontes=["FIN-POL-001 §6"], evidencia=True)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()


@pytest.mark.parametrize(
    "frase",
    [
        "nao ha evidencia",
        "nao encontrei evidencia",
        "nao existe evidencia",
        "nao foi encontrada evidencia",
        "nao ha informacao",
        "nao encontrei informacao",
        "nao existe informacao",
        "nao foi encontrada informacao",
    ],
)
def test_cada_frase_de_negacao_com_flag_verdadeira_vira_nao_ha_evidencia(
    frase: str, caplog: pytest.LogCaptureFixture
) -> None:
    texto = f"{frase} nos documentos para responder. [FIN-POL-001 §6]"
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §6"], evidencia=True)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA in caplog.text


def test_frase_de_negacao_com_acentos_e_maiusculas_vira_nao_ha_evidencia(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(
        resposta="Não encontrei Evidência nos documentos. [FIN-POL-001 §6]",
        fontes=["FIN-POL-001 §6"],
        evidencia=True,
    )

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA in caplog.text


def test_frase_que_nao_e_recusa_continua_valida() -> None:
    texto = (
        "Não há prazo definido para a revisão, mas o reembolso segue o prazo de 30 dias. "
        "[FIN-POL-001 §6]"
    )
    saida = _saida(resposta=texto)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta.texto == texto
    assert resposta.evidencia_suficiente is True


def test_flag_verdadeira_sem_fontes_vira_nao_ha_evidencia_e_registra_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(fontes=[])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)


def test_texto_vazio_com_flag_verdadeira_vira_nao_ha_evidencia_e_registra_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(resposta="   ")

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)


def test_sem_trechos_recuperados_qualquer_fonte_vira_nao_ha_evidencia() -> None:
    resposta = validar_saida(_saida(), [])

    assert resposta == Resposta.sem_evidencia()


def test_json_muito_aninhado_vira_nao_ha_evidencia_sem_vazar_conteudo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = "[" * 200000

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert _avisos(caplog)
    assert "[[[" not in caplog.text


def test_fontes_da_lista_e_citacoes_do_texto_sao_unidas_sem_repeticao() -> None:
    trechos = [
        _trecho("FIN-POL-001", "6", "Reembolso", TEXTO_REEMBOLSO),
        _trecho("EST-NRM-002", "3.1", "Estoque", TEXTO_ESTOQUE),
    ]
    texto = (
        "O reembolso é pago em até 30 dias [FIN-POL-001 §6]. "
        "O estoque é mantido por 60 dias [EST-NRM-002 §3.1]."
    )
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §6"])

    resposta = validar_saida(saida, trechos)

    assert resposta.fontes == (
        FONTE_REEMBOLSO,
        Fonte(documento="EST-NRM-002", secao="3.1", titulo="Estoque"),
    )


@pytest.mark.parametrize(
    "identificador",
    ["FIN-POL-001  §6", "FIN-POL-001 § 6", "FIN-POL-001  §  6", "  FIN-POL-001\t§6  "],
)
def test_identificador_com_espacos_internos_e_normalizado_na_lista(identificador: str) -> None:
    resposta = validar_saida(_saida(fontes=[identificador]), _trechos_recuperados())

    assert resposta.fontes == (FONTE_REEMBOLSO,)


@pytest.mark.parametrize("identificador", ["FIN-POL-001  §6", "FIN-POL-001 § 6"])
def test_identificador_com_espacos_internos_e_normalizado_no_texto(identificador: str) -> None:
    texto = f"O reembolso é pago em até 30 dias após a aprovação. [{identificador}]"

    resposta = validar_saida(
        _saida(resposta=texto, fontes=["FIN-POL-001 §6"]), _trechos_recuperados()
    )

    assert resposta.texto == texto
    assert resposta.fontes == (FONTE_REEMBOLSO,)


def test_negacao_com_citacao_valida_no_texto_vira_nao_ha_evidencia(
    caplog: pytest.LogCaptureFixture,
) -> None:
    texto = "Não há evidência de prazo para revisão. O reembolso é 30 dias [FIN-POL-001 §6]"
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §6"], evidencia=True)

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert resposta.texto == MENSAGEM_SEM_EVIDENCIA
    assert resposta.evidencia_suficiente is False
    assert MOTIVO_TEXTO_DIZ_SEM_EVIDENCIA in caplog.text
    assert "reembolso" not in caplog.text


def _trechos_faq() -> list[Trecho]:
    return [
        _trecho("FRO-POL-002", "faq-5", "Perguntas frequentes", TEXTO_FAQ_COMBUSTIVEL),
        _trecho("FIN-POL-001", "faq-3", "Perguntas frequentes", TEXTO_FAQ_LIMITES_MONETARIOS),
    ]


# Trava de citação no texto (MOTIVO_SEM_CITACAO_NO_TEXTO).


@pytest.mark.parametrize(
    "texto",
    [
        "O reembolso é pago em até 30 dias após a aprovação.",
        "O reembolso é pago em até 30 dias após a aprovação. FIN-POL-001 §6",
        "O reembolso é pago em até 30 dias após a aprovação (FIN-POL-001 §6).",
        "O documento não estabelece limite mensal de combustível.",
    ],
)
def test_texto_sem_citacao_entre_colchetes_vira_nao_ha_evidencia_mesmo_com_lista_valida(
    texto: str, caplog: pytest.LogCaptureFixture
) -> None:
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §6"])

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_SEM_CITACAO_NO_TEXTO in caplog.text
    assert "reembolso" not in caplog.text


def test_colchetes_sem_simbolo_de_secao_nao_contam_como_citacao(
    caplog: pytest.LogCaptureFixture,
) -> None:
    saida = _saida(resposta="O reembolso é pago em até 30 dias [FIN-POL-001].")

    resposta = validar_saida(saida, _trechos_recuperados())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_SEM_CITACAO_NO_TEXTO in caplog.text


@pytest.mark.parametrize(
    "texto",
    [
        "[FIN-POL-001 §6] O reembolso é pago em até 30 dias após a aprovação.",
        "O reembolso é pago em até 30 dias [FIN-POL-001 §6] após a aprovação.",
        "O reembolso é pago em até 30 dias após a aprovação. [FIN-POL-001 §6]",
    ],
)
def test_texto_com_citacao_entre_colchetes_em_qualquer_posicao_e_aceito(texto: str) -> None:
    resposta = validar_saida(_saida(resposta=texto), _trechos_recuperados())

    assert resposta.evidencia_suficiente is True
    assert resposta.texto == texto
    assert resposta.fontes == (FONTE_REEMBOLSO,)


# Afirmação de ausência sem sustentação (MOTIVO_AUSENCIA_SEM_SUSTENTACAO).


@pytest.mark.parametrize(
    "texto",
    [
        "O documento não estabelece limite mensal de combustível, e o trecho não trata de "
        "limites em outros períodos [FRO-POL-002 §faq-5].",
        "O documento não estabelece limite mensal de combustível e não trata de limite por "
        "viagem [FRO-POL-002 §faq-5]. A informação deve ser consultada na área responsável "
        "pela frota [FRO-POL-002 §faq-5].",
    ],
)
def test_ausencia_do_que_o_trecho_citado_nega_e_aceita(texto: str) -> None:
    saida = _saida(resposta=texto, fontes=["FRO-POL-002 §faq-5"])

    resposta = validar_saida(saida, _trechos_faq())

    assert resposta.evidencia_suficiente is True
    assert resposta.texto == texto
    assert [fonte.secao for fonte in resposta.fontes] == ["faq-5"]


@pytest.mark.parametrize(
    ("texto", "fonte"),
    [
        (
            "O documento não define o horário de funcionamento do refeitório [FIN-POL-001 §faq-3].",
            "FIN-POL-001 §faq-3",
        ),
        (
            "O documento não define a quantidade de dias de licença maternidade, e o trecho "
            "não trata de licença maternidade [FRO-POL-002 §faq-5].",
            "FRO-POL-002 §faq-5",
        ),
        (
            "O documento não estabelece limite de reembolso de combustível por viagem "
            "[FRO-POL-002 §faq-5].",
            "FRO-POL-002 §faq-5",
        ),
    ],
)
def test_ausencia_de_assunto_que_o_trecho_citado_nao_trata_vira_nao_ha_evidencia(
    texto: str, fonte: str, caplog: pytest.LogCaptureFixture
) -> None:
    saida = _saida(resposta=texto, fontes=[fonte])

    resposta = validar_saida(saida, _trechos_faq())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_AUSENCIA_SEM_SUSTENTACAO in caplog.text
    assert "refeit" not in caplog.text
    assert "maternidade" not in caplog.text


def test_ausencia_com_palavras_genericas_e_aceita_quando_o_trecho_nega_o_valor() -> None:
    texto = "O documento não define o valor [FIN-POL-001 §faq-3]."
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §faq-3"])

    resposta = validar_saida(saida, _trechos_faq())

    assert resposta.evidencia_suficiente is True


def test_ausencia_aceita_plural_simples_das_palavras_do_trecho() -> None:
    texto = "A política não estabelece limites monetários [FIN-POL-001 §faq-3]."
    saida = _saida(resposta=texto, fontes=["FIN-POL-001 §faq-3"])

    resposta = validar_saida(saida, _trechos_faq())

    assert resposta.evidencia_suficiente is True


def test_ausencia_aceita_flexao_das_palavras_do_trecho() -> None:
    trechos = [
        _trecho(
            "FIN-POL-001",
            "4",
            "Comprovantes",
            "Despesas sem comprovante fiscal não "
            "serão reembolsadas, salvo autorização formal da diretoria.",
        )
    ]
    texto = (
        "O documento não estabelece reembolso sem comprovante fiscal, salvo autorização da "
        "diretoria [FIN-POL-001 §4]."
    )

    resposta = validar_saida(_saida(resposta=texto, fontes=["FIN-POL-001 §4"]), trechos)

    assert resposta.evidencia_suficiente is True


def test_negacao_que_nao_e_afirmacao_de_ausencia_do_documento_nao_e_conferida() -> None:
    texto = "Multas de trânsito não são elegíveis e o gestor não define exceções [FIN-POL-001 §6]."

    resposta = validar_saida(_saida(resposta=texto), _trechos_recuperados())

    assert resposta.evidencia_suficiente is True


# Radical e conectores da trava de ausência (revisão).


@pytest.mark.parametrize(
    ("palavra_no_trecho", "palavra_na_resposta"),
    [
        ("mensal", "mensais"),
        ("mensais", "mensal"),
        ("viagem", "viagens"),
        ("viagens", "viagem"),
        ("exceção", "exceções"),
        ("exceções", "exceção"),
        ("diário", "diária"),
        ("diária", "diário"),
    ],
)
def test_ausencia_aceita_plural_e_genero_das_palavras_do_trecho(
    palavra_no_trecho: str, palavra_na_resposta: str
) -> None:
    trechos = [
        _trecho(
            "ABC-001",
            "1",
            "Limites",
            f"Este documento não estabelece limite {palavra_no_trecho} para o reembolso.",
        )
    ]
    texto = f"O documento não estabelece limite {palavra_na_resposta} [ABC-001 §1]."

    resposta = validar_saida(_saida(resposta=texto, fontes=["ABC-001 §1"]), trechos)

    assert resposta.evidencia_suficiente is True


def test_limites_mensais_e_aceito_contra_o_trecho_de_limite_mensal() -> None:
    texto = "O documento não estabelece limites mensais de combustível [FRO-POL-002 §faq-5]."

    resposta = validar_saida(_saida(resposta=texto, fontes=["FRO-POL-002 §faq-5"]), _trechos_faq())

    assert resposta.evidencia_suficiente is True


def test_radical_nao_troca_o_periodo_negado_pelo_trecho() -> None:
    texto = "O documento não estabelece limites semanais de combustível [FRO-POL-002 §faq-5]."

    resposta = validar_saida(_saida(resposta=texto, fontes=["FRO-POL-002 §faq-5"]), _trechos_faq())

    assert resposta == Resposta.sem_evidencia()


@pytest.mark.parametrize("conector", ["e", "ou", "nem"])
def test_complemento_depois_de_e_ou_nem_nao_e_conferido(conector: str) -> None:
    texto = (
        f"O documento não estabelece limite mensal de combustível {conector} trata de limite "
        "por viagem [FRO-POL-002 §faq-5]."
    )

    resposta = validar_saida(_saida(resposta=texto, fontes=["FRO-POL-002 §faq-5"]), _trechos_faq())

    assert resposta.evidencia_suficiente is True


@pytest.mark.parametrize(
    "texto",
    [
        "Os documentos não definem o horário do refeitório [FIN-POL-001 §faq-3].",
        "O documento também não estabelece o horário do refeitório [FIN-POL-001 §faq-3].",
        "O documento não estabelece, para o refeitório, horário de funcionamento "
        "[FIN-POL-001 §faq-3].",
    ],
)
def test_ausencia_no_plural_com_tambem_ou_com_aposto_tambem_e_conferida(
    texto: str, caplog: pytest.LogCaptureFixture
) -> None:
    resposta = validar_saida(_saida(resposta=texto, fontes=["FIN-POL-001 §faq-3"]), _trechos_faq())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_AUSENCIA_SEM_SUSTENTACAO in caplog.text


def test_citacao_do_exemplo_ficticio_do_prompt_vira_nao_ha_evidencia(
    caplog: pytest.LogCaptureFixture,
) -> None:
    texto = (
        "O documento não estabelece limite diário de horas extras e não trata de limite por "
        "semana [ABC-001 §faq-2]."
    )

    resposta = validar_saida(_saida(resposta=texto, fontes=["ABC-001 §faq-2"]), _trechos_faq())

    assert resposta == Resposta.sem_evidencia()
    assert MOTIVO_FONTE_NAO_RECUPERADA in caplog.text
