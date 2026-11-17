# ==========================================================================
# AVISO DE LIMITEDS BARATOS (Roblox -> Discord)
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
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")   # vem do segredo do GitHub (nao fica no arquivo)
DESCONTO_MIN = 20      # avisa quando o menor preco estiver 20 por cento abaixo do valor
ITENS = []             # lista de IDs para vigiar. Vazio = vigia todos. Ex.: [1031429, 21070012]
DEMANDA_MIN = 2        # demanda minima no Rolimon's (0 a 4). Evita itens que ninguem compra
PRECO_MIN = 100        # ignora itens com valor menor que isso (em Robux)
IGNORAR_PROJETADOS = True   # ignora itens marcados como projected (preco manipulado)
SO_COM_LUCRO = False   # True = so avisa se der lucro na revenda (depois da taxa de 30 por cento)
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
        if not referencia or referencia < PRECO_MIN:
            continue
        if IGNORAR_PROJETADOS and projetado is not None and projetado > 0:
            continue   # item projected: preco inflado por trocas combinadas
        if demanda is not None and demanda != -1 and demanda < DEMANDA_MIN:
            continue
        if ITENS and int(id_texto) not in ITENS:
            continue
        itens[int(id_texto)] = (nome, referencia, rap if rap and rap > 0 else referencia)
    return itens


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
        precos = menores_precos(lote)
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
        time.sleep(2)                                # pausa entre lotes para nao sobrecarregar


def main():
    if not WEBHOOK_URL:
        print("Faltou o segredo WEBHOOK_URL.")
        raise SystemExit(1)
    carregar_estado()
    try:
        rodada()
    finally:
        salvar_estado()   # salva mesmo se der erro no meio
    print("Execucao terminada.")


if __name__ == "__main__":
    main()
