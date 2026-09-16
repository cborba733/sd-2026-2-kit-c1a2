# C1.A2 — Serviço de Inferência Distribuído

Trabalho da disciplina **Sistemas Distribuídos e Computação em Nuvem** (FAESA, 2026/2,
prof. Howard Roatti). Serviço que recebe um texto, classifica o sentimento (positivo/negativo)
usando um modelo de IA já pronto, e devolve o resultado — exposto por **REST** e **gRPC**,
com processamento **assíncrono** via fila e worker.

## Arquitetura

```
                         ┌──────────────────┐
                         │   modelo.py       │  classificador de sentimento
                         │ (scikit-learn)     │  (carregado 1x por processo)
                         └─────────▲──────────┘
                                   │
        ┌──────────────────┐      │      ┌──────────────────┐
        │   api_rest.py     │──────┤      │  servidor_grpc.py │
        │   (FastAPI)       │      │      │   (gRPC, porta     │
        │   porta 8000      │      │      │   50051)           │
        └────────┬──────────┘      │      └────────────────────┘
                  │                │
      /predict-sync                │        Prever / PreverLote
      (síncrono, sem fila)         │        (síncrono, sem fila)
                  │                │
      /predict ──►│                │
      (enfileira) │                │
                  ▼                │
           ┌─────────────┐         │
           │  fila.py     │◄────────┘
           │  (Redis)     │
           └──────┬───────┘
                  │
                  ▼
           ┌─────────────┐
           │  worker.py   │  consome a fila, chama o modelo,
           │              │  grava o resultado, faz retry + DLQ
           └─────────────┘
```

Todos os três componentes (`api_rest.py`, `servidor_grpc.py`, `worker.py`) carregam o
modelo **uma única vez**, na inicialização — nunca a cada requisição — e compartilham o
mesmo módulo de log (`app/log.py`), garantindo que REST e gRPC produzam o mesmo resultado
para a mesma entrada, já que os dois chamam exatamente `modelo.prever(texto)`.

### Fluxo síncrono (REST `/predict-sync` e gRPC `Prever`/`PreverLote`)

O cliente chama e espera a resposta na hora. Usado quando a inferência é rápida o
suficiente para não valer a pena enfileirar.

### Fluxo assíncrono (REST `/predict` + `/resultado/{id}`)

1. `POST /predict` enfileira a tarefa no Redis e devolve `{"id": ...}` com status `202`,
   sem esperar a inferência terminar.
2. O `worker.py` (processo separado) consome a fila (`BLPOP`), executa a inferência e
   grava o resultado no Redis, associado ao `id`.
3. O cliente consulta `GET /resultado/{id}` quando quiser; enquanto o worker não
   terminou, a chave ainda está com `status: "na_fila"`; quando pronto, vem o resultado
   completo. Se o `id` não existir, a rota devolve `404`.

## Resiliência

- **Validação de entrada**: `POST /predict-sync` e `POST /predict` devolvem `400` se o
  texto vier vazio.
- **Id inexistente**: `GET /resultado/{id}` devolve `404` (com log de aviso) se o id não
  existir.
- **Falha no worker**: se `modelo.prever(...)` lançar uma exceção, o worker tenta
  novamente até **3 vezes** (com um pequeno intervalo entre tentativas). Se todas
  falharem, a tarefa é movida para uma fila de descarte (*dead-letter*, `tarefas_descartadas`
  no Redis) e o resultado é marcado como `status: "falhou"`, ambos registrados em log.

## Logging

Todas as três interfaces (`api_rest.py`, `servidor_grpc.py`, `worker.py`) usam o mesmo
logger centralizado (`app/log.py`), registrando para cada requisição/tarefa o
identificador (quando existe), o tamanho da entrada e o tempo de resposta em
milissegundos. Exemplos de linhas de log:

```
predict id=ccf1a8e5-... tamanho_entrada=14 tempo_ms=8.52
resultado id=ccf1a8e5-... tempo_ms=0.86
worker id=ccf1a8e5-... tamanho_entrada=14 tempo_ms=2.84
grpc PreverLote quantidade=3 tempo_ms=5.32
predict-sync tamanho_entrada=14 tempo_ms=3.01
```

## Estrutura do projeto

```
.
├── app/
│   ├── modelo.py         # modelo de sentimento (pronto, não alterado)
│   ├── fila.py            # auxiliares de fila no Redis (pronto, não alterado)
│   ├── log.py              # logging centralizado, reaproveitado pelas 3 interfaces
│   ├── api_rest.py         # FastAPI: /predict-sync, /predict, /resultado/{id}, /saude
│   ├── worker.py           # consome a fila, chama o modelo, retry + dead-letter
│   └── servidor_grpc.py    # gRPC: Prever e PreverLote
├── proto/inferencia.proto  # contrato gRPC
├── exemplos/cliente_rest.py
├── testar_grpc.py          # cliente de teste do PreverLote (lote de 3 textos)
├── scripts/gerar_stubs.sh / .ps1
├── docker-compose.yml      # sobe o Redis
└── requirements.txt
```

## Como executar do zero

Pré-requisitos: Python 3.10+, Docker (para o Redis).

```bash
# 1. Clone o repositório
git clone https://github.com/cborba733/sd-2026-2-kit-c1a2.git
cd sd-2026-2-kit-c1a2

# 2. Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Suba o Redis (fila)
docker compose up -d

# 5. Gere os stubs do gRPC (necessário antes de rodar o servidor gRPC)
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/inferencia.proto

# 6. Em um terminal: suba a API REST
uvicorn app.api_rest:app --reload --port 8000
# docs interativos em http://localhost:8000/docs

# 7. Em outro terminal: suba o worker
python -m app.worker

# 8. Em outro terminal: suba o servidor gRPC
python -m app.servidor_grpc
```

### Testando

**REST síncrono** (Swagger em `/docs`, ou curl):
```bash
curl -X POST http://localhost:8000/predict-sync \
  -H "Content-Type: application/json" \
  -d '{"texto": "gol do sevilla"}'
```

**REST assíncrono**:
```bash
# 1. Envia a tarefa (devolve um id)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"texto": "gol do sevilla"}'

# 2. Consulta o resultado com o id devolvido acima
curl http://localhost:8000/resultado/<id>
```

**gRPC** (com o servidor rodando em outro terminal):
```bash
python testar_grpc.py
```

O modelo é treinado localmente na primeira execução (não precisa de internet nem GPU) e
salvo em `app/modelo.joblib` para as próximas vezes.

## Decisões de projeto

- **Redis** como fila por ser simples de rodar via Docker e já ter sido usado no
  laboratório da Aula 8 (comandos `RPUSH`/`BLPOP`), sem precisar de um broker mais
  pesado (RabbitMQ, Kafka) para o escopo do trabalho.
- **REST e gRPC compartilham o mesmo `modelo.py`**, cada um carregando sua própria
  instância na subida do processo — garante que os dois protocolos produzam exatamente
  o mesmo resultado para o mesmo texto, sem duplicar lógica de inferência.
- **Retry + dead-letter no worker**, em vez de deixar a tarefa perdida silenciosamente
  em caso de falha: até 3 tentativas, e se persistir o erro, a tarefa vai para uma fila
  separada (`tarefas_descartadas`) para investigação posterior, e o cliente consegue ver
  pelo `GET /resultado/{id}` que a tarefa falhou (`status: "falhou"`).
