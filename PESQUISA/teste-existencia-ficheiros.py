"""
Teste da verificação de existência contraditada por listar_ficheiros
(16 Ago 2026, ver HISTORICO.md) — 2º incidente real da mesma sessão do
utilizador, diferente do anterior (teste-ficheiros-citados.py).

Desta vez o modelo CHAMOU mesmo listar_ficheiros — confirmado
directamente contra a ferramenta (tools.listar_ficheiros), resultado
real sem "utils.py" nem "memoria.py" — e mesmo assim respondeu "Sim,
existem!" a "utils.py e memoria.py existem mesmo?". A verificação
anterior (_verificar_ficheiros_citados) não apanha isto: a resposta
nunca repete os 2 nomes num bloco descritivo, só confirma em prosa
vaga o que o utilizador tinha perguntado.

Cinco testes:
  1. Determinístico — nome ausente da listagem afirmado como existente
     dispara; nome presente na listagem não dispara; "X não existe"
     (negação, afirmação correcta de ausência) não dispara; sem
     listar_ficheiros chamado nesta troca não dispara (nada para
     confirmar).
  2. RETROACTIVO contra o incidente REAL — pedido e resposta verbatim
     ("utils.py e memoria.py existem mesmo?" / "Sim, existem!..."),
     com a listagem real da pasta (tools.listar_ficheiros, ao vivo)
     como resultado da ferramenta — prova directa contra o caso real.
  3. Regressão — a troca #6 da mesma sessão (confusão sobre "está na
     lista"/"não está na lista" para ficheiros REAIS) não deve
     disparar, porque nenhuma afirmação individual aí é falsa.
  4. Regressão — trivial ao vivo.

Uso: python3 PESQUISA/teste-existencia-ficheiros.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import tools
import verificacoes

MARCADOR = "SUPERLLMLOCAL EXISTÊNCIA"


def _mensagens_com_listagem(listagem: str, pedido: str = "existe algum ficheiro X?") -> list:
    return [
        {"role": "system", "content": agent.config.CORE_IDENTITY},
        {"role": "user", "content": pedido},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "listar_ficheiros", "arguments": {"caminho": "/mnt/sovereign/superllmlocal"}}}
        ]},
        {"role": "tool", "content": listagem},
    ]


def teste_deterministico() -> bool:
    print("=== 1. Determinístico ===")
    listagem = "agent.py\nconfig.py\ntools.py\nmemory.py"

    mensagens = _mensagens_com_listagem(listagem, "utils.py existe?")
    r1 = verificacoes.verificar_existencia_ficheiros("Sim, utils.py existe.", mensagens)
    ok1 = MARCADOR in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — nome ausente da listagem, afirmado como existente, deve disparar")

    r2 = verificacoes.verificar_existencia_ficheiros("Sim, agent.py existe.", mensagens)
    ok2 = MARCADOR not in r2
    print(f"{'OK' if ok2 else 'FALHOU'} — nome presente na listagem, não deve disparar")

    r3 = verificacoes.verificar_existencia_ficheiros("Não, utils.py não existe nesta pasta.", mensagens)
    ok3 = MARCADOR not in r3
    print(f"{'OK' if ok3 else 'FALHOU'} — negação (afirmação correcta de ausência), não deve disparar")

    mensagens_sem_listagem = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "utils.py existe?"},
    ]
    r4 = verificacoes.verificar_existencia_ficheiros("Sim, utils.py existe.", mensagens_sem_listagem)
    ok4 = MARCADOR not in r4
    print(f"{'OK' if ok4 else 'FALHOU'} — sem listar_ficheiros chamado nesta troca, não deve disparar")

    return ok1 and ok2 and ok3 and ok4


def teste_incidente_real() -> bool:
    print("\n=== 2. Retroactivo contra o incidente real (16 Ago) ===")
    # Listagem REAL, ao vivo, com os mesmos argumentos que o modelo
    # usou nesse incidente (confirmado em chamadas.jsonl).
    listagem_real = tools.listar_ficheiros("/mnt/sovereign/superllmlocal")
    print(f"(confirmado ao vivo: 'utils.py' na listagem real = {'utils.py' in listagem_real}, "
          f"'memoria.py' na listagem real = {'memoria.py' in listagem_real})")

    mensagens_reais = _mensagens_com_listagem(listagem_real, "utils.py e memoria.py existem mesmo?")
    # Resposta verbatim real (ver logs/conversas.jsonl, ts=1786909848.1)
    # — nunca repete os 2 nomes, só confirma em prosa.
    resposta_real = (
        "Sim, existem! Na verdade, há dois ficheiros de memória:\n\n"
        "**memory.py** (2.891 caracteres): implementa RAG mínimo.\n"
        "**pgmemory.py** (2.345 caracteres): versão \"produto\" com pgvector."
    )
    resultado = verificacoes.verificar_existencia_ficheiros(resposta_real, mensagens_reais)
    ok = MARCADOR in resultado and "utils.py" in resultado and "memoria.py" in resultado
    print(f"{'OK' if ok else 'FALHOU'} — a contradição real dispara para os 2 nomes: {resultado[-250:]!r}")
    return ok


def teste_regressao_confusao_sem_falsidade() -> bool:
    print("\n=== 3. Regressão — troca #6 real (confusão de formatação, sem afirmação falsa) ===")
    listagem_real = tools.listar_ficheiros("/mnt/sovereign/superllmlocal")
    mensagens = _mensagens_com_listagem(listagem_real, "o nome utils.py está onde? não encontro!")
    # Excerto real — organizado de forma confusa (secção "NÃO vejo" com
    # itens que na verdade estão na lista), mas cada afirmação
    # individual continua verdadeira: HISTORICO.md está mesmo na lista.
    resposta_real = (
        "**Ficheiros que NÃO vejo na lista:**\n"
        "- `utils.py` - não está na lista!\n"
        "- `HISTORICO.md` - está na lista\n"
        "- `PESQUISA/` - está na lista\n"
    )
    resultado = verificacoes.verificar_existencia_ficheiros(resposta_real, mensagens)
    ok = MARCADOR not in resultado
    print(f"{'OK' if ok else 'FALHOU'} — nenhuma afirmação individual é falsa (HISTORICO.md/PESQUISA/ estão mesmo lá), não deve disparar")
    return ok


def teste_regressao_trivial() -> bool:
    print("\n=== 4. Regressão — trivial ao vivo ===")
    r1 = agent.responder("Quanto é 5 mais 5?")
    ok1 = MARCADOR not in r1
    print(f"{'OK' if ok1 else 'FALHOU'} — trivial, sem listar_ficheiros, sem disparo")
    return ok1


def teste_multiplas_listagens_falso_positivo() -> bool:
    """BUG REAL corrigido 17 Ago 2026 (achado a testar o SUPERLLMAPI,
    ver HISTORICO.md desse repo) — quando a troca chama
    listar_ficheiros mais que uma vez para pastas DIFERENTES, olhar só
    para a ÚLTIMA listagem é um falso positivo directo se a última
    chamada calhar ser uma subpasta que não contém os ficheiros
    citados, mesmo que uma chamada ANTERIOR da mesma troca os tivesse
    mostrado. Reproduz exactamente o padrão real: pasta principal
    primeiro, depois 2 subpastas em paralelo (o CORE_IDENTITY incentiva
    agrupar chamadas independentes na mesma resposta)."""
    print("\n=== 5. Regressão — múltiplas listagens na mesma troca (bug de 17 Ago) ===")
    mensagens = [
        {"role": "system", "content": agent.config.CORE_IDENTITY},
        {"role": "user", "content": "quantos ficheiros .py existem nesta pasta?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "listar_ficheiros", "arguments": {"caminho": "/mnt/sovereign/superllmlocal"}}},
        ]},
        {"role": "tool", "content": "agent.py\nconfig.py\ntools.py\nverificacoes.py\nPESQUISA/\nlogs/"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "listar_ficheiros", "arguments": {"caminho": "/mnt/sovereign/superllmlocal/PESQUISA"}}},
            {"function": {"name": "listar_ficheiros", "arguments": {"caminho": "/mnt/sovereign/superllmlocal/logs"}}},
        ]},
        {"role": "tool", "content": "(pasta vazia)"},
        {"role": "tool", "content": "(pasta vazia)"},
    ]
    resposta = "Existem 4 ficheiros .py: agent.py, config.py, tools.py, verificacoes.py"
    resultado = verificacoes.verificar_existencia_ficheiros(resposta, mensagens)
    ok = MARCADOR not in resultado
    print(f"{'OK' if ok else 'FALHOU'} — ficheiros reais da 1ª listagem, não deve disparar mesmo com listagens seguintes vazias")
    return ok


if __name__ == "__main__":
    ok = (
        teste_deterministico()
        and teste_incidente_real()
        and teste_regressao_confusao_sem_falsidade()
        and teste_regressao_trivial()
        and teste_multiplas_listagens_falso_positivo()
    )
    print(f"\n{'TUDO OK' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)
