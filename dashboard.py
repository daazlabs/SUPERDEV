"""
Dashboard web do SUPERLLMLOCAL — "espião" do agente (17 Ago 2026).

Visão geral de tokens, tempo de resposta, avisos de confabulação,
pedidos por dia, chat interactivo, e limpeza de logs. Tudo num único
ficheiro FastAPI que lê os JSONL que o agente já gera
(chamadas.jsonl, conversas.jsonl, revisoes.jsonl).

Uso:
  python3 dashboard.py                # http://0.0.0.0:8852
  python3 dashboard.py --porta 9999   # porta à escolha

Dependências: fastapi, uvicorn (já instalados — server.py usa-os).
"""
import asyncio
import datetime
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import agent
import config

PORTA = 8852
_executor = ThreadPoolExecutor(max_workers=1)

app = FastAPI(title="SUPERLLMLOCAL Dashboard")

# Servir ficheiros estáticos (o próprio dashboard.html)
_stativos = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_stativos):
    app.mount("/static", StaticFiles(directory=_stativos), name="static")


# ---------------------------------------------------------------------------
# Helpers — leitura e agregação de logs
# ---------------------------------------------------------------------------

def _ler_jsonl(caminho: str) -> list[dict]:
    """Lê um ficheiro JSONL e devolve lista de dicts. Vazio se não existir."""
    if not os.path.isfile(caminho):
        return []
    with open(caminho) as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def _ler_novas_voltas(pos_antes: int) -> list[dict]:
    """Lê o LOG_FILE a partir de `pos_antes` e devolve as voltas (chamadas ao
    modelo) registadas desde aí. Corre numa thread do executor — é E/S
    bloqueante e o /api/chat não pode travar o event loop com ela."""
    voltas = []
    if not os.path.isfile(config.LOG_FILE):
        return voltas
    with open(config.LOG_FILE) as f:
        f.seek(pos_antes)
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registo = json.loads(linha)
            except json.JSONDecodeError:
                continue
            ferramentas = [fp["nome"] for fp in (registo.get("ferramentas_pedidas") or [])]
            voltas.append({
                "tokens_entrada": registo.get("prompt_eval_count") or 0,
                "tokens_saida": registo.get("eval_count") or 0,
                "tempo_s": round(registo.get("tempo_medido_end_to_end_s") or 0, 2),
                "pediu_ferramenta": registo.get("pediu_ferramenta", False),
                "ferramentas": ferramentas,
            })
    return voltas


_UTC = datetime.timezone.utc


def _ts_para_dia(ts: float) -> str:
    """Timestamp float -> 'YYYY-MM-DD' no timezone local."""
    return datetime.datetime.fromtimestamp(ts, tz=_UTC).strftime("%Y-%m-%d")


def _ts_para_hora(ts: float) -> str:
    """Timestamp float -> 'HH:MM' no timezone local."""
    return datetime.datetime.fromtimestamp(ts, tz=_UTC).strftime("%H:%M")


def _ler_revisoes() -> dict[float, dict]:
    """Indexa revisões por timestamp da troca."""
    return {r["timestamp"]: r for r in _ler_jsonl(config.REVISOES_LOG_FILE)}


def _agrupar_por_troca(chamadas: list[dict], conversas: list[dict]) -> list[dict]:
    """Junta chamadas (por volta) com conversas (por pedido) — mesma
    lógica do ver_diagnostico._agrupar_por_troca, replicada aqui para
    não dependender desse script."""
    LIMIAR = 900
    conv_ord = sorted(conversas, key=lambda d: d["timestamp"])
    cham_ord = sorted(chamadas, key=lambda d: d["timestamp"])

    trocas = []
    inicio_anterior = None
    i = 0
    for conv in conv_ord:
        fim = conv["timestamp"]
        tecto = fim - LIMIAR
        inicio = max(tecto, inicio_anterior) if inicio_anterior is not None else tecto
        grupo = []
        while i < len(cham_ord) and cham_ord[i]["timestamp"] <= fim:
            if cham_ord[i]["timestamp"] > inicio:
                grupo.append(cham_ord[i])
            i += 1
        trocas.append({"conversa": conv, "chamadas": grupo})
        inicio_anterior = fim
    return trocas


def _detectar_avisos(resposta: str) -> list[str]:
    """Lista os tipos de aviso presentes numa resposta.

    Cada categoria confere a tag curta nova (18 Ago 2026, ver
    verificacoes._aviso_curto — "[SUPERLLMLOCAL N1]" etc.) OU a frase
    verbosa antiga, para conversas já gravadas antes desta mudança
    continuarem a ser reconhecidas — sem isso, o histórico já em
    conversas.jsonl ficava com os avisos invisíveis no painel."""
    avisos = []
    if "atingi o limite de voltas" in resposta:
        avisos.append("LIMITE")
    if "[SUPERLLMLOCAL N1]" in resposta or "verificação automática de constantes citadas" in resposta:
        avisos.append("N1")
    if "[SUPERLLMLOCAL N1.5]" in resposta or "Nível 1.5" in resposta:
        avisos.append("N1.5")
    if "[SUPERLLMLOCAL URLS]" in resposta or "aviso de URLs não confirmados" in resposta:
        avisos.append("URLS")
    if "[SUPERLLMLOCAL FONTES]" in resposta or "aviso de fontes não confirmadas" in resposta:
        avisos.append("FONTES")
    if "[SUPERLLMLOCAL FICHEIROS]" in resposta or "aviso de ficheiros não confirmados" in resposta:
        avisos.append("FICHEIROS")
    if "[SUPERLLMLOCAL EXISTÊNCIA]" in resposta or "aviso de existência contraditada" in resposta:
        avisos.append("EXISTÊNCIA")
    if "verificação semântica Nível 2" in resposta:
        avisos.append("N2")
    if "percentagem não confirmada" in resposta:
        avisos.append("PCT")
    return avisos


# ---------------------------------------------------------------------------
# Endpoints da API
# ---------------------------------------------------------------------------

@app.get("/api/resumo")
def resumo():
    """KPIs gerais + dados para gráficos diários."""
    chamadas = _ler_jsonl(config.LOG_FILE)
    conversas = _ler_jsonl(config.CONVERSATION_LOG_FILE)
    revisoes = _ler_revisoes()
    trocas = _agrupar_por_troca(chamadas, conversas)

    hoje = datetime.datetime.now(tz=_UTC).date().isoformat()
    total_trocas = len(trocas)
    tokens_entrada_hoje = 0
    tokens_saida_hoje = 0
    tokens_entrada_total = 0
    tokens_saida_total = 0
    tempo_total = 0.0
    tempo_hoje = 0.0
    trocas_hoje = 0
    avisos_total = 0
    avisos_hoje = 0
    ferramentas_contagem: dict[str, int] = defaultdict(int)

    # Agregação diária para gráficos
    por_dia: dict[str, dict] = {}

    for t in trocas:
        conv = t["conversa"]
        resp = conv["resposta"]
        ts = conv["timestamp"]
        dia = _ts_para_dia(ts)
        chamadas_troca = t["chamadas"]

        tok_ent = sum(c.get("prompt_eval_count") or 0 for c in chamadas_troca)
        tok_sai = sum(c.get("eval_count") or 0 for c in chamadas_troca)
        tempo = sum(c.get("tempo_medido_end_to_end_s") or 0 for c in chamadas_troca)

        tokens_entrada_total += tok_ent
        tokens_saida_total += tok_sai
        tempo_total += tempo

        if dia not in por_dia:
            por_dia[dia] = {"tokens_entrada": 0, "tokens_saida": 0, "tempo_s": 0.0, "trocas": 0, "avisos": 0}
        por_dia[dia]["tokens_entrada"] += tok_ent
        por_dia[dia]["tokens_saida"] += tok_sai
        por_dia[dia]["tempo_s"] += tempo
        por_dia[dia]["trocas"] += 1

        avisos = _detectar_avisos(resp)
        if avisos:
            avisos_total += 1
            por_dia[dia]["avisos"] += 1

        if dia == hoje:
            tokens_entrada_hoje += tok_ent
            tokens_saida_hoje += tok_sai
            tempo_hoje += tempo
            trocas_hoje += 1
            if avisos:
                avisos_hoje += 1

        for c in chamadas_troca:
            for fp in c.get("ferramentas_pedidas") or []:
                ferramentas_contagem[fp["nome"]] += 1

    # Últimos 30 dias para o gráfico
    hoje_date = datetime.datetime.now(tz=_UTC).date()
    dias_30 = []
    for i in range(29, -1, -1):
        d = (hoje_date - datetime.timedelta(days=i)).isoformat()
        dados = por_dia.get(d, {"tokens_entrada": 0, "tokens_saida": 0, "tempo_s": 0.0, "trocas": 0, "avisos": 0})
        media_tempo = dados["tempo_s"] / dados["trocas"] if dados["trocas"] else 0
        dias_30.append({
            "dia": d,
            "tokens_entrada": dados["tokens_entrada"],
            "tokens_saida": dados["tokens_saida"],
            "trocas": dados["trocas"],
            "tempo_medio": round(media_tempo, 1),
            "avisos": dados["avisos"],
        })

    tempo_medio = tempo_total / total_trocas if total_trocas else 0
    revisadas = sum(1 for r in revisoes.values())
    acertos = sum(1 for r in revisoes.values() if r.get("veredito") == "acerto")
    falsos_pos = sum(1 for r in revisoes.values() if r.get("veredito") == "falso_positivo")

    return {
        "hoje": {
            "trocas": trocas_hoje,
            "tokens_entrada": tokens_entrada_hoje,
            "tokens_saida": tokens_saida_hoje,
            "tempo_medio": round(tempo_hoje / trocas_hoje, 1) if trocas_hoje else 0,
            "avisos": avisos_hoje,
        },
        "total": {
            "trocas": total_trocas,
            "tokens_entrada": tokens_entrada_total,
            "tokens_saida": tokens_saida_total,
            "tempo_medio": round(tempo_medio, 1),
            "avisos": avisos_total,
            "revisadas": revisadas,
            "acertos": acertos,
            "falsos_positivos": falsos_pos,
        },
        "dias_30": dias_30,
        "ferramentas": dict(sorted(ferramentas_contagem.items(), key=lambda x: -x[1])),
    }


@app.get("/api/pedidos")
def pedidos(dia: str = Query(None, description="Filtrar por dia YYYY-MM-DD")):
    """Lista de pedidos (trocas), com tokens/tempo/avisos. Devolve os
    últimos 100 por omissão, ou só os de um dia se dia for dado."""
    chamadas = _ler_jsonl(config.LOG_FILE)
    conversas = _ler_jsonl(config.CONVERSATION_LOG_FILE)
    revisoes = _ler_revisoes()
    trocas = _agrupar_por_troca(chamadas, conversas)

    resultado = []
    for t in trocas:
        conv = t["conversa"]
        ts = conv["timestamp"]
        dia_ts = _ts_para_dia(ts)
        if dia and dia_ts != dia:
            continue

        chamadas_troca = t["chamadas"]
        tok_ent = sum(c.get("prompt_eval_count") or 0 for c in chamadas_troca)
        tok_sai = sum(c.get("eval_count") or 0 for c in chamadas_troca)
        tempo = sum(c.get("tempo_medido_end_to_end_s") or 0 for c in chamadas_troca)
        avisos = _detectar_avisos(conv["resposta"])
        ferramentas = []
        for c in chamadas_troca:
            for fp in c.get("ferramentas_pedidas") or []:
                ferramentas.append(fp["nome"])

        revisao = revisoes.get(ts)
        resultado.append({
            "timestamp": ts,
            "hora": _ts_para_hora(ts),
            "dia": dia_ts,
            "pedido": conv["pedido"][:200],
            "tokens_entrada": tok_ent,
            "tokens_saida": tok_sai,
            "tempo_s": round(tempo, 1),
            "voltas": len(chamadas_troca),
            "ferramentas": list(set(ferramentas)),
            "avisos": avisos,
            "revisao": revisao["veredito"] if revisao else None,
        })

    # Mais recentes primeiro, limitar a 100 se não houver filtro
    resultado.sort(key=lambda x: -x["timestamp"])
    if not dia:
        resultado = resultado[:100]

    return resultado


@app.get("/api/pedidos/{timestamp}")
def ver_pedido(timestamp: float):
    """Conversa completa de um pedido (pergunta + resposta + breakdown
    por volta de ferramentas)."""
    chamadas = _ler_jsonl(config.LOG_FILE)
    conversas = _ler_jsonl(config.CONVERSATION_LOG_FILE)
    trocas = _agrupar_por_troca(chamadas, conversas)
    for t in trocas:
        conv = t["conversa"]
        if conv["timestamp"] == timestamp:
            voltas = []
            for c in t["chamadas"]:
                ferramentas = [
                    fp["nome"] for fp in (c.get("ferramentas_pedidas") or [])
                ]
                voltas.append({
                    "tokens_entrada": c.get("prompt_eval_count") or 0,
                    "tokens_saida": c.get("eval_count") or 0,
                    "tempo_s": round(c.get("tempo_medido_end_to_end_s") or 0, 2),
                    "pediu_ferramenta": c.get("pediu_ferramenta", False),
                    "ferramentas": ferramentas,
                })
            return {
                "timestamp": timestamp,
                "hora": _ts_para_hora(timestamp),
                "dia": _ts_para_dia(timestamp),
                "pedido": conv["pedido"],
                "resposta": conv["resposta"],
                "commit": conv.get("commit", "desconhecido"),
                "voltas": voltas,
            }
    return JSONResponse({"error": "troca não encontrada"}, status_code=404)


@app.post("/api/chat")
async def chat(pedido: dict):
    """Envia um pedido ao agente e devolve a resposta com tokens/tempo.
    Usa run_in_executor para não bloquear o event loop (agent.responder()
    é síncrono e pode demorar vários segundos). Lê o log DEPOIS da
    chamada para extrair os tokens por volta."""
    texto = (pedido.get("pedido") or "").strip()
    if not texto:
        return JSONResponse({"error": "pedido vazio"}, status_code=400)

    pos_antes = os.path.getsize(config.LOG_FILE) if os.path.isfile(config.LOG_FILE) else 0
    loop = asyncio.get_event_loop()
    sessao = agent.nova_sessao()
    t0 = time.time()
    resposta = await loop.run_in_executor(_executor, agent.responder, texto, sessao)
    duracao = time.time() - t0

    voltas = await loop.run_in_executor(_executor, _ler_novas_voltas, pos_antes)

    tok_ent = sum(v["tokens_entrada"] for v in voltas)
    tok_sai = sum(v["tokens_saida"] for v in voltas)
    return {
        "resposta": resposta,
        "tokens_entrada": tok_ent,
        "tokens_saida": tok_sai,
        "tempo_s": round(duracao, 1),
        "voltas": voltas,
    }


@app.get("/api/avisos")
def avisos():
    """Todas as trocas com algum aviso, com veredito humano se existir."""
    chamadas = _ler_jsonl(config.LOG_FILE)
    conversas = _ler_jsonl(config.CONVERSATION_LOG_FILE)
    revisoes = _ler_revisoes()
    trocas = _agrupar_por_troca(chamadas, conversas)

    resultado = []
    for t in trocas:
        conv = t["conversa"]
        avisos = _detectar_avisos(conv["resposta"])
        if not avisos:
            continue
        ts = conv["timestamp"]
        revisao = revisoes.get(ts)
        resultado.append({
            "timestamp": ts,
            "hora": _ts_para_hora(ts),
            "dia": _ts_para_dia(ts),
            "pedido": conv["pedido"][:300],
            "resposta": conv["resposta"][:500],
            "avisos": avisos,
            "voltas": len(t["chamadas"]),
            "revisao": revisao["veredito"] if revisao else None,
        })

    resultado.sort(key=lambda x: -x["timestamp"])
    return resultado


@app.post("/api/revisao")
def gravar_revisao(dados: dict):
    """Grava veredito humano (acerto/falso_positivo) para uma troca."""
    ts = dados.get("timestamp")
    veredito = dados.get("veredito")
    if not ts or veredito not in ("acerto", "falso_positivo"):
        return JSONResponse({"error": "timestamp e veredito ('acerto'/'falso_positivo') obrigatórios"}, status_code=400)

    revisoes = _ler_revisoes()
    revisao = revisoes.get(ts)
    registo = {
        "timestamp": ts,
        "commit": revisao.get("commit", "desconhecido") if revisao else "desconhecido",
        "marcas": [],
        "veredito": veredito,
        "revisado_em": time.time(),
    }
    os.makedirs(os.path.dirname(config.REVISOES_LOG_FILE), exist_ok=True)
    with open(config.REVISOES_LOG_FILE, "a") as f:
        f.write(json.dumps(registo, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.post("/api/limpar")
def limpar_logs(dados: dict):
    """Apaga linhas dos 3 JSONL anteriores a uma data (YYYY-MM-DD).
    Reescreve os ficheiros sem essas linhas. Confirma antes de chamar."""
    data_str = dados.get("antes_de")
    if not data_str:
        return JSONResponse({"error": "campo 'antes_de' (YYYY-MM-DD) obrigatório"}, status_code=400)

    try:
        corte = datetime.datetime.strptime(data_str, "%Y-%m-%d").replace(tzinfo=_UTC).timestamp()
    except ValueError:
        return JSONResponse({"error": "formato de data inválido (YYYY-MM-DD)"}, status_code=400)

    stats = {"chamadas": 0, "conversas": 0, "revisoes": 0}

    for caminho, chave in [
        (config.LOG_FILE, "chamadas"),
        (config.CONVERSATION_LOG_FILE, "conversas"),
        (config.REVISOES_LOG_FILE, "revisoes"),
    ]:
        if not os.path.isfile(caminho):
            continue
        with open(caminho) as f:
            linhas = f.readlines()
        novas = []
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registo = json.loads(linha)
                if registo.get("timestamp", 0) >= corte:
                    novas.append(linha)
            except json.JSONDecodeError:
                novas.append(linha)  # linha inválida, manter por segurança

        removidas = len(linhas) - len(novas)
        stats[chave] = removidas
        with open(caminho, "w") as f:
            f.write("\n".join(novas) + "\n" if novas else "")

    return {"ok": True, "removidas": stats}


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "dashboard.html")
    if os.path.isfile(html_path):
        with open(html_path) as f:
            return f.read()
    return "<h1>SUPERLLMLOCAL Dashboard</h1><p>dashboard.html não encontrado em static/</p>"


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    porta = PORTA
    if "--porta" in sys.argv:
        idx = sys.argv.index("--porta")
        if idx + 1 < len(sys.argv):
            porta = int(sys.argv[idx + 1])

    print(f"SUPERLLMLOCAL Dashboard — http://0.0.0.0:{porta}")
    uvicorn.run(app, host="0.0.0.0", port=porta)
