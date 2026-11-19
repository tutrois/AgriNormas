"""Testes do estilo da tela de perguntas (HIST-030): recursos externos, cores e contraste.

São testes estáticos: não sobem o Streamlit. Calculam a razão de contraste WCAG 2.x a partir das
constantes de `interface.estilo`, que são as mesmas usadas no CSS da página.
"""

from __future__ import annotations

import re

from interface.estilo import (
    COR_BRANCO,
    COR_CAMPO_ESCURO,
    COR_CAMPO_ESCURO_SOBREVOO,
    COR_CONTORNO_CONTROLE,
    COR_CONTORNO_SUAVE,
    COR_CONTORNO_TRILHO,
    COR_DESTAQUE,
    COR_FUNDO,
    COR_SECUNDARIA,
    COR_TEXTO_TRILHO,
    COR_TEXTO_TRILHO_SUAVE,
    COR_TINTA,
    CSS_PAGINA,
    LARGURA_BARRA,
    TEXTO_MARCA,
)

MINIMO_TEXTO = 4.5
MINIMO_COMPONENTE = 3.0


def _canal_linear(valor: int) -> float:
    c = valor / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminancia(hexa: str) -> float:
    h = hexa.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal_linear(r) + 0.7152 * _canal_linear(g) + 0.0722 * _canal_linear(b)


def _razao(cor_a: str, cor_b: str) -> float:
    claro, escuro = sorted((_luminancia(cor_a), _luminancia(cor_b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def _bloco_da_regra(seletor: str) -> str:
    """Corpo da regra CSS exata `seletor {...}` dentro de `CSS_PAGINA`."""
    corpo = re.search(re.escape(seletor) + r" \{([^}]*)\}", CSS_PAGINA)
    assert corpo is not None, f"regra {seletor} não encontrada"
    return corpo.group(1)


def test_css_da_pagina_nao_tem_url_nem_import_nem_origem_externa() -> None:
    assert CSS_PAGINA.startswith("<style>")
    assert "url(" not in CSS_PAGINA
    assert "@import" not in CSS_PAGINA
    assert "http://" not in CSS_PAGINA
    assert "https://" not in CSS_PAGINA


def test_variaveis_de_cor_do_css_vem_das_constantes_medidas() -> None:
    assert f"--agri-contorno-controle: {COR_CONTORNO_CONTROLE};" in CSS_PAGINA
    assert f"--agri-tinta: {COR_TINTA};" in CSS_PAGINA
    assert f"--agri-destaque: {COR_DESTAQUE};" in CSS_PAGINA


def test_marca_e_texto_curto_e_nao_dependem_de_fonte_de_icones() -> None:
    # Os ícones da Tabler (CDN) e do Material Symbols não carregam em todas as máquinas. A marca
    # é texto curto, e os avatares são formas em CSS: nenhuma fonte de ícones sobra no CSS.
    assert TEXTO_MARCA.strip() == TEXTO_MARCA
    assert 1 <= len(TEXTO_MARCA) <= 2
    assert "Material Symbols" not in CSS_PAGINA
    assert "tabler" not in CSS_PAGINA.lower()
    assert "agri-icone" not in CSS_PAGINA
    assert "<svg" not in CSS_PAGINA


def test_barra_lateral_tem_200_px_e_a_marca_nao_quebra_nem_transborda() -> None:
    # A largura vale só com a barra aberta: o recolhimento do Streamlit continua funcionando.
    regra_largura = _bloco_da_regra('[data-testid="stSidebar"][data-collapsed="false"]')
    assert "width: var(--agri-barra) !important;" in regra_largura
    assert f"--agri-barra: {LARGURA_BARRA};" in CSS_PAGINA
    assert LARGURA_BARRA == "200px"
    # A alça de redimensionar do Streamlit não aparece.
    assert "display: none !important;" in _bloco_da_regra('[data-testid="stSidebarResizeHandle"]')
    regra_marca = _bloco_da_regra(".agri-marca")
    assert "white-space: nowrap" in regra_marca
    assert "font-size: 13px" in regra_marca


def test_cabecalho_da_barra_fica_na_mesma_linha_da_marca_sem_margem_negativa() -> None:
    # Botão de recolher no canto superior direito, 40 px, centro igual ao da marca (40 px).
    cabecalho = _bloco_da_regra(
        '[data-testid="stSidebar"][data-collapsed="false"] [data-testid="stSidebarHeader"]'
    )
    assert "position: absolute;" in cabecalho
    assert "top: 8px;" in cabecalho
    assert "height: 40px;" in cabecalho
    assert _bloco_da_regra(".agri-marca-bloco").count("height: 40px;") == 1
    assert "-60px" not in CSS_PAGINA


def test_divisor_de_redimensionar_e_seu_contenor_nao_ocupam_espaco() -> None:
    # Esconder só a alça deixava 8 px de contêiner e causava rolagem horizontal de 6 px.
    regra = _bloco_da_regra(
        '[data-testid="stSidebar"] > div:has([data-testid="stSidebarResizeHandle"])'
    )
    assert "display: none !important;" in regra


def test_botao_nova_conversa_tem_borda_3_para_1_e_destaque_no_sobrevoo_e_foco() -> None:
    assert _razao(COR_CONTORNO_TRILHO, COR_TINTA) >= MINIMO_COMPONENTE
    assert _razao(COR_BRANCO, COR_CAMPO_ESCURO_SOBREVOO) >= MINIMO_TEXTO
    assert "var(--agri-contorno-trilho)" in _bloco_da_regra(".agri-nova")
    assert "var(--agri-campo-sobrevoo)" in _bloco_da_regra(".agri-nova:hover")
    assert "var(--agri-destaque)" in _bloco_da_regra(".agri-nova:focus-visible")


def test_selo_sem_evidencia_usa_destaque_e_tinta_e_nao_cor_de_erro() -> None:
    regra = _bloco_da_regra(".agri-selo-sem-evidencia")

    assert "var(--agri-destaque)" in regra
    assert "var(--agri-tinta)" in regra
    # Nenhuma cor avermelhada entra no selo: o selo é informativo, não um erro.
    for cor in (COR_DESTAQUE, COR_TINTA):
        r, g, b = (int(cor.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        assert not (r > g + 60 and r > b + 60), f"{cor} é avermelhada"


def test_texto_atende_4_5_para_1_nas_combinacoes_usadas() -> None:
    pares = [
        (COR_TINTA, COR_FUNDO),
        (COR_TINTA, COR_BRANCO),
        (COR_BRANCO, COR_TINTA),
        (COR_SECUNDARIA, COR_FUNDO),
        (COR_SECUNDARIA, COR_BRANCO),
        (COR_TINTA, COR_DESTAQUE),
        # Marca da barra lateral (lima sobre preto) e texto da barra sobre o preto e o campo.
        (COR_DESTAQUE, COR_TINTA),
        (COR_TEXTO_TRILHO, COR_TINTA),
        (COR_TEXTO_TRILHO_SUAVE, COR_TINTA),
        (COR_TEXTO_TRILHO_SUAVE, COR_CAMPO_ESCURO),
    ]
    for texto, fundo in pares:
        assert _razao(texto, fundo) >= MINIMO_TEXTO, f"{texto} sobre {fundo}"


def test_componentes_atendem_3_para_1() -> None:
    pares = [
        # Marca do trilho e inicial do avatar do assistente: 3:1 para não texto, com folga.
        (COR_DESTAQUE, COR_TINTA),
        # Inicial do avatar do usuário (preto sobre lima).
        (COR_TINTA, COR_DESTAQUE),
        # Contorno do campo de pergunta (escuro, na barra lateral) e do campo claro.
        (COR_CONTORNO_CONTROLE, COR_CAMPO_ESCURO),
        (COR_CONTORNO_CONTROLE, COR_TINTA),
        (COR_CONTORNO_CONTROLE, COR_BRANCO),
        # Botão de envio (fundo escuro) sobre a pílula branca.
        (COR_TINTA, COR_BRANCO),
        # Contorno de foco (tinta) sobre o fundo da página.
        (COR_TINTA, COR_FUNDO),
    ]
    for componente, fundo in pares:
        assert _razao(componente, fundo) >= MINIMO_COMPONENTE, f"{componente} sobre {fundo}"


def test_contorno_do_mockup_nao_e_usado_por_ser_abaixo_de_3_para_1() -> None:
    # O mockup usava #dcdde0 no campo (1,36:1). A medição obriga a troca, por isso o teste fixa
    # a razão do contorno suave só como decorativo: ele não pode ser o contorno do campo.
    assert _razao(COR_CONTORNO_SUAVE, COR_BRANCO) < MINIMO_COMPONENTE
    assert COR_CONTORNO_CONTROLE != COR_CONTORNO_SUAVE
    assert f"--agri-contorno-controle: {COR_CONTORNO_CONTROLE};" in CSS_PAGINA


def test_regra_do_campo_de_pergunta_usa_o_contorno_controle() -> None:
    regra = _bloco_da_regra(".st-key-composer")

    assert "var(--agri-contorno-controle)" in regra
    assert "border-radius: 16px" in regra


TAMANHO_MINIMO_ROTULO = 13


def test_nenhum_texto_da_pagina_fica_abaixo_de_13_px() -> None:
    tamanhos = [int(valor) for valor in re.findall(r"font-size:\s*(\d+)px", CSS_PAGINA)]
    assert tamanhos, "nenhum tamanho de fonte encontrado"
    assert min(tamanhos) >= TAMANHO_MINIMO_ROTULO


def test_baloes_e_campo_de_pergunta_tem_15_a_16_px() -> None:
    assert "font-size: 16px" in _bloco_da_regra(".agri-balao")
    assert "font-size: 16px" in _bloco_da_regra(".st-key-composer input")


def test_quadro_centralizado_tem_cantos_arredondados_e_moldura_escura() -> None:
    quadro = _bloco_da_regra('[data-testid="stAppViewContainer"]')
    assert "border-radius: 28px" in quadro
    assert "margin: 0 auto" in quadro
    assert "overflow: hidden" in quadro
    # O fundo em volta do quadro é cinza claro; a moldura do quadro é preta (como na referência).
    assert "background-color: #ececec !important;" in CSS_PAGINA
    assert "background: var(--agri-tinta);" in CSS_PAGINA
    # Em tela estreita o quadro ocupa a tela toda, sem moldura nem cantos.
    assert "inset: 0 !important;" in CSS_PAGINA
    assert "border-radius: 0;" in CSS_PAGINA


def test_botao_de_recolher_da_barra_fica_sempre_visivel() -> None:
    # O Streamlit esconde o botão até o cursor passar sobre a barra; a regra o torna visível.
    assert "visibility: visible !important;" in CSS_PAGINA
    assert '[data-testid="stSidebarCollapseButton"] button' in CSS_PAGINA


def test_altura_da_conversa_vem_do_css_e_nao_da_altura_fixa_do_streamlit() -> None:
    # O autoscroll exige altura fixa no Streamlit; o CSS anula essa altura e a área ocupa o espaço
    # que sobra. A rolagem continua em `overflow-y: auto`.
    assert "height: auto !important;" in CSS_PAGINA
    assert "max-height: none !important;" in CSS_PAGINA
    assert "overflow-y: auto;" in CSS_PAGINA


def test_campo_fica_na_base_so_depois_da_primeira_pergunta() -> None:
    # Só com conversa (balões) o wrapper da entrada vai para a base e fica preso ao fim.
    assert ".st-key-conversa .agri-linha" in CSS_PAGINA
    assert "position: sticky;" in CSS_PAGINA
    assert "margin-top: auto;" in CSS_PAGINA


def test_menu_da_base_e_a_tela_da_base_usam_o_estilo_dos_botoes() -> None:
    # Botões nativos estilizados como itens da barra: foco visível e item ativo destacado.
    assert '.st-key-menu_base [data-testid="stButton"] button:focus-visible' in CSS_PAGINA
    assert 'data-testid="stBaseButton-primary"' in CSS_PAGINA
    grade = _bloco_da_regra(".st-key-grade_base")
    assert "display: grid !important;" in grade
    assert "repeat(auto-fill, minmax(min(240px, 100%), 1fr))" in grade


def test_texto_do_documento_tem_largura_de_leitura_e_16_px() -> None:
    assert "max-width: 70ch;" in _bloco_da_regra(".agri-doc-secao")
    paragrafo = _bloco_da_regra(".agri-doc-secao p")
    assert "font-size: 16px;" in paragrafo
    assert "line-height: 1.65;" in paragrafo


def test_entrada_some_na_tela_da_base_mas_continua_no_dom() -> None:
    assert ":has(.st-key-tela_base) .st-key-entrada" in CSS_PAGINA
    assert "display: none !important;" in CSS_PAGINA


def test_tela_da_base_comeca_abaixo_da_barra_de_topo_do_streamlit() -> None:
    # A barra de topo (60 px, z-index alto) cobre o início da área principal e rouba o clique dos
    # botões de voltar. O recuo vem da variável da barra, menos os 16 px do bloco principal.
    assert "--agri-barra-topo: 60px;" in CSS_PAGINA
    tela = _bloco_da_regra(".st-key-tela_base")
    assert "padding: calc(var(--agri-barra-topo) - 16px) 0 24px;" in tela
