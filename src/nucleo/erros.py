"""Exceções do domínio.

As mensagens destas exceções nunca devem conter chaves de API, conteúdo de prompt
ou resposta bruta do modelo.
"""


class ErroAssistente(Exception):
    """Base de todas as exceções do assistente."""


class ErroDocumento(ErroAssistente):
    """Arquivo inexistente, corrompido ou sem texto extraível."""


class ErroBusca(ErroAssistente):
    """Falha ao gerar embeddings ou consultar o índice."""


class ErroGeracao(ErroAssistente):
    """Falha na chamada ao modelo de linguagem."""


class ConfiguracaoInvalida(ErroAssistente):
    """Configuração ausente ou inválida. A mensagem cita o nome da variável, nunca o valor."""


class PerguntaInvalida(ErroAssistente):
    """Pergunta vazia, só com espaços ou longa demais.

    É erro de entrada, não ausência de evidência (ADR-007).
    """
