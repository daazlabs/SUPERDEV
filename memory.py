"""
Memória por recuperação semântica (RAG mínimo).

Cada facto é um ficheiro .md dentro de memory/. Os embeddings são
calculados uma vez por facto (não a cada pedido — seria caro e lento)
e guardados num índice em memory/_index.json. Só se recalcula quando
o ficheiro é novo ou foi alterado.

AVISO — teste isolado feito antes de este ficheiro existir mostrou que
a recuperação por semelhança pode falhar: numa pergunta feita de forma
muito diferente da memória escrita, a memória certa ficou em 2º lugar,
por uma margem mínima face à errada. k e o threshold ainda não estão
afinados. É para afinar aqui dentro, com testes reais, à medida que o
agente é usado — não confiar cegamente nisto ainda.
"""
import json
import os
import urllib.request

import numpy as np

import config

_STOPWORDS_PT = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "é", "que",
    "qual", "quais", "para", "por", "porque", "com", "sem", "um", "uma",
    "uns", "umas", "em", "no", "na", "nos", "nas", "se", "sempre", "anda",
    "vai", "está", "estão", "foi", "são", "ser", "ter", "tem", "têm",
}


def _palavras_chave(texto: str) -> set:
    """Extrai palavras-chave em minúsculas, sem stopwords nem pontuação.
    Mecânico de propósito — não depende de o modelo 'adivinhar' bem."""
    limpo = "".join(c.lower() if c.isalnum() else " " for c in texto)
    return {p for p in limpo.split() if p not in _STOPWORDS_PT and len(p) > 2}


def _sobreposicao(query_palavras: set, texto: str) -> float:
    """Fracção das palavras-chave da query que aparecem literalmente
    no texto da memória. 0.0 a 1.0."""
    if not query_palavras:
        return 0.0
    texto_palavras = _palavras_chave(texto)
    return len(query_palavras & texto_palavras) / len(query_palavras)


# 17 Ago 2026 — bug real apanhado a testar correcções do SUPERLEADS:
# um pedido com ~5657+ caracteres faz o Ollama devolver 500 (não um
# erro limpo) no endpoint de embeddings — quase de certeza o contexto
# do modelo de embeddings (nomic-embed-text) a ser excedido, mas sem
# nenhuma mensagem útil do lado do Ollama para confirmar a causa
# exacta. Reproduzido de forma determinística por bissecção de
# comprimento (ver HISTORICO.md) — não é intermitente, é sempre que o
# texto passa este tamanho. Isto rebentava build_system_prompt() por
# inteiro (nenhuma ferramenta chegava sequer a correr) sempre que um
# agente qualquer (SUPERLEADS incluído, depois de um prompt de sector
# ficar mais longo) mandasse um pedido comprido. _embed() só serve
# para RECUPERAR memórias semelhantes — não precisa do texto inteiro,
# um excerto já dá sinal suficiente. Cortar aqui, mesmo princípio de
# "nunca rebentar, corta com aviso" já usado em tools.ler_ficheiro.
LIMITE_CARACTERES_EMBED = 2000


def _embed(texto: str) -> list:
    if len(texto) > LIMITE_CARACTERES_EMBED:
        texto = texto[:LIMITE_CARACTERES_EMBED]
    body = json.dumps({"model": config.EMBED_MODEL, "prompt": texto}).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_HOST}/api/embeddings",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["embedding"]


def _cosine(a, b) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _index_path() -> str:
    return os.path.join(config.MEMORY_DIR, "_index.json")


def _load_index() -> dict:
    path = _index_path()
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_index(index: dict) -> None:
    with open(_index_path(), "w") as f:
        json.dump(index, f)


def _sync_index() -> dict:
    """Garante que cada ficheiro de memória tem embedding calculado e actual."""
    index = _load_index()
    changed = False
    ficheiros = [f for f in os.listdir(config.MEMORY_DIR) if f.endswith(".md")]

    for fname in ficheiros:
        path = os.path.join(config.MEMORY_DIR, fname)
        mtime = os.path.getmtime(path)
        if fname not in index or index[fname]["mtime"] != mtime:
            with open(path) as f:
                texto = f.read()
            index[fname] = {
                "mtime": mtime,
                "embedding": _embed(texto),
                "texto": texto,
            }
            changed = True

    for fname in list(index.keys()):
        if fname not in ficheiros:
            del index[fname]
            changed = True

    if changed:
        _save_index(index)
    return index


def retrieve(query: str, k: int | None = None) -> list:
    """Devolve as k memórias mais relevantes, ordenadas por pontuação
    híbrida (semelhança vectorial + sobreposição de palavras-chave).

    Cada item: (score, nome_do_ficheiro, texto). Memórias abaixo de
    config.MEMORY_MIN_SCORE ficam de fora — nenhuma é melhor que uma
    errada.
    """
    k = k or config.MEMORY_TOP_K
    index = _sync_index()
    if not index:
        return []

    q_vec = _embed(query)
    query_palavras = _palavras_chave(query)

    resultados = []
    for fname, item in index.items():
        semantico = _cosine(q_vec, item["embedding"])
        palavras = _sobreposicao(query_palavras, item["texto"])
        score = (
            config.MEMORY_PESO_SEMANTICO * semantico
            + config.MEMORY_PESO_PALAVRAS * palavras
        )
        resultados.append((score, fname, item["texto"]))

    resultados.sort(reverse=True)
    resultados = [r for r in resultados if r[0] >= config.MEMORY_MIN_SCORE]
    return resultados[:k]
