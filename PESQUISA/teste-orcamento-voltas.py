"""
Teste do orçamento dinâmico de voltas de ferramentas (13 Ago 2026, ver
HISTORICO.md e o comentário junto a agent._calcular_orcamento_voltas).

Determinístico (sem Ollama) — confirma que _calcular_orcamento_voltas
devolve VOLTAS_BASE (5) para 0-1 categorias e cresce
VOLTAS_POR_CATEGORIA_EXTRA (3) por cada categoria extra, com tecto em
VOLTAS_TECTO_ABSOLUTO (12).

ACHADO HONESTO AO TESTAR AO VIVO, documentado aqui em vez de escondido
(não coberto por este script, que é só a parte determinística — ver
HISTORICO.md para o detalhe completo): repetir o pedido exacto do
incidente do DAAZPRIME (2 categorias: ficheiro+web) com o orçamento
correcto de 8 voltas em vez de 5 NÃO foi suficiente para o modelo
chegar a chamar pesquisar_web — continuou preso a reler os mesmos 2
ficheiros locais (4 das 7 voltas de leitura tiveram pelo menos uma
repetição exacta, apesar do cache de 13 Ago já estar activo). Ou seja:
mais orçamento sozinho não resolve este caso concreto — é uma
limitação de PLANEAMENTO do modelo (qwen3.5:9b), não de falta de
tempo/voltas. O Nível 1.5 continuou a apanhar a fabricação resultante
em todas as tentativas testadas (3/3 até agora), por isso o utilizador
nunca ficou sem aviso, mesmo quando a tarefa em si não foi cumprida.

Uso: python3 PESQUISA/teste-orcamento-voltas.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent

CASOS = [
    ("Quanto é 7 vezes 6?", "", 5, "trivial, 0 categorias"),
    ("Lê o ficheiro config.py", "", 5, "1 categoria (ficheiro)"),
    ("Pesquisa na web as últimas notícias", "", 5, "1 categoria (web)"),
    (
        "Lê o ficheiro BRIEFING.md e depois pesquisa na web sobre isto",
        "",
        8,
        "2 categorias (ficheiro+web) — o padrão real do incidente do DAAZPRIME",
    ),
    (
        "Lê o código, corre o linter, e pesquisa online notícias sobre o assunto",
        "",
        11,
        "3 categorias (ficheiro+codigo+web)",
    ),
]


def correr() -> bool:
    ok = True
    for pedido, contexto, esperado, nota in CASOS:
        obtido = agent._calcular_orcamento_voltas(pedido, contexto)
        certo = obtido == esperado
        ok &= certo
        print(f"{'OK' if certo else 'FALHOU'} [{nota}] esperado={esperado} obtido={obtido}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if correr() else 1)
