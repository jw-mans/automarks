# TikTok CAPI — масштабирование под множество воронок (спека для БД/N8N)

Документ фиксирует задачи на **стороне склада (Postgres) и N8N** для перехода от
single-воронки к конфигурируемой атрибуции TikTok. Сторона automarks (приём
заявок, страница TikTok-воронок, запись черновика в `activation_data.tt_funnels`)
уже реализована — см. раздел «Интеграция с automarks» и код в
[marks/services/funnels.py](../marks/services/funnels.py).

Проект «sdelki» / ЕГЭЛЕНД. Домены лендингов: `go-egeland.ru/<endpoint>`.

**Цель.** Скрипт лендинга и CAPI-воркфлоу — неизменяемые шаблоны; всё различие
воронок (пиксель, токен, оффер, бот) вынесено в справочник БД. Новая воронка =
строка в `tt_funnels` + подключение пикселя/токена, без правки кода.

**Ключ воронки** — `landing_endpoint` (= `location.pathname`, напр. `/pasha_all`).
Он уже пишется в каждую строку `visits_data`, поэтому связка строится по нему.

---

## Блок 2 — Справочники (DDL + права)

Две таблицы в схеме `activation_data`. `tt_funnels` открыта на чтение пайплайну;
`tiktok_tokens` защищена (токен = полный доступ к рекламному кабинету).

```sql
-- Справочник воронок
CREATE TABLE IF NOT EXISTS activation_data.tt_funnels (
  landing_endpoint TEXT PRIMARY KEY,                 -- '/pasha_all' — ключ воронки
  offer            TEXT NOT NULL,                     -- 'ell010005'
  bot_url          TEXT NOT NULL,                     -- 'https://telegram.me/efir_tt_el_bot'
  bot_name         TEXT,                              -- 'efir_tt_el_bot'
  pixel_code       TEXT,                              -- заполняет разработчик
  ym_counter_id    BIGINT,                            -- сейчас общий на все сайты
  status           TEXT NOT NULL DEFAULT 'pending',   -- pending → active
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Защищённая таблица токенов
CREATE TABLE IF NOT EXISTS activation_data.tiktok_tokens (
  pixel_code    TEXT PRIMARY KEY,                     -- логическая связь с tt_funnels.pixel_code
  access_token  TEXT NOT NULL,
  advertiser_id TEXT,
  note          TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Права

Два разных потребителя:

- **Пользователь N8N** (сервисный) — читает обе таблицы в lookup-SELECT.
- **Пользователь automarks** (из `GLOBAL_PGUSER`, в раннем DDL — `visits_user`) —
  пишет черновики воронок. Ему нужен **INSERT/UPDATE/SELECT на `tt_funnels`** (в
  исходном DDL был только `SELECT` — это блокирует приём заявок) и **SELECT на
  `tiktok_tokens`** (для гарда активации).

```sql
-- N8N сервисный пользователь
GRANT SELECT ON activation_data.tt_funnels       TO n8n_service;
GRANT SELECT ON activation_data.tiktok_tokens TO n8n_service;

-- automarks (GLOBAL_PGUSER) — приём заявок и активация
GRANT SELECT, INSERT, UPDATE ON activation_data.tt_funnels TO visits_user;
GRANT SELECT                 ON activation_data.tiktok_tokens TO visits_user;

-- Токены закрыты для всех остальных
REVOKE ALL ON activation_data.tiktok_tokens FROM PUBLIC;
```

> Записывать токены (`INSERT INTO tiktok_tokens`) должен только разработчик/N8N.
> automarks токен не пишет — только читает наличие строки при активации.

### Текущая воронка (сид)

```sql
INSERT INTO activation_data.tt_funnels
  (landing_endpoint, offer, bot_url, bot_name, pixel_code, status)
VALUES
  ('/pasha_all', 'ell010005', 'https://telegram.me/efir_tt_el_bot',
   'efir_tt_el_bot', 'D5NMAQRC77U4HM3KJMPG', 'active');

INSERT INTO activation_data.tiktok_tokens (pixel_code, access_token)
VALUES ('D5NMAQRC77U4HM3KJMPG', 'ACCESS_TOKEN');   -- подставить реальный
```

### Приёмка блока 2
- [ ] Обе таблицы созданы, права выданы обоим потребителям.
- [ ] `REVOKE ALL ... FROM PUBLIC` на `tiktok_tokens` применён.
- [ ] Текущая воронка `/pasha_all` и её токен залиты.
- [ ] automarks под `GLOBAL_PGUSER` может сделать `INSERT ... ON CONFLICT DO NOTHING` в `tt_funnels`.

---

## Блок 1 — Безопасность (N8N)

### 1.1 Header Auth на Purchase-вебхук
Purchase-вебхук (событие-деньги) сейчас открыт всему интернету. Включить в N8N на
webhook-ноде **Header Auth** (общий секрет в заголовке), обновить вызывающую
сторону. Приоритет — этот вебхук; по возможности закрыть и остальные.

### 1.2 Параметризация SQL
Во **всех** `executeQuery`-нодах перейти на bind-параметры (`$1`, `$2` + Query
Parameters) вместо интерполяции значений в строку запроса. Защита от инъекций и
от поломки на нестандартных значениях (кавычки, юникод).

### Приёмка блока 1
- [ ] Purchase-вебхук отвечает 401/403 без корректного заголовка.
- [ ] В воркфлоу не осталось `executeQuery` со склейкой значений в текст SQL.

---

## Блок 3 — Раскодхардить CAPI-воркфлоу (N8N)

Убрать из HTTP-нод захардкоженные пиксель и токен — доставать их из БД в том же
lookup-SELECT, что и `ttclid/ttp`. Атрибуция Purchase — **last-click**.

### 3.1 Lookup-SELECT (Click / Subscribe / Purchase)
В каждом из трёх воркфлоу заменить SELECT на джойн обеих справочных таблиц:

```sql
SELECT v.tiktok_ttclid, v.tiktok_ttp, f.pixel_code, t.access_token
FROM activation_data.visits_data v
JOIN activation_data.tt_funnels f       ON f.landing_endpoint = v.landing_endpoint
JOIN activation_data.tiktok_tokens t ON t.pixel_code = f.pixel_code
WHERE v."startID" = $1 AND v.tiktok_ttclid IS NOT NULL
LIMIT 1;
```

Purchase-цепочка идёт через `tg_id`; сохранить `ORDER BY created_at DESC LIMIT 1`
(last-click, осознанный выбор). JOIN добавляется к существующему запросу.

> Воронка со `status='pending'` (без пикселя) в JOIN по `tiktok_tokens` не
> смэтчится — события просто не уйдут, пока воронка не активирована. Это
> ожидаемое поведение, не баг.

### 3.2 HTTP-нода TikTok
Пиксель и токен брать из результата запроса, а не из констант:
- `event_source_id = {{ $json.pixel_code }}`
- `Authorization: Bearer {{ $json.access_token }}`

### 3.3 Проверка ответа и ретрай
- Проверять тело ответа TikTok на `code == 0` — `event/track/` может вернуть
  HTTP 200 с ошибкой в теле.
- Ретрай на HTTP-ноде TikTok + лог неуспешных отправок (особенно Purchase).
- **Не логировать** тело запросов с `access_token` — маскировать при отладке.

### Приёмка блока 3
- [ ] Пиксель/токен во всех трёх воркфлоу приходят из lookup-SELECT.
- [ ] HTTP-нода читает `pixel_code`/`access_token` из `$json`, констант нет.
- [ ] Есть проверка `code == 0` + ретрай + лог ошибок.
- [ ] `access_token` не попадает в логи.

---

## Интеграция с automarks (уже готово)

- Маркетолог заводит заявку на странице **TikTok-воронки** (3 поля: эндпоинт,
  оффер, ссылка на бота). endpoint нормализуется до `/path`, `bot_name` парсится
  из ссылки.
- На сабмите automarks делает `INSERT INTO activation_data.tt_funnels (...)
  VALUES (...) ON CONFLICT (landing_endpoint) DO NOTHING` со `status='pending'`
  через отдельное подключение `global` (креды `GLOBAL_*`), параметризованно.
- Разработчик подключает пиксель/токен (`INSERT tiktok_tokens`), затем активирует
  воронку — automarks делает `UPDATE tt_funnels SET pixel_code=..., status='active'`
  с гардом: **активация запрещена, если для пикселя нет строки в `tiktok_tokens`**.
- automarks никогда не мигрирует и не мигрирует ORM-модели в `activation_data`
  (см. [marks/db_routers.py](../marks/db_routers.py)); запись только явным raw-SQL.

Что нужно от вашей стороны для работы этой интеграции: **расширенный GRANT на
`tt_funnels`** (см. Блок 2) — без него `INSERT` из automarks упадёт, и заявка
останется со статусом «не в складе» (с кнопкой повторной синхронизации).

---

## Следующий этап (не в этой итерации)
- Универсальный скрипт лендинга + конфиг-эндпоинт `GET /config?landing=/endpoint`.
- Единый под-воркфлоу `send_to_capi` (одна точка отправки, версия API в одном месте).
- `campaign_pixel_map` — если пиксель начнут определять по кампании, а не по воронке.
