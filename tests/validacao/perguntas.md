# Validação do assistente

Fonte única das perguntas de validação e das respostas de referência. Usada pelo `tester` (suíte automatizada, HIST-022) e pelo `po` (aceite). Não copie esta tabela para outros arquivos: referencie este.

## Perguntas e respostas de referência

| # | Pergunta | Deve conter | Fontes que devem aparecer |
|---|---|---|---|
| 1 | Qual é o prazo para solicitar o reembolso de despesas de viagem? | até 5 dias úteis após o encerramento da viagem; contagem a partir do primeiro dia útil seguinte ao retorno | FIN-POL-001 §6 |
| 2 | É possível solicitar reembolso sem apresentar comprovante fiscal? | não, salvo autorização formal da diretoria; extrato de cartão não substitui o comprovante | FIN-POL-001 §4, §5 |
| 3 | Quem é responsável pelas multas de veículos corporativos? | o próprio condutor; multas não são reembolsáveis | FRO-POL-002 §6; FIN-POL-001 §4 |
| 4 | Qual é o procedimento para solicitar férias? | registro no canal oficial, com 30 dias de antecedência; aprovação do gestor e do RH | RH-PRO-003 §2 a §4 |
| 5 | A empresa permite utilizar veículos corporativos para atividades pessoais? | não; uso exclusivo para atividades profissionais | FRO-POL-002 §2 |
| 6 | Qual é o limite de reembolso de combustível por viagem? | não há evidência nos documentos | nenhuma; não apresentar trecho como se respondesse à pergunta |

## Regras de aceite

- A pergunta 6 falha se o sistema inventar um valor ou limite, ou citar um trecho como se respondesse a ela.
- Cada resposta deve citar as fontes listadas, com documento e seção.
- Nas perguntas 3 e 5, as duas políticas devem ser citadas quando a resposta depender de ambas.
- A resposta deve estar em português do Brasil.
- Formato da tabela: a suíte lê as linhas desta tabela. Não altere o número de colunas sem ajustar `tests/validacao/`.
