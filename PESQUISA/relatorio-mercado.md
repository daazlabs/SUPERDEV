# Relatório de mercado — SUPERDEV: agilidade e token-economia em agentes de código locais

> Pesquisa feita a pedido de `/mnt/sovereign/superdev/PESQUISA/COMANDO-mercado.txt`
> (11 Ago 2026). Relatório escrito **incrementalmente**: cada secção foi salva
> assim que concluída, para uma versão parcial ser sempre útil.
>
> **Objectivo:** antes de afinar o SUPERDEV mais à mão, saber se o problema —
> um agente de código **local, single-GPU, VRAM 12GB partilhada**, rápido e
> token-lean — já foi resolvido melhor por outra coisa. Onde existir resposta
> real, adoptar/adaptar em vez de re-derivar por tentativa e erro.
>
> **Enquadramento (não perder):** o objectivo NÃO é escolher "o melhor modelo".
> O SUPERDEV é o motor + ferramentas à volta de qualquer modelo (de ~1B a
> ~120B). Cada técnica é classificada como **MODEL-AGNOSTIC** ou
> **MODEL-SPECIFIC**.
>
> **Regras de evidência:** URL para cada afirmação factual; números reais
> preferidos a marketing; `NÃO VERIFICADO` quando não for possível confirmar;
> restrições respeitadas (inferência local, Ollama hoje, 12GB VRAM partilhada,
> tool-calling fiável); custo de adopção explicitado por recomendação.

---

## 1. Agent scaffolds desenhados para agentes de código locais, rápidos e token-lean

Métricas de manutenção recolhidas via API do GitHub em 11 Ago 2026. O que
interessa a este projecto não é "quem edita melhor código", é **que
técnicas concretas cada um usa para cortar tokens/latência** e se podem
ser adaptadas ao SUPERDEV (motor + ferramentas à volta de qualquer
modelo, 12GB VRAM partilhada).

### 1.1 Aider (terminal, git-native) — Apache-2.0, ~48,1k stars, último push 2026-05-22

Técnicas concretas de token-economia:

- **Repo map em vez de despejar ficheiros no contexto**: um mapa
  resumido de símbolos do repo inteiro (classes, funções, assinaturas,
  linhas críticas), gerado com tree-sitter + ranking por grafo de
  dependências, enviado junto de cada pedido. Budget por omissão
  `--map-tokens` = **1000 tokens**, expandido dinamicamente quando não há
  ficheiros adicionados ao chat
  (https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md;
  https://aider.chat/2023/10/22/repomap.html).
- **Edição por diff em vez de reescrita integral**: formatos `whole`
  (reescreve o ficheiro todo — o modelo indica como "simples mas caro"),
  `diff` (blocos SEARCH/REPLACE), `udiff` (unified diff simplificado).
  O `whole` é descrito nos próprios docs como lento e caro para edições
  pequenas; o `udiff` foi criado para reduzir "lazy coding"
  (https://github.com/Aider-AI/aider/blob/main/aider/website/docs/more/edit-formats.md).
- **Modelo fraco para tarefas simples, modelo forte para as difíceis**
  (`--weak-model`): roteia chamadas simples para um modelo barato
  (https://github.com/Aider-AI/aider/blob/main/aider/website/docs/usage.md).
- **Só envia os ficheiros que interessam** (`/add`), em vez de ler o repo
  todo; o resto vem pelo repo map
  (https://aider.chat/docs/usage.html).

Compatível com Ollama tal como está (`aider --model ollama/qwen3.5:27b`;
docs oficiais recomendam o prefixo `ollama_chat/` por dar melhores
edições) (https://aider.chat/docs/llms.html; https://aider.chat/docs/llms/ollama.html).

**Aviso de calibração para SUPERDEV:** os números de edição por diff do
próprio leaderboard do Aider mostram que o formato de edição é
**modelo-dependente** — o `llama3-70b` só conseguiu 73.5% de edições
bem-formadas no formato `diff`, e o `gemini-1.5-pro` 87.2% no
`diff-fenced` (https://aider.chat/docs/leaderboards/; dados citados em
https://dreaming.press/posts/coding-agent-edit-formats-diff-vs-whole-file.html).
Ou seja, o diff é barato em tokens mas o modelo pequeno tem de o
produzir bem-formado — isto mede o risco exacto que o SUPERDEV já sente
com tool-calling: a *técnica* é model-agnostic, a *fiabilidade de a
produzir* não é. Para modelos fracos, o próprio Aider usa `whole`
(reescrita completa), aceitando mais tokens por fiabilidade
(https://github.com/Aider-AI/aider/blob/main/aider/website/docs/more/edit-formats.md).

### 1.2 Continue.dev (IDE) — Apache-2.0, ~35,4k stars, muito activo (push 2026-08-11)

Modelos por **papel** (roles), não um modelo para tudo: `chat`, `edit`,
`apply`, `autocomplete`, `embed`
(https://docs.continue.dev/customize/model-roles/apply;
https://dev.to/jovan_chan_9500711396d4e6/continuedev-configuration-guide-for-multi-language-projects-2026-14k3).
Duas técnicas relevantes:

- **Modelo "apply" dedicado a gerar o diff preciso** da mudança, para o
  modelo de chat não ter de produzir edições exactas; recomenda-se um
  modelo pequeno/barato para isso (Claude Haiku, ou modelos open
  FastApply 15B) (https://docs.continue.dev/customize/model-roles/apply).
  É a mesma ideia do "fast-apply" do Cursor/Morph: um modelo pequeno e
  rápido faz a fusão mecânica, o modelo grande fica "preguiçoso" e só
  emite a mudança solta
  (https://cursor.com/blog/instant-apply; https://www.morphllm.com/fast-apply-model).
- **Autocomplete com modelo pequeno dedicado** (ex.: qwen2.5-coder:1.5b),
  com `maxPromptTokens: 1024` e debounce, para latência <500ms — trade-off
  explícito: completions são jogo de latência, não de qualidade
  (https://runaihome.com/blog/continue-dev-ollama-local-ai-coding-stack-2026/).

Funciona com Ollama as-is (provider nativo). Para agentes de chat/edit
com modelos locais o guia recomenda janela de contexto ≥16K
(https://docs.continue.dev/guides/ollama-guide).

### 1.3 Cline / Roo-Code (extensões VS Code) — Apache-2.0; Cline ~66k stars; Roo-Code ~24,3k stars

- Ambos são agentes autónomos no IDE que **reescrevem ficheiros inteiros**
  por omissão (edição whole-file) e guardam "snapshots" para undo.
- Ambas recomendam **contexto ≥32K** para tarefas de código
  (https://docs.ollama.com/integrations/cline; https://docs.ollama.com/integrations/roo-code).
- **Aviso de calibração relevante:** o system prompt do Cline é de
  ~15K tokens; o do Roo-Code ~8-9K. A avaliação do canitrun.dev diz
  explicitamente que **12GB VRAM NÃO chega para "agentic coding sério"
  com estas ferramentas** (modelo de ~14B em Q4 + contexto curto fica
  sem espaço; o system prompt sozinho consome uma fatia grande da janela)
  (https://canitrun.dev/apps/compare/cline-vs-roo-code).
  Isto é uma medição indirecta do que o SUPERDEV já sabe por experiência:
  num total de 12GB partilhados, o orçamento de contexto é apertado e um
  system prompt inchado come-o. É contra-argumento para quem recomende
  "adoptar Cline/Roo" para este hardware: o design deles assume modelo
  grande (preferencialmente cloud) e janela larga.
- Roo-Code tem system prompt **mais pequeno** que Cline de propósito
  ("slightly more efficient with limited VRAM") — reconhecimento explícito
  de que prompt de sistema é custo por pedido (https://canitrun.dev/apps/compare/cline-vs-roo-code).
- Token tracking/custo por sessão em ambos.

### 1.4 Qwen-Agent / Qwen Code — Apache-2.0; Qwen-Agent ~16,9k stars (push 2026-03-04, mais parado); Qwen Code ~26,9k stars (activo)

- **Qwen-Agent** encapsula *template de tool-calling* + *parser* por
  modelo ("Qwen-Agent encapsulates tool-calling templates and tool-calling
  parsers internally") — ou seja, é **model-specific por desenho** (amarrado
  à família Qwen): o template e o parser mudam com a convenção de tool
  calls de cada modelo (https://qwen.readthedocs.io/en/latest/framework/qwen_agent.html).
  Não é o modelo certo para um motor que tem de ser agnóstico — confirma
  o aviso já escrito no `config.py` do SUPERDEV.
- **Qwen Code** é o agente de código (CLI estilo Claude Code) construído
  sobre modelos Qwen, com edição por diff, subagentes com contextos
  isolados e fork de contextos (https://qwenlm.github.io/qwen-code-docs/).
  NÃO VERIFICADO: números públicos de tokens/latência do Qwen Code.

### 1.5 smolagents (Hugging Face) — Apache-2.0, ~28,8k stars, activo (push 2026-07-21)

A técnica de longe mais relevante desta lista para o SUPERDEV:

- **CodeAgent — "o agente pensa em código", não em JSON.** Em vez de o
  modelo emitir tool-calls estruturados (JSON) um a um, o modelo escreve
  *um snippet de Python* que chama as ferramentas como funções, executado
  uma vez num sandbox. O loop model→tool→model→tool colapsa num único
  passo. A biblioteca é ~1000 linhas de núcleo
  (https://github.com/huggingface/smolagents).
- **Porque interessa a um modelo pequeno:** o `CodeAgent` não depende da
  capacidade de *formatação* de tool-call do modelo — escrever código é
  uma habilidade que até um 1B razoável tem; o `ToolCallingAgent` (JSON)
  é o que precisa de tool-calling nativo fiável. O README da Microsoft
  Agent Framework documenta exactamente o mesmo trade-off com o mesmo
  argumento: "many agents aren't bottlenecked by model quality, they're
  bottlenecked by orchestration overhead... each step is a separate model
  turn, driving up latency and token usage"; CodeAct "collapses that loop"
  (https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight).
  Os números "antes/depois" estão nesse post da Microsoft (ver secção 2).
- O paper de referência ("Executable Code Actions Elicit Better LLM
  Agents", 2402.01030) é citado na própria doc
  (https://huggingface.co/papers/2402.01030).
- Funciona com Ollama via LiteLLM/`ollama` e com `transformers` local
  (https://github.com/huggingface/smolagents#readme).
- **Risco conhecido:** execução de código gerado pelo modelo pede
  sandbox (local/Docker/E2B/Blaxel) — segurança é o trade-off clássico
  do CodeAct. Para o SUPERDEV (só lê ficheiros hoje, não executa), isto
  é uma mudança grande de paradigma (ver secção 6).

### 1.6 llama.cpp server (runtime, não scaffold) — MIT, ~123,4k stars, muito activo

Não é um agente, mas expõe as duas primitivas que qualquer agente
precisa e que são as mais model-agnostic desta pesquisa:

- **Decodificação constrangida por gramática (GBNF)** no servidor:
  `grammar`/`json_schema` no corpo do pedido; converte JSON Schema em
  gramática e **mascara tokens inválidos na amostragem** — output
  malformado torna-se impossível por construção, não corrigido depois
  (https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md).
  Custo medido: "a few percent in throughput" (single-digit %) e elimina o
  ciclo validate-retry
  (https://llmconfigurator.com/en/guides/coding-agents/tool-calling-local-models).
- **Function calling nativo universal**: `chat.h` (PR #9639) suporta
  formatos nativos de várias famílias (Llama 3.1/3.x, ChatML etc.) **e um
  handler genérico** ("Universal support w/ Native & Generic handlers")
  para modelos sem formato nativo
  (https://huggingface.co/rohan23998/llama-cpp-model/blob/main/docs/function-calling.md).
  Isto é exactamente a resposta à pergunta "existe uma interface de
  tool-calling model-agnostic?" (ver secção 4).
- **Reuso de slots / KV-cache**: `--slot-prompt-similarity` permite um
  pedido reutilizar o slot de outro com prompt semelhante (o contexto
  não é re-avaliado de raiz) (manpage do llama-server, `-sps`).

O Ollama usa llama.cpp por baixo e herda o GBNF para o `format`
(JSON schema → gramática). **Mas há evidência de bug real:** em modelos
com tokens de thinking (qwen3.5 e gemma4), `think=false` faz o
constraint de `format` ser **silenciosamente ignorado** — o modelo
devolve texto livre, sem erro nenhum (issue #14645 da série qwen3.5,
confirmada também para gemma4: https://www.stepcodex.com/en/issue/think-false-breaks-format-structured-output;
issue relacionada no repo do Ollama sobre o endpoint /v1:
https://github.com/ollama/ollama/issues/10937). Isto bate certo com o
incidente documentado no `HISTORICO.md` do SUPERDEV (o `format` não
restringiu nada) e com o facto de o SUPERDEV correr `think=False` desde
sempre — a combinação pode ter sido a causa, não o `format` em si.

### 1.7 opencode (o tool a correr esta pesquisa) — MIT, ~196k stars, muito activo (push 2026-08-11)

Arquitectura e técnicas de economia:
- **Edição por search/replace exacto** (`edit` tool: "Modify existing
  files using exact string replacements"), não reescrita de ficheiro
  (https://opencode.ai/docs/tools).
- **LSP para contexto estruturado** em vez de despejar ficheiros:
  o agente consulta o language server para definitions/references/hover
  e recebe símbolos e assinaturas (contexto pequeno e preciso), em vez de
  ler o ficheiro todo. Os docs avisam que LSP "is not always a net
  positive" e recomendam correr lint/typecheck por CLI para alimentar o
  loop — o mesmo raciocínio da ferramenta `correr_ruff` do SUPERDEV
  (https://opencode.ai/docs/lsp).
- **Contexto incremental**: `read` com ranges de linhas; `grep`/`glob`
  (ripgrep por baixo) para procurar em vez de ler tudo; "referências" @
  para anexar ficheiros específicos (https://opencode.ai/docs/tools).
- **Context compaction** de conversas longas, em vez de reenviar tudo
  (https://datalakehousehub.com/blog/2026-03-context-management-opencode).
- **Plan vs Build**: agente Plan raciocina sem tocar em ficheiros,
  agente Build edita — separação de contextos por tipo de tarefa.
- **Camada de provedores agnóstica** (75+ provedores incluindo Ollama) —
  o motor não está amarrado ao formato de tool-calling de nenhum modelo
  (https://opencode.ai/docs/providers).

### 1.8 Conclusão intermédia da secção 1

Não existe, entre o que foi pesquisado, um "superdev pronto" que ganhe à
mão com a mesma filosofia de negócio (motor agnóstico + 12GB partilhada).
O mais próximo de um padrão de indústria para "rápido e token-lean" é o
combo de quatro técnicas, que aparecem em várias destas ferramentas de
forma independente:
1. **Mapa de repo / símbolos em vez de ficheiros no contexto** (Aider, opencode/LSP).
2. **Edição por diff/search-replace, não reescrita** (Aider, opencode, Cline/Roo têm ferramentas de replace; Continue tem modelo "apply").
3. **Modelo pequeno dedicado ao passo mecânico** (Continue apply/autocomplete, fast-apply do Cursor).
4. **CodeAct/expressar várias chamadas num só bloco** (smolagents, MS Agent Framework).

Cada uma destas é model-agnostic por natureza (detalhe na secção 4). As
avaliações independentes concordam num facto que o SUPERDEV já mediu: a
12GB, o orçamento não dá para system prompts grandes nem contextos de
32K+ com modelos de ~14B (https://canitrun.dev/apps/compare/cline-vs-roo-code).

---

## 2. Técnicas de redução de tokens com evidência medida

Atenção à origem dos números: quase toda a literatura sobre "redução de
tokens" vem do mundo **API pago** (onde comprimir = dinheiro poupado). O
SUPERDEV é local, onde o custo que importa é **VRAM + latência + janela
de contexto**. As técnicas transferem-se, mas a *justificação* muda:
reduzir input não é economizar €, é (a) caber na janela que o modelo
realmente usa, (b) cortar tempo de prefill e (c) manter o KV-cache
reutilizável. Números de € do mundo API são citados só como ordem de
grandeza do ganho.

### 2.1 CodeAct / "uma chamada em vez de dez" — o maior ganho medido

Benchmark oficial do Microsoft Agent Framework (mesmo modelo, mesmas
ferramentas, mesmo prompt; única diferença = wiring), task realista com
dúzias de tool-calls encadeadas (lookups de users/orders/taxas):
(https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/)

| Wiring | Tempo | Tokens |
|--------|-------|--------|
| Tool-calling tradicional (1 turn por passo) | 27.81s | 6,890 |
| CodeAct (plano inteiro num bloco de código) | 13.23s | 2,489 |
| **Melhoria** | **52.4%** | **63.9%** |

A causa é estrutural: com tool-calling clássico, cada passo é um turn do
modelo, e **cada turn reenvia a conversa toda** (exactamente o problema
que o SUPERDEV já mediu ao subir `MAX_VOLTAS_FERRAMENTAS`). Com CodeAct,
os N passos colapsam num único turn; o trace de raciocínio fica num só
bloco em vez de espalhado por N mensagens de tool-call. O mesmo efeito —
não exactamente o mesmo design — é o **batching de múltiplas tool-calls
numa só resposta** (mais em 2.7).

Custo/risco: o modelo passa a gerar código executável → exige sandbox
(micro-VM Hyperlight, Docker/E2B no smolagents) e, nos testes da MS, as
descrições de ferramentas têm de ser boas porque o modelo raciocina sobre
elas como contrato em Python (docstrings, tipos) (idem). Papel original:
Wang et al., "Executable Code Actions Elicit Better LLM Agents"
(https://huggingface.co/papers/2402.01030).

### 2.2 "Onde vão os tokens": decomposição 45/25/20/10

Guia independente (RockB, Jun 2026) com análise do desperdício típico de
um agente de código: ~45% do gasto em contexto/ficheiros re-lidos,
~25% em histórico de conversa, ~20% em instruções de sistema/ferramentas,
~10% em resultados de ferramentas
(https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).
Uma sessão típica de agente de código após 30 turns acumula **25-35K
tokens de histórico**, a maior parte irrelevante para a tarefa corrente
(idem). O Tokoscope (benchmarks de produção 2026) mede "agentic task (por
passo)" entre 2.5K-12K tokens — um agente com 10 passos gasta 25-120K
por tarefa (https://tokoscope.com/articles/llm-stats).

**Implicação para SUPERDEV:** com o num_ctx que o modelo usa, a "sessão
que acumula 25-35K" é impossível — corta-se no meio. Isto não é só um
problema de qualidade: é a demonstração de que, para o modelo caber no
contexto, o SUPERDEV precisa de *compactação* (2.3) ou *contexto
selectivo* (2.4), não apenas prompts mais curtos.

### 2.3 Compactação de histórico (summarize, não append)

- Claude Code `/compact` (e congéneres no opencode/Continue): resume a
  conversa ao estado essencial e descarta turns antigos; regra prática
  documentada: usar a cada 15-20 mensagens
  (https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).
- Compressão de prompt (LLMLingua e derivados): 20-50% de redução de
  tokens mantendo conteúdo semântico; trade-off = 100-500ms de latência
  extra por compressão e perda de pormenores técnicos precisos (números
  de versão, mensagens de erro exactas, snippets). Regra documentada:
  **nunca comprimir dados, só texto instrucional/explicativo** (idem).
  NÃO VERIFICADO: replicação independente dos 20-50% (estudo de 2026
  mostra que a compressão é dependente do benchmark — MBPP perde,
  HumanEval aguenta: https://arxiv.org/abs/2603.23527).
- **Aviso KV-cache (crítico para local):** o TokenPilot (arXiv
  2606.17016) mostra que "compactar" frequentemente é contraproducente
  *no local*: cada compactação muda o prefixo → **invalida o KV-cache →
  o motor re-processa o prompt todo (prefill caro)**. O framework
  optimiza para manter o prefixo estável e reduziu custos de inferência
  até 87% em streams contínuos
  (https://www.alphaxiv.org/overview/2606.17016).

### 2.4 Contexto selectivo em vez de ler tudo (repo map, LSP, AST)

- **Repo map (Aider)**: mapa de símbolos do repo (~1000 tokens por
  omissão) em vez de ficheiros inteiros — ver secção 1.1. Estudo citado
  no guia RockB: *AST-level dependency mapping* dá **~65% de redução sem
  mudar o modelo** quando o agente lia ficheiros inteiros em cada chamada
  (https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).
- **LSP (opencode)**: consultar o language server por definitions/
  references/hover dá símbolos e assinaturas em vez do ficheiro completo
  (https://opencode.ai/docs/lsp). O token-optimizer-mcp do ecossistema
  Claude Code anuncia "smart_ast_grep — 83% reduction" e "smart_cron —
  85% reduction" (repo de terceiros, números auto-declarados, não auditei
  o método: https://github.com/ooples/token-optimizer-mcp).
- **RAG de memória selectiva**: o SUPERDEV já resolveu isto com pgmemory
  (fora de âmbito desta pesquisa). Para contexto: o playbook Mem0 2026
  mediu 594 tokens naive vs 166 com retrieval = **~72% de redução** de
  tokens de memória, ao preço de ~200ms de latência por query
  (https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).

### 2.5 System prompt enxuto + instruções por camadas (progressive disclosure)

- Técnica documentada como *AGENTS.md progressive disclosure*: em vez de
  despejar todas as convenções no system prompt, estruturar por camadas e
  carregar apenas as relevantes à tarefa. Ganho citado: **~70% de
  redução** nos tokens de instruções
  (https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).
- Dados do mundo real do tamanho de system prompts de agentes: Cline
  ~15K tokens vs Roo-Code ~8-9K; Roo-Code cortou de propósito para caber
  em VRAM limitada (https://canitrun.dev/apps/compare/cline-vs-roo-code).
  O system prompt do SUPERDEV é curto de propósito (decisão já em
  `config.py`) — confirmado aqui como boa prática, com números.
- Regra fundamental de *context engineering* (guia TokenOptimize 2026):
  manter o **prefixo do prompt estável entre turns** é pré-requisito para
  prompt caching/cache de KV — cada mudança no system prompt invalida o
  cache do ponto da mudança em diante
  (https://www.tokenoptimize.dev/guides/llm-token-optimization-strategies).

### 2.6 Caching — e o que significa em local vs API

No mundo API, prompt caching é o maior item (Anthropic: 90% de desconto
em cache reads; OpenAI: automático, até 90%; ProjectDiscovery: hit rate
7%→84%, corte de 59-70% do gasto total com uma mudança arquitectónica;
semantic caching: 20-45% do tráfego sem tocar o modelo, benchmarks
Technion 2026)
(https://neuraltrust.ai/blog/llm-caching-strategies;
https://www.tokenoptimize.dev/guides/llm-token-optimization-strategies;
https://devtoollab.com/blog/prompt-caching-guide).

**Em local, o equivalente é o KV-cache de llama.cpp/Ollama** e o ganho é
latência (não €): se o prefixo (system prompt + schema de tools + história
recente) for idêntico ao do turn anterior, o engine **não re-prefilla** —
o `llama-server` tem até `--slot-prompt-similarity` para reutilizar slots
com prompts semelhantes (manpage do llama-server). Implicação directa
para SUPERDEV:
- Não mudar o system prompt a meio de uma sessão.
- Não reordenar as definições de tools entre turns.
- Não truncar a história pelo meio sem resumir (ver 2.3).
O contraste está medido no paper do TokenPilot: agentes que "compactam"
com frequência perdem o benefício do cache porque o prefill volta a ser
caro (https://www.alphaxiv.org/overview/2606.17016).

### 2.7 Batching de tool-calls e respostas curtas

- Vários turnos de ferramenta **na mesma resposta**: modelos modernos
  conseguem emitir N tool-calls num único assistant turn (cada um é um
  token-a-token, sem reenvio da conversa entre eles). Poupa o reenvio do
  histórico entre passos encadeados — o mesmo mecanismo de custo que o
  CodeAct elimina por completo (secção 2.1). O Ollama suporta múltiplas
  tool-calls por turn nas famílias com template próprio
  (https://github.com/ollama/ollama/issues/2915).
- **Verbosity != veracity**: instruir saídas curtas tem ganho medido em
  tokens sem perda de qualidade; paper dedicado
  (https://arxiv.org/abs/2411.07858); compilação de papers sobre mínimo
  de tokens intrínseco por tarefa
  (https://github.com/pleasedodisturb/awesome-llm-token-optimization).

### 2.8 Rotear modelos por complexidade (routing)

- Aider `--weak-model`: modelo barato para tarefas simples, forte para
  difíceis (https://aider.chat/docs/usage.html).
- Continue: modelo "apply"/"autocomplete" pequeno para o passo mecânico
  (https://docs.continue.dev/customize/model-roles/apply).
- RouteLLM: **85% de redução de custo mantendo 95% da performance** do
  frontier no benchmark Agentic Coding (citado no guia RockB:
  https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).
- Modelos bem mais pequenos resolvem a maioria das chamadas: a "regra
  70/20/10" do mesmo guia (70% das chamadas não precisam do modelo topo
  de gama).
- **Aviso para SUPERDEV:** isto é model-specific na prática — para haver
  "rotas", têm de existir modelos diferentes acessíveis. Hoje o SUPERDEV
  tem um só (qwen3.5:9b); a porta 8090 (Qwen3.6-35B llama.cpp) existe mas
  está fora da arquitectura actual. Ver secção 6.

### 2.9 Resumo com números

| Técnica | Ganho citado | Fonte |
|---|---|---|
| CodeAct / colapsar passos | 52% latência, 64% tokens (medido, benchmark oficial) | MS Agent Framework |
| Contexto selectivo (AST/mapa) | ~65% se lia ficheiros inteiros | RockB / Aider |
| Progressive disclosure do prompt | ~70% nos tokens de instrução | RockB / Mem0 |
| Retrieval de memória | ~72% vs histórico naive | Mem0 |
| Compressão de prompt (LLMLingua) | 20-50% (depende do benchmark) | vários |
| Semantic caching | 20-45% de chamadas sem modelo | Technion 2026 |
| Compactação de histórico | mantém sessões longas em contexto curto | Claude Code / open |

Nenhum destes números é uma lei universal: são medições em workloads
específicos. A recomendação de método do próprio guia RockB: medir no
próprio workload antes de adoptar
(https://baeseokjae.github.io/posts/coding-agent-token-waste-reduction-guide-2026).

---

## 3. Técnicas de velocidade para inferência local em GPU partilhada, VRAM 12GB

Premissa deste projecto: a GPU **não é exclusiva** do SUPERDEV — outros
serviços carregam/descarregam modelos na mesma placa. Portanto as duas
alavancas de "velocidade" não são só tok/s; são **caber no VRAM sem OOM
quando os vizinhos acordam** e **não pagar reload de modelo/contexto**
por descuido de configuração. As evidências abaixo são do universo
llama.cpp/Ollama (o SUPERDEV corre Ollama sobre llama.cpp).

### 3.1 Quanto cabe em 12GB — o tecto prático

Medições independentes para RTX 3060 12GB (o cartão de referência deste
tipo de workload), quantização Q4_K_M, janela longa (8K/16K/32K)
(https://craftrigs.com/guides/best-llm-rtx-3060-12gb-vram-2026;
https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms):

- 7-8B: ~4.5-5GB pesos → 7GB de folga para KV cache → cabe 32K ctx.
- 13-14B: ~8.5-9GB pesos → 2-3GB para KV cache → **8K folgado, 16K
  apertado (2.5-3GB), 32K já não cabe (5-6GB)**.
- 20B: ~11.5-12GB → pesos enchem a VRAM, quase zero KV → só contextos
  curtos, experiência degradada.
- 32B+: offload CPU → **5-8 tok/s**, inutilizável para agente
  (https://craftrigs.com/guides/best-llm-rtx-3060-12gb-vram-2026).

Velocidades medidas no cartão: 14B ~28-32 tok/s; 8B ~42-48 tok/s
(idem). Conclusão directa: **o tecto prático desta placa é 14B; a escolha
qwen3.5:9b do SUPERDEV está dentro da zona confortável** (pesos ~6GB,
deixa ~6GB para KV cache + folga de vizinhos). O teste comum de "contexto
32K + modelo 14B" é fisicamente impossível aqui sem offload.

### 3.2 KV cache quantizado — o ganho de memória maior para contexto

O KV cache cresce com o contexto e, a f16, rouba VRAM que faz falta.
Quantizar K e V separadamente (`--cache-type-k q4_0 --cache-type-v q4_0`
no llama-server) **reduz o KV cache em ~75%** com perda mínima de
qualidade (27B a 16K ctx: ~8GB → ~2GB de VRAM no exemplo do autor)
(https://docs.bswen.com/blog/2026-03-15-llamacpp-optimization-speed/).
É independente da quantização dos pesos — são dois eixos ortogonais
(https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec).

Nota Ollama: a partir de versões recentes, o Ollama aplica
automaticamente quantização de cache para modelos grandes quando o VRAM é
curto (falha para `q8_0`/`q4_0`). NÃO VERIFICADO nesta pesquisa qual o
comportamento exacto na versão instalada do servidor 11435 — pode ser
forçado via Modelfile (`PARAMETER cache_type_k q4_0`) se a versão o
suportar.

### 3.3 Tamanho de contexto certo, não máximo

Os guias insistem num ponto que o HISTORICO.md do SUPERDEV já descobriu
por acidente (num_ctx 4096 truncava silenciosamente): **contexto grande
demais para o hardware é pior que contexto suficiente**. Recomendações
concretas:
- Definir `--ctx-size`/`num_ctx` explícito e **não máximo**: "use
  `--ctx-size 8192` explicitly in llama.cpp to cap context and prevent
  out-of-memory crashes" (https://craftrigs.com/guides/best-llm-rtx-3060-12gb-vram-2026).
- `llama-fit-params` (binário oficial de tuning) sugere `-ngl`/`-b`
  óptimos dado modelo e ctx
  (https://docs.bswen.com/blog/2026-03-15-llamacpp-optimization-speed/).
- Interacção mal compreendida: `--ctx-size`, `--parallel` e memória
  interagem através do KV cache (cada slot paralelo aloca KV próprio);
  subir um sem pensar no outro esmaga o VRAM (tutorial dedicado em 8GB:
  https://alejandro.criadoperez.com/blog/Llama_server_memory).
- Reafirmação: com 4 users × 8K ctx num 24GB, só o KV cache multi-slot
  consumiu 0.8GB extra e o TTFT subiu; em 12GB partilhada, `parallel=1`
  é a escolha segura (https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms).

### 3.4 Offload híbrido: o "precipício" e o `low_vram`

- O Ollama decide sozinho quantas camadas põem na GPU; se não couber,
  cai para CPU. Velocidade é dominada por largura de banda de memória —
  um modelo parcialmente offloaded é **muito** mais lento do que parece
  (análise "bandwidth-first" para 12GB:
  https://sergiiob.dev/posts/gpu-vram-cpu-offload-llama-cpp-deep-dive/).
  Regra geral: é melhor um modelo que caiba inteiro do que um maior
  "quase inteiro".
- Em Ollama, `low_vram=true` coloca o KV cache em RAM do sistema — evita
  crash mas paga em velocidade
  (https://eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling/).
  Relevante como último recurso se um vizinho roubar VRAM a meio de uma
  sessão longa.
- Ordem de ajuste documentada para VRAM apertada: **quantização > ctx >
  batch > camadas GPU > low_vram**
  (https://eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling/).

### 3.5 Flash attention + batch — ganhos pequenos mas grátis

- Flash Attention: ~1.2-1.5x e reduz memória do contexto; precisa de
  build com `GGML_FLASH_ATTN=ON` (binários pré-embalados podem não ter)
  (https://docs.bswen.com/blog/2026-03-15-llamacpp-optimization-speed/).
- Batch size maior acelera prefill (processamento do prompt): ~1.1-1.3x;
  em 12GB usar 256/512 e não valores máximos
  (idem; https://eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling/).
- Ollama vs llama.cpp directo: ~2-3% de diferença — irrelevante para a
  decisão arquitectónica (https://craftrigs.com/guides/best-llm-rtx-3060-12gb-vram-2026).
- Preenchimento do contexto importa: prompts longos são dominados por
  prefill; cortar tokens de input (secção 2) é também uma técnica de
  velocidade aqui, não só de custo.

### 3.6 Reutilizar cache em vez de re-calcular (crítico em partilha)

- **KV cache intra-sessão**: manter prefixo estável entre turns evita
  re-prefill (secção 2.6). Em GPU partilhada é ainda mais valioso: cada
  re-prefill dá aos vizinhos uma janela de contenção.
- **Host-memory prompt caching** (llama.cpp v1.70+, PR #16391): o
  `llama-server` pode manter caches em RAM do sistema
  (`--cram 256`), aliviando a VRAM para o modelo; recomendado
  explicitamente para "limited VRAM (24GB or less)". Contra-indicado para
  prompts <500 tokens e sistemas com <16GB RAM
  (https://github.com/ggml-org/llama.cpp/discussions/20574). NÃO
  VERIFICADO: disponibilidade/equivalentes em Ollama (o Ollama gere slots
  internamente, sem equivalente directo ao `--cram`).
- **`--slot-prompt-similarity`**: pedidos com prompts semelhantes
  reutilizam o slot em vez de re-avaliar (manpage do llama-server).

### 3.7 Gestão de modelos residentes — a alavanca nº1 da GPU partilhada

O Ollama **mantém modelos em VRAM 5 minutos** após o último pedido; se
outros serviços precisam da placa, um modelo "adormecido" bloqueia a
memória. Controlos documentados (https://sumguy.com/ollama-memory-management;
https://www.glukhov.org/llm-performance/ollama/how-ollama-handles-parallel-requests/):

- `keep_alive` por pedido (`"keep_alive": 0` descarrega imediatamente;
  `"5m"`, negativo = nunca descarrega).
- `OLLAMA_KEEP_ALIVE` (global), `OLLAMA_MAX_LOADED_MODELS` (cap de
  quantos modelos ficam residentes), `OLLAMA_NUM_PARALLEL` (nº de
  pedidos em paralelo; valores altos aumentam latência e pressão de
  VRAM; para um agente single-user, 1).
- Padrão para workload batch: carregar, correr, `keep_alive: 0`,
  libertar VRAM (https://www.runaihome.com/blog/ollama-model-keeps-reloading-vram-fix-2026/).
- Trocar de modelo entre pedidos = reload de disco = segundos perdidos
  em cada troca; evitar ter vários modelos "quentes" ao mesmo tempo em
  12GB (https://sumguy.com/ollama-memory-management).
- O Ollama processa pedidos **serialmente por omissão**; para um único
  agente isto é correcto (não há contenção), e `OLLAMA_NUM_PARALLEL>1`
  só é útil com VRAM de sobra (https://eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling/).

### 3.8 MoE em 12GB: a alternativa "velocidade de modelo pequeno, qualidade de grande"

Dois exemplos reais de 2026 de MoE (Mixture-of-Experts) inteiros na VRAM:
- **Qwen3.5-35B-A3B** (3B activos de 35B) em 8GB, Q4_K_M — tutorial do
  autor com `--ctx-size`/`--parallel`/KV a negociar os três
  (https://alejandro.criadoperez.com/blog/Llama_server_memory).
- **Gemma-4-26B-A4B** (4B activos de 26B) em 12GB (RTX 3060): IQ2_M
  ~9.97GB + **cache KV 3-bit** (`-ctk turbo3 -ctv turbo3`, fork
  llama-cpp-turboquant) → 32,768 ctx inteiro em VRAM, **40-55 tok/s**
  (https://github.com/julien9679/Gemma-4-26B-A4B-on-RTX-3060-12GB).
- O Ollama **não faz model-parallelism** (cada modelo usa uma GPU), mas
  um MoE inteiro em 12GB é o caminho para ter "qualidade 26B" com a
  latência de um ~4B (https://eastondev.com/blog/en/posts/ai/ollama-gpu-scheduling/).

**Aviso de calibração:** o exemplo Gemma usa quantização IQ2_M + cache
3-bit (fork não-mainstream) — os números de qualidade e o suporte em
Ollama puro não foram verificados. Para o SUPERDEV isto seria uma
mudança de modelo (qwen3.5:9b → MoE ~24B) e não uma técnica de tuning.

### 3.9 Resumo de acções para o SUPERDEV (GPU 12GB partilhada)

1. Confirmar `num_ctx` 16384 (não 4096 nem 32768) e monitorizar OOM.
2. Verificar se o servidor 11435 suporta forçar cache KV quantizado.
3. `OLLAMA_NUM_PARALLEL=1` e `OLLAMA_MAX_LOADED_MODELS=1` para não
   competir com os vizinhos; `keep_alive` controlado por serviço.
4. System prompt/tool schema estáveis entre turns (cache, secção 2.6).
5. Não carregar modelos concorrentes na mesma placa durante sessões.
6. Para "mais cérebro" mantendo a placa: considerar MoE (secção 3.8)
   como projecto separado, com medição própria antes de adoptar.

---

## 4. Check MODEL-AGNOSTIC vs MODEL-SPECIFIC

Pergunta central do projecto: o motor do SUPERDEV tem de continuar a
funcionar se o modelo mudar (é a filosofia declarada). Este check
classifica cada técnica recolhida nas secções 1-3. **Critério: uma técnica
é MODEL-AGNOSTIC se não depende do formato de saída nem dos tokens
treinados do modelo; é MODEL-SPECIFIC se depende deles.**

### 4.1 O facto estrutural: tool-calling é model-specific por natureza

Tool-calling **nativo** é um formato treinado no modelo — cada família
tem o seu (Qwen usa tokens `tool_calls`, Llama usa JSON, Llama 4 /
Qwen3-Coder usam XML/pythonic). Três fontes independentes confirmam que
todo o tool-calling passa por templates e parsers por família:

- **Ollama**: o parser "references each model's template to understand
  the prefix of the tool call"; os modelos são divididos entre os que têm
  tokens de tool específicos e os que não têm (nestes o parser faz
  fallback a detecção de JSON)
  (https://ollama.com/blog/streaming-tool). O Ollama só expõe a API de
  `tools` para modelos cujo chat template a suporte — o "badge Tools" na
  página do modelo (https://localaimaster.com/blog/ollama-function-calling-tools).
- **vLLM**: tem um parser e um chat-template **por família** (`hermes`
  para Qwen2.5, `qwen3_xml` para Qwen3-Coder, `llama3_json` para Llama,
  `pythonic`, `mistral`, etc.) — o utilizador tem de escolher o parser
  certo ou o tool-call falha
  (https://docs.vllm.ai/en/latest/features/tool_calling/).
- **Continue**: conseguir tool-calling com qwen3-coder exigiu editar o
  template do modelo para o de qwen3 — ou seja, mesmo via Ollama, o
  formato vem do template do modelo
  (https://github.com/continuedev/continue/issues/6913).

Consequência prática: a **abstracção model-agnostic vive no servidor**
(Ollama/llama.cpp escolhem o template/parser pelo modelo), não no motor
do agente. O agente fala OpenAI-compatible e o servidor trata do resto.
Isto é o que o SUPERDEV já faz e está certo.

### 4.2 Taxas de tool-calling bem-formado por modelo (o risco medido)

Testes independentes (2026) com a mesma API Ollama, "schema-correct rate"
= % de tool-calls cujo JSON de argumentos valida contra o schema
(https://localaimaster.com/blog/ollama-function-calling-tools):

| Modelo | Tamanho | Schema-correct | Notas |
|---|---|---|---|
| qwen2.5:14b | 9.0GB | 99% | melhor small-tier |
| qwen2.5:7b | 4.7GB | 98% | melhor balanço latência/fiabilidade |
| llama3.1:8b | 4.9GB | 96% | workhorse fiável |
| llama3.2:3b | 2.0GB | 78% | não fiável acima de 1 tool |

Notas do mesmo teste: modelos <~7B "occasionally hallucinate parameters
or skip required fields"; `gemma2` e `phi3.5` a evitar para multi-tool
(https://localaimaster.com/blog/ollama-function-calling-tools). A
recomendação "default" de 2026 para agentes: **`qwen3:8b`** — e o guia
da Parallel.ai para a série **`qwen3.5` diz "native tool calling across
all sizes"** e recomenda-a como ponto de partida
(https://docs.parallel.ai/integrations/ollama-tool-calling).
Implicação: a escolha actual `qwen3.5:9b` do SUPERDEV está alinhada com
o estado da arte — os incidentes de formato do HISTORICO.md não são
"culpa" da família, são o bug `think=false`+`format` (secção 1.6) e/ou
limites da classe de tamanho.

### 4.3 Classificação das técnicas recolhidas

| # | Técnica (secção) | Classe | Porquê |
|---|---|---|---|
| 1.1 | Repo map (Aider) | **MODEL-AGNOSTIC** | engenharia de contexto; não depende de formato de saída |
| 1.1 | Edição por diff/udiff | **MODEL-SPECIFIC na fiabilidade** | leaderboard do Aider: modelo-dependente; weak models falham formato (73.5% llama3-70b em `diff`); `whole` é o robusto para modelos fracos |
| 1.2 | Papéis apply/autocomplete com modelo pequeno | AGNOSTIC no conceito, SPECIFIC na prática | precisa de modelos diferentes; fast-apply são modelos afinados |
| 1.3 | System prompt pequeno (Roo vs Cline) | **MODEL-AGNOSTIC** | é custo por pedido, não formato |
| 1.5 | CodeAct (smolagents, MS) | **MODEL-AGNOSTIC por construção** | o modelo escreve código, não tokens de tool-call; depende da habilidade de escrever código (universal) |
| 1.6 | GBNF / `json_schema` (llama.cpp) | **MODEL-AGNOSTIC por construção** | máscara de tokens na amostragem; não depende de treino de formato. Custo: 5-15% throughput; bugs com schemas complexos em alguns modelos |
| 1.4 | Qwen-Agent (templates/parsers internos) | **MODEL-SPECIFIC por desenho** | amarra-se à convenção de tool-calling de cada modelo da família Qwen |
| 2.1 | CodeAct / colapsar passos | **MODEL-AGNOSTIC** | 52% latência / 64% tokens, medido, modelo inalterado |
| 2.3 | Compactação de histórico | **MODEL-AGNOSTIC** | summarize em vez de append; só cuidado com KV-cache |
| 2.4 | Contexto selectivo (AST/LSP) | **MODEL-AGNOSTIC** | menos input, mesmo modelo |
| 2.8 | Routing de modelos | AGNOSTIC no conceito, SPECIFIC na infra | exige vários modelos disponíveis |
| 3.2 | KV cache quantizado | **MODEL-AGNOSTIC** | nível de motor |
| 3.7 | keep_alive / num_parallel / max_loaded | **MODEL-AGNOSTIC** | nível de servidor |
| 3.8 | MoE em 12GB | AGNOSTIC no conceito | qualquer MoE serve; depende do modelo escolhido |
| 4.1 | Tool-calling via Ollama | SPECIFIC no fundo, **AGNOSTIC na interface** | o servidor abstractiza template/parser; a API do agente não muda |

### 4.4 Conclusão do check

- **O que mantém o SUPERDEV model-agnostic é a camada de servidor**
  (Ollama + OpenAI-compatible), não código próprio. Manter o motor a
  falar essa API é o suficiente para trocar de modelo sem mexer no motor.
- **As três técnicas "por construção" mais agnósticas** (GBNF, CodeAct,
  contexto selectivo) são as que não dependem do capricho do modelo — e
  coincidem com os maiores ganhos medidos de tokens/latência.
- **Onde o modelo vaza para o agente:** qualidade do tool-call (a "Taxa
  schema-correct" varia 78-99% pela família/tamanho) e qualidade das
  edições em formato diff. O SUPERDEV já mitigou o primeiro com `format`
  (quando funcionava) e o segundo ainda não tenta (edita ficheiros
  inteiros — ver secção 6).
- Verificação concreta pedida pelo comando: o `config.py` do SUPERDEV já
  documenta que o template de tool-calling **é por modelo** e que "a
  verificação tem de acontecer por mudança de modelo". Esta pesquisa
  confirma-o com fontes (Ollama blog, vLLM docs, Continue issue) e acrescenta
  que o teste a fazer por mudança de modelo é o de **schema-correct rate**
  (método replicável da secção 4.2), não só "conseguiu chamar a tool?".
- Nota: nenhuma destas técnicas é "verdade universal"; as medições de
  4.2 são de um único autor com o seu workload
  (https://localaimaster.com/blog/ollama-function-calling-tools).
  Servem para comparar ordens de grandeza, não como lei.

---

## 5. Evidência do mundo real — queixas e soluções de quem constrói agentes locais

O objectivo desta secção é verificar se os incidentes documentados no
`HISTORICO.md` do SUPERDEV são excentricidades do projecto ou problemas
conhecidos e generalizados do ecossistema (e se as soluções escolhidas
batem certo com o que a comunidade encontrou).

### 5.1 Truncamento silencioso de contexto — o incidente nº1 do ecossistema

O incidente `num_ctx=4096` do SUPERDEV (o início do contexto era cortado
silenciosamente) é provavelmente o problema mais reportado de agentes
locais. Fontes independentes:

- **Ollama #8531**: "Ollama truncates beginning of user messages and
  system prompt when exceeding context window" — confirmado pelos
  maintainers (https://github.com/ollama/ollama/issues/8531).
- **Qwen Code #4657** (diagnóstico mais preciso): "when the prompt
  overflows, Ollama silently rolls the KV cache from the front, dropping
  the system prompt and tool definitions first. That's why the agent
  'forgets the original context' and then produces narrative text without
  ever emitting a tool call." Fix recomendado: gravar `num_ctx` num
  Modelfile derivado (sobrevive a restarts, ao contrário do env var)
  (https://github.com/QwenLM/qwen-code/issues/4657).
- **Aider + Ollama (2026)**: "Ollama defaults to a 2,048-token context
  window and silently discards anything beyond that... 80% of the public
  tutorials produce broken output because of it"; `OLLAMA_CONTEXT_LENGTH
  =16384` como chão
  (https://dev.to/jovan_chan_9500711396d4e6/aider-ollama-local-llm-setup-guide-2026-official-config-model-selection-context-fix-5hfk).
- **Gist kaapstorm (OpenCode+Ollama+Qwen3.5-9B, Jul 2026)**: "Ollama
  defaults to a 4096-token context window. OpenCode needs at least 16k–
  64k to function reliably"
  (https://gist.github.com/kaapstorm/b612e270e34906a392de8b01c7d792f8).
- **Ollama docs recomendam ≥64K** para "web search, agents, and coding
  tools" (https://markaicode.com/errors/ollama-context-length-exceeded-fix) —
  um alvo fisicamente impossível em 12GB partilhada com 9B (secção 3).
  Isto é o argumento central para o SUPERDEV **não** subir o contexto ao
  máximo, mas sim **gerir o contexto** (secções 2.3/2.4): a comunidade
  ainda recomenda contexto grande; os builders com VRAM curta resolvem
  com compactação/routing, não com contexto enorme.

**Conclusão de calibração:** a decisão `num_ctx=16384` do HISTORICO é a
recomendação chã da comunidade para 12GB; o problema de fundo (Ollama
cortar o início sem aviso) continua por resolver no servidor e o
SUPERDEV já o mitigou controlando o comprimento por código — correcto.

### 5.3 XML vs JSON nos tool-calls — dependente do tamanho do modelo

Issue #125 da família Qwen (Abr 2026, SGLang): com tool-call parser
activado, os Qwen3.5 geram **XML** em vez de JSON — e o padrão é
model-size dependent:
- 4B: maioritariamente JSON válido;
- 9B: instável, frequentemente XML;
- 35B-A3B: falha consistentemente.

E, num detalhe que interessa ao SUPERDEV, o XML aparece por vezes **no
canal de reasoning** (`reasoning_content`), onde o parser não o apanha —
o pedido devolve tool_calls vazio e o agente fica sem acção. Repro
final: 10/12 sucesso (https://github.com/QwenLM/Qwen3.6/issues/125).
Há ainda relato (NVIDIA forums, DGX Spark) de que a escolha do parser
importa (`qwen3_xml` vs `qwen3_coder`) e que o chat template do Qwen3.5
tinha um bug que exigia patch
(https://forums.developer.nvidia.com/t/qwen3-5-tool-calling-finally-fixed-possibly/366451).

**Conclusão de calibração:** o facto de o SUPERDEV correr `qwen3.5:9b` —
exactamente o tamanho "instável" da família — explica parte dos
incidentes de formato do HISTORICO sem qualquer culpa da lógica do motor.
A mitigação `format`+`think=False` bateu com o bug documentado na secção
1.6 (constraint ignorado) e com o padrão XML/malformado da família.
Nota: o guia de 2026 para agentes recomenda `qwen3:8b` (geração anterior)
como default por consistência — a troca para `qwen3.5:9b` trouxe
capacidade mas estabilizou mais tarde na série
(https://localaimaster.com/blog/ollama-function-calling-tools).

### 5.4 repeat_penalty: o paradoxo da verbosidade

Dois lados da mesma moeda, ambos com fontes:

- O incidente "repeat loops" do SUPERDEV (fix: `repeat_penalty=1.3`) é um
  sintoma conhecido: o PSA clássico de r/LocalLLaMA mostra que
  `repeat_penalty` 1.15-1.20 **sufoca a saída** — "the easiest way to
  avoid repetition is to just keep the output short" — e baixar para
  1.05-1.08 gera saídas muito mais longas mantendo o controle
  (https://www.reddit.com/r/LocalLLaMA/comments/188v3kj/psa_if_your_model_isnt_producing_enough_text_try/).
- Contradição potencial: um guia da comunidade (qwen-ai.com) afirma que
  em Qwen 3.5 via Ollama, `repeat_penalty`/`frequency_penalty`/
  `presence_penalty` são **silenciosamente ignorados** — aceites sem erro
  mas sem efeito (https://qwen-ai.com/run-qwen-ollama/). NÃO VERIFICADO e
  em conflito com a experiência medida do próprio SUPERDEV (em que
  `repeat_penalty=1.3` resolveu o loop). Possível explicação: diferença de
  versões do Ollama (o comportamento varia entre releases — ver 5.2) ou
  o penalty a actuar sobre o texto de thinking em vez do texto final.
  Regra: confirmar na versão instalada antes de confiar.

**Conclusão de calibração:** o valor 1.3 escolhido está dentro da gama
documentada como eficaz contra loops; se a verbosidade do modelo parecer
cortada, a comunidade sugere testar 1.05-1.08. Não mexer sem rever o
histórico de incidents.

### 5.5 Relatos de setups que "funcionam" no mundo real (2026)

- **Stack completo local (Ollama + Qwen3-Coder 8B em 8GB)**: chat
  (Continue) + autocomplete (StarCoder2 3B) + agente autónomo (Cline).
  Aviso honesto do guia: "agentic loops burn context fast and lean hard
  on model capability. On 8 GB hardware keep tasks small and
  single-file" (https://llmconfigurator.com/en/guides/coding-agents/setup-local-coding-agent).
  É a mesma conclusão do canitrun.dev (secção 1.3): a 12GB, tarefas
  multi-ficheiro autónomas estão no limite.
- **Qwen 3.5 + Ollama + OpenClaw**: relato de 48h de teste — tool calling
  "leap" vs 2.5, "sempre-em-diante" para agentes, 8B corre confortável em
  RTX 3060 12GB (https://matteogiardino.com/en/blog/qwen-35-ollama-openclaw-setup-guide).
  Nota: quem usa agentes com Qwen 3.5 via Ollama é aconselhado a
  confirmar a versão do Ollama (bugs da série 0.17.x — ver 5.2).
- **Loop de agente em produção com Qwen 3**: guia reporta que o
  `think=True` "reveals intermediate reasoning, which is invaluable for
  debugging agent behavior" — argumento a ponderar contra a decisão do
  SUPERDEV de desligar o thinking
  (https://niteagent.com/blog/2026-06-03-ollama-agent-loop-production-guide/).
- **Routing + auto-unload de VRAM entre modelos**: tool comunitário que
  encadeia um modelo pequeno com um grande e **descarrega VRAM entre
  eles** (r/ollama) — implementação directa do keep_alive da secção 3.7,
  prova de que a técnica se usa no terreno para GPU partilhada
  (https://www.reddit.com/r/ollama/comments/1uqxbe0/i_made_a_tool_that_chains_a_small_local_model/).
- **"É tãooo lentoo"**: o queixume mais comum de agentes locais é o
  modelo errado para a tarefa ("For non-coding tasks... a smaller model
  will be capable, and faster") e o contexto errado — não a placa
  (https://gist.github.com/kaapstorm/b612e270e34906a392de8b01c7d792f8;
  https://tecnobits.com/en/how-to-speed-up-rocama-complete-guide-for-your-local-ai/).

### 5.6 Síntese: o que a comunidade confirma sobre o SUPERDEV

| Incidente do HISTORICO.md | Verificação externa |
|---|---|
| num_ctx=4096 trunca o início silenciosamente | Confirmado generalizado (5.1) |
| repeat loops; repeat_penalty=1.3 resolveu | Comportamento conhecido; valor na gama certa; atenção a versões (5.4) |
| Subir MAX_VOLTAS_FERRAMENTAS não reduz tokens (reenvio da conversa) | Confirmado estruturalmente: cada turn reenvia o contexto (secção 2.1) |
| format+think=False não restringiu | Consistente com bug conhecido na série qwen3.5 (1.6, 5.3) |
| Open WebUI 3 chamadas escondidas | Não verificado nesta pesquisa; fora de âmbito |

Conclusão geral: o SUPERDEV bateu com os mesmos problemas que toda a
comunidade local — as suas soluções estão alinhadas com as práticas
dominantes (16384 de contexto, penalty controlado, prompt de sistema
curto, controlo do comprimento por código). Os pontos onde o ecossistema
aponta para além do que o SUPERDEV faz hoje estão na secção 6.

---

## 6. Matriz de recomendação

Recapitulando as restrições do SUPERDEV: motor agnóstico (filosofia),
modelo actual `qwen3.5:9b` via Ollama (porta 11435), num_ctx 16384, GPU
12GB **partilhada**, memória e web search já resolvidos (não recomendadas
aqui). Cada recomendação indica o ganho (com evidência), o custo de
adopção e a classe (secção 4).

### 6.1 Recomendações A — baixo custo, config/pequenas (fazer já)

| # | Recomendação | Ganho (evidência) | Custo | Classe |
|---|---|---|---|---|
| A1 | Confirmar que a versão do Ollama da porta 11435 inclui o fix do bug "tool-call impresso como texto" (PR #15022; workaround 0.17.5) | Elimina o incidente reportado no qwen3.5:9b (secção 5.2) | 5 min: `ollama --version` + changelog | AGNOSTIC |
| A2 | `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `keep_alive` controlado por pedido | Evita contenção/swap de VRAM com vizinhos na placa partilhada (secção 3.7) | 10 min: env vars no serviço | AGNOSTIC |
| A3 | Gravar `num_ctx` num Modelfile derivado, não depender só de env var | `num_ctx` sobrevive a restarts; evita o roll silencioso do início (secção 5.1) | 15 min + re-teste | AGNOSTIC |
| A4 | Manter system prompt + definições de tools **estáveis e na mesma ordem** entre turns | Reuso do KV-cache local (sem re-prefill) — equivalente local do prompt caching (secções 2.6, 3.6) | Config: não reordenar schema dinamicamente | AGNOSTIC |
| A5 | Contar tokens do prompt e manter margem de segurança (10-15%) sob os 16384 | Evita o roll silencioso antes do limite (secção 5.1) | Pequeno: função de contagem no motor | AGNOSTIC |
| A6 | Verificar cache KV quantizado no servidor 11435 e activar se possível | Até ~75% menos VRAM do KV cache → mais folga com vizinhos (secção 3.2) | Teste: `ollama ps` + `nvidia-smi` | AGNOSTIC |

### 6.2 Recomendações B — médio custo, mudanças de comportamento

| # | Recomendação | Ganho (evidência) | Custo | Classe |
|---|---|---|---|---|
| B1 | Compactação de histórico (summarize a cada N turns em vez de append) antes de bater no limite | Sessões longas cabem nos 16384 sem cortar o início; padrão `/compact` (secção 2.3) | Médio: função de resumo + política (a cada 10-15 turns) | AGNOSTIC |
| B2 | Contexto selectivo: em vez de ficheiros inteiros, injectar símbolos/assinaturas (mapa AST) ou ranges de linhas | ~65% de redução de input (secção 2.4) | Médio: mapa AST leve por projecto | AGNOSTIC |
| B3 | Batching de tool-calls: aceitar N chamadas na mesma resposta do modelo (confirmar qwen3.5) | Reduz turnos e reenvio do histórico entre passos (secções 2.1, 2.7) | Médio: lógica de loop aceitar lista de tool_calls | AGNOSTIC |
| B4 | Teste de schema-correct rate por mudança de modelo (método secção 4.2) | Dá métrica objectiva antes de adoptar um modelo novo (secção 4.4) | Baixo-médio: mini-script de validação | AGNOSTIC |

### 6.3 Recomendações C — custo alto / mudança de paradigma (avaliar em projecto separado)

| # | Recomendação | Ganho (evidência) | Custo | Classe |
|---|---|---|---|---|
| C1 | **CodeAct** — o modelo escreve código que chama as ferramentas, executado em sandbox, em vez de N tool-calls | 52% latência / 64% tokens, medido pela MS; a técnica agnóstica mais forte (secções 2.1, 4.3) | Alto: sandbox (Docker/Hyperlight/E2B), refactor do loop, segurança | AGNOSTIC |
| C2 | Edição por diff (SEARCH/REPLACE) em vez de reescrita integral | Menos tokens por edição; cuidado: fiabilidade do formato é model-dependent (secções 1.1, 4.3) | Médio-alto: formatos de edição + parser; risco em modelo pequeno | SPECIFIC na fiabilidade |
| C3 | Routing de modelos (pequeno para tarefas simples, grande para difíceis) | Aider `--weak-model`; RouteLLM 85% custo com 95% performance (secção 2.8) | Alto: segundo modelo carregado, gestão VRAM — em 12GB partilhada é delicado | SPECIFIC na infra |
| C4 | MoE ~24-35B em 12GB (Qwen3.5-35B-A3B / Gemma-4-26B) como upgrade de cérebro | 40-55 tok/s com qualidade 26B, medido (secção 3.8) | Alto: modelo novo + fork/kernel optimizado; NÃO VERIFICADO em Ollama puro | SPECIFIC (modelo) |

### 6.4 O que NÃO adoptar (com base nesta pesquisa)

- **Cline/Roo-Code como motor**: assumem contexto 32K+ e system prompts
  grandes; em 12GB partilhada ficam sem espaço — são para hardware maior
  ou modelos cloud (secções 1.3, 5.5).
- **Qwen-Agent como framework**: model-specific por desenho; contradiz a
  filosofia agnóstica do SUPERDEV (secção 1.4).
- **`format`+`think=False` como fix de structured output**: a
  combinação é a causa conhecida do constraint ignorado na série
  qwen3.5 (secção 1.6). Testar caminho alternativo: `think=False` sem
  `format`, ou `format` com thinking activo, ou gramática GBNF no
  servidor (se a versão suportar) — com medição de schema-correct rate.
- **Contexto 32K-64K "como manda a doc do Ollama"**: impossível em 12GB
  partilhada; o caminho é gerir o contexto (B1/B2), não alargá-lo
  (secções 3.3, 5.1).

### 6.5 Ordem de execução sugerida

1. **A1-A6** (uma manhã) — elimina bugs conhecidos e estabiliza a placa
   partilhada. A1 primeiro (bug directo do modelo actual).
2. **B4** — métrica de schema-correct para o estado actual (baseline).
3. **B1, B3** — ganho de tokens/robustez sem mudar paradigma.
4. **B2** — maior redução de input com menor risco (contexto selectivo).
5. **C1 (CodeAct)** — o maior ganho medido da pesquisa, mas exige
   sandbox e refactor; tratar como projecto próprio com o baseline B4 a
   medir antes/depois.
6. C2/C3/C4 — só depois de estabilizar; cada uma traz um modelo ou
   formato novo e deve passar pelo teste B4.

Fim da pesquisa. Nota de método: todas as medições citadas são de
terceiros e dependem do workload de cada um; o padrão recomendado pelo
próprio mercado é medir no workload real antes de adoptar (secção 2.9).
