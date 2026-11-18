"""Testes da montagem do índice a partir dos chunks (apoio à HIST-011).

Offline: o provedor é falso e conta as chamadas.
"""

from __future__ import annotations

from collections.abc import Sequence

from busca.indexacao import construir_indice, texto_indexavel
from nucleo.modelos import Secao, Vetor


class ProvedorContador:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, ...]] = []

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.chamadas.append(tuple(textos))
        # Vetores ortogonais entre si: a primeira seção é a única com pontuação 1 para (1, 0).
        return tuple(
            tuple(1.0 if posicao == indice else 0.0 for posicao in range(len(textos)))
            for indice in range(len(textos))
        )


def _secao(numero: str, texto: str = "corpo da seção") -> Secao:
    return Secao(documento="FIN-POL-001", numero=numero, titulo=f"Título {numero}", texto=texto)


def test_texto_indexavel_traz_codigo_numero_e_titulo_antes_do_corpo() -> None:
    texto = texto_indexavel(_secao("6.1", "Prazo de cinco dias"))

    assert texto == "FIN-POL-001 §6.1 Título 6.1\nPrazo de cinco dias"


def test_construir_indice_envia_um_pedido_com_um_texto_por_secao() -> None:
    provedor = ProvedorContador()
    secoes = [_secao("1"), _secao("2")]

    indice = construir_indice(secoes, provedor)

    assert provedor.chamadas == [tuple(texto_indexavel(secao) for secao in secoes)]
    assert indice.buscar((1.0, 0.0), 2)[0].secao == secoes[0]


def test_sem_secoes_nao_chama_o_provedor_e_devolve_indice_vazio() -> None:
    provedor = ProvedorContador()

    indice = construir_indice([], provedor)

    assert provedor.chamadas == []
    assert indice.buscar((1.0, 0.0), 1) == ()
