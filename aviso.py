# ==========================================================================
# AVISO DE LIMITEDS BARATOS (Roblox -> Discord) - versao para rodar no PC
# Este script NAO compra nada e NAO pede senha nem cookie.
# Ele confere precos publicos e manda um aviso no seu Discord quando um
# limitado esta abaixo do valor. Voce compra na mao, no site do Roblox.
# Precisa so do Python 3 (nao precisa instalar nada extra).
# ==========================================================================
import json
import os
import time
import urllib.request
import urllib.error

# ------------------------- CONFIGURE AQUI ---------------------------------
WEBHOOK_URL = "https://discord.com/api/webhooks/1572098942378840164/BpA8x0wFVR_-DpNZ7dZkC-LSCiahsnw95zkCQzOB6E5jMH5EXz7c5aDnncoZgwF7JFh-"   # link do webhook do seu canal do Discord
DESCONTO_MIN = 20      # avisa quando o menor preco estiver 20 por cento abaixo do valor
ITENS = []             # lista de IDs para vigiar. Vazio = vigia todos. Ex.: [1031429, 21070012]
DEMANDA_MIN = 2        # demanda minima no Rolimon's (0 a 4). Evita itens que ninguem compra
PRECO_MIN = 100        # ignora itens com valor menor que isso (em Robux)
VALOR_MAX = 5000       # ignora itens com valor MAIOR que isso (em Robux). Aumente quando tiver mais Robux
IGNORAR_PROJETADOS = True   # ignora itens marcados como projected (preco manipulado)
SO_COM_LUCRO = False   # True = so avisa se der lucro na revenda (depois da taxa de 30 por cento)
MAX_ITENS = 300        # vigia no maximo esses itens por execucao (os mais valiosos), para o Roblox nao bloquear
PAUSA_LOTES = 5        # segundos de pausa entre os lotes
INTERVALO = 120        # segundos entre cada rodada (mais devagar para o Roblox nao bloquear)
ESPERA_429 = 300       # segundos de espera quando o Roblox pede para ir devagar
ARQUIVO_ESTADO = "estado.json"   # guarda o que ja foi avisado entre uma execucao e outra
# --------------------------------------------------------------------------

UA = {"User-Agent": "Mozilla/5.0 (aviso-limiteds)"}
avisados = {}          # guarda o ultimo preco avisado de cada item (evita repetir aviso)


def carregar_estado():
    try:
        with open(ARQUIVO_ESTADO, encoding="utf-8") as f:
            for chave, valor in json.load(f).items():
                avisados[int(chave)] = valor
    except (OSError, ValueError):
        pass   # primeira execucao: ainda nao existe estado


def salvar_estado():
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in avisados.items()}, f)

csrf = {"token": ""}   # token temporario que o Roblox pede em pedidos POST


def pegar_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def valores_rolimons():
    # devolve {id: (nome, valor, rap)} a partir do site do Rolimon's
    dados = pegar_json("https://www.rolimons.com/itemapi/itemdetails")
    itens = {}
    for id_texto, d in dados["items"].items():
        nome, rap, valor, demanda, projetado = d[0], d[2], d[3], d[5], d[7]
        referencia = valor if valor and valor > 0 else rap   # se nao tem valor, usa o RAP
        if not referencia or referencia < PRECO_MIN or referencia > VALOR_MAX:
            continue
        if IGNORAR_PROJETADOS and projetado is not None and projetado > 0:
            continue   # item projected: preco inflado por trocas combinadas
        if demanda is not None and demanda != -1 and demanda < DEMANDA_MIN:
            continue
        if ITENS and int(id_texto) not in ITENS:
            continue
        itens[int(id_texto)] = (nome, referencia, rap if rap and rap > 0 else referencia)
    if len(itens) > MAX_ITENS:   # fica so com os MAX_ITENS de maior valor
        ordenados = sorted(itens.items(), key=lambda par: par[1][1], reverse=True)
        itens = dict(ordenados[:MAX_ITENS])
    return itens


class LimiteExcedido(Exception):
    pass


def menores_precos(ids):
    # pergunta ao catalogo do Roblox o menor preco de revenda de cada item
    corpo = json.dumps({"items": [{"itemType": "Asset", "id": i} for i in ids]}).encode()
    for tentativa in range(2):
        cab = dict(UA)
        cab["Content-Type"] = "application/json"
        cab["x-csrf-token"] = csrf["token"]
        req = urllib.request.Request(
            "https://catalog.roblox.com/v1/catalog/items/details",
            data=corpo, headers=cab, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
            return {x["id"]: x.get("lowestPrice") for x in dados.get("data", [])}
        except urllib.error.HTTPError as erro:
            if erro.code == 403 and tentativa == 0:
                csrf["token"] = erro.headers.get("x-csrf-token", "")   # pega o token e tenta de novo
                continue
            if erro.code == 429:
                raise LimiteExcedido()   # o Roblox pediu para ir mais devagar
            raise
    return {}


def enviar_discord(texto):
    corpo = json.dumps({"content": texto}).encode()
    cab = dict(UA)
    cab["Content-Type"] = "application/json"
    req = urllib.request.Request(WEBHOOK_URL, data=corpo, headers=cab, method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def rodada():
    referencias = valores_rolimons()
    ids = list(referencias.keys())
    for inicio in range(0, len(ids), 100):          # o Roblox aceita lotes de ate 100 itens
        lote = ids[inicio:inicio + 100]
        try:
            precos = menores_precos(lote)
        except LimiteExcedido:
            print("O Roblox pediu para esperar (erro 429).")
            return True
        for item_id in lote:
            preco = precos.get(item_id)
            nome, valor, rap = referencias[item_id]
            if not preco:
                continue
            desconto = (valor - preco) * 100 / valor
            lucro = int(valor * 0.7) - preco   # estimativa: o Roblox fica com 30 por cento na venda
            if preco >= rap:
                continue   # so avisa se tambem estiver abaixo do RAP (media de vendas)
            if SO_COM_LUCRO and lucro <= 0:
                continue
            if desconto >= DESCONTO_MIN and avisados.get(item_id) != preco:
                avisados[item_id] = preco
                enviar_discord(
                    "💸 **%s** esta barato!\nPreco: %d R$ | Valor: %d R$ | RAP: %d R$ | Desconto: %.0f%%\n"
                    "Lucro estimado na revenda (apos taxa de 30%%): %d R$\n"
                    "https://www.roblox.com/catalog/%d" % (nome, preco, valor, rap, desconto, lucro, item_id))
                print("Aviso enviado:", nome, preco)
        time.sleep(PAUSA_LOTES)                      # pausa entre lotes para nao sobrecarregar
    return False


def main():
    carregar_estado()
    print("Aviso de limiteds ligado. Aperte Ctrl+C para parar.")
    while True:
        try:
            bloqueado = rodada()
        except Exception as erro:
            bloqueado = False
            print("Erro nesta rodada (vou tentar de novo):", erro)
        salvar_estado()
        if bloqueado:
            print("Esperando %d segundos antes de tentar de novo..." % ESPERA_429)
            time.sleep(ESPERA_429)
        else:
            time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
