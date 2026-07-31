import html
import logging
import uuid
from datetime import datetime as dt_datetime
from urllib.error import HTTPError, URLError
from urllib import parse, request
import json

from django.conf import settings

from ..models import TaskRequest
from ..task_time import format_task_datetime

logger = logging.getLogger(__name__)


def _clean_env_value(value):
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _safe(value):
    return html.escape(str(value))


def _format_datetime(dt):
    return format_task_datetime(dt)


def _format_deadline(value):
    if not value:
        return "-"
    if isinstance(value, dt_datetime):
        return format_task_datetime(value)
    return value.strftime("%d.%m.%Y")


def _mask_token(value):
    value = (value or "").strip()
    if len(value) <= 8:
        return value or "-"
    return f"{value[:4]}...{value[-4:]}"


def _format_branches(task):
    return _safe(task.get_bot_branch_text())


def _build_task_details(task):
    lines = [
        f"ID: #{task.id}",
        f"Тип: {_safe(task.get_task_type_display())}",
        f"Статус: {_safe(task.get_status_display())}",
        f"Создал: {_safe(task.created_by.username if task.created_by else '-')}",
        f"Создано: {_format_datetime(task.created_at)}",
        f"Дедлайн: {_format_deadline(task.deadline)}",
        f"Ветки: {_format_branches(task)}",
    ]

    if task.task_type == TaskRequest.Type.PATCH:
        lines.append(f"CJM: {_safe(task.cjm_url or '-')}")
        if task.tz_url:
            lines.append(f"ТЗ: {_safe(task.tz_url)}")
    elif task.task_type == TaskRequest.Type.MAILING:
        lines.append(f"ТЗ: {_safe(task.tz_url or '-')}")
    elif task.task_type == TaskRequest.Type.BUILD:
        lines.extend(
            [
                f"Бот и ветки: {_safe(task.get_bot_branch_text())}",
                f"Токен: {_safe(_mask_token(task.build_token))}",
                f"CJM: {_safe(task.cjm_url or '-')}",
            ]
        )
        if task.tz_url:
            lines.append(f"ТЗ: {_safe(task.tz_url)}")

    if task.comment:
        lines.append(f"Комментарий: {_safe(task.comment)}")
    if task.photo:
        lines.append("Фото: приложено")
    return "\n".join(lines)


def _send_message(chat_id, text):
    token = _clean_env_value(getattr(settings, "TELEGRAM_NOTIFY_BOT_TOKEN", ""))
    chat_id = _clean_env_value(chat_id)
    if not token or not chat_id:
        return False, "Не задан TELEGRAM_NOTIFY_BOT_TOKEN или chat_id"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    data = parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        req = request.Request(url=url, data=data, method="POST")
        with request.urlopen(req, timeout=7):
            return True, ""
    except HTTPError as exc:
        details = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            details = data.get("description") or body
        except Exception:
            details = str(exc)
        logger.exception("Telegram HTTP error")
        return False, f"Telegram API error: {details}"
    except URLError as exc:
        logger.exception("Telegram URL error")
        return False, f"Telegram network error: {exc.reason}"
    except Exception:
        logger.exception("Failed to send Telegram notification")
        return False, "Неизвестная ошибка отправки в Telegram"


def _normalize_direct_chat(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        return raw
    if raw.lstrip("-").isdigit():
        return raw
    return f"@{raw}"


def _send_document(chat_id, filename, content_bytes, caption=""):
    token = _clean_env_value(getattr(settings, "TELEGRAM_NOTIFY_BOT_TOKEN", ""))
    chat_id = _clean_env_value(chat_id)
    if not token or not chat_id:
        return False, "Не задан TELEGRAM_NOTIFY_BOT_TOKEN или chat_id"

    if isinstance(content_bytes, str):
        content_bytes = content_bytes.encode("utf-8")

    boundary = f"----automarks-{uuid.uuid4().hex}"
    crlf = b"\r\n"
    body = bytearray()

    def add_field(name, value):
        body.extend(f"--{boundary}".encode("utf-8") + crlf)
        body.extend(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8") + crlf + crlf)
        body.extend(str(value).encode("utf-8") + crlf)

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)

    body.extend(f"--{boundary}".encode("utf-8") + crlf)
    body.extend(
        f'Content-Disposition: form-data; name="document"; filename="{filename}"'.encode("utf-8") + crlf
    )
    body.extend(
        b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" + crlf + crlf
    )
    body.extend(content_bytes + crlf)
    body.extend(f"--{boundary}--".encode("utf-8") + crlf)

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    try:
        req = request.Request(url=url, data=bytes(body), headers=headers, method="POST")
        with request.urlopen(req, timeout=15):
            return True, ""
    except HTTPError as exc:
        details = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body_text)
            details = data.get("description") or body_text
        except Exception:
            details = str(exc)
        logger.exception("Telegram document HTTP error")
        return False, f"Telegram API error: {details}"
    except URLError as exc:
        logger.exception("Telegram document URL error")
        return False, f"Telegram network error: {exc.reason}"
    except Exception:
        logger.exception("Failed to send Telegram document")
        return False, "Неизвестная ошибка отправки файла в Telegram"


def notify_new_task(task):
    chat_id = getattr(settings, "TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID", "")
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    header = f"[{_safe(platform_name)}] Новая задача" if platform_name else "Новая задача"
    text = f"{header}\n\n{_build_task_details(task)}"
    return _send_message(chat_id=chat_id, text=text)


def notify_status_change(task, old_status, changed_by):
    chat_id = getattr(settings, "TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    try:
        old_label = task.Status(old_status).label
    except Exception:
        old_label = old_status
    new_label = task.get_status_display()
    header = f"[{_safe(platform_name)}] Изменение статуса задачи" if platform_name else "Изменение статуса задачи"
    details = _build_task_details(task)
    text = (
        f"{header}\n\n"
        f"Было: {_safe(old_label)}\n"
        f"Стало: {_safe(new_label)}\n"
        f"Изменил: {_safe(changed_by.username if changed_by else '-')}\n\n"
        f"{details}"
    )
    return _send_message(chat_id=chat_id, text=text)


def notify_done_to_user(task, tg_username):
    raw_target = (tg_username or "").strip()
    direct_chat_id = _normalize_direct_chat(raw_target)
    if not direct_chat_id:
        return False, "Не указан username/chat_id для персонального уведомления."

    mention = raw_target if raw_target.startswith("@") else f"@{raw_target}"
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    header = f"[{_safe(platform_name)}] Задача выполнена" if platform_name else "Задача выполнена"
    text = (
        f"{header}\n\n"
        f"Получатель: {_safe(mention)}\n"
        f"ID задачи: #{task.id}\n"
        f"Ваша задача #{task.id} переведена в статус: {_safe(task.get_status_display())}\n"
        f"Тип: {_safe(task.get_task_type_display())}\n"
        f"Дедлайн: {_format_deadline(task.deadline)}\n"
        f"Бот и ветки: {_format_branches(task)}\n\n"
        f"<b>Пожалуйста, оставьте комментарий о работе, ответив на это сообщение!</b>"
    )
    ok, error = _send_message(chat_id=direct_chat_id, text=text)
    if ok:
        return True, ""

    # Usernames are usually not valid chat_id for direct bot messages.
    # Fallback: notify in status chat with @mention.
    status_chat_id = getattr(settings, "TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
    if raw_target.lstrip("-").isdigit() or not status_chat_id:
        return False, error
    fallback_ok, fallback_error = _send_message(chat_id=status_chat_id, text=text)
    if fallback_ok:
        return True, ""
    return False, fallback_error or error


def notify_new_tiktok_funnel(funnel_request):
    chat_id = getattr(settings, "TELEGRAM_NOTIFY_TIKTOK_CHAT_ID", "") or getattr(
        settings, "TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID", ""
    )
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    header = (
        f"[{_safe(platform_name)}] Новая TikTok-заявка"
        if platform_name
        else "Новая TikTok-заявка"
    )
    lines = [
        f"Эндпоинт: {_safe(funnel_request.landing_endpoint)}",
        f"Оффер: {_safe(funnel_request.offer)}",
        f"Бот: {_safe(funnel_request.bot_url)}",
        f"Создал: {_safe(funnel_request.created_by.username if funnel_request.created_by else '-')}",
    ]
    if funnel_request.comment:
        lines.append(f"Комментарий: {_safe(funnel_request.comment)}")
    lines.append("\nПодключите пиксель и токен, затем активируйте воронку.")
    text = f"{header}\n\n" + "\n".join(lines)
    return _send_message(chat_id=chat_id, text=text)


def send_weekly_tasks_report(chat_id, filename, content_bytes, caption=""):
    return _send_document(chat_id=chat_id, filename=filename, content_bytes=content_bytes, caption=caption)


def send_text_message(chat_id, text):
    return _send_message(chat_id=chat_id, text=text)
