"""
Diagnóstico agregado dos logs (13 Ago 2026, ver HISTORICO.md) — 4ª de
4 sugestões "sem subir de nível" pedidas pelo utilizador. Motivação:
todo o trabalho de hoje (filtro de TOOL_DEFS, Nível 1.5, cache de
ferramentas repetidas, orçamento de voltas dinâmico) foi analisado
escarafunchando chamadas.jsonl/conversas.jsonl à mão, uma consulta
Python de cada vez — útil para um incidente à vez, mas não dá visão
de conjunto sobre o que está a acontecer nos pedidos reais.

Junta chamadas.jsonl (uma linha por VOLTA — cada ida-e-volta à Ollama)
com conversas.jsonl (uma linha por PEDIDO completo do utilizador, só
existe na fase de testes — ver ver_conversa.py) para agrupar as
chamadas por TROCA: um pedido do utilizador pode gerar várias
chamadas (uma por volta de ferramentas), e só ao nível da troca é que
fazem sentido perguntas como "quantas voltas usou", "repetiu alguma
ferramenta", "disparou algum aviso" — cada linha de chamadas.jsonl,
sozinha, não sabe nada disto.

Uso:
  python3 ver_diagnostico.py            # resumo agregado
  python3 ver_diagnostico.py --detalhe  # + lista de trocas com sinal a rever
"""
import json
import os
import sys

import config


def _carregar(caminho: str) -> list[dict]:
    if not os.path.isfile(caminho):
        return []
    with open(caminho) as f:
        return [json.loads(linha) for linha in f if linha.strip()]


# Tecto generoso para o tamanho de UMA troca (13 Ago 2026) — nenhuma
# troca vista até agora, mesmo com 8 voltas de ferramentas reais,
# passou de ~2 minutos. Existe só para a 1ª troca de conversas.jsonl,
# que de outra forma não tinha limite inferior nenhum: BUG REAL
# apanhado ao testar — sem isto, a 1ª troca "herdava" TODAS as
# chamadas de chamadas.jsonl anteriores ao início de conversas.jsonl
# (que começou a gravar depois, 9 Ago), incluindo semanas de chamadas
# de testes antigos sem relação nenhuma — um "olá" trivial aparecia
# com "149 voltas". Não é protecção contra troca real longa (essas já
# têm o próprio MAX_VOLTAS_FERRAMENTAS/orçamento a limitar), é só para
# não confundir "não sei onde começa" com "começa no topo do ficheiro".
LIMIAR_MAX_TROCA_SEGUNDOS = 900


def _agrupar_por_troca(chamadas: list[dict], conversas: list[dict]) -> list[dict]:
    """Cada conversa (pedido+resposta final) marca o FIM de uma troca
    — junta a ela todas as chamadas com timestamp entre o fim da
    troca anterior (ou LIMIAR_MAX_TROCA_SEGUNDOS antes, o que for mais
    recente) e o seu próprio timestamp. Trocas sem par em
    conversas.jsonl (gravação desligada, ou troca ainda a meio ao
    correr isto) ficam de fora — sem o texto da resposta não dá para
    saber se algum aviso disparou."""
    conversas_ordenadas = sorted(conversas, key=lambda d: d["timestamp"])
    chamadas_ordenadas = sorted(chamadas, key=lambda d: d["timestamp"])

    trocas = []
    inicio_troca_anterior = None
    i = 0
    for conversa in conversas_ordenadas:
        fim = conversa["timestamp"]
        tecto_inferior = fim - LIMIAR_MAX_TROCA_SEGUNDOS
        inicio = max(tecto_inferior, inicio_troca_anterior) if inicio_troca_anterior is not None else tecto_inferior
        do_grupo = []
        while i < len(chamadas_ordenadas) and chamadas_ordenadas[i]["timestamp"] <= fim:
            if chamadas_ordenadas[i]["timestamp"] > inicio:
                do_grupo.append(chamadas_ordenadas[i])
            i += 1
        trocas.append({"conversa": conversa, "chamadas": do_grupo})
        inicio_troca_anterior = fim
    return trocas


def _tem_ferramenta_repetida(chamadas: list[dict]) -> bool:
    """Mesma noção de 'repetição' do cache em agent.py — (nome,
    argumentos) já visto antes nesta troca."""
    vistas = set()
    for c in chamadas:
        for fer in c.get("ferramentas_pedidas") or []:
            chave = (fer["nome"], json.dumps(fer["args"], sort_keys=True, ensure_ascii=False))
            if chave in vistas:
                return True
            vistas.add(chave)
    return False


def analisar() -> dict:
    chamadas = _carregar(config.LOG_FILE)
    conversas = _carregar(config.CONVERSATION_LOG_FILE)
    trocas = _agrupar_por_troca(chamadas, conversas)

    resumo = {
        "total_trocas": len(trocas),
        "bateu_limite_voltas": 0,
        "aviso_nivel1": 0,
        "aviso_nivel1_5": 0,
        "aviso_urls": 0,
        "aviso_fontes_nomeadas": 0,
        "ferramenta_repetida": 0,
        "filtro_anexou_tools": 0,
        "filtro_poupou_tools": 0,
        "tokens_entrada_totais": 0,
        "tokens_saida_totais": 0,
        "tempo_total_s": 0.0,
        "problematicas": [],  # só preenchido para --detalhe
    }

    for t in trocas:
        resposta = t["conversa"]["resposta"]
        pedido = t["conversa"]["pedido"]
        chamadas_desta_troca = t["chamadas"]
        tokens_entrada = sum(c.get("prompt_eval_count") or 0 for c in chamadas_desta_troca)
        tokens_saida = sum(c.get("eval_count") or 0 for c in chamadas_desta_troca)
        tempo = sum(c.get("tempo_medido_end_to_end_s") or 0 for c in chamadas_desta_troca)
        resumo["tokens_entrada_totais"] += tokens_entrada
        resumo["tokens_saida_totais"] += tokens_saida
        resumo["tempo_total_s"] += tempo

        bateu_limite = "atingi o limite de voltas" in resposta
        tem_n1 = "verificação automática de constantes citadas" in resposta
        tem_n15 = "Nível 1.5" in resposta
        # Avisos de 13/16 Ago (ver HISTORICO.md) — não entravam ainda
        # neste resumo, ficava-se cego a eles a partir de agora.
        tem_urls = "aviso de URLs não confirmados" in resposta
        tem_fontes = "aviso de fontes não confirmadas" in resposta
        repetida = _tem_ferramenta_repetida(chamadas_desta_troca)
        # filtro do TOOL_DEFS (13 Ago) só existe nas trocas de hoje em
        # diante — trocas mais antigas não têm este campo (None),
        # ficam de fora desta contagem específica de propósito.
        filtro = chamadas_desta_troca[0].get("filtro_ferramentas_pedido") if chamadas_desta_troca else None

        resumo["bateu_limite_voltas"] += int(bateu_limite)
        resumo["aviso_nivel1"] += int(tem_n1)
        resumo["aviso_nivel1_5"] += int(tem_n15)
        resumo["aviso_urls"] += int(tem_urls)
        resumo["aviso_fontes_nomeadas"] += int(tem_fontes)
        resumo["ferramenta_repetida"] += int(repetida)
        if filtro is True:
            resumo["filtro_anexou_tools"] += 1
        elif filtro is False:
            resumo["filtro_poupou_tools"] += 1

        if bateu_limite or tem_n1 or tem_n15 or tem_urls or tem_fontes or repetida:
            resumo["problematicas"].append({
                "pedido": pedido[:100],
                "voltas": len(chamadas_desta_troca),
                "bateu_limite": bateu_limite,
                "nivel1": tem_n1,
                "nivel1_5": tem_n15,
                "urls": tem_urls,
                "fontes": tem_fontes,
                "repetida": repetida,
            })

    return resumo


def imprimir(resumo: dict, detalhe: bool) -> None:
    total = resumo["total_trocas"]
    if total == 0:
        print("[sem trocas com par em conversas.jsonl — nada para analisar ainda]")
        return

    def pct(n: int) -> str:
        return f"{n}/{total} ({n / total * 100:.0f}%)"

    print(f"=== Diagnóstico de {total} trocas (chamadas.jsonl + conversas.jsonl) ===")
    print(f"Bateram no limite de voltas:          {pct(resumo['bateu_limite_voltas'])}")
    print(f"Aviso Nível 1 (números/constantes):   {pct(resumo['aviso_nivel1'])}")
    print(f"Aviso Nível 1.5 (fundamento zero):    {pct(resumo['aviso_nivel1_5'])}")
    print(f"Aviso URLs não confirmados:           {pct(resumo['aviso_urls'])}")
    print(f"Aviso fontes nomeadas não confirmadas: {pct(resumo['aviso_fontes_nomeadas'])}")
    print(f"Repetiram alguma ferramenta na troca: {pct(resumo['ferramenta_repetida'])}")
    print(f"Filtro TOOL_DEFS anexou ferramentas:  {pct(resumo['filtro_anexou_tools'])}")
    print(f"Filtro TOOL_DEFS poupou (sem tools):  {pct(resumo['filtro_poupou_tools'])}")
    print(f"Tokens de entrada somados:            {resumo['tokens_entrada_totais']}")
    print(f"Tokens de saída somados:              {resumo['tokens_saida_totais']}")
    if total:
        print(f"Tempo médio por troca:                {resumo['tempo_total_s'] / total:.1f}s")

    if detalhe and resumo["problematicas"]:
        print(f"\n=== {len(resumo['problematicas'])} trocas com algum sinal a rever ===")
        for p in resumo["problematicas"]:
            marcas = []
            if p["bateu_limite"]:
                marcas.append("LIMITE")
            if p["nivel1"]:
                marcas.append("N1")
            if p["nivel1_5"]:
                marcas.append("N1.5")
            if p["urls"]:
                marcas.append("URLS")
            if p["fontes"]:
                marcas.append("FONTES")
            if p["repetida"]:
                marcas.append("REPETIU")
            print(f"[{','.join(marcas):<20}] ({p['voltas']} voltas) {p['pedido']!r}")


if __name__ == "__main__":
    imprimir(analisar(), detalhe="--detalhe" in sys.argv)
