"""Testes unitários da marcação dos balões (HIST-030), sem Streamlit.

Garantem que todo texto vindo da pergunta ou da resposta sai escapado, e que o selo "Sem
evidência" só aparece quando é pedido.
"""

from __future__ import annotations

from interface.marcacao import (
    ajuda_html,
    balao_assistente_html,
    balao_usuario_html,
    barra_lateral_html,
    boas_vindas_html,
    lista_conversas_html,
)

CARGA_HOSTIL = '<img src=x onerror="alert(1)"> & <a href="http://exemplo.invalido">x</a>'
CARGA_ESCAPADA = (
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; "
    "&lt;a href=&quot;http://exemplo.invalido&quot;&gt;x&lt;/a&gt;"
)


def test_balao_usuario_escapa_a_pergunta() -> None:
    bloco = balao_usuario_html("Você", CARGA_HOSTIL)

    assert CARGA_ESCAPADA in bloco
    assert "<img" not in bloco
    assert "<a " not in bloco


def test_balao_assistente_escapa_o_texto_da_resposta() -> None:
    bloco = balao_assistente_html("Assistente", CARGA_HOSTIL)

    assert f'<div class="agrinormas-resposta">{CARGA_ESCAPADA}</div>' in bloco
    assert "<img" not in bloco


def test_balao_assistente_sem_selo_nao_mostra_sem_evidencia() -> None:
    bloco = balao_assistente_html("Assistente", "Resposta.")

    assert "Sem evidência" not in bloco
    assert "agri-selo-sem-evidencia" not in bloco


def test_balao_assistente_com_selo_mostra_o_selo_em_texto() -> None:
    bloco = balao_assistente_html("Assistente", "Não há evidência.", "Sem evidência")

    assert '<span class="agri-selo-sem-evidencia">Sem evidência</span>' in bloco
    assert bloco.index("agri-selo-sem-evidencia") < bloco.index("agrinormas-resposta")


def test_rotulos_de_autor_ficam_so_para_leitor_de_tela() -> None:
    usuario = '<span class="agri-autor agri-so-leitor">Você</span>'
    assistente = '<span class="agri-autor agri-so-leitor">Assistente</span>'
    assert usuario in balao_usuario_html("Você", "oi")
    assert assistente in balao_assistente_html("Assistente", "oi")


def test_avatares_dos_baloes_sao_formas_ocultas_para_leitores() -> None:
    usuario = balao_usuario_html("Você", "oi")
    assistente = balao_assistente_html("Assistente", "oi")

    assert '<span class="agri-avatar agri-avatar-usuario" aria-hidden="true"></span>' in usuario
    assert '<span class="agri-avatar agri-avatar-assistente" aria-hidden="true"></span>' in (
        assistente
    )
    assert "agri-icone" not in usuario + assistente


def test_fontes_aparecem_como_chips_dentro_do_balao_escapadas() -> None:
    bloco = balao_assistente_html("Assistente", "Resposta.", chips=("FIN-POL-001 · Seção 6", "<b>"))

    assert '<span class="agri-chip">FIN-POL-001 · Seção 6</span>' in bloco
    assert '<span class="agri-chip">&lt;b&gt;</span>' in bloco
    assert bloco.index("agri-chips") > bloco.index("agrinormas-resposta")


def test_balao_sem_fontes_nao_cria_lista_de_chips() -> None:
    assert "agri-chips" not in balao_assistente_html("Assistente", "oi")


def test_titulo_e_boas_vindas_escapam_o_texto() -> None:
    boas_vindas = boas_vindas_html("<b>t</b>", "<i>s</i>")
    assert "&lt;b&gt;t&lt;/b&gt;" in boas_vindas
    assert "&lt;i&gt;s&lt;/i&gt;" in boas_vindas


def test_barra_lateral_mostra_marca_e_nova_conversa_sem_ocultar_o_link() -> None:
    bloco = barra_lateral_html()

    assert '<span class="agri-marca" aria-hidden="true">RH</span>' in bloco
    assert '<a class="agri-nova" href="./">Nova conversa</a>' in bloco
    # O link é uma ação real: não pode ficar oculto para leitores de tela.
    assert "aria-hidden" not in bloco.split("agri-nova", 1)[1]


def test_lista_hoje_mostra_as_perguntas_da_mais_recente_para_a_mais_antiga() -> None:
    bloco = lista_conversas_html(["primeira", "segunda"], "Hoje")

    assert bloco.index("segunda") < bloco.index("primeira")
    assert 'class="agri-item-conversa agri-item-conversa-atual"' in bloco


def test_lista_hoje_escapa_e_corta_perguntas_longas() -> None:
    bloco = lista_conversas_html(["<b>" + "x" * 80], "Hoje")

    assert "&lt;b&gt;" in bloco
    assert "…" in bloco
    assert "<b>" not in bloco


def test_lista_hoje_vazia_nao_mostra_nada() -> None:
    assert lista_conversas_html([], "Hoje") == ""


def test_ajuda_do_campo_escapa_o_texto() -> None:
    bloco = ajuda_html("<b>ajuda</b>")

    assert bloco == '<p class="agri-ajuda">&lt;b&gt;ajuda&lt;/b&gt;</p>'
