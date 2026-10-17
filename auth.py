import hashlib
import hmac
import json
import os
import urllib.parse
from typing import Optional, Dict, Any

DEFAULT_BOT_TOKEN = "8961172401:AAF-q6J_EbbbmX2VTrxCRA1e9rzj_tHQJ6M"
BOT_TOKEN = os.getenv("BOT_TOKEN", DEFAULT_BOT_TOKEN).strip().strip("'\"")


def validate_telegram_init_data(init_data: str, bot_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Валидирует строку initData, полученную от Telegram WebApp SDK по официальному алгоритму HMAC-SHA256.
    Возвращает словарь с данными пользователя или None, если подпись неверна.
    """
    raw_token = bot_token or os.getenv("BOT_TOKEN") or BOT_TOKEN or DEFAULT_BOT_TOKEN
    token = str(raw_token).strip().strip("'\"")
    if not init_data or not token:
        return None

    try:
        # Разбираем параметры строки
        parsed_params = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        params_dict = dict(parsed_params)

        received_hash = params_dict.pop("hash", None)
        if not received_hash:
            return None

        # Сортируем параметры в алфавитном порядке и собираем data_check_string
        data_check_list = [f"{k}={v}" for k, v in sorted(params_dict.items())]
        data_check_string = "\n".join(data_check_list)

        # 1. secret_key = HMAC_SHA256("WebAppData", bot_token)
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()

        # 2. computed_hash = HMAC_SHA256(secret_key, data_check_string)
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        # Проверяем равенство хешей константным по времени сравнением
        if not hmac.compare_digest(computed_hash, received_hash):
            return None

        # Извлекаем объект user из параметров
        user_raw = params_dict.get("user")
        user_data = json.loads(user_raw) if user_raw else {}
        return user_data

    except Exception as e:
        print(f"[Auth Error] Failed to validate initData: {e}")
        return None
