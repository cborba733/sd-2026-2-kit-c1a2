"""
Interface REST do servico de inferencia.

O QUE JA ESTA PRONTO:
  - carregamento do modelo UMA vez, na subida (nao a cada requisicao)
  - rota sincrona /predict-sync, usada no laboratorio da Aula 6

O QUE VOCE PRECISA FAZER (TAREFAS.md, itens 1 e 2):
  - POST /predict  -> colocar na fila e devolver o id
  - GET  /resultado/{id} -> devolver o resultado quando estiver pronto

Rodar:  uvicorn app.api_rest:app --reload --port 8000
Docs:   http://localhost:8000/docs
"""
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.modelo import carregar_modelo
from app import fila
from app.log import logger

app = FastAPI(title="Servico de Inferencia - C1.A2", version="0.1.0")

modelo = None


class Entrada(BaseModel):
    texto: str


@app.on_event("startup")
def _subir():
    """Carrega o modelo UMA vez. Este e o ponto-chave da Aula 6."""
    global modelo
    inicio = time.time()
    modelo = carregar_modelo()
    print(f"[startup] modelo carregado em {time.time() - inicio:.3f}s")


@app.get("/saude")
def saude():
    return {"status": "ok", "modelo_carregado": modelo is not None}


@app.post("/predict-sync")
def predict_sync(entrada: Entrada):
    """Inferencia SINCRONA: o cliente espera a resposta. Lab da Aula 6."""
    if not entrada.texto.strip():
        raise HTTPException(status_code=400, detail="texto vazio")
    inicio = time.time()
    resultado = modelo.prever(entrada.texto)
    resultado["tempo_ms"] = round((time.time() - inicio) * 1000, 2)
    logger.info(
        "predict-sync tamanho_entrada=%d tempo_ms=%.2f",
        len(entrada.texto), resultado["tempo_ms"],
    )
    return resultado


# ------------------------------------------------------------------
# TAREFA 1 - submissao assincrona
# ------------------------------------------------------------------
@app.post("/predict", status_code=202)
def predict(entrada: Entrada):
    """Enfileira a tarefa e devolve o id SEM esperar o resultado."""
    if not entrada.texto.strip():
        raise HTTPException(status_code=400, detail="texto vazio")
    inicio = time.time()
    tarefa_id = fila.enfileirar(entrada.texto)
    tempo_ms = round((time.time() - inicio) * 1000, 2)
    logger.info(
        "predict id=%s tamanho_entrada=%d tempo_ms=%.2f",
        tarefa_id, len(entrada.texto), tempo_ms,
    )
    return {"id": tarefa_id}


# ------------------------------------------------------------------
# TAREFA 2 - consulta do resultado
# ------------------------------------------------------------------
@app.get("/resultado/{tarefa_id}")
def resultado(tarefa_id: str):
    """Devolve o resultado da tarefa; 404 se o id nao existir."""
    inicio = time.time()
    dados = fila.buscar_resultado(tarefa_id)
    tempo_ms = round((time.time() - inicio) * 1000, 2)
    if dados is None:
        logger.warning(
            "resultado id=%s nao_encontrado tempo_ms=%.2f", tarefa_id, tempo_ms
        )
        raise HTTPException(status_code=404, detail="tarefa nao encontrada")
    logger.info("resultado id=%s tempo_ms=%.2f", tarefa_id, tempo_ms)
    return dados