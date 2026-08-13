"""
Teste ao vivo do bug de fragmentação de colagens em chat.py (13 Ago
2026, ver HISTORICO.md e o comentário grande no topo de chat.py).

Corre chat.py dentro de um pseudo-terminal real (módulo `pty` —
precisa de ser um tty a sério para o readline se comportar como no
uso real, não um pipe simples), simula os dois cenários que importam,
e confirma pelo `logs/conversas.jsonl` (fonte da verdade, não o que é
impresso no ecrã) quantos "pedidos" separados o agente recebeu:

  1. RAJADA (simula colar um texto de 5 linhas) — todas as linhas
     escritas ao mesmo tempo, sem pausa nenhuma. Devia virar 1 PEDIDO
     SÓ, juntando as 5 linhas.
  2. CONVERSA NORMAL (simula uma pessoa a sério: espera a resposta
     completa antes de escrever a mensagem seguinte, com uma pausa
     real a ler/pensar) — devia continuar a virar pedidos separados,
     um por mensagem, como sempre foi. 1ª versão deste teste (sem
     esperar pela resposta entre mensagens) apanhou um caso real em
     que 2 mensagens escritas ENQUANTO o agente ainda respondia à
     anterior ficavam ambas à espera no buffer e eram juntas por
     engano — corrigido aqui para esperar a resposta a sério, que é
     como uma conversa normal acontece de facto.
"""
import json
import os
import pty
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_CONVERSAS = os.path.join(BASE_DIR, "logs", "conversas.jsonl")
CHAT_PY = os.path.join(BASE_DIR, "chat.py")


def _contar_linhas(caminho: str) -> int:
    if not os.path.exists(caminho):
        return 0
    with open(caminho) as f:
        return sum(1 for _ in f)


def _ultimos_pedidos(caminho: str, desde: int) -> list[str]:
    with open(caminho) as f:
        linhas = f.readlines()
    return [json.loads(l)["pedido"] for l in linhas[desde:]]


def _esperar_resposta(baseline: int, timeout: float = 60) -> None:
    """Poll a conversas.jsonl até aparecer mais uma linha do que
    `baseline` — é como saber que o agente já respondeu de facto,
    não um sleep(N) às cegas."""
    t0 = time.time()
    while _contar_linhas(LOG_CONVERSAS) <= baseline:
        if time.time() - t0 > timeout:
            raise TimeoutError("agente não respondeu a tempo")
        time.sleep(0.2)


def _correr_cenario(nome: str, escrever_fn) -> list[str]:
    print(f"\n=== {nome} ===")
    antes = _contar_linhas(LOG_CONVERSAS)

    pid, fd = pty.fork()
    if pid == 0:  # processo filho — corre o chat.py a sério
        os.chdir(BASE_DIR)
        os.execvp(sys.executable, [sys.executable, CHAT_PY])
        os._exit(1)  # só chega aqui se o exec falhar

    try:
        time.sleep(2)  # dar tempo ao banner/import arrancar
        escrever_fn(fd, antes)
    finally:
        os.write(fd, b"\x04")  # Ctrl+D — sai do chat.py de forma limpa
        time.sleep(1)
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        os.close(fd)

    pedidos = _ultimos_pedidos(LOG_CONVERSAS, antes)
    print(f"Pedidos registados em conversas.jsonl: {len(pedidos)}")
    for p in pedidos:
        print(f"  - {p!r}")
    return pedidos


def cenario_rajada(fd: int, baseline: int) -> None:
    """5 linhas, uma escrita a seguir à outra, sem pausa — simula uma
    colagem que o terminal NÃO marcou como bracketed paste."""
    texto = (
        "STEP 1 — linha um do briefing\n"
        "STEP 2 — linha dois do briefing\n"
        "STEP 3 — linha três do briefing\n"
        "STEP 4 — linha quatro do briefing\n"
        "STEP 5 — linha cinco, fim do briefing\n"
    )
    os.write(fd, texto.encode())
    _esperar_resposta(baseline)


def cenario_conversa_normal(fd: int, baseline: int) -> None:
    """3 mensagens, cada uma só escrita DEPOIS de a resposta anterior
    já ter chegado — o padrão real de uma conversa, não uma rajada de
    escrita às cegas."""
    mensagens = ["Olá, primeira mensagem.", "Segunda mensagem, a sério.", "Terceira e última."]
    linhas_vistas = baseline
    for msg in mensagens:
        os.write(fd, (msg + "\n").encode())
        _esperar_resposta(linhas_vistas)
        linhas_vistas = _contar_linhas(LOG_CONVERSAS)
        time.sleep(0.3)  # pausa real de "ler a resposta antes de escrever a seguinte"


if __name__ == "__main__":
    p1 = _correr_cenario("RAJADA (deve virar 1 pedido)", cenario_rajada)
    p2 = _correr_cenario("CONVERSA NORMAL (deve continuar a virar 3 pedidos)", cenario_conversa_normal)

    ok_rajada = len(p1) == 1 and all(f"STEP {i}" in p1[0] for i in range(1, 6))
    ok_conversa = len(p2) == 3

    print("\n=== RESULTADO ===")
    print(f"Rajada juntou tudo num pedido só: {'OK' if ok_rajada else 'FALHOU'}")
    print(f"Conversa normal manteve 3 pedidos separados: {'OK' if ok_conversa else 'FALHOU'}")
    sys.exit(0 if (ok_rajada and ok_conversa) else 1)
