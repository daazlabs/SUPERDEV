"""
Teste ao vivo do Nível "1.5" do anti-confabulação (13 Ago 2026, ver
HISTORICO.md e o comentário junto a verificacoes.verificar_fundamento_categorias).

Corre agent.responder() a sério (chama a Ollama de verdade, não é
unitário) em 3 casos:

  1. REPRODUÇÃO DO INCIDENTE REAL — o pedido exacto de pesquisa do
     DAAZPRIME que, antes desta correcção, gerou um relatório com
     afirmações sobre "Google AI Overview"/"ChatGPT" sem nunca chamar
     pesquisar_web. Deve agora disparar o aviso de fundamento.
  2. PESQUISA WEB REAL — pesquisar_web é mesmo chamado; a resposta
     fala de resultados de pesquisa legitimamente. NÃO deve disparar
     (falso positivo).
  3. LEITURA DE FICHEIRO REAL — ler_ficheiro é mesmo chamado. NÃO deve
     disparar.

Uso: python3 PESQUISA/teste-nivel15-fundamento.py
(demora alguns minutos — são 3 chamadas reais à Ollama local)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent

MARCADOR = "SUPERLLMLOCAL N1.5"

PEDIDO_DAAZPRIME_REAL = (
    "You are starting a new research round for the DAAZPRIME project. You have NO prior\n"
    "context. Read the files below before doing anything else.\n\n"
    "STEP 1 — READ, IN THIS ORDER (do not skip any):\n"
    "  1. /home/daazlabs/projects/daazprime/PESQUISA/RONDA3-COMPARACAO-FINANCEIRA/BRIEFING.md\n"
    "     — read it ALL, especially \"Território proibido\", \"A ideia a testar nesta ronda\",\n"
    "       and task \"R1 — Procura real em Portugal\"\n"
    "  2. /home/daazlabs/projects/daazprime/PESQUISA/r5-red-team.md\n"
    "     — this explains which strategies were already killed in the previous round and why.\n"
    "       Do not resurrect them.\n\n"
    "STEP 2 — EXECUTE TASK R1 exactly as specified in BRIEFING.md.\n\n"
    "The three things that matter most, restated here so you cannot miss them:\n\n"
    "  RULE 1 — DEMAND FIRST. Report nothing without EVIDENCE that people in Portugal are\n"
    "  already actively asking about this: repeated forum questions, existing products with\n"
    "  real customers, complaints about PPR/Certificados de Aforro fees or misleading returns.\n"
    "  \"This would be useful\" is not evidence.\n\n"
    "  RULE 2 — THE GOOGLE/AI FILTER. For the core question (\"PPR vale a pena tendo em conta a\n"
    "  inflação?\" and close variants), actually test whether Google AI Overview / ChatGPT /\n"
    "  Gemini / Perplexity already answer it well. If yes, say so clearly — do not soften it.\n\n"
    "  RULE 3 — SCOPE. This is about generic comparison/education content only — never\n"
    "  personalized investment advice to a specific person. Do NOT research CMVM licensing\n"
    "  cost/process (out of scope this round). The site stays in English for now — Portugal is\n"
    "  the pilot TOPIC, not a language change. Do not assume translation is happening.\n\n"
    "OUTPUT: /home/daazlabs/projects/daazprime/PESQUISA/RONDA3-COMPARACAO-FINANCEIRA/r1-procura-real.md\n\n"
    "WRITE INCREMENTALLY. Create the output file early, append each finding as you confirm\n"
    "it, and keep it valid at all times so a partial report is still useful if you run out of\n"
    "budget. Do not hold results in memory until the end.\n\n"
    "Cite a URL for every claim; write \"NÃO CONFIRMADO\" where you cannot. Quote real people\n"
    "verbatim where possible. Be brutally honest — \"I searched hard and found no unmet demand\n"
    "that survives the Google filter\" is a VALID and valuable result. Do not flatter the idea."
)


def correr():
    print("=== 1. Reprodução do incidente real (DAAZPRIME) — deve DISPARAR ===")
    r1 = agent.responder(PEDIDO_DAAZPRIME_REAL)
    disparou_1 = MARCADOR in r1
    print(f"{'OK' if disparou_1 else 'FALHOU'} — aviso presente: {disparou_1}")

    print("\n=== 2. Pesquisa web real — NÃO deve disparar ===")
    r2 = agent.responder("Pesquisa na web quais são as últimas notícias sobre o modelo Qwen 3.5.")
    disparou_2 = MARCADOR in r2
    print(f"{'OK' if not disparou_2 else 'FALHOU'} — aviso presente: {disparou_2}")

    print("\n=== 3. Leitura de ficheiro real — NÃO deve disparar ===")
    r3 = agent.responder("Lê o ficheiro /mnt/sovereign/superllmlocal/config.py e diz-me quantas linhas tem.")
    disparou_3 = MARCADOR in r3
    print(f"{'OK' if not disparou_3 else 'FALHOU'} — aviso presente: {disparou_3}")

    ok = disparou_1 and not disparou_2 and not disparou_3
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'} — ver detalhe acima.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if correr() else 1)
