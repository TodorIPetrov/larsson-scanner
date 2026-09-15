# 🚀 Larsson Line Market Scanner & Alert System

Автоматизирана система с нулев разход за следене и известяване (alerts) за състоянията на индикатора **Larsson Line (CTO Line)** върху стотици активи едновременно (Crypto, US Stocks, International Stocks, Commodities, Indices).

---

## 🧮 Математическа формула и логика на състоянията

Индикаторът използва панделка (ribbon) от 4 Smoothed Moving Averages (SMMA / Wilder's MA) върху цена `hl2 = (High + Low) / 2`:
- **Периоди:** $v_1 = 15$, $m_1 = 19$, $m_2 = 25$, $v_2 = 29$
- **Инициализация:** Първите $N$ бара се изчисляват като обикновена средна $\text{SMA}(\text{hl2}, N)$.
- **Рекурентно изглаждане:**
  $$\text{SMMA}_i = \frac{\text{SMMA}_{i-1} \times (N - 1) + \text{hl2}_i}{N}$$

### Класификация на състоянията:
- 🟡 **Gold (Bullish):** $v_1 \ge m_1$ И $m_2 \ge v_2$ И $v_1 \ge v_2$ (възходяща подредба на панделката)
- 🔵 **Blue (Bearish):** $v_1 < m_1$ И $m_2 < v_2$ И $v_1 < v_2$ (низходяща подредба на панделката)
- ⚪ **Neutral (Consolidation):** Всяко разминаване / пресичане между линиите

---

## 🏗️ Архитектура

- **Data Fetcher:** Binance REST API (безплатен, без API ключ за публични пазарни данни, с автоматичен подбор на най-ликвидните USDT двойки)
- **Engine:** Векторизиран NumPy алгоритъм с прецизност `float64`
- **Persistence:** SQLite с активиран **WAL (Write-Ahead Logging)** режим за светкавичен запис и четене
- **Alerts:** Telegram Bot API с HTML форматиране, emoji маркери, anti-spam групиране и директни линкове към TradingView
- **Scheduler:** Вграден APScheduler daemon за автоматизирано сканиране по график (1D в 00:02 UTC, 4H на всеки 4 часа, 1W в понеделник 00:05 UTC)
- **Dashboard:** Статичен уеб интерфейс с тъмна тема, sentiment bar и търсачка

---

## 📦 Инсталация

1. Клонирайте хранилището и активирайте виртуалната среда:
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
```

2. Инсталирайте зависимостите:
```bash
pip install -r requirements.txt
```

---

## ⚙️ Конфигурация на Telegram известяването

Отворете `config/settings.yaml` и попълнете вашите данни (или ги подайте като environment variables):

```yaml
telegram:
  bot_token: "ВАШИЯТ_BOT_TOKEN"      # Взема се безплатно от @BotFather
  chat_id: "ВАШИЯТ_CHAT_ID"          # Вашият Telegram ID или ID на канал/група
  batch_threshold: 5                 # Ако има над 5 промени едновременно, изпраща 1 обобщено съобщение
```

*Забележка: Докато не въведете Telegram токен, системата работи в безопасен `DRY-RUN` режим и логва съобщенията в конзолата.*

---

## 🕹️ Начин на употреба

### 1. Ръчно сканиране на пазара (On-demand)
```bash
# Сканиране на ВСИЧКИ пазари едновременно (Crypto, Stocks, Commodities, Indices):
python src/main.py --scan --asset-class all --timeframe 1D

# Сканиране само на определен клас актив:
python src/main.py --scan --asset-class crypto --limit 50 --timeframe 1D
python src/main.py --scan --asset-class us_stocks --timeframe 1D
python src/main.py --scan --asset-class intl_stocks --timeframe 1D
python src/main.py --scan --asset-class commodities --timeframe 1D
python src/main.py --scan --asset-class indices --timeframe 1D

# Седмично сканиране (1W):
python src/main.py --scan --asset-class all --timeframe 1W

# 4-часово сканиране (само за Crypto):
python src/main.py --scan --asset-class crypto --timeframe 4H
```

### 2. Преглед на текущите състояния в конзолата
```bash
# Всички активи:
python src/main.py --status

# Филтриране само по клас:
python src/main.py --status --asset-class commodities
python src/main.py --status --asset-class us_stocks
```

### 3. Автоматичен 24/7 фонов режим (Scheduler)
```bash
python src/main.py --scheduler
```
*График на автоматичното сканиране:*
- `Crypto 1D`: Всеки ден в 00:02 UTC
- `Crypto 4H`: На всеки 4 часа (00:02, 04:02, 08:02, 12:02, 16:02, 20:02 UTC)
- `Crypto 1W`: Всеки понеделник в 00:05 UTC
- `Stocks & Commodities 1D`: Понеделник - Петък в 21:05 UTC (след затварянето на Wall Street)
- `Stocks & Commodities 1W`: Всеки петък в 21:10 UTC

### 4. Стартиране на Уеб Дашборда
```bash
# Експортиране на последните данни:
python src/main.py --export-dashboard

# Стартиране на локален уеб сървър:
python -m http.server 8080 -d dashboard
```
Отворете браузъра на `http://localhost:8080` за достъп до интерактивния дашборд.

---

## 🧪 Тестове

Цялата математика, състояния, база данни и форматиране са покрити с автоматични тестове:
```bash
pytest tests/
```
Всички 16 теста се изпълняват за под 4 секунди.
