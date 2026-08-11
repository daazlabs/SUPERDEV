"""
Ferramentas do SUPERDEV.

Usa a API nativa de "tools" da Ollama (não o parâmetro genérico
"format" — testámos os dois; "format" não restringiu nada, o modelo
ignorou-o ou inventou a sua própria forma de JSON. A API nativa de
tools é a que o qwen3.5 foi treinado a respeitar, e é a Ollama, não
nós, que garante a forma da chamada.

ISTO É ESPECÍFICO DO MODELO EM config.MODEL (qwen3.5), NÃO É
GARANTIDO PARA QUALQUER MODELO. A Ollama tem um interpretador dedicado
para este modelo (PARSER qwen3.5). Se o modelo mudar, este ficheiro
tem de ser testado outra vez do zero — "format" pode passar a
funcionar, "tools" pode deixar de funcionar, pode ser preciso outra
abordagem qualquer. Não assumir que continua igual.

Primeira ferramenta: ler_ficheiro.
Ferramentas 2 e 3 (9 Ago 2026): listar_ficheiros e procurar_texto —
adicionadas para testar se o modelo escolhe bem entre várias
ferramentas, não só usar uma sozinha. Mesmo espírito do ler_ficheiro:
só leitura, nunca inventa, falha de forma clara.

Ferramenta 4, correr_ruff (9 Ago 2026) — primeira que EXECUTA algo,
não só lê. Objectivo: fechar o ciclo gera→verifica→corrige com um
erro REAL de um linter, em vez do modelo "adivinhar" onde errou
(auto-crítica) — mesmo princípio já validado com o grounding de
memória (deixar o modelo decidir por si próprio se está certo tem o
mesmo ponto cego de o deixar inventar factos). Custo é CONDICIONAL,
não fixo: o modelo só chama esta ferramenta se decidir que vale a
pena (é ele que escolhe via tool_calls, como as outras 3) e correr o
ruff é um subprocesso (milissegundos, ~0 tokens), não uma 2ª chamada
ao modelo — ao contrário de auto-crítica, que dobra sempre o custo. O
código recebido nunca toca em ficheiros reais do projecto: é escrito
num ficheiro temporário descartável só para a duração da verificação,
apagado logo a seguir, mesmo em caso de erro/timeout.

Ferramenta 5, ler_varios_ficheiros (9 Ago 2026) — motivada por um caso
real: um pedido para analisar 9 ficheiros do próprio projecto excedeu
MAX_VOLTAS_FERRAMENTAS (5) a meio, porque ler_ficheiro só lê 1 de cada
vez, e CADA volta reenvia a conversa TODA até ali (a Ollama não tem
memória entre chamadas) — o custo crescia a cada ficheiro, não só o
número de voltas. A correcção óbvia (subir o limite) foi rejeitada de
propósito: só adiava o problema, não o resolvia — continuava a pagar
o "reenviar tudo" N vezes, só que N maior. Ler vários ficheiros numa
só volta corta as voltas necessárias de ~N para ~1-2, sem tocar no
limite. Mesmo espírito só-leitura das outras: falha de forma clara por
ficheiro (reaproveita ler_ficheiro), nunca inventa.

Ferramenta 6, pesquisar_web (10 Ago 2026) — primeira ferramenta que sai
da máquina. Motivada pelo utilizador: queria testar o agente com
perguntas que precisam de informação actual, não só código local. Usa
o SearXNG que já corre no Docker local (config.SEARXNG_HOST) — sem
chave de API nenhuma, sem enviar nada para fora desta máquina (o
SearXNG é que fala com os motores de busca reais). Mesmo espírito das
outras: falha de forma clara se o SearXNG estiver em baixo, nunca
inventa um resultado.

Ferramenta 7, listar_simbolos (11 Ago 2026) — "contexto selectivo"
(recomendação B2 da pesquisa de mercado, ver PESQUISA/relatorio-
mercado.md secção 2.4/6.2): um mapa de classes/funções/assinaturas de
um ficheiro ou pasta .py, sem o corpo das funções — para o modelo
poder decidir "o que há aqui" sem gastar o ler_ficheiro inteiro
quando só precisa de uma visão geral. Usa só `ast` (biblioteca
padrão, sem dependência nova). Limitação deliberada: só Python — o
projecto é só Python, e um mapa genérico multi-linguagem seria muito
mais caro de construir para um ganho que não existe aqui.
"""
import ast
import fnmatch
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import config

# Limite simples para não rebentar a janela de contexto com um
# ficheiro enorme.
LIMITE_CARACTERES = 8000

# Limites para as ferramentas de listagem/procura — mesma lógica do
# LIMITE_CARACTERES: cortar de forma clara em vez de rebentar o
# contexto ou correr para sempre num diretório grande.
LIMITE_ENTRADAS_LISTAR = 200
LIMITE_RESULTADOS_PROCURAR = 40
LIMITE_FICHEIROS_PROCURADOS = 500

# Protecção contra o ruff (ou o próprio SO) ficar preso — nunca deve
# demorar mais que isto num ficheiro só; se demorar, é sinal de que
# algo está mal, não vale a pena esperar mais.
RUFF_TIMEOUT_S = 5

# Limites do ler_varios_ficheiros — dois tectos independentes: nº de
# ficheiros pedidos de uma vez (não vale a pena pedir 200) e caracteres
# somados de todos juntos (não vale a pena um só lote rebentar sozinho
# com a janela de contexto). Mesma filosofia dos outros limites deste
# ficheiro: cortar de forma clara, nunca correr sem tecto.
LIMITE_FICHEIROS_LOTE = 15
LIMITE_CARACTERES_LOTE = 30000

# pesquisar_web — poucos resultados de propósito (mesma filosofia dos
# outros limites): o modelo já recebe pouco contexto por resultado
# (título+resumo, sem o conteúdo completo da página), 5 chega para
# decidir se vale a pena e não enche o prompt com ruído.
LIMITE_RESULTADOS_WEB = 5
PESQUISA_WEB_TIMEOUT_S = 8

# listar_simbolos — mesma filosofia: nº de ficheiros mapeados de uma
# vez tem tecto (não vale a pena mapear um repo inteiro de propósito),
# e o mapa somado também, reaproveitando LIMITE_CARACTERES_LOTE (é o
# mesmo tipo de tecto — texto agregado de vários ficheiros numa só
# chamada — não vale a pena um terceiro nome para o mesmo conceito).
LIMITE_FICHEIROS_SIMBOLOS = 30


def ler_ficheiro(caminho: str, inicio: int = 0) -> str:
    """Lê um ficheiro de texto do disco, a partir do caractere `inicio`
    (0 = desde o princípio). Falha de forma clara se não existir ou
    não for legível — nunca inventa conteúdo.

    `inicio` existe por um bug real (10 Ago 2026): um ficheiro maior
    que LIMITE_CARACTERES corta, e o modelo, ao pedirem-lhe para
    "continuar a ler", só sabia voltar a chamar ler_ficheiro sem mais
    nada — o que devolvia o MESMO excerto cortado no MESMO sítio,
    outra vez (confirmado a reproduzir: 2 chamadas seguidas, resultado
    idêntico). A mensagem de corte agora diz exactamente que valor de
    `inicio` usar a seguir, para o ciclo poder mesmo avançar."""
    caminho = os.path.abspath(os.path.expanduser(caminho))
    if not os.path.isfile(caminho):
        return f"[ERRO] Ficheiro não encontrado: {caminho}"
    try:
        with open(caminho, "r", errors="replace") as f:
            conteudo = f.read()
    except Exception as e:
        return f"[ERRO] Não foi possível ler o ficheiro: {e}"

    tamanho_total = len(conteudo)
    if inicio:
        if inicio >= tamanho_total:
            return (
                f"[AVISO] inicio={inicio} está para lá do fim do ficheiro "
                f"({tamanho_total} caracteres no total) — nada mais para ler."
            )
        conteudo = conteudo[inicio:]

    if len(conteudo) > LIMITE_CARACTERES:
        fim = inicio + LIMITE_CARACTERES
        conteudo = (
            conteudo[:LIMITE_CARACTERES]
            + f"\n...[cortado — a mostrar caracteres {inicio}-{fim} de "
              f"{tamanho_total} no total. Para continuar, chama "
              f"ler_ficheiro outra vez com inicio={fim}.]"
        )
    return conteudo


def listar_ficheiros(caminho: str) -> str:
    """Lista o conteúdo de uma pasta (não recursivo). Falha de forma
    clara se a pasta não existir ou não for uma pasta."""
    caminho = os.path.abspath(os.path.expanduser(caminho))
    if not os.path.isdir(caminho):
        return f"[ERRO] Pasta não encontrada: {caminho}"
    try:
        entradas = sorted(os.listdir(caminho))
    except Exception as e:
        return f"[ERRO] Não foi possível listar a pasta: {e}"

    linhas = []
    for nome in entradas[:LIMITE_ENTRADAS_LISTAR]:
        completo = os.path.join(caminho, nome)
        linhas.append(f"{nome}/" if os.path.isdir(completo) else nome)

    resultado = "\n".join(linhas) if linhas else "(pasta vazia)"
    if len(entradas) > LIMITE_ENTRADAS_LISTAR:
        resultado += (
            f"\n...[cortado — pasta tem {len(entradas)} entradas, só as "
            f"primeiras {LIMITE_ENTRADAS_LISTAR} foram listadas]"
        )
    return resultado


def procurar_texto(caminho: str, termo: str) -> str:
    """Procura um termo de texto (sem regex, sensível a maiúsculas)
    num ficheiro ou, se caminho for uma pasta, em todos os ficheiros
    de texto dentro dela (recursivo). Devolve "caminho:linha: texto"
    por cada ocorrência, até ao limite. Falha de forma clara se o
    caminho não existir."""
    caminho = os.path.abspath(os.path.expanduser(caminho))
    if not os.path.exists(caminho):
        return f"[ERRO] Caminho não encontrado: {caminho}"

    if os.path.isfile(caminho):
        ficheiros = [caminho]
    else:
        ficheiros = []
        for raiz, pastas, nomes in os.walk(caminho):
            # ignora pastas óbvias de lixo/dependências para não
            # perder tempo (e resultados úteis) em ruído
            pastas[:] = [p for p in pastas if p not in (
                ".git", "__pycache__", "node_modules", ".venv", "venv"
            )]
            for nome in nomes:
                ficheiros.append(os.path.join(raiz, nome))
                if len(ficheiros) >= LIMITE_FICHEIROS_PROCURADOS:
                    break
            if len(ficheiros) >= LIMITE_FICHEIROS_PROCURADOS:
                break

    resultados = []
    for f in ficheiros:
        if len(resultados) >= LIMITE_RESULTADOS_PROCURAR:
            break
        try:
            with open(f, "r", errors="replace") as fh:
                for i, linha in enumerate(fh, start=1):
                    if termo in linha:
                        resultados.append(f"{f}:{i}: {linha.strip()}")
                        if len(resultados) >= LIMITE_RESULTADOS_PROCURAR:
                            break
        except Exception:
            # ficheiro binário ou ilegível — ignora e continua, não é
            # um erro fatal da ferramenta
            continue

    if not resultados:
        return f"[SEM RESULTADOS] Termo '{termo}' não encontrado em {caminho}"

    resultado = "\n".join(resultados)
    if len(resultados) >= LIMITE_RESULTADOS_PROCURAR:
        resultado += (
            f"\n...[cortado — atingiu o limite de "
            f"{LIMITE_RESULTADOS_PROCURAR} resultados]"
        )
    return resultado


def correr_ruff(codigo: str) -> str:
    """Verifica um excerto de código Python com o ruff (linter) e
    devolve os problemas encontrados, ou confirmação de que está
    limpo. O código é escrito num ficheiro temporário só para a
    verificação e apagado logo a seguir — nunca fica no disco, nunca
    toca em ficheiros reais do projecto."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(codigo)
    try:
        try:
            resultado = subprocess.run(
                ["ruff", "check", "--output-format=concise", tmp.name],
                capture_output=True,
                text=True,
                timeout=RUFF_TIMEOUT_S,
                check=False,
            )
        except FileNotFoundError:
            return "[ERRO] ruff não está instalado neste sistema."
        except subprocess.TimeoutExpired:
            return f"[ERRO] ruff excedeu o tempo limite ({RUFF_TIMEOUT_S}s)."
    finally:
        # apaga sempre, mesmo se o subprocess falhar/exceder o tempo —
        # nunca deixar o ficheiro temporário para trás
        os.remove(tmp.name)

    # o caminho do ficheiro temporário não interessa ao modelo (é
    # descartável e não corresponde a nada real) — substitui-se por um
    # rótulo neutro para não o confundir com um caminho a citar
    saida = (resultado.stdout + resultado.stderr).strip().replace(tmp.name, "código")

    # returncode==0 chega para "está limpo" — não confiar em stdout
    # vazio: o ruff escreve "All checks passed!" mesmo sem problemas
    # (apanhado ao testar ao vivo), por isso essa condição falhava.
    if resultado.returncode == 0:
        return "[OK] ruff não encontrou problemas."
    if len(saida) > LIMITE_CARACTERES:
        saida = saida[:LIMITE_CARACTERES] + "\n...[cortado]"
    return saida


def ler_varios_ficheiros(caminhos: list) -> str:
    """Lê vários ficheiros de texto numa só chamada — cada ficheiro
    passa pelo mesmo ler_ficheiro (mesmas mensagens de erro, mesmo
    corte por ficheiro), mas tudo junto numa só volta em vez de uma
    volta por ficheiro. Pára de ler mais ficheiros se o total somado
    ultrapassar LIMITE_CARACTERES_LOTE, avisando de forma clara
    quantos ficaram por ler — nunca corta um ficheiro a meio sem
    dizer."""
    aviso_demasiados = None
    if len(caminhos) > LIMITE_FICHEIROS_LOTE:
        aviso_demasiados = (
            f"[AVISO] Pediste {len(caminhos)} ficheiros, só os "
            f"primeiros {LIMITE_FICHEIROS_LOTE} foram lidos."
        )
        caminhos = caminhos[:LIMITE_FICHEIROS_LOTE]

    partes = []
    total = 0
    ficheiros_por_ler = 0
    for i, caminho in enumerate(caminhos):
        if total >= LIMITE_CARACTERES_LOTE:
            ficheiros_por_ler = len(caminhos) - i
            break
        conteudo = ler_ficheiro(caminho)
        restante = LIMITE_CARACTERES_LOTE - total
        if len(conteudo) > restante:
            conteudo = conteudo[:restante] + "\n...[cortado — limite total do lote atingido]"
        partes.append(f"=== {caminho} ===\n{conteudo}")
        total += len(conteudo)

    resultado = "\n\n".join(partes)
    if ficheiros_por_ler:
        resultado += (
            f"\n\n[AVISO] {ficheiros_por_ler} ficheiro(s) não lidos — "
            "limite total do lote atingido."
        )
    if aviso_demasiados:
        resultado += f"\n\n{aviso_demasiados}"
    return resultado


def pesquisar_web(query: str) -> str:
    """Pesquisa na web através do SearXNG local (config.SEARXNG_HOST) e
    devolve título + resumo + URL dos primeiros resultados. Falha de
    forma clara se o SearXNG estiver em baixo ou não responder a
    tempo — nunca inventa um resultado."""
    url = f"{config.SEARXNG_HOST}/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "SUPERDEV/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=PESQUISA_WEB_TIMEOUT_S) as r:
            dados = json.loads(r.read())
    except urllib.error.URLError as e:
        return f"[ERRO] Não foi possível contactar o SearXNG ({config.SEARXNG_HOST}): {e}"
    except TimeoutError:
        return f"[ERRO] SearXNG excedeu o tempo limite ({PESQUISA_WEB_TIMEOUT_S}s)."
    except json.JSONDecodeError:
        return "[ERRO] SearXNG devolveu uma resposta que não é JSON válido."

    resultados = dados.get("results") or []
    if not resultados:
        return f"[SEM RESULTADOS] A pesquisa por '{query}' não devolveu nada."

    partes = []
    for r in resultados[:LIMITE_RESULTADOS_WEB]:
        titulo = (r.get("title") or "(sem título)").strip()
        resumo = (r.get("content") or "").strip()
        link = r.get("url") or ""
        partes.append(f"- {titulo}\n  {resumo}\n  {link}")
    return "\n".join(partes)


def _assinatura(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstrói "a, b=1, *args, c, **kwargs" a partir do nó AST de
    uma função — sem correr o código, só a árvore sintáctica."""
    args = node.args
    partes = []
    n_pos = len(args.args)
    n_defaults = len(args.defaults)
    for i, a in enumerate(args.args):
        s = a.arg
        idx_default = i - (n_pos - n_defaults)
        if idx_default >= 0:
            s += f"={ast.unparse(args.defaults[idx_default])}"
        partes.append(s)
    if args.vararg:
        partes.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        partes.append("*")
    for kw, default in zip(args.kwonlyargs, args.kw_defaults):
        s = kw.arg
        if default is not None:
            s += f"={ast.unparse(default)}"
        partes.append(s)
    if args.kwarg:
        partes.append(f"**{args.kwarg.arg}")
    return ", ".join(partes)


def _primeira_linha_docstring(node) -> str:
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0] if doc else ""


def listar_simbolos(caminho: str) -> str:
    """Mapa de classes/funções de um ficheiro .py ou pasta (recursivo)
    — nome, assinatura e 1ª linha da docstring de cada uma, sem o
    corpo. "Contexto selectivo": para o modelo perceber o que um
    ficheiro/módulo contém sem pagar o custo de ler_ficheiro inteiro
    quando só precisa de uma visão geral (ex.: "o que há em tools.py"
    antes de decidir se vale a pena ler uma função específica). Falha
    de forma clara por ficheiro (sintaxe inválida não pára os
    restantes) — nunca inventa uma assinatura."""
    caminho = os.path.abspath(os.path.expanduser(caminho))
    if not os.path.exists(caminho):
        return f"[ERRO] Caminho não encontrado: {caminho}"

    if os.path.isfile(caminho):
        ficheiros = [caminho]
    else:
        ficheiros = []
        for raiz, pastas, nomes in os.walk(caminho):
            pastas[:] = [p for p in pastas if p not in (
                ".git", "__pycache__", "node_modules", ".venv", "venv"
            )]
            ficheiros.extend(
                os.path.join(raiz, nome) for nome in nomes if nome.endswith(".py")
            )
            if len(ficheiros) >= LIMITE_FICHEIROS_SIMBOLOS:
                break
        ficheiros = ficheiros[:LIMITE_FICHEIROS_SIMBOLOS]

    if not ficheiros:
        return f"[SEM RESULTADOS] Nenhum ficheiro .py encontrado em {caminho}"

    blocos = []
    for f in ficheiros:
        try:
            with open(f, "r", errors="replace") as fh:
                arvore = ast.parse(fh.read(), filename=f)
        except SyntaxError as e:
            blocos.append(f"{f}:\n  [ERRO] não é Python válido: {e}")
            continue
        except Exception as e:
            blocos.append(f"{f}:\n  [ERRO] não foi possível ler/analisar: {e}")
            continue

        linhas = []
        for node in arvore.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sufixo = _primeira_linha_docstring(node)
                linhas.append(
                    f"  def {node.name}({_assinatura(node)})"
                    + (f" — {sufixo}" if sufixo else "")
                )
            elif isinstance(node, ast.ClassDef):
                sufixo = _primeira_linha_docstring(node)
                linhas.append(f"  class {node.name}:" + (f" — {sufixo}" if sufixo else ""))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        subsufixo = _primeira_linha_docstring(sub)
                        linhas.append(
                            f"    def {sub.name}({_assinatura(sub)})"
                            + (f" — {subsufixo}" if subsufixo else "")
                        )
        blocos.append(f"{f}:\n" + ("\n".join(linhas) if linhas else "  (sem classes/funções de topo)"))

    resultado = "\n\n".join(blocos)
    if len(resultado) > LIMITE_CARACTERES_LOTE:
        resultado = resultado[:LIMITE_CARACTERES_LOTE] + "\n...[cortado — mapa maior que o limite]"
    return resultado


# Definições no formato nativo da Ollama (compatível com a convenção
# OpenAI de function-calling) — é isto que vai no campo "tools" do
# pedido à API.
#
# TEXTO EM INGLÊS DE PROPÓSITO (9 Ago 2026) — decisão testada, não
# esquecimento: isto nunca é visto pelo utilizador, só é lido pelo
# modelo para saber o que as ferramentas fazem. Medido ao vivo: ~3%
# menos tokens por pedido com ferramentas oferecidas (e isto repete em
# cada volta do ciclo) sem alterar nada da conversa em português. Os
# nomes das funções (`name`) e dos parâmetros ficam como estão
# (`ler_ficheiro`, `caminho`, etc.) — mudar isso obrigaria a
# revalidar todo o tools.py (ver aviso no topo do ficheiro), o texto
# livre de "description" não tem esse risco.
TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "ler_ficheiro",
            "description": (
                "Reads the content of a text file from disk. If you need "
                "more than one file, use ler_varios_ficheiros instead — "
                "one round-trip for all of them is much cheaper than one "
                "round-trip per file. If the result was cut off (file "
                "bigger than the character limit), the cutoff message "
                "tells you the exact 'inicio' value to pass on the next "
                "call to keep reading from where it stopped — calling "
                "ler_ficheiro again with the same arguments just returns "
                "the same cut-off excerpt, not the rest of the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Absolute path of the file to read",
                    },
                    "inicio": {
                        "type": "integer",
                        "description": (
                            "Character offset to start reading from — 0 "
                            "(default) reads from the beginning. Use the "
                            "value given in a previous cutoff message to "
                            "continue reading a large file."
                        ),
                    },
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_ficheiros",
            "description": "Lists the files and subfolders of a folder (non-recursive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Absolute path of the folder to list",
                    },
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "procurar_texto",
            "description": (
                "Searches for an exact text term in a file or, "
                "recursively, across all files in a folder. Returns "
                "the lines where the term appears."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Absolute path of the file or folder to search",
                    },
                    "termo": {
                        "type": "string",
                        "description": "Exact text term to search for",
                    },
                },
                "required": ["caminho", "termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "correr_ruff",
            "description": (
                "Checks a Python code snippet with ruff (a linter) and "
                "returns real errors/warnings found, or confirmation "
                "it's clean. Use this to verify code you just wrote "
                "before giving it as the final answer, instead of "
                "guessing whether it's correct."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "The Python code to check",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_varios_ficheiros",
            "description": (
                "Reads multiple text files in a single call. Prefer this "
                "over calling ler_ficheiro repeatedly whenever you need "
                "more than one file — each tool round-trip resends the "
                "whole conversation so far, so one call for N files is "
                "much cheaper than N separate calls."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminhos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths of the files to read",
                    },
                },
                "required": ["caminhos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_web",
            "description": (
                "Searches the web for current information (news, "
                "docs, anything outside this project's local files). "
                "Returns title, short summary, and URL for the top "
                "results. Use this instead of guessing when a question "
                "needs up-to-date or external information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_simbolos",
            "description": (
                "Returns a lightweight map of a Python file (or folder, "
                "recursive) — class/function names, signatures, and the "
                "first line of each docstring, WITHOUT the function "
                "bodies. Prefer this over ler_ficheiro when you just "
                "need to know what a file/module contains (what "
                "functions/classes it has, what arguments they take) "
                "before deciding whether to read it in full. Python "
                "files only (.py) — for other file types use "
                "ler_ficheiro or procurar_texto instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Absolute path of the .py file or folder to map",
                    },
                },
                "required": ["caminho"],
            },
        },
    },
]

# Mapa nome -> função real, para executar o que o modelo pedir.
FUNCOES = {
    "ler_ficheiro": ler_ficheiro,
    "listar_ficheiros": listar_ficheiros,
    "procurar_texto": procurar_texto,
    "correr_ruff": correr_ruff,
    "ler_varios_ficheiros": ler_varios_ficheiros,
    "pesquisar_web": pesquisar_web,
    "listar_simbolos": listar_simbolos,
}
