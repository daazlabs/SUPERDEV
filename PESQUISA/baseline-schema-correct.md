# B4 — baseline de schema-correct rate (tool-calling), qwen3.5:9b

> Método: secção 4.2 de `relatorio-mercado.md`. 5 repetições por caso, `config.OPTIONS`/`config.THINK`/`tools.TOOL_DEFS` reais (via `agent.ollama_chat`), não isolado. Escrito incrementalmente.

| Caso | Repetição | Classe | Detalhe | Tempo (s) |
|---|---|---|---|---|
| ler_ficheiro | 1/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py'} | 40.4 |
| ler_ficheiro | 2/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py'} | 15.1 |
| ler_ficheiro | 3/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py'} | 14.9 |
| ler_ficheiro | 4/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py'} | 15.1 |
| ler_ficheiro | 5/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py'} | 15.0 |
| listar_ficheiros | 1/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/'} | 14.5 |
| listar_ficheiros | 2/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/'} | 14.4 |
| listar_ficheiros | 3/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/'} | 14.8 |
| listar_ficheiros | 4/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/'} | 15.1 |
| listar_ficheiros | 5/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/'} | 15.2 |
| procurar_texto | 1/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py', 'termo': 'OLLAMA_HOST'} | 21.0 |
| procurar_texto | 2/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py', 'termo': 'OLLAMA_HOST'} | 20.6 |
| procurar_texto | 3/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py', 'termo': 'OLLAMA_HOST'} | 20.3 |
| procurar_texto | 4/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py', 'termo': 'OLLAMA_HOST'} | 20.5 |
| procurar_texto | 5/5 | CORRECTO | args: {'caminho': '/mnt/sovereign/superdev/config.py', 'termo': 'OLLAMA_HOST'} | 20.4 |
| correr_ruff | 1/5 | CORRECTO | args: {'codigo': 'def soma(a, b):\n    return a+b'} | 14.9 |
| correr_ruff | 2/5 | CORRECTO | args: {'codigo': 'def soma(a, b):\n    return a+b'} | 15.0 |
| correr_ruff | 3/5 | CORRECTO | args: {'codigo': 'def soma(a, b):\n    return a+b'} | 15.0 |
| correr_ruff | 4/5 | CORRECTO | args: {'codigo': 'def soma(a, b):\n    return a+b'} | 14.7 |
| correr_ruff | 5/5 | CORRECTO | args: {'codigo': 'def soma(a, b):\n    return a+b'} | 14.9 |
| ler_varios_ficheiros | 1/5 | CORRECTO | args: {'caminhos': ['/mnt/sovereign/superdev/config.py', '/mnt/sovereign/superdev/agent.py']} | 21.0 |
| ler_varios_ficheiros | 2/5 | CORRECTO | args: {'caminhos': ['/mnt/sovereign/superdev/config.py', '/mnt/sovereign/superdev/agent.py']} | 21.0 |
| ler_varios_ficheiros | 3/5 | CORRECTO | args: {'caminhos': ['/mnt/sovereign/superdev/config.py', '/mnt/sovereign/superdev/agent.py']} | 20.9 |
| ler_varios_ficheiros | 4/5 | CORRECTO | args: {'caminhos': ['/mnt/sovereign/superdev/config.py', '/mnt/sovereign/superdev/agent.py']} | 20.2 |
| ler_varios_ficheiros | 5/5 | CORRECTO | args: {'caminhos': ['/mnt/sovereign/superdev/config.py', '/mnt/sovereign/superdev/agent.py']} | 20.0 |
| pesquisar_web | 1/5 | CORRECTO | args: {'query': 'últimas notícias sobre o modelo Qwen 3.5'} | 14.5 |
| pesquisar_web | 2/5 | CORRECTO | args: {'query': 'últimas notícias sobre o modelo Qwen 3.5'} | 14.0 |
| pesquisar_web | 3/5 | CORRECTO | args: {'query': 'últimas notícias sobre o modelo Qwen 3.5'} | 14.2 |
| pesquisar_web | 4/5 | CORRECTO | args: {'query': 'últimas notícias sobre o modelo Qwen 3.5'} | 14.6 |
| pesquisar_web | 5/5 | CORRECTO | args: {'query': 'últimas notícias sobre o modelo Qwen 3.5'} | 16.3 |
| controlo_negativo_1 | 1/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 4.4 |
| controlo_negativo_1 | 2/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 4.0 |
| controlo_negativo_1 | 3/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 4.3 |
| controlo_negativo_1 | 4/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 4.2 |
| controlo_negativo_1 | 5/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 3.9 |
| controlo_negativo_2 | 1/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 20.2 |
| controlo_negativo_2 | 2/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 18.9 |
| controlo_negativo_2 | 3/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 23.6 |
| controlo_negativo_2 | 4/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 19.7 |
| controlo_negativo_2 | 5/5 | CORRECTO | não chamou nenhuma ferramenta, como esperado | 21.9 |

## Resumo

| Caso | Taxa correcta |
|---|---|
| ler_ficheiro | 5/5 (100%) |
| listar_ficheiros | 5/5 (100%) |
| procurar_texto | 5/5 (100%) |
| correr_ruff | 5/5 (100%) |
| ler_varios_ficheiros | 5/5 (100%) |
| pesquisar_web | 5/5 (100%) |
| controlo_negativo_1 | 5/5 (100%) |
| controlo_negativo_2 | 5/5 (100%) |

**Total: 40/40 (100%)**
