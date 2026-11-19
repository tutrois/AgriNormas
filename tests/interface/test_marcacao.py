"""Testes unitários da marcação dos balões (HIST-030), sem Streamlit.

Garantem que todo texto vindo da pergunta ou da resposta sai escapado, e que o selo "Sem
evidência" só aparece quando é pedido.
"""

from __future__ import annotations

from dataclasses import dataclass

from interface.marcacao import (
    ajuda_html,
    balao_assistente_html,
    balao_usuario_html,
    barra_lateral_html,
    base_conhecimento_html,
    boas_vindas_html,
    lista_conversas_html,
    remover_citacoes,
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


def test_remove_varias_citacoes_inclusive_coladas() -> None:
    texto = (
        "Vale para atividade profissional [FIN-POL-001 §1]. Exige nota "
        "[FIN-POL-001 §3.1][FIN-POL-001 §3.2] e prazo [FIN-POL-001 §6]."
    )

    assert remover_citacoes(texto) == ("Vale para atividade profissional. Exige nota e prazo.")


def test_remove_citacao_separada_por_espaco_e_antes_de_pontuacao() -> None:
    assert remover_citacoes("Sim [A-1 §2] [B-2 §3], ok.") == "Sim, ok."
    assert remover_citacoes("Fim [A-1 §2].") == "Fim."
    assert remover_citacoes("Um [A-1 §2]; dois") == "Um; dois"


def test_remove_secao_com_ponto_e_faq() -> None:
    assert remover_citacoes("Regra [FIN-POL-001 §3.1] e [FIN-FAQ-001 §faq-5].") == "Regra e."


def test_citacao_no_meio_deixa_um_unico_espaco() -> None:
    assert remover_citacoes("antes [A-1 §2] depois") == "antes depois"


def test_nao_remove_colchetes_que_nao_sao_citacao() -> None:
    texto = "Veja [anexo] e [1] e [A-1 seção 2] e [§3]."

    assert remover_citacoes(texto) == texto


def test_texto_sem_citacao_fica_igual_e_quebras_de_linha_ficam() -> None:
    assert remover_citacoes("Linha um.\nLinha dois.") == "Linha um.\nLinha dois."
    assert remover_citacoes("a [A-1 §2]\nb") == "a\nb"


def test_texto_so_com_citacao_mantem_o_original() -> None:
    assert remover_citacoes("[FIN-POL-001 §1]") == "[FIN-POL-001 §1]"


def test_chips_tem_rotulo_para_leitor_de_tela() -> None:
    bloco = balao_assistente_html("Assistente", "Texto", chips=["FIN-POL-001 · 1"])

    assert "Fontes:" in bloco
    assert "agri-so-leitor" in bloco.split("agri-chips")[1]


@dataclass(frozen=True)
class _Doc:
    arquivo: str = "Politica_Reembolso.pdf"
    codigo: str = "FIN-POL-001"
    titulo: str = "POLÍTICA DE REEMBOLSO"
    versao: str = "1.0"


def _base(documentos: object) -> str:
    return base_conhecimento_html(documentos, "Base de conhecimento", "Vazia.", "Erro.")  # type: ignore[arg-type]


def test_base_mostra_titulo_em_caixa_de_frase_codigo_versao_e_arquivo() -> None:
    bloco = _base((_Doc(), _Doc(titulo="Procedimento de Férias", versao="")))

    assert "Política de reembolso" in bloco
    assert "<span>FIN-POL-001</span> <span>v1.0</span>" in bloco
    assert "Politica_<wbr>Reembolso.<wbr>pdf" in bloco
    assert "Procedimento de Férias" in bloco
    assert "2 documentos" in bloco
    assert 'aria-labelledby="agri-base-titulo"' in bloco


def test_base_usa_singular_para_um_documento() -> None:
    assert "1 documento<" in _base((_Doc(),))


def test_base_escapa_todo_texto_e_nao_cria_link_nem_imagem() -> None:
    bloco = _base(
        (_Doc(arquivo=CARGA_HOSTIL, codigo=CARGA_HOSTIL, titulo=CARGA_HOSTIL, versao="1"),)
    )

    assert CARGA_ESCAPADA in bloco
    assert "<img" not in bloco
    assert "<a " not in bloco
    assert "<script" not in bloco


def test_base_com_campos_vazios_nao_cria_linhas_vazias() -> None:
    bloco = _base((_Doc(codigo="", versao=""),))

    assert "agri-base-meta" not in bloco
    assert " · " not in bloco


def test_base_vazia_e_com_erro_mostram_so_o_aviso() -> None:
    vazia = _base(())
    erro = _base(None)

    assert "Vazia." in vazia
    assert "<li" not in vazia
    assert "Erro." in erro
    assert "<li" not in erro
    assert "documentos<" not in erro


def test_base_permite_quebra_no_nome_do_arquivo_sem_quebrar_o_escape() -> None:
    bloco = _base((_Doc(arquivo="Pol_<b>&x.pdf"),))

    assert "Pol_<wbr>&lt;b&gt;&amp;x.<wbr>pdf" in bloco
    assert "<b>" not in bloco
    assert 'Pol_&lt;b&gt;&amp;x.pdf"' in bloco  # a dica (title) guarda o nome completo, escapado


def test_base_mantem_codigo_e_versao_em_trechos_que_nao_se_partem() -> None:
    bloco = _base((_Doc(),))

    assert '<span class="agri-base-meta"><span>FIN-POL-001</span> <span>v1.0</span></span>' in bloco
