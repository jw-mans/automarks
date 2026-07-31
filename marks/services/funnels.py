"""Direct writes to the shared warehouse funnels reference table.

The TikTok CAPI pipeline reads funnel config from ``activation_data.tt_funnels`` on
the remote warehouse (see docs/tiktok_funnels_intake.md). automarks provisions a
draft row (status=pending) when a marketer submits a funnel request, and can
flip it to ``active`` once a developer has connected the pixel/token.

All access goes through the ``global`` DB alias with parameterized SQL. The
schema name is an identifier (cannot be a bind parameter), so it is validated
against a strict pattern and quoted before interpolation.
"""

import logging
import re

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _connection():
    if "global" not in settings.DATABASES:
        return None, "Склад не настроен (нет GLOBAL_PGHOST в окружении)."
    return connections["global"], ""


def _funnels_table():
    schema = getattr(settings, "GLOBAL_DB_SCHEMA", "activation_data")
    if not _SCHEMA_RE.match(schema or ""):
        raise ValueError(f"Недопустимое имя схемы склада: {schema!r}")
    return f'"{schema}"."tt_funnels"'


def _tokens_table():
    schema = getattr(settings, "GLOBAL_DB_SCHEMA", "activation_data")
    if not _SCHEMA_RE.match(schema or ""):
        raise ValueError(f"Недопустимое имя схемы склада: {schema!r}")
    return f'"{schema}"."tiktok_tokens"'


def provision_funnel(landing_endpoint, offer, bot_url, bot_name):
    """Insert a pending draft funnel; no-op if the endpoint already exists.

    Returns ``(ok, created, error)``:
    - ``ok`` — the warehouse write completed without error;
    - ``created`` — a new row was inserted (False means the endpoint was taken);
    - ``error`` — human-readable reason when ``ok`` is False.
    """
    connection, error = _connection()
    if connection is None:
        return False, False, error

    try:
        table = _funnels_table()
    except ValueError as exc:
        return False, False, str(exc)

    sql = (
        f"INSERT INTO {table} (landing_endpoint, offer, bot_url, bot_name, status) "
        "VALUES (%s, %s, %s, %s, 'pending') "
        "ON CONFLICT (landing_endpoint) DO NOTHING "
        "RETURNING landing_endpoint"
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, [landing_endpoint, offer, bot_url, bot_name])
            created = cursor.fetchone() is not None
        return True, created, ""
    except Exception as exc:
        logger.exception("Failed to provision funnel in warehouse (endpoint=%s)", landing_endpoint)
        return False, False, f"Ошибка записи в склад: {exc}"


def activate_funnel(landing_endpoint, pixel_code):
    """Flip a funnel to ``active`` — refuses if the pixel has no token row.

    Guards the README failure mode: a funnel marked active without a matching
    ``tiktok_tokens`` row looks live but silently drops every CAPI event.
    Returns ``(ok, error)``.
    """
    pixel_code = (pixel_code or "").strip()
    if not pixel_code:
        return False, "Укажите pixel_code для активации."

    connection, error = _connection()
    if connection is None:
        return False, error

    try:
        funnels = _funnels_table()
        tokens = _tokens_table()
    except ValueError as exc:
        return False, str(exc)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {tokens} WHERE pixel_code = %s LIMIT 1", [pixel_code])
            if cursor.fetchone() is None:
                return False, (
                    f"Для пикселя {pixel_code} нет токена в tiktok_tokens — "
                    "активация запрещена (события не пойдут)."
                )
            cursor.execute(
                f"UPDATE {funnels} SET pixel_code = %s, status = 'active' "
                "WHERE landing_endpoint = %s RETURNING landing_endpoint",
                [pixel_code, landing_endpoint],
            )
            if cursor.fetchone() is None:
                return False, "Воронка с таким endpoint не найдена в складе."
        return True, ""
    except Exception as exc:
        logger.exception("Failed to activate funnel in warehouse (endpoint=%s)", landing_endpoint)
        return False, f"Ошибка активации в складе: {exc}"
