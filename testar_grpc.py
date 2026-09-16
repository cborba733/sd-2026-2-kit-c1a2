import grpc

import inferencia_pb2
import inferencia_pb2_grpc


def main():
    canal = grpc.insecure_channel("localhost:50051")
    stub = inferencia_pb2_grpc.InferenciaStub(canal)

    pedido = inferencia_pb2.PedidoLote(
        textos=[
            "gol do flamengo no ultimo minuto",
            "que jogo horrivel, time sem criatividade",
            "empate sem graca, nada aconteceu",
        ]
    )
    resposta = stub.PreverLote(pedido)

    for r in resposta.resultados:
        print(f"{r.texto!r} -> {r.sentimento} (confianca={r.confianca:.4f})")


if __name__ == "__main__":
    main()