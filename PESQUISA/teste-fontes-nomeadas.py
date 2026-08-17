"""
Teste da verificação de fontes nomeadas sem URL (16 Ago 2026, ver
HISTORICO.md e o comentário junto a verificacoes.verificar_fontes_nomeadas).

Extensão directa de _verificar_urls_citados (13 Ago 2026) para o caso
adjacente: uma fonte citada por NOME ("segundo a CMVM...", "de acordo
com o Fórum X...") sem link nenhum a acompanhar — o incidente real de
13 Ago (fórum/banco/CMVM inventados) tinha sempre URL, por isso ficou
coberto pela verificação anterior; isto fecha a versão sem URL do
mesmo padrão, ainda não vista ao vivo.

Âmbito deliberadamente estreito, mesma disciplina do resto do plano:
só actua em frases com uma pista de citação explícita, e só em nomes
de 2+ palavras ou siglas de 2-6 letras — não tenta apanhar invenção
difusa em prosa livre (ver a conversa com o utilizador de 16 Ago
sobre essa distinção).

Quatro testes:
  1. Determinístico — fonte real (aparece no texto das ferramentas)
     não dispara; fonte inventada (sigla e nome próprio) dispara;
     frase sem pista de citação não dispara mesmo com nome ausente;
     nome de 1 palavra só não dispara (âmbito deliberado).
  2. Reprodução sintética do padrão do incidente real, mas sem URL
     (a variante ainda não vista ao vivo) — "segundo a CMVM" sem
     nenhuma pesquisa a confirmar CMVM nesta troca.
  3. Regressão — caso trivial ao vivo (via agent.responder(), servidor
     real) não deve disparar.
  4. Regressão — caso de pesquisa real com fonte legítima citada não
     deve disparar por engano.

Uso: python3 PESQUISA/teste-fontes-nomeadas.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import verificacoes

MARCADOR = "aviso de fontes não confirmadas"


def teste_deterministico() -> bool:
    print("=== 1. Determinístico ===")
    mensagens = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "pesquisa sobre X"},
        {"role": "tool", "content": "Resultado real do Banco de Portugal sobre inflação."},
    ]

    r1 = verificacoes.verificar_fontes_nomeadas(
        "Segundo o Banco de Portugal, a inflação desceu.", mensagens)
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — fonte real citada, não deve disparar")

    r2 = verificacoes.verificar_fontes_nomeadas(
        "Segundo a CMVM, o produto foi suspenso.", mensagens)
    ok2 = MARCADOR in r2
    print(f"{'OK' if ok2 else 'FALHOU'} — sigla inventada (CMVM não apareceu nesta troca), deve disparar")

    r3 = verificacoes.verificar_fontes_nomeadas(
        "De acordo com o Fórum Investidores Unidos, o produto é mau.", mensagens)
    ok3 = MARCADOR in r3
    print(f"{'OK' if ok3 else 'FALHOU'} — nome próprio inventado, deve disparar")

    r4 = verificacoes.verificar_fontes_nomeadas(
        "A CMVM não foi mencionada em lado nenhum desta troca.", mensagens)
    ok4 = MARCADOR not in r4
    print(f"{'OK' if ok4 else 'FALHOU'} — sem pista de citação, não deve disparar mesmo com sigla ausente")

    r5 = verificacoes.verificar_fontes_nomeadas(
        "Segundo Portugal, a inflação desceu.", mensagens)
    ok5 = MARCADOR not in r5
    print(f"{'OK' if ok5 else 'FALHOU'} — nome de 1 palavra só, fora do âmbito deliberado, não deve disparar")

    return ok1 and ok2 and ok3 and ok4 and ok5


def teste_padrao_sem_url() -> bool:
    print("\n=== 2. Reprodução sintética do padrão real, variante sem URL ===")
    # Mesma estrutura do incidente real do DAAZPRIME (ver
    # teste-verificacao-urls.py) — 3 queries reais, sem resultados,
    # mas agora a resposta fabricada cita a fonte só pelo nome, sem
    # link (a variante que a verificação de URLs sozinha não apanha).
    mensagens = [{"role": "system", "content": agent.config.CORE_IDENTITY},
                 {"role": "user", "content": "pedido do DAAZPRIME (ver HISTORICO.md)"}]
    for query in (
        "PPR vale a pena tendo em conta a inflação Portugal 2026",
        "PPR vale a pena inflação Google AI Overview",
    ):
        mensagens.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "pesquisar_web", "arguments": {"query": query}}}
        ]})
        mensagens.append({"role": "tool", "content": "[SEM RESULTADOS] A pesquisa não devolveu nada de útil."})

    resposta_fabricada = (
        "Segundo a CMVM, há reclamações registadas sobre este PPR em 2026, "
        "e de acordo com o Fórum Investidores Unidos o produto tem mau retorno."
    )
    resultado = verificacoes.verificar_fontes_nomeadas(resposta_fabricada, mensagens)
    ok = MARCADOR in resultado
    print(f"{'OK' if ok else 'FALHOU'} — fontes fabricadas sem URL disparam o aviso")
    return ok


def teste_regressao_trivial() -> bool:
    print("\n=== 3. Regressão — trivial ao vivo ===")
    r1 = agent.responder("Quanto é 7 vezes 6?")
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — trivial, sem fonte citada, sem disparo")
    return ok1


def teste_regressao_fonte_legitima() -> bool:
    print("\n=== 4. Regressão — fonte legítima não deve disparar por engano ===")
    mensagens = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "o que diz a Comissão Europeia sobre isto?"},
        {"role": "tool", "content": "A Comissão Europeia publicou um relatório em 2026 sobre o tema."},
    ]
    r1 = verificacoes.verificar_fontes_nomeadas(
        "Segundo a Comissão Europeia, o relatório de 2026 confirma isto.", mensagens)
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — fonte legítima (presente no texto lido), não deve disparar")
    return ok1


if __name__ == "__main__":
    ok = (
        teste_deterministico()
        and teste_padrao_sem_url()
        and teste_regressao_trivial()
        and teste_regressao_fonte_legitima()
    )
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
