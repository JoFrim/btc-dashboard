import requests
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
import csv
from pathlib import Path


BTC_PER_VIRTUNE_PRIME_ETP = 0.00009976


def fetch_btc_data(days=365):
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"

    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily"
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    prices = pd.DataFrame(data["prices"], columns=["timestamp", "close"])
    prices["date"] = pd.to_datetime(prices["timestamp"], unit="ms")

    return prices[["date", "close"]]


def fetch_usd_sek_rate():
    url = "https://api.frankfurter.app/latest"

    params = {
        "from": "USD",
        "to": "SEK"
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()
    return data["rates"]["SEK"]


def add_indicators(df):
    df = df.copy()

    df["ema20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()
    df["rsi14"] = RSIIndicator(close=df["close"], window=14).rsi()

    return df.dropna()


def create_signal(df):
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    
    price = latest["close"]
    btc_change_24h = ((price - previous["close"]) / previous["close"]) * 100
    usd_sek = fetch_usd_sek_rate()
    virtune_estimated_price = price * usd_sek * BTC_PER_VIRTUNE_PRIME_ETP

    ema20 = latest["ema20"]
    ema50 = latest["ema50"]
    ema200 = latest["ema200"]
    rsi = latest["rsi14"]

    score = 0
    comments = []

    if price > ema200:
        score += 30
        comments.append("Priset är över EMA200: lång trend är positiv.")
    else:
        score -= 30
        comments.append("Priset är under EMA200: lång trend är negativ.")
    if btc_change_24h > 5:
        risk_comment = "BTC är upp kraftigt senaste dygnet. Jaga inte öppningen på Avanza; vänta gärna 30–60 minuter."
    elif btc_change_24h < -5:
        risk_comment = "BTC är ner kraftigt senaste dygnet. Risk för stressad handel och bred spread i ETP:n."
    elif rsi > 70:
        risk_comment = "RSI är högt. Trenden är positiv men nytt köp bör göras försiktigt."
    elif price < ema50:
        risk_comment = "Priset är under EMA50. Swingläget är svagare och risken är förhöjd."
    else:
        risk_comment = "Ingen extrem dygnsrörelse. Bedöm signalen enligt trend, RSI och egen risknivå."

    if ema20 > ema50:
        score += 25
        comments.append("EMA20 är över EMA50: kort trend är positiv.")
    else:
        score -= 15
        comments.append("EMA20 är under EMA50: kort trend är svag.")

    if 45 <= rsi <= 70:
        score += 25
        comments.append("RSI ligger i ett bra swing trade-intervall.")
    elif rsi > 70:
        score -= 10
        comments.append("RSI är högt: risk för överköpt läge.")
    else:
        score -= 10
        comments.append("RSI är svagt: momentum är inte optimalt.")

    if score >= 60:
        signal = "KÖP / ÖKA FÖRSIKTIGT"
    elif score >= 25:
        signal = "BEHÅLL / AVVAKTA NYTT KÖP"
    elif score >= 0:
        signal = "AVVAKTA"
    else:
        signal = "SÄLJ / MINSKA RISK"
    if signal == "KÖP / ÖKA FÖRSIKTIGT":
        avanza_action = "Bevaka köpläge i Virtune Prime. Köp endast liten post och undvik att jaga öppningen."
    elif signal == "BEHÅLL / AVVAKTA NYTT KÖP":
        avanza_action = "Behåll eventuell befintlig position. Avvakta nytt köp tills signalen blir starkare."
    elif signal == "AVVAKTA":
        avanza_action = "Gör inget köp på Avanza idag. Följ marknaden och vänta på tydligare trend."
    else:
        avanza_action = "Minska risk eller sälj del av positionen om du redan äger Virtune Prime."

    return {
        "date": latest["date"].date(),
        "price": round(price, 2),
        "usd_sek": round(usd_sek, 4),
        "virtune_estimated_price_sek": round(virtune_estimated_price, 2),
        "btc_change_24h": round(btc_change_24h, 2),
        "risk_comment": risk_comment,
        "rsi": round(rsi, 1),
        "score": score,
        "signal": signal,
        "avanza_action": avanza_action,
        "comments": comments
    }


def print_report(signal):
    print("\n=== BTC SWING TRADE ANALYS ===")
    print(f"Datum: {signal['date']}")
    print(f"BTC-pris: ${signal['price']}")
    print(f"USD/SEK: {signal['usd_sek']}")
    print(f"Beräknat Virtune Prime-värde: ca {signal['virtune_estimated_price_sek']} SEK")
    print(f"BTC-förändring senaste dygnet: {signal['btc_change_24h']} %")
    print(f"RSI: {signal['rsi']}")
    print(f"Signalstyrka: {signal['score']}/100")
    print(f"Signal: {signal['signal']}")
    print(f"Riskkommentar: {signal['risk_comment']}")
    print(f"Avanza-åtgärd: {signal['avanza_action']}")

    print("\nKommentar:")
    for comment in signal["comments"]:
        print(f"- {comment}")

def save_signal_to_csv(signal):
    file_path = Path("btc_signal_logg.csv")
    file_exists = file_path.exists()

    fieldnames = [
        "date",
        "price",
        "usd_sek",
        "virtune_estimated_price_sek",
        "btc_change_24h",
        "rsi",
        "score",
        "signal",
        "risk_comment",
        "avanza_action",
    ]

    with open(file_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "date": signal["date"],
            "price": signal["price"],
            "usd_sek": signal["usd_sek"],
            "virtune_estimated_price_sek": signal["virtune_estimated_price_sek"],
            "btc_change_24h": signal["btc_change_24h"],
            "rsi": signal["rsi"],
            "score": signal["score"],
            "signal": signal["signal"],
            "risk_comment": signal["risk_comment"],
            "avanza_action": signal["avanza_action"]
        })


def save_dashboard_html(signal):
    file_path = Path("btc_dashboard.html")

    html = f"""
    <!DOCTYPE html>
    <html lang="sv">
    <head>
    <meta charset="UTF-8">
        <title>BTC Swing Trade Dashboard</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #f4f4f4;
                color: #222;
                padding: 30px;
            }}
            .container {{
                max-width: 850px;
                margin: auto;
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            }}
            h1 {{
                margin-top: 0;
            }}
            .signal {{
                font-size: 28px;
                font-weight: bold;
                padding: 20px;
                border-radius: 12px;
                background: #eef2ff;
                margin-bottom: 20px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-bottom: 25px;
            }}
            .card {{
                background: #f8f8f8;
                padding: 18px;
                border-radius: 12px;
            }}
            .label {{
                font-size: 13px;
                color: #666;
            }}
            .value {{
                font-size: 22px;
                font-weight: bold;
                margin-top: 6px;
            }}
            .risk {{
                background: #fff7ed;
                padding: 18px;
                border-radius: 12px;
                margin-bottom: 25px;
            }}
            ul {{
                line-height: 1.6;
            }}
            .footer {{
                font-size: 12px;
                color: #777;
                margin-top: 25px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>BTC Swing Trade Dashboard</h1>

            <div class="signal">
                Signal: {signal["signal"]}
            </div>

            <div class="grid">
                <div class="card">
                    <div class="label">Datum</div>
                    <div class="value">{signal["date"]}</div>
            </div>

            <div class="card">
                <div class="label">BTC-pris</div>
                <div class="value">${signal["price"]}</div>
            </div>

            <div class="card">
                <div class="label">USD/SEK</div>
                <div class="value">{signal["usd_sek"]}</div>
            </div>

            <div class="card">
                <div class="label">Beräknat Virtune Prime-värde</div>
                <div class="value">{signal["virtune_estimated_price_sek"]} SEK</div>
            </div>

            <div class="card">
                <div class="label">BTC-förändring senaste dygnet</div>
                <div class="value">{signal["btc_change_24h"]} %</div>
            </div>

            <div class="card">
                <div class="label">RSI</div>
                <div class="value">{signal["rsi"]}</div>
            </div>

            <div class="card">
                <div class="label">Signalstyrka</div>
                <div class="value">{signal["score"]}/100</div>
            </div>
        </div>

        <div class="risk">
            <strong>Riskkommentar:</strong><br>
            {signal["risk_comment"]}
        </div>

        <div class="risk">
            <strong>Rekommenderad åtgärd på Avanza:</strong><br>
            {signal["avanza_action"]}
        </div>
        
        <h2>Motivering</h2>
        <ul>
            {"".join(f"<li>{comment}</li>" for comment in signal["comments"])}
        </ul>

        <div class="footer">
            <p>
                <a href="logg.html">Öppna signal-loggen</a>
            </p>
            <p>
                Detta är en analysrapport och inte finansiell rådgivning. Handla alltid manuellt och med egen riskkontroll.
            </p>
        </div>
        
    </div>
</body>
</html>
"""

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(html)
def save_log_html():
    csv_path = Path("btc_signal_logg.csv")
    html_path = Path("logg.html")

    if not csv_path.exists():
        return

    df = pd.read_csv(csv_path)

    # Visa senaste raderna överst
    df = df.tail(50).iloc[::-1]

    rows_html = ""

    for _, row in df.iterrows():
        rows_html += f"""
        <tr>
            <td>{row.get("date", "")}</td>
            <td>{row.get("price", "")}</td>
            <td>{row.get("usd_sek", "")}</td>
            <td>{row.get("virtune_estimated_price_sek", "")}</td>
            <td>{row.get("btc_change_24h", "")}</td>
            <td>{row.get("rsi", "")}</td>
            <td>{row.get("score", "")}</td>
            <td>{row.get("signal", "")}</td>
            <td>{row.get("risk_comment", "")}</td>
            <td>{row.get("avanza_action", "")}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <title>BTC Signal-logg</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: #f4f4f4;
            color: #222;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: auto;
            background: white;
            padding: 24px;
            border-radius: 16px;
        }}
        h1 {{
            margin-top: 0;
        }}
        a {{
            color: #1d4ed8;
            text-decoration: none;
            font-weight: bold;
        }}
        .table-wrap {{
            overflow-x: auto;
            margin-top: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            border-bottom: 1px solid #ddd;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background: #f1f5f9;
            position: sticky;
            top: 0;
        }}
        tr:hover {{
            background: #f8fafc;
        }}
        .footer {{
            font-size: 12px;
            color: #777;
            margin-top: 25px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC Signal-logg</h1>

        <p>
            <a href="index.html">← Tillbaka till dashboard</a>
        </p>

        <p>Visar de senaste 50 signalerna, nyaste överst.</p>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Datum</th>
                        <th>BTC-pris</th>
                        <th>USD/SEK</th>
                        <th>Virtune ca SEK</th>
                        <th>BTC 24h %</th>
                        <th>RSI</th>
                        <th>Score</th>
                        <th>Signal</th>
                        <th>Riskkommentar</th>
                        <th>Avanza-åtgärd</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="footer">
            Detta är en historisk signal-logg och inte finansiell rådgivning.
        </div>
    </div>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as file:
        file.write(html)

if __name__ == "__main__":
    df = fetch_btc_data()
    df = add_indicators(df)
    signal = create_signal(df)
    print_report(signal)
    save_signal_to_csv(signal)
    save_dashboard_html(signal)
    save_log_html()
