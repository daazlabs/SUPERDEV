"""
Memória por recuperação semântica — versão pgvector (motor "produto",
multi-tenant), 9 Ago 2026.

Mesma ideia do memory.py (pontuação híbrida: semântica + palavras-
-chave, threshold mínimo de confiança), mas a pesquisa deixa de ser um
ciclo em Python sobre todos os ficheiros — passa a ser UMA query SQL,
com os dois índices (HNSW para a parte semântica, GIN para a parte de
palavras-chave) a fazer o trabalho dentro da base de dados. Ver
db/init/001_schema.sql para o esquema e HISTORICO.md para o porquê de
cada escolha.

Reutiliza memory._embed() — o nomic-embed-text continua a ser a régua,
só o sítio onde os números ficam guardados é que muda.

DSN local de desenvolvimento — credenciais em db/.env, container
próprio (superllmlocal-postgres), porta 5443 só em 127.0.0.1.

POOL DE LIGAÇÕES (9 Ago 2026) — medido ao vivo: abrir uma ligação nova
a cada pesquisa custava ~8ms, a maior parte do que tornava isto mais
lento que o memory.py antigo à escala pequena de hoje (ver
HISTORICO.md). Uma pool aberta uma vez, reutilizada em todas as
chamadas, evita esse custo repetido — mesmo princípio do modelo
"aquecido" vs "frio" que já vimos com a Ollama.
"""
from psycopg_pool import ConnectionPool

import config
import memory

# min_size=1: mantém sempre pelo menos uma ligação pronta (evita pagar
# o custo de abrir de novo depois de estar tudo em repouso).
# max_size=5: um agente a correr localmente não precisa de mais do que
# isto; subir se um dia houver pedidos a sério em paralelo.
_pool = ConnectionPool(config.DB_DSN, min_size=1, max_size=5, open=True)


def _vec_literal(v: list) -> str:
    """pgvector aceita vectores como texto '[v1,v2,...]', convertido
    com ::vector directamente no SQL — evita depender do pacote
    pgvector-python (o resto do projecto corre sem venv, sem pacotes
    extra instalados fora do que já vinha no sistema)."""
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def store(texto: str, tenant_id: str = None, categoria: str = None) -> int:
    """Grava um facto novo. Devolve o id da linha criada."""
    tenant_id = tenant_id or config.TENANT_PADRAO
    emb = memory._embed(texto)
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memorias (tenant_id, categoria, texto, embedding) "
                "VALUES (%s, %s, %s, %s::vector) RETURNING id",
                (tenant_id, categoria, texto, _vec_literal(emb)),
            )
            novo_id = cur.fetchone()[0]
        conn.commit()
    return novo_id


def retrieve(query: str, tenant_id: str = None, categoria: str = None, k: int = None) -> list:
    """Devolve as k memórias mais relevantes PARA ESTE tenant (nunca
    mistura clientes), ordenadas por pontuação híbrida. Cada item:
    (score, id, texto) — mesma forma de memory.retrieve(), trocável.

    CORRIGIDO 11 Ago 2026 — a pensar no amanhã, ver a nota em
    config.POOL_CANDIDATOS_SEMANTICOS para o porquê: a query já pede
    só os N mais próximos semanticamente (ORDER BY ... LIMIT, é isto
    que deixa o Postgres usar o índice HNSW a sério), em vez de trazer
    a tabela toda do tenant para reordenar tudo em Python."""
    k = k or config.MEMORY_TOP_K
    tenant_id = tenant_id or config.TENANT_PADRAO
    q_vec = _vec_literal(memory._embed(query))

    sql = """
        SELECT id, texto,
               1 - (embedding <=> %(qvec)s::vector) AS score_semantico,
               ts_rank(texto_tsv, plainto_tsquery('portuguese', %(query)s)) AS score_palavras
        FROM memorias
        WHERE tenant_id = %(tenant_id)s
    """
    params = {
        "qvec": q_vec, "query": query, "tenant_id": tenant_id,
        "pool": config.POOL_CANDIDATOS_SEMANTICOS,
    }
    if categoria:
        sql += " AND categoria = %(categoria)s"
        params["categoria"] = categoria
    sql += " ORDER BY embedding <=> %(qvec)s::vector LIMIT %(pool)s"

    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            linhas = cur.fetchall()

    resultados = []
    for id_, texto, semantico, palavras in linhas:
        score = (
            config.MEMORY_PESO_SEMANTICO * semantico
            + config.MEMORY_PESO_PALAVRAS * palavras
        )
        resultados.append((score, id_, texto))

    resultados.sort(reverse=True)
    resultados = [r for r in resultados if r[0] >= config.PG_MEMORY_MIN_SCORE]
    return resultados[:k]
