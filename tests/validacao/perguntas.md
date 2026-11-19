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
| 6 | Qual é o limite de reembolso de combustível por viagem? | não recusa, responde ausência com citação: o documento não estabelece limite mensal de combustível e não trata de limite por viagem; cita FRO-POL-002 §faq-5; indica onde consultar (área responsável pela frota); não informa valor, número, R$ nem percentual; evidencia_suficiente verdadeiro | FRO-POL-002 §faq-5 |
| 7 | Qual o limite de reembolso de combustível? | não recusa, responde ausência com citação: o documento não estabelece limite mensal de combustível; cita FRO-POL-002 §faq-5; indica onde consultar (área responsável pela frota); não informa valor nem limite | FRO-POL-002 §faq-5 |

## Regras de aceite

- As perguntas 6 e 7 tratam do mesmo fato (limite de combustível), por decisão do usuário em 2026-11-18. Nenhuma das duas é recusa. A pergunta 7 não tem período, por isso não exige a frase sobre limite por viagem. A pergunta 6 exige.
- A pergunta 6 falha se o sistema informar valor, número, R$ ou percentual de limite, se recusar (`evidencia_suficiente` falso ou mensagem padrão de sem evidência), se responder sem citar `FRO-POL-002 §faq-5`, ou se não disser que o documento não estabelece limite mensal de combustível e não trata de limite por viagem.
- O caso 7 (regressão de combustível) falha se o sistema informar valor ou limite, se recusar, se responder sem citar `FRO-POL-002 §faq-5`, se não disser que o documento não estabelece limite mensal de combustível, ou se não indicar onde consultar (área responsável pela frota). Ele não é recusa: a resposta cita o trecho que afirma a ausência de limite mensal. Não se exige a menção a limite por viagem, porque a pergunta 7 não tem período (decisão de 2026-11-18).
- Cada resposta deve citar as fontes listadas, com documento e seção.
- Nas perguntas 3 e 5, as duas políticas devem ser citadas quando a resposta depender de ambas.
- A resposta deve estar em português do Brasil.
- Formato da tabela: a suíte lê as linhas desta tabela. Não altere o número de colunas sem ajustar `tests/validacao/`.
