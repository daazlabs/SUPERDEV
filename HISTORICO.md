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
