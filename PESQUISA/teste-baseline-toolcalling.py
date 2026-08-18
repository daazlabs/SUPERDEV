"""
B4 — baseline de "schema-correct rate" do tool-calling actual do
SUPERLLMLOCAL (qwen3.5:9b via Ollama), método da secção 4.2 do
relatorio-mercado.md: por cada pedido que devia gerar UMA chamada de
ferramenta específica, medir se o modelo (a) chamou a ferramenta certa
e (b) os argumentos validam contra o schema dela (chaves obrigatórias
presentes, tipos certos). Corre N repetições por caso para dar uma
taxa, não um sim/não de uma amostra só.

Reaproveita agent.ollama_chat() a sério — mesmo config.OPTIONS, mesmo
THINK, mesmo tools.TOOL_DEFS que o agente usa em produção. Não passa
pelo ciclo completo de agent.responder() (memória/destilação) de
propósito: queremos isolar só a decisão de tool-calling do modelo, não
o resto do pipeline.

Uso: python3 PESQUISA/teste-baseline-toolcalling.py
Escreve o relatório incrementalmente em PESQUISA/baseline-schema-correct.md
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import tools

REPETICOES = 5

RELATORIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline-schema-correct.md")

SYSTEM = (
    "You are SUPERLLMLOCAL, an expert programming agent. "
    "You have tools available — use one when the request needs it."
)

# Cada caso: pergunta, ferramenta esperada (None = não devia chamar
# nenhuma), chaves obrigatórias esperadas nos argumentos (para
# validar contra o schema real de tools.TOOL_DEFS).
CASOS = [
    {
        "id": "ler_ficheiro",
        "pergunta": "Lê o ficheiro /mnt/sovereign/superllmlocal/config.py e diz-me quantas linhas tem.",
        "ferramenta_esperada": "ler_ficheiro",
        "chaves_obrigatorias": ["caminho"],
    },
    {
        "id": "listar_ficheiros",
        "pergunta": "O que há na pasta /mnt/sovereign/superllmlocal/?",
        "ferramenta_esperada": "listar_ficheiros",
        "chaves_obrigatorias": ["caminho"],
    },
    {
        "id": "procurar_texto",
        "pergunta": "Procura o texto 'OLLAMA_HOST' no ficheiro /mnt/sovereign/superllmlocal/config.py",
        "ferramenta_esperada": "procurar_texto",
        "chaves_obrigatorias": ["caminho", "termo"],
    },
    {
        "id": "correr_ruff",
        "pergunta": (
            "Verifica se este código Python está bem escrito, usa o "
            "linter: def soma(a, b):\n    return a+b"
        ),
        "ferramenta_esperada": "correr_ruff",
        "chaves_obrigatorias": ["codigo"],
    },
    {
        "id": "ler_varios_ficheiros",
        "pergunta": (
            "Lê os ficheiros /mnt/sovereign/superllmlocal/config.py e "
            "/mnt/sovereign/superllmlocal/agent.py, os dois."
        ),
        "ferramenta_esperada": "ler_varios_ficheiros",
        "chaves_obrigatorias": ["caminhos"],
    },
    {
        "id": "pesquisar_web",
        "pergunta": "Pesquisa na web quais são as últimas notícias sobre o modelo Qwen 3.5.",
        "ferramenta_esperada": "pesquisar_web",
        "chaves_obrigatorias": ["query"],
    },
    {
        "id": "controlo_negativo_1",
        "pergunta": "Quanto é 2+2?",
        "ferramenta_esperada": None,
        "chaves_obrigatorias": [],
    },
    {
        "id": "controlo_negativo_2",
        "pergunta": "Explica numa frase o que é uma API REST.",
        "ferramenta_esperada": None,
        "chaves_obrigatorias": [],
    },
]


def validar(tool_calls, esperado, chaves_obrigatorias):
    """Devolve (classe, detalhe) — classe é uma de:
    CORRECTO / FERRAMENTA_ERRADA / ARGS_INVALIDOS / SEM_CHAMADA /
    CHAMADA_INESPERADA."""
    if esperado is None:
        if not tool_calls:
            return "CORRECTO", "não chamou nenhuma ferramenta, como esperado"
        return "CHAMADA_INESPERADA", f"chamou {tool_calls[0]['function']['name']} sem precisar"

    if not tool_calls:
        return "SEM_CHAMADA", "não chamou nenhuma ferramenta quando devia"

    nome = tool_calls[0]["function"]["name"]
    if nome != esperado:
        return "FERRAMENTA_ERRADA", f"chamou {nome}, esperava-se {esperado}"

    args_raw = tool_calls[0]["function"]["arguments"]
    try:
        args = args_raw if isinstance(args_raw, dict) else json.loads(args_raw)
    except (json.JSONDecodeError, TypeError) as e:
        return "ARGS_INVALIDOS", f"argumentos não são JSON válido: {e!r} — bruto: {args_raw!r}"

    faltam = [k for k in chaves_obrigatorias if k not in args]
    if faltam:
        return "ARGS_INVALIDOS", f"faltam chaves obrigatórias: {faltam} — args: {args}"

    return "CORRECTO", f"args: {args}"


def main():
    with open(RELATORIO, "w") as f:
        f.write("# B4 — baseline de schema-correct rate (tool-calling), qwen3.5:9b\n\n")
        f.write(
            f"> Método: secção 4.2 de `relatorio-mercado.md`. "
            f"{REPETICOES} repetições por caso, `config.OPTIONS`/`config.THINK`/"
            f"`tools.TOOL_DEFS` reais (via `agent.ollama_chat`), não isolado. "
            f"Escrito incrementalmente.\n\n"
        )
        f.write("| Caso | Repetição | Classe | Detalhe | Tempo (s) |\n")
        f.write("|---|---|---|---|---|\n")

    resumo = {}
    for caso in CASOS:
        acertos = 0
        detalhes_caso = []
        for i in range(1, REPETICOES + 1):
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": caso["pergunta"]},
            ]
            t0 = time.time()
            try:
                mensagem, _done = agent.ollama_chat(messages, ferramentas=tools.TOOL_DEFS)
                tempo = time.time() - t0
                tool_calls = mensagem.get("tool_calls") or []
                classe, detalhe = validar(
                    tool_calls, caso["ferramenta_esperada"], caso["chaves_obrigatorias"]
                )
            except Exception as e:  # nunca deixar 1 falha parar o resto do teste
                tempo = time.time() - t0
                classe, detalhe = "ERRO", repr(e)

            if classe == "CORRECTO":
                acertos += 1
            detalhes_caso.append((i, classe, detalhe, tempo))

            with open(RELATORIO, "a") as f:
                f.write(
                    f"| {caso['id']} | {i}/{REPETICOES} | {classe} | "
                    f"{detalhe.replace('|', chr(92)+'|')} | {tempo:.1f} |\n"
                )
            print(f"[{caso['id']} {i}/{REPETICOES}] {classe} ({tempo:.1f}s) — {detalhe}")

        resumo[caso["id"]] = (acertos, REPETICOES)

    with open(RELATORIO, "a") as f:
        f.write("\n## Resumo\n\n")
        f.write("| Caso | Taxa correcta |\n|---|---|\n")
        for caso_id, (acertos, total) in resumo.items():
            f.write(f"| {caso_id} | {acertos}/{total} ({100*acertos/total:.0f}%) |\n")
        total_acertos = sum(a for a, _ in resumo.values())
        total_geral = sum(t for _, t in resumo.values())
        f.write(
            f"\n**Total: {total_acertos}/{total_geral} "
            f"({100*total_acertos/total_geral:.0f}%)**\n"
        )

    print("\nRelatório escrito em", RELATORIO)


if __name__ == "__main__":
    main()
