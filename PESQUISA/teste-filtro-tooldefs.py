"""
Teste do filtro mecânico tools.provavelmente_precisa_ferramentas
(13 Ago 2026, ver HISTORICO.md) — antes de confiar nele para poupar
os ~1000 tokens de TOOL_DEFS por pedido, confirma que continua a
mandar "sim" nos mesmos 6 casos positivos do B4 (um por ferramenta,
ver PESQUISA/teste-baseline-toolcalling.py) e "não" nos 2 controlos
negativos — mais alguns casos novos (listar_simbolos, que não
existia ainda quando o B4 foi escrito, e continuação de conversa sem
palavra-chave própria).

Verificação pura de string matching — não chama a Ollama, não custa
nada, corre em milissegundos. Uso: python3 PESQUISA/teste-filtro-tooldefs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools

# Mesmos 8 casos do B4 (ver teste-baseline-toolcalling.py) + extras.
CASOS = [
    ("ler_ficheiro (B4)", "Lê o ficheiro /mnt/sovereign/superllmlocal/config.py e diz-me quantas linhas tem.", True),
    ("listar_ficheiros (B4)", "O que há na pasta /mnt/sovereign/superllmlocal/?", True),
    ("procurar_texto (B4)", "Procura o texto 'OLLAMA_HOST' no ficheiro /mnt/sovereign/superllmlocal/config.py", True),
    ("correr_ruff (B4)", "Verifica se este código Python está bem escrito, usa o linter: def soma(a, b):\n    return a+b", True),
    ("ler_varios_ficheiros (B4)", "Lê os ficheiros /mnt/sovereign/superllmlocal/config.py e /mnt/sovereign/superllmlocal/agent.py, os dois.", True),
    ("pesquisar_web (B4)", "Pesquisa na web quais são as últimas notícias sobre o modelo Qwen 3.5.", True),
    ("controlo_negativo_1 (B4)", "Quanto é 2+2?", False),
    ("controlo_negativo_2 (B4)", "Explica numa frase o que é uma API REST.", False),
    ("listar_simbolos (novo, pós-B4)", "O que há neste ficheiro, que funções e classes tem o tools.py?", True),
    ("trivial 1 (novo)", "Bom dia! Como estás?", False),
    ("trivial 2 (novo)", "Traduz 'good morning' para português.", False),
    ("trivial 3 (novo)", "Escreve um poema curto sobre o mar.", False),
]

# Continuação: pedido sozinho não tem palavra-chave própria, só faz
# sentido com o contexto da troca anterior.
CASOS_CONTEXTO = [
    (
        "'continua' sozinho, é a própria palavra-chave",
        "continua",
        "",
        True,
    ),
    (
        "pedido sem keyword própria, mas contexto fala de ficheiro",
        "podes detalhar mais?",
        "Lê o ficheiro config.py e diz-me o que encontras.",
        True,
    ),
    (
        "mesmo pedido, sem contexto nenhum — nem ele nem o contexto têm keyword",
        "podes detalhar mais?",
        "",
        False,
    ),
]


def correr():
    falhas = 0
    print("=== Casos simples (pedido isolado) ===")
    for nome, pergunta, esperado in CASOS:
        obtido = tools.provavelmente_precisa_ferramentas(pergunta)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'OK ' if ok else 'FALHOU'} [{nome}] esperado={esperado} obtido={obtido} — {pergunta[:60]!r}")

    print("\n=== Casos com contexto (troca anterior) ===")
    for nome, pergunta, contexto, esperado in CASOS_CONTEXTO:
        obtido = tools.provavelmente_precisa_ferramentas(pergunta, contexto)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'OK ' if ok else 'FALHOU'} [{nome}] esperado={esperado} obtido={obtido}")

    print(f"\n{len(CASOS) + len(CASOS_CONTEXTO) - falhas}/{len(CASOS) + len(CASOS_CONTEXTO)} casos correctos.")
    return falhas == 0


if __name__ == "__main__":
    sys.exit(0 if correr() else 1)
