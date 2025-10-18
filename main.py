import os, time, pandas as pd
from dotenv import load_dotenv
from telegram import Bot
from coinbase.rest import RESTClient
import ta

load_dotenv()

PAIR = os.getenv("PAIR", "BTC-USD")
CAPITAL = float(os.getenv("CAPITAL", "1000"))
RISK = float(os.getenv("RISK_PERCENT", "1")) / 100
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
client = RESTClient(api_key=os.getenv("COINBASE_KEY"), api_secret=os.getenv("COINBASE_SECRET"))

def notify(msg):
    try:
        bot.send_message(chat_id=CHAT_ID, text=msg)
    except Exception as e:
        print("Erro Telegram:", e)

def get_data():
    import datetime as dt
    import time

    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=30)

    # Obter candles da Coinbase
    candles = client.get_candles(
        product_id=PAIR,
        granularity="FOUR_HOUR",
        start=int(start.timestamp()),
        end=int(end.timestamp())
    )

    # Converter objetos Candle em dicionários
    data = []
    for c in candles:
        data.append({
            "time": c.start,
            "low": float(c.low),
            "high": float(c.high),
            "open": float(c.open),
            "close": float(c.close),
            "volume": float(c.volume)
        })

    if not data:
        raise ValueError("Sem candles devolvidos pela API.")

    # Criar DataFrame
    df = pd.DataFrame(data)
    df = df.sort_values("time")

    # Indicadores técnicos
    df["MA9"] = df["close"].rolling(9).mean()
    df["MA21"] = df["close"].rolling(21).mean()
    df["MA200"] = df["close"].rolling(200).mean()
    df["RSI"] = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    df["VOL_MA20"] = df["volume"].rolling(20).mean()

    # Sinais de compra e venda
    df["cross_up"] = (df["MA9"].shift(1) <= df["MA21"].shift(1)) & (df["MA9"] > df["MA21"])
    df["cross_dn"] = (df["MA9"].shift(1) >= df["MA21"].shift(1)) & (df["MA9"] < df["MA21"])
    df["BUY_SIGNAL"] = df["cross_up"] & (df["close"] > df["MA200"]) & (df["RSI"] > 55) & (df["volume"] > df["VOL_MA20"])
    df["SELL_SIGNAL"] = df["cross_dn"] & (df["close"] < df["MA200"]) & (df["RSI"] < 45) & (df["volume"] > df["VOL_MA20"])

    return df

def loop():
    while True:
        df = get_data()
        last = df.iloc[-1]
        if last["BUY_SIGNAL"]:
            notify(f"🟢 BUY {PAIR} @ {last['close']}")
        elif last["SELL_SIGNAL"]:
            notify(f"🔴 SELL {PAIR} @ {last['close']}")
        time.sleep(60*60*4)

if __name__ == "__main__":
    notify("🤖 Bot iniciado.")
    loop()
