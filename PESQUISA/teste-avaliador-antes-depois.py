"""
Teste dos 2 gaps fechados no avaliador (16 Ago 2026, ver HISTORICO.md)
— a pedido explícito do utilizador ("avança! precisamos de testes"),
depois de ambas as peças terem sido validadas só por comandos
avulsos no terminal, não por um teste repetível como o resto do
projecto.

Cobre:
  1. agent._COMMIT_ATUAL bate certo com o HEAD real do git, e um
     pedido real (agent.responder()) grava esse commit em
     conversas.jsonl — prova ao vivo, não só a existência do campo.
  2. ver_diagnostico.analisar() agrega correctamente por commit
     (--por-commit) e cruza vereditos de logs/revisoes.jsonl com as
     trocas problemáticas (revisadas/acertos/falsos_positivos) —
     determinístico, com config.LOG_FILE/CONVERSATION_LOG_FILE/
     REVISOES_LOG_FILE trocados para ficheiros temporários (nunca
     mexe nos logs reais).
  3. revisar_avisos._gravar_revisao() escreve um registo que
     ver_diagnostico._carregar_revisoes() lê de volta sem perdas
     (ida e volta).

Uso: python3 PESQUISA/teste-avaliador-antes-depois.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import config
import ver_diagnostico
from revisar_avisos import _gravar_revisao


def teste_commit_real() -> bool:
    print("=== 1. Commit real (ao vivo) ===")
    head_real = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=config.BASE_DIR, capture_output=True, text=True, check=True,
    ).stdout.strip()
    ok1 = agent._COMMIT_ATUAL == head_real
    print(f"{'OK' if ok1 else 'FALHOU'} — agent._COMMIT_ATUAL ({agent._COMMIT_ATUAL}) bate com git rev-parse ({head_real})")

    agent.responder("Quanto é 2 mais 2?")
    with open(config.CONVERSATION_LOG_FILE) as f:
        ultima = json.loads(f.readlines()[-1])
    ok2 = ultima.get("commit") == agent._COMMIT_ATUAL
    print(f"{'OK' if ok2 else 'FALHOU'} — pedido real gravou o commit certo em conversas.jsonl")

    return ok1 and ok2


def teste_agregacao_por_commit(tmpdir: str) -> bool:
    print("\n=== 2. Agregação por commit (determinístico, ficheiros temporários) ===")
    config.LOG_FILE = os.path.join(tmpdir, "chamadas.jsonl")
    config.CONVERSATION_LOG_FILE = os.path.join(tmpdir, "conversas.jsonl")
    config.REVISOES_LOG_FILE = os.path.join(tmpdir, "revisoes.jsonl")

    # 2 trocas do commit "aaa111" (1 delas dispara Nível 1.5), 1 troca
    # do commit "bbb222" (limpa) — simula uma mudança de código a meio
    # do dia, o cenário exacto que o --por-commit existe para separar.
    with open(config.LOG_FILE, "w") as f:
        f.writelines(json.dumps(c) + "\n" for c in (
            {"timestamp": 100.0, "commit": "aaa111", "prompt_eval_count": 1000, "eval_count": 50, "tempo_medido_end_to_end_s": 2.0, "ferramentas_pedidas": []},
            {"timestamp": 200.0, "commit": "aaa111", "prompt_eval_count": 2000, "eval_count": 80, "tempo_medido_end_to_end_s": 3.0, "ferramentas_pedidas": []},
            {"timestamp": 300.0, "commit": "bbb222", "prompt_eval_count": 500, "eval_count": 30, "tempo_medido_end_to_end_s": 1.0, "ferramentas_pedidas": []},
        ))
    with open(config.CONVERSATION_LOG_FILE, "w") as f:
        f.writelines(json.dumps(c) + "\n" for c in (
            {"timestamp": 100.0, "commit": "aaa111", "pedido": "pedido limpo 1", "resposta": "resposta normal, sem aviso"},
            {"timestamp": 200.0, "commit": "aaa111", "pedido": "pedido suspeito", "resposta": "algo com [SUPERLLMLOCAL — aviso de fundamento (Nível 1.5)]"},
            {"timestamp": 300.0, "commit": "bbb222", "pedido": "pedido limpo 2", "resposta": "resposta normal, sem aviso"},
        ))

    resumo = ver_diagnostico.analisar()
    ok1 = resumo["total_trocas"] == 3
    print(f"{'OK' if ok1 else 'FALHOU'} — 3 trocas carregadas")

    por_commit = resumo["por_commit"]
    ok2 = por_commit.get("aaa111", {}).get("trocas") == 2 and por_commit.get("bbb222", {}).get("trocas") == 1
    print(f"{'OK' if ok2 else 'FALHOU'} — agrupadas certo por commit (aaa111=2, bbb222=1): {por_commit}")

    ok3 = por_commit["aaa111"]["avisos"] == 1 and por_commit["bbb222"]["avisos"] == 0
    print(f"{'OK' if ok3 else 'FALHOU'} — só a troca com Nível 1.5 conta como aviso, e fica no commit certo")

    ok4 = len(resumo["problematicas"]) == 1 and resumo["problematicas"][0]["commit"] == "aaa111"
    print(f"{'OK' if ok4 else 'FALHOU'} — a troca problemática identifica o commit onde aconteceu")

    return ok1 and ok2 and ok3 and ok4


def teste_revisoes(tmpdir: str) -> bool:
    print("\n=== 3. Veredito humano — ida e volta + cruzamento no resumo ===")
    # Continua a usar os ficheiros temporários do teste anterior — a
    # troca "aaa111"/200.0 é a única problemática, vamos revê-la.
    troca_fake = {
        "timestamp": 200.0, "commit": "aaa111",
        "bateu_limite": False, "nivel1": False, "nivel1_5": True,
        "urls": False, "fontes": False, "repetida": False,
    }
    _gravar_revisao(troca_fake, "falso_positivo")

    revisoes = ver_diagnostico._carregar_revisoes()
    ok1 = revisoes.get(200.0, {}).get("veredito") == "falso_positivo"
    print(f"{'OK' if ok1 else 'FALHOU'} — revisão gravada por _gravar_revisao lida de volta certa")

    resumo = ver_diagnostico.analisar()
    ok2 = resumo["revisadas"] == 1 and resumo["falsos_positivos"] == 1 and resumo["acertos"] == 0
    print(f"{'OK' if ok2 else 'FALHOU'} — resumo cruza o veredito certo (revisadas=1, falsos_positivos=1)")

    return ok1 and ok2


if __name__ == "__main__":
    log_file_original = config.LOG_FILE
    conversation_log_original = config.CONVERSATION_LOG_FILE
    revisoes_log_original = config.REVISOES_LOG_FILE

    ok_commit = teste_commit_real()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            ok_agregacao = teste_agregacao_por_commit(tmpdir)
            ok_revisoes = teste_revisoes(tmpdir)
        finally:
            # Nunca deixar os testes a apontar para os ficheiros reais,
            # mesmo que um teste falhe a meio.
            config.LOG_FILE = log_file_original
            config.CONVERSATION_LOG_FILE = conversation_log_original
            config.REVISOES_LOG_FILE = revisoes_log_original

    ok = ok_commit and ok_agregacao and ok_revisoes
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
