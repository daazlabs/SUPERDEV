"""
SUPERDEV — agente especialista em programação, qwen3.5:9b via Ollama local.

Ciclo por pedido:
  1. recebe o pedido do utilizador
  2. vai buscar memória relevante (pgmemory.retrieve, isolado por tenant)
  3. monta o contexto mínimo (núcleo + memória recuperada)
  4. chama o modelo, com as ferramentas disponíveis (tools.TOOL_DEFS)
  5. se o modelo pedir uma ferramenta, executa-a e volta a chamar com
     o resultado; senão devolve a resposta directa

Cada peça é uma função à parte, chamável directamente (ver o fundo do
ficheiro) — para testar/depurar um pedaço sem ter de correr o agente
todo.

MEMÓRIA (9 Ago 2026) — passou de ficheiros (memory.py) para Postgres+
pgvector (pgmemory.py), testado e calibrado nesse dia (ver
HISTORICO.md). memory.py/memory/*.md ficam como registo histórico e
motor de referência, mas já não são o que o agente usa ao vivo.
"""
import json
import os
import time
import urllib.request

import config
import pgmemory
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


def build_system_prompt(pedido: str, tenant_id: str = None):
    tenant_id = tenant_id or config.TENANT_PADRAO
    partes = [config.CORE_IDENTITY]
    relevantes = pgmemory.retrieve(pedido, tenant_id=tenant_id)
    memorias_usadas = []
    if relevantes:
        partes.append("\n## Memória relevante para este pedido:")
        for score, id_, texto in relevantes:
            partes.append(f"- (id={id_}, relevância {score:.2f}): {texto.strip()}")
            memorias_usadas.append({"id": id_, "score": round(score, 4)})
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


def nova_sessao(tenant_id: str = None) -> dict:
    """Estado de uma conversa (9 Ago 2026). Três campos:
      - "tenant_id": de que cliente é esta conversa — nunca lê nem
        grava memória fora deste tenant (isolamento testado em
        HISTORICO.md). 'default' para uso pessoal/desenvolvimento.
      - "historico": janela de curto prazo, tamanho fixo
        (config.MEMORIA_CURTO_PRAZO_TROCAS), sempre enviada ao modelo
        para dar coerência à conversa actual. Desliza — trocas antigas
        saem daqui e desaparecem do prompt, mas não se perdem de vez
        (ver "buffer_destilar").
      - "buffer_destilar": acumula as mesmas trocas até chegar a
        config.MEMORIA_DESTILAR_A_CADA_TROCAS, altura em que são
        resumidas e gravadas em Postgres (pgmemory.store), sob o
        mesmo tenant_id desta sessão, e o buffer é limpo. Existe
        separado do "historico" precisamente para que uma troca não
        se perca sem ser avaliada para memória de longo prazo só
        porque já saiu da janela curta.
    """
    return {
        "tenant_id": tenant_id or config.TENANT_PADRAO,
        "historico": [],
        "buffer_destilar": [],
    }


def _destilar(buffer_destilar: list, tenant_id: str = None) -> None:
    """Pede ao próprio modelo para extrair, do excerto recente de
    conversa, só os factos concretos que valham a pena persistir.
    Mesmo princípio do PG_MEMORY_MIN_SCORE em pgmemory.py: se não
    houver nada relevante, o modelo pode (e deve) dizer 'NADA' —
    preferimos não gravar nada a gravar ruído com ar de importante.
    Grava sob o tenant_id da sessão — nunca mistura clientes."""
    tenant_id = tenant_id or config.TENANT_PADRAO
    # Instruções em inglês (o utilizador nunca vê este prompt), mas a
    # EXIGIR explicitamente que os factos saiam em português — testado
    # 9 Ago 2026: uma memória gravada em inglês partiu a pesquisa por
    # palavras-chave contra perguntas em português (ver HISTORICO.md).
    # O idioma da instrução é livre; o idioma do resultado guardado não.
    transcript = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Agent'}: {m['content']}"
        for m in buffer_destilar
    )
    prompt_destilacao = (
        "Here is a recent excerpt from a conversation. Extract ONLY "
        "facts about THE USER, THE PROJECT, or DECISIONS made in the "
        "conversation — things worth keeping specifically because "
        "they came from this conversation (stated preferences, "
        "project names/versions/data, choices made). NEVER extract "
        "general knowledge the model already knows anyway (capitals, "
        "definitions, public facts) — not worth storing, redundant.\n\n"
        "Example of what TO extract: user preference, project detail, "
        "explicit decision.\n"
        "Example of what NOT to extract: general/public knowledge "
        "unrelated to the user or this conversation.\n\n"
        "Write each fact as one short, self-contained sentence per "
        "line, IN EUROPEAN PORTUGUESE (Portugal, not Brazil) — the "
        "facts must be in Portuguese even though these instructions "
        "are in English, because they will be searched against future "
        "questions asked in Portuguese. Never invent anything not in "
        "the excerpt. If there is no fact about the user/project/"
        "decision worth keeping, respond exactly: NADA\n\n"
        f"--- conversation excerpt ---\n{transcript}"
    )
    mensagens = [
        {
            "role": "system",
            "content": (
                "Be extremely literal and concise. Do not elaborate, "
                "do not invent, do not repeat the instruction."
            ),
        },
        {"role": "user", "content": prompt_destilacao},
    ]
    resposta = ollama_chat(mensagens, memorias_usadas=[])
    texto = (resposta.get("content") or "").strip()
    if not texto or texto.upper() == "NADA":
        return
    for linha in texto.splitlines():
        linha = linha.strip("-• ").strip()
        if not linha or linha.upper() == "NADA":
            continue
        pgmemory.store(linha, tenant_id=tenant_id)


def responder(pedido: str, sessao: dict = None) -> str:
    """Sessao opcional — se não for dada, comporta-se como antes
    (sem memória de curto/longo prazo entre chamadas, cada pedido é
    uma ilha). Passar a mesma sessao entre chamadas é o que liga a
    conversa."""
    if sessao is None:
        sessao = nova_sessao()

    system, memorias_usadas = build_system_prompt(pedido, tenant_id=sessao["tenant_id"])
    janela = sessao["historico"][-(config.MEMORIA_CURTO_PRAZO_TROCAS * 2):]
    mensagens = [{"role": "system", "content": system}] + janela + [
        {"role": "user", "content": pedido}
    ]

    resposta = None
    for _ in range(MAX_VOLTAS_FERRAMENTAS):
        mensagem = ollama_chat(mensagens, ferramentas=tools.TOOL_DEFS, memorias_usadas=memorias_usadas)

        if not mensagem.get("tool_calls"):
            resposta = mensagem.get("content", "")
            break

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

    if resposta is None:
        resposta = (
            "[ERRO] Excedi o limite de voltas de ferramentas "
            f"({MAX_VOLTAS_FERRAMENTAS}) sem chegar a uma resposta final."
        )

    # Só o par pergunta/resposta final entra na memória de conversa —
    # o vaivém interno das ferramentas é descartado, era só andaime
    # para chegar a esta resposta, não vale a pena lembrar.
    troca = [
        {"role": "user", "content": pedido},
        {"role": "assistant", "content": resposta},
    ]
    sessao["historico"] = (sessao["historico"] + troca)[-(config.MEMORIA_CURTO_PRAZO_TROCAS * 2):]
    sessao["buffer_destilar"].extend(troca)

    if len(sessao["buffer_destilar"]) >= config.MEMORIA_DESTILAR_A_CADA_TROCAS * 2:
        _destilar(sessao["buffer_destilar"], tenant_id=sessao["tenant_id"])
        sessao["buffer_destilar"] = []

    return resposta


def main():
    print("SUPERDEV — escreve o teu pedido (Ctrl+C para sair)\n")
    sessao = nova_sessao()
    while True:
        try:
            pedido = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not pedido:
            continue
        print(f"\n{responder(pedido, sessao)}\n")


if __name__ == "__main__":
    main()
