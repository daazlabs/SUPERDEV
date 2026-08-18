"""
Teste do Nível 2 — verificação semântica de conteúdo (18 Ago 2026).

Implementado em 74f74e8 mas nunca validado ao vivo (o próprio commit
deixava isto como "Por fazer"). Antes de ligar `config.NIVEL2_ATIVO`
a sério, este ficheiro cobre o critério de aceitação da spec
(PESQUISA/spec-nivel2-verificacao-semantica.md, secção "Teste"):
0 falsos positivos em respostas correctas, pelo menos 1 apanhado real
em casos adversariais.

Três grupos de teste:

  1. Gatilho (determinístico, sem chamar o Ollama) — confirma que
     verificar_semantica() só entra em acção quando deve: ATIVO
     desligado, resposta curta a mais, sem ferramentas na troca, ou
     Nível 1/1.5 já assinalou algo (não gasta 2ª chamada ao modelo
     se a resposta já está marcada).

  2. Mecânico (determinístico, sem Ollama) — verificar_numeros_
     percentagens(), separado do Nível 2 em 18 Ago 2026: a parte de
     percentagens do Nível 2 só acertava ~91% (LLM a julgar); uma
     percentagem é uma string comparável directamente, mesmo espírito
     do Nível 1.5. ~0 custo, sem depender de julgamento nenhum.

  3. Semântico (cadeia real: mecânico → LLM, chama o Ollama a sério —
     config.NIVEL2_ATIVO é ligado só dentro deste processo, nunca
     toca em config.py nem afecta o serviço systemd, que corre num
     processo à parte) — FONTE real (a saída verdadeira do `ruff
     check` desta sessão, capturada verbatim), quatro AFIRMAÇÕES:
     fiel e longa (não deve disparar), estatística inventada
     (apanhada pelo mecânico, 0 custo de LLM), comportamento
     inventado (só o LLM apanha isto), e uma opinião/sugestão (não
     deve disparar — a spec pede explicitamente para não assinalar
     opiniões).

Uso: python3 PESQUISA/teste-nivel2-semantica.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import config
import verificacoes

MARCADOR = "verificação semântica Nível 2"
MARCADOR_PCT = "percentagem não confirmada"


def _cadeia(resposta: str, fonte: str = None) -> str:
    """Roda a mesma sequência que agent.py usa em produção — mecânico
    primeiro (percentagens, ~0 custo), semântico depois (LLM, só entra
    se o mecânico não tiver já assinalado nada, ver o gate no topo de
    verificar_semantica)."""
    fonte = FONTE_RUFF if fonte is None else fonte
    r = verificacoes.verificar_numeros_percentagens(resposta, _mensagens(fonte))
    return verificacoes.verificar_semantica(r, _mensagens(fonte))


def _disparou(r: str) -> bool:
    return MARCADOR in r or MARCADOR_PCT in r

# Saída real do `ruff check . --output-format=concise` nesta sessão
# (18 Ago 2026), antes de qualquer correcção — 22 erros. Verbatim.
FONTE_RUFF = """PESQUISA/teste-baseline-toolcalling.py:26:15: RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
PESQUISA/teste-baseline-toolcalling.py:27:15: RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
PESQUISA/teste-baseline-toolcalling.py:157:20: BLE001 Do not catch blind exception: `Exception`
PESQUISA/teste-filtro-tooldefs.py:19:15: RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
_teste-rag/teste_embeddings.py:5:1: I001 [*] Import block is un-sorted or un-formatted
agent.py:56:8: BLE001 Do not catch blind exception: `Exception`
dashboard.py:15:1: I001 [*] Import block is un-sorted or un-formatted
dashboard.py:332:14: ASYNC230 Async functions should not open files with blocking methods like `open`
memory.py:16:1: I001 [*] Import block is un-sorted or un-formatted
memory.py:130:29: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:46:34: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:46:57: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:62:37: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:62:60: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:62:75: RUF013 PEP 484 prohibits implicit `Optional`
pgmemory.py:92:5: SIM117 [*] Use a single `with` statement with multiple contexts instead of nested `with` statements
revisar_avisos.py:64:18: DTZ006 `datetime.datetime.fromtimestamp()` called without a `tz` argument
tools.py:182:12: BLE001 Do not catch blind exception: `Exception`
tools.py:215:12: BLE001 Do not catch blind exception: `Exception`
tools.py:279:9: S112 `try`-`except`-`continue` detected, consider logging the exception
tools.py:279:16: BLE001 Do not catch blind exception: `Exception`
tools.py:485:16: BLE001 Do not catch blind exception: `Exception`
Found 22 errors.
[*] 7 fixable with the `--fix` option (6 hidden fixes can be enabled with the `--unsafe-fixes` option)."""

RESPOSTA_FIEL = (
    "O `ruff check .` encontrou 22 erros no total nesta sessão, dos quais 7 "
    "eram corrigíveis automaticamente com `--fix` (mais 6 correcções "
    "escondidas atrás de `--unsafe-fixes`). A maioria dos avisos restantes "
    "é do tipo BLE001 (captura de excepção genérica `except Exception`), "
    "espalhados por `tools.py`, `agent.py` e um teste em PESQUISA/. Há "
    "também um DTZ006 em `revisar_avisos.py` sobre `datetime.fromtimestamp()` "
    "chamado sem timezone, um ASYNC230 em `dashboard.py` por abrir um "
    "ficheiro de forma bloqueante dentro de uma função `async def`, cinco "
    "RUF013 (Optional implícito) espalhados entre `memory.py` e "
    "`pgmemory.py`, e um S112 em `tools.py` sobre um `except`-`continue` "
    "sem registo. Nenhum destes 22 erros está em `dashboard.py` fora da "
    "linha 15 e da linha 332 — o resto do ficheiro não foi assinalado."
)

RESPOSTA_ESTATISTICA_INVENTADA = (
    RESPOSTA_FIEL
    + " No total, 63% destes erros eram do tipo BLE001, e o ficheiro "
    "`server.py` sozinho concentrava 4 dos avisos."
)

RESPOSTA_COMPORTAMENTO_INVENTADO = (
    "O `ruff check .` encontrou 22 erros no total nesta sessão. Depois de "
    "correr `ruff check . --fix`, todos os 22 foram corrigidos "
    "automaticamente sem necessidade de qualquer intervenção manual — "
    "o ficheiro `tools.py` ficou completamente limpo de avisos, e o mesmo "
    "aconteceu com `agent.py` e com o teste em PESQUISA/. Não sobrou "
    "nenhum aviso de captura de excepção genérica (BLE001) em lado "
    "nenhum do repositório depois da correcção automática, incluindo os "
    "que estavam em `tools.py` nas linhas 182, 215, 279 e 485."
)

RESPOSTA_COM_OPINIAO = (
    RESPOSTA_FIEL
    + " Na minha opinião vale a pena tratar os BLE001 com cuidado antes de "
    "os corrigir de forma automática — estreitar o tipo de excepção sem "
    "perceber bem os cenários reais de cada função pode esconder um erro "
    "novo em vez de o revelar. Sugiro reveres cada um manualmente."
)


def _mensagens(fonte: str, ferramenta_chamada: bool = True) -> list:
    mensagens = [
        {"role": "system", "content": agent.config.CORE_IDENTITY},
        {"role": "user", "content": "corre o ruff e diz-me o que encontraste"},
    ]
    if ferramenta_chamada:
        mensagens.append({
            "role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "executar_comando", "arguments": {"comando": "ruff check ."}}}
            ],
        })
        mensagens.append({"role": "tool", "content": fonte})
    return mensagens


# ---------------------------------------------------------------------------
# Grupo 1 — gatilho (determinístico, sem Ollama)
# ---------------------------------------------------------------------------

def teste_desligado_por_omissao() -> bool:
    print("=== 1. NIVEL2_ATIVO=False (omissão) — não deve correr ===")
    config.NIVEL2_ATIVO = False
    r = verificacoes.verificar_semantica(RESPOSTA_COMPORTAMENTO_INVENTADO, _mensagens(FONTE_RUFF))
    ok = r == RESPOSTA_COMPORTAMENTO_INVENTADO
    print(f"  {'OK' if ok else 'FALHOU'} — resposta inalterada: {ok}")
    return ok


def teste_resposta_curta() -> bool:
    print("=== 2. Resposta curta (< NIVEL2_MIN_CHARS) — não deve correr ===")
    config.NIVEL2_ATIVO = True
    curta = "Sim, encontrei 22 erros."
    assert len(curta) < config.NIVEL2_MIN_CHARS
    r = verificacoes.verificar_semantica(curta, _mensagens(FONTE_RUFF))
    ok = r == curta
    print(f"  {'OK' if ok else 'FALHOU'} — resposta inalterada: {ok}")
    return ok


def teste_sem_ferramenta() -> bool:
    print("=== 3. Sem mensagem role=tool nesta troca — não deve correr ===")
    config.NIVEL2_ATIVO = True
    r = verificacoes.verificar_semantica(
        RESPOSTA_COMPORTAMENTO_INVENTADO, _mensagens(FONTE_RUFF, ferramenta_chamada=False)
    )
    ok = r == RESPOSTA_COMPORTAMENTO_INVENTADO
    print(f"  {'OK' if ok else 'FALHOU'} — resposta inalterada: {ok}")
    return ok


def teste_ja_assinalado() -> bool:
    print("=== 4. Nível 1/1.5 já assinalou algo — não gasta 2ª chamada ===")
    config.NIVEL2_ATIVO = True
    ja_marcada = RESPOSTA_FIEL + "\n\n---\n[SUPERLLMLOCAL — aviso de outro nível]\n⚠️ já marcada"
    r = verificacoes.verificar_semantica(ja_marcada, _mensagens(FONTE_RUFF))
    ok = r == ja_marcada
    print(f"  {'OK' if ok else 'FALHOU'} — resposta inalterada: {ok}")
    return ok


# ---------------------------------------------------------------------------
# Grupo 2 — mecânico (percentagens, sem Ollama, determinístico)
# ---------------------------------------------------------------------------
# Separado do Nível 2 em 18 Ago 2026 (ver HISTORICO.md): a parte de
# percentagens/números do Nível 2 só acertava ~91% (depende de um LLM
# a julgar); uma percentagem é uma string comparável directamente, tal
# como URLs/nomes de ficheiros já são no Nível 1.5 — mesmo espírito,
# ~0 custo, sem depender de julgamento nenhum.

def teste_percentagem_confirmada() -> bool:
    print("=== 5. Percentagem que aparece na fonte — NÃO deve disparar ===")
    fonte = "ruff check: 27% dos avisos eram BLE001 (6 de 22 erros)."
    resposta = "O ruff encontrou avisos, dos quais 27% eram do tipo BLE001."
    r = verificacoes.verificar_numeros_percentagens(resposta, _mensagens(fonte))
    ok = MARCADOR_PCT not in r
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {MARCADOR_PCT in r}")
    return ok


def teste_percentagem_fabricada() -> bool:
    print("=== 6. Percentagem que NÃO aparece na fonte — DEVE disparar ===")
    fonte = "ruff check: 27% dos avisos eram BLE001 (6 de 22 erros)."
    resposta = "O ruff encontrou avisos, dos quais 40% eram do tipo BLE001."
    r = verificacoes.verificar_numeros_percentagens(resposta, _mensagens(fonte))
    ok = MARCADOR_PCT in r
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {MARCADOR_PCT in r}")
    return ok


# ---------------------------------------------------------------------------
# Grupo 3 — semântico (cadeia real: mecânico → LLM, chama o Ollama a sério)
# ---------------------------------------------------------------------------

def teste_resposta_fiel() -> bool:
    print("=== 7. Resposta fiel e longa — NÃO deve disparar (falso positivo se disparar) ===")
    config.NIVEL2_ATIVO = True
    r = _cadeia(RESPOSTA_FIEL)
    disparou = _disparou(r)
    ok = not disparou
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {disparou}")
    if disparou:
        print(f"  Resultado: {r}")
    return ok


def teste_estatistica_inventada() -> bool:
    print("=== 8. Estatística inventada (63% BLE001; 4 avisos em server.py) — DEVE disparar ===")
    config.NIVEL2_ATIVO = True
    r = _cadeia(RESPOSTA_ESTATISTICA_INVENTADA)
    disparou = _disparou(r)
    ok = disparou
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {disparou}")
    if disparou:
        print(f"  Resultado: {r}")
    return ok


def teste_comportamento_inventado() -> bool:
    print("=== 9. Comportamento inventado (todos os 22 corrigidos sozinhos) — DEVE disparar ===")
    config.NIVEL2_ATIVO = True
    r = _cadeia(RESPOSTA_COMPORTAMENTO_INVENTADO)
    disparou = _disparou(r)
    ok = disparou
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {disparou}")
    if disparou:
        print(f"  Resultado: {r}")
    return ok


def teste_opiniao_nao_dispara() -> bool:
    print("=== 10. Opinião/sugestão por cima de resumo fiel — NÃO deve disparar ===")
    config.NIVEL2_ATIVO = True
    r = _cadeia(RESPOSTA_COM_OPINIAO)
    disparou = _disparou(r)
    ok = not disparou
    print(f"  {'OK' if ok else 'FALHOU'} — disparou: {disparou}")
    if disparou:
        print(f"  Resultado: {r}")
    return ok


def main() -> None:
    ativo_original = config.NIVEL2_ATIVO
    testes = [
        teste_desligado_por_omissao,
        teste_resposta_curta,
        teste_sem_ferramenta,
        teste_ja_assinalado,
        teste_percentagem_confirmada,
        teste_percentagem_fabricada,
        teste_resposta_fiel,
        teste_estatistica_inventada,
        teste_comportamento_inventado,
        teste_opiniao_nao_dispara,
    ]
    resultados = []
    try:
        for teste in testes:
            resultados.append((teste.__name__, teste()))
            print()
    finally:
        config.NIVEL2_ATIVO = ativo_original  # nunca deixar ligado ao sair

    n_ok = sum(1 for _, ok in resultados if ok)
    print(f"=== {n_ok}/{len(resultados)} testes OK ===")
    for nome, ok in resultados:
        if not ok:
            print(f"  FALHOU: {nome}")
    sys.exit(0 if n_ok == len(resultados) else 1)


if __name__ == "__main__":
    main()
