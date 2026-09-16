"""
Logging centralizado - TAREFA 6.

Configuracao unica de log, reaproveitada pelas tres interfaces do
servico (REST, worker e gRPC), para registrar id da requisicao/tarefa,
tamanho da entrada e tempo de resposta de forma consistente.
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("inferencia")