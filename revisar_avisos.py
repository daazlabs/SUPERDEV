"""
Revisão manual dos avisos mecânicos (16 Ago 2026, ver HISTORICO.md) —
fecha o gap "sabemos que dispara, não se acerta" apontado pelo
utilizador ao perguntar se o SUPERLLMLOCAL está a progredir ou regredir.

ver_diagnostico.py só conta QUANTAS VEZES um aviso disparou — nunca se
a suspeita estava certa. Um aviso pode disparar sobre uma resposta que
estava genuinamente errada (acerto) ou sobre uma que estava certa mas
só não tinha a fonte agarrada nesta troca específica (falso positivo).
Só um humano a ler o pedido+resposta reais sabe distinguir isto.

Percorre as trocas com algum sinal (mesmo critério do
ver_diagnostico.py --detalhe) que ainda não têm veredito gravado, uma
de cada vez, e pede um veredito curto. Grava em
config.REVISOES_LOG_FILE, indexado pelo timestamp da troca — não
mexe nos logs originais (chamadas.jsonl/conversas.jsonl ficam
intocados, mesmo princípio do CONVERSATION_LOG_FILE: ficheiro à parte
para o que é mais sensível/opinativo).

Uso:
  python3 revisar_avisos.py
"""
import datetime
import json
import os
import sys
import time

import config
from ver_diagnostico import _carregar_revisoes, analisar


def _gravar_revisao(troca: dict, veredito: str) -> None:
    registo = {
        "timestamp": troca["timestamp"],
        "commit": troca["commit"],
        "marcas": [m for m, presente in (
            ("LIMITE", troca["bateu_limite"]), ("N1", troca["nivel1"]),
            ("N1.5", troca["nivel1_5"]), ("URLS", troca["urls"]),
            ("FONTES", troca["fontes"]), ("REPETIU", troca["repetida"]),
        ) if presente],
        "veredito": veredito,
        "revisado_em": time.time(),
    }
    os.makedirs(os.path.dirname(config.REVISOES_LOG_FILE), exist_ok=True)
    with open(config.REVISOES_LOG_FILE, "a") as f:
        f.write(json.dumps(registo, ensure_ascii=False) + "\n")


def main() -> None:
    resumo = analisar()
    ja_revistas = set(_carregar_revisoes().keys())
    por_rever = [p for p in resumo["problematicas"] if p["timestamp"] not in ja_revistas]

    if not por_rever:
        print("Nada por rever — todas as trocas com aviso já têm veredito.")
        return

    print(f"{len(por_rever)} trocas com aviso por rever. "
          "Para cada uma: [a]certo, [f]also positivo, [s]altar, [q]sair.\n")

    revistas_agora = 0
    for troca in por_rever:
        quando = datetime.datetime.fromtimestamp(troca["timestamp"]).strftime("%d %b %H:%M")
        marcas = ",".join(m for m, presente in (
            ("LIMITE", troca["bateu_limite"]), ("N1", troca["nivel1"]),
            ("N1.5", troca["nivel1_5"]), ("URLS", troca["urls"]),
            ("FONTES", troca["fontes"]), ("REPETIU", troca["repetida"]),
        ) if presente)
        print("=" * 70)
        print(f"[{quando}] commit={troca['commit']} marcas={marcas} ({troca['voltas']} voltas)")
        print(f"\nPEDIDO:\n{troca['pedido'][:800]}")
        print(f"\nRESPOSTA:\n{troca['resposta'][:1500]}")
        print()
        while True:
            escolha = input("Veredito [a/f/s/q]: ").strip().lower()
            if escolha in ("a", "acerto"):
                _gravar_revisao(troca, "acerto")
                revistas_agora += 1
                break
            if escolha in ("f", "falso_positivo", "falso"):
                _gravar_revisao(troca, "falso_positivo")
                revistas_agora += 1
                break
            if escolha in ("s", "saltar"):
                break
            if escolha in ("q", "sair"):
                print(f"\nParado. {revistas_agora} trocas revistas nesta sessão.")
                sys.exit(0)
            print("Não percebi — usa a, f, s ou q.")

    print(f"\nFeito. {revistas_agora} trocas revistas nesta sessão.")


if __name__ == "__main__":
    main()
