"""Testes unitários da marcação dos balões (HIST-030), sem Streamlit.

Garantem que todo texto vindo da pergunta ou da resposta sai escapado, e que o selo "Sem
evidência" só aparece quando é pedido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interface.marcacao import (
    ajuda_html,
    aviso_base_html,
    balao_assistente_html,
    balao_usuario_html,
    barra_lateral_html,
    boas_vindas_html,
    cabecalho_da_base_html,
    contagem_de_documentos,
    contagem_de_secoes,
    documento_html,
    meta_do_documento,
    remover_citacoes,
    resumir,
    rotulo_lista_html,
    titulo_legivel,
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


def test_resumir_corta_perguntas_longas_com_reticencias() -> None:
    assert resumir("a" * 80).endswith("…")
    assert len(resumir("a" * 80)) == 40
    assert resumir("  curta \n pergunta ") == "curta pergunta"


def test_rotulo_da_lista_escapa_o_texto() -> None:
    assert rotulo_lista_html("<b>x</b>") == '<p class="agri-lista-rotulo">&lt;b&gt;x&lt;/b&gt;</p>'


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
class _Secao:
    numero: str = "1"
    titulo: str = "Objetivo"
    texto: str = "Texto da seção."
    tipo: str = "norma"


@dataclass(frozen=True)
class _Conteudo:
    arquivo: str = "Politica_Reembolso.pdf"
    codigo: str = "FIN-POL-001"
    titulo: str = "POLÍTICA DE REEMBOLSO"
    versao: str = "1.0"
    secoes: tuple[_Secao, ...] = (_Secao(),)


def _doc(conteudo: _Conteudo) -> str:
    return documento_html(conteudo, "Seções", "Pergunta frequente", "Sem seções.")


def test_titulo_legivel_passa_caixa_alta_para_caixa_de_frase() -> None:
    assert titulo_legivel("POLÍTICA DE REEMBOLSO") == "Política de reembolso"
    assert titulo_legivel("Procedimento de RH") == "Procedimento de RH"


def test_meta_do_documento_junta_codigo_e_versao() -> None:
    assert meta_do_documento("FIN-POL-001", "1.0") == "FIN-POL-001 · v1.0"
    assert meta_do_documento("FIN-POL-001", "") == "FIN-POL-001"
    assert meta_do_documento("", "") == ""


def test_contagens_usam_singular_e_plural() -> None:
    assert contagem_de_documentos(1) == "1 documento"
    assert contagem_de_documentos(3) == "3 documentos"
    assert contagem_de_secoes(1) == "1 seção"
    assert contagem_de_secoes(12) == "12 seções"


def test_aviso_e_cabecalho_da_base_escapam_o_texto() -> None:
    assert aviso_base_html("<i>x</i>") == '<p class="agri-base-aviso">&lt;i&gt;x&lt;/i&gt;</p>'
    assert "&lt;b&gt;" in cabecalho_da_base_html("<b>", "<b>")


def test_documento_mostra_cabecalho_e_secoes_em_ordem() -> None:
    conteudo = _Conteudo(
        secoes=(_Secao("1", "Objetivo", "Primeiro."), _Secao("2.1", "Prazo", "Segundo."))
    )

    bloco = _doc(conteudo)

    assert "<h2>Política de reembolso</h2>" in bloco
    assert "FIN-POL-001 · v1.0" in bloco
    assert "Politica_Reembolso.pdf" in bloco
    assert "<h3>1 Objetivo</h3>" in bloco
    assert "<h3>2.1 Prazo</h3>" in bloco
    assert bloco.index("Primeiro.") < bloco.index("Segundo.")
    assert 'id="agri-sec-0"' in bloco
    assert 'href="#agri-sec-1"' in bloco


def test_documento_faq_fica_em_bloco_distinto_com_rotulo() -> None:
    bloco = _doc(_Conteudo(secoes=(_Secao("faq-1", "Como pedir?", "Assim.", "faq"),)))

    assert "agri-doc-faq" in bloco
    assert ">Pergunta frequente<" in bloco
    assert "agri-doc-faq" not in _doc(_Conteudo())


def test_documento_preserva_paragrafos_e_quebras_de_linha() -> None:
    bloco = _doc(_Conteudo(secoes=(_Secao(texto="Linha 1\nLinha 2\n\nOutro parágrafo"),)))

    assert "<p>Linha 1<br>Linha 2</p>" in bloco
    assert "<p>Outro parágrafo</p>" in bloco


def test_documento_escapa_todo_texto_e_so_cria_os_links_do_indice() -> None:
    hostil = _Conteudo(
        arquivo=CARGA_HOSTIL,
        codigo=CARGA_HOSTIL,
        titulo=CARGA_HOSTIL,
        versao=CARGA_HOSTIL,
        secoes=(
            _Secao(CARGA_HOSTIL, CARGA_HOSTIL, CARGA_HOSTIL + "\n[a](http://x.invalido)", "faq"),
        ),
    )

    bloco = _doc(hostil)

    assert CARGA_ESCAPADA in bloco
    assert "<img" not in bloco
    assert "<script" not in bloco
    assert "onerror=&quot;" in bloco  # só como texto escapado
    assert "http://exemplo.invalido" not in re.sub(r"&lt;.*?&gt;", "", bloco)
    # os únicos `<a>` são os do índice, com destino gerado pela página
    assert re.findall(r"<a [^>]*>", bloco) == ['<a href="#agri-sec-0">']


def test_documento_sem_secoes_mostra_aviso() -> None:
    bloco = _doc(_Conteudo(secoes=()))

    assert "Sem seções." in bloco
    assert "<h3" not in bloco


def test_documento_com_campos_vazios_nao_cria_linhas_vazias() -> None:
    bloco = _doc(_Conteudo(codigo="", versao="", secoes=(_Secao("", "", "Só texto."),)))

    assert "agri-doc-meta" not in bloco
    assert "<h3" not in bloco
    assert "Só texto." in bloco
