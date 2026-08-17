"""
Rede de verificação mecânica anti-confabulação do SUPERLLMLOCAL — Nível 1 →
1.5 → URLs → fontes nomeadas → ficheiros citados → existência
contraditada (10-16 Ago 2026, ver HISTORICO.md para o incidente real
que motivou cada peça).

Extraído de agent.py (16 Ago 2026) — refactor puro, sem mudar
comportamento nenhum. Estava tudo ali porque cresceu incidente a
incidente dentro do mesmo ficheiro; passa a módulo próprio porque
estas funções são, por desenho desde o início (ver os comentários
junto a cada uma), completamente independentes do modelo por baixo —
só olham para texto simples (a resposta final e o que as ferramentas
devolveram nesta troca), nunca para nada específico do Qwen/Ollama.
Isso é o que torna este módulo reaproveitável por cópia noutro agente
que fale com um modelo diferente por um protocolo diferente (ver
SUPERLLMAPI) sem precisar de reescrever nada aqui.

Convenção: as 6 funções `verificar_*` são a API pública deste módulo
(chamadas de fora, ex. agent.responder()) — sem underscore inicial,
ao contrário de quando viviam dentro de agent.py como detalhe de
implementação. Os helpers e as constantes de regex continuam privados
ao módulo (underscore mantido).

Todas têm a mesma forma: `(resposta: str, mensagens: list) -> str` —
devolvem a resposta tal e qual se nada houver a assinalar, ou a
resposta com um aviso "[SUPERLLMLOCAL — ...]" acrescentado no fim. Nunca
corrigem nem bloqueiam, só tornam a suspeita visível — mesmo princípio
em todas, repetido em cada docstring.

Custo: ~0 em todas (regex + comparação de string, nenhuma chamada
extra ao modelo) — só correm depois de já termos a resposta final.
"""
import json
import re
import urllib.request

import config

# Nível 1 do plano anti-confabulação (10 Ago 2026, ver HISTORICO.md) —
# verificação MECÂNICA (regex + comparação de texto), não outro pedido
# ao modelo. Desenhada de propósito para ser genérica, não afinada
# para o qwen3.5:9b: só olha para texto simples (a resposta final e o
# que as ferramentas devolveram), nunca para nada específico deste
# modelo — a ideia, a pedido do utilizador, é que isto continue a
# valer quando o modelo por baixo mudar (14B, 35B, outro qualquer).
# Custo: ~0 (nenhuma chamada extra ao modelo, só string matching),
# nunca atrasa nem gasta tokens a mais — só corre depois de já termos
# a resposta final.
#
# Âmbito deliberadamente estreito: nenhum destes apanha invenções em
# prosa livre (percentagens fabricadas, afirmações erradas sobre
# comportamento) — só valores de configuração citados, em 3 formatos
# de texto diferentes. Começou só com o 1º (10 Ago, incidente
# MEMORY_TOP_K); ampliado no mesmo dia depois de um 2º incidente
# escapar: `config.OPTIONS` tem chaves em MINÚSCULAS (`temperature`,
# `num_ctx`...), não maiúsculas, e uma resposta citou-as numa tabela
# markdown (`| num_ctx | 16384 |`) — nem o nome nem o formato batiam
# com o padrão original, a verificação nunca chegou a correr. Testado
# ao vivo que isto reproduzia (ver HISTORICO.md).
_PADRAO_CONSTANTE = re.compile(
    r"\b([A-Z][A-Z0-9_]{2,})\s*=\s*"
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|-?\d+(?:\.\d+)?|True|False|None)"
)
# Chave de dicionário Python, como config.OPTIONS escreve as suas
# ("temperature": 0.2,) — cobre tanto o ficheiro real (o que
# ler_ficheiro devolve tal e qual) como uma resposta que cite a mesma
# sintaxe num bloco de código.
_PADRAO_CHAVE_DICT = re.compile(
    r"[\"']([a-z][a-z0-9_]{2,})[\"']\s*:\s*"
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|-?\d+(?:\.\d+)?|True|False|None)"
)
# Linha de tabela markdown, ex.: "| `num_ctx` | 16384 | ..." — formato
# muito comum nas respostas do SUPERLLMLOCAL quando comparam "actual vs.
# sugerido", confirmado nos logs de hoje.
_PADRAO_LINHA_TABELA = re.compile(
    r"\|\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*\|\s*"
    r"(-?\d+(?:\.\d+)?|True|False|None)\s*\|"
)
_PADRAO_NOME_SOLTO = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

# Frases de incerteza — segundo padrão (10 Ago 2026), motivado por um
# caso real que o padrão acima (NOME = valor) NÃO apanhou: o modelo
# nunca escreveu "MEMORY_TOP_K = 5" (uma afirmação directa, fácil de
# comparar) — escreveu "k e MEMORY_TOP_K não estão explícitos
# (provavelmente 5 ou 10)", quando MEMORY_TOP_K=3 estava mesmo ali no
# texto da ferramenta lida na mesma troca. Confirmado ao testar: o
# padrão _PADRAO_CONSTANTE sozinho não apanhava este caso, precisou
# deste segundo.
_FRASES_DE_INCERTEZA = (
    "não está explícit", "não estão explícit", "não está definid",
    "não estão definid", "provavelmente", "não tenho a certeza",
    "não sei ao certo", "não é claro", "não aparece explícit",
    "não aparece definid", "não aparece no código",
)


def _constantes_citadas(texto: str) -> dict[str, str]:
    """Extrai pares nome->valor de um texto, juntando os 3 formatos
    (constante Python, chave de dict, linha de tabela markdown — ver
    padrões acima). Nomes normalizados para minúsculas só para efeitos
    de comparação (config.OPTIONS usa minúsculas, o resto das
    constantes usa maiúsculas — um único caminho de comparação chega,
    não vale a pena complicar). Em caso de repetição do mesmo nome,
    fica o último visto — suficiente para este fim."""
    pares = {}
    for padrao in (_PADRAO_CONSTANTE, _PADRAO_CHAVE_DICT, _PADRAO_LINHA_TABELA):
        for nome, valor in padrao.findall(texto):
            pares[nome.lower()] = valor
    return pares


def _alegacoes_falsas_de_incerteza(resposta: str, reais: dict) -> list[str]:
    """Frase a frase, se a frase tiver uma expressão de dúvida
    (_FRASES_DE_INCERTEZA) E mencionar o nome de uma constante que na
    verdade apareceu com um valor concreto no texto das ferramentas
    desta troca, é quase certo que o modelo está a "adivinhar em voz
    alta" algo que já tinha lido — sinalizado, não corrigido sozinho."""
    encontradas = []
    for frase in re.split(r"(?<=[.!?])\s+", resposta):
        frase_min = frase.lower()
        if not any(gancho in frase_min for gancho in _FRASES_DE_INCERTEZA):
            continue
        for nome in _PADRAO_NOME_SOLTO.findall(frase):
            nome_norm = nome.lower()
            if nome_norm in reais:
                encontradas.append(f"{nome} (disseste que não sabias, mas li {nome}={reais[nome_norm]} nesta troca)")
    return encontradas


def verificar_grounding(resposta: str, mensagens: list) -> str:
    """Confere se as constantes que a resposta final cita — ou diz não
    saber — batem certo com o que as ferramentas desta troca realmente
    devolveram. Não corrige sozinha (podia estar a inventar a
    correcção também) — só torna a suspeita visível, para o utilizador
    decidir."""
    # CORRIGIDO 10 Ago 2026 — a condição de saída antecipada aqui era
    # demasiado permissiva: media se ALGUMA constante reconhecida foi
    # lida (reais vazio → desistia logo), não se houve leitura
    # nenhuma. Incidente real que isto escondia: um pedido só
    # pesquisou "LOG_FILE" (irrelevante), e a resposta afirmou 6
    # valores de config.OPTIONS com total confiança — como "reais"
    # ficava vazio (nada bateu com o padrão de então), a verificação
    # desistia sem tentar, em vez de assinalar tudo como não
    # confirmado (o que é a suspeita certa quando houve leitura mas
    # nada dela bate com o que foi citado).
    if not any(m.get("role") == "tool" for m in mensagens):
        return resposta  # não houve ferramentas nesta troca, nada a confirmar

    texto_ferramentas = "\n".join(
        m["content"] for m in mensagens if m.get("role") == "tool" and m.get("content")
    )
    reais = _constantes_citadas(texto_ferramentas)

    citadas = _constantes_citadas(resposta)
    contradicoes = []
    nao_confirmadas = []
    for nome, valor in citadas.items():
        if nome in reais:
            if reais[nome] != valor:
                contradicoes.append(f"{nome}={valor} (o que li diz {nome}={reais[nome]})")
        else:
            nao_confirmadas.append(f"{nome}={valor}")

    falsas_duvidas = _alegacoes_falsas_de_incerteza(resposta, reais)

    if not contradicoes and not nao_confirmadas and not falsas_duvidas:
        return resposta

    aviso = "\n\n---\n[SUPERLLMLOCAL — verificação automática de constantes citadas]"
    if contradicoes:
        aviso += "\n⚠️ Contradiz o que li nesta troca: " + "; ".join(contradicoes)
    if falsas_duvidas:
        aviso += "\n⚠️ Disseste \"não sei\" sobre algo que li nesta troca: " + "; ".join(falsas_duvidas)
    if nao_confirmadas:
        aviso += (
            "\n(Não confirmados nos ficheiros lidos nesta troca — podem "
            "estar certos noutro ficheiro não lido agora, ou inventados: "
            + "; ".join(nao_confirmadas) + ")"
        )
    return resposta + aviso


# Nível "1.5" do anti-confabulação (13 Ago 2026, ver HISTORICO.md) —
# incidente real motivador: um pedido de pesquisa (DAAZPRIME) recebeu
# uma resposta a citar "Google AI Overview"/"ChatGPT"/fóruns com ar de
# facto confirmado, com um URL incluído — e nunca, em nenhuma das 5
# voltas, chamou pesquisar_web. Fundamento ZERO, não uma distorção
# subtil do que foi pesquisado (isso continua por apanhar — seria o
# Nível 2, uma verificação semântica a sério, que dobra o custo por
# exigir uma 2ª chamada ao modelo, e por isso continua adiado; ver
# HISTORICO.md).
#
# Mais estreito de propósito, mesmo espírito do Nível 1 acima: não
# confirma SE o que foi dito bate certo com o que a ferramenta
# devolveu (isso é o Nível 2) — só confirma que a categoria de
# ferramenta que a resposta implica ter usado foi mesmo chamada
# nesta troca. Apanha "fingiu que pesquisou"; não apanha "pesquisou
# mas exagerou". Custo ~0 — reaproveita o mesmo mecanismo por
# palavras-chave do filtro de TOOL_DEFS (tools.PALAVRAS_CHAVE_
# FERRAMENTAS), só ao contrário: em vez de perguntar ao PEDIDO
# "precisas de ferramenta?", pergunta à RESPOSTA "falas de algo que só
# uma ferramenta confirma — e essa ferramenta foi mesmo chamada?"
#
# Categorias deliberadamente poucas e concretas — começa só com "web"
# (o caso real) e "ficheiro" (o mais óbvio a seguir), ampliar se
# aparecer um 3º padrão real, mesma disciplina do Nível 1 (começou só
# com 1 padrão, cresceu com incidentes a sério, não especulação).
_CATEGORIAS_FUNDAMENTO = {
    "web": {
        "palavras_chave": (
            "google ai overview", "google ai", "chatgpt", "gemini",
            "perplexity", "pesquisei na web", "pesquisa na web encontrou",
            "segundo a pesquisa", "resultados da pesquisa", "notícia recente",
            "notícias recentes", "fórum", "forum", "reddit",
            "de acordo com o site", "site oficial",
        ),
        # ler_pagina_web (17 Ago 2026, SUPERLEADS) — mesma categoria:
        # também é fundamento real para afirmações sobre o que "um site
        # diz", só que a partir do conteúdo da página, não do resumo da
        # pesquisa. Não existe no SUPERLLMLOCAL (tools.FUNCOES não a tem lá),
        # por isso esta entrada não muda nada para ele — só passa a
        # contar como fundamento válido para agentes que a tenham.
        "ferramentas": ("pesquisar_web", "ler_pagina_web"),
    },
    "ficheiro": {
        "palavras_chave": (
            "li o ficheiro", "o ficheiro contém", "de acordo com o código",
            "no código-fonte",
        ),
        "ferramentas": (
            "ler_ficheiro", "ler_varios_ficheiros", "procurar_texto", "listar_simbolos",
        ),
    },
}


def verificar_fundamento_categorias(resposta: str, mensagens: list) -> str:
    """Para cada categoria em _CATEGORIAS_FUNDAMENTO, se a resposta usa
    linguagem típica dessa categoria mas nenhuma das ferramentas
    correspondentes foi chamada nesta troca, sinaliza — sem corrigir
    nem bloquear, mesmo princípio do Nível 1: tornar a suspeita
    visível, não decidir por ninguém."""
    resposta_min = resposta.lower()
    ferramentas_chamadas = {
        tc["function"]["name"]
        for m in mensagens
        if m.get("role") == "assistant"
        for tc in (m.get("tool_calls") or [])
    }

    suspeitas = []
    for categoria, regras in _CATEGORIAS_FUNDAMENTO.items():
        tem_linguagem_da_categoria = any(p in resposta_min for p in regras["palavras_chave"])
        tem_ferramenta_correspondente = any(f in ferramentas_chamadas for f in regras["ferramentas"])
        if tem_linguagem_da_categoria and not tem_ferramenta_correspondente:
            suspeitas.append(f"{categoria} (esperava-se uma de: {', '.join(regras['ferramentas'])})")

    if not suspeitas:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — aviso de fundamento (Nível 1.5)]\n"
        "⚠️ Esta resposta usa linguagem típica de: " + "; ".join(suspeitas) +
        " — mas a ferramenta correspondente nunca foi chamada nesta "
        "troca. Pode estar inventado, não confirmado por nenhuma "
        "pesquisa/leitura real."
    )
    return resposta + aviso


# Verificação de URLs citados (13 Ago 2026, ver HISTORICO.md) —
# incidente real motivador: ao testar a regra preventiva acima, o
# modelo chamou pesquisar_web A SÉRIO (3 vezes) e MESMO ASSIM a
# resposta final incluiu URLs completamente inventados (um fórum, um
# banco, a CMVM) sem relação nenhuma com as 3 pesquisas reais feitas.
# O Nível 1.5 não apanha isto — só confirma "pesquisar_web foi
# chamado?" (sim), não confirma se CADA afirmação bate com o que essa
# pesquisa devolveu. É exactamente "pesquisou mas inventou por cima",
# o caso que o Nível 1.5 já avisava não cobrir.
#
# Continua deliberadamente mecânico e barato (regex + substring, sem
# chamar o modelo) — não é o Nível 2 completo (que exigiria perceber
# se o CONTEÚDO de cada afirmação bate com o resultado, não só o
# link). Mas um URL é um caso especial fácil: um link real citado
# como prova tem de ter vindo de algum lado (resultado de ferramenta,
# ou o próprio utilizador a dá-lo) — se o texto exacto do URL nunca
# apareceu em nenhum resultado de ferramenta nem em nada que o
# utilizador escreveu nesta troca, não há forma honesta de o modelo o
# ter "confirmado". Não conta o que o próprio modelo já disse antes
# nesta troca (role "assistant") como fonte válida — um URL inventado
# numa volta não se torna "confirmado" só por ser repetido depois.
_PADRAO_URL = re.compile(r'https?://[^\s<>"\')\]]+')


def _limpar_url(url: str) -> str:
    """Tira pontuação de fecho de frase/markdown colada ao URL (ex.:
    'https://exemplo.com/pagina.' ou '(https://exemplo.com)') — sem
    isto, um URL correcto no fim de uma frase nunca batia certo com o
    mesmo URL no texto da ferramenta, por causa do ponto final."""
    return url.rstrip('.,;:!?)"\']>')


def verificar_urls_citados(resposta: str, mensagens: list) -> str:
    """Cada URL que a resposta final cita como prova tem de aparecer,
    tal e qual, nalgum resultado de ferramenta ou em algo que o
    utilizador escreveu nesta troca — senão não há forma honesta de
    ter sido "confirmado". Não corrige nem apaga, só assinala, mesmo
    princípio dos níveis acima."""
    urls_citados = {_limpar_url(u) for u in _PADRAO_URL.findall(resposta)}
    if not urls_citados:
        return resposta

    texto_fontes = "\n".join(
        m.get("content") or "" for m in mensagens if m.get("role") in ("tool", "user", "system")
    )
    nao_confirmados = sorted(u for u in urls_citados if u not in texto_fontes)
    if not nao_confirmados:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — aviso de URLs não confirmados]\n"
        "⚠️ Estes links não aparecem em nenhum resultado de ferramenta "
        "nem em nada que escreveste nesta troca — podem estar "
        "inventados: " + "; ".join(nao_confirmados)
    )
    return resposta + aviso


# Verificação de fontes nomeadas citadas em prosa, sem URL (16 Ago
# 2026, ver HISTORICO.md) — extensão directa de
# _verificar_urls_citados para o caso adjacente: uma fonte citada por
# NOME ("segundo a CMVM...", "de acordo com o Fórum X...") sem link
# nenhum a acompanhar. O incidente real de 13 Ago (fórum/banco/CMVM
# inventados) já ficou coberto pelo caso COM URL — isto fecha a
# versão sem URL do mesmo padrão. Ainda por reproduzir ao vivo; ver a
# conversa com o utilizador (16 Ago) sobre a distinção entre invenção
# ESTRUTURADA (um nome/sigla concreto citado como prova — isto
# apanha) e invenção DIFUSA em prosa livre (cor narrativa sem nada
# concreto agarrado — nenhuma verificação mecânica alcança isso; fica
# para a auditoria por amostragem do Nível 2, não decidida ainda).
#
# Só actua dentro de frases com uma pista de citação explícita
# (_PISTAS_CITACAO) — sem isso, qualquer nome próprio em maiúsculas
# dispararia constantemente (nomes de pessoas, países, o próprio
# projecto), ruído sem sinal nenhum, mesmo problema que motivou o
# âmbito estreito do Nível 1.5. Dentro dessas frases, só conta nomes
# de 2+ palavras com maiúscula inicial (ligações de/da/do/dos/das/e
# permitidas no meio, ex. "Banco de Portugal") ou siglas de 2-6
# letras (ex. "CMVM", "INE", "BCE") — um nome de 1 palavra só é
# ambíguo demais para confirmar ou negar com segurança.
_PISTAS_CITACAO = (
    "segundo", "de acordo com", "conforme", "fonte:", "publicado por",
    "relatório da", "relatório do", "comunicado da", "comunicado do",
    "no site da", "no site do", "site oficial",
) + _CATEGORIAS_FUNDAMENTO["web"]["palavras_chave"]

_PADRAO_SIGLA = re.compile(r"\b[A-Z]{2,6}\b")
_PADRAO_NOME_PROPRIO = re.compile(
    r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+(?:de|da|do|dos|das|e)\s+[A-ZÀ-Ý][a-zà-ÿ]+"
    r"|\s+[A-ZÀ-Ý][a-zà-ÿ]+){1,3}\b"
)
# Palavras soltas das próprias pistas de citação (_PISTAS_CITACAO) —
# só as conectoras curtas, não as frases-chave do Nível 1.5 (essas são
# nomes de produto/site reais como "chatgpt"/"reddit", não ruído).
# Achado ao testar: "Segundo Portugal, ..." capturava "Segundo
# Portugal" como um nome próprio de 2 palavras só porque o conector
# em início de frase vem com maiúscula — sem isto, o próprio gatilho
# contaminava o que estava a tentar extrair.
_PALAVRAS_PISTA_CONECTORAS = {
    "segundo", "de", "acordo", "com", "conforme", "fonte", "publicado",
    "por", "relatório", "da", "do", "comunicado", "no", "site", "oficial",
}


def _fontes_citadas(frase: str) -> set[str]:
    """Siglas + nomes próprios de 2+ palavras encontrados numa frase,
    com as palavras de ligação das pistas de citação removidas das
    pontas do nome (ver _PALAVRAS_PISTA_CONECTORAS) — o que sobrar com
    menos de 2 palavras é ambíguo demais e é descartado, mesmo âmbito
    deliberado do resto desta verificação."""
    encontradas = set(_PADRAO_SIGLA.findall(frase))
    for candidato in _PADRAO_NOME_PROPRIO.findall(frase):
        palavras = candidato.split()
        while palavras and palavras[0].lower() in _PALAVRAS_PISTA_CONECTORAS:
            palavras.pop(0)
        while palavras and palavras[-1].lower() in _PALAVRAS_PISTA_CONECTORAS:
            palavras.pop()
        if len(palavras) >= 2:
            encontradas.add(" ".join(palavras))
    return encontradas


def verificar_fontes_nomeadas(resposta: str, mensagens: list) -> str:
    """Para cada frase que cita uma fonte externa por nome (pista em
    _PISTAS_CITACAO), confere se o nome citado aparece no texto das
    ferramentas/utilizador desta troca — mesmo princípio do
    verificar_urls_citados, só sem exigir um link."""
    texto_fontes = "\n".join(
        m.get("content") or "" for m in mensagens if m.get("role") in ("tool", "user", "system")
    )

    nao_confirmadas = set()
    for frase in re.split(r"(?<=[.!?])\s+", resposta):
        frase_min = frase.lower()
        if not any(pista in frase_min for pista in _PISTAS_CITACAO):
            continue
        for nome in _fontes_citadas(frase):
            if nome not in texto_fontes:
                nao_confirmadas.add(nome)

    if not nao_confirmadas:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — aviso de fontes não confirmadas]\n"
        "⚠️ Estes nomes são citados como fonte, mas não aparecem em "
        "nenhum resultado de ferramenta nem em nada que escreveste "
        "nesta troca — podem estar inventados: " + "; ".join(sorted(nao_confirmadas))
    )
    return resposta + aviso


# Verificação de ficheiros citados sem terem sido lidos/listados (16
# Ago 2026, ver HISTORICO.md) — incidente real ao vivo, apanhado pelo
# utilizador na sua própria conversa: um pedido trivial de continuação
# ("sim") gerou uma resposta a descrever "utils.py" e "memoria.py" —
# nome de função a função, contagem de caracteres incluída — quando
# NENHUM dos dois ficheiros existe no projecto (é "memory.py", nem o
# nome bateu certo) e SEM CHAMAR NENHUMA FERRAMENTA nesta troca.
#
# Nenhum nível anterior apanha isto: sem URL, sem "segundo..."/fonte
# nomeada, sem a linguagem estreita de _CATEGORIAS_FUNDAMENTO ("li o
# ficheiro"/"o ficheiro contém" — a resposta real dizia só "Contém
# funções utilitárias gerais", nunca essas frases exactas). É
# precisamente a "invenção difusa em prosa livre" que o Nível 1 já
# assumia, desde o início, estar fora do alcance de qualquer
# verificação mecânica — confirmado ao vivo nesta troca real.
#
# Âmbito estreito, mesmo espírito do resto: só actua no padrão exacto
# do incidente — um nome de ficheiro (extensão reconhecida) citado
# como um bloco descritivo ("**nome.ext** (N caracteres):" ou
# "**nome.ext**:"), não qualquer menção casual do nome dentro de uma
# frase corrida. Confirma se esse nome apareceu nesta troca nalgum
# resultado de ferramenta, no que o utilizador escreveu, ou nos
# próprios argumentos de uma chamada de ferramenta feita pelo modelo
# — um ficheiro que ele tentou ler, mesmo que o resultado ainda não
# tenha chegado ou tenha dado erro, não é invenção, é uma tentativa
# real.
_PADRAO_FICHEIRO_DESCRITO = re.compile(
    r"[`*]*\b([\w\-./]+\.(?:py|md|txt|json|jsonl|toml|cfg|ini|sh|yml|yaml|env))\b[`*]*\s*[:(]"
)


def verificar_ficheiros_citados(resposta: str, mensagens: list) -> str:
    """Cada ficheiro citado como um bloco descritivo (nome + resumo do
    que faz) tem de ter sido realmente tocado nesta troca — lido,
    listado, ou pelo menos tentado — senão não há forma honesta de o
    modelo saber o que lá está."""
    citados = set(_PADRAO_FICHEIRO_DESCRITO.findall(resposta))
    if not citados:
        return resposta

    texto_fontes = "\n".join(
        m.get("content") or "" for m in mensagens if m.get("role") in ("tool", "user", "system")
    )
    for m in mensagens:
        if m.get("role") == "assistant":
            for tc in (m.get("tool_calls") or []):
                texto_fontes += "\n" + json.dumps(
                    tc.get("function", {}).get("arguments", {}), ensure_ascii=False
                )

    nao_confirmados = sorted(nome for nome in citados if nome not in texto_fontes)
    if not nao_confirmados:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — aviso de ficheiros não confirmados]\n"
        "⚠️ Estes ficheiros são descritos como se tivessem sido lidos, "
        "mas nunca foram tocados por nenhuma ferramenta nesta troca — "
        "podem estar inventados: " + "; ".join(nao_confirmados)
    )
    return resposta + aviso


# Verificação de existência contraditada por listar_ficheiros (16 Ago
# 2026, ver HISTORICO.md) — 2º incidente real da mesma sessão do
# utilizador, DIFERENTE do anterior: aqui o modelo chamou mesmo
# listar_ficheiros (confirmado: resultado real, sem "utils.py" nem
# "memoria.py", testado directamente contra a ferramenta — não é bug
# das ferramentas), e MESMO ASSIM respondeu "Sim, existem!" a "utils.py
# e memoria.py existem mesmo?". A verificação anterior
# (verificar_ficheiros_citados) não apanha isto: não há um bloco
# descritivo "**nome.ext** (N caracteres):" a citar esses 2 nomes na
# própria resposta — a resposta nem sequer os repete, só confirma em
# prosa vaga ("Sim, existem!") o que o utilizador tinha perguntado.
#
# Mais próximo do "Nível 2" discutido com o utilizador (verificar o
# CONTEÚDO de uma afirmação contra o resultado real de uma ferramenta,
# não só se a ferramenta foi chamada) — mas continua mecânico e
# barato: listar_ficheiros devolve uma lista de nomes em texto simples,
# por isso "o nome está literalmente na última listagem desta troca?"
# é uma verificação de substring, não semântica a sério.
#
# Cuidado deliberado com negação: "X não existe" é uma afirmação
# CORRECTA de ausência, não deve disparar — só "X existe"/"existem"
# sem "não" a preceder é que é uma afirmação de presença a confirmar.
_FRASES_AFIRMA_EXISTENCIA = ("existe", "existem", "está na lista", "estão na lista")
_PADRAO_NOME_FICHEIRO = re.compile(
    r"\b[\w\-]+\.(?:py|md|txt|json|jsonl|toml|cfg|ini|sh|yml|yaml|env)\b"
)


def _tem_negacao_antes(frase_min: str, pos: int) -> bool:
    """'não' na janela curta imediatamente antes de pos — para não
    confundir 'X não existe' (correcto) com 'X existe' (o que esta
    verificação quer confirmar)."""
    return "não" in frase_min[max(0, pos - 15):pos]


def _resultados_por_ferramenta(mensagens: list, nome_ferramenta: str) -> list[str]:
    """Resultados (conteúdo) de todas as chamadas a uma ferramenta
    específica nesta troca, na ordem em que aconteceram — casa cada
    tool_call de uma mensagem assistant com as mensagens tool
    seguintes (protocolo padrão: N tool_calls seguidos de N respostas
    tool, pela mesma ordem — não há campo 'name' na mensagem tool que
    diga directamente qual ferramenta respondeu)."""
    resultados = []
    for i, m in enumerate(mensagens):
        if m.get("role") != "assistant":
            continue
        chamadas = m.get("tool_calls") or []
        seguintes = [x for x in mensagens[i + 1:i + 1 + len(chamadas)] if x.get("role") == "tool"]
        for chamada, resposta_tool in zip(chamadas, seguintes):
            if chamada["function"]["name"] == nome_ferramenta:
                resultados.append(resposta_tool.get("content") or "")
    return resultados


def verificar_existencia_ficheiros(resposta: str, mensagens: list) -> str:
    """Se a resposta afirma que um ficheiro existe/está na lista, e
    listar_ficheiros foi mesmo chamado nesta troca, confere se o nome
    aparece de facto nalguma listagem real desta troca — sem isto, é
    uma contradição directa do próprio resultado que o modelo leu.

    BUG REAL corrigido 17 Ago 2026 (achado ao testar o SUPERLLMAPI,
    ver HISTORICO.md desse repo — lógica idêntica aqui, mesmo bug):
    quando a troca chama listar_ficheiros mais que uma vez para
    pastas DIFERENTES (ex.: pasta principal, depois 2 subpastas em
    paralelo — o próprio CORE_IDENTITY incentiva agrupar chamadas
    independentes na mesma resposta), olhar só para listagens[-1]
    pega na ÚLTIMA chamada, não necessariamente a relevante — ficheiros
    reais listados numa chamada ANTERIOR da mesma troca disparavam
    "existência contraditada" por engano, um falso positivo directo.
    Corrigido para juntar TODAS as listagens desta troca antes de
    confirmar — um ficheiro só conta como "não confirmado" se estiver
    ausente de qualquer uma delas."""
    listagens = _resultados_por_ferramenta(mensagens, "listar_ficheiros")
    if not listagens:
        return resposta
    todas_listagens = "\n".join(listagens)

    # Nomes da última pergunta do utilizador nesta troca — uma
    # afirmação vaga ("Sim, existem!") confirma implicitamente os
    # nomes que o utilizador tinha acabado de perguntar, mesmo que a
    # resposta não os repita — foi exactamente o caso real.
    pedido_utilizador = next(
        (m["content"] for m in reversed(mensagens) if m.get("role") == "user" and m.get("content")),
        "",
    )
    nomes_do_pedido = set(_PADRAO_NOME_FICHEIRO.findall(pedido_utilizador))

    afirmados_ausentes = set()
    for frase in re.split(r"(?<=[.!?])\s+", resposta):
        frase_min = frase.lower()
        tem_afirmacao = any(
            f in frase_min and not _tem_negacao_antes(frase_min, frase_min.index(f))
            for f in _FRASES_AFIRMA_EXISTENCIA
        )
        if not tem_afirmacao:
            continue
        nomes_na_frase = set(_PADRAO_NOME_FICHEIRO.findall(frase)) or nomes_do_pedido
        for nome in nomes_na_frase:
            if nome not in todas_listagens:
                afirmados_ausentes.add(nome)

    if not afirmados_ausentes:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — aviso de existência contraditada]\n"
        "⚠️ Estes ficheiros são afirmados como existentes, mas NÃO "
        "aparecem no resultado real do último listar_ficheiros desta "
        "troca — contradição directa: " + "; ".join(sorted(afirmados_ausentes))
    )
    return resposta + aviso


# Verificação semântica de conteúdo (17 Ago 2026) — Nível 2 do plano
# anti-confabulação. Diferente de todos os anteriores: NÍVEL 1/1.5 são
# mecânicos (regex + comparação de string, custo ~0), esta é a primeira
# que pede uma 2ª chamada ao modelo — por isso desligada por omissão
# (config.NIVEL2_ATIVO = False) e só corre em respostas com texto
# suficiente para conter afirmações factuais reais (config.NIVEL2_MIN_CHARS).
#
# Incidente real motivador: um pedido de pesquisa (DAAZPRIME, 13 Ago
# 2026) recebeu uma resposta a citar "Google AI Overview"/"ChatGPT" com
# URLs inventados — o Nível 1.5 confirmou que pesquisar_web NÃO foi
# chamado (apanhou o "fingiu que pesquisou"), e os URLs foram apanhados
# pelo verificar_urls_citados. Mas o caso mais subtil ficou por apanhar:
# "pesquisou mas exagerou por cima" — a ferramenta foi chamada a sério,
# o URL até pode estar correcto, mas o conteúdo em prosa livre
# (percentagens, resumos, afirmações de comportamento) não bate com o
# que a ferramenta realmente devolveu. Nenhuma verificação mecânica
# alcança isto — é preciso perceber se o SENTIDO de uma frase é
# suportado pelo texto da fonte, não só se uma string aparece.
#
# Gatilho deliberadamente estreito (mesma disciplina de sempre): só
# corre quando (1) NIVEL2_ATIVO está ligado, (2) a resposta tem texto
# suficiente (NIVEL2_MIN_CHARS), (3) houve ferramentas nesta troca, E
# (4) as verificações anteriores não encontraram nada — se o Nível 1/1.5
# já assinalou um problema concreto, não gastamos uma 2ª chamada ao
# modelo para ver se há mais; a resposta já está marcada.
#
# Custo: 1 chamada ao modelo por resposta que chegue até aqui. O prompt
# é curto (fontes + resposta), sem tools/histórico — o suficiente para
# o modelo decidir se as afirmações são suportadas, sem carregar com o
# contexto pesado do pedido original.


def verificar_semantica(resposta: str, mensagens: list) -> str:
    """Verifica se o conteúdo em prosa livre da resposta (afirmações
    factuais concretas) é suportado pelo que as ferramentas desta troca
    realmente devolveram. Não corrige — mesmo princípio do Nível 1:
    torna a suspeita visível, utilizador decide.

    Só corre quando NIVEL2_ATIVO está ligado. Em caso de dúvida (JSON
    do modelo inválido, erro de rede, timeout) devolve a resposta
    original sem aviso — nunca deixa a troca rebentar."""
    if not config.NIVEL2_ATIVO:
        return resposta
    if len(resposta) < config.NIVEL2_MIN_CHARS:
        return resposta
    if not any(m.get("role") == "tool" for m in mensagens):
        return resposta

    # Se as verificações anteriores já assinalaram algo, não gastamos
    # uma 2ª chamada ao modelo — a resposta já tem aviso(s).
    if "\n[SUPERLLMLOCAL —" in resposta:
        return resposta

    fontes = "\n".join(
        m["content"] for m in mensagens if m.get("role") == "tool" and m.get("content")
    )
    if not fontes.strip():
        return resposta

    prompt = (
        "Tarefa: verificação factual. FONTE é o resultado real de "
        "ferramentas. AFIRMAÇÃO é uma resposta que deve basear-se só na "
        "FONTE. Lista, em JSON (array de strings, [] se nenhuma), as "
        "frases da AFIRMAÇÃO que fazem uma alegação factual concreta "
        "(número, comportamento, facto) NÃO suportada pela FONTE. Não "
        "assinales opiniões, sugestões ou o que já está correcto.\n\n"
        f"FONTE:\n{fontes}\n\nAFIRMAÇÃO:\n{resposta}"
    )

    try:
        body = json.dumps({
            "model": config.MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "options": config.OPTIONS,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{config.OLLAMA_HOST}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        texto_modelo = (data.get("message", {}).get("content") or "").strip()
        # O modelo nem sempre devolve JSON puro apesar de pedido no
        # prompt — HISTORICO.md já documentou (10 Ago 2026, tool-calling)
        # que este modelo pode ignorar instruções de formato e escrever
        # texto/markdown à volta. Extrai o array JSON de dentro do texto
        # (ex.: ```json [...] ``` ou "Aqui está: [...]") em vez de exigir
        # que a resposta inteira seja só o array.
        match = re.search(r"\[.*\]", texto_modelo, re.DOTALL)
        if not match:
            return resposta
        nao_suportadas = json.loads(match.group(0))
        if not isinstance(nao_suportadas, list):
            return resposta
        nao_suportadas = [s for s in nao_suportadas if isinstance(s, str) and s.strip()]
    except Exception:  # noqa: BLE001 — catch-all intencional, ver comentário acima
        # Erro de rede, timeout, JSON inválido do modelo, ou qualquer
        # outro problema — devolve resposta original sem aviso. Mesmo
        # princípio das outras verificar_*: em caso de dúvida, não
        # bloqueia nem assinala, só deixa passar.
        return resposta

    if not nao_suportadas:
        return resposta

    aviso = (
        "\n\n---\n[SUPERLLMLOCAL — verificação semântica Nível 2]\n"
        "⚠️ Não confirmado na fonte: " + "; ".join(nao_suportadas)
    )
    return resposta + aviso
