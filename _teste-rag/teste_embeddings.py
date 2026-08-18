"""
Teste isolado: a pesquisa por semelhança (embeddings) acerta na memória certa?
Não faz parte do agente final — é só para validar antes de confiarmos nisto.
"""
import json
import urllib.request

import numpy as np

OLLAMA = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"

# "memórias" fictícias, parecidas com o que seria memória real de projecto
memorias = [
    "O projecto DaazLeads usa PostgreSQL e tem 55 mil empresas publicadas na base de dados.",
    "O bug do dashboard ASSIST era porta 18791 a colidir com o browser-control do DEV, corrigido movendo para 18800.",
    "O utilizador prefere respostas em português com analogias antes do código técnico.",
    "O DaazNexus corre em Electron e teve um bug em que perdia a resposta ao navegar entre páginas.",
    "A GPU da máquina tem 12GB de VRAM partilhada entre vários serviços, é preciso gerir com cuidado.",
]

perguntas = [
    "qual é a base de dados que o DaazLeads usa?",
    "porque é que a GPU anda sempre cheia?",
]

def embed(texto):
    body = json.dumps({"model": MODEL, "prompt": texto}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return np.array(json.loads(r.read())["embedding"])

def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

print("A gerar embeddings das 5 memórias...")
vecs_memorias = [embed(m) for m in memorias]

for pergunta in perguntas:
    print(f"\n--- Pergunta: {pergunta}")
    v = embed(pergunta)
    scores = [(cosine(v, vm), m) for vm, m in zip(vecs_memorias, memorias)]
    scores.sort(reverse=True)
    for score, memoria in scores:
        print(f"  {score:.4f}  {memoria}")
