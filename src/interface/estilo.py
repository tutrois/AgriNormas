"""Estilo visual da tela de perguntas: paleta e CSS (HIST-030).

Tudo fica embutido na página. Não há fonte, imagem, ícone externo ou script de outra origem,
nem `url(` ou `@import` no CSS.

Os mockups aprovados usam ícones da Tabler por CDN. Na máquina do usuário esse CDN não carrega
e os ícones aparecem como quadrados. Por isso esta tela não usa ícone de fonte externa:
- as marcas (barra lateral e avatares) são texto curto ou formas feitas em CSS;
- a seta do botão de envio é ícone nativo do Streamlit, em `app.py`.

Layout (spec. "Navegação da barra lateral"): barra lateral escura de 200 px com marca, "Nova
conversa", "Perguntar", "Base de conhecimento", divisor e "Perguntas recentes", nessa ordem.
A área clara tem cabeçalho discreto, saudação centralizada, o campo de pergunta em cartão branco
e três cartões de sugestão.

A barra tem 200 px só enquanto está aberta (`data-collapsed="false"`). Quando recolhida, o
Streamlit cuida da largura, e a regra fixa não a impede de sumir.

Desvio do mockup: o contorno dos controles é `#8a8a92`, porque o mockup usa `#dcdde0`, abaixo
de 3:1 sobre o fundo claro.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

COR_TINTA: Final[str] = "#0d0d0d"
COR_FUNDO: Final[str] = "#f4f4f5"
COR_BRANCO: Final[str] = "#ffffff"
COR_SECUNDARIA: Final[str] = "#5f5f67"
COR_CONTORNO_CONTROLE: Final[str] = "#8a8a92"
COR_CONTORNO_SUAVE: Final[str] = "#dcdde0"
COR_DESTAQUE: Final[str] = "#d4ff3a"
COR_TEXTO_TRILHO: Final[str] = "#d6d6da"
COR_TEXTO_TRILHO_SUAVE: Final[str] = "#8a8a92"
COR_CAMPO_ESCURO: Final[str] = "#1f1f22"
# Contorno dos controles da barra (botão "Nova conversa"): 3,68:1 sobre o preto.
COR_CONTORNO_TRILHO: Final[str] = "#6b6b73"
# Fundo do controle da barra com o cursor em cima: texto branco continua acima de 4,5:1.
COR_CAMPO_ESCURO_SOBREVOO: Final[str] = "#2a2a2e"
# Sobrevoo de destino inativo na barra: um tom acima do preto. Texto #d6d6da fica em 12:1.
COR_SOBREVOO_TRILHO_SUAVE: Final[str] = "#1a1a1d"
COR_DIVISOR_TRILHO: Final[str] = "#2a2a2e"
LARGURA_BARRA: Final[str] = "200px"
# Altura da barra de topo do Streamlit (`stAppToolbar`, fixa e acima do conteúdo, z-index alto).
ALTURA_BARRA_TOPO: Final[str] = "60px"

# Marca da barra lateral, em texto (a fonte de ícones não é usada).
TEXTO_MARCA: Final[str] = "RH"

_VARIAVEIS_CSS: Final[str] = f"""
.stApp {{
  --agri-tinta: {COR_TINTA};
  --agri-fundo: {COR_FUNDO};
  --agri-branco: {COR_BRANCO};
  --agri-secundaria: {COR_SECUNDARIA};
  --agri-contorno-controle: {COR_CONTORNO_CONTROLE};
  --agri-contorno-suave: {COR_CONTORNO_SUAVE};
  --agri-destaque: {COR_DESTAQUE};
  --agri-texto-trilho: {COR_TEXTO_TRILHO};
  --agri-texto-trilho-suave: {COR_TEXTO_TRILHO_SUAVE};
  --agri-campo-escuro: {COR_CAMPO_ESCURO};
  --agri-contorno-trilho: {COR_CONTORNO_TRILHO};
  --agri-campo-sobrevoo: {COR_CAMPO_ESCURO_SOBREVOO};
  --agri-sobrevoo-suave: {COR_SOBREVOO_TRILHO_SUAVE};
  --agri-divisor: {COR_DIVISOR_TRILHO};
  --agri-barra: {LARGURA_BARRA};
  --agri-barra-topo: {ALTURA_BARRA_TOPO};
}}
"""

# Regras fixas, no arquivo `estilo.css` ao lado. Sem `url(` nem `@import`.
_REGRAS_CSS: Final[str] = (Path(__file__).with_name("estilo.css")).read_text(encoding="utf-8")

CSS_PAGINA: Final[str] = f"<style>{_VARIAVEIS_CSS}{_REGRAS_CSS}</style>"
