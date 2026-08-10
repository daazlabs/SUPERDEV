# Histórico de implementação — SUPERDEV

Registo do que foi construído e porquê, por ordem cronológica. Só entra
aqui o que já está feito e testado — não planos nem próximos passos.

---

## 8 Ago 2026 — Fundação do projecto

**O quê:** Agente especialista em programação, em Python, a correr o
`qwen3.5:9b` via Ollama local. Estrutura criada em `/mnt/sovereign/superdev/`.

**Porquê Python e não Rust:** o gargalo de velocidade de um agente
destes é quase todo a geração de tokens do modelo (que corre em
C/C++ por baixo, via llama.cpp/Ollama) — o código à volta (Python)
passa a maior parte do tempo à espera, não a calcular. Rust ganharia
em concorrência massiva ou em construir o próprio motor de inferência;
nenhum dos dois é o caso aqui. Python ganha em ecossistema e
velocidade de iteração, e isso pesa mais à medida que o agente cresce.

**Porquê especialização em programação:** é o único domínio com um
"juiz" externo objectivo e barato — o código corre ou não corre, os
testes passam ou não passam. Isso permite usar verificação e
estrutura para compensar um modelo pequeno, em vez de precisar de mais
parâmetros.

---

## `config.py` — núcleo mínimo por pedido

Todos os pedidos ao Ollama são sem estado — o modelo não se lembra de
nada entre chamadas, só sabe o que está escrito nesse pedido exacto.
Por isso o núcleo (`CORE_IDENTITY`) é propositadamente curto: só o
que é indispensável em *todos* os pedidos. Tudo o resto (memória,
conhecimento) é ido buscar por pedido, nunca carregado por defeito.

---

## `agent.py` — ciclo do agente

Ciclo simples: recebe o pedido → monta o contexto mínimo → chama o
Ollama → devolve a resposta. Cada peça é uma função separada e
chamável directamente (`ollama_chat`, `build_system_prompt`,
`responder`) para se poder testar/depurar uma peça isolada sem correr
o agente todo.

---

## `think=False` — desligar o modo "pensamento" do qwen3.5

Testado em 8 Ago 2026, com dados reais (ver `logs/chamadas.jsonl`):

| | thinking ligado (default Ollama) | thinking desligado |
|---|---|---|
| Pergunta trivial | 19.2s, 765 tokens | 1.1s, 34 tokens |
| Bug de código (argumento por defeito mutável) | 33.1s, 1320 tokens, resposta incompleta | 2.8s, 102 tokens, resposta completa (incluiu a correcção) |

Nos dois testes, desligar o "thinking" não perdeu qualidade — pelo
contrário, deu a resposta mais completa das duas no caso do bug. Fica
desligado por defeito. Não é uma técnica nova construída por nós — já
existe nativamente na API da Ollama (`"think": false`), só não vinha
ligada.

---

## `logs/chamadas.jsonl` — o "espião"

A Ollama já devolve, por cada pedido, os tokens de prompt vs. geração
e a decomposição de tempos (carregar modelo / ler pergunta / gerar
resposta) — o agente estava a descartar essa informação. Agora cada
pedido fica registado: tamanho do contexto enviado, memórias usadas
(e com que pontuação), `OPTIONS` activas, tokens de pensamento vs.
resposta, tempos de cada fase. Serve para deixar de adivinhar e passar
a medir sempre, incluindo em uso real, não só em testes isolados.

---

## `memory.py` — memória por recuperação semântica (RAG)

Em vez de carregar sempre um índice de tudo (que cresce para sempre à
medida que o agente acumula memórias), cada facto vive num ficheiro
`.md` próprio em `memory/`, com o embedding calculado uma vez e
guardado em cache (`memory/_index.json`) — só recalcula quando o
ficheiro muda. Por pedido, só entram no contexto as memórias mais
relevantes para esse pedido específico.

**Pontuação híbrida (semântica + palavras-chave), não semelhança
vectorial pura.** Testámos primeiro só com semelhança vectorial e uma
pergunta feita de forma coloquial ("porque é que a GPU anda sempre
cheia?") falhou — a memória certa ficou em 2º lugar, atrás de uma sem
qualquer relação. Tentámos corrigir pedindo ao próprio modelo para
reformular a pergunta antes de pesquisar; falhou também, porque o
modelo elaborou a mais e inventou conceitos que não estavam no pedido
original. A correcção que funcionou: somar à semelhança vectorial uma
pontuação mecânica de sobreposição de palavras-chave exactas (sem
depender do modelo "adivinhar" bem) — depois desta mudança, o mesmo
caso que falhava passou a acertar.

**Threshold mínimo de confiança.** Uma memória errada injectada no
contexto, com ar de relevante, engana o modelo mais do que não ter
memória nenhuma — por isso memórias abaixo de uma pontuação mínima
ficam de fora, mesmo que sejam as "melhores disponíveis". Testado: uma
pergunta parafraseada de forma muito diferente da memória ("memória de
vídeo" em vez de "VRAM") não encontrou nada — não é o resultado ideal,
mas é o resultado seguro, preferível a devolver a memória errada.

---

## `tools.py` + ciclo de ferramentas no `agent.py` — primeira ferramenta real

**Primeira tentativa falhada:** tentámos decodificação constrangida
com o parâmetro genérico `"format"` da Ollama (um schema JSON nosso).
Testado com dois casos: quando precisava de ler um ficheiro, o modelo
devolveu um JSON com uma forma diferente da que pedimos
(`name`/`arguments`, não `usar_ferramenta`/`ferramenta`/`caminho`);
quando não precisava, ignorou o schema por completo e escreveu texto
livre. Ou seja, `"format"` não estava a restringir nada de facto.

**O que funcionou:** a API nativa de "tools" da Ollama (convenção de
function-calling, `tools` no pedido, `tool_calls` na resposta) — é
esta que o qwen3.5 foi treinado a respeitar, confirmado pelo
`PARSER qwen3.5` dedicado que a Ollama usa para este modelo. Testado
nos dois casos (precisa / não precisa de ferramenta): acertou nos
dois, com o nome do argumento (`caminho`) já a bater certo com a
função Python real, sem termos de traduzir nada.

**Ferramenta implementada:** `ler_ficheiro` — lê um ficheiro de texto
do disco, com limite de 8000 caracteres para não rebentar o contexto,
e falha de forma clara (não inventa conteúdo) se o ficheiro não
existir ou não for legível.

**Ciclo do agente:** uma chamada com as ferramentas disponíveis; se o
modelo pedir uma, executa-se a função real e volta-se a chamar o
modelo com o resultado para a resposta final; se não pedir nenhuma,
usa-se a resposta directa. Testado ponta a ponta: leu um ficheiro real
e resumiu-o correctamente; uma pergunta normal, sem precisar de
ferramenta, continuou a responder directamente sem se perder no meio
do ciclo.

**Risco conhecido, documentado em `config.py` e `tools.py`:** o que
funcionou (a API `tools`) funciona porque a Ollama tem um
interpretador dedicado a este modelo em concreto (`PARSER qwen3.5`).
Isto não é garantido para outro modelo — trocar `config.MODEL` obriga
a re-validar `tools.py` do zero, não é uma troca de uma linha.

---

## Correcções de ambiente descobertas a testar (não são decisões de
## arquitectura, são factos da máquina)

- A Ollama corre na porta **11435**, não a 11434 por defeito —
  configurado em `/etc/systemd/system/ollama.service.d/override.conf`.
- A GPU (12GB) é partilhada com outros serviços (ex: `llama-server` de
  35B) — testado com os dois a correr ao mesmo tempo e a resposta
  demorou mais de 5 minutos por falta de VRAM livre. Resolvido à parte
  (fora deste projecto) com um mecanismo de ligar/desligar o modelo de
  35B.

---

## Mais ferramentas + BUG REAL encontrado e corrigido (9 Ago 2026)

**Duas ferramentas novas**, mesmo espírito do `ler_ficheiro` (só
leitura, nunca inventa, falha de forma clara): `listar_ficheiros`
(lista uma pasta, não recursivo) e `procurar_texto` (procura um termo
exacto num ficheiro ou, recursivamente, numa pasta inteira, ignorando
`.git`/`__pycache__`/`node_modules`/`venv`). As três têm limites de
corte claros (entradas listadas, resultados encontrados, ficheiros
percorridos), mesma lógica do `LIMITE_CARACTERES` já existente.

**Teste 1 — o modelo escolhe bem entre 3 ferramentas?** Sim. Testado
com um pedido para cada ferramenta (listar uma pasta / ler um
ficheiro concreto / encontrar onde está definida uma variável) —
acertou a ferramenta certa e os argumentos certos nos 3 casos,
confirmado inspeccionando directamente o `tool_calls` da resposta
(não só o texto final, que podia estar certo por coincidência).
Testado também que uma pergunta normal, sem precisar de ferramenta
nenhuma, continua a responder directamente com as 3 ferramentas
disponíveis — não ficou confuso por ter mais opções.

**Teste 2 — um pedido que precisa de duas ferramentas em sequência
(listar uma pasta, depois ler um ficheiro lá dentro) — BUG REAL:**
a resposta final vinha **vazia**. Investigado ao nível da chamada:
o `agent.py` só oferecia `tools` na 1ª volta ao modelo; depois de
executar a 1ª ferramenta pedida (`listar_ficheiros`), a 2ª chamada à
Ollama já não tinha `tools` disponível — e o modelo, que queria pedir
`ler_ficheiro` a seguir, não tinha como. Confirmado a causa com um
teste directo: oferecendo `tools` também na 2ª volta, o modelo pediu
correctamente `ler_ficheiro` a seguir.

**Correcção:** `responder()` deixou de ser "no máximo uma volta de
ferramentas" e passou a ser um ciclo — oferece sempre `tools`, executa
o que for pedido, repete, até o modelo não pedir mais nenhuma ou até
`MAX_VOLTAS_FERRAMENTAS` (5, protecção contra ciclo infinito, devolve
erro claro se for atingido em vez de ficar preso). Reteste completo
depois da correcção: o pedido composto passou a devolver um resumo
real do `config.py` (fez `listar_ficheiros` → `ler_ficheiro` →
resposta final, confirmado nos logs pela sequência
`pediu_ferramenta=True,True,False`); os testes de ferramenta única e
o de pergunta directa continuaram a funcionar sem gastar voltas a
mais.

**Porque interessa este bug:** não era um caso extremo raro — é o
padrão mais óbvio de tarefa de programação ("vê o que há na pasta e
depois lê o ficheiro X"). Um agente que só suporta uma ferramenta de
cada vez, sem se aperceber disso, falha em silêncio (resposta vazia,
sem erro nenhum) exactamente no tipo de pedido em que mais se confia
nele.

**Descoberta extra durante estes testes:** o modelo por vezes pede
duas ferramentas de uma vez na mesma mensagem (`tool_calls` com 2
entradas — chamadas paralelas), não sempre uma de cada vez. Confirmado
inspeccionando directamente a resposta da Ollama. O `agent.py` já
aguentava isto bem (percorre `mensagem["tool_calls"]` em ciclo), mas
foi bom confirmar que os dois padrões (paralelo numa volta / sequencial
em várias voltas) acontecem ambos na prática, e que a correcção acima
cobre os dois.

---

## Revisão dos `OPTIONS` + BUG REAL nº 2: `num_ctx` demasiado baixo (9 Ago 2026)

**Ponto de partida:** `ollama show qwen3.5:9b` dá os valores que o
próprio Qwen recomenda de fábrica (o Modelfile do modelo):
`temperature=1`, `top_p=0.95`, `top_k=20`, `presence_penalty=1.5`,
context length nativo `262144`. Os nossos `OPTIONS` (herdados do
Paulito, nunca revistos) divergiam em quase tudo, sem se saber se de
propósito ou por esquecimento.

**`presence_penalty` — confirmado que está activo mesmo sem estar no
nosso `config.py`.** Pesquisado nos docs oficiais da Ollama: uma opção
que não vai no pedido não é reposta a zero, herda o valor do Modelfile
do modelo. Como nunca definimos `presence_penalty`, o travão de
repetição de 1.5 do Qwen está activo "nas costas" desde sempre — só
não estava documentado. Decisão: manter por herança automática (não
definir explicitamente), mas documentar isto no `config.py` para
ninguém pensar que está desligado.

**`temperature=0.2` — mantido, divergência intencional.** Baixo de
propósito para determinismo em código, prática comum em agentes deste
tipo; diverge do `1.0` de chat geral do Qwen mas por boa razão.

**`top_p`/`top_k` — alinhados aos valores do Qwen** (`0.95`/`20`, não
os `0.9`/`40` herdados do Paulito). Com temperatura tão baixa o efeito
prático é pequeno, mas sem razão para divergir do que o modelo foi
afinado a usar.

**`num_ctx=4096` — BUG REAL, mesmo estilo do bug das ferramentas: falha
silenciosa.** Testado deliberadamente um caso limite: pedir para ler
dois ficheiros perto do limite de `tools.LIMITE_CARACTERES` (8000
caracteres cada) e somar as funções dos dois. Com `num_ctx=4096`, o
`prompt_eval_count` bateu exactamente no tecto (4096) — a Ollama
cortou silenciosamente o início da conversa (o 1º ficheiro lido e
parte das instruções) para caber o resto, sem devolver erro nenhum. O
agente respondeu com confiança usando só o que sobrou (só falou do 2º
ficheiro, "32 funções", ignorando o pedido de somar os dois) — nenhum
sinal de que tinha perdido informação.

**Medição de VRAM antes de decidir o novo valor** (em vez de adivinhar):
com o modelo descarregado, GPU em ~640MB. Carregado, o custo é
dominado pelo modelo em si, não pelo `num_ctx` — testado ao vivo com
`num_ctx` em 2048/4096/8192/16384/32768: ~8.5GB a 2048, só ~9.0GB a
16384, ~9.7GB a 32768. Ou seja, subir o `num_ctx` de 4096 para 16384
custou uns ~500MB extra, não vale a pena poupar aqui.

**Escolhido `num_ctx=16384`.** Reteste do caso que falhava, agora com
16384: respondeu certo — "Ficheiro 1: 32, Ficheiro 2: 32, Total: 64" —
usando as duas ferramentas correctamente (`prompt_eval_count=4835`,
bem dentro do novo tecto). Confirmado com a config real do ficheiro,
não só com o valor manipulado em memória durante o teste.

**`num_predict=2048` — novo, não existia.** Antes não havia tecto
nenhum ao tamanho da resposta (só limitado pelo espaço livre no
`num_ctx`). Para um agente que promete respostas curtas, um tecto
explícito é rede de segurança, não travão do dia-a-dia.

**Achado à parte (fora do `config.py`):** o drop-in do systemd
`numctx.conf` dizia `OLLAMA_NUM_CTX=8192`, mas o `override.conf`
(carrega depois, por ordem alfabética) sobrepõe-no com `4096` —
confirmado no ambiente real do processo (`systemctl show`). Era
configuração morta, do mesmo tipo dos cron jobs encontrados na revisão
de backups — não decidia nada, só enganava quem olhasse para lá a
pensar que estava a ter efeito. Remoção pedida ao utilizador (precisa
de `sudo` com password, não corre em modo não-interactivo).

**Esclarecimento importante, discutido com o utilizador depois desta
revisão:** `num_ctx` não é uma torneira de economia de tokens — testado
ao vivo o mesmo pedido trivial com `num_ctx` entre 2048 e 32768: tokens
gastos e tempo de resposta ficaram *idênticos* em todos os valores
(`prompt_eval_duration_s` ~0.45s, `eval_duration_s` ~0.03s, sempre).
`num_ctx` só entra em jogo quando o que está realmente a ser usado se
aproxima do tecto — é um tecto de segurança, não um travão do dia-a-
-dia. Confundir os dois leva à tentação errada de o manter pequeno
"para poupar", quando na prática isso só troca uma resposta mais longa
por uma falha silenciosa (o bug documentado acima).

---

## Memória de conversa — curto prazo + destilação automática (9 Ago 2026)

**O problema real que motivou isto:** até aqui, cada `responder()`
começava do zero — nenhuma troca da conversa actual sobrevivia à
seguinte (confirmado a olhar para `main()`: não guardava nada entre
iterações do `while`). Não era "económico", era memória zero — o
agente não conseguia ter uma conversa, só respostas isoladas.

**Duas estruturas com propósitos diferentes, ambas na `sessao` (dict
devolvido por `nova_sessao()`, passado a cada `responder()`):**
- `historico` — janela fixa (`MEMORIA_CURTO_PRAZO_TROCAS=4` trocas),
  sempre enviada ao modelo, desliza (trocas antigas saem do prompt).
  Dá coerência imediata sem o prompt crescer sem parar.
- `buffer_destilar` — acumula as mesmas trocas até
  `MEMORIA_DESTILAR_A_CADA_TROCAS=6`, altura em que o próprio modelo é
  chamado para resumir o que vale a pena persistir, grava em
  `memory/*.md` (mesmo mecanismo RAG já existente) e o buffer é
  limpo. Decisão do utilizador: automático, não à espera de um
  comando — risco aceite de poder gravar ruído, mitigado como abaixo.

**Testado: coerência de curto prazo funciona.** "O meu projecto
chama-se DaazPrisma e uso Python 3.12" seguido de "qual é o nome do
meu projecto e que versão de Python uso?" — respondeu certo aos dois,
usando só a janela curta (sem tocar em memória persistente).

**BUG REAL na destilação, encontrado e corrigido:** primeira versão do
prompt de destilação, testada com "prefiro sempre respostas em
português europeu, nunca brasileiro" seguido de "qual é a capital de
Portugal?" — gravou **"A capital de Portugal é Lisboa"** (trivial, o
modelo já sabe isto, redundante) e **ignorou** a preferência real do
utilizador, que era o único facto que valia a pena guardar. Confirmado
que a resposta "correcta" que veio a seguir numa sessão nova
("português de Portugal") não veio da memória — `memory.retrieve()`
devolveu zero resultados para essa pergunta, foi só o modelo a
adivinhar bem pelo contexto geral da conversa (podia ter adivinhado
mal). **Correcção:** prompt de destilação reescrito para pedir
explicitamente factos "sobre o utilizador, o projecto ou decisões
tomadas na conversa", com um exemplo do que extrair e um exemplo do
que NÃO extrair (conhecimento geral). Reteste com o mesmo par de
frases: gravou só a preferência, ignorou correctamente a trivialidade.

**Achado extra, ainda por resolver (não é bug novo — é o aviso que já
estava escrito em `memory.py` desde 8 Ago, agora confirmado com um
caso real):** a memória da preferência, depois de gravada, ficou com
pontuação **0.579** para a pergunta "em que variante do português devo
responder?" — abaixo do `MEMORY_MIN_SCORE=0.6` por uma margem mínima
(0.021), apesar de semanticamente relevante (0.72) e com sobreposição
de palavras real ("português" nos dois). Ficou de fora por pouco.
Decisão: não mexer no threshold com base num único caso (risco de
sobreajustar a um exemplo só) — fica documentado como confirmação real
do aviso já existente, para revisitar quando houver mais casos reais
acumulados, não um ajuste reactivo agora.

---

## Discussão de arquitectura para escala (9 Ago 2026) — decisões, não só notas

Conversa mais longa com o utilizador sobre onde este projecto vai a
seguir: o SUPERDEV não é só para uso pessoal, é para se tornar produto
usado por empresas pequenas/médias/grandes, desenhado para aguentar
crescimento de 10 anos sem precisar de reescrita total (referência
directa de uma experiência real do utilizador numa empresa de
telecomunicações: sistema para 1M de utilizadores atingiu 2M a fazer
"remendos" e teve de ser reconstruído do zero por várias empresas
contratadas). Isto muda o critério de decisão: não é "o que
precisamos agora", é "que arquitectura aguenta desde o dia 1".

**Medição de escala real, antes de decidir se precisamos de base de
dados vectorial:** varrimento linear (o que o `memory.py` faz hoje,
um `_cosine()` por ficheiro, em Python) — 100 factos: 0.5ms; 10.000
factos: ~49ms; **100.000 factos: ~457ms**. Uma chamada normal ao
modelo demora 1-20+ segundos. Calcular o embedding da pergunta em si
(chamada à Ollama): ~70ms. Ou seja, mesmo a 100 mil factos, a
pesquisa continua a ser uma fracção pequena do tempo total — não é o
gargalo. Decisão inicial (antes de o utilizador corrigir o
enquadramento): não vale a pena base de dados vectorial "ainda".

**Correcção de enquadramento pedida pelo utilizador:** o critério não
deve ser "resolve um problema que temos agora", deve ser "resolve o
problema que vamos ter com múltiplos clientes, multi-tenant, a
escalar". Aceite — a análise de velocidade acima continua válida, mas
não é o critério de decisão certo sozinho; multi-tenant, isolamento
entre clientes e pesquisa indexada por categoria são requisitos de
produto, não optimizações prematuras.

**Decisão de arquitectura: PostgreSQL + `pgvector`**, não ficheiros
`.md` (para a versão "produto"/cliente — o `memory.py` actual continua
válido como motor pessoal/desenvolvimento). Porquê esta e não Qdrant/
Chroma/Milvus: já há Postgres a correr no ecossistema (DaazLeads,
DaazRecover, cada um isolado no seu projecto, mesma regra de sempre);
multi-tenant em Postgres é um padrão maduro há décadas (schemas /
`tenant_id` indexado / row-level security); o produto de auditoria
RGPD/EU AI Act do utilizador tem uma conversa de conformidade mais
fácil com "Postgres" do que com uma base vectorial de nicho. FAISS
(usado noutros projectos do utilizador) foi considerado e descartado
para este papel — é uma biblioteca rápida para a matemática pura de
vizinhos mais próximos, mas não dá multi-tenant, filtros SQL,
backups/replicação de fábrica; tudo isso teria de ser construído à
volta dele. `pgvector` dá o mesmo tipo de indexação (HNSW) dentro de
um motor que já resolve o resto.

**Ainda por fazer:** desenho do esquema (tabela de memórias com
`tenant_id`, `categoria`, `texto`, `embedding vector(768)`, índice
HNSW) e protótipo mínimo testado com dados reais — ainda não
começado, é o próximo passo.

### O teste decisivo: quem deve fazer a pesquisa — código ou o agente?

Pergunta central do utilizador: é o agente que decide pesquisar (via
ferramenta) ou o código que busca sempre, antes de sequer falar com o
modelo? Testado ao vivo, mesma pergunta real ("em que porta corre o
Ollama?", facto real gravado: 11435), dois caminhos:

- **Caminho A — código busca sempre** (`memory.retrieve()` corre
  incondicionalmente, é o que já fazemos): 1 chamada, 655 tokens,
  6.37s, resposta **11435 — correcta**.
- **Caminho B — ferramenta `pesquisar_memoria`, o modelo decide**:
  1 chamada, 384 tokens, 1.32s, resposta **11434 — errada**. O modelo
  nem chegou a pedir a ferramenta — respondeu com a porta por defeito
  genérica da Ollama (conhecimento de treino), sem saber que esta
  instalação em concreto foi configurada de forma diferente.

**O caminho B foi mais rápido e mais barato — e errou.** Discutido com
o utilizador se isto é "porque o modelo é pequeno/fraco" e se um
modelo melhor resolveria sozinho, deixando de ser preciso forçar a
busca no código. Conclusão a que chegámos: não é um problema de
inteligência, é um problema de acesso à informação — nenhum modelo,
por maior que seja, pode saber um facto específico desta instalação
sem lhe ser dado; e um modelo maior tende a soar mais convincente a
inventar, não menos, o que piora a detecção do erro, não melhora.
É exactamente a razão pela qual "grounding"/RAG obrigatório é usado
na indústria toda mesmo com os modelos mais caros e capazes que
existem — não é workaround de modelo fraco.

**Decisão de arquitectura (não vai mudar com modelos melhores):**
factos específicos do cliente/projecto — busca sempre obrigatória no
código, nunca ao critério do modelo. Raciocínio geral, código,
explicações — o agente continua completamente livre, sem restrição
nenhuma, e melhora sozinho com modelos melhores. Já tínhamos esta
separação por instinto (`memory.retrieve()` obrigatório vs. ferramentas
de ficheiro que o modelo escolhe) — ficou confirmada como a distinção
certa: obrigatório para o que é sempre relevante e não descobrível por
raciocínio; ao critério do agente só quando genuinamente não há como
saber de antemão o quê procurar.

### Português vs. inglês — onde poupa tokens a sério, testado

Pedido do utilizador: tudo o que não for a conversa com o utilizador/
cliente pode ir para inglês, se isso poupar tempo e tokens. Testado
antes de aplicar às cegas:

- **Comentários no código nunca custam nada** — confirmado a inspeccionar
  o `system` enviado ao modelo, não contém nenhum `#` de comentário.
  Não é alavanca nenhuma, é só documentação para humanos.
- **Mesmo conteúdo, PT vs. EN, medido 2x com textos diferentes:** PT
  usa **+13% a +15% mais tokens** que EN para dizer a mesma coisa,
  neste tokenizer.
- **Testado traduzir factos de memória para inglês — PARTIU a
  pesquisa.** Facto gravado em inglês, pergunta em português: pontuação
  de palavras-chave caiu para **0.000** (nenhuma palavra em comum) e a
  semântica também caiu (0.538, mais baixa que o normal). Score final
  0.377, bem abaixo do `MEMORY_MIN_SCORE=0.6` — memória perdida por
  completo. **Decisão: factos de memória ficam em português**, o custo
  de +15% aqui é o preço real de operar em português, não desperdício
  a cortar.
- **Descrições de ferramentas (`tools.py` `TOOL_DEFS`) traduzidas para
  inglês** — nunca comparadas por palavras-chave, só lidas pelo
  modelo. Medido: 16 tokens poupados por pedido (~3%), repete em cada
  volta do ciclo de ferramentas. Aplicado.
- **`CORE_IDENTITY` (`config.py`) traduzido para inglês**, com
  instrução explícita "responde sempre em português europeu". Testado:
  continua a responder em português mesmo quando a pergunta do
  utilizador foi escrita em inglês — instrução a "pegar" bem.
  Poupança medida: só 1 token (texto curto, a percentagem de 13-15%
  em números absolutos pequenos não dá muito) — aplicado por ser
  grátis e correcto, não por ser a maior poupança.
- **Prompt de destilação (`agent._destilar`) traduzido para inglês**,
  mas a EXIGIR explicitamente que os factos extraídos saiam em
  português (a mesma razão do ponto acima sobre memória). Retestado
  com o mesmo par de frases (preferência real + trivialidade da
  capital): continuou a extrair só o facto certo, em português.

**Regra geral que ficou destas experiências:** o idioma da instrução
é livre (grátis trocar para inglês); o idioma do que fica guardado ou
é comparado por palavras-chave tem de continuar em português, porque
é isso que vai ser perguntado no futuro.

---

## Protótipo `pgvector` construído e testado (9 Ago 2026)

Infra-estrutura nova, isolada, mesma regra de sempre (rede/volume/.env
próprios, porta só em `127.0.0.1`): `db/docker-compose.yml` (imagem
`pgvector/pgvector:pg16`), container `superdev-postgres`, porta
**5443** (5440 e 5442 já reservadas a outros projectos). Esquema em
`db/init/001_schema.sql`: tabela `memorias` com `tenant_id`,
`categoria`, `texto`, `embedding vector(768)`, coluna gerada
`texto_tsv` (full-text search nativo em português), índice **HNSW**
sobre o embedding, índices normais sobre `tenant_id` e
`(tenant_id, categoria)`, índice GIN sobre `texto_tsv`. Módulo Python
novo, `pgmemory.py` — mesma interface do `memory.py` (`retrieve()`
devolve `(score, id, texto)`), reutiliza `memory._embed()` (a régua
não muda, só onde os números ficam guardados).

**Sem o pacote `pgvector-python`** — o resto do projecto corre sem
venv, com pacotes já existentes no sistema (`psycopg` já estava
instalado); vectores formatados à mão como texto `'[v1,v2,...]'` com
`::vector` no SQL, evita mais uma dependência nova.

**BUG DE CALIBRAÇÃO encontrado e corrigido:** o `ts_rank` nativo do
Postgres não está na escala 0-1 da sobreposição de palavras calculada
à mão no `memory.py` antigo — valores típicos ficam entre 0.0 e 0.22.
Reaproveitar `MEMORY_MIN_SCORE=0.6` às cegas fazia o `retrieve()`
devolver **sempre vazio**, mesmo quando o facto certo estava
correctamente em 1º lugar (confirmado: pergunta sobre a GPU, facto
certo rankeado primeiro com score 0.468, mas 0.6 exigido — nada
passava). Corrigido com um `PG_MEMORY_MIN_SCORE` próprio (não reusa o
`MEMORY_MIN_SCORE` do motor antigo), calibrado com dados reais: 4
perguntas claramente irrelevantes pontuaram 0.40-0.43; 5 perguntas
com facto real relevante pontuaram 0.47-0.60. Threshold escolhido:
**0.45**, na margem entre os dois grupos. Retestado com os 9 casos
(5 relevantes + 4 irrelevantes): **9/9 certos** — nem falso positivo
nem falso negativo.

**Isolamento multi-tenant testado com um caso deliberadamente
sensível:** gravado um facto fictício ("CEO da Empresa XPTO ganha
8000€/mês") sob `tenant_id='cliente_xpto'`. Pesquisado esse mesmo
facto sob `tenant_id='default'` e sob um terceiro tenant qualquer —
**nunca apareceu fora do seu próprio tenant**, confirmado a olhar
directamente para os resultados devolvidos, não só a confiar no
`WHERE`. O que apareceu sob `default` foram dois factos *do próprio*
tenant, sem relação com "CEO", só por coincidência acima do threshold
(0.468 e 0.452 — mesmo em cima da margem) — não é fuga de dados, é o
mesmo aviso de precisão já conhecido, a confirmar-se também aqui.

**Teste de escala real — a prova do "vai direto lá, não leias tudo":**
inseridos 50.000 factos sintéticos (vectores aleatórios, 5 categorias)
via `COPY` (inserção em massa demorou ~250s, dominado pela construção
do índice HNSW à medida que os dados entram — custo pago uma vez, na
escrita, não na leitura). Com o modelo de embedding "aquecido"
(primeira chamada ~50ms fria, chamadas seguintes ~16ms — o mesmo
custo de arranque existe também no `memory.py` antigo, não é
específico disto):

| Pesquisa | Linhas na tabela | Tempo |
|---|---|---|
| `tenant=default` (5 factos reais, entre 50 mil) | 50.005 | ~9ms |
| `stress_test` + categoria='tecnologia' (10 mil) | 50.000 | ~15ms |
| `stress_test` sem categoria, só HNSW (50 mil) | 50.000 | ~13ms |

Para comparação, o varrimento linear em Python medido antes (sem
índice nenhum) foi ~450ms a 100 mil linhas. Confirmado: o índice HNSW
não varre a tabela, o tempo não cresce por aí a fora com o número de
linhas — é a diferença real entre "ele sabe onde estão as cebolas" e
"lê tudo à procura delas".

**Dados de teste (stress_test, cliente_xpto) removidos depois dos
testes** — só ficam os 5 factos reais migrados do `memory.py`.

**Categorização automática — decisão tomada (9 Ago 2026): NÃO fazer
por agora.** Discutido: a categoria ajuda organização/precisão, mas o
próprio teste de escala mostrou que a 50 mil linhas o HNSW sozinho
(13.3ms) foi tão rápido como filtrar por categoria antes (15.6ms) —
não é questão de velocidade a esta escala. Decidir uma lista fixa de
categorias sem dados reais de vários clientes seria apostar às cegas;
deixar o modelo inventar categorias livremente arrisca o mesmo
problema de inconsistência já visto nesta sessão (nomes diferentes
para a mesma coisa). Coluna `categoria` fica na tabela, por preencher,
para decidir com casos reais mais tarde.

**`pgmemory.py` ligado ao `agent.py` a sério (9 Ago 2026) — já não é
só um protótipo isolado.** Mudanças: `DB_DSN` centralizado em
`config.py` (deixou de estar hardcoded em `pgmemory.py`);
`build_system_prompt()` e a destilação (`_destilar`) passaram de
`memory.retrieve()`/gravação em ficheiro para `pgmemory.retrieve()`/
`pgmemory.store()`; `nova_sessao()` ganhou um `tenant_id` (por omissão
`config.TENANT_PADRAO="default"`), passado a partir daí a tudo o que
lê ou grava memória nessa conversa. `memory.py`/`memory/*.md` deixam
de ser usados ao vivo pelo agente — ficam como registo histórico (os
5 factos já foram migrados para o Postgres antes).

Testado ponta-a-ponta depois da troca: pesquisa real via Postgres
através do `agent.responder()` (não só chamando `pgmemory`
directamente) respondeu certo sobre a GPU; destilação automática
gravou um facto novo ("Projecto Fénix") sob um tenant de teste, e uma
sessão de outro tenant a perguntar a mesma coisa **não soube
responder** — isolamento confirmado através do fluxo real do agente,
não só da base de dados isolada; memória de curto prazo e de longo
prazo testadas a funcionar juntas na mesma conversa ("que bug
aconteceu no DaazNexus?" seguido de "e foi corrigido?" — a segunda
pergunta só faz sentido com a janela curta a funcionar). Dados de
teste limpos, ficam só os 5 factos reais, todos sob `tenant_id=
'default'`.

**Por fazer:** credenciais em `db/.env`/`config.DB_DSN` são só de
desenvolvimento local, por rever antes de qualquer deployment a
sério.

---

## Pool de ligações — fechado o gap de velocidade (9 Ago 2026)

Comparação directa pedida pelo utilizador: à escala de hoje (5
factos), o `memory.py` antigo (ficheiros) era mais rápido que o
`pgmemory.py` novo (~19ms vs. ~29ms) — confirmado ao vivo, não
escondido. Causa isolada: abrir uma ligação nova à Postgres a cada
pesquisa custava ~7.8ms sozinho (medido à parte) — o ficheiro antigo
não paga isto, é só ler um dicionário já em memória.

**Corrigido com `psycopg_pool.ConnectionPool`** (já instalado no
sistema, sem dependência nova): uma pool aberta uma vez
(`min_size=1, max_size=5`), reutilizada em todas as chamadas de
`store()`/`retrieve()`, em vez de `psycopg.connect()` a abrir e fechar
por pedido. Reteste depois da correcção: **15.8ms (novo) vs. 16.3ms
(antigo)** — praticamente empatados à escala pequena, mantendo a
vantagem de dezenas de vezes a escalas maiores (13-16ms a 50 mil
factos, já medido antes). Confirmado também ponta-a-ponta através do
`agent.responder()` real, sem regressões.

## Comparação com os outros agentes do utilizador (DAAZLABS Audit, Hermes PT)

Pedido do utilizador: comparar com o RAG de dois agentes já existentes
(FAISS + chunks). Medido ao vivo, não por documentação:

- **DAAZLABS Audit** (FAISS `IndexFlatL2`, 1.304 chunks, modelo e
  índice em cache em memória, `sentence-transformers` local): ~19ms
  por pesquisa, depois de ~4.1s de carregamento inicial (uma vez só).
- **Hermes PT** (`rag_laboral_pt`, FAISS `IndexFlatL2`, **65.627**
  vectores): **~287ms** por pesquisa — muito mais lento, mas não pela
  tecnologia. Decomposto: ler o índice do disco 75.6ms, ler
  `documents.pkl`/`metadatas.pkl` do disco 187.7ms, chamar o serviço
  de embeddings partilhado 28.4ms, **a pesquisa vectorial em si só
  6.5ms**. O código relê tudo do disco em cada chamada, nunca
  guarda em memória entre pedidos — mesma classe de problema do
  connection-per-request que corrigimos aqui, só que maior impacto
  (~270ms perdidos em vez de ~8ms).
- **Conclusão que ficou clara desta comparação:** a escolha da
  tecnologia (FAISS vs. Postgres/pgvector vs. ficheiros) importa menos
  para a velocidade real do que a qualidade da implementação (cache,
  evitar E/S repetida). FAISS exacto, bem implementado, é rapidíssimo
  mesmo sem índice aproximado (6.5ms a 65 mil vectores). O `pgvector`
  ganha à mesma escala (13-16ms) por já vir com indexação HNSW e não
  precisar de recarregar tudo para memória.

## Discussão: aplicar isto ao Hermes PT? (9 Ago 2026)

O Hermes PT tem um problema real de performance (a leitura do disco
em cada pedido, acima) — correcção recomendada, independente de
qualquer decisão maior, mesmo padrão do pool de ligações aqui.

Sobre migrar o Hermes para `pgvector`: esclarecido com o utilizador
que o Hermes vai ser um serviço pago, no site, onde clientes enviam
documentos e dados privados de casos jurídicos (área inicial: direito
civil e imobiliário), com validação humana da empresa de advocacia
antes de qualquer resposta sair. **Isto é exactamente o cenário
multi-tenant que este esquema resolve** — o Hermes hoje não tem
nenhum isolamento por cliente (um índice FAISS partilhado por tudo).
Decisão: não construir agora dentro desta sessão (é trabalho com peso
próprio — pipeline de ingestão de documentos, interface de chat no
site, fluxo de validação humana, segurança à altura de dados pessoais/
sigilo profissional) — mas confirma que a arquitectura construída hoje
para o SUPERDEV generaliza como planeado desde o início do projecto.
Fica registado como próximo grande projecto, com sessão de desenho
própria quando for a vez.

---

## Segurança: password da BD quase commitada para repositório público (9 Ago 2026)

Ao rever as credenciais da BD (pedido do utilizador, última tarefa
pendente da lista), descoberto que o `SUPERDEV` é um repositório git
com remote `https://github.com/daazlabs/SUPERDEV.git`, **público**
(confirmado com `gh repo view`). `config.py` já tinha sido commitado
2 vezes antes de hoje; a versão de hoje, com a password da BD escrita
directamente numa string (`DB_DSN = "...password=..."`), ainda **não**
tinha sido commitada nem enviada — apanhada a tempo, confirmado com
`git log`/`git diff` antes de qualquer `git add`.

**Também descoberto, já público nos 2 commits enviados anteriormente:**
`memory/_index.json` (cache de embeddings — inclui o texto dos 5
factos internos: GPU/VRAM, bugs, preferência do utilizador, dados do
DaazLeads) e `logs/chamadas.jsonl` (log de pedidos). Inspeccionado o
conteúdo antes de reagir: o log só grava métricas (tamanhos, tokens,
tempos, scores) — **nunca o texto real de perguntas ou respostas**;
o `_index.json` não tem passwords nem dados pessoais, só os factos já
conhecidos. Não é grave, mas não devia estar num repo público —
corrigido para a frente (ver abaixo); o histórico já enviado não foi
reescrito (decisão do utilizador, não decidida por mim).

**Corrigido:**
- `config.py` deixou de ter a password escrita — carrega agora
  `db/.env` via `python-dotenv` (já disponível no sistema, sem
  dependência nova), falha de forma clara (`KeyError`) se faltar.
- `.gitignore` novo: `db/.env`, `__pycache__/`, `*.pyc`,
  `memory/_index.json`, `logs/*.jsonl`.
- `git rm --cached` nos ficheiros que já estavam a ser seguidos por
  engano (`__pycache__/*.pyc`, `memory/_index.json`,
  `logs/chamadas.jsonl`) — continuam no disco, só deixam de ir para o
  próximo commit.
- Retestado ponta-a-ponta depois da mudança: `config.DB_DSN` continua
  a montar-se correctamente, `agent.responder()` continua a falar com
  a BD sem problemas.

**Por decidir com o utilizador:** se vale a pena reescrever o
histórico do git para tirar `memory/_index.json`/`logs/chamadas.jsonl`
dos 2 commits já públicos (mais invasivo, muda hashes de commit) — não
feito sem essa decisão explícita. Alterações de hoje ficaram só
preparadas (`git add`), não commitadas nem enviadas — por pedido
explícito de nunca commitar/enviar sem confirmação.

## Fecho da questão de segurança: commit feito, histórico não reescrito (9 Ago 2026)

Sessão caiu (saída acidental) antes deste ficheiro ser actualizado com
o desfecho, mas a decisão pendente acima foi tomada e executada:
commit `78c49a6` ("Segurança: password da BD deixa de estar no código;
pgvector ligado ao agente") enviado para `origin/main`. Confirmado
outra vez, já não só planeado: `git show 78c49a6 -- config.py` não tem
password nenhuma, usa `dotenv.load_dotenv`; `db/.env` não está a ser
seguido pelo git (`git ls-files | grep env` vazio).

Sobre reescrever o histórico para tirar `memory/_index.json` e
`logs/chamadas.jsonl` dos 2 commits antigos: reinspeccionado o
conteúdo ao pormenor antes de decidir — chaves do `_index.json` são só
5 nomes de ficheiro (`gpu_vram.md`, `daaznexus_bug_navegar.md`,
`preferencia_utilizador.md`, `daazleads_bd.md`,
`bug_assist_porta.md`) + vectores de embedding; `chamadas.jsonl` só
métricas (tamanhos, tempos, tokens), nunca texto de conversas.
**Decisão do utilizador: não reescrever o histórico.** Sem fuga real
de password/PII, o custo de um `force-push` num repositório público
(quebra qualquer clone/fork existente, operação difícil de desfazer)
não compensa o ganho. Questão de segurança fechada.

## `correr_ruff`: 1ª verificação por execução real, não auto-crítica (9 Ago 2026)

Depois da fundação (memória, ferramentas de leitura, velocidade), 1ª
tentativa directa de atacar o objectivo de fundo do projecto — o 9B
"parecer" um 35B na qualidade da resposta em si, não só na infra à
volta. Duas opções discutidas: **auto-crítica** (o modelo gera,
depois critica-se a ele mesmo com um 2º pedido) vs. **verificação por
execução real** (correr um linter/teste de verdade). Escolhida a
segunda, por pedido explícito do utilizador com uma restrição clara:
não pode custar mais velocidade nem tokens do que já custa hoje.
Auto-crítica dobra sempre o custo — é uma 2ª chamada completa ao
modelo, mesmo quando a 1ª resposta já estava certa. Verificação por
execução é **condicional**: correr o `ruff` é um subprocesso
(milissegundos, ~0 tokens), não uma chamada ao modelo, e só acontece
se o próprio modelo decidir chamar a ferramenta. Mesmo princípio já
validado com o grounding de memória neste projecto — deixar o modelo
"adivinhar" se está certo tem o mesmo ponto cego de o deixar inventar
factos; um erro real do compilador/linter é informação nova, não um
2º palpite do mesmo modelo.

**Desenho.** `ruff` instalado no sistema (`pip install
--break-system-packages ruff`, não havia `requirements.txt`/venv no
projecto — seguido o mesmo padrão do resto). 4ª ferramenta do agente
(`ler_ficheiro`, `listar_ficheiros`, `procurar_texto`, agora
`correr_ruff`) e a **1ª que executa algo**, não só lê. Como o SUPERDEV
ainda não tem ferramenta para escrever ficheiros, `correr_ruff`
recebe o código como texto (`codigo: str`), grava-o num ficheiro
temporário descartável (`tempfile.NamedTemporaryFile`) só para a
duração da verificação, apaga-o logo a seguir (`finally`, mesmo em
caso de timeout/erro) — nunca toca em ficheiros reais do projecto.
Timeout de 5s (`RUFF_TIMEOUT_S`) contra o subprocesso ficar preso.

**BUG REAL apanhado a testar ao vivo (não só lido):** a condição
inicial para "está tudo bem" era `returncode == 0 and not saida` — mas
o `ruff` imprime `"All checks passed!"` no stdout mesmo quando está
tudo bem, por isso `saida` nunca ficava vazia e a condição falhava
sempre, devolvendo o texto cru do ruff em vez do `[OK]` uniforme.
Corrigido para confiar só no `returncode`.

**Testado ponta-a-ponta pelo `agent.responder()` real, não só a
função isolada:**
- Pedido a pedir verificação explícita ("verifica o código que
  escreveste antes de responder") → modelo chamou `correr_ruff`
  sozinho via `tool_calls`, recebeu o resultado (`[OK] ruff não
  encontrou problemas.`), deu resposta final. Confirmado no log:
  `pediu_ferramenta=True` seguido de `False` na volta seguinte.
- Pedido de código normal, sem pedir verificação nenhuma ("Escreve uma
  função Python que inverte uma string.") → só 1 chamada ao modelo,
  `pediu_ferramenta=False` — **não chamou a ferramenta por iniciativa
  própria**, confirma que não é eager e não aumenta o custo quando não
  faz sentido.

**Aviso, para não sobrevender o resultado:** só 2 casos testados, os
dois com código trivial. Não é prova de que o modelo nunca vai chamar
`correr_ruff` por iniciativa própria em código mais complexo/propenso
a erro, nem de que o padrão "só chama quando faz sentido" aguenta a
tarefas difíceis — é o comportamento observado até agora, por
confirmar com mais casos.

Commitado e enviado: `5bcf11b`, em `origin/main`.

## Terminal com rótulos + `server.py`: interface de chat sem alterar o agente (9 Ago 2026)

Duas peças pedidas pelo utilizador para conseguir testar o SUPERDEV à
vontade, para lá dos testes feitos até aqui.

**1. `agent.py` `main()` — rótulos + cor + separador entre trocas.**
O modo interactivo (`python3 agent.py`) antes só tinha `input("> ")`
seguido da resposta sem nada a indicar quem escreveu o quê — confuso
numa conversa mais longa. Adicionado `Tu:`/`SUPERDEV:` (cor ANSI só se
`sys.stdout.isatty()`, nunca em ficheiro/pipe) e uma linha divisória
(`─` × 60) entre trocas. Testado com uma conversa real de 2 perguntas
via stdin: os rótulos e a separação ficaram correctos. **Achado à
parte, não é bug da formatação**: as 2 perguntas eram diferentes
(confirmado no log — 16 e 27 caracteres), mas o modelo deu a resposta
*exactamente igual* às duas, ignorando o pedido explícito "sem código"
na 2ª. Fica registado como observação sobre a qualidade de resposta a
seguimentos subtis — não investigado a fundo, N=1.

**2. `server.py` — servidor novo, API compatível com a OpenAI, para
ligar interfaces de chat prontas (Open WebUI) ao SUPERDEV.** Motivado
por o utilizador achar o terminal difícil de usar para conversar a
sério. Decisão importante, confirmada explicitamente com o utilizador
antes de avançar: **ficheiro à parte, não altera `agent.py`/
`tools.py`/`config.py`/`pgmemory.py`** — só importa `agent` e chama
`agent.responder()`, exactamente como `agent.main()` já fazia.

Desenho:
- `GET /v1/models` e `POST /v1/chat/completions`, os 2 endpoints que o
  Open WebUI precisa para listar e falar com um modelo custom.
- **Sessão única e persistente** (`SESSAO = agent.nova_sessao()`, ao
  nível do módulo) em vez de seguir o histórico que o cliente reenvia
  a cada pedido (a API da OpenAI é "sem estado" por definição — o
  SUPERDEV já tem a sua própria gestão de memória, duas fontes de
  verdade a competir seria pior). Só a última mensagem do utilizador é
  usada como pedido. Consequência assumida: uma "New Chat" no Open
  WebUI reinicia o que aparece no ecrã, mas a memória de longo prazo
  do SUPERDEV (pgvector) continua a acumular por baixo — é uma
  ferramenta pessoal de um utilizador só, não multi-utilizador, não
  vale a pena mais complexidade que isto agora.
- `usage` (tokens) no formato de resposta calculado a partir do
  próprio `logs/chamadas.jsonl` — regista o tamanho do ficheiro antes
  de chamar `agent.responder()`, lê só o que foi escrito depois, soma
  `prompt_eval_count`/`eval_count` de todas as linhas novas (cobre
  também pedidos com voltas de ferramentas, que geram mais que uma
  linha de log para uma só resposta ao utilizador).
- Suporta `stream: true/false`, mas não é streaming real: o
  `agent.py` já chama a Ollama com `stream=False` internamente
  (decisão anterior, testada). Quando o cliente pede `stream=true`,
  devolve a resposta inteira num único "pedaço" SSE, no formato
  correcto — evita bloquear/dar erro no Open WebUI, mas não aparece
  palavra a palavra.
- Porta `8850` (nova reserva, ver `portas_reservadas_sistema` na
  memória do utilizador) — confirmada livre com `ss -tlnp` antes de
  escolher.

**Testado ao vivo, ponta a ponta, antes de entregar:**
- `GET /v1/models` devolve o modelo `superdev`.
- `POST /v1/chat/completions` com `stream:false` — resposta completa,
  formato OpenAI correcto, `usage` com números reais (794 entrada +
  216 saída, coerente com o que o `ver_logs.py` também mostrou).
- `stream:true` — confirmado o formato SSE certo (`data: {...}` por
  pedaço, termina em `data: [DONE]`).
- `docker exec open-webui curl http://host.docker.internal:8850/v1/models`
  — confirma que o container do Open WebUI alcança mesmo o servidor
  (não só localhost do host).
- `python3 ver_logs.py 3` depois dos testes acima — confirmou que os 3
  pedidos feitos através do `server.py` apareceram no log, sem
  qualquer alteração ao `ver_logs.py` nem ao `agent.py`: reaproveita a
  mesma escrita de log que já existia, por usar a mesma
  `agent.responder()` por baixo.

**Por decidir/testar a seguir:** login real no Open WebUI a falar com
o modelo "superdev" (só testado por `curl`/`docker exec` até agora,
não pela interface a sério); se ficar bem, considerar systemd
`--user` para o `server.py` sobreviver a reinícios, como o resto do
ecossistema — não feito ainda, prematuro antes de validação com uso
real.

## Bug real de uso: ciclo preso a adivinhar caminhos + explicação confabulada (9 Ago 2026)

Incidente real do utilizador, a conversar com o SUPERDEV no terminal:
pediu "lê o código do sistema vectorial... é só leres!" (sem dar
caminho) e recebeu `[ERRO] Excedi o limite de voltas de ferramentas
(5) sem chegar a uma resposta final.` Ao perguntar "que erro foi
esse?", o agente respondeu com uma explicação a soar plausível mas
inventada ("gastei as minhas tentativas a tentar um por um").

**Causa raiz nº1, confirmada ao vivo reproduzindo o pedido exacto**
(`ver_logs.py` já mostrava nome+argumentos de cada ferramenta pedida,
ver secção anterior): o modelo tentou, nesta ordem, `ler_ficheiro(/historico.md)`,
`listar_ficheiros(/)`, `listar_ficheiros(/opt)`,
`listar_ficheiros(/opt/DaazNexus)`, `listar_ficheiros(/home)` —
**adivinhou caminhos absolutos pelo disco todo**, nunca chegou perto.
Porquê: `CORE_IDENTITY` nunca dizia ao modelo onde vivia o próprio
projecto; as ferramentas exigem caminho absoluto (`tools.py`
`TOOL_DEFS`); um pedido vago sem essa informação não tinha como ter
sucesso, para nenhum modelo deste tamanho ou maior — não era o modelo
a "ser mau", era uma peça de contexto a faltar.

**Causa raiz nº2, confirmada por leitura do código, não suposição**:
`responder()` só guarda o par pergunta/resposta final em
`sessao["historico"]` — "o vaivém interno das ferramentas é
descartado" (decisão de desenho antiga, documentada acima). Quando o
pedido falhava com o erro genérico, a próxima pergunta do utilizador
("que erro foi esse?") chegava ao modelo **sem nenhuma informação
real** sobre o que se tinha passado — só a frase do erro. A resposta
"explicativa" que deu foi inventada a partir de conhecimento geral
sobre o que esse tipo de erro costuma significar, não de memória real
do que aconteceu (a mesma classe de problema já discutida com
auto-crítica: o modelo preenche um vazio com uma história plausível em
vez de admitir que não sabe).

**Corrigido, testado ao vivo em ambas as partes, não só lido:**
- `config.py` `CORE_IDENTITY` ganhou uma frase com `BASE_DIR` real
  (`/mnt/sovereign/superdev`), instruindo o modelo a usá-lo como base
  quando um pedido de ficheiro/pasta não vier com caminho completo.
  Reteste com a pergunta exacta do utilizador: leu `HISTORICO.md` à
  primeira tentativa, sem adivinhar nada.
- `agent.py` `responder()`: quando o limite de voltas é excedido, a
  mensagem de erro passou a incluir a lista real de tentativas
  (`nome(args)` de cada chamada de ferramenta feita nessa volta) — como
  essa mensagem é o que fica gravado em `historico`, uma pergunta
  seguinte tipo "que erro foi esse?" passa a ter uma resposta com chão
  verdadeiro, não inventado. Testado de forma determinística (não
  dependente do modelo cooperar): `ollama_chat` substituído
  temporariamente por uma função de teste que força sempre pedido de
  ferramenta, confirmado que a mensagem final lista as 5 tentativas
  simuladas na ordem certa.

**Ainda por rever, não feito agora**: se um pedido genuinamente precisar
de mais de 5 voltas de ferramentas (não um ciclo preso, uma tarefa real
maior), `MAX_VOLTAS_FERRAMENTAS=5` corta-o na mesma — não distinguido
dos dois casos. Fica para quando houver um caso real desse tipo, não
antes.

## `ler_varios_ficheiros`: o caso real previsto acima aconteceu (9 Ago 2026)

Consequência directa da secção anterior — utilizador pediu ao
SUPERDEV, pelo Open WebUI, para se auto-analisar lendo o
`HISTORICO.md` + todo o código (`agent.py`, `config.py`, `memory.py`,
`pgmemory.py`, `server.py`, `tools.py`, `ver_conversa.py`,
`ver_logs.py`) — 9 ficheiros. Excedeu `MAX_VOLTAS_FERRAMENTAS` a meio
(leu 7 de 9), mesmo já com a correcção do caminho do dia (achou o
projecto certo à primeira, só tropeçou na maiúscula
`historico.md`/`HISTORICO.md`, e corrigiu-se sozinho).

**Achado à parte, importante**: a 1ª ideia (subir
`MAX_VOLTAS_FERRAMENTAS` de 5 para 12+) foi **rejeitada pelo
utilizador, com razão** — subir o limite não reduz tokens nenhuns, só
adia a falha: cada volta reenvia a conversa TODA até ali (Ollama não
tem memória entre chamadas), por isso os tokens de entrada cresciam a
cada ficheiro (950 → 1158 → 3109 → 3233 → 3387 → 5738 → 14125,
confirmado no log). Subir o número só deixaria a mesma escalada
continuar mais tempo, não a cortaria.

**Descoberta lateral, no mesmo incidente**: o Open WebUI, por
omissão, chama o modelo configurado (`superdev`) 3 vezes extra a
seguir a cada resposta — para gerar título da conversa, sugestões de
seguimento, e tags — cada uma dessas chamadas passa pelo agente
completo (RAG + identidade + ferramentas), gastando ~13 mil tokens
"escondidos" só em tarefas de interface, sem valor para o utilizador.
**Corrigido, mas fora deste repositório** — são definições do próprio
Open WebUI (Admin Panel → Settings → Interface → Tasks): "Title
Generation", "Follow Up Generation" e "Tags Generation" desligados.
Nada a mudar no SUPERDEV para isto.

**A correcção real (que reduz tokens, não só adia a falha):** nova
ferramenta `ler_varios_ficheiros(caminhos: list)` — lê vários
ficheiros numa só volta, reaproveitando `ler_ficheiro` por dentro
(mesmas mensagens de erro, mesmo corte por ficheiro), com dois tectos
próprios (`LIMITE_FICHEIROS_LOTE=15`, `LIMITE_CARACTERES_LOTE=30000`)
para nunca rebentar sozinha com o lote todo. Descrição do
`ler_ficheiro` em `TOOL_DEFS` ganhou uma frase a apontar para a nova
ferramenta quando for preciso mais que 1 ficheiro — é o que fez o
modelo preferi-la sem precisar de mais nada.

De caminho, aproveitado para corrigir 2 avisos do `ruff` no
`correr_ruff` (código de hoje, nunca tinha corrido `ruff check
tools.py` depois de o escrever): `tempfile.NamedTemporaryFile` passou
a usar `with` em vez de abrir/fechar à mão, e `subprocess.run` ganhou
`check=False` explícito. Os avisos pré-existentes de 8 Ago
(`fnmatch` por usar, `except Exception` genérico em 3 sítios) ficaram
por resolver, fora do âmbito de hoje.

**Testado ao vivo, ponta-a-ponta, com o pedido exacto que tinha
falhado antes:** reiniciado o `server.py` (código só carrega uma vez
no arranque), repetido o pedido pelo `curl` (simula o Open WebUI).
Resultado: **3 voltas em vez de 7**, o modelo usou
`ler_varios_ficheiros` sozinho com os 8 ficheiros de código numa só
chamada (confirmado no log, nome+argumentos completos), respondeu com
sucesso — e a resposta já listava primeiro o que estava implementado
antes de sugerir melhorias (o que faltava na tentativa anterior).

## `server.py` não sobrevivia a reinícios do PC (10 Ago 2026)

Incidente real: `localhost:3000` (Open WebUI) deixou de mostrar o
modelo `superdev`, que ontem tinha ficado a funcionar. Causa raiz,
confirmada por `ss -tlnp` + `ps aux`: o PC reiniciou hoje às 15:28 (os
outros serviços do ecossistema sovereign, todos `systemd --user`,
arrancaram sozinhos nessa hora); o `server.py` tinha sido corrido à
mão num terminal ontem (ver secção anterior), não era serviço — o
reinício matou o processo e nada o voltou a ligar. A ligação continuava
configurada no Open WebUI (`http://host.docker.internal:8850/v1`),
só inalcançável.

**Segunda causa, só apareceu depois de religar o `server.py` à mão e
confirmar por `curl`/`docker exec` que respondia:** o modelo continuava
a não aparecer na lista do Open WebUI. Admin → Settings → Connections
tem um toggle **"Cache Base Model List"** ligado — só vai buscar a
lista de modelos ao arrancar o container ou quando as definições da
ligação são gravadas, nunca sozinho entretanto. Como a ligação esteve
morta o dia todo, a cache ficou presa numa foto sem o `superdev`.
Corrigido clicando "Save" nessa página (força o refetch) — nada a
mudar no lado do SUPERDEV. Fica registado para o futuro: se o modelo
desaparecer outra vez sem razão óbvia, primeiro confirmar se o
`server.py` está mesmo a responder (`curl localhost:8850/v1/models`)
antes de mexer em connections; se estiver a responder e mesmo assim não
aparecer, é este cache.

**Correcção definitiva, testada não só configurada:** criado
`systemd/superdev-server.service` (`systemd --user`, mesmo padrão do
resto do ecossistema sovereign — `Restart=always`, `WorkingDirectory`
no repo, log para o `journal`). `ExecStartPre` mata o que estiver preso
à porta 8850 antes de arrancar (evita falha por porta ocupada num
restart). Corre com `/usr/bin/python3` (não o `venv` do
`agent-sovereign` — esse não tem `psycopg2`/`fastapi`/`uvicorn`
instalados, confirmado a testar). Instalado com
`systemctl --user enable --now`; `loginctl show-user` já tinha
`Linger=yes`, por isso arranca mesmo sem sessão gráfica aberta.
**Testado com um `systemctl --user restart` a sério** (não só o
arranque inicial) — voltou a responder em segundos, confirmado outra
vez ponta a ponta com `curl` directo e `docker exec open-webui curl
http://host.docker.internal:8850/v1/models`.

Nota para manutenção futura: o serviço só carrega `config.py`/
`agent.py`/etc. uma vez, ao arrancar (mesma decisão de desenho já
documentada acima para o modo terminal) — qualquer alteração a esses
ficheiros ou ao `db/.env` só entra em vigor depois de
`systemctl --user restart superdev-server`.
