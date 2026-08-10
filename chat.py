"""
SUPERDEV — terminal de conversa "bonito", por cima do agent.py.

Ficheiro à parte de propósito (10 Ago 2026), mesmo espírito do
server.py (ver esse ficheiro): NÃO mexe em agent.py/tools.py/
config.py/pgmemory.py — só importa agent e usa agent.responder() e
agent.nova_sessao(), exactamente como agent.main() (o modo terminal
"bruto") já fazia. A lógica do agente é a mesma nos dois caminhos; só
a apresentação muda aqui.

PORQUÊ UM FICHEIRO À PARTE, não uma opção dentro de agent.py: isto usa
`rich` (dependência extra só para desenhar o terminal) — agent.py
continua a correr só com a biblioteca padrão (mais fácil de correr em
qualquer sítio, incluindo dentro do server.py como serviço, que nunca
tem terminal nenhum e não precisa disto).

Motivado pelo utilizador (10 Ago 2026): o modo bruto (`python3
agent.py`) funciona mas é difícil de ler numa conversa mais longa —
sem destaque de markdown (as respostas vêm cheias de **negrito**,
### títulos, blocos de código), sem indicação de que está a trabalhar
enquanto o modelo gera a resposta. Isto resolve os dois com o `rich`
(já estava instalado no /usr/bin/python3, confirmado antes de usar).

Lançado pelo comando `superdev` (ver ~/.local/bin/superdev) — corre de
qualquer pasta, não precisa de estar dentro deste directório (o script
usa o caminho absoluto deste ficheiro).

EDIÇÃO DE LINHA + CTRL+C (10 Ago 2026) — dois problemas reais
apanhados pelo utilizador ao testar: (1) `input()` sem o módulo
`readline` importado não sabe mover o cursor a sério com as setas
esquerda/direita nem apagar bem texto colado — só bastou importar
`readline` (biblioteca padrão, já estava disponível, só não estava
activado); dá também histórico com as setas cima/baixo, de borla. (2)
Ctrl+C, antes, fechava o programa inteiro mesmo a meio de escrever uma
linha errada — sem forma de cancelar só essa linha. Incidente real:
utilizador colou texto errado, tentou Ctrl+C para cancelar antes de
enviar, e isso fechou a sessão toda em vez de limpar a linha. Corrigido
abaixo: Ctrl+C a escrever cancela só a linha actual; Ctrl+D (EOF) é que
sai a sério. Ctrl+C enquanto o modelo está a gerar também passou a
cancelar a ESPERA (deixa de bloquear o utilizador) — não cancela o
trabalho no lado da Ollama, que continua a correr em segundo plano até
terminar, só deixa de bloquear quem está a usar o terminal.
"""
import readline  # noqa: F401 — activa edição de linha no input(), não é chamado directamente
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import agent

console = Console()


def _banner() -> None:
    console.print(
        Panel(
            "[bold cyan]SUPERDEV[/] — agente de programação local\n"
            "[dim]Escreve o teu pedido e Enter. Ctrl+C cancela a linha, "
            "Ctrl+D sai.[/]",
            border_style="cyan",
        )
    )


def main() -> None:
    _banner()
    sessao = agent.nova_sessao()
    while True:
        try:
            pedido = console.input("\n[bold yellow]Tu[/] › ").strip()
        except KeyboardInterrupt:
            console.print("[dim](linha cancelada — Ctrl+D para sair)[/]")
            continue
        except EOFError:
            console.print()
            break
        if not pedido:
            continue

        inicio = time.time()
        try:
            with console.status("[dim]SUPERDEV a pensar...[/]", spinner="dots"):
                resposta = agent.responder(pedido, sessao)
        except KeyboardInterrupt:
            console.print(
                "[dim](deixei de esperar — a Ollama pode continuar a "
                "trabalhar nisto em segundo plano)[/]"
            )
            continue
        duracao = time.time() - inicio

        console.print(
            Panel(
                Markdown(resposta),
                title=f"[bold cyan]SUPERDEV[/] [dim]· {duracao:.1f}s[/]",
                title_align="left",
                border_style="cyan",
            )
        )


if __name__ == "__main__":
    main()
