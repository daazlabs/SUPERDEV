"""
Configuração central do SUPERDEV.

Agente especialista em programação. Fala exclusivamente com o Ollama
local, sempre o mesmo modelo — sem lógica de fallback para outro
provedor. Se o Ollama ou o modelo não estiverem disponíveis, falha de
forma clara em vez de usar outra coisa.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Ligação ao Ollama --------------------------------------------------
# Porta 11435, não a 11434 por defeito — confirmado em
# /etc/systemd/system/ollama.service.d/override.conf (OLLAMA_HOST).
OLLAMA_HOST = "http://127.0.0.1:11435"

# AVISO — trocar este modelo NÃO é uma troca de uma linha.
# O tools.py/agent.py foram testados e afinados especificamente para
# como o qwen3.5 se comporta com a Ollama (a API nativa "tools", não o
# "format" genérico — ver tools.py e HISTORICO.md). A Ollama tem um
# interpretador feito à medida para este modelo (PARSER qwen3.5,
# confirmado com `ollama show qwen3.5:9b`). Outro modelo pode não ter
# esse tratamento dedicado, pode usar "format" correctamente (ou não),
# pode ter outra convenção de tool-calling. Se este valor mudar, é
# preciso re-validar tools.py inteiro, não assumir que continua a
# funcionar.
MODEL = "qwen3.5:9b"
EMBED_MODEL = "nomic-embed-text"

# Parâmetros de geração — REVISTOS item a item 9 Ago 2026 (ver
# HISTORICO.md para o detalhe de cada teste; aqui fica só o resultado).
#
# Referência: `ollama show qwen3.5:9b` devolve os valores que o
# próprio Qwen recomenda de fábrica (o que está no Modelfile do
# modelo): temperature=1, top_p=0.95, top_k=20, presence_penalty=1.5,
# context length nativo=262144. Os nossos valores abaixo divergem
# disso de propósito onde faz sentido para um agente de código, não
# por esquecimento — cada divergência está justificada.
OPTIONS = {
    # Baixo de propósito: código, queremos determinismo. Diverge do
    # 1.0 "de fábrica" do Qwen (afinado para chat geral) — mantido
    # após revisão, é prática comum em agentes de código.
    "temperature": 0.2,

    # Alinhados aos valores que o Qwen recomenda (0.95/20, não os
    # 0.9/40 que tínhamos por herança do Paulito). Com temperature tão
    # baixa o efeito prático é pequeno, mas não há razão para divergir
    # do que o próprio modelo foi afinado a usar.
    "top_p": 0.95,
    "top_k": 20,

    # Redundante mas inofensivo: é o próprio valor por defeito da
    # Ollama quando nada é dito, e o Qwen não define este parâmetro no
    # Modelfile (usa presence_penalty como travão de repetição — ver
    # nota abaixo). Mantido explícito por clareza.
    "repeat_penalty": 1.1,

    # NOTA IMPORTANTE: não definimos "presence_penalty" aqui — e isso
    # é intencional, não um esquecimento. Confirmado nos docs da
    # Ollama: uma opção que não vai no pedido não é reposta a zero,
    # herda o valor do Modelfile do modelo. O Qwen define
    # presence_penalty=1.5 de fábrica (o travão de repetição que o
    # próprio modelo foi afinado a usar) — ao não mexer aqui, estamos
    # a deixá-lo activo "nas costas". Se um dia isto for definido aqui
    # explicitamente, ganha-se clareza mas perde-se esta herança
    # automática — não fazer sem intenção.

    # BUG REAL encontrado e corrigido 9 Ago 2026 (ver HISTORICO.md):
    # com 4096, um pedido para ler dois ficheiros (cada um perto do
    # limite de tools.LIMITE_CARACTERES) enchia o contexto a meio da
    # tarefa — a Ollama cortou silenciosamente o início (1º ficheiro +
    # parte das instruções), sem erro nenhum, e o agente respondeu com
    # confiança usando só o que sobrou. Subir para 16384 corrigiu o
    # mesmo teste (voltou a somar os dois ficheiros correctamente).
    # Custo em VRAM medido ao vivo: creditar ao modelo em si (~8.5GB
    # só por estar carregado), não ao num_ctx — subir de 4096 para
    # 16384 só acrescentou ~500MB, folga confortável nos 12GB
    # partilhados com o resto do ecossistema Sovereign. O modelo
    # suporta nativamente até 262144, mas isso é claramente mais do
    # que este agente precisa por agora.
    "num_ctx": 16384,

    # Tecto de segurança para o tamanho da resposta — antes não havia
    # nenhum (só limitado pelo espaço livre no num_ctx). Para um
    # agente que promete "respostas curtas e directas", uma resposta a
    # fugir do previsto devia ser a excepção, não algo só travado pelo
    # limite físico do contexto.
    "num_predict": 2048,
}

# Modo "thinking" do qwen3.5 — TESTADO 8 Ago 2026, ver logs/.
# Com thinking ligado (default da Ollama): 19.2s e 765 tokens para UMA
# frase de resposta (o modelo "pensa em voz alta" num campo à parte
# antes de responder). Com think=False: 1.1s e 34 tokens, resposta
# igualmente correcta. ~17x mais rápido, ~22x menos tokens, no único
# teste feito até agora (uma pergunta trivial) — ainda não sabemos se
# perde qualidade em tarefas mais difíceis. Por isso fica já desligado
# por defeito aqui, mas é o primeiro candidato a rever se as respostas
# começarem a sair piores em tarefas complexas.
THINK = False

# Ficheiro de registo de cada pedido (o "espião") — para deixarmos de
# adivinhar e passarmos a medir sempre.
LOG_FILE = os.path.join(BASE_DIR, "logs", "chamadas.jsonl")

# --- Núcleo mínimo (Grupo A — sempre presente em todos os pedidos) ------
# Curto de propósito. Tudo o resto (memória, skills, conhecimento) é
# recuperado por pedido, nunca carregado por defeito.
CORE_IDENTITY = (
    "És o SUPERDEV, um agente especialista em programação. "
    "Respostas curtas e directas, em português. "
    "Usas apenas o que está no teu contexto — nunca inventas memória "
    "ou factos que não te foram dados."
)

# --- Memória (RAG mínimo) ------------------------------------------------
MEMORY_DIR = os.path.join(BASE_DIR, "memory")

# Quantas memórias trazer por pedido. AINDA A AFINAR — o teste isolado
# (_teste-rag/) mostrou que com k baixo a memória certa pode ficar em
# 2º lugar por uma margem mínima. Rever com testes reais dentro do agente.
MEMORY_TOP_K = 3

# Pontuação híbrida: semelhança vectorial + sobreposição de palavras-
# -chave exactas. A parte de palavras-chave é mecânica de propósito —
# não depende do modelo "adivinhar" bem, ao contrário de uma tentativa
# anterior (reformular a pergunta com o próprio modelo) que falhou por
# o modelo elaborar a mais em vez de resumir. Pesos de arranque, por
# afinar com uso real.
MEMORY_PESO_SEMANTICO = 0.7
MEMORY_PESO_PALAVRAS = 0.3

# Pontuação mínima de confiança para injectar uma memória no contexto.
# Abaixo disto, preferimos dizer "sem memória relevante" a arriscar
# meter a memória errada com ar de confiança — uma memória errada
# injectada engana o modelo mais do que não ter memória nenhuma.
# Valor de arranque, por afinar com uso real (ver logs/).
MEMORY_MIN_SCORE = 0.6

# --- Memória de conversa (curto e longo prazo, 9 Ago 2026) ---------------
# Objectivo: conversas longas sem ficarem cada vez mais caras. O erro
# óbvio seria reenviar a conversa toda a cada pedido (cresce sem
# parar) — em vez disso, janela curta sempre presente + destilação
# automática para memória persistente, para nunca ser preciso reler o
# histórico todo. `num_ctx` (acima) fica generoso de propósito — não é
# ele que controla a economia, é este mecanismo. Ver HISTORICO.md.

# Curto prazo: quantas trocas (pergunta+resposta) da conversa actual
# ficam sempre no pedido, para dar coerência imediata. Fixo, não
# cresce — janela desliza, trocas mais antigas saem. Valor de arranque,
# por afinar com uso real.
MEMORIA_CURTO_PRAZO_TROCAS = 4

# Longo prazo: de quantas em quantas trocas o agente tenta destilar a
# conversa recente em memória persistente (memory/*.md), com o mesmo
# modelo. AUTOMÁTICO por decisão do utilizador (não à espera de um
# comando explícito) — risco conhecido: pode gravar ruído se não
# houver nada relevante na janela destilada. Mitigado pedindo ao
# modelo para responder literalmente "NADA" quando não há nada que
# valha a pena — preferimos não gravar a gravar lixo, mesmo princípio
# do MEMORY_MIN_SCORE acima. Valor de arranque, por afinar com uso real.
MEMORIA_DESTILAR_A_CADA_TROCAS = 6
