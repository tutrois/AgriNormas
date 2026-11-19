"""Casos de borda da limpeza do texto: entradas vazias, só com cabeçalho ou espaços, fronteira de
largura e finais de linha do Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from documentos.leitor_pdf import LeitorPdf
from documentos.limpeza import LARGURA_LINHA_CHEIA, limpar_paginas, remover_rodape
from nucleo.modelos import Pagina

PASTA_BASE: Final[Path] = Path(__file__).resolve().parents[2] / "base_conhecimento"

CABECALHO_BRUTO: Final[str] = "AGRICOPPEL \x7f MATERIAL FICTÍCIO PARA AVALIAÇÃO TÉCNICA"


def _unir(texto: str) -> str:
    """Texto de uma página só, limpo e com as quebras do layout unidas, como em produção."""
    return "\n".join(par for _, par in limpar_paginas((Pagina(numero=1, texto=texto),)))


def test_texto_so_com_cabecalho_repetido_devolve_vazio() -> None:
    texto = f"{CABECALHO_BRUTO}\n{CABECALHO_BRUTO}\n{CABECALHO_BRUTO}"

    assert _unir(texto) == ""


def test_texto_so_com_espacos_e_quebras_devolve_vazio() -> None:
    assert _unir(" \t \n\n   \n") == ""


def test_rodape_com_espacos_ao_redor_e_removido() -> None:
    assert remover_rodape("   Página 7   \nCorpo") == "Corpo"


def test_linha_com_94_caracteres_termina_o_paragrafo() -> None:
    quase_cheia = "x" * (LARGURA_LINHA_CHEIA - 1)
    texto = f"{quase_cheia}\ncontinua aqui."

    assert _unir(texto) == f"{quase_cheia}\ncontinua aqui."


def test_linha_com_exatamente_95_caracteres_continua_o_paragrafo() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\ncontinua aqui."

    assert _unir(texto) == f"{cheia} continua aqui."


def test_finais_de_linha_do_windows_sao_tratados_como_quebras() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\r\ncontinua aqui.\r\n3.1 Transporte\r\nCorpo."

    assert _unir(texto) == f"{cheia} continua aqui.\n3.1 Transporte\nCorpo."


def test_dois_titulos_seguidos_ficam_em_linhas_proprias() -> None:
    cheia = "x" * LARGURA_LINHA_CHEIA
    texto = f"{cheia}\n3. Despesas\n3.1 Transporte"

    assert _unir(texto).split("\n") == [cheia, "3. Despesas", "3.1 Transporte"]


def test_procedimento_ferias_nao_tem_rodape_de_fim_colado_ao_paragrafo() -> None:
    paginas = LeitorPdf().ler(PASTA_BASE / "Procedimento_Ferias.pdf")

    assert all("Fim do documento" not in texto for _, texto in limpar_paginas(paginas))


def test_pagina_de_rodape_isolada_nao_altera_a_ordem_das_outras() -> None:
    paginas = (
        Pagina(numero=1, texto=f"{CABECALHO_BRUTO}\nPágina 1\n1. Objetivo\nCorpo."),
        Pagina(numero=2, texto=f"{CABECALHO_BRUTO}\nPágina 2\n2. Escopo"),
    )

    assert limpar_paginas(paginas) == (
        (1, "1. Objetivo"),
        (1, "Corpo."),
        (2, "2. Escopo"),
    )
