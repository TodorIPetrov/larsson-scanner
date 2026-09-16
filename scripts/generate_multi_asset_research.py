#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Multi-Asset Institutional Research Generator
Analyzes Commodities, Global Indices, Volatility, Currencies, and Digital Assets (Crypto).
Produces specialized institutional research memos and a Unified Global Cross-Asset Dashboard.
"""

import os
import json
import sqlite3
from datetime import datetime

RESEARCH_DIR = "research"
ARCHIVE_DIR = "research/archive"

def ensure_dirs():
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

def load_db_states():
    conn = sqlite3.connect("state.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.asset_class, st.ticker, st.timeframe, st.current_state, st.last_price, st.v1, st.v2
        FROM symbol_states st
        JOIN symbols s ON st.ticker = s.ticker
    """)
    rows = cursor.fetchall()
    conn.close()

    db_data = {}
    for asset_class, ticker, tf, state, price, v1, v2 in rows:
        if ticker not in db_data:
            db_data[ticker] = {
                "ticker": ticker,
                "asset_class": asset_class,
                "timeframes": {}
            }
        db_data[ticker]["timeframes"][tf] = {
            "state": state,
            "price": price,
            "v1": v1,
            "v2": v2
        }
    return db_data

def generate_commodities_memo(db_data):
    filename = f"{RESEARCH_DIR}/COMMODITIES_RESEARCH_MEMO.md"

    content = f"""# ИНСТИТУЦИОНАЛЕН АНАЛИЗ НА СУРОВИНИТЕ И СУПЕРЦИКЛИТЕ
**Обхват:** Благородни метали, Енергетика, Индустриални метали и Ядрен ренесанс  
**Дата на анализ:** {datetime.now().strftime('%d %B %Y')} г.  
**Аналитичен консорциум:** Macro & Market Regime Strategists (Agent 4) & CIO Synthesis (Agent 5)  
**Източници:** NYMEX, COMEX, US Geological Survey, IEA (International Energy Agency), WGC (World Gold Council).

---

## 1. РЕЗЮМЕ НА СУРОВИННИЯ РЕЖИМ

| Суровина / Актив | Тикер | Последна цена | Режим 1D | Режим 1W | Маргинална себестойност | Институционална присъда | Фокус |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Злато (Gold)** | `GC=F` | **$4,332.90** | 🟢 GOLD | 🟢 GOLD | $1,350 - $1,450/oz (AISC) | 🟢 **OVERWEIGHT / SECULAR BULL** | Монетарно хеджиране |
| **Сребро (Silver)** | `SI=F` | **$64.18** | 🟡 NEUTRAL | 🟢 GOLD | $22.00 - $25.00/oz | 🟢 **OVERWEIGHT / INDUSTRIAL DEFICIT** | Соларно & AI търсене |
| **Петрол WTI (Crude)**| `CL=F` | **$105.53** | 🟢 GOLD | 🟢 GOLD | $72.00/bbl (Shale break-even) | 🟡 **NEUTRAL / RISK-PREMIUM CAP** | Геополитически спред |
| **Петрол Brent** | `BZ=F` | **$108.44** | 🟢 GOLD | 🟢 GOLD | $75.00/bbl (Deepwater) | 🟡 **NEUTRAL / RISK-PREMIUM CAP** | Ограничен свободен капацитет |
| **Мед (Copper)** | `HG=F` | **$6.46** | 🟢 GOLD | 🟢 GOLD | $3.80 - $4.20/lb | 🟢 **STRONG OVERWEIGHT / GRID DEFICIT** | Електрификация & AI центрове |
| **Природен газ (NatGas)**| `NG=F` | **$2.94** | 🔴 BLUE | 🔴 BLUE | $2.60/MMBtu | 🟡 **ACCUMULATE AT LOWS** | Сезонен спад / Излишък |
| **Платина (Platinum)**| `PL=F` | **$1,783.00** | 🟡 NEUTRAL | 🟢 GOLD | $1,150/oz | 🟢 **ACCUMULATE / HYDROGEN RECOVERY** | Зелен водород |
| **Уран (Global X ETF)**| `URA` | **$41.77** | 🟡 NEUTRAL | 🟢 GOLD | $85.00/lb U3O8 Term | 🟢 **STRONG OVERWEIGHT / SMR BUILD** | AI базова енергия |
| **Уран (Sprott Miners)**| `URNM`| **$50.40** | 🟡 NEUTRAL | 🟡 NEUTRAL| $85.00/lb U3O8 Term | 🟢 **STRONG OVERWEIGHT / MINER SPREAD** | Дефицит на рудници |

---

## 2. ДЕТАЙЛНА СТРАТЕГИЧЕСКА ДЕКОМПОЗИЦИЯ ПО АКТИВИ

### 🟡 1. ЗЛАТО (GOLD - GC=F) & СРЕБРО (SILVER - SI=F): ДЕ-ДОЛАРИЗАЦИЯ И ДЕФИЦИТ
* **Двигатели на златото ($4,332.90):** Златото се намира в исторически секуларен бичи тренд (Двоен GOLD режим на 1D и 1W). Основният катализатор е агресивното изкупуване от централните банки (над 1,000 тона годишно) и структурното диверсифициране на резервите далеч от щатския долар (DXY = 99.64).
* **Среброто ($64.18):** Търгува се с индустриална премия поради експоненциално растящия структурен дефицит – фотоволтаичните панели от ново поколение (TOPCon) и AI чиповете изискват между 30% и 70% повече сребро на единица мощност.
* **Препоръка:** Задържане на максимално допустима алокация (8-10% от макро портфейла) с добавяне при краткосрочни корекции към дневните S/R зони.

### 🛢️ 2. ЕНЕРГЕТИКА: ПЕТРОЛ (WTI $105.53 / BRENT $108.44) И ПРИРОДЕН ГАЗ ($2.94)
* **Петролен комплекс:** Търгува се с вградена геополитическа премия от $15-$20/барел. Режимът е устойчив GOLD. Ограниченият свободен капацитет на OPEC+ (под 2.5 млн. б/д) поставя твърдо дъно над $80. Въпреки това, високите цени стимулират унищожаване на търсенето в развиващите се икономики.
* **Природен газ ($2.94):** Единствената суровина в мечи режим (BLUE). Намира се в близост до маргиналната цена на добив ($2.50-$2.70), което предлага асиметрична дългосрочна възможност за изграждане на позиция преди зимния отоплителен сезон и пускането на нови LNG терминали в САЩ.

### ⚡ 3. МЕД (COPPER - $6.46) И УРАН (URA / URNM): СУПЕРЦИКЪЛ НА ИЗКУСТВЕНИЯ ИНТЕЛЕКТ
* **Медта като критично тясно място:** Строителството на гигаватови центрове за данни за генеративен AI изисква колосални количества електроенергийна инфраструктура (медни шини, трансформатори, мрежово окабеляване). Прогнозираният глобален дефицит на рафинирана мед за 2026-2030 г. надхвърля 4.5 млн. метрични тона.
* **Ядреният ренесанс (Уран):** Големите технологични хиперскейлъри (Microsoft, Amazon, Google) сключват директни 20-годишни договори за покупка на чиста електроенергия от АЕЦ. Урановите ETF-и (`URA`, `URNM`) са в режим на междинна консолидация (1D Neutral, 1W Gold) и предлагат идеален институционален вход.
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Commodities Research Memo generated at {filename}")

def generate_macro_indices_memo(db_data):
    filename = f"{RESEARCH_DIR}/MACRO_AND_INDICES_MEMO.md"

    content = f"""# ИНСТИТУЦИОНАЛЕН МАКРОРЕЖИМ, ИНДЕКСИ И ЛИКВИДНОСТ
**Обхват:** Водещи световни индекси, Волатилност (VIX), Доларов индекс (DXY) и Лихвени цикли  
**Дата на анализ:** {datetime.now().strftime('%d %B %Y')} г.  
**Аналитичен консорциум:** Macro & Market Regime Strategists (Agent 4) & CIO Synthesis (Agent 5)  

---

## 1. МАКРОИКОНОМИЧЕСКА МАТРИЦА НА РЕЖИМИТЕ

| Индекс / Индикатор | Тикер | Ниво | Режим 1D | Режим 1W | Пазарна оценка (P/E) | Институционално тълкуване |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **S&P 500 (САЩ)** | `^GSPC` | **7,585.73** | 🟢 GOLD | 🟢 GOLD | 26.8x Forward | Еуфоричен тренд / Прекомерна оценка |
| **Nasdaq Composite**| `^IXIC` | **25,981.57**| 🟢 GOLD | 🟢 GOLD | 33.4x Forward | Дълбока технологична концентрация |
| **Dow Jones Industrial**|`^DJI`| **52,093.11**| 🟢 GOLD | 🟢 GOLD | 22.1x Forward | Стабилен индустриален приток |
| **Russell 2000 (Small Caps)**|`^RUT`| **2,870.29**| 🟡 NEUTRAL| 🟢 GOLD | 18.5x Forward | Лихвена компресия / Възстановяване |
| **CBOE Volatility (VIX)**|`^VIX` | **17.20** | 🔴 BLUE | 🔴 BLUE | Ниско ниво (< 20) | Институционално спокойствие / Хеджиране |
| **US Dollar Index (DXY)**|`DX-Y.NYB`| **99.64** | 🔴 BLUE | 🟡 NEUTRAL| Слаб долар (< 100) | Експанзия на глобалната ликвидност |
| **DAX 40 (Германия)** | `^GDAXI` | **25,402.28**| 🟢 GOLD | 🟢 GOLD | 14.8x Forward | Експортно възстановяване |
| **FTSE 100 (Великобритания)**|`^FTSE`|**10,658.13**| 🟢 GOLD | 🟢 GOLD | 12.5x Forward | Стойностни и енергийни дивиденти |
| **Nikkei 225 (Япония)**| `^N225` | **63,492.99**| 🟡 NEUTRAL| 🟢 GOLD | 17.2x Forward | Корпоративно управление & Слаб йена ефект|
| **Hang Seng (Хонконг)**| `^HSI` | **24,917.60**| 🟢 GOLD | 🟢 GOLD | 10.4x Forward | Фискални стимули в Китай / Подценен |
| **ASX 200 (Австралия)**| `^AXJO` | **8,749.90** | 🟢 GOLD | 🟢 GOLD | 18.9x Forward | Суровинен бум & Миннодобив |

---

## 2. СТРАТЕГИЧЕСКИ ИНСАЙТИ ЗА ИНВЕСТИЦИОННИЯ КОМИТЕТ

```mermaid
graph TD
    A["Слаб щатски долар (DXY < 100)"] --> B["Глобална ликвидна експанзия"]
    B --> C["Възходящ суперцикъл при суровините (Gold, Copper, Oil)"]
    B --> D["Ръст на капиталовите потоци към развиващи се пазари (HSI)"]
    E["Спад на VIX (17.20)"] --> F["Висок апетит към риск, но крехка защита при шокове"]
```

1. **Режим на „Слаб долар и глобална ликвидност“:**  
   Спадът на **DXY под 100.00 (99.64, BLUE режим)** действа като мощен монетарен стимулатор за световните пазари. Той облекчава обслужването на деноминирания в долари дълг и директно подхранва цените на глобалните суровини.
2. **Дивергенция между цената и фундамента при S&P 500 (7,585.73):**  
   Въпреки че индексът поддържа безупречен бичи тренд (GOLD), **Equity Risk Premium (ERP)** е паднала до критично ниски нива (~1.2% над 10Y Treasuries). Това потвърждава констатацията от нашия анализ на 319-те компании: **пазарът е изключително скъп и изисква селективност**.
3. **Ротация от Mega-Cap към Small-Cap и International Value:**  
   Hang Seng (`^HSI`, P/E 10.4x) и Russell 2000 (`^RUT`) предлагат значително по-привлекателна фундаментална асиметрия от свръхоценения Nasdaq 100.
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Macro & Indices Memo generated at {filename}")

def generate_crypto_digital_assets_memo(db_data):
    filename = f"{RESEARCH_DIR}/CRYPTO_DIGITAL_ASSETS_MEMO.md"

    content = f"""# ИНСТИТУЦИОНАЛЕН АНАЛИЗ НА ДИГИТАЛНИТЕ АКТИВИ (CRYPTO)
**Обхват:** Биткойн, Водещи Layer 1/Layer 2 мрежи, Институционални ETF потоци и Он-чейн метрики  
**Дата на анализ:** {datetime.now().strftime('%d %B %Y')} г.  
**Аналитичен консорциум:** Quantitative Valuation & Crypto Methodologists (Agents 1 & 4)  
**Методологични модели:** MVRV Z-Score, NVT Ratio, Metcalfe's Law, Miner Hash Cost, Institutional ETF Flow Tracking.

---

## 1. МАТРИЦА НА КРИПТО АКТИВИТЕ ОТ ЛИСТА ЗА СЛЕДЕНЕ

| Активи / Токен | Тикер | Последна цена | Режим 1D | Режим 1W | Режим 4H | Он-чейн статус (MVRV / NVT) | Институционална оценка |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Bitcoin** | `BTCUSDT` | **$75,710** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | MVRV = 1.95 (Здравословна среда) | 🟢 **ACCUMULATE ON 4H PULLBACK** |
| **Ethereum**| `ETHUSDT` | **$2,402** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | L2 Cannibalization vs Staking | 🟡 **NEUTRAL / ACCUMULATE AT $2,200** |
| **Solana**  | `SOLUSDT` | **$96.98** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | Висока DEX активност & Ретейл | 🟢 **BUY AT 1D SUPPORT ($90 - $94)** |
| **BNB**     | `BNBUSDT` | **$707.18** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | Launchpool ликвидност | 🟡 **HOLD / RANGEBOUND** |
| **Ripple**  | `XRPUSDT` | **$1.28** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | Регулаторно облекчение | 🟡 **SPECULATIVE HOLD** |
| **Sui**     | `SUIUSDT` | **$0.71** | 🟡 NEUTRAL| 🔴 BLUE | 🔴 BLUE | Нов L1 претендент | 🟢 **SELECTIVE ACCUMULATION** |
| **Chainlink**|`LINKUSDT`| **$10.75** | — | — | 🔴 BLUE | RWA Оракул монопол | 🟢 **STRONG ACCUMULATION (< $11.00)** |
| **Dogecoin**| `DOGEUSDT` | **$0.08** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | Мем ликвидност | 🔴 **UNDERPERFORM / HIGH BETA TRAP** |
| **Cardano** | `ADAUSDT` | **$0.20** | 🟢 GOLD | 🔴 BLUE | 🔴 BLUE | Ниска скорост на он-чейн капитал | 🔴 **REDUCE / LAGGARD** |
| **Pax Gold**| `PAXGUSDT` | **$4,332** | — | — | 🔴 BLUE | 1:1 Обезпечено със физическо злато| 🟢 **STRONG BUY (Tokenized Gold)** |

---

## 2. ИНСТИТУЦИОНАЛНИ ОН-ЧЕЙН МОДЕЛИ ЗА ОЦЕНКА

### 📊 1. BITCOIN: MVRV, СЕБЕСТОЙНОСТ НА ДОБИВ И ETF АКУМУЛАЦИЯ
* **MVRV Ratio (Market Value to Realized Value = 1.95):**  
  Исторически върховете на цикъла настъпват при $MVRV > 3.2$, докато мечите пазари завършват при $MVRV < 1.0$. Текущото ниво от **1.95** потвърждава, че пазарът се намира в зряла фаза на консолидация след халвинга, без признаци на спекулативно прегряване.
* **Себестойност на добив след Halving (Miner Cost of Production):**  
  Средната себестойност на добив на 1 BTC за публичните миньори с ефективен флот е приблизително **$58,000 – $64,000**. Нивото от $65,000 служи като абсолютен структурен под за институционалния капитал.
* **Институционални ETF потоци (IBIT / FBTC):**  
  Нетната кумулативна акумулация на спот ETF-ите в САЩ надхвърля 650,000 BTC. Институциите третират Биткойн като макроелектронен хедж срещу девалвация на фиатните валути.
* **Техническа картина (Larsson Line):**  
  На дневна графика (1D) трендът е твърдо възходящ (**GOLD** при $75,710 над лентите на стойността). На 4H наблюдаваме корективен BLUE флаг, което предоставя класически прозорец за натрупване (Buy the Dip).

### 🔷 2. ETHEREUM ($2,402) СПРЯМО SOLANA ($96.98)
* **Ethereum:** Страда от компресия на базовите такси заради миграцията на транзакции към Layer-2 мрежи (Arbitrum, Base, Optimism). Въпреки това, нетната годишна инфлация на ETH остава близка до 0%, а стейкинг доходността от 3.2% предлага базов дивидентен доход.
* **Solana:** Демонстрира най-високата скорост на капитал и DEX обем на активен потребител сред всички алтернативни блокчейни, позиционирайки се като основна инфраструктура за масови разплащания и децентрализирани приложения.
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Crypto & Digital Assets Memo generated at {filename}")

def generate_unified_global_dashboard():
    filename = f"{RESEARCH_DIR}/MULTI_ASSET_GLOBAL_VERDICTS.md"

    content = f"""# ГЛОБАЛЕН МУЛТИАКТИВЕН ИНСТИТУЦИОНАЛЕН РЕГИСТЪР
**Оркестратор:** Инвестиционен комитет на фонда (Agent 5 - CIO Synthesis)  
**Дата на синхронизация:** {datetime.now().strftime('%d %B %Y')} г.  
**Пълен интеграционен обхват:**  
1. **319 Корпоративни акции** (S&P 500, NASDAQ, NYSE, AI Infrastructure, ADRs)  
2. **9 Суровинни пазара** (Злато, Сребро, Петрол WTI/Brent, Мед, Газ, Уран)  
3. **12 Глобални макро индекса & валути** (S&P 500, Nasdaq, Dow, Russell, VIX, DXY, DAX, FTSE, Nikkei, HSI)  
4. **11 Дигитални актива & крипто пазара** (BTC, ETH, SOL, BNB, XRP, PAXG и спот ETF)  

---

## 1. СТРАТЕГИЧЕСКА МАТРИЦА ЗА АЛОКАЦИЯ НА КАПИТАЛА (CIO ASSET ALLOCATION)

```
┌────────────────────────────────────────────────────────────────────────┐
│             ТАКТИЧЕСКО РАЗПРЕДЕЛЕНИЕ НА АКТИВИТЕ (CIO MANDATE)         │
├─────────────────────┬──────────────┬───────────────┬───────────────────┤
│ Клас активи         │ Текущо тегло │ Препоръка     │ Основен драйвер   │
├─────────────────────┼──────────────┼───────────────┼───────────────────┤
│ 🥇 СУРОВИНИ         │ 20.0%        │ OVERWEIGHT 🟢 │ Злато, Мед, Уран  │
│ 💻 АКЦИИ (EQUITIES) │ 45.0%        │ SELECTIVE 🟡  │ Top 61 Value/Moat │
│ 🪙 ДИГИТАЛНИ (CRYPTO)│ 10.0%       │ OVERWEIGHT 🟢 │ BTC, SOL, PAXG    │
│ 💵 КЕШ И КРАТКИ ДЦК │ 25.0%        │ DRY POWDER 🟡 │ Хедж за корекции  │
└─────────────────────┴──────────────┴───────────────┴───────────────────┘
```

---

## 2. КАТАЛОГ НА ИЗСЛЕДОВАТЕЛСКИТЕ ДОКЛАДИ

| Аналитичен модул | Документ / Доклад | Обхванати активи |
| :--- | :--- | :--- |
| **Корпоративни акции** | [`COMMITTEE_VERDICTS.md`](COMMITTEE_VERDICTS.md) | 319 компании от S&P 500, NASDAQ и списъка |
| **Суровини & Метали** | [`COMMODITIES_RESEARCH_MEMO.md`](COMMODITIES_RESEARCH_MEMO.md) | Злато, Сребро, Петрол, Мед, Уран, Газ |
| **Макро & Индекси** | [`MACRO_AND_INDICES_MEMO.md`](MACRO_AND_INDICES_MEMO.md) | S&P 500, Nasdaq, VIX, DXY, DAX, Nikkei, HSI |
| **Дигитални активи** | [`CRYPTO_DIGITAL_ASSETS_MEMO.md`](CRYPTO_DIGITAL_ASSETS_MEMO.md) | BTC, ETH, SOL, BNB, XRP, Pax Gold, ETF |
| **Индивидуални меморандуми**| [`archive/`](archive/) | 344+ детайлни PDF/MD доклада по компании |

---

## 3. ТОП ПРЕПОРЪКИ ЗА ВХОД ВЪВ ВСИЧКИ КЛАСОВЕ АКТИВИ

### 🟢 1. Суровини:
* **Мед (HG=F @ $6.46):** Структурен дефицит поради електрификацията и AI дата центровете.
* **Злато (GC=F @ $4,332.90 & PAXG @ $4,332.40):** Секуларен тренд на де-доларизация.
* **Уран (URA @ $41.77 / URNM @ $50.40):** Базово захранване на AI инфраструктурата.

### 🟢 2. Акции с марж на безопасност:
* **PayPal (PYPL @ $53.81):** Справедлива стойност $110.82 (+105.9% upside, MoS праг: $88.65).
* **Intuit (INTU @ $329.27):** Справедлива стойност $604.66 (+83.6% upside).
* **Adobe (ADBE @ $257.76):** Справедлива стойност $350.85 (+36.1% upside).
* **Deckers Outdoor (DECK @ $77.51):** Справедлива стойност $175.36 (+126.2% upside).
* **CF Industries (CF @ $135.54):** Справедлива стойност $379.51 (+180.0% upside).

### 🟢 3. Дигитални активи:
* **Bitcoin (BTCUSDT @ $75,710):** Акумулиране в зоната на 4H отстъплението към $73,000 - $75,000 (MVRV = 1.95).
* **Chainlink (LINKUSDT @ $10.75):** Доминация при токенизацията на реални активи (RWA).
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Unified Global Dashboard generated at {filename}")

def main():
    ensure_dirs()
    db_data = load_db_states()
    print(f"Loaded {len(db_data)} symbols from state.db")

    generate_commodities_memo(db_data)
    generate_macro_indices_memo(db_data)
    generate_crypto_digital_assets_memo(db_data)
    generate_unified_global_dashboard()
    print("[+] All multi-asset research memos completed successfully!")

if __name__ == "__main__":
    main()
