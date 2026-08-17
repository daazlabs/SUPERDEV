# Spec — Nível 2: verificação semântica de conteúdo

Contexto: HISTORICO.md, "Nível 1.5" (13 Ago) e "extrai verificacoes.py" (17
Ago). Nível 1/1.5 já existem e são mecânicos (confirmam que a ferramenta
certa foi chamada, ou que constantes `NOME_MAIUSCULO` batem certo). O que
falta: confirmar que o CONTEÚDO em prosa livre da resposta (percentagens,
afirmações de comportamento, resumos) bate com o que a ferramenta devolveu
— não só "foi citada/chamada".

## Decisão de desenho (a que estava por tomar)

- **Gatilho**: só corre quando `verificar_*` do Nível 1/1.5 não encontrou
  nada (resposta "limpa" até aqui) **e** houve pelo menos 1 mensagem
  `role == "tool"` nesta troca **e** `len(resposta) > NIVEL2_MIN_CHARS`
  (400). Não corre em respostas curtas/triviais — é aí que "pedido de
  risco" (framing original de 10 Ago) se torna concreto e barato de medir.
- **Custo**: 2ª chamada ao modelo, sempre. Por isso fica **desligado por
  omissão** (`config.NIVEL2_ATIVO = False`) — liga-se para testar.
- **Modelo**: reaproveita `config.MODEL` (não criar dependência de puxar
  modelo novo). Se ficar lento a mais nos testes, mudar para um modelo
  mais pequeno dedicado é ajuste de configuração, não de arquitectura.
- **Não corrige** — mesmo espírito do Nível 1: só assinala, utilizador
  decide. Sem isso, arriscamos confabulação a "corrigir" confabulação.

## Implementação

`verificacoes.py` — nova função, mesma assinatura das outras:

```python
def verificar_semantica(resposta: str, mensagens: list) -> str:
    if not config.NIVEL2_ATIVO:
        return resposta
    if len(resposta) < config.NIVEL2_MIN_CHARS:
        return resposta
    if not any(m.get("role") == "tool" for m in mensagens):
        return resposta

    fontes = "\n".join(m["content"] for m in mensagens if m.get("role") == "tool" and m.get("content"))
    prompt = (
        "Tarefa: verificação factual. FONTE é o resultado real de "
        "ferramentas. AFIRMAÇÃO é uma resposta que deve basear-se só na "
        "FONTE. Lista, em JSON (array de strings, [] se nenhuma), as "
        "frases da AFIRMAÇÃO que fazem uma alegação factual concreta "
        "(número, comportamento, facto) NÃO suportada pela FONTE. Não "
        "assinales opiniões, sugestões ou o que já está correcto.\n\n"
        f"FONTE:\n{fontes}\n\nAFIRMAÇÃO:\n{resposta}"
    )
    # chamada directa ao Ollama (mesmo padrão de agent.py _chamar_modelo,
    # mas sem tools/histórico — só este prompt avulso), parse do JSON
    # com fallback silencioso (se o modelo não devolver JSON válido,
    # não bloqueia — devolve resposta original, como as outras verificar_*
    # fazem em caso de dúvida).
    ...
    if nao_suportadas:
        aviso = "\n\n---\n[SUPERLLMLOCAL — verificação semântica Nível 2]"
        aviso += "\n⚠️ Não confirmado na fonte: " + "; ".join(nao_suportadas)
        return resposta + aviso
    return resposta
```

`config.py` — 2 constantes novas, junto às outras de verificação:

```python
NIVEL2_ATIVO = False       # liga só para testar — dobra custo por resposta
NIVEL2_MIN_CHARS = 400
```

`agent.py` — última linha da cadeia (depois de `verificar_existencia_ficheiros`,
linha ~534):

```python
resposta = verificacoes.verificar_semantica(resposta, mensagens)
```

## Teste (reaproveita o que já existe)

1. `config.NIVEL2_ATIVO = True` só numa sessão de teste.
2. Correr `chat.py` com 10-15 pedidos reais que envolvam ferramentas.
3. `ver_diagnostico.py` já sabe listar trocas com aviso; `revisar_avisos.py`
   já sabe pedir veredicto humano (acerto/falso-positivo) — mesmo fluxo
   usado para validar o Nível 1.5.
4. Critério de aceitação: 0 falsos positivos em respostas correctas, e
   pelo menos 1 apanhado real (frase fabricada não suportada pela fonte)
   nos testes propositadamente adversariais.

## Fora de âmbito desta spec

- Trocar de modelo verificador (fica para depois de medir custo real).
- Estender a categorias além de "prosa livre vs. fonte de ferramenta"
  (ex.: coerência entre voltas, não só última resposta vs. fontes).
