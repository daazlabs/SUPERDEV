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
"""
import fnmatch
import os

# Limite simples para não rebentar a janela de contexto com um
# ficheiro enorme.
LIMITE_CARACTERES = 8000

# Limites para as ferramentas de listagem/procura — mesma lógica do
# LIMITE_CARACTERES: cortar de forma clara em vez de rebentar o
# contexto ou correr para sempre num diretório grande.
LIMITE_ENTRADAS_LISTAR = 200
LIMITE_RESULTADOS_PROCURAR = 40
LIMITE_FICHEIROS_PROCURADOS = 500


def ler_ficheiro(caminho: str) -> str:
    """Lê um ficheiro de texto do disco. Falha de forma clara se não
    existir ou não for legível — nunca inventa conteúdo."""
    caminho = os.path.abspath(os.path.expanduser(caminho))
    if not os.path.isfile(caminho):
        return f"[ERRO] Ficheiro não encontrado: {caminho}"
    try:
        with open(caminho, "r", errors="replace") as f:
            conteudo = f.read()
    except Exception as e:
        return f"[ERRO] Não foi possível ler o ficheiro: {e}"

    if len(conteudo) > LIMITE_CARACTERES:
        conteudo = (
            conteudo[:LIMITE_CARACTERES]
            + f"\n...[cortado — ficheiro tem {len(conteudo)} caracteres, "
              f"só os primeiros {LIMITE_CARACTERES} foram lidos]"
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
            "description": "Reads the content of a text file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Absolute path of the file to read",
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
]

# Mapa nome -> função real, para executar o que o modelo pedir.
FUNCOES = {
    "ler_ficheiro": ler_ficheiro,
    "listar_ficheiros": listar_ficheiros,
    "procurar_texto": procurar_texto,
}
