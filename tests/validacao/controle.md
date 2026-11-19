# Conjunto de controle · glossário de sinônimos (HIST-029)

**Dono do conteúdo:** `po` · **Escrito em:** 2026-11-18, antes do glossário e de qualquer medição · **Versão:** 1 (congelada)

Fonte única das 8 perguntas de controle. Não substitui nem altera [perguntas.md](perguntas.md). Os números usam o prefixo `C` para não se confundirem com as perguntas 1 a 7.

Documentos: FIN-POL-001 (reembolso), FRO-POL-002 (veículos) e RH-PRO-003 (férias), em `base_conhecimento/`. As seções citadas são as do próprio documento.

## Perguntas

| # | Pergunta | Fontes esperadas | Comportamento esperado |
|---|---|---|---|
| C1 | Na viagem a serviço, paguei o jantar de uma pessoa que foi comigo mas não trabalha para a empresa. Dá para pedir o reembolso desse jantar? | FIN-POL-001 §3.2 e §4 | Diz que não: refeição de acompanhante não é elegível. |
| C2 | Um colega sem carteira de motorista pode dirigir o carro da empresa para levar um cliente, se eu for junto? | FRO-POL-002 §3 e §3.1 | Diz que não: a condução exige habilitação válida e autorização individual, e o veículo não pode ser conduzido por pessoa não autorizada. |
| C3 | Posso trocar parte das minhas férias por dinheiro? | RH-PRO-003 §6 | Diz que é possível pedir formalmente o abono pecuniário, que o RH analisa conforme a legislação, e que o pedido não garante aprovação. |
| C4 | Abasteci o carro da empresa com meu cartão pessoal porque o posto credenciado estava fora do ar. Posso pedir o dinheiro de volta? O que preciso fazer? | FRO-POL-002 §5 e FIN-POL-001 §5 | Diz que o reembolso depende de autorização para pagamento particular, manda comunicar o responsável pela frota assim que possível e cita a exigência de comprovante fiscal. |
| C5 | Vou levar o carro da empresa a um cliente em outra cidade e dormir lá dois dias. Preciso avisar alguém? Posso pedir reembolso da hospedagem? | FRO-POL-002 §9 e FIN-POL-001 §3.3 | Diz que a viagem intermunicipal deve constar na solicitação de uso (destino, período e justificativa) e que a hospedagem deve ser reservada pelos canais da empresa, com reembolso sujeito a custo razoável. |
| C6 | Minha empresa cobre plano de saúde para os dependentes? | nenhuma | Diz que não há evidência nos documentos e não cita fonte. |
| C7 | Posso trabalhar de casa dois dias por semana? | nenhuma | Diz que não há evidência nos documentos e não cita fonte. |
| C8 | Posso pedir um adiantamento do meu salário antes do dia do pagamento? | nenhuma | Diz que não há evidência nos documentos e não cita fonte. Não usa o adiantamento de viagem (FIN-POL-001 §8) como resposta. |

**Tipos**
- Documento só: C1, C2 e C3.
- Dois documentos: C4 e C5.
- Ausência de informação: C6, C7 e C8.

## Regra de uso

1. **Congelamento.** O conjunto está congelado desde 2026-11-18. Pergunta, fonte e comportamento não mudam depois do início da medição. Mudança exige nova versão (v2), com data e motivo registrados no backlog. Resultados da v1 deixam de ser comparáveis com a v2.
2. **Medição.** A mesma lista é medida em duas variantes: base (sem glossário) e com glossário. As duas usam o mesmo índice, o mesmo `TOP_K` e o mesmo limiar. Esses três valores são registrados no relatório.
3. **Critério por tipo.**
   - Documento só (C1 a C3): a fonte esperada aparece na resposta.
   - Dois documentos (C4 e C5): as duas fontes aparecem. Citar só uma é falha parcial e entra no relatório.
   - Ausência (C6 a C8): nenhuma fonte citada e resposta de "não há evidência". Fonte citada ou resposta afirmativa é falso positivo.
4. **Critério para adotar o glossário** (proposta do `po`, a confirmar pelo usuário). O glossário só é adotado se, em relação à base, não piorar em C1 a C5 e mantiver zero falso positivo em C6 a C8. Ganho nas perguntas 1 a 7 não compensa regressão aqui.
5. **Uso único para decisão.** O glossário é escrito e congelado antes de rodar este conjunto. Não se ajusta o glossário depois de ver resultados de C1 a C8, e não se copiam termos das perguntas C1 a C8 para o glossário. Se isso acontecer, o conjunto é marcado como contaminado no backlog, e uma nova versão é necessária antes de qualquer nova decisão.
6. **Papéis.** O `tester` executa e reporta por pergunta (fontes recuperadas e comportamento observado). O `po` aceita o resultado. Este arquivo é editado só pelo `po`; o `tester` apenas executa.
7. **Limitações.** São oito perguntas, em uma execução. O resultado é indicativo e não tem significância estatística. Autoria: o `po` leu os três documentos antes de escrever e não consultou `perguntas.md` nem as respostas de referência.
