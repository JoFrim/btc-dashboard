import requests
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator


INITIAL_CAPITAL = 10000
TRADE_COST_PERCENT = 0.30

def fetch_btc_data(days=1000):
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

    return prices[["date", "close"]].drop_duplicates("date")


def add_indicators(df):
    df = df.copy()

    df["ema20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()
    df["rsi14"] = RSIIndicator(close=df["close"], window=14).rsi()

    return df.dropna().reset_index(drop=True)

def create_backtest_signal(row):
    score = 0

    price = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    ema200 = row["ema200"]
    rsi = row["rsi14"]

    if price > ema200:
        score += 30
    else:
        score -= 30

    if ema20 > ema50:
        score += 25
    else:
        score -= 15

    if 45 <= rsi <= 70:
        score += 25
    elif rsi > 70:
        score -= 10
    else:
        score -= 10

    # Stark köpsignal: positiv lång trend
    if score >= 60:
        return "BUY", score

    # Försiktig recovery-köpsignal:
    # priset är fortfarande under EMA200, men kort trend har vänt upp
    if (
        price > ema50
        and ema20 > ema50
        and 45 <= rsi <= 70
        and score >= 20
    ):
        return "BUY", score

    # Sälj om priset tappar EMA50 eller total score är negativ
    if price < ema50 or score < 0:
        return "SELL", score

    return "HOLD", score



def run_backtest(df):
    cash = INITIAL_CAPITAL
    btc_position = 0
    in_market = False

    results = []

    for _, row in df.iterrows():
        price = row["close"]
        signal, score = create_backtest_signal(row)

        if signal == "BUY" and not in_market:
            trade_cost = cash * (TRADE_COST_PERCENT / 100)
            investable_cash = cash - trade_cost

            btc_position = investable_cash / price
            cash = 0
            in_market = True
            action = "BUY"

        elif signal == "SELL" and in_market:
            gross_cash = btc_position * price
            trade_cost = gross_cash * (TRADE_COST_PERCENT / 100)

            cash = gross_cash - trade_cost
            btc_position = 0
            in_market = False
            action = "SELL"

        else:
            action = "HOLD"

        portfolio_value = cash + btc_position * price

        results.append({
            "date": row["date"],
            "price": price,
            "signal": signal,
            "score": score,
            "action": action,
            "portfolio_value": portfolio_value
        })

    result_df = pd.DataFrame(results)

    buy_and_hold_btc = INITIAL_CAPITAL / df.iloc[0]["close"]
    result_df["buy_and_hold_value"] = buy_and_hold_btc * result_df["price"]

    return result_df


def calculate_stats(result_df):
    final_strategy = result_df.iloc[-1]["portfolio_value"]
    final_hold = result_df.iloc[-1]["buy_and_hold_value"]

    strategy_return = ((final_strategy / INITIAL_CAPITAL) - 1) * 100
    hold_return = ((final_hold / INITIAL_CAPITAL) - 1) * 100

    result_df["strategy_peak"] = result_df["portfolio_value"].cummax()
    result_df["strategy_drawdown"] = (
        (result_df["portfolio_value"] - result_df["strategy_peak"])
        / result_df["strategy_peak"]
    ) * 100

    max_drawdown = result_df["strategy_drawdown"].min()

    trades = result_df[result_df["action"].isin(["BUY", "SELL"])]

    return {
        "final_strategy": round(final_strategy, 2),
        "final_hold": round(final_hold, 2),
        "strategy_return": round(strategy_return, 2),
        "hold_return": round(hold_return, 2),
        "max_drawdown": round(max_drawdown, 2),
        "number_of_trades": len(trades)
    }


def print_report(stats):
    print("\n=== BTC SWING BACKTEST ===")
    print(f"Startkapital: ${INITIAL_CAPITAL}")
    print(f"Antagen handelskostnad: {TRADE_COST_PERCENT} % per köp/sälj")
    print(f"Slutvärde strategi: ${stats['final_strategy']}")
    print(f"Slutvärde buy and hold: ${stats['final_hold']}")
    print(f"Avkastning strategi: {stats['strategy_return']} %")
    print(f"Avkastning buy and hold: {stats['hold_return']} %")
    print(f"Max drawdown strategi: {stats['max_drawdown']} %")
    print(f"Antal köp/sälj-affärer: {stats['number_of_trades']}")

def save_backtest_html(stats, result_df):
    html_path = "backtest.html"

    chart_df = result_df.copy().reset_index(drop=True)

    width = 900
    height = 260
    padding = 35

    min_value = min(
        chart_df["portfolio_value"].min(),
        chart_df["buy_and_hold_value"].min()
    )
    max_value = max(
        chart_df["portfolio_value"].max(),
        chart_df["buy_and_hold_value"].max()
    )

    def make_points(values):
        points = []
        count = len(values)

        for i, value in enumerate(values):
            x = padding + (i / max(count - 1, 1)) * (width - 2 * padding)
            y = height - padding - ((value - min_value) / max(max_value - min_value, 1)) * (height - 2 * padding)
            points.append(f"{round(x, 2)},{round(y, 2)}")

        return " ".join(points)

    strategy_points = make_points(chart_df["portfolio_value"])
    hold_points = make_points(chart_df["buy_and_hold_value"])

    trades_df = result_df[result_df["action"].isin(["BUY", "SELL"])].copy()
    trades_df = trades_df.tail(20).iloc[::-1]

    trade_rows = ""

    for _, row in trades_df.iterrows():
        trade_rows += f"""
        <tr>
            <td>{row["date"]}</td>
            <td>{round(row["price"], 2)}</td>
            <td>{row["signal"]}</td>
            <td>{row["score"]}</td>
            <td>{row["action"]}</td>
            <td>{round(row["portfolio_value"], 2)}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <title>BTC Swing Backtest</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: #f4f4f4;
            color: #222;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: auto;
            background: white;
            padding: 24px;
            border-radius: 16px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 20px 0;
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
            font-size: 24px;
            font-weight: bold;
            margin-top: 6px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 20px;
        }}
        th, td {{
            border-bottom: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background: #f1f5f9;
        }}
        a {{
            color: #1d4ed8;
            text-decoration: none;
            font-weight: bold;
        }}
        .note {{
            background: #fff7ed;
            padding: 16px;
            border-radius: 12px;
            margin-top: 20px;
        }}
        .chart-box {{
            background: #f8f8f8;
        padding: 18px;
        border-radius: 12px;
        margin-top: 20px;
        overflow-x: auto;
    }}
    .legend {{
        display: flex;
        gap: 20px;
        margin-top: 10px;
        font-size: 14px;
    }}
    .legend-item {{
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .legend-line {{
        width: 24px;
        height: 4px;
        display: inline-block;
        border-radius: 4px;
    }}
    .strategy-line {{
        background: #1d4ed8;
    }}
    .hold-line {{
        background: #dc2626;
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
        <h1>BTC Swing Backtest</h1>

        <p>
            <a href="index.html">Dashboard</a> |
            <a href="logg.html">Signal-logg</a>
        </p>

        <div class="grid">
            <div class="card">
                <div class="label">Startkapital</div>
                <div class="value">${INITIAL_CAPITAL}</div>
            </div>

            <div class="card">
                <div class="label">Handelskostnad per köp/sälj</div>
                <div class="value">{TRADE_COST_PERCENT} %</div>
            </div>

            <div class="card">
                <div class="label">Slutvärde strategi</div>
                <div class="value">${stats["final_strategy"]}</div>
            </div>

            <div class="card">
                <div class="label">Slutvärde buy and hold</div>
                <div class="value">${stats["final_hold"]}</div>
            </div>

            <div class="card">
                <div class="label">Avkastning strategi</div>
                <div class="value">{stats["strategy_return"]} %</div>
            </div>

            <div class="card">
                <div class="label">Avkastning buy and hold</div>
                <div class="value">{stats["hold_return"]} %</div>
            </div>

            <div class="card">
                <div class="label">Max drawdown strategi</div>
                <div class="value">{stats["max_drawdown"]} %</div>
            </div>

            <div class="card">
                <div class="label">Antal köp/sälj-affärer</div>
                <div class="value">{stats["number_of_trades"]}</div>
            </div>
        </div>

        <div class="note">
            Strategin jämförs mot buy and hold på BTC/USD. Detta är ett förenklat backtest och tar inte hänsyn till faktisk Virtune-kurs, exakta spreadar, valutaväxling eller skatt.
        </div>

        <h2>Strategi vs Buy and hold</h2>

<div class="chart-box">
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
        <line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#d1d5db" stroke-width="1" />
        <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" stroke="#d1d5db" stroke-width="1" />

        <polyline
            points="{hold_points}"
            fill="none"
            stroke="#dc2626"
            stroke-width="3"
        />

        <polyline
            points="{strategy_points}"
            fill="none"
            stroke="#1d4ed8"
            stroke-width="3"
        />
    </svg>

    <div class="legend">
        <div class="legend-item">
            <span class="legend-line strategy-line"></span>
            Strategi
        </div>
        <div class="legend-item">
            <span class="legend-line hold-line"></span>
            Buy and hold
        </div>
    </div>
</div>

        <h2>Senaste köp/sälj-affärer</h2>

        <table>
            <thead>
                <tr>
                    <th>Datum</th>
                    <th>BTC-pris</th>
                    <th>Signal</th>
                    <th>Score</th>
                    <th>Action</th>
                    <th>Portföljvärde</th>
                </tr>
            </thead>
            <tbody>
                {trade_rows}
            </tbody>
        </table>

        <div class="footer">
            Detta är endast ett analysverktyg och inte finansiell rådgivning.
        </div>
    </div>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as file:
        file.write(html)

if __name__ == "__main__":
    df = fetch_btc_data(days=365)
    df = add_indicators(df)

    result_df = run_backtest(df)
    stats = calculate_stats(result_df)

    result_df.to_csv("backtest_result.csv", index=False)

    print_report(stats)
    save_backtest_html(stats, result_df)

    print("\nResultat sparat i backtest_result.csv")
    print("Backtest-sida sparad i backtest.html")
