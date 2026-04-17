import os
import re
import itertools
import logging
import asyncio
import urllib.parse
from typing import Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from fastapi import FastAPI, Request
import httpx
from bs4 import BeautifulSoup

app = FastAPI(title="CurrencyBot", description="Cloudflare Worker Telegram Bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip(' "\'\r\n')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

USER_CITIES: dict[int, str] = {}

CURRENCIES = ["USD", "EUR", "RUB", "PLN", "CNY", "GBP", "CHF", "KZT", "TRY", "AED", "GEL", "AMD"]

REGIONS = {
    "minsk_reg": {
        "name": "Минск и область", 
        "cities": {"minsk": "Минск", "borisov": "Борисов", "soligorsk": "Солигорск", "molodechno": "Молодечно", "zhodino": "Жодино", "slutsk": "Слуцк"}
    },
    "brest_reg": {
        "name": "Брестская обл.", 
        "cities": {"brest": "Брест", "baranovichi": "Барановичи", "pinsk": "Пинск", "kobrin": "Кобрин", "bereza": "Береза"}
    },
    "vitebsk_reg": {
        "name": "Витебская обл.", 
        "cities": {"vitebsk": "Витебск", "orsha": "Орша", "novopolotsk": "Новополоцк", "polotsk": "Полоцк", "postavy": "Поставы"}
    },
    "gomel_reg": {
        "name": "Гомельская обл.", 
        "cities": {"gomel": "Гомель", "mozyr": "Мозырь", "zhlobin": "Жлобин", "rechitsa": "Речица", "svetlogorsk": "Светлогорск"}
    },
    "grodno_reg": {
        "name": "Гродненская обл.", 
        "cities": {"grodno": "Гродно", "lida": "Лида", "volkovysk": "Волковыск", "smorgon": "Сморгонь", "slonim": "Слоним"}
    },
    "mogilev_reg": {
        "name": "Могилевская обл.", 
        "cities": {"mogilev": "Могилев", "bobruisk": "Бобруйск", "gorki": "Горки", "osipovichi": "Осиповичи", "krichev": "Кричев"}
    }
}

MINSK_LOCATIONS = {
    "all": ("🌍 Все отделения", None),
    "nemiga": ("📍 Немига", "Немига"),
    "vokzal": ("🚂 Ж/Д Вокзал", "Вокзал"),
    "kamenka": ("🏢 Каменная Горка", "Каменная"),
    "dana": ("🛍 Дана Молл", "Мстиславца") 
}

def get_city_name_and_region(target_city_code: str) -> tuple[str, str]:
    for reg_code, reg_data in REGIONS.items():
        if target_city_code in reg_data["cities"]:
            return reg_data["cities"][target_city_code], reg_code
    return "Город", "minsk_reg"


class TelegramUI:
    
    @staticmethod
    def get_persistent_keyboard() -> dict:
        return {
            "keyboard": [
                [{"text": "💵 Продать USD"}, {"text": "💶 Продать EUR"}],
                [{"text": "💱 Кросс-курсы (USD ↔ EUR)"}, {"text": "🧮 Калькулятор"}],
                [{"text": "🌍 Все курсы"}, {"text": "📍 Изменить город"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    @staticmethod
    def get_city_setup_keyboard() -> dict:
        return {"inline_keyboard": [
            [{"text": "Минск", "callback_data": "setcity_minsk"}, {"text": "Брест", "callback_data": "setcity_brest"}],
            [{"text": "Витебск", "callback_data": "setcity_vitebsk"}, {"text": "Гомель", "callback_data": "setcity_gomel"}],
            [{"text": "Гродно", "callback_data": "setcity_grodno"}, {"text": "Могилев", "callback_data": "setcity_mogilev"}]
        ]}

    @staticmethod
    def get_main_menu() -> dict:
        keyboard = [
            [{"text": "🏦 Курсы валют по городам", "callback_data": "menu_rates"}],
            [{"text": "🧮 Умный калькулятор", "callback_data": "menu_calc"}]
        ]
        return {"inline_keyboard": keyboard}

    @staticmethod
    def get_regions_keyboard() -> dict:
        keyboard = []
        row = []
        for reg_code, reg_data in REGIONS.items():
            row.append({"text": reg_data["name"], "callback_data": f"reg_{reg_code}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return {"inline_keyboard": keyboard}

    @staticmethod
    def get_cities_keyboard(region_code: str) -> dict:
        keyboard = []
        row = []
        cities = REGIONS.get(region_code, REGIONS["minsk_reg"])["cities"]
        for city_code, city_name in cities.items():
            row.append({"text": city_name, "callback_data": f"cit_{city_code}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([{"text": "🔙 К областям", "callback_data": "menu_rates"}])
        return {"inline_keyboard": keyboard}

    @staticmethod
    def get_currencies_keyboard(city_code: str) -> dict:
        keyboard = []
        row = []
        for curr in CURRENCIES:
            row.append({"text": curr, "callback_data": f"cur_{city_code}_{curr}"})
            if len(row) == 4: 
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        
        _, reg_code = get_city_name_and_region(city_code)
        keyboard.append([{"text": "🔙 К городам", "callback_data": f"reg_{reg_code}"}])
        return {"inline_keyboard": keyboard}

    @staticmethod
    def get_locations_keyboard(city: str, currency: str) -> dict:
        keyboard = [
            [{"text": "📊 ТОП-5 выгодных курсов", "callback_data": f"top5_{city}_{currency}"}],
            [{"text": MINSK_LOCATIONS["all"][0], "callback_data": f"rate_{city}_{currency}_all"}]
        ]
        row = []
        for loc_key, (loc_name, _) in MINSK_LOCATIONS.items():
            if loc_key == "all": continue
            row.append({"text": loc_name, "callback_data": f"rate_{city}_{currency}_{loc_key}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([{"text": "🔙 К выбору валюты", "callback_data": f"cit_{city}"}])
        return {"inline_keyboard": keyboard}

    @staticmethod
    def get_quick_sell_keyboard(currency: str, city: str) -> dict:
        city_name, _ = get_city_name_and_region(city)
        return {"inline_keyboard": [
            [{"text": f"🌍 Все курсы {currency} ({city_name})", "callback_data": f"rate_{city}_{currency}_all"}],
            [{"text": "🔙 В главное меню", "callback_data": "start_menu"}]
        ]}

    @staticmethod
    def get_calc_keyboard(amount: float, active_curr: str) -> dict:
        keyboard = []
        row = []
        for curr in ["USD", "EUR", "RUB", "PLN", "BYN"]:
            if curr != active_curr:
                row.append({"text": f"В {curr}", "callback_data": f"calc_{amount}_{curr}"})
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return {"inline_keyboard": keyboard}


class MyFinScraper:
    BASE_URL = "https://myfin.by/currency"

    @classmethod
    async def fetch_html(cls, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _parse_float(val_str: str) -> float:
        try:
            return float(val_str.replace(',', '.'))
        except ValueError:
            return 0.0

    @classmethod
    def _extract_main_page_data(cls, html: str) -> Any:
        soup = BeautifulSoup(html, "html.parser")
        current_bank = "Неизвестный банк"
        
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 5: continue 
                
            bank_col = cols[0]
            
            valid_links = [a.get_text(strip=True) for a in bank_col.find_all("a") if a.get_text(strip=True) and "myfin" not in a.get_text(strip=True).lower()]
            link_text = valid_links[0] if valid_links else ""
            
            img = bank_col.find("img")
            
            address_keywords = ["ул.", "г.", "пр-т", "тракт", "пер.", "ш.", "пл.", "тц", "д."]
            is_address = any(kw in link_text.lower() for kw in address_keywords)
            
            if img or not is_address:
                if img and img.get("alt") and "myfin" not in img.get("alt").lower():
                    current_bank = img.get("alt").strip()
                elif link_text:
                    current_bank = link_text
                bank_name = link_text if link_text else current_bank
                address_text = "Основной курс (онлайн / главное отделение)"
            else:
                bank_name = current_bank
                address_text = link_text
            
            all_texts = list(bank_col.stripped_strings)
            bad_words = {'usd', 'eur', 'rub', 'онлайн', 'лучший курс', 'myfin очередь', 'очередь'}
            address_parts = [t for t in all_texts if t and t.lower() not in bad_words and bank_name.lower() not in t.lower()]
            
            if address_text == "Основной курс (онлайн / главное отделение)" and address_parts:
                potential_address = address_parts[0]
                if any(kw in potential_address.lower() for kw in address_keywords):
                    address_text = potential_address

            yield {
                "bank": bank_name,
                "address": address_text,
                "usd_buy": cls._parse_float(cols[1].get_text(strip=True)),
                "usd_sell": cls._parse_float(cols[2].get_text(strip=True)),
                "eur_buy": cls._parse_float(cols[3].get_text(strip=True)),
                "eur_sell": cls._parse_float(cols[4].get_text(strip=True)),
            }

    @classmethod
    def _extract_data(cls, html: str, address_filter: Optional[str], currency: str, is_main_page: bool) -> Any:
        soup = BeautifulSoup(html, "html.parser")
        current_bank = "Неизвестный банк"
        
        if is_main_page and currency in ("usd", "eur", "rub"):
            col_map = {"usd": (1, 2), "eur": (3, 4), "rub": (5, 6)}
            buy_idx, sell_idx = col_map[currency]
        else:
            buy_idx, sell_idx = 1, 2
            
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) <= max(buy_idx, sell_idx): continue
                
            bank_col = cols[0]
            
            valid_links = [a.get_text(strip=True) for a in bank_col.find_all("a") if a.get_text(strip=True) and "myfin" not in a.get_text(strip=True).lower()]
            link_text = valid_links[0] if valid_links else ""
            
            img = bank_col.find("img")
            
            address_keywords = ["ул.", "г.", "пр-т", "тракт", "пер.", "ш.", "пл.", "тц", "д."]
            is_address = any(kw in link_text.lower() for kw in address_keywords)
            
            if img or not is_address:
                if img and img.get("alt") and "myfin" not in img.get("alt").lower():
                    current_bank = img.get("alt").strip()
                elif link_text:
                    current_bank = link_text
                bank_name = link_text if link_text else current_bank
                address_text = "Основной курс (онлайн / главное отделение)"
            else:
                bank_name = current_bank
                address_text = link_text
                
            all_texts = list(bank_col.stripped_strings)
            bad_words = {'usd', 'eur', 'rub', 'онлайн', 'лучший курс', 'myfin очередь', 'очередь'}
            address_parts = [t for t in all_texts if t and t.lower() not in bad_words and bank_name.lower() not in t.lower()]
            
            if address_text == "Основной курс (онлайн / главное отделение)" and address_parts:
                potential_address = address_parts[0]
                if any(kw in potential_address.lower() for kw in address_keywords):
                    address_text = potential_address
            
            buy_str = cols[buy_idx].get_text(strip=True)
            sell_str = cols[sell_idx].get_text(strip=True)
            
            buy_val = cls._parse_float(buy_str)
            sell_val = cls._parse_float(sell_str)
            
            if buy_val == 0.0 and sell_val == 0.0:
                continue
            
            if address_filter:
                filter_lower = address_filter.lower()
                if filter_lower not in address_text.lower() and filter_lower not in bank_name.lower():
                    continue
                    
            yield {
                "bank": bank_name,
                "address": address_text,
                "buy_str": buy_str,
                "sell_str": sell_str,
                "buy": buy_val,
                "sell": sell_val
            }

    @classmethod
    async def get_raw_rates(cls, city: str, currency: str, address_filter: Optional[str] = None) -> list[dict]:
        currency = currency.lower()
        is_main_page = currency in ('usd', 'eur', 'rub')
        
        if is_main_page:
            url = f"{cls.BASE_URL}/{city}"
        else:
            url = f"{cls.BASE_URL}/{city}/{currency}"
        
        try:
            html = await cls.fetch_html(url)
            return list(itertools.islice(cls._extract_data(html, address_filter, currency, is_main_page), 100))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return [] 
            raise

    @classmethod
    async def get_cross_rates_raw(cls, city: str = "minsk") -> list[dict]:
        try:
            html = await cls.fetch_html(f"{cls.BASE_URL}/{city}")
            return list(itertools.islice(cls._extract_main_page_data(html), 100))
        except Exception as e:
            logger.error(f"Cross rates fetching error: {e}")
            return []


class CurrencyService:
    @staticmethod
    def _format_address_line(bank: str, address: str) -> str:
        if "Основной курс" in address or "онлайн" in address.lower():
            return "🌐 <i>Онлайн-банкинг / Приложение</i>"

        display_addr = re.split(r'(?i)контакт-центр|тел\.|пн-пт|ежедневно|\+375', address)[0].strip(' .,')
        search_addr = re.sub(r'(?i)(?:пом\.|помещение|этаж|пав\.|павильон)\s*[\d\w-]+', '', display_addr).strip(' .,')
        clean_bank = re.sub(r'(?i)(приложение|онлайн|курс|выгодно|очередь|будь в курсе)', '', bank).strip()
        
        if not clean_bank:
            clean_bank = "Обмен валют"

        query = f"{clean_bank}, {search_addr}"
        encoded_query = urllib.parse.quote(query)
        gmaps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"

        return f"📍 <a href='{gmaps_url}'>{display_addr}</a>"

    @staticmethod
    async def get_quick_sell_top(currency: str, city: str = "minsk") -> str:
        rates = await MyFinScraper.get_raw_rates(city, currency)
        city_name, _ = get_city_name_and_region(city)
        
        if not rates:
            return f"📭 Актуальные данные для <b>{currency}</b> в городе <b>{city_name}</b> временно недоступны."

        valid_buy = [r for r in rates if r['buy'] > 0]
        online_rates = []
        physical_rates = []
        
        for r in valid_buy:
            if "Основной курс" in r['address'] or "онлайн" in r['address'].lower():
                online_rates.append(r)
            else:
                physical_rates.append(r)

        top_physical = sorted(physical_rates, key=lambda x: x['buy'], reverse=True)[:5]
        top_online = sorted(online_rates, key=lambda x: x['buy'], reverse=True)[:3]

        msg = f"📈 <b>Аналитика: Продажа {currency} банку ({city_name})</b>\n<i>Отображены наиболее выгодные предложения для сдачи валюты.</i>\n\n"
        msg += "🏢 <b>Отделения банков:</b>\n"
        
        if top_physical:
            for i, r in enumerate(top_physical, 1):
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                msg += f"{i}. <b>{r['buy_str']} BYN</b> — {r['bank']}\n   {addr_line}\n"
        else:
            msg += "<i>Нет доступных данных по физическим отделениям.</i>\n"

        if top_online:
            msg += "\n🌐 <b>Мобильные приложения (Онлайн):</b>\n"
            for i, r in enumerate(top_online, 1):
                msg += f"• <b>{r['buy_str']} BYN</b> — {r['bank']}\n"

        return msg

    @staticmethod
    async def get_cross_rates_text(city: str = "minsk") -> str:
        rates = await MyFinScraper.get_cross_rates_raw(city)
        city_name, _ = get_city_name_and_region(city)
        
        if not rates:
            return "⚠️ Ошибка связи с сервером. Невозможно получить данные по кросс-курсам."

        cross_eur_to_usd = []
        cross_usd_to_eur = []

        for r in rates:
            if r['eur_buy'] > 0 and r['usd_sell'] > 0:
                rate = r['eur_buy'] / r['usd_sell']
                cross_eur_to_usd.append({"bank": r['bank'], "address": r['address'], "rate": rate})
            
            if r['usd_buy'] > 0 and r['eur_sell'] > 0:
                rate = r['usd_buy'] / r['eur_sell']
                cross_usd_to_eur.append({"bank": r['bank'], "address": r['address'], "rate": rate})

        def split_and_sort_cross(rate_list):
            online = []
            physical = []
            for r in rate_list:
                if "Основной курс" in r['address'] or "онлайн" in r['address'].lower():
                    online.append(r)
                else:
                    physical.append(r)
            return sorted(physical, key=lambda x: x['rate'], reverse=True)[:5], \
                   sorted(online, key=lambda x: x['rate'], reverse=True)[:3]

        top_eur_usd_phys, top_eur_usd_onl = split_and_sort_cross(cross_eur_to_usd)
        top_usd_eur_phys, top_usd_eur_onl = split_and_sort_cross(cross_usd_to_eur)

        msg = f"💱 <b>Аналитика кросс-курсов ({city_name})</b>\n<i>Расчет оптимальной прямой конвертации внутри одного отделения.</i>\n\n"

        msg += "💶➡️💵 <b>Конвертация EUR в USD:</b>\n"
        msg += "🏢 <i>Отделения банков:</i>\n"
        if top_eur_usd_phys:
            for i, r in enumerate(top_eur_usd_phys, 1):
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                msg += f"{i}. <b>{r['rate']:.4f} USD</b> за 1 EUR\n   🏦 {r['bank']}\n   {addr_line}\n"
        else:
            msg += "<i>Нет доступных данных по физическим отделениям.</i>\n"

        if top_eur_usd_onl:
            msg += "🌐 <i>Онлайн-банкинг:</i>\n"
            for r in top_eur_usd_onl:
                msg += f"• <b>{r['rate']:.4f} USD</b> за 1 EUR — 🏦 {r['bank']}\n"

        msg += "\n💵➡️💶 <b>Конвертация USD в EUR:</b>\n"
        msg += "🏢 <i>Отделения банков:</i>\n"
        if top_usd_eur_phys:
            for i, r in enumerate(top_usd_eur_phys, 1):
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                msg += f"{i}. <b>{r['rate']:.4f} EUR</b> за 1 USD\n   🏦 {r['bank']}\n   {addr_line}\n"
        else:
            msg += "<i>Нет доступных данных по физическим отделениям.</i>\n"

        if top_usd_eur_onl:
            msg += "🌐 <i>Онлайн-банкинг:</i>\n"
            for r in top_usd_eur_onl:
                msg += f"• <b>{r['rate']:.4f} EUR</b> за 1 USD — 🏦 {r['bank']}\n"

        return msg

    @staticmethod
    async def get_top_5_text(city: str, currency: str) -> str:
        city_name, _ = get_city_name_and_region(city)
        rates = await MyFinScraper.get_raw_rates(city, currency)

        if not rates:
            return f"📭 В городе <b>{city_name}</b> актуальные курсы для {currency} не найдены."

        valid_buy = [r for r in rates if r['buy'] > 0]
        valid_sell = [r for r in rates if r['sell'] > 0]

        def split_and_sort(rate_list, key_name, reverse_flag):
            online = []
            physical = []
            for r in rate_list:
                if "Основной курс" in r['address'] or "онлайн" in r['address'].lower():
                    online.append(r)
                else:
                    physical.append(r)
            return sorted(physical, key=lambda x: x[key_name], reverse=reverse_flag)[:5], \
                   sorted(online, key=lambda x: x[key_name], reverse=reverse_flag)[:3]

        top_buy_phys, top_buy_onl = split_and_sort(valid_buy, 'buy', True)
        top_sell_phys, top_sell_onl = split_and_sort(valid_sell, 'sell', False)

        msg = f"📊 <b>ТОП предложений: {currency} ({city_name})</b>\n\n"

        msg += "📥 <b>Вы сдаете (Покупка банком):</b>\n"
        msg += "🏢 <i>Отделения банков:</i>\n"
        if top_buy_phys:
            for i, r in enumerate(top_buy_phys, 1):
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                msg += f"{i}. <b>{r['buy_str']}</b> — {r['bank']}\n   {addr_line}\n"
        else:
            msg += "<i>Нет данных.</i>\n"
            
        if top_buy_onl:
            msg += "🌐 <i>Онлайн-банкинг:</i>\n"
            for r in top_buy_onl:
                msg += f"• <b>{r['buy_str']}</b> — {r['bank']}\n"

        msg += "\n📤 <b>Вы покупаете (Продажа банком):</b>\n"
        msg += "🏢 <i>Отделения банков:</i>\n"
        if top_sell_phys:
            for i, r in enumerate(top_sell_phys, 1):
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                msg += f"{i}. <b>{r['sell_str']}</b> — {r['bank']}\n   {addr_line}\n"
        else:
            msg += "<i>Нет данных.</i>\n"
            
        if top_sell_onl:
            msg += "🌐 <i>Онлайн-банкинг:</i>\n"
            for r in top_sell_onl:
                msg += f"• <b>{r['sell_str']}</b> — {r['bank']}\n"

        return msg

    @staticmethod
    async def format_rates_text(city: str, currency: str, loc_key: str) -> str:
        city_name, _ = get_city_name_and_region(city)
        loc_name, address_filter = MINSK_LOCATIONS.get(loc_key, ("🌍 Все отделения", None)) if city == "minsk" else ("🌍 Все отделения", None)
        
        try:
            rates = await MyFinScraper.get_raw_rates(city, currency, address_filter)
            if not rates:
                return f"📭 Данные по <b>{currency}</b> в городе <b>{city_name}</b> отсутствуют."
                
            lines = []
            for r in rates[:10]:
                addr_line = CurrencyService._format_address_line(r['bank'], r['address'])
                lines.append(f"🏦 <b>{r['bank']}</b>\n{addr_line}\n💵 Покупка: <code>{r['buy_str']}</code> | Продажа: <code>{r['sell_str']}</code>")
            return "\n\n".join(lines)
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            return "⚠️ Внутренняя ошибка сервера при обработке данных."

    @staticmethod
    async def calculate_exchange(amount: float, currency: str) -> tuple[str, dict]:
        currency = currency.upper()
        
        if currency == "BYN":
            return await CurrencyService._calc_from_byn(amount)
            
        try:
            rates = await MyFinScraper.get_raw_rates("minsk", currency)
            if not rates:
                return f"⚠️ Данные для валюты {currency} недоступны.", TelegramUI.get_calc_keyboard(amount, currency)
                
            valid_buy = [r for r in rates if r['buy'] > 0]
            valid_sell = [r for r in rates if r['sell'] > 0]
            
            if not valid_buy or not valid_sell:
                return "⚠️ Актуальные предложения отсутствуют.", TelegramUI.get_calc_keyboard(amount, currency)
                
            best_buy = max(valid_buy, key=lambda x: x['buy'])
            best_sell = min(valid_sell, key=lambda x: x['sell'])
            
            msg = f"🧮 <b>Финансовый конвертер: {amount:g} {currency}</b>\n<i>Расчет произведен по наиболее выгодным курсам (Минск)</i>\n\n"
            
            msg += f"📥 <b>Сдача валюты банку:</b>\n"
            msg += f"Сумма к получению: <b>{amount * best_buy['buy']:.2f} BYN</b>\n"
            msg += f"<i>Оптимально: {best_buy['bank']} (Курс: {best_buy['buy']})</i>\n\n"
            
            msg += f"📤 <b>Покупка валюты у банка:</b>\n"
            msg += f"Требуемая сумма: <b>{amount * best_sell['sell']:.2f} BYN</b>\n"
            msg += f"<i>Оптимально: {best_sell['bank']} (Курс: {best_sell['sell']})</i>"
            
            return msg, TelegramUI.get_calc_keyboard(amount, currency)
        except Exception as e:
            logger.error(f"Calc error: {e}")
            return "⚠️ Возникла ошибка при выполнении вычислений.", TelegramUI.get_calc_keyboard(amount, currency)

    @staticmethod
    async def _calc_from_byn(amount: float) -> tuple[str, dict]:
        msg = f"🧮 <b>Финансовый конвертер: {amount:g} BYN</b>\n<i>Оценочная покупательная способность (по лучшим курсам продажи)</i>\n\n"
        
        for curr in ["USD", "EUR", "RUB"]:
            try:
                rates = await MyFinScraper.get_raw_rates("minsk", curr)
                if not rates: continue
                
                sell_rates = [r['sell'] for r in rates if r['sell'] > 0]
                buy_rates = [r['buy'] for r in rates if r['buy'] > 0]
                
                if sell_rates and buy_rates:
                    best_sell = min(sell_rates)
                    
                    can_buy = amount / best_sell
                    msg += f"🔹 <b>{curr}</b>: доступно к покупке ~<b>{can_buy:.2f} {curr}</b>\n"
            except:
                pass
                
        msg += "\n<i>Выберите целевую валюту для точного расчета:</i>"
        return msg, TelegramUI.get_calc_keyboard(amount, "BYN")


async def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def answer_callback_query(callback_query_id: str) -> None:
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"callback_query_id": callback_query_id})


async def process_update(update: dict) -> None:
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].strip()
        
        if text in ("/start", "/help"):
            welcome_msg = "Здравствуйте! 🏛 Добро пожаловать в сервис аналитики курсов валют.\nДля начала работы, пожалуйста, <b>укажите ваш основной регион</b> для персонализации выдачи данных:"
            await send_telegram_message(chat_id, welcome_msg, reply_markup=TelegramUI.get_city_setup_keyboard())
            return
            
        elif text == "📍 Изменить город":
            await send_telegram_message(chat_id, "📍 <b>Выберите ваш основной регион:</b>", reply_markup=TelegramUI.get_city_setup_keyboard())
            return
            
        elif text == "💵 Продать USD":
            user_city = USER_CITIES.get(chat_id, "minsk") 
            city_name, _ = get_city_name_and_region(user_city)
            await send_telegram_message(chat_id, f"⏳ <i>Выполняется анализ предложений ({city_name})...</i>")
            msg = await CurrencyService.get_quick_sell_top("USD", user_city)
            await send_telegram_message(chat_id, msg, reply_markup=TelegramUI.get_quick_sell_keyboard("USD", user_city))
            return

        elif text == "💶 Продать EUR":
            user_city = USER_CITIES.get(chat_id, "minsk")
            city_name, _ = get_city_name_and_region(user_city)
            await send_telegram_message(chat_id, f"⏳ <i>Выполняется анализ предложений ({city_name})...</i>")
            msg = await CurrencyService.get_quick_sell_top("EUR", user_city)
            await send_telegram_message(chat_id, msg, reply_markup=TelegramUI.get_quick_sell_keyboard("EUR", user_city))
            return
            
        elif text == "💱 Кросс-курсы (USD ↔ EUR)":
            user_city = USER_CITIES.get(chat_id, "minsk")
            city_name, _ = get_city_name_and_region(user_city)
            await send_telegram_message(chat_id, f"⏳ <i>Формируется список котировок для прямой конвертации ({city_name})...</i>")
            msg = await CurrencyService.get_cross_rates_text(user_city)
            await send_telegram_message(chat_id, msg)
            return

        elif text == "🌍 Все курсы":
            await send_telegram_message(chat_id, "📍 <b>Выберите интересующий вас регион:</b>", reply_markup=TelegramUI.get_regions_keyboard())
            return
            
        elif text == "🧮 Калькулятор":
            calc_text = (
                "🧮 <b>Использование конвертера:</b>\n\n"
                "Отправьте боту сообщение, содержащее сумму и буквенный код валюты.\n"
                "Примеры запросов:\n"
                "• <code>100 USD</code>\n"
                "• <code>50.5 EUR</code>\n"
                "• <code>1000</code> (по умолчанию распознается как BYN)"
            )
            await send_telegram_message(chat_id, calc_text)
            return

        calc_match = re.match(r"^([\d\.,]+)(?:\s*([a-zA-Z]{3}|[а-яА-Я]+))?$", text, re.IGNORECASE)
        
        if calc_match:
            amount_str = calc_match.group(1).replace(',', '.')
            curr_str = calc_match.group(2)
            amount = float(amount_str)
            
            currency = curr_str.upper() if curr_str else "BYN"
            if currency in CURRENCIES or currency == "BYN":
                await send_telegram_message(chat_id, "⏳ <i>Производится расчет...</i>")
                text_res, markup = await CurrencyService.calculate_exchange(amount, currency)
                await send_telegram_message(chat_id, text_res, reply_markup=markup)
                return

    elif "callback_query" in update:
        query = update["callback_query"]
        callback_id = query["id"]
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        data = query["data"]
        
        await answer_callback_query(callback_id)
        
        if data.startswith("setcity_"):
            city_code = data.split("_")[1]
            USER_CITIES[chat_id] = city_code
            city_name, _ = get_city_name_and_region(city_code)
            
            await edit_telegram_message(chat_id, message_id, f"✅ Регион <b>{city_name}</b> установлен по умолчанию!")
            
            msg = "Настройка завершена. Теперь элементы быстрого доступа будут предоставлять информацию по выбранному региону 👇"
            await send_telegram_message(chat_id, msg, reply_markup=TelegramUI.get_persistent_keyboard())
            
        elif data == "start_menu":
            await edit_telegram_message(chat_id, message_id, "🏛 <b>Главное меню:</b>", reply_markup=TelegramUI.get_main_menu())
            
        elif data == "menu_rates":
            await edit_telegram_message(chat_id, message_id, "📍 <b>Выберите интересующий вас регион:</b>", reply_markup=TelegramUI.get_regions_keyboard())
            
        elif data == "menu_calc":
            text = (
                "🧮 <b>Использование конвертера:</b>\n\n"
                "Отправьте боту сообщение, содержащее сумму и буквенный код валюты.\n"
                "Примеры запросов:\n"
                "• <code>100 USD</code>\n"
                "• <code>50.5 EUR</code>\n"
                "• <code>1000</code> (по умолчанию распознается как BYN)"
            )
            kb = {"inline_keyboard": [[{"text": "🔙 В главное меню", "callback_data": "start_menu"}]]}
            await edit_telegram_message(chat_id, message_id, text, reply_markup=kb)

        elif data.startswith("reg_"):
            reg_code = data.split("_")[1] + "_reg"
            reg_name = REGIONS.get(reg_code, REGIONS["minsk_reg"])["name"]
            text = f"📍 <b>{reg_name}</b>\nУкажите населенный пункт:"
            await edit_telegram_message(chat_id, message_id, text, reply_markup=TelegramUI.get_cities_keyboard(reg_code))
            
        elif data.startswith("cit_"):
            city = data.split("_")[1]
            city_name, _ = get_city_name_and_region(city)
            text = f"📍 Регион: <b>{city_name}</b>\n💱 Выберите целевую валюту:"
            await edit_telegram_message(chat_id, message_id, text, reply_markup=TelegramUI.get_currencies_keyboard(city))
            
        elif data.startswith("cur_"):
            _, city, currency = data.split("_")
            if city == "minsk":
                text = f"💱 Текущая валюта: <b>{currency}</b> (Минск)\nУточните критерии поиска:"
                await edit_telegram_message(chat_id, message_id, text, reply_markup=TelegramUI.get_locations_keyboard(city, currency))
            else:
                await _show_top5_ui(chat_id, message_id, city, currency)
                
        elif data.startswith("top5_"):
            _, city, currency = data.split("_")
            await _show_top5_ui(chat_id, message_id, city, currency)
                
        elif data.startswith("rate_"):
            _, city, currency, loc_key = data.split("_")
            await _show_rates_ui(chat_id, message_id, city, currency, loc_key)
            
        elif data.startswith("calc_"):
            parts = data.split("_")
            if len(parts) >= 3:
                amount = float(parts[1])
                currency = parts[2]
                
                await edit_telegram_message(chat_id, message_id, f"⏳ <i>Выполняется перерасчет в {currency}...</i>")
                text_res, markup = await CurrencyService.calculate_exchange(amount, currency)
                await edit_telegram_message(chat_id, message_id, text_res, reply_markup=markup)


async def _show_rates_ui(chat_id: int, message_id: int, city: str, currency: str, loc_key: str) -> None:
    city_name, _ = get_city_name_and_region(city)
    loc_name = MINSK_LOCATIONS.get(loc_key, ("🌍 Все отделения",))[0] if city == "minsk" else "🌍 Все отделения"
    
    await edit_telegram_message(chat_id, message_id, f"⏳ <i>Обработка данных по валюте <b>{currency}</b> ({city_name})...</i>")
    rates_text = await CurrencyService.format_rates_text(city, currency, loc_key)
    
    final_text = f"📊 <b>Сводка: {currency} | {city_name}</b> | {loc_name}\n\n{rates_text}"
    kb = {"inline_keyboard": [[{"text": "🔙 Выбрать другую валюту", "callback_data": f"cit_{city}"}]]}
    await edit_telegram_message(chat_id, message_id, final_text, reply_markup=kb)

async def _show_top5_ui(chat_id: int, message_id: int, city: str, currency: str) -> None:
    city_name, _ = get_city_name_and_region(city)
    await edit_telegram_message(chat_id, message_id, f"⏳ <i>Сбор актуальных предложений <b>{currency}</b> ({city_name})...</i>")
    
    top5_text = await CurrencyService.get_top_5_text(city, currency)
    kb = {"inline_keyboard": [[{"text": "🔙 Выбрать другую валюту", "callback_data": f"cit_{city}"}]]}
    await edit_telegram_message(chat_id, message_id, top5_text, reply_markup=kb)


@app.post("/webhook")
async def telegram_webhook(request: Request) -> dict[str, str]:
    update = await request.json()
    asyncio.create_task(process_update(update))
    return {"status": "ok"}

async def local_polling() -> None:
    logger.info("Запуск локального тестирования (Long Polling)...")
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API_URL}/deleteWebhook")
        
    offset = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            try:
                response = await client.get(
                    f"{TELEGRAM_API_URL}/getUpdates",
                    params={"offset": offset, "timeout": 30}
                )
                data = response.json()
                
                if not data.get("ok"):
                    logger.error(f"Telegram API Error: {data}")
                    await asyncio.sleep(5)
                    continue
                    
                updates = data.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    await process_update(update)
            except Exception as e:
                logger.error(f"Ошибка polling: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_LOCAL_TOKEN" or not BOT_TOKEN:
        logger.error("⚠️ Установите переменную окружения BOT_TOKEN перед запуском!")
    else:
        try:
            asyncio.run(local_polling())
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем.")