# AgriNormas · Assistente de normativas internas (RAG)

Assistente que responde perguntas em linguagem natural com base nas normativas internas. Cada resposta cita as fontes (documento e seção). Quando os documentos não respondem à pergunta, o assistente diz que **não há evidência**, em vez de inventar uma resposta.

> Os três documentos em `base_conhecimento/` são **fictícios** e foram criados para um desafio técnico. Não representam política oficial.

## Escopo

- **Inclui:** consulta em linguagem natural às três políticas (reembolso, veículos e férias), recuperação de trechos, resposta com fontes e aviso de falta de evidência.
- **Fora do escopo atual:** controle de solicitações, fluxos de aprovação e banco de dados SQL. SQLite fica como extensão futura.

## Documentos base

| Código | Documento | Arquivo |
|---|---|---|
| FIN-POL-001 | Política de reembolso | `base_conhecimento/Politica_Reembolso.pdf` |
| FRO-POL-002 | Política de utilização de veículos | `base_conhecimento/Politica_Veiculos.pdf` |
| RH-PRO-003 | Procedimento de solicitação de férias | `base_conhecimento/Procedimento_Ferias.pdf` |

## Stack

- **Linguagem:** Python 3.15 (versão fixada em `.python-version`)
- **Geração de respostas:** OpenAI `gpt-4o-mini`
- **Embeddings:** OpenAI `text-embedding-3-small`
- **Índice:** numpy, em memória, com cache em disco
- **Leitura de PDF:** pypdf
- **Interface:** Streamlit
- **Testes e qualidade:** pytest, ruff, mypy

## Status do projeto

| Área | Situação |
|---|---|
| Ambiente, dependências e estrutura de pacotes | Concluído |
| Configuração validada | Concluído |
| Contratos e modelos de domínio | Concluído |
| Leitura, limpeza e divisão dos PDFs | Concluído |
| Recuperação e limiar de similaridade | Concluído; limitação conhecida nas perguntas 2, 3 e 4 |
| Geração fundamentada e validação de citações | Aceita com ressalva; limitação conhecida nas perguntas 2, 3 e 4 |
| Orquestração e composição | Aceita com ressalva |
| Interface Streamlit | Aceita com ressalvas |
| Suíte de validação das seis perguntas | Aceita com limitação nas perguntas 2, 3 e 4 |
| Qualidade estática e CI | Em andamento |
| Documentação e entrega | Em andamento |

## Pré-requisitos

- **Python 3.15**, a versão fixada em `.python-version`. Versões anteriores não são suportadas.
- **Chave de API da OpenAI**, com saldo. É necessária para gerar respostas e embeddings.
- **Git**, para clonar o repositório.

## Instalação

Clone o repositório e entre na pasta do projeto. Os comandos abaixo criam um ambiente virtual em `.venv` e instalam as dependências fixadas em `requirements.txt`.

**Windows (PowerShell):**

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Se o PowerShell bloquear a ativação do ambiente, rode `Set-ExecutionPolicy -Scope Process RemoteSigned` na mesma janela e tente de novo. Com `-Scope Process`, a mudança vale só para a sessão atual.

**Windows (Git Bash):**

```bash
py -3.15 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

**Linux:**

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Os comandos seguintes assumem o ambiente virtual ativo.

### Pre-commit (recomendado para quem contribui)

O pre-commit não está no `requirements.txt`. Ao ser instalado a partir do código-fonte, o PyYAML pode tentar compilar a extensão LibYAML, e a variável `PYYAML_FORCE_LIBYAML=0` evita isso. O hook roda `ruff check` e `ruff format` antes de cada commit.

**Windows (PowerShell):**

```powershell
$env:PYYAML_FORCE_LIBYAML = "0"
python -m pip install pre-commit
pre-commit install
```

**Windows (Git Bash) e Linux:**

```bash
PYYAML_FORCE_LIBYAML=0 python -m pip install pre-commit
pre-commit install
```

## Configuração

1. Copie o arquivo de exemplo.

   **PowerShell:** `Copy-Item .env.example .env`

   **Git Bash ou Linux:** `cp .env.example .env`

2. Abra o `.env` em um editor e preencha `OPENAI_API_KEY`.

O arquivo `.env` fica fora do repositório (está no `.gitignore`). Não cole a chave em código, em log, em issue ou em commit.

Os demais valores já têm padrão no `.env.example`, e um valor vazio usa o padrão:

| Variável | Padrão | Função |
|---|---|---|
| `MODELO_GERACAO` | `gpt-4o-mini` | Modelo que gera a resposta |
| `MODELO_EMBEDDING` | `text-embedding-3-small` | Modelo dos embeddings |
| `LIMIAR_SIMILARIDADE` | `0.60` | Abaixo dele, o trecho é descartado. Valor provisório (igual ao `.env.example`). Três das seis perguntas de validação (2, 3 e 4) têm seções de apoio abaixo dele |
| `TOP_K` | `4` | Número de trechos recuperados por pergunta |
| `PASTA_DOCUMENTOS` | `base_conhecimento` | Pasta com os PDFs lidos |
| `TAMANHO_MAXIMO_CHUNK` | `1200` | Tamanho máximo de uma seção indexada |
| `TIMEOUT_SEGUNDOS` | `30` | Tempo limite das chamadas à API |

Se a aplicação mostrar um erro de configuração, confira o nome da variável e o valor no `.env`. A mensagem de erro não mostra o valor.

## Execução

Com o ambiente virtual ativo, na raiz do projeto:

```bash
streamlit run src/interface/app.py
```

O Streamlit mostra o endereço da aplicação no terminal, normalmente `http://localhost:8501`. Digite uma pergunta e confira a resposta, as fontes e, quando for o caso, o aviso de falta de evidência.

Na primeira execução, a aplicação lê os PDFs, gera os embeddings das seções e grava o cache em `dados/indice.npz`. Nas execuções seguintes, só as perguntas novas chamam a API. A pasta `dados/` pode ser apagada com segurança: o índice é recalculado na próxima execução, com custo de embeddings.

## Testes e qualidade

```bash
# Testes offline (não chamam a API e não precisam de chave)
python -m pytest

# Testes de integração com a API real (exige OPENAI_API_KEY no .env e consome créditos)
python -m pytest -m integracao

# Lint, formatação e tipagem
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

A suíte offline é o padrão. Os casos marcados como `xfail` (falha esperada) são estritos: enquanto a falha existir, eles aparecem no resumo do pytest sem quebrar a execução. Quando o problema for corrigido, o teste passa, o pytest acusa a passagem como erro e a marca `xfail` deve ser removida (ver a seção abaixo).

### Perguntas de validação

As seis perguntas usadas para validar o assistente, com as respostas de referência, estão em [tests/validacao/perguntas.md](tests/validacao/perguntas.md). A pergunta 6 (limite de combustível por viagem) deve receber a resposta de que **não há evidência nos documentos**.

Na integração com a API real, as perguntas 1, 5 e 6 passam. As perguntas 2, 3 e 4 seguem como `xfail`. Essas medições foram feitas com `TOP_K` 6, valor do `.env` local. Com `TOP_K` 4, que é o padrão do `.env.example`, a pergunta 4 também perde a seção RH-PRO-003 §3.

A pergunta 6 apresenta resultados diferentes entre execuções da integração real. Ela não tem marca de falha esperada, então uma falha nela aparece como erro no teste.

### Vetores gravados da validação

O modo offline da suíte não chama a API. Ele usa os embeddings gravados em `tests/validacao/vetores_gravados.npz`. **Regrave esse arquivo sempre que mudar** a base de documentos (`base_conhecimento/`), as perguntas (`tests/validacao/perguntas.md`), o modelo de embedding ou o texto indexado (`src/busca/indexacao.py`). Sem a regravação, o teste offline falha com uma mensagem pedindo para regravar.

```bash
python tests/validacao/gravar_vetores.py
```

O script faz um único pedido à API (com as seções e as seis perguntas) e consome créditos. Ele precisa da `OPENAI_API_KEY` no `.env`.

### Limitação conhecida: perguntas 2, 3 e 4

A recuperação não traz hoje todas as seções que sustentam estas respostas, porque elas ficam abaixo do limiar de 0,60:

- **Pergunta 2:** FIN-POL-001 §4 tem cosseno 0,568.
- **Pergunta 3:** a seção FIN-POL-001 §4 não é recuperada (cosseno 0,41, abaixo do limiar 0,60), por isso a resposta não a cita.
- **Pergunta 4:** RH-PRO-003 §4 tem cosseno 0,44. Com `TOP_K` 4, a seção RH-PRO-003 §3 também fica de fora.

As falhas estão marcadas como `xfail` na suíte. Uma busca híbrida (cosseno com BM25) foi testada e não resolveu esses casos, por isso foi descartada. A abordagem para esses casos ainda não foi decidida.

## Estrutura de pastas

```
AgriNormas/
├── base_conhecimento/     # Políticas em PDF lidas pelo assistente (versionado)
├── src/
│   ├── config.py          # Configuração validada a partir do .env
│   ├── composicao.py      # Montagem das dependências (único lugar com implementações concretas)
│   ├── nucleo/            # Regras de negócio: modelos, contratos, erros e assistente
│   ├── documentos/        # Leitura, limpeza, metadados e chunking dos PDFs
│   ├── busca/             # Embeddings, índice em memória, buscador com limiar e cache
│   ├── geracao/           # Cliente do modelo, prompt e validação de citações
│   └── interface/         # Tela Streamlit
├── tests/                 # Testes unitários, de robustez, de integração e de validação
│   └── validacao/         # Perguntas de validação e vetores gravados (versionado)
├── scripts/               # Calibração do limiar
├── dados/                 # Cache do índice, gerado em execução (não versionado)
├── pyproject.toml         # Configuração de ruff, mypy e pytest
├── requirements.txt       # Dependências com versões fixadas
└── .env.example           # Modelo de configuração
```

| Pasta | O que contém | Versionado |
|---|---|---|
| `base_conhecimento/` | As três políticas em PDF. É a entrada de dados da aplicação, apontada por `PASTA_DOCUMENTOS` no `.env`. | Sim |
| `tests/validacao/` | Perguntas de validação (`perguntas.md`), fonte única das respostas de referência, e vetores gravados. | Sim |
| `dados/` | Cache do índice, gerado na execução. | Não |

## Arquitetura

A interface chama o `AssistenteRAG`, que depende apenas de contratos (busca e geração), definidos em `src/nucleo/contratos.py`. As implementações concretas, como OpenAI, numpy e pypdf, são escolhidas em `src/composicao.py`, o único lugar que as conhece. Assim, cada parte pode ser trocada sem alterar as regras de negócio.

- **Documentos:** leitura, limpeza e chunking dos PDFs por seção numerada, com metadados (código do documento e número da seção). Seções de exceção ficam inteiras.
- **Busca:** embeddings das seções, índice em memória e filtro pelo limiar de similaridade. Abaixo do limiar, o assistente responde que não há evidência.
- **Geração:** monta o prompt com os trechos recuperados, pede a resposta ao modelo e valida se as citações correspondem aos trechos enviados. Quando a resposta depende de duas políticas, cita as duas.
