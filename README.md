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
- **Índice:** numpy, em memória
- **Leitura de PDF:** pypdf
- **Interface:** Streamlit
- **Testes e qualidade:** pytest, ruff, mypy


## Status do projeto

| Área | Situação |
|---|---|
| Ambiente, dependências e estrutura de pacotes (HIST-001) | Concluído |
| Configuração validada (HIST-002) | Planejado |
| Contratos e modelos de domínio (HIST-003) | Concluído |
| Leitura, limpeza e chunking dos PDFs (EP-01) | Planejado |
| Recuperação e limiar de similaridade (EP-02) | Planejado |
| Geração fundamentada e validação de citações (EP-03) | Planejado |
| Orquestração e composição (EP-04) | Planejado |
| Interface Streamlit (EP-05) | Planejado |
| Suíte de validação das seis perguntas (EP-06) | Planejado |

## Pré-requisitos

- Python 3.15 ou superior (o projeto usa a versão fixada em `.python-version`; versões anteriores não são suportadas)
- Uma chave de API da OpenAI, necessária para gerar respostas e embeddings reais

## Instalação

Clone o repositório e entre na pasta do projeto.

**Windows (PowerShell):**

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS, Linux ou Git Bash:**

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Configuração

1. Copie o arquivo de exemplo:

   ```bash
   cp .env.example .env
   ```

2. Preencha `OPENAI_API_KEY` no `.env`.

O arquivo `.env` fica fora do repositório (está no `.gitignore`). Nunca coloque a chave em código, em log ou em commits.

Os demais valores (modelos, limiar de similaridade, `TOP_K`, pasta dos documentos) têm padrões no `.env.example`. O limiar de similaridade é provisório e será calibrado com as perguntas de validação (ADR-002).

## Execução

> Disponível quando a HIST-019 (tela de perguntas) estiver concluída.

```bash
streamlit run src/interface/app.py
```

A aplicação abre no navegador. Digite uma pergunta e confira a resposta, as fontes e, quando for o caso, o aviso de falta de evidência.

## Testes e qualidade

```bash
# Testes offline (não chamam a API e não gastam créditos)
pytest

# Testes de integração com a API real (exige OPENAI_API_KEY no .env)
pytest -m integracao

# Lint e formatação
ruff check .

# Tipagem (modo estrito no núcleo)
mypy
```

A suíte offline é o padrão. Os testes marcados com `integracao` são opcionais e chamam a API real.

## Perguntas de validação

As seis perguntas usadas para validar o assistente, com as respostas de referência, estão em [tests/validacao/perguntas.md](tests/validacao/perguntas.md). A pergunta sobre limite de combustível por viagem deve receber a resposta de que **não há evidência nos documentos**.

## Estrutura de pastas

```
AgriNormas/
├── base_conhecimento/     # Políticas em PDF lidas pelo assistente (versionado)
├── docs/                  # Documentação de arquitetura e ADRs (versionado)
│   ├── arquitetura/
│   └── decisoes/
├── planejamento/          # Backlog e material do desafio (não versionado)
├── src/
│   ├── config.py          # Configuração validada a partir do .env
│   ├── composicao.py      # Montagem das dependências (único lugar com implementações concretas)
│   ├── nucleo/            # Regras de negócio: modelos, contratos, erros e assistente
│   ├── documentos/        # Leitura, limpeza, metadados e chunking dos PDFs
│   ├── busca/             # Embeddings, índice em memória e buscador com limiar
│   ├── geracao/           # Cliente do modelo, prompt e validação de citações
│   └── interface/         # Tela Streamlit
├── tests/                 # Testes unitários, de validação e de robustez (validacao/ é versionado)
├── dados/                 # Cache do índice (gerado em execução, não versionado)
├── .claude/               # Agentes e fluxo de desenvolvimento (não versionado)
├── pyproject.toml         # Configuração de ruff, mypy e pytest
├── requirements.txt       # Dependências com versões fixadas
└── .env.example           # Modelo de configuração
```

Os itens da árvore que ainda não existem no repositório (por exemplo, `src/config.py`, `src/composicao.py`, `src/nucleo/assistente.py` e os módulos de documentos, busca, geração e interface) são o destino previsto. O andamento de cada um está na tabela de status acima.

| Pasta | O que contém | Versionado |
|---|---|---|
| `base_conhecimento/` | As três políticas em PDF. É a entrada de dados da aplicação, apontada por `PASTA_DOCUMENTOS` no `.env`. | Sim |
| `docs/` | Arquitetura (`docs/arquitetura/`) e decisões técnicas (`docs/decisoes/`, os ADRs). | Sim |
| `planejamento/` | Backlog (`backlog.md`) e material do desafio. Uso interno do projeto. | Não |
| `tests/validacao/` | Perguntas de validação (`perguntas.md`), fonte única das respostas de referência. | Sim |
| `dados/` | Cache do índice, gerado na execução. | Não |
| `.claude/` | Agentes e fluxo de desenvolvimento, ferramenta local. | Não |

Esta estrutura inclui `src/nucleo/` e `src/composicao.py`, que não estavam no desenho inicial. Eles isolam as regras de negócio das bibliotecas de IA, de PDF e de interface, o que permite testar a recusa sem chamar a API.

## Arquitetura em uma frase

A interface chama o `AssistenteRAG`, que depende apenas de contratos (busca e geração). As implementações concretas, como OpenAI, numpy e pypdf, são escolhidas em `src/composicao.py`. Assim, cada parte pode ser trocada sem alterar as regras de negócio.
