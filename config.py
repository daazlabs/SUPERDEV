"""
Configuração central do SUPERDEV.

Agente especialista em programação. Fala exclusivamente com o Ollama
local, sempre o mesmo modelo — sem lógica de fallback para outro
provedor. Se o Ollama ou o modelo não estiverem disponíveis, falha de
forma clara em vez de usar outra coisa.
"""
import os

import dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carrega db/.env para o ambiente — é o ÚNICO sítio onde a password da
# BD existe, nunca escrita aqui no código. CORRIGIDO 9 Ago 2026: antes
# a password estava directamente numa string neste ficheiro, que já
# tinha sido commitado 2x para um repositório PÚBLICO no GitHub — por
# sorte, essa versão em concreto ainda não tinha sido enviada. Ver
# HISTORICO.md.
dotenv.load_dotenv(os.path.join(BASE_DIR, "db", ".env"))

# --- Ligação ao Ollama --------------------------------------------------
# Porta 11435, não a 11434 por defeito — confirmado em
# /etc/systemd/system/ollama.service.d/override.conf (OLLAMA_HOST).
OLLAMA_HOST = "http://127.0.0.1:11435"

# --- Ligação à pesquisa web (10 Ago 2026) --------------------------------
# SearXNG já corre localmente para outros projectos (container "searxng",
# porta 8888) — reaproveitado em vez de meter uma API paga (Google/Bing/
# Brave) só para isto. Sem chave nenhuma: confirmado ao vivo que o
# endpoint /search?format=json já responde sem qualquer configuração
# extra no container. Ver ferramenta pesquisar_web em tools.py.
SEARXNG_HOST = "http://127.0.0.1:8888"

# --- Ligação à base de dados de memória (pgvector, 9 Ago 2026) ---------
# Container isolado próprio (db/docker-compose.yml), porta 5443 — ver
# portas_reservadas_sistema na memória do utilizador. Falha de forma
# clara (KeyError) se db/.env não existir ou estiver incompleto, em
# vez de usar um valor por omissão silencioso — mesmo princípio do
# resto deste ficheiro.
_DB_USER = os.environ["POSTGRES_USER"]
_DB_PASSWORD = os.environ["POSTGRES_PASSWORD"]
_DB_NAME = os.environ["POSTGRES_DB"]
DB_DSN = f"host=127.0.0.1 port=5443 dbname={_DB_NAME} user={_DB_USER} password={_DB_PASSWORD}"

# Tenant por defeito para uso pessoal/desenvolvimento (não um cliente
# real) — todo o uso normal do agente cai aqui a não ser que uma
# sessão especifique outro tenant_id explicitamente.
TENANT_PADRAO = "default"

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

    # SUBIDO de 1.1 (default herdado, redundante) para 1.3 — 10 Ago
    # 2026, incidente real visto nos logs de teste do utilizador:
    # pedidos tipo "o que farias diferente" (lista longa, item a item)
    # entravam num ciclo a repetir blocos inteiros já escritos (não só
    # palavras/frases soltas — parágrafos completos idênticos,
    # confirmado em logs/conversas.jsonl), até bater no tecto de
    # num_predict e cortar a meio de uma palavra. O presence_penalty=1.5
    # herdado do Modelfile (ver nota abaixo, não mexido) penaliza um
    # token já visto, mas não travou blocos estruturados inteiros a
    # repetirem-se. Ainda por confirmar com mais uso real se 1.3 chega
    # ou se é preciso subir mais — primeira tentativa, não afinação
    # exaustiva.
    "repeat_penalty": 1.3,

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

    # REMOVIDO o tecto fixo de 2048 — 10 Ago 2026, a pedido do
    # utilizador. Histórico: posto a 9 Ago como rede de segurança
    # (antes disso, uma resposta a fugir do previsto só parava ao
    # encher o num_ctx todo). Mas a causa real de uma resposta longa
    # descontrolada era o ciclo de repetição corrigido no mesmo dia
    # (ver repeat_penalty acima) — este tecto só estava a cortar
    # respostas legítimas que precisassem de ser compridas (ex.: listas
    # exaustivas item a item), sem resolver o problema de fundo. -1 =
    # sem tecto artificial, só limitado pelo num_ctx acima (a rede de
    # segurança real). O aviso de corte em agent.py (done_reason ==
    # "length") continua activo — se um dia isto encher o num_ctx a
    # sério, o utilizador ainda é avisado, só não há mais um 2º tecto
    # artificial mais baixo a cortar primeiro.
    "num_predict": -1,
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
# adivinhar e passarmos a medir sempre. Só métricas, nunca o texto real
# (decisão deliberada, ver HISTORICO.md — susto de segurança 9 Ago).
LOG_FILE = os.path.join(BASE_DIR, "logs", "chamadas.jsonl")

# Ficheiro à parte, SÓ para a fase de testes (9 Ago 2026) — pergunta e
# resposta reais, para o utilizador (e o Claude, a pedido dele) poderem
# reler a conversa toda depois, não só métricas. Separado de LOG_FILE
# de propósito: mais sensível (tem texto real), fácil de apagar sozinho
# no fim da fase de testes sem tocar no registo de métricas. Também em
# .gitignore (logs/*.jsonl já cobre qualquer ficheiro novo aqui).
CONVERSATION_LOG_FILE = os.path.join(BASE_DIR, "logs", "conversas.jsonl")

# --- Núcleo mínimo (Grupo A — sempre presente em todos os pedidos) ------
# Curto de propósito. Tudo o resto (memória, skills, conhecimento) é
# recuperado por pedido, nunca carregado por defeito.
#
# EM INGLÊS DE PROPÓSITO (9 Ago 2026) — vai em TODOS os pedidos, é o
# sítio de maior alavancagem para poupar tokens: a instrução em si não
# precisa de estar em português para produzir português, só o
# resultado é que tem de ficar (testado abaixo, `THINK`-style). A
# conversa com o utilizador continua sempre em português — é uma
# instrução explícita aqui ("respond in European Portuguese"), não
# depende do resto do texto estar em PT.
CORE_IDENTITY = (
    "You are SUPERDEV, an expert programming agent. "
    "Always respond in European Portuguese (Portugal, not Brazil) — "
    "short, direct answers. "
    "Use only what is in your context — never invent memories or "
    "facts you were not given. "
    # 9 Ago 2026 — bug real confirmado ao vivo: sem isto, um pedido vago
    # ("lê o código") levava a adivinhar caminhos às cegas (/, /opt,
    # /home...) até esgotar as voltas de ferramentas sem nunca acertar.
    # As ferramentas exigem caminho absoluto; o modelo não tinha como
    # saber qual, mesmo sendo essa a sua própria pasta.
    f"Your own project folder, where your source code and files live, "
    f"is at the absolute path {BASE_DIR} — use it as the base when a "
    f"file/folder tool request doesn't give you a full path. "
    # 10 Ago 2026 — Nível 0 do plano anti-confabulação (ver HISTORICO.md,
    # incidente real: o modelo leu MEMORY_TOP_K=3 e MEMORIA_CURTO_PRAZO_
    # TROCAS=4 no próprio texto de uma ferramenta, e mesmo assim escreveu
    # "provavelmente 5 ou 10"/"10 ou 20" na resposta final). A regra
    # genérica de cima ("never invent facts") já existia e não chegou —
    # modelos pequenos respondem melhor a regras estreitas e concretas
    # do que a princípios largos. Esta é sobre o caso específico que
    # falhou: números/constantes citados de cabeça em vez de olhados.
    # Rede de segurança de verdade é o Nível 1 (verificação mecânica em
    # agent.py) — isto sozinho reduz, não garante.
    "When stating a specific number, config value, or named constant "
    "(e.g. SOME_CONSTANT = 5), only do so if you can point to the "
    "exact tool result text where you saw it earlier in THIS "
    "conversation — never recall it from general knowledge, training "
    "data, or a similar-looking project. If you're not sure of the "
    "exact value, say so explicitly instead of guessing a plausible "
    "one. "
    # 10 Ago 2026 — motivado por um caso real: um ficheiro grande
    # cortava (LIMITE_CARACTERES em tools.py), o modelo parava e
    # perguntava "posso continuar a ler?" em vez de continuar sozinho.
    # O utilizador tinha de responder "sim" — uma volta inteira gasta
    # (a pergunta dele + a resposta seguinte) só para dizer o óbvio,
    # quando já havia voltas de ferramentas de sobra para continuar
    # sem perguntar (ler_ficheiro agora aceita "inicio" para continuar
    # exactamente daí, ver tools.py).
    "You have several tool-call rounds available per request. If a "
    "file read comes back cut off and reading more of it is needed to "
    "properly answer the user's original request, keep calling tools "
    "yourself right away (e.g. ler_ficheiro again with the 'inicio' "
    "the cutoff message gave you) — do NOT stop and ask the user for "
    "permission to keep reading. Only ask the user something when you "
    "genuinely lack information only they can give you (e.g. an "
    "ambiguous path, a choice between real alternatives) — never for "
    "a mechanical next step you can already do yourself."
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

# --- Memória via pgvector (motor "produto", multi-tenant, 9 Ago 2026) ---
# Threshold PRÓPRIO, não o MEMORY_MIN_SCORE acima — a escala do score
# combinado aqui é diferente (o ts_rank nativo do Postgres não é 0-1
# como a sobreposição de palavras calculada à mão no memory.py
# original). Calibrado com dados reais (ver HISTORICO.md): perguntas
# claramente irrelevantes (ex: "como se faz uma omolete?") pontuaram
# 0.40-0.43; factos realmente relevantes pontuaram 0.47-0.60. 0.45
# fica na margem entre os dois grupos. Valor de arranque, mesma
# filosofia do MEMORY_MIN_SCORE (preferir não trazer nada a trazer
# ruído) — por afinar com mais casos reais.
PG_MEMORY_MIN_SCORE = 0.45
