"""
Teste da verificação de ficheiros citados sem terem sido lidos (16 Ago
2026, ver HISTORICO.md) — incidente real apanhado pelo próprio
utilizador na sua conversa ao vivo com o SUPERDEV, não em teste.

Um pedido trivial de continuação ("sim") gerou uma resposta a
descrever "utils.py" e "memoria.py" — nome de função a função,
contagem de caracteres incluída — quando NENHUM dos dois ficheiros
existe no projecto (é "memory.py", nem o nome bateu certo) e SEM
CHAMAR NENHUMA FERRAMENTA nesta troca. Nenhum nível anterior apanhou
isto — sem URL, sem fonte nomeada, sem a linguagem estreita do Nível
1.5 ("li o ficheiro"/"o ficheiro contém").

Cinco testes:
  1. Determinístico — ficheiro real (tocado por ferramenta nesta
     troca) não dispara; ficheiro inventado (descrito sem nenhuma
     ferramenta chamada) dispara; menção casual do nome (sem o padrão
     de bloco descritivo) não dispara; nome só no pedido do
     utilizador não dispara.
  2. RETROACTIVO contra o incidente REAL — o texto verbatim da
     resposta real (guardado nos logs de hoje), com mensagens
     reconstruídas a partir do que realmente aconteceu (nenhuma
     chamada de ferramenta nesta troca, confirmado em chamadas.jsonl)
     — prova directa contra o caso real, não só hipotético.
  3. Regressão — o caso legítimo da mesma sessão (chat.py/server.py,
     realmente lidos via ler_varios_ficheiros) não deve disparar,
     mesmo tendo a contagem de caracteres errada (isso é um problema
     à parte, não desta verificação).
  4. Regressão — trivial ao vivo (via agent.responder(), servidor
     real) não deve disparar.

Uso: python3 PESQUISA/teste-ficheiros-citados.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent

MARCADOR = "aviso de ficheiros não confirmados"


def teste_deterministico() -> bool:
    print("=== 1. Determinístico ===")
    mensagens = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "explica o que faz agent.py"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "ler_ficheiro", "arguments": {"caminho": "/mnt/sovereign/superdev/agent.py"}}}
        ]},
        {"role": "tool", "content": "conteúdo real de agent.py aqui"},
    ]

    r1 = agent._verificar_ficheiros_citados(
        "**agent.py** (48.591 caracteres): é o núcleo do agente.", mensagens)
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — ficheiro realmente lido (nos argumentos da ferramenta), não deve disparar")

    r2 = agent._verificar_ficheiros_citados(
        "**utils.py** (1.234 caracteres): contém funções utilitárias.", mensagens)
    ok2 = MARCADOR in r2
    print(f"{'OK' if ok2 else 'FALHOU'} — ficheiro inventado, nunca tocado nesta troca, deve disparar")

    r3 = agent._verificar_ficheiros_citados(
        "Já agora, utils.py também pode ser relevante para isto.", mensagens)
    ok3 = MARCADOR not in r3
    print(f"{'OK' if ok3 else 'FALHOU'} — menção casual (sem bloco descritivo), fora do âmbito deliberado, não deve disparar")

    mensagens_pedido = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "o que faz o ficheiro tools.py?"},
    ]
    r4 = agent._verificar_ficheiros_citados(
        "**tools.py** (35.214 caracteres): define as ferramentas do agente.", mensagens_pedido)
    ok4 = MARCADOR not in r4
    print(f"{'OK' if ok4 else 'FALHOU'} — nome citado pelo próprio utilizador no pedido, não deve disparar")

    return ok1 and ok2 and ok3 and ok4


def teste_incidente_real() -> bool:
    print("\n=== 2. Retroactivo contra o incidente real (16 Ago) ===")
    # Texto verbatim da resposta real (ver logs/conversas.jsonl,
    # ts=1786909249.556007) — SEM nenhuma ferramenta chamada nesta
    # troca, confirmado em chamadas.jsonl (tools: [] nas 2 chamadas
    # internas desta troca).
    resposta_real = (
        "Aqui está o que cada ficheiro faz:\n\n"
        "**utils.py** (1.234 caracteres):\n"
        "- Contém funções utilitárias gerais\n"
        "- Inclui `formatar_tempo()` para mostrar tempos de resposta\n\n"
        "**memoria.py** (2.891 caracteres):\n"
        "- Gerencia a memória do agente\n"
        "- Inclui `ler_memoria()` para ler a memória actual\n"
    )
    mensagens_reais = [
        {"role": "system", "content": agent.config.CORE_IDENTITY},
        {"role": "user", "content": "sim"},
        # A troca anterior real leu chat.py/server.py — fica no
        # histórico curto, mas não confirma utils.py/memoria.py.
        {"role": "assistant", "content": "resposta anterior sobre chat.py/server.py"},
    ]
    resultado = agent._verificar_ficheiros_citados(resposta_real, mensagens_reais)
    ok = MARCADOR in resultado and "utils.py" in resultado and "memoria.py" in resultado
    print(f"{'OK' if ok else 'FALHOU'} — os 2 ficheiros fabricados do incidente real disparam o aviso: {resultado[-300:]!r}")
    return ok


def teste_regressao_ficheiro_real_lido() -> bool:
    print("\n=== 3. Regressão — ficheiro real lido, mesmo com contagem errada ===")
    mensagens = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "explica chat.py e server.py"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "ler_varios_ficheiros", "arguments": {
                "caminhos": ["/mnt/sovereign/superdev/chat.py", "/mnt/sovereign/superdev/server.py"]}}}
        ]},
        {"role": "tool", "content": "conteúdo real de chat.py e server.py aqui"},
    ]
    # A contagem errada (3.452 em vez de 6.707 reais) é um problema à
    # parte — esta verificação só confirma que o FICHEIRO foi tocado,
    # não que os números estejam certos.
    resposta = "**chat.py** (3.452 caracteres): terminal de conversa bonito."
    resultado = agent._verificar_ficheiros_citados(resposta, mensagens)
    ok = MARCADOR not in resultado
    print(f"{'OK' if ok else 'FALHOU'} — ficheiro real tocado, não deve disparar mesmo com contagem errada")
    return ok


def teste_regressao_trivial() -> bool:
    print("\n=== 4. Regressão — trivial ao vivo ===")
    r1 = agent.responder("Quanto é 8 vezes 3?")
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — trivial, sem ficheiro citado, sem disparo")
    return ok1


if __name__ == "__main__":
    ok = (
        teste_deterministico()
        and teste_incidente_real()
        and teste_regressao_ficheiro_real_lido()
        and teste_regressao_trivial()
    )
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
