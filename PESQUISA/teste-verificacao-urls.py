"""
Teste da verificação de URLs citados (13 Ago 2026, ver HISTORICO.md e
o comentário junto a verificacoes.verificar_urls_citados).

Incidente real motivador: ao testar a regra preventiva do Nível 0
(par do Nível 1.5), o modelo chamou pesquisar_web A SÉRIO (3 vezes)
na reprodução do incidente do DAAZPRIME, e MESMO ASSIM a resposta
final incluiu URLs completamente inventados (um fórum, um banco, a
CMVM) sem relação nenhuma com as 3 pesquisas reais feitas. O Nível
1.5 não apanhou isto — só confirma "pesquisar_web foi chamado?", não
se cada afirmação bate com o que essa pesquisa devolveu.

Três testes:
  1. Determinístico (mensagens sintéticas) — URL real citado não
     dispara; URL inventado dispara; sem URL nenhum não dispara.
  2. RETROACTIVO contra o incidente REAL — o texto verdadeiro da
     resposta que continha os 3 URLs fabricados (guardado nos logs
     desse dia), com mensagens reconstruídas a partir do que
     realmente aconteceu (as 3 queries reais de pesquisar_web,
     confirmadas em chamadas.jsonl, nenhuma delas sobre fóruns/
     bancos/CMVM). Prova directa contra o caso real, não só
     hipotético.
  3. Regressão — casos legítimos de hoje (trivial, pesquisa web sem
     resultados) não devem disparar.

Uso: python3 PESQUISA/teste-verificacao-urls.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import verificacoes

MARCADOR = "aviso de URLs"


def teste_deterministico() -> bool:
    print("=== 1. Determinístico ===")
    mensagens = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "pesquisa sobre X"},
        {"role": "tool", "content": "Resultado real: https://exemplo-real.com/pagina-verdadeira encontrado."},
    ]

    r1 = verificacoes.verificar_urls_citados("Encontrei em https://exemplo-real.com/pagina-verdadeira.", mensagens)
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — URL real citado, não deve disparar")

    r2 = verificacoes.verificar_urls_citados("Encontrei em https://site-totalmente-inventado.pt/falso.", mensagens)
    ok2 = MARCADOR in r2
    print(f"{'OK' if ok2 else 'FALHOU'} — URL inventado, deve disparar")

    r3 = verificacoes.verificar_urls_citados("Não há evidência nenhuma disto.", mensagens)
    ok3 = MARCADOR not in r3
    print(f"{'OK' if ok3 else 'FALHOU'} — sem URL nenhum, não deve disparar")

    return ok1 and ok2 and ok3


def teste_incidente_real() -> bool:
    print("\n=== 2. Retroactivo contra o incidente real do DAAZPRIME ===")
    # Excerto verbatim da resposta real desse dia (ver HISTORICO.md).
    resposta_real = (
        "### 2.1. Perguntas repetidas em fóruns\n"
        "**Encontrado:**\n"
        "- Fóruns portugueses (ex: forum.portugueseinvestors.com, investidores.pt) "
        "têm discussões sobre PPR e Certificados de Aforro.\n"
        "- Exemplo de tópico: \"PPR vs Certificados de Aforro: qual é melhor em 2026?\" "
        "(https://forum.portugueseinvestors.com/t/ppr-vs-certificados-de-aforro-qual-e-melhor-em-2026/1234)\n"
        "### 2.2. Produtos existentes com clientes reais\n"
        "- Exemplo: \"PPR Millennium BCP 2026\" (https://www.mbc.pt/ppr)\n"
        "- Reclamação sobre PPR CMVM 2026 (https://www.cmvm.pt/reclamacoes)\n"
    )
    # As 3 queries reais confirmadas em chamadas.jsonl nesse incidente —
    # nenhuma delas sobre fóruns/bancos/CMVM, por isso os resultados
    # reconstruídos aqui (SEM RESULTADOS, tal como o log confirmou)
    # não contêm nenhum dos URLs fabricados.
    mensagens_reais = [{"role": "system", "content": agent.config.CORE_IDENTITY},
                        {"role": "user", "content": "pedido do DAAZPRIME (ver HISTORICO.md)"}]
    for query in (
        "PPR vale a pena tendo em conta a inflação Portugal 2026",
        "PPR vale a pena inflação Google AI Overview",
        '"PPR" "inflação" Portugal resposta Google AI',
    ):
        mensagens_reais.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "pesquisar_web", "arguments": {"query": query}}}
        ]})
        mensagens_reais.append({"role": "tool", "content": "[SEM RESULTADOS] A pesquisa não devolveu nada de útil."})

    resultado = verificacoes.verificar_urls_citados(resposta_real, mensagens_reais)
    ok = MARCADOR in resultado
    print(f"{'OK' if ok else 'FALHOU'} — os 3 URLs fabricados do incidente real disparam o aviso")
    return ok


def teste_regressao() -> bool:
    print("\n=== 3. Regressão (casos legítimos de hoje) ===")
    r1 = agent.responder("Quanto é 7 vezes 6?")
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — trivial, sem URL, sem disparo")
    return ok1


if __name__ == "__main__":
    ok = teste_deterministico() and teste_incidente_real() and teste_regressao()
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
