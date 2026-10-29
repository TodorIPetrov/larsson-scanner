# 🔬 Доклад: Quantamental Value-Dip Лаборатория (2016–2026)

## 1. Резюме на Изследването
- **Тествани активи:** 384 корпоративни акции с институционални DCF/EVA профили.
- **Период на симулация:** 2016–2026 г. (включващ QT разпродажбата от 2018 г., COVID паниката от 2020 г., мечия пазар от 2022 г. и AI експанзията 2023–2026 г.).
- **Одобрени за покупка на спад (`value_dip_allowed = True`):** **23 актива (6.0%)**
- **Забранени за купуване на спад (`value_dip_allowed = False`):** **361 актива (94.0%)**
  - *Извод:* При 361 от акциите купуването на спад в `BLUE` исторически води до лоши резултати (Value Trap). За тях системата налага **строга забрана** и търгува **единствено по тренда в `GOLD`**!

---

## 2. Разпределение на 4-те Value Стратегии сред Одобрените Лидери

| Стратегия | Брой Печеливши Акции | Дял | Описание на Тригера |
| :--- | :---: | :---: | :--- |
| **`V1_SMA200_BOUNCE`** | 8 | 34.8% | Институционална подкрепа на 200-дневната пълзяща средна при възходящ тренд. |
| **`V2_SPRING_REVERSAL`** | 0 | 0.0% | Преход от `BLUE` към `NEUTRAL` със затваряне над $v_1$ и стоп под локалното дъно. |
| **`V3_CAPITULATION_S1`** | 10 | 43.5% | Капитулация на структурна подкрепа $S_1$ с обръщане на RSI от свръхпродаденост. |
| **`V4_VALUE_GOLD_HOLD`** | 5 | 21.7% | Златен пробив на подценена качествена компания с дълго задържане. |

---

## 3. Топ 20 Одобрени Компании за Покупка на Спад (с най-висок Sharpe & Win Rate)

| Тикер | Име | Сектор | Оптимална Value Стратегия | Win Rate % | Sharpe | CAGR % | Max DD % |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **4938.TW** | PEGATRON CORPORATION | Technology | `V3_CAPITULATION_S1` | **50.0%** | **1.18** | +27.1% | -19.7% |
| **META** | Meta Platforms, Inc. | Communication Services | `V4_VALUE_GOLD_HOLD` | **66.7%** | **1.12** | +33.4% | -33.1% |
| **2345.TW** | ACCTON TECHNOLOGY CORP | Technology | `V3_CAPITULATION_S1` | **75.0%** | **1.04** | +35.3% | -30.5% |
| **ASWD.DE** | HANetf Sprott Pure Play Copper Miners UCITS ETF | Базови ресурси & Енергиен преход | `V1_SMA200_BOUNCE` | **25.0%** | **0.94** | +31.3% | -27.3% |
| **GILD** | Gilead Sciences, Inc. | Healthcare | `V1_SMA200_BOUNCE` | **50.0%** | **0.91** | +17.4% | -22.0% |
| **6383.T** | DAIFUKU CO LTD | Industrials | `V3_CAPITULATION_S1` | **33.3%** | **0.89** | +23.6% | -27.6% |
| **1513.TW** | CHUNG HSIN ELECTRIC & MACHINERY | Industrials | `V3_CAPITULATION_S1` | **50.0%** | **0.88** | +17.3% | -28.8% |
| **NFLX** | Netflix, Inc. | Communication Services | `V4_VALUE_GOLD_HOLD` | **40.0%** | **0.84** | +19.5% | -25.7% |
| **GDIG.MI** | VanEck S&P Global Mining UCITS ETF (Acc) | Минен сектор & Базови ресурси | `V3_CAPITULATION_S1` | **50.0%** | **0.74** | +12.3% | -22.7% |
| **EG** | Everest Group, Ltd. | Financial Services | `V3_CAPITULATION_S1` | **80.0%** | **0.67** | +9.1% | -16.8% |
| **HIG** | The Hartford Insurance Group, I | Financial Services | `V1_SMA200_BOUNCE` | **33.3%** | **0.67** | +10.7% | -21.8% |
| **CPRT** | Copart, Inc. | Industrials | `V3_CAPITULATION_S1` | **22.2%** | **0.64** | +8.9% | -23.7% |
| **HAS** | Hasbro, Inc. | Consumer Cyclical | `V4_VALUE_GOLD_HOLD` | **50.0%** | **0.62** | +11.7% | -25.1% |
| **BATE.DE** | L&G Battery Value-Chain UCITS ETF (Acc) | Чисти технологии & Батерии | `V1_SMA200_BOUNCE` | **50.0%** | **0.6** | +9.3% | -26.5% |
| **BKNG** | Booking Holdings Inc. Common St | Consumer Cyclical | `V1_SMA200_BOUNCE` | **57.1%** | **0.59** | +9.0% | -22.1% |
| **GL** | Globe Life Inc. | Financial Services | `V3_CAPITULATION_S1` | **66.7%** | **0.58** | +7.1% | -14.7% |
| **0700.HK** | TENCENT | Communication Services | `V4_VALUE_GOLD_HOLD` | **100.0%** | **0.57** | +11.1% | -26.5% |
| **BATT.MI** | L&G Battery Value-Chain UCITS ETF (Milan) | Чисти технологии & Батерии | `V1_SMA200_BOUNCE` | **50.0%** | **0.57** | +8.8% | -27.4% |
| **ACGL** | Arch Capital Group Ltd. | Financial Services | `V3_CAPITULATION_S1` | **66.7%** | **0.54** | +5.5% | -17.3% |
| **FISV** | Fiserv, Inc. | General Corporate | `V1_SMA200_BOUNCE` | **29.4%** | **0.53** | +7.3% | -25.6% |


---

## 4. Примери за Активи със Строга Забрана за Покупка на Спад (`Value Trap Protection`)

| Тикер | Име | Сектор | Статус | Причина за Забраната |
| :--- | :--- | :--- | :---: | :--- |
| **3443.TW** | GLOBAL UNICHIP CORP. | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **1519.TW** | FORTUNE ELECTRIC CO LTD | Industrials | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **3017.TW** | ASIA VITAL COMPONENTS CO LTD | Technology | **🚫 ЗАБРАНЕН** | Прекалено дълбок мечи спад в миналото |
| **3711.TW** | ASE TECHNOLOGY HOLDING CO LTD | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **298040.KS** | HYOSUNG HEAVY | Industrials | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **GE** | GE Aerospace | Industrials | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **2330.TW** | TAIWAN SEMICONDUCTOR MANUFACTUR | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **ALV.DE** | Allianz SE                    v | Financial Services | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **267260.KS** | HD HYUNDAI ELECTRIC | Industrials | **🚫 ЗАБРАНЕН** | Прекалено дълбок мечи спад в миналото |
| **3037.TW** | UNIMICRON TECHNOLOGY | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **6857.T** | ADVANTEST CORP | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **EME** | EMCOR Group, Inc. | Industrials | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **DELL** | Dell Technologies Inc. | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |
| **PLTR** | Palantir Technologies Inc. | Information Technology | **🚫 ЗАБРАНЕН** | Прекалено дълбок мечи спад в миналото |
| **000660.KS** | SK hynix | Technology | **🚫 ЗАБРАНЕН** | Ниска рентабилност/Без ров |

