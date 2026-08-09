-- Esquema de memória do SUPERDEV — versão "produto" (multi-tenant),
-- desenhado 9 Ago 2026. Ver HISTORICO.md para o porquê de cada escolha.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memorias (
    id          BIGSERIAL PRIMARY KEY,

    -- Isolamento entre clientes — nunca uma pesquisa de um tenant vê
    -- dados de outro. 'default' para uso pessoal/desenvolvimento.
    tenant_id   TEXT NOT NULL DEFAULT 'default',

    -- Categorização leve para pesquisa dirigida (o teste das
    -- "cebolas": filtrar primeiro por categoria, indexado, em vez de
    -- varrer tudo). Livre, sem lista fixa — 'projecto', 'preferencia',
    -- 'bug', 'decisao', etc., ou vazio se não classificado.
    categoria   TEXT,

    texto       TEXT NOT NULL,

    -- nomic-embed-text produz vectores de 768 dimensões (confirmado
    -- 9 Ago 2026 — ver HISTORICO.md).
    embedding   vector(768) NOT NULL,

    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Full-text search nativo do Postgres, em português (stemming
    -- próprio da língua) — substitui a sobreposição de palavras-chave
    -- feita à mão em Python no memory.py original. Gerada
    -- automaticamente a partir de "texto", sempre em sincronia.
    texto_tsv   tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', texto)) STORED
);

-- Índice HNSW — é isto que resolve o "vai direto lá, não leias tudo":
-- pesquisa por vizinhos mais próximos em distância de cosseno, sem
-- comparar com todas as linhas da tabela.
CREATE INDEX IF NOT EXISTS memorias_embedding_hnsw
    ON memorias USING hnsw (embedding vector_cosine_ops);

-- Isolamento por cliente, indexado — toda a pesquisa filtra por
-- tenant_id primeiro.
CREATE INDEX IF NOT EXISTS memorias_tenant_idx
    ON memorias (tenant_id);

-- Pesquisa dirigida por categoria dentro de um cliente.
CREATE INDEX IF NOT EXISTS memorias_tenant_categoria_idx
    ON memorias (tenant_id, categoria);

-- Índice GIN para a parte de palavras-chave da pontuação híbrida.
CREATE INDEX IF NOT EXISTS memorias_texto_tsv_idx
    ON memorias USING GIN (texto_tsv);
