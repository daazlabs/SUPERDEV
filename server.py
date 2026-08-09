"""
Servidor HTTP compatível com a API da OpenAI (/v1/chat/completions,
/v1/models) — a "tomada adaptadora" para ligar interfaces de chat
prontas (Open WebUI, etc.) ao SUPERDEV sem alterar nada do agente.

ESTE FICHEIRO NÃO MEXE em agent.py/tools.py/config.py/pgmemory.py —
só importa `agent` e usa `agent.responder()`, exactamente como
`agent.main()` já fazia no modo de terminal. Corres os dois em
paralelo se quiseres (terminal + Open WebUI), são clientes
independentes da mesma lógica.

DECISÃO DE DESENHO — sessão única, ignora o histórico que o cliente
envia (9 Ago 2026): a API da OpenAI é "sem estado": o cliente
reenvia a conversa toda a cada pedido. O SUPERDEV já tem a sua
própria gestão de memória (janela curta + destilação para longo
prazo em pgmemory, ver agent.nova_sessao). Para não ter duas fontes
de verdade a competir, este servidor usa só a ÚLTIMA mensagem do
utilizador como pedido, e mantém UMA sessão persistente própria
(SESSAO) durante todo o tempo de vida do processo — mesmo que abras
uma "New Chat" no Open WebUI, a memória de longo prazo do SUPERDEV
continua a acumular por baixo. Ferramenta pessoal de um utilizador
só, não multi-utilizador — não vale a pena mais complexidade que
isto agora.

STREAMING — suporta os dois modos que a API pede (`stream: true/false`),
mas não é streaming real token-a-token: o agent.py chama a Ollama com
stream=False internamente (decisão já tomada e testada nesse
ficheiro), por isso quando o cliente pede stream=true devolvemos a
resposta inteira num único "pedaço" SSE, formatado como a API espera,
em vez de aparecer palavra a palavra. Suficiente para não bloquear/
dar erro no Open WebUI; não é "escrita em tempo real".
"""
import json
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

import agent
import config

PORTA = 8850

app = FastAPI()

# Sessão única, persistente enquanto o processo viver — ver decisão de
# desenho no cabeçalho do ficheiro.
SESSAO = agent.nova_sessao()


def _gastos_desde(pos_inicial: int) -> dict:
    """Lê só o que foi escrito no log DEPOIS de pos_inicial (bytes) e
    soma tokens/tempo — cobre também os pedidos que envolveram
    ferramentas (várias voltas = várias linhas de log para uma só
    resposta ao utilizador). Se o ficheiro ainda não existir, devolve
    zeros em vez de rebentar."""
    if not os.path.isfile(config.LOG_FILE):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    with open(config.LOG_FILE) as f:
        f.seek(pos_inicial)
        novas = f.readlines()
    prompt = sum(json.loads(linha).get("prompt_eval_count") or 0 for linha in novas)
    completion = sum(json.loads(linha).get("eval_count") or 0 for linha in novas)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


@app.get("/v1/models")
def listar_modelos():
    return {
        "object": "list",
        "data": [
            {"id": "superdev", "object": "model", "created": 0, "owned_by": "local"}
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    mensagens = body.get("messages", [])
    stream = bool(body.get("stream", False))

    pedido = ""
    for m in reversed(mensagens):
        if m.get("role") == "user":
            pedido = m.get("content", "")
            break
    if not pedido:
        return JSONResponse(
            {"error": "nenhuma mensagem 'user' encontrada no pedido"},
            status_code=400,
        )

    pos_antes = os.path.getsize(config.LOG_FILE) if os.path.isfile(config.LOG_FILE) else 0
    resposta = agent.responder(pedido, sessao=SESSAO)
    usage = _gastos_desde(pos_antes)

    agora = int(time.time())
    id_resposta = f"superdev-{agora}"

    if not stream:
        return {
            "id": id_resposta,
            "object": "chat.completion",
            "created": agora,
            "model": "superdev",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": resposta},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }

    def eventos():
        base = {
            "id": id_resposta,
            "object": "chat.completion.chunk",
            "created": agora,
            "model": "superdev",
        }
        abre = {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
        yield f"data: {json.dumps(abre, ensure_ascii=False)}\n\n"

        conteudo = {**base, "choices": [{"index": 0, "delta": {"content": resposta}, "finish_reason": None}]}
        yield f"data: {json.dumps(conteudo, ensure_ascii=False)}\n\n"

        fecha = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        yield f"data: {json.dumps(fecha, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    print(f"SUPERDEV — servidor compatível OpenAI em http://0.0.0.0:{PORTA}/v1")
    uvicorn.run(app, host="0.0.0.0", port=PORTA)
