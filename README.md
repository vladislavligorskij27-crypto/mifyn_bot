README_RAW_TEXT = """
# 🇧🇾 MyFin Currency Telegram Bot

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Cloudflare Workers](https://img.shields.io/badge/Cloudflare-Workers-F38020.svg)](https://workers.cloudflare.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MyFin Currency Bot** — это высокопроизводительный асинхронный Telegram-бот, агрегирующий актуальные банковские курсы валют Республики Беларусь на базе данных портала myfin.by. 

Проект спроектирован с упором на максимальный UX и чистую архитектуру: он умеет отделять физические кассы от онлайн-приложений, рассчитывать прямые кросс-курсы внутри одного банка и генерировать маршруты в Google Картах.

---

## ✨ Ключевые возможности

* 🧮 **Умный калькулятор:** Просто отправьте боту `150 USD` или `1000`, и он мгновенно рассчитает стоимость по наиболее выгодному курсу в вашем городе.
* 🏆 **Раздельные ТОП-5:** Интеллектуальный парсер (State Machine) отличает физические отделения от банковских приложений, выдавая честные рейтинги для обмена наличных.
* 💱 **Прямые кросс-курсы:** Уникальный алгоритм вычисляет выгоду обмена USD ↔ EUR внутри одного отделения, избавляя от потерь на двойной конвертации через BYN.
* 📍 **Геолокация и Карты:** Автоматическая очистка адресов и генерация точных ссылок для построения маршрута в Google Maps.
* ⚙️ **Персонализация:** In-Memory кэширование запоминает выбранный пользователем регион (Минск, областные центры) для быстрого доступа к локальным данным.

---

## 🛠 Технологический стек

* **Core:** Python 3.10+ (Асинхронная архитектура)
* **Web Framework:** FastAPI (поддержка Webhooks)
* **HTTP Client:** HTTPX (асинхронные запросы с автоматическим редиректом)
* **Scraping:** BeautifulSoup4 (Defensive parsing, защита от изменения верстки)
* **Деплой:** Поддержка Cloudflare Workers (Pyodide) / Локальный Long Polling

---

## 🚀 Установка и локальный запуск (Long Polling)

Идеально для разработки, отладки и запуска на домашнем ПК или VPS без настройки SSL.

1. **Клонируйте репозиторий:**
   ```bash
   git clone [https://github.com/ВАШ_USERNAME/myfin-currency-bot.git](https://github.com/ВАШ_USERNAME/myfin-currency-bot.git)
   cd myfin-currency-bot
   ```

2. **Создайте и активируйте виртуальное окружение:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Для Windows: venv\Scripts\activate
   ```

3. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Настройте переменные окружения:**
   * Скопируйте шаблон `.env.example` в новый файл `.env`.
   * Откройте `.env` и добавьте токен вашего бота (получить можно у [@BotFather](https://t.me/BotFather)).
   ```env
   BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefgh
   ```

5. **Запустите бота:**
   ```bash
   python myfin.py
   ```
   *При локальном запуске скрипт автоматически удалит установленный Webhook и перейдет в режим Long Polling.*

---

## ☁️ Деплой на Cloudflare Workers (Serverless)

Проект полностью совместим с бесплатным тарифом Cloudflare Workers. Это обеспечивает нулевую стоимость хостинга и высокую доступность (Edge Network).

1. Установите [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/install-and-update/):
   ```bash
   npm install -g wrangler
   ```

2. Авторизуйтесь в Cloudflare:
   ```bash
   wrangler login
   ```

3. Безопасно сохраните токен бота в Cloudflare Secrets:
   ```bash
   wrangler secret put BOT_TOKEN
   ```

4. Опубликуйте воркер:
   ```bash
   wrangler deploy
   ```

5. **Привяжите Webhook:** После успешного деплоя скопируйте выданный URL (например, `https://bot.your-subdomain.workers.dev`) и зарегистрируйте его в Telegram:
   ```
   [https://api.telegram.org/bot](https://api.telegram.org/bot)<ВАШ_BOT_TOKEN>/setWebhook?url=[https://bot.your-subdomain.workers.dev/webhook](https://bot.your-subdomain.workers.dev/webhook)
   ```

---

## 📄 Отказ от ответственности

Данный проект является независимой разработкой с открытым исходным кодом и не аффилирован с порталом myfin.by. Данные предоставляются "как есть" в ознакомительных целях. Автор не несет ответственности за возможные финансовые риски, возникшие при использовании сервиса.

---
*Разработано с ❤️ для удобного финансового мониторинга.*
"""
