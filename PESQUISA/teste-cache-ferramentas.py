"""
Teste do cache de chamadas repetidas dentro da mesma troca (13 Ago
2026, ver HISTORICO.md e o comentário junto a
agent._chamar_ferramenta_com_cache).

Achado real motivador: no incidente do DAAZPRIME, 2 das 4 voltas de
ferramentas gastas foram cópias EXACTAS de voltas anteriores
(ler_ficheiro com o mesmo caminho e o mesmo "início" duas vezes cada)
— o modelo nunca chegou a pesquisar na web porque gastou metade do
orçamento a repetir-se.

Dois testes, por camadas:
  1. DETERMINÍSTICO (mock) — não depende do modelo nem da Ollama,
     corre em milissegundos. Substitui tools.FUNCOES por uma função
     falsa que conta quantas vezes é chamada a sério, confirma que a
     2ª chamada com os MESMOS argumentos não volta a invocá-la, e que
     o resultado vem com a etiqueta de repetição.
  2. REAL — usa tools.ler_ficheiro a sério (lê um ficheiro deste
     projecto), confirma que funciona igual com uma ferramenta real,
     não só com um mock.

Uso: python3 PESQUISA/teste-cache-ferramentas.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import tools

MARCADOR_REPETICAO = "já chamaste esta ferramenta com estes"


def teste_deterministico() -> bool:
    print("=== 1. Determinístico (mock, sem Ollama) ===")
    chamadas_reais = []

    def _fake(caminho: str) -> str:
        chamadas_reais.append(caminho)
        return f"[conteúdo falso de {caminho}]"

    original = tools.FUNCOES.get("ler_ficheiro")
    tools.FUNCOES["ler_ficheiro"] = _fake
    try:
        cache = {}
        args = {"caminho": "/qualquer/coisa.py"}

        r1 = agent._chamar_ferramenta_com_cache("ler_ficheiro", args, cache)
        r2 = agent._chamar_ferramenta_com_cache("ler_ficheiro", dict(args), cache)  # dict novo, mesmo conteúdo
        r3 = agent._chamar_ferramenta_com_cache("ler_ficheiro", {"caminho": "/outro/ficheiro.py"}, cache)
    finally:
        tools.FUNCOES["ler_ficheiro"] = original

    ok_execucoes = chamadas_reais == ["/qualquer/coisa.py", "/outro/ficheiro.py"]
    print(f"{'OK' if ok_execucoes else 'FALHOU'} — função real só executada 2x (1ª vez de cada args): {chamadas_reais}")

    ok_r1_normal = MARCADOR_REPETICAO not in r1
    print(f"{'OK' if ok_r1_normal else 'FALHOU'} — 1ª chamada sem etiqueta de repetição")

    ok_r2_marcado = MARCADOR_REPETICAO in r2 and "[conteúdo falso de /qualquer/coisa.py]" in r2
    print(f"{'OK' if ok_r2_marcado else 'FALHOU'} — 2ª chamada (repetida) tem a etiqueta E o resultado real")

    ok_r3_normal = MARCADOR_REPETICAO not in r3
    print(f"{'OK' if ok_r3_normal else 'FALHOU'} — 3ª chamada (argumentos diferentes) sem etiqueta")

    return ok_execucoes and ok_r1_normal and ok_r2_marcado and ok_r3_normal


def teste_real() -> bool:
    print("\n=== 2. Real (tools.ler_ficheiro a sério) ===")
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py")
    cache = {}
    args = {"caminho": caminho}

    r1 = agent._chamar_ferramenta_com_cache("ler_ficheiro", args, cache)
    r2 = agent._chamar_ferramenta_com_cache("ler_ficheiro", dict(args), cache)

    # "OLLAMA_HOST" está perto do topo do ficheiro real, bem dentro do
    # LIMITE_CARACTERES=8000 da leitura por omissão — ao contrário da
    # 1ª versão deste teste, que assumia "CORE_IDENTITY" (byte 11349,
    # fora do que ler_ficheiro devolve sem "início") e falhava por
    # engano do teste, não da função.
    ok_conteudo_real = "OLLAMA_HOST" in r1
    print(f"{'OK' if ok_conteudo_real else 'FALHOU'} — 1ª chamada devolveu conteúdo real do ficheiro")

    ok_repeticao = MARCADOR_REPETICAO in r2 and "OLLAMA_HOST" in r2
    print(f"{'OK' if ok_repeticao else 'FALHOU'} — 2ª chamada repetida, com etiqueta, mantendo o conteúdo real")

    return ok_conteudo_real and ok_repeticao


if __name__ == "__main__":
    ok = teste_deterministico() and teste_real()
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
