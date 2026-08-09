"""
Visualizador do 'espião' (logs/chamadas.jsonl), para testar o agente à
mão sem ter de ler JSON em bruto.

Uso:
  python3 ver_logs.py            # mostra as últimas 10 chamadas
  python3 ver_logs.py 30         # mostra as últimas 30
  python3 ver_logs.py --seguir   # fica a acompanhar em tempo real
                                  # (corre isto numa 2ª janela enquanto
                                  # conversas com `python3 agent.py`
                                  # na 1ª)
"""
import json
import os
import sys
import time

import config


def _formatar(d: dict) -> str:
    hora = time.strftime("%H:%M:%S", time.localtime(d["timestamp"]))
    ferramenta = "chamou ferramenta" if d["pediu_ferramenta"] else "resposta final"
    return (
        f"[{hora}] {ferramenta:<18} | "
        f"tokens: {d.get('prompt_eval_count', '?'):>4} entrada + "
        f"{d.get('eval_count', '?'):>4} saída | "
        f"tempo: {d.get('tempo_medido_end_to_end_s', 0):>6.2f}s "
        f"(geração {d.get('eval_duration_s', 0):.2f}s) | "
        f"memórias usadas: {len(d.get('memorias_usadas', []))}"
    )


def mostrar_ultimas(n: int) -> None:
    if not os.path.isfile(config.LOG_FILE):
        print(f"[ainda não há log em {config.LOG_FILE}]")
        return
    with open(config.LOG_FILE) as f:
        linhas = f.readlines()[-n:]
    for linha in linhas:
        print(_formatar(json.loads(linha)))


def seguir() -> None:
    """Modo 'tail -f' à mão — não assume que o ficheiro já existe no
    arranque (pode ainda não ter havido nenhuma chamada)."""
    print("A acompanhar novas chamadas (Ctrl+C para sair)...\n")
    pos = 0
    if os.path.isfile(config.LOG_FILE):
        pos = os.path.getsize(config.LOG_FILE)
    try:
        while True:
            if os.path.isfile(config.LOG_FILE):
                with open(config.LOG_FILE) as f:
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
