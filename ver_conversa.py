"""
Leitor da conversa real (logs/conversas.jsonl) — só para a fase de
testes (9 Ago 2026, a pedido do utilizador). Complementa o
ver_logs.py: esse mostra métricas (tokens/tempo/ferramentas), este
mostra o que foi dito de facto, para reler ou analisar depois.

Uso:
  python3 ver_conversa.py            # últimas 10 trocas
  python3 ver_conversa.py 30         # últimas 30
  python3 ver_conversa.py --seguir   # acompanha em tempo real

Para desligar esta gravação no fim da fase de testes: apagar a
chamada a _log(..., caminho=config.CONVERSATION_LOG_FILE) em
agent.py responder(), e o ficheiro logs/conversas.jsonl.
"""
import json
import os
import sys
import time

import config


def _formatar(d: dict) -> str:
    hora = time.strftime("%H:%M:%S", time.localtime(d["timestamp"]))
    return (
        f"\n[{hora}]\n"
        f"Tu: {d['pedido']}\n"
        f"SUPERLLMLOCAL: {d['resposta']}\n"
        f"{'─' * 60}"
    )


def mostrar_ultimas(n: int) -> None:
    if not os.path.isfile(config.CONVERSATION_LOG_FILE):
        print(f"[ainda não há conversas gravadas em {config.CONVERSATION_LOG_FILE}]")
        return
    with open(config.CONVERSATION_LOG_FILE) as f:
        linhas = f.readlines()[-n:]
    for linha in linhas:
        print(_formatar(json.loads(linha)))


def seguir() -> None:
    print("A acompanhar a conversa (Ctrl+C para sair)...\n")
    pos = 0
    if os.path.isfile(config.CONVERSATION_LOG_FILE):
        pos = os.path.getsize(config.CONVERSATION_LOG_FILE)
    try:
        while True:
            if os.path.isfile(config.CONVERSATION_LOG_FILE):
                with open(config.CONVERSATION_LOG_FILE) as f:
                    f.seek(pos)
                    novas = f.readlines()
                    pos = f.tell()
                for linha in novas:
                    print(_formatar(json.loads(linha)))
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    if "--seguir" in sys.argv:
        seguir()
    else:
        n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
        mostrar_ultimas(n)
