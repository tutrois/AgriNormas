"""Testes do cache de vetores em disco (HIST-012).

Offline: o provedor é falso e conta as chamadas. Todos os arquivos ficam em `tmp_path`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from busca.cache import EntradaCache, RepositorioCacheVetores, hash_texto
from busca.indexacao import (
    MENSAGEM_CACHE_DIMENSAO_DIVERGENTE,
    construir_indice_com_cache,
    texto_indexavel,
)
from nucleo.erros import ErroBusca
from nucleo.modelos import Secao, Vetor

MODELO = "modelo-teste"


class ProvedorContador:
    """Provedor falso: vetor determinístico derivado do texto, e conta cada pedido."""

    def __init__(self) -> None:
        self.textos_enviados: list[tuple[str, ...]] = []

    @property
    def chamadas(self) -> int:
        return len(self.textos_enviados)

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.textos_enviados.append(tuple(textos))
        return tuple(_vetor_do_texto(texto) for texto in textos)


def _vetor_do_texto(texto: str) -> Vetor:
    return tuple(float(byte) + 1.0 for byte in hashlib.sha256(texto.encode()).digest()[:8])


def _secao(documento: str, numero: str, texto: str = "corpo da seção") -> Secao:
    return Secao(documento=documento, numero=numero, titulo=f"Título {numero}", texto=texto)


def _repositorio(tmp_path: Path) -> RepositorioCacheVetores:
    return RepositorioCacheVetores(tmp_path / "dados" / "indice.npz")


def _entrada(texto: str, modelo: str = MODELO) -> EntradaCache:
    return EntradaCache(hash_texto=hash_texto(texto), modelo=modelo, vetor=_vetor_do_texto(texto))


# Hash do texto


def test_hash_texto_e_determinístico_e_hexadecimal_de_64_caracteres() -> None:
    primeiro = hash_texto("Prazo de cinco dias")
    segundo = hash_texto("Prazo de cinco dias")

    assert primeiro == segundo
    assert len(primeiro) == 64
    assert all(caractere in "0123456789abcdef" for caractere in primeiro)


def test_hash_texto_muda_quando_o_texto_muda() -> None:
    assert hash_texto("Prazo de cinco dias") != hash_texto("Prazo de sete dias")


# Leitura e gravação do repositório


def test_arquivo_inexistente_devolve_cache_vazio_sem_criar_arquivo(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)

    assert repositorio.ler(MODELO) == {}
    assert not (tmp_path / "dados").exists()


def test_gravar_e_ler_devolve_os_vetores_do_mesmo_modelo(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    entradas = (_entrada("primeiro"), _entrada("segundo"))

    repositorio.gravar(entradas)
    lidos = repositorio.ler(MODELO)

    assert lidos == {entrada.hash_texto: entrada.vetor for entrada in entradas}


def test_ler_com_outro_modelo_nao_devolve_vetores(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("primeiro"),))

    assert repositorio.ler("outro-modelo") == {}


def test_gravar_sem_entradas_limpa_o_cache_anterior(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("primeiro"),))

    repositorio.gravar(())

    assert repositorio.ler(MODELO) == {}


def test_gravar_nao_deixa_arquivo_temporario(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)

    repositorio.gravar((_entrada("primeiro"),))

    assert sorted(arquivo.name for arquivo in (tmp_path / "dados").iterdir()) == ["indice.npz"]


def test_falha_de_gravacao_nao_levanta_excecao(tmp_path: Path) -> None:
    # Depende do comportamento do SO: um diretório no lugar do arquivo faz o `os.replace`
    # levantar OSError. Esse comportamento é do sistema operacional, não do Python; em outro
    # SO a falha pode ser diferente, e o teste precisaria de outro meio de provocar a falha.
    caminho = tmp_path / "indice.npz"
    caminho.mkdir()
    repositorio = RepositorioCacheVetores(caminho)

    repositorio.gravar((_entrada("primeiro"),))

    assert repositorio.ler(MODELO) == {}


# Arquivo corrompido ou adulterado


def test_arquivo_corrompido_devolve_cache_vazio(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("primeiro"),))
    caminho = tmp_path / "dados" / "indice.npz"
    caminho.write_bytes(b"isto nao e um npz")

    assert repositorio.ler(MODELO) == {}


def test_arquivo_truncado_devolve_cache_vazio(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("primeiro"), _entrada("segundo")))
    caminho = tmp_path / "dados" / "indice.npz"
    caminho.write_bytes(caminho.read_bytes()[:40])

    assert repositorio.ler(MODELO) == {}


def test_arquivo_com_hashes_em_objeto_pickle_devolve_cache_vazio(tmp_path: Path) -> None:
    caminho = tmp_path / "indice.npz"
    with caminho.open("wb") as destino:
        np.savez(
            destino,
            hashes=np.array(["x"], dtype=object),
            modelos=np.array([MODELO], dtype=str),
            vetores=np.array([[1.0, 2.0]]),
        )

    assert RepositorioCacheVetores(caminho).ler(MODELO) == {}


def test_leitura_chama_np_load_com_allow_pickle_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O teste acima sozinho não prova a flag: com `allow_pickle=True` o arquivo também seria
    # recusado, pelo tipo de dado. Por isso a chamada a `np.load` é espionada aqui.
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("primeiro"),))
    carregar_original = np.load
    argumentos_recebidos: list[dict[str, object]] = []

    def espiao_np_load(*args: object, **kwargs: object) -> object:
        argumentos_recebidos.append(kwargs)
        return carregar_original(*args, **kwargs)

    monkeypatch.setattr(np, "load", espiao_np_load)
    repositorio.ler(MODELO)

    assert len(argumentos_recebidos) == 1
    assert argumentos_recebidos[0]["allow_pickle"] is False


def test_arquivo_sem_colunas_obrigatorias_devolve_cache_vazio(tmp_path: Path) -> None:
    caminho = tmp_path / "indice.npz"
    with caminho.open("wb") as destino:
        np.savez(destino, outra_coluna=np.zeros((1, 2)))

    assert RepositorioCacheVetores(caminho).ler(MODELO) == {}


def test_arquivo_com_valor_nao_finito_devolve_cache_vazio(tmp_path: Path) -> None:
    caminho = tmp_path / "indice.npz"
    with caminho.open("wb") as destino:
        np.savez(
            destino,
            hashes=np.array(["x"], dtype=str),
            modelos=np.array([MODELO], dtype=str),
            vetores=np.array([[np.nan, 1.0]]),
        )

    assert RepositorioCacheVetores(caminho).ler(MODELO) == {}


def test_arquivo_com_tamanhos_divergentes_devolve_cache_vazio(tmp_path: Path) -> None:
    caminho = tmp_path / "indice.npz"
    with caminho.open("wb") as destino:
        np.savez(
            destino,
            hashes=np.array(["x", "y"], dtype=str),
            modelos=np.array([MODELO], dtype=str),
            vetores=np.array([[1.0, 2.0]]),
        )

    assert RepositorioCacheVetores(caminho).ler(MODELO) == {}


# Reconstrução do índice com cache (TSK-012.2)


def test_segunda_inicializacao_sem_mudanca_nao_chama_o_provedor(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    secoes = [_secao("FIN-POL-001", "1"), _secao("FIN-POL-001", "2")]
    primeiro = ProvedorContador()
    construir_indice_com_cache(secoes, primeiro, modelo=MODELO, repositorio=repositorio)

    segundo = ProvedorContador()
    indice = construir_indice_com_cache(secoes, segundo, modelo=MODELO, repositorio=repositorio)

    assert primeiro.chamadas == 1
    assert segundo.chamadas == 0
    assert indice.buscar(_vetor_do_texto(texto_indexavel(secoes[1])), 1)[0].secao == secoes[1]


def test_documento_alterado_recalcula_apenas_os_chunks_dele(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1"), _secao("FIN-POL-001", "2")]
    doc_b = [_secao("FRO-POL-002", "1"), _secao("FRO-POL-002", "2")]
    construir_indice_com_cache(
        doc_a + doc_b, ProvedorContador(), modelo=MODELO, repositorio=repositorio
    )

    doc_a_alterado = [_secao("FIN-POL-001", "1", "prazo novo"), doc_a[1]]
    provedor = ProvedorContador()
    construir_indice_com_cache(
        doc_a_alterado + doc_b, provedor, modelo=MODELO, repositorio=repositorio
    )

    assert provedor.textos_enviados == [(texto_indexavel(doc_a_alterado[0]),)]


def test_alteracao_nao_deixa_vetor_antigo_no_indice(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    original = _secao("FIN-POL-001", "1", "prazo de cinco dias")
    construir_indice_com_cache(
        [original], ProvedorContador(), modelo=MODELO, repositorio=repositorio
    )

    alterada = _secao("FIN-POL-001", "1", "prazo de sete dias")
    indice = construir_indice_com_cache(
        [alterada], ProvedorContador(), modelo=MODELO, repositorio=repositorio
    )

    vetor_novo = _vetor_do_texto(texto_indexavel(alterada))
    assert indice.buscar(vetor_novo, 1)[0].pontuacao == pytest.approx(1.0)
    assert repositorio.ler(MODELO) == {hash_texto(texto_indexavel(alterada)): vetor_novo}


def test_modelo_diferente_invalida_o_cache(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    secoes = [_secao("FIN-POL-001", "1"), _secao("FIN-POL-001", "2")]
    construir_indice_com_cache(secoes, ProvedorContador(), modelo=MODELO, repositorio=repositorio)

    provedor = ProvedorContador()
    construir_indice_com_cache(secoes, provedor, modelo="outro-modelo", repositorio=repositorio)

    assert provedor.textos_enviados == [tuple(texto_indexavel(secao) for secao in secoes)]


def test_arquivo_corrompido_recalcula_tudo_sem_excecao(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    secoes = [_secao("FIN-POL-001", "1"), _secao("FIN-POL-001", "2")]
    construir_indice_com_cache(secoes, ProvedorContador(), modelo=MODELO, repositorio=repositorio)
    (tmp_path / "dados" / "indice.npz").write_bytes(b"lixo")

    provedor = ProvedorContador()
    indice = construir_indice_com_cache(secoes, provedor, modelo=MODELO, repositorio=repositorio)

    assert provedor.textos_enviados == [tuple(texto_indexavel(secao) for secao in secoes)]
    assert indice.buscar(_vetor_do_texto(texto_indexavel(secoes[0])), 1)[0].secao == secoes[0]


def test_depois_de_recalcular_o_cache_volta_a_valer(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    secoes = [_secao("FIN-POL-001", "1")]
    (tmp_path / "dados").mkdir()
    (tmp_path / "dados" / "indice.npz").write_bytes(b"lixo")
    construir_indice_com_cache(secoes, ProvedorContador(), modelo=MODELO, repositorio=repositorio)

    provedor = ProvedorContador()
    construir_indice_com_cache(secoes, provedor, modelo=MODELO, repositorio=repositorio)

    assert provedor.chamadas == 0


def test_textos_repetidos_no_mesmo_pedido_sao_enviados_uma_vez(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    secoes = [_secao("FIN-POL-001", "1", "mesmo texto"), _secao("FIN-POL-001", "1", "mesmo texto")]
    provedor = ProvedorContador()

    construir_indice_com_cache(secoes, provedor, modelo=MODELO, repositorio=repositorio)

    assert provedor.textos_enviados == [(texto_indexavel(secoes[0]),)]


def test_sem_secoes_nao_chama_o_provedor_e_grava_cache_vazio(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.gravar((_entrada("antigo"),))
    provedor = ProvedorContador()

    indice = construir_indice_com_cache([], provedor, modelo=MODELO, repositorio=repositorio)

    assert provedor.chamadas == 0
    assert indice.buscar((1.0, 0.0), 1) == ()
    assert repositorio.ler(MODELO) == {}


def test_provedor_com_dimensoes_diferentes_levanta_erro_sem_gravar(tmp_path: Path) -> None:
    class ProvedorDimensoesDiferentes:
        def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
            return tuple(
                (1.0, 2.0) if indice == 0 else (1.0, 2.0, 3.0) for indice in range(len(textos))
            )

    repositorio = _repositorio(tmp_path)

    with pytest.raises(ErroBusca):
        construir_indice_com_cache(
            [_secao("FIN-POL-001", "1"), _secao("FIN-POL-001", "2")],
            ProvedorDimensoesDiferentes(),
            modelo=MODELO,
            repositorio=repositorio,
        )
    assert not (tmp_path / "dados").exists()


def test_provedor_que_devolve_quantidade_errada_levanta_erro_de_busca(tmp_path: Path) -> None:
    class ProvedorIncompleto:
        def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
            return ()

    repositorio = _repositorio(tmp_path)

    with pytest.raises(ErroBusca):
        construir_indice_com_cache(
            [_secao("FIN-POL-001", "1")],
            ProvedorIncompleto(),
            modelo=MODELO,
            repositorio=repositorio,
        )
    assert repositorio.ler(MODELO) == {}


# Dimensão do cache diferente da do provedor (M-29)


class ProvedorComDimensao:
    """Provedor falso que devolve vetores de dimensão escolhida e conta os pedidos."""

    def __init__(self, dimensao: int) -> None:
        self._dimensao = dimensao
        self.textos_enviados: list[tuple[str, ...]] = []

    @property
    def chamadas(self) -> int:
        return len(self.textos_enviados)

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.textos_enviados.append(tuple(textos))
        return tuple(tuple(float(indice + 1) for indice in range(self._dimensao)) for _ in textos)


class ProvedorQueMudaDeDimensaoEntrePedidos:
    """Primeiro pedido devolve dimensão 5; o segundo mistura dimensões 2 e 3."""

    def __init__(self) -> None:
        self.chamadas = 0

    def gerar(self, textos: Sequence[str]) -> tuple[Vetor, ...]:
        self.chamadas += 1
        if self.chamadas == 1:
            return tuple((1.0,) * 5 for _ in textos)
        return tuple((1.0,) * (2 + indice) for indice in range(len(textos)))


def test_documento_novo_com_mesma_dimensao_reaproveita_o_cache(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1")]
    doc_b = [_secao("FRO-POL-002", "1")]
    construir_indice_com_cache(
        doc_a, ProvedorComDimensao(3), modelo=MODELO, repositorio=repositorio
    )
    provedor = ProvedorComDimensao(3)

    indice = construir_indice_com_cache(
        doc_a + doc_b, provedor, modelo=MODELO, repositorio=repositorio
    )

    assert provedor.textos_enviados == [(texto_indexavel(doc_b[0]),)]
    assert len(repositorio.ler(MODELO)) == 2
    assert [trecho.secao for trecho in indice.buscar((1.0, 2.0, 3.0), 2)] == doc_a + doc_b


def test_vetores_novos_de_outra_dimensao_descartam_o_cache_e_regravam(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1")]
    doc_b = [_secao("FRO-POL-002", "1")]
    construir_indice_com_cache(
        doc_a, ProvedorComDimensao(3), modelo=MODELO, repositorio=repositorio
    )
    provedor = ProvedorComDimensao(5)

    indice = construir_indice_com_cache(
        doc_a + doc_b, provedor, modelo=MODELO, repositorio=repositorio
    )

    # Primeiro pedido só com o texto novo; ao ver a dimensão 5, recalcula tudo em outro pedido.
    assert provedor.textos_enviados == [
        (texto_indexavel(doc_b[0]),),
        (texto_indexavel(doc_a[0]), texto_indexavel(doc_b[0])),
    ]
    assert MENSAGEM_CACHE_DIMENSAO_DIVERGENTE in caplog.text
    lidos = repositorio.ler(MODELO)
    assert len(lidos) == 2
    assert {len(vetor) for vetor in lidos.values()} == {5}
    assert sorted(arquivo.name for arquivo in (tmp_path / "dados").iterdir()) == ["indice.npz"]
    assert len(indice.buscar((1.0, 2.0, 3.0, 4.0, 5.0), 2)) == 2


def test_inicializacao_seguinte_ao_recalculo_nao_erra_nem_chama_o_provedor(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1")]
    doc_b = [_secao("FRO-POL-002", "1")]
    construir_indice_com_cache(
        doc_a, ProvedorComDimensao(3), modelo=MODELO, repositorio=repositorio
    )
    construir_indice_com_cache(
        doc_a + doc_b, ProvedorComDimensao(5), modelo=MODELO, repositorio=repositorio
    )
    provedor = ProvedorComDimensao(5)

    indice = construir_indice_com_cache(
        doc_a + doc_b, provedor, modelo=MODELO, repositorio=repositorio
    )

    assert provedor.chamadas == 0
    assert len(indice.buscar((1.0, 2.0, 3.0, 4.0, 5.0), 2)) == 2


def test_recalculo_com_dimensoes_divergentes_levanta_erro_e_preserva_o_cache_antigo(
    tmp_path: Path,
) -> None:
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1")]
    doc_b = [_secao("FRO-POL-002", "1")]
    construir_indice_com_cache(
        doc_a, ProvedorComDimensao(3), modelo=MODELO, repositorio=repositorio
    )

    with pytest.raises(ErroBusca):
        construir_indice_com_cache(
            doc_a + doc_b,
            ProvedorQueMudaDeDimensaoEntrePedidos(),
            modelo=MODELO,
            repositorio=repositorio,
        )

    lidos = repositorio.ler(MODELO)
    assert len(lidos) == 1
    assert {len(vetor) for vetor in lidos.values()} == {3}


def test_sem_textos_novos_cache_de_outra_dimensao_so_falha_na_consulta_m29(tmp_path: Path) -> None:
    # Limitação registrada na M-29: sem vetores novos não há dimensão do provedor para comparar,
    # e a montagem não pode chamar o provedor (critério da HIST-012). O teste fixa o
    # comportamento atual. Se a limitação for fechada, este teste deve mudar junto.
    repositorio = _repositorio(tmp_path)
    doc_a = [_secao("FIN-POL-001", "1")]
    construir_indice_com_cache(
        doc_a, ProvedorComDimensao(3), modelo=MODELO, repositorio=repositorio
    )
    provedor = ProvedorComDimensao(5)

    indice = construir_indice_com_cache(doc_a, provedor, modelo=MODELO, repositorio=repositorio)

    assert provedor.chamadas == 0
    with pytest.raises(ErroBusca):
        indice.buscar((1.0, 2.0, 3.0, 4.0, 5.0), 1)
