"""
Worker: consome a fila e executa a inferencia.

O QUE JA ESTA PRONTO: o laco principal e o carregamento do modelo.
O QUE VOCE PRECISA FAZER (TAREFAS.md, itens 3 e 5):
  - guardar o resultado ao terminar
  - tratar erro com retentativa e fila de descarte (dead-letter)

Rodar:  python -m app.worker
Suba mais de um worker em terminais diferentes e veja a carga se dividir.
"""
import time

from app import fila
from app.modelo import carregar_modelo

MAX_TENTATIVAS = 3


def main():
    print("[worker] carregando modelo...")
    modelo = carregar_modelo()
    print("[worker] pronto. aguardando tarefas (Ctrl+C para sair)")

    while True:
        tarefa = fila.proxima_tarefa(timeout=5)
        if tarefa is None:
            continue

        print(f"[worker] processando {tarefa['id']}")

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            inicio = time.time()
            try:
                resultado = modelo.prever(tarefa["texto"])
                resultado["status"] = "pronto"
                resultado["tempo_ms"] = round((time.time() - inicio) * 1000, 2)

                # TAREFA 3: guarda o resultado para o cliente consultar depois.
                fila.guardar_resultado(tarefa["id"], resultado)
                print(f"[worker] concluido {tarefa['id']}")
                break  # deu certo, nao precisa tentar de novo

            except Exception as erro:  # noqa: BLE001
                print(f"[worker] ERRO em {tarefa['id']} "
                      f"(tentativa {tentativa}/{MAX_TENTATIVAS}): {erro}")

                if tentativa == MAX_TENTATIVAS:
                    # esgotou as tentativas: manda pra fila de descarte
                    fila.descartar(tarefa, str(erro))
                    fila.guardar_resultado(
                        tarefa["id"],
                        {"status": "falhou", "erro": str(erro)},
                    )
                    print(f"[worker] {tarefa['id']} descartada "
                          f"apos {MAX_TENTATIVAS} tentativas")
                else:
                    time.sleep(1)  # espera um pouco antes de tentar de novo


if __name__ == "__main__":
    main()