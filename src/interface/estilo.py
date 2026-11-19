"""Estilo visual da tela de perguntas: paleta e CSS (HIST-030).

Tudo fica embutido na página. Não há fonte, imagem, ícone externo ou script de outra origem,
nem `url(` ou `@import` no CSS.

Os mockups aprovados usam ícones da Tabler por CDN. Na máquina do usuário esse CDN não carrega
e os ícones aparecem como quadrados. Por isso esta tela não usa ícone de fonte externa:
- as marcas (barra lateral e avatares) são texto curto ou formas feitas em CSS;
- a seta do botão de envio é ícone nativo do Streamlit, em `app.py`.

Layout (referência aprovada pelo coordenador): barra lateral escura de 200 px com marca,
"Nova conversa" e "Recentes". A área clara tem cabeçalho discreto, saudação
centralizada, o campo de pergunta em cartão branco e três cartões de sugestão.

A barra tem 200 px só enquanto está aberta (`data-collapsed="false"`). Quando recolhida, o
Streamlit cuida da largura, e a regra fixa não a impede de sumir.

Desvio do mockup: o contorno dos controles é `#8a8a92`, porque o mockup usa `#dcdde0`, abaixo
de 3:1 sobre o fundo claro.
"""

from __future__ import annotations

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
LARGURA_BARRA: Final[str] = "200px"

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
  --agri-barra: {LARGURA_BARRA};
}}
"""

# Regras fixas. Sem `url(` nem `@import`. Só cores das variáveis acima.
_REGRAS_CSS: Final[str] = """
/* Fundo em volta do quadro. O quadro (`stAppViewContainer`) é que tem a cor clara. */
.stApp {
  background-color: #ececec !important;
  color: var(--agri-tinta);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
}
/* O cabeçalho do Streamlit é fixo no topo. Transparente, não cobre o título da página. */
[data-testid="stHeader"] {
  background: transparent !important;
}
[data-testid="stMainBlockContainer"] {
  max-width: 760px;
  padding-top: 16px;
  padding-bottom: 24px;
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {
    padding-left: 16px;
    padding-right: 16px;
  }
}
/* Quadro centralizado, com cantos arredondados. A barra e a área clara ficam dentro dele. */
[data-testid="stAppViewContainer"] {
  inset: 48px 32px !important;
  max-width: 1200px;
  margin: 0 auto;
  border-radius: 28px;
  padding: 10px;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--agri-tinta);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18), 0 2px 8px rgba(0, 0, 0, 0.10);
}
/* Área da conversa: cartão claro e arredondado dentro da moldura preta, como na referência. */
/* O conteúdo do quadro cabe na moldura, sem estourar a base.
   A conversa rola por dentro do cartão. */
[data-testid="stAppViewContainer"] > div {
  height: 100% !important;
  max-height: 100%;
  box-sizing: border-box;
}
[data-testid="stMain"] {
  height: 100%;
  max-height: 100%;
  box-sizing: border-box;
  margin: 0 10px 0 0;
  border: none;
  border-radius: 20px;
  background: var(--agri-fundo);
  overflow: hidden;
}
[data-testid="stAppDeployButton"] {
  display: none;
}
.agri-so-leitor {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* Barra lateral: 200 px reais, sem alça de redimensionar e sem rolagem horizontal. */
[data-testid="stSidebar"][data-collapsed="false"] {
  width: var(--agri-barra) !important;
  min-width: var(--agri-barra) !important;
  max-width: var(--agri-barra) !important;
  background: var(--agri-tinta) !important;
  overflow-x: hidden;
  color: var(--agri-texto-trilho);
}
[data-testid="stSidebarResizeHandle"] {
  display: none !important;
}
/* O Streamlit põe a alça dentro de um contêiner de 8 px ao lado da barra. Esconder só a alça
   deixa esse contêiner ocupando espaço e cria rolagem horizontal, então o contêiner também some. */
[data-testid="stSidebar"] > div:has([data-testid="stSidebarResizeHandle"]) {
  display: none !important;
}
[data-testid="stSidebarContent"] {
  display: flex;
  flex-direction: column;
  width: 100% !important;
  height: 100%;
  padding: 0 !important;
  margin: 0 !important;
  box-sizing: border-box;
  overflow-x: hidden;
  background: var(--agri-tinta) !important;
}
/* Conteúdo da barra: começa no topo, logo abaixo da margem de 8 px. A marca e o botão de
   recolher dividem essa primeira linha de 40 px. */
[data-testid="stSidebarUserContent"] {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  padding: 8px 12px 16px;
}
/* O cabeçalho (botão de recolher) sai do fluxo e fica no canto superior direito, na mesma linha
   da marca: 40 px de altura, centro no mesmo ponto. A marca reserva 48 px à direita. */
[data-testid="stSidebar"][data-collapsed="false"] [data-testid="stSidebarContent"] {
  position: relative;
}
[data-testid="stSidebar"][data-collapsed="false"] [data-testid="stSidebarHeader"] {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  width: 40px;
  height: 40px;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* Os contêineres do Streamlit entre a raiz e o conteúdo ocupam a altura da barra. */
[data-testid="stSidebarUserContent"] > div,
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  box-sizing: border-box;
}
/* O botão de recolher tem visibilidade escondida até o cursor passar sobre a barra. Aqui ele
   fica sempre visível, sobre a barra escura. */
[data-testid="stSidebarHeader"],
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button {
  visibility: visible !important;
  opacity: 1 !important;
}
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarHeader"] button *,
[data-testid="stSidebarCollapseButton"] button * {
  color: var(--agri-texto-trilho) !important;
}
/* Botão que abre a barra quando ela está recolhida: fica sobre o fundo claro da página. */
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] span {
  color: var(--agri-tinta) !important;
}
/* Marca: a mesma altura do botão de recolher (40 px). O recuo à direita evita o botão. */
.agri-marca-bloco {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  margin: 0 0 12px;
  padding: 0 48px 0 0;
  font-size: 16px;
  font-weight: 500;
  color: #ffffff;
  white-space: nowrap;
}
.agri-marca {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--agri-destaque);
  color: var(--agri-tinta);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}
/* Ação "Nova conversa": borda sutil (contraste 3:1 sobre o preto), destaque no sobrevoo e no foco.
   O foco usa contorno lima de 2 px, que não depende só de cor. Ocupa a largura da barra. */
.agri-nova {
  display: flex;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border-radius: 8px;
  background: var(--agri-campo-escuro);
  border: 1px solid var(--agri-contorno-trilho);
  color: #ffffff;
  font-size: 14px;
  text-decoration: none;
}
.agri-nova:hover {
  background: var(--agri-campo-sobrevoo);
  border-color: var(--agri-destaque);
}
.agri-nova:focus-visible {
  outline: 2px solid var(--agri-destaque);
  outline-offset: 2px;
}
/* Rótulo "Recentes": cinza pequeno. O texto dos itens fica recuado do mesmo jeito. */
.agri-lista-rotulo {
  margin: 0 0 6px;
  padding: 0 10px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--agri-texto-trilho-suave);
}
.agri-item-conversa {
  box-sizing: border-box;
  width: 100%;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.4;
  color: var(--agri-texto-trilho);
  overflow-wrap: anywhere;
}
.agri-item-conversa + .agri-item-conversa {
  margin-top: 4px;
}
/* Pergunta mais recente: a única destacada. Não é link (a sessão não guarda conversas). */
.agri-item-conversa-atual {
  background: var(--agri-campo-escuro);
  color: #ffffff;
}
/* A ajuda tem a mesma largura da caixa de pergunta, centralizada abaixo dela. */
.st-key-ajuda {
  box-sizing: border-box;
  width: 100%;
  max-width: 640px;
  margin: 0 auto;
}
.st-key-ajuda > div,
.st-key-ajuda [data-testid="stHtml"] {
  width: 100%;
}
/* Só a conversa rola: a página não tem rolagem. O campo e os cartões ficam fixos, e a área dos
   balões ocupa o espaço que sobra. */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
}
[data-testid="stLayoutWrapper"]:has(> .st-key-conversa) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
/* A altura da conversa vem do flex (ocupa o que sobra), e não da altura fixa que o Streamlit põe
   inline para ligar a rolagem automática (`autoscroll` em `app.py`). */
.st-key-conversa {
  flex: 1 1 auto;
  height: auto !important;
  max-height: none !important;
  min-height: 0;
  width: 100%;
  overflow-y: auto;
}
/* Cartões numa linha só, com a mesma largura. */
.st-key-sugestoes {
  flex-wrap: nowrap !important;
  gap: 8px !important;
}
.st-key-sugestoes > [data-testid="stElementContainer"] {
  flex: 1 1 0;
  min-width: 0;
}
.agri-rotulo-sugestoes {
  font-size: 15px !important;
  font-weight: 600 !important;
  color: var(--agri-tinta) !important;
  margin: 0 0 10px !important;
}
/* Bloco dos cartões: mesma largura e centro da caixa de pergunta. O rótulo fica alinhado à
   esquerda, junto dos cartões. */
.st-key-bloco_sugestoes {
  box-sizing: border-box;
  width: 100%;
  max-width: 600px;
  margin: 0 auto;
  gap: 0 !important;
}
.st-key-bloco_sugestoes > [data-testid="stElementContainer"] {
  margin-bottom: 0 !important;
}
.st-key-bloco_sugestoes .agri-rotulo-sugestoes {
  margin: 0 0 4px !important;
}
.agri-rotulo-sugestoes {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--agri-secundaria);
}
.agri-ajuda {
  box-sizing: border-box;
  display: block;
  width: 100%;
  margin: 8px 0 0;
  padding: 0 6px;
  font-size: 13px;
  line-height: 1.4;
  text-align: center;
  color: var(--agri-secundaria);
}

/* Cabeçalho discreto da conversa: título à esquerda */
.agri-topo {
  padding: 8px 0 8px;
  color: var(--agri-tinta);
}
.agri-topo h1 {
  margin: 0;
  font-size: 16px;
  line-height: 1.3;
  font-weight: 500;
  color: var(--agri-tinta);
}

/* Estado inicial: saudação centralizada, como na referência */
.agri-boas-vindas {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 40px !important;
  padding: 25vh 8px 24px;
  text-align: center;
}
.agri-boas-vindas h2 {
  margin: 0;
  font-size: 28px;
  line-height: 1.25;
  font-weight: 500;
  color: var(--agri-tinta);
}
.agri-boas-vindas p {
  margin: 0;
  font-size: 16px;
  line-height: 1.5;
  color: var(--agri-secundaria);
}
@media (min-width: 641px) {
  .agri-boas-vindas h2 {
    font-size: 32px;
  }
}

/* Balões: usuário em preto à direita, assistente em branco à esquerda */
.agri-linha {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin: 0 0 12px;
}
.agri-linha-usuario {
  justify-content: flex-end;
}
.agri-coluna {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  max-width: 76%;
}
.agri-linha-usuario .agri-coluna {
  align-items: flex-end;
}
.agri-linha-assistente .agri-coluna {
  align-items: flex-start;
}
.agri-balao {
  min-width: 0;
  max-width: 100%;
  padding: 9px 13px;
  font-size: 16px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.agri-balao-usuario {
  background: var(--agri-tinta);
  color: var(--agri-branco);
  border-radius: 16px 16px 4px 16px;
}
.agri-balao-assistente {
  background: var(--agri-branco);
  color: var(--agri-tinta);
  border: 1px solid var(--agri-contorno-suave);
  border-radius: 16px 16px 16px 4px;
}
.agri-selo-sem-evidencia {
  display: inline-block;
  margin-bottom: 4px;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--agri-destaque);
  color: var(--agri-tinta);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
}
.agri-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.agri-chip {
  padding: 2px 7px;
  border-radius: 6px;
  background: var(--agri-destaque);
  color: var(--agri-tinta);
  font-size: 13px;
  line-height: 1.5;
}
.agrinormas-resposta {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* Avatares: formas em CSS, sem fonte de ícones. A cor da forma vem de `color`. */
.agri-avatar {
  position: relative;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  overflow: hidden;
}
.agri-avatar-usuario {
  background: var(--agri-destaque);
  color: var(--agri-tinta);
}
.agri-avatar-usuario::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: currentColor;
}
.agri-avatar-usuario::after {
  content: "";
  position: absolute;
  left: 6px;
  top: 18px;
  width: 18px;
  height: 14px;
  border-radius: 9px 9px 0 0;
  background: currentColor;
}
.agri-avatar-assistente {
  background: var(--agri-tinta);
  color: var(--agri-destaque);
}
.agri-avatar-assistente::before {
  content: "";
  position: absolute;
  left: 7px;
  top: 9px;
  width: 16px;
  height: 13px;
  border-radius: 4px;
  background:
    radial-gradient(circle at 5px 6px, var(--agri-tinta) 1.6px, transparent 2px),
    radial-gradient(circle at 11px 6px, var(--agri-tinta) 1.6px, transparent 2px),
    currentColor;
}
.agri-avatar-assistente::after {
  content: "";
  position: absolute;
  left: 14px;
  top: 4px;
  width: 2px;
  height: 4px;
  background: currentColor;
}

/* Fontes: detalhes ficam em um expansor abaixo do balão */
[data-testid="stExpander"] {
  background: var(--agri-branco);
  border: 1px solid var(--agri-contorno-suave);
  border-radius: 12px;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p {
  color: var(--agri-tinta);
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
  overflow-wrap: anywhere;
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] li {
  color: var(--agri-tinta);
  font-size: 15px;
}
.st-key-fontes {
  box-sizing: border-box;
  width: 76%;
}

/* Campo de pergunta: cartão branco centralizado, botão de envio preto no canto */
.st-key-composer {
  box-sizing: border-box;
  width: 100%;
  max-width: 640px;
  min-height: 56px;
  margin: 8px auto 0;
  padding: 6px 6px 6px 18px;
  border: 1px solid var(--agri-contorno-controle);
  border-radius: 16px;
  background: var(--agri-branco);
}
.st-key-composer:has(input:focus-visible) {
  outline: 2px solid var(--agri-tinta);
  outline-offset: 2px;
}
.st-key-composer [data-testid="stTextInput"] {
  flex: 1 1 auto;
  min-width: 0;
  width: auto;
}
.st-key-composer [data-testid="stTextInputRootElement"],
.st-key-composer [data-baseweb="input"],
.st-key-composer [data-baseweb="base-input"] {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
.st-key-composer input {
  height: 40px;
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  color: var(--agri-tinta);
  font-size: 16px;
}
.st-key-composer input::placeholder {
  color: var(--agri-secundaria);
  opacity: 1;
}
.st-key-composer [data-testid="InputInstructions"] {
  display: none;
}
.st-key-composer [data-testid="stFormSubmitButton"] {
  flex: none;
  width: auto;
}
.st-key-composer [data-testid="stFormSubmitButton"] button {
  width: 36px;
  min-width: 36px;
  height: 36px;
  min-height: 36px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: var(--agri-tinta);
  color: var(--agri-branco);
  display: flex;
  align-items: center;
  justify-content: center;
}
/* A seta fica centralizada: os envoltórios internos do botão também são flex centrados. */
.st-key-composer [data-testid="stFormSubmitButton"] button > div,
.st-key-composer [data-testid="stFormSubmitButton"] button > div > span,
.st-key-composer [data-testid="stFormSubmitButton"] button > div > span > span {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
}
.st-key-composer [data-testid="stFormSubmitButton"] button:hover {
  background: #2a2a2e;
  color: var(--agri-branco);
}
.st-key-composer [data-testid="stFormSubmitButton"] button:focus-visible {
  outline: 2px solid var(--agri-tinta);
  outline-offset: 2px;
}
.st-key-composer [data-testid="stFormSubmitButton"] button p {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* Entrada (campo e ajuda). Antes da primeira pergunta ela segue o fluxo da página, no meio da
   área clara. Depois da primeira pergunta, o wrapper dela vai para a base e fica preso ao fim da
   área de conversa, que rola acima dela (como um chat). */
.st-key-entrada {
  box-sizing: border-box;
  width: 100%;
  padding: 8px 0 14px;
  background: var(--agri-fundo);
}
[data-testid="stMainBlockContainer"] {
  height: 100%;
  min-height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
  flex: 1 1 auto;
}
[data-testid="stVerticalBlock"]:has(.st-key-conversa .agri-linha)
  > [data-testid="stLayoutWrapper"]:has(> .st-key-entrada) {
  margin-top: auto;
  position: sticky;
  bottom: 0;
  z-index: 5;
  background: var(--agri-fundo);
}

/* Cartões de sugestão: botões que enviam uma pergunta pronta, com quadrado verde-limão */
.st-key-sugestoes {
  box-sizing: border-box;
  width: 100%;
  max-width: 640px;
  margin: 16px auto 0;
}
/* O filho direto de cada cartão é o contêiner do Streamlit; ele é que divide a linha. */
.st-key-sugestoes > [data-testid="stElementContainer"] {
  flex: 1 1 180px;
  min-width: 0;
}
.st-key-sugestoes [data-testid="stButton"] {
  width: 100%;
  min-width: 0;
}
.st-key-sugestoes [data-testid="stButton"] button {
  box-sizing: border-box;
  position: relative;
  width: 100%;
  min-height: 92px;
  height: auto;
  display: block;
  padding: 40px 14px 14px;
  border: 1px solid var(--agri-contorno-controle);
  border-radius: 14px;
  background: var(--agri-branco);
  color: var(--agri-tinta);
  text-align: left;
}
/* O Streamlit reserva um espaço de ícone antes do rótulo; os cartões não usam ícone. */
.st-key-sugestoes [data-testid="stButton"] button > div {
  display: block;
  width: 100%;
  padding: 0;
  margin: 0;
  gap: 0;
}
.st-key-sugestoes [data-testid="stButton"] button::before {
  content: "";
  position: absolute;
  left: 14px;
  top: 14px;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  background: var(--agri-destaque);
}
.st-key-sugestoes [data-testid="stButton"] button:hover {
  background: var(--agri-fundo);
  border-color: var(--agri-tinta);
}
.st-key-sugestoes [data-testid="stButton"] button:focus-visible {
  outline: 2px solid var(--agri-tinta);
  outline-offset: 2px;
}
.st-key-sugestoes [data-testid="stButton"] button p {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  text-align: left;
  color: var(--agri-secundaria);
}
.st-key-sugestoes [data-testid="stButton"] button p strong {
  font-size: 16px;
  font-weight: 500;
  color: var(--agri-tinta);
}

/* Tela estreita (fim do arquivo: estas regras vencem as de largura acima).
   O botão que abre a barra fica sobre o início do título, então o título ganha recuo.
   Os cartões empilham em uma coluna. */
@media (max-width: 640px) {
  /* Tela estreita: a conversa ocupa a largura toda, sem cartão recuado. */
  [data-testid="stMain"] {
    margin: 0;
    border: none;
    border-radius: 0;
  }
  /* Tela estreita: o quadro ocupa a tela toda, sem moldura nem cantos. */
  [data-testid="stAppViewContainer"] {
    inset: 0 !important;
    max-width: none;
    border-radius: 0;
    padding: 0;
    background: var(--agri-fundo);
  }
  .agri-topo {
    padding-left: 40px;
  }
  .st-key-sugestoes {
    flex-wrap: wrap !important;
  }
  .st-key-sugestoes > [data-testid="stElementContainer"] {
    flex: 1 1 100%;
  }
}
"""

CSS_PAGINA: Final[str] = f"<style>{_VARIAVEIS_CSS}{_REGRAS_CSS}</style>"
