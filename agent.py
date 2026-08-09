"""
SUPERDEV — agente especialista em programação, qwen3.5:9b via Ollama local.

Ciclo por pedido:
  1. recebe o pedido do utilizador
  2. vai buscar memória relevante (memory.retrieve)
  3. monta o contexto mínimo (núcleo + memória recuperada)
  4. chama o modelo, com as ferramentas disponíveis (tools.TOOL_DEFS)
  5. se o modelo pedir uma ferramenta, executa-a e volta a chamar com
     o resultado; senão devolve a resposta directa

Cada peça é uma função à parte, chamável directamente (ver o fundo do
ficheiro) — para testar/depurar um pedaço sem ter de correr o agente
todo.
"""
import json
import os
import time
import urllib.request

import config
import memory
import tools


def _log(registo: dict) -> None:
    """O 'espião' — uma linha JSON por pedido, nada é descartado."""
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    with open(config.LOG_FILE, "a") as f:
        f.write(json.dumps(registo, ensure_ascii=False) + "\n")


def ollama_chat(messages: list, ferramentas: list = None, memorias_usadas: list = None) -> dict:
    """Chama a Ollama e devolve a mensagem completa (não só o texto) —
    pode vir com 'content' (resposta directa) ou 'tool_calls' (pedido
    de ferramenta), consoante o modelo decidir.
    """
    body_dict = {
        "model": config.MODEL,
        "messages": messages,
        "options": config.OPTIONS,
        "think": config.THINK,
        "stream": False,
    }
    if ferramentas:
        body_dict["tools"] = ferramentas
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_HOST}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    tempo_total_medido = time.time() - t0

    # Regista tudo o que a Ollama nos dá de graça e que estávamos a
    # deitar fora: tokens de prompt vs. geração, tempos de cada fase,
    # e o que decidimos nós (options, think, memórias trazidas).
    _log({
        "timestamp": time.time(),
        "pedido_tamanho_chars": len(messages[-1]["content"]) if messages[-1].get("content") else 0,
        "system_tamanho_chars": len(messages[0]["content"]) if messages and messages[0]["role"] == "system" else 0,
        "memorias_usadas": memorias_usadas or [],
        "tinha_ferramentas": bool(ferramentas),
        "pediu_ferramenta": bool(data["message"].get("tool_calls")),
        "options": config.OPTIONS,
        "think": config.THINK,
        "thinking_tokens": len(data["message"].get("thinking", "")) if data["message"].get("thinking") else 0,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
        "load_duration_s": data.get("load_duration", 0) / 1e9,
        "prompt_eval_duration_s": data.get("prompt_eval_duration", 0) / 1e9,
        "eval_duration_s": data.get("eval_duration", 0) / 1e9,
        "total_duration_s": data.get("total_duration", 0) / 1e9,
        "tempo_medido_end_to_end_s": tempo_total_medido,
    })

    return data["message"]


def build_system_prompt(pedido: str):
    partes = [config.CORE_IDENTITY]
    relevantes = memory.retrieve(pedido)
    memorias_usadas = []
    if relevantes:
        partes.append("\n## Memória relevante para este pedido:")
        for score, fname, texto in relevantes:
            partes.append(f"- ({fname}, relevância {score:.2f}): {texto.strip()}")
            memorias_usadas.append({"ficheiro": fname, "score": round(score, 4)})
    return "\n".join(partes), memorias_usadas


# Limite de voltas de ferramentas por pedido — protecção contra ciclo
# infinito (o modelo a pedir ferramentas sem nunca chegar a uma
# resposta final). BUG REAL encontrado e corrigido 9 Ago 2026: antes
# disto, as "tools" só eram oferecidas na 1ª volta — um pedido que
# precisasse de duas ferramentas em sequência (ex: listar uma pasta e
# depois ler um ficheiro lá dentro) ficava sem resposta nenhuma na 2ª
# volta, porque o modelo queria pedir a 2ª ferramenta mas não lhe
# eram oferecidas. Confirmado com teste directo: oferecendo "tools"
# também na 2ª volta, o modelo pediu correctamente a 2ª ferramenta.
MAX_VOLTAS_FERRAMENTAS = 5


def responder(pedido: str) -> str:
    system, memorias_usadas = build_system_prompt(pedido)
    mensagens = [
        {"role": "system", "content": system},
        {"role": "user", "content": pedido},
    ]

    for _ in range(MAX_VOLTAS_FERRAMENTAS):
        mensagem = ollama_chat(mensagens, ferramentas=tools.TOOL_DEFS, memorias_usadas=memorias_usadas)

        if not mensagem.get("tool_calls"):
            return mensagem.get("content", "")

        mensagens.append(mensagem)
        for chamada in mensagem["tool_calls"]:
            nome = chamada["function"]["name"]
            args = chamada["function"]["arguments"]
            funcao = tools.FUNCOES.get(nome)
            if funcao:
                resultado = funcao(**args)
            else:
                resultado = f"[ERRO] ferramenta desconhecida: {nome}"
            mensagens.append({"role": "tool", "content": resultado})

    return (
        "[ERRO] Excedi o limite de voltas de ferramentas "
        f"({MAX_VOLTAS_FERRAMENTAS}) sem chegar a uma resposta final."
    )


def main():
    print("SUPERDEV — escreve o teu pedido (Ctrl+C para sair)\n")
    while True:
        try:
            pedido = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not pedido:
            continue
        print(f"\n{responder(pedido)}\n")


if __name__ == "__main__":
    main()
