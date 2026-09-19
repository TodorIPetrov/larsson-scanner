# ☁️ 24/7 Автономна Работа в Облака (Когато Компютърът е Изключен)

Тази документация описва двете решения за 24/7 работа в облака, така че системата да сканира пазарите, да изпраща известия в Telegram и да обновява сайта, без компютърът ти изобщо да е включен.

---

## 🧭 Двата Подхода — Каква е разликата?

| Възможност | Подход 1: GitHub Actions (Периодичен график) | Подход 2: Render.com / Koyeb (24/7 Контейнер) |
| :--- | :--- | :--- |
| **Цена** | 100% Безплатно (GitHub) | 100% Безплатно (Free Tier) |
| **Периодични сканирания** | ✅ Да (всеки 4 ч + в 11:00 и 23:05 БГ време) | ✅ Да (непрекъснато по график) |
| **Обновяване на сайта** | ✅ Да ([GitHub Pages](https://todoripetrov.github.io/larsson-scanner/)) | ✅ Да (GitHub Pages + собствен URL) |
| **Telegram известия за сигнали** | ✅ Да (при всяко планирано сканиране) | ✅ Да (на секундата при candle close) |
| **Интерактивен чат с бота** (`/scan`, `/status`, `/alpha`) | ❌ Не (GitHub Actions се изключва след изпълнение) | ✅ **Да! Ботът отговаря мигновено на съобщения 24/7** |
| **WebSocket на живо (Binance)** | ❌ Не (няма постоянен сокет) | ✅ **Да (постоянна WebSocket връзка)** |

---

## 🛠️ Подход 1: GitHub Actions (Вече настроен и коригиран)

### 1. Добавяне на тайните ключове в GitHub Secrets:
1. Отвори хранилището в браузъра: [**https://github.com/TodorIPetrov/larsson-scanner**](https://github.com/TodorIPetrov/larsson-scanner)
2. Кликни на таб **Settings** (горе вдясно) ⚙️.
3. В лявото меню избери **Secrets and variables** ➡️ **Actions**.
4. Кликни върху зеления бутон **New repository secret**:
   - **Secret 1**:
     - *Name*: `TELEGRAM_BOT_TOKEN`
     - *Secret*: `8875473177:AAHB3HbEuF764xf7lqzMZwLC7wycsQ8DyxE`
   - **Secret 2**:
     - *Name*: `TELEGRAM_CHAT_ID`
     - *Secret*: `8464055753`

### 2. Активиране на права за запис (Workflow Permissions):
*Важно за автоматично обновяване на сайта при сканиране:*
1. В **Settings** ➡️ вляво избери **Actions** ➡️ **General**.
2. Превърти надолу до секция **Workflow permissions**.
3. Избери **Read and write permissions**.
4. Кликни **Save**.

### 3. Ръчно стартиране от телефона:
1. Отвори `https://github.com/TodorIPetrov/larsson-scanner/actions` през телефона.
2. Избери **24/7 Autonomous Market Scanner**.
3. Кликни **Run workflow** ➡️ избери `all` ➡️ кликни **Run workflow**.
4. След ~35 секунди резултатите ще пристигнат в Telegram!

---

## 🚀 Подход 2: Render.com (Препоръчително за интерактивен Telegram бот 24/7)

Ако искаш ботът `@CTO_larsson_bot` да отговаря в Telegram, когато му пишеш `/scan`, `/status`, `/gold`, `/portfolio` от телефона с изключен компютър:

1. Отиди на [**https://render.com**](https://render.com) и се логни с твоя GitHub акаунт.
2. Кликни на **New +** (горе вдясно) ➡️ избери **Web Service**.
3. Избери твоето хранилище `TodorIPetrov/larsson-scanner`.
4. Попълни настройките (отнема 1 минута):
   - **Name**: `larsson-scanner`
   - **Region**: `Frankfurt (EU Central)`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python src/main.py --scheduler`
   - **Instance Type**: `Free` ($0/месец)
5. В секция **Environment Variables** добави:
   - `TELEGRAM_BOT_TOKEN`: `8875473177:AAHB3HbEuF764xf7lqzMZwLC7wycsQ8DyxE`
   - `TELEGRAM_CHAT_ID`: `8464055753`
   - `PORT`: `10000`
6. Кликни **Deploy Web Service**!

От този момент:
- Render поддържа контейнера жив 24/7/365.
- Ботът слуша за команди денонощно.
- Binance WebSocket следи пазара в реално време.
- Сайтът е достъпен и на GitHub Pages, и на Render URL.
