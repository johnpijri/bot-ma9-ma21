import os
import time
import datetime as dt
import requests
import pandas as pd
from dotenv import load_dotenv
from flask import Flask
import threading

# ------------ CONFIGURAÇÃO ------------
load_dotenv()

PAIR = os.getenv("PAIR", "BTC-USD")           # Ex.: BTC-USD, ETH-USD
RESOLUTION = os.getenv("RESOLUTION", "6h")    # "1m","5m","15m","1h","6h","1d"
CAPITAL = float(os.getenv("CAPITAL", "1000"))
RISK_P = float(os.getenv("RISK_PERCENT", "1")) / 100.0

TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# ------------ CONSTANTES ------------
RESO_TO_SEC = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}

# ------------ FUNÇÕES UTIL ------------
def notify(text: str) -> None:
    """Envia mensagem para Telegram sem dependências assíncronas."""
    if not TG_TOKEN or not TG_CHAT:
        print("[TELEGRAM] Falta TG token/chat. Msg:", text)
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT, "text": text}, timeout=10)
    except Exception as e:
        print("[TELEGRAM] Erro ao enviar:", e)


def fetch_candles(pair: str, resolution: str, days: int = 30) -> pd.DataFrame:
    """Vai buscar candles ao endpoint público do Coinbase Exchange (sem auth)."""
    gran = RESO_TO_SEC.get(resolution, 3600)
    end = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = end - days * 24 * 3600

    url = f"https://api.exchange.coinbase.com/products/{pair}/candles"
    params = {"granularity": gran, "start": start, "end": end}
    headers = {"User-Agent": "ma9-ma21-bot/1.0"}

    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()

    if not isinstance(data, list) or len(data) == 0:
        raise RuntimeError("Sem dados de candles recebidos.")

    df = pd.DataFrame(data, columns=["time","low","high","open","close","volume"])
    df = df.sort_values("time").reset_index(drop=True)

    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula MAs, sinais e filtros simples."""
    df["MA9"]   = df["close"].rolling(9).mean()
    df["MA21"]  = df["close"].rolling(21).mean()
    df["MA200"] = df["close"].rolling(200).mean()

    df["cross_up"] = (df["MA9"].shift(1) <= df["MA21"].shift(1)) & (df["MA9"] > df["MA21"])
    df["cross_dn"] = (df["MA9"].shift(1) >= df["MA21"].shift(1)) & (df["MA9"] < df["MA21"])

    df["VOL_MA20"] = df["volume"].rolling(20).mean()
    df["BUY_SIGNAL"]  = df["cross_up"] & (df["close"] > df["MA200"]) & (df["volume"] > df["VOL_MA20"])
    df["SELL_SIGNAL"] = df["cross_dn"] & (df["close"] < df["MA200"]) & (df["volume"] > df["VOL_MA20"])
    return df


def position_size(price: float) -> float:
    """Calcula tamanho de posição com base no risco fixo."""
    risco_abs = CAPITAL * RISK_P
    stop_dist = 0.02 * price
    if stop_dist <= 0:
        return 0.0
    qty = risco_abs / stop_dist
    return max(0.0, round(qty, 6))


def loop():
    """Loop principal do bot."""
    notify(f"🤖 Bot MA9/MA21 iniciado | Par: {PAIR} | TF: {RESOLUTION}")
    print("[BOOT] Bot iniciado.")

    interval = RESO_TO_SEC.get(RESOLUTION, 3600)

    while True:
        try:
            df = fetch_candles(PAIR, RESOLUTION, days=60)
            df = add_indicators(df)
            last = df.iloc[-1]

            msg_base = f"{PAIR} | {RESOLUTION} | preço: {last['close']:.2f}"

            if bool(last.get("BUY_SIGNAL", False)):
                qty = position_size(float(last["close"]))
                notify(f"🟢 BUY sinal | {msg_base} | size~{qty}")
                print("[SIGNAL] BUY", msg_base, "size~", qty)

            elif bool(last.get("SELL_SIGNAL", False)):
                notify(f"🔴 SELL sinal | {msg_base}")
                print("[SIGNAL] SELL", msg_base)

            else:
                print("[OK] Sem sinal. Última vela:", last["time"])

        except Exception as e:
            print("[ERRO]", repr(e))
            notify(f"⚠️ Erro no bot: {e}")

        # Dorme até à próxima verificação
        sleep_s = max(60, int(interval / 2))
        time.sleep(sleep_s)


# ------------ FLASK SERVER PARA O RENDER ------------
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot MA9/MA21 ativo e online no Render!"


def run_flask():
    """Mantém o serviço online no Render."""
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ------------ ENTRY POINT ------------
if __name__ == "__main__":
    # Lança o loop de trading em paralelo
    threading.Thread(target=loop, daemon=True).start()
    # Inicia o servidor Flask (Render precisa disto)
    run_flask()