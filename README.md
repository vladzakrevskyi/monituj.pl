# Monituj

**Monituj pilnuje Twoich dokumentów i terminów.**

Monituj — это польский сервис для фирм, которым регулярно нужны документы от клиентов: бухгалтерских бюро, кадровых отделов, юристов, кредитных посредников, строительных фирм. Это не «ещё один способ переслать файл», а инструмент, который выстраивает процесс сбора документов:

- фирма один раз формирует просьбу со списком нужных документов и сроком;
- клиент получает защищённую ссылку и загружает файлы без регистрации;
- Monituj сам напоминает клиенту о недостающих документах по расписанию;
- фирма видит в панели, у кого чего не хватает, принимает или отклоняет файлы с причиной;
- по истечении выбранного срока хранения файлы автоматически и безвозвратно удаляются, а обе стороны получают уведомление.

Весь интерфейс, письма и юридические тексты — на польском языке.

## Возможности

| Область | Что умеет |
|---|---|
| Клиенты | Список с поиском и фильтрами, количество активных просьб и недостающих документов, все документы клиента на одной странице |
| Просьбы | Список документов, срок, необязательный пароль на ссылку, выбор срока хранения файлов (до 365 дней) |
| Публичная ссылка `/d/<token>/` | Загрузка файлов клиентом без аккаунта, drag & drop, проверка типа и размера (до 20 МБ), удаление своего файла до принятия |
| Проверка | Принять или отклонить документ с причиной — клиент получает письмо и может загрузить заново |
| Напоминания | Автоматические по расписанию (первое через N дней, затем каждые N дней, максимум N штук, в заданный час) и ручные; в панели видны даты всех следующих напоминаний |
| Хранение | Автоматическое удаление файлов после срока хранения, в истории остаётся заглушка «файл удалён» |
| Журнал | История событий каждой просьбы (создание, открытие ссылки клиентом, загрузки, решения, напоминания) |
| Панель | Статистика: активные просьбы, недостающие и доставленные документы, отправленные напоминания, последняя активность |
| Без аккаунта | `/wyslij-prosbe/` — одна просьба в день без регистрации |
| Демо | `/demo/` — каждый посетитель получает отдельный временный аккаунт с примерами данных (удаляется через 24 часа, письма не отправляются) |
| Аккаунт | Регистрация с подтверждением email, смена пароля и email с подтверждением, удаление аккаунта с подтверждением по почте (удаляются все данные сразу) |
| Письма | HTML-письма в стиле сайта + текстовая версия |
| Право | Regulamin, Polityka prywatności, Polityka cookies, Umowa powierzenia (DPA) — данные фирмы подставляются из переменных окружения |

## Технологии

- **Python 3.14, Django 6.1** — серверные шаблоны + немного чистого JavaScript, без фронтенд-фреймворков;
- **PostgreSQL 16** — база данных;
- **Redis 7 + Celery** — отправка писем и фоновые задачи;
- **Gunicorn + WhiteNoise** — приложение и статика в продакшене;
- **nginx + Let's Encrypt** — HTTPS на сервере;
- **Docker Compose** — весь стек на сервере запускается одной командой.

Безопасность: пароли хешируются Argon2, строгий CSP (`'self'`, без inline-скриптов и стилей), HSTS, защищённые cookie, проверка содержимого загружаемых файлов (libmagic), приватное хранилище файлов вне публичной папки, лимиты запросов по IP, журнал аудита.

### Структура

```
apps/
  accounts/       пользователи, вход, регистрация, настройки, удаление аккаунта
  clients/        клиенты
  requests/       просьбы, пункты, публичная ссылка, просьба без аккаунта
  documents/      загрузка, проверка и хранение файлов, удаление по сроку
  reminders/      ручные и автоматические напоминания
  notifications/  отправка и журнал писем
  audit/          журнал событий
  demo/           временные демо-аккаунты
  common/         общие вещи: маркетинговые и юридические страницы, middleware, типографика
config/           настройки (base / dev / prod), urls, celery
templates/        HTML-шаблоны страниц и писем
static/           CSS и JS
deploy/           конфиг nginx, шаблон .env для продакшена, скрипт бэкапов
tests/            тесты (pytest)
```

### Фоновые задачи (Celery beat, раз в час)

| Задача | Что делает |
|---|---|
| `send_automatic_reminders` | Отправляет автоматические напоминания, у которых наступил срок |
| `anonymize_expired_documents` | Удаляет файлы, у которых истёк срок хранения, и уведомляет обе стороны |
| `delete_expired_demo_accounts` | Удаляет демо-аккаунты старше 24 часов |

Без запущенных `worker` и `beat` сайт работает, но напоминания не уходят, а файлы не удаляются по сроку. В продакшене они запускаются автоматически вместе с сайтом.

---

## Локальная разработка

Нужны Python 3.14 и Docker (для PostgreSQL и Redis) — или локально установленные PostgreSQL и Redis.

```bash
python3.14 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements/dev.txt
```

```bash
cp .env.example .env
```

В `.env` впишите `DJANGO_SECRET_KEY` (любая длинная строка) и при желании настройки SMTP. Чтобы письма печатались в консоль вместо отправки, поставьте `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.

```bash
docker compose up -d db redis
```

```bash
python manage.py migrate
```

```bash
python manage.py runserver
```

Сайт: http://localhost:8000. Фоновые задачи (в отдельных терминалах):

```bash
celery -A config worker -l info
```

```bash
celery -A config beat -l info
```

Тесты и линтер:

```bash
pytest -q
```

```bash
ruff check . && ruff format --check .
```

> `docker-compose.yml` — только для разработки: он открывает порты базы и Redis наружу и запускает `runserver`. На сервере используется `docker-compose.prod.yml`.

---

## Развёртывание на VPS — пошагово

Ниже — полный путь от чистого сервера до работающего `https://monituj.pl`. Везде вместо `monituj.pl` подставьте свой домен, вместо `1.2.3.4` — IP сервера.

**Как это устроено на сервере:**

```
Интернет ──443──▶ nginx (на сервере, HTTPS, Let's Encrypt)
                    │
                    ▼  127.0.0.1:8000
          ┌──────── Docker Compose ─────────────────────────┐
          │ web (gunicorn + Django)   worker (Celery)       │
          │ beat (расписание)         db (PostgreSQL)       │
          │ redis                     тома: postgres_data,  │
          │                                  storage (файлы)│
          └─────────────────────────────────────────────────┘
```

Наружу открыты только порты 22, 80 и 443. База, Redis и само приложение снаружи недоступны.

### Шаг 0. Что понадобится

- **VPS**: Ubuntu 24.04 LTS, минимум 2 vCPU, 2 ГБ RAM, 40 ГБ SSD. Сервер лучше взять **в ЕС** (клиенты польские, данные подпадают под RODO/GDPR) — эту страну потом нужно указать в `LEGAL_HOSTING_LOCATION`.
- **Домен** и доступ к его DNS.
- **SMTP** для писем: транзакционный сервис (например, Brevo, Mailgun, Postmark, Amazon SES) или почта хостинга. Нужны хост, порт, логин, пароль.
- **Реквизиты фирмы** для юридических страниц: название, адрес, NIP, REGON, KRS/CEIDG, контактный email.
- Код в Git-репозитории. Сейчас в репозитории нет ни одного коммита — сначала закоммитьте и запушьте проект на своём компьютере:

```bash
git add -A && git commit -m "Monituj v1" && git push -u origin main
```

### Шаг 1. DNS

У регистратора домена создайте записи:

| Тип | Имя | Значение |
|---|---|---|
| A | `@` | `1.2.3.4` |
| A | `www` | `1.2.3.4` |
| AAAA | `@`, `www` | IPv6 сервера (если есть) |

Проверить (может занять от нескольких минут до пары часов):

```bash
dig +short monituj.pl
```

### Шаг 2. Первый вход и пользователь для деплоя

Зайдите на сервер под root (данные даёт хостер):

```bash
ssh root@1.2.3.4
```

Обновите систему и создайте пользователя `deploy`:

```bash
apt update && apt upgrade -y
```

```bash
adduser deploy
```

```bash
usermod -aG sudo deploy
```

Скопируйте свой SSH-ключ этому пользователю (команда выполняется **на вашем компьютере**; если ключа нет — сначала `ssh-keygen -t ed25519`):

```bash
ssh-copy-id deploy@1.2.3.4
```

Проверьте, что вход по ключу работает, **в новом окне терминала**:

```bash
ssh deploy@1.2.3.4
```

### Шаг 3. Защита сервера

Все дальнейшие команды — на сервере под пользователем `deploy`.

**Запрет входа по паролю и под root.** Откройте конфиг SSH:

```bash
sudo nano /etc/ssh/sshd_config
```

Установите (раскомментируйте) строки:

```
PermitRootLogin no
PasswordAuthentication no
```

Перезапустите SSH (не закрывая текущую сессию, пока не проверите вход в новом окне):

```bash
sudo systemctl restart ssh
```

**Файрвол** — открываем только SSH, HTTP и HTTPS:

```bash
sudo ufw allow OpenSSH
```

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

```bash
sudo ufw enable
```

**Автоматические обновления безопасности:**

```bash
sudo apt install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
```

**Защита от перебора паролей SSH:**

```bash
sudo apt install -y fail2ban
```

**Swap** (на сервере с 2 ГБ RAM сборка образа без него может упасть):

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Часовой пояс** (для логов; само приложение всегда работает по `Europe/Warsaw`):

```bash
sudo timedatectl set-timezone Europe/Warsaw
```

### Шаг 4. Установка Docker

Официальный репозиторий Docker:

```bash
sudo apt install -y ca-certificates curl git
```

```bash
sudo install -m 0755 -d /etc/apt/keyrings && sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

```bash
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Разрешите пользователю `deploy` работать с Docker без sudo:

```bash
sudo usermod -aG docker deploy
```

Выйдите с сервера (`exit`) и зайдите снова, чтобы группа применилась. Проверка:

```bash
docker run --rm hello-world
```

> Docker сам управляет правилами iptables, и опубликованные порты контейнеров **обходят ufw**. Поэтому в `docker-compose.prod.yml` приложение слушает только `127.0.0.1:8000`, а у базы и Redis портов наружу нет вообще. Не добавляйте туда `ports:` без `127.0.0.1:`.

### Шаг 5. Код на сервере

Если репозиторий приватный, дайте серверу ключ только на чтение (deploy key):

```bash
ssh-keygen -t ed25519 -C "monituj-vps" -f ~/.ssh/monituj_deploy -N ""
```

```bash
cat ~/.ssh/monituj_deploy.pub
```

Скопируйте вывод в GitHub: репозиторий → **Settings → Deploy keys → Add deploy key** (галочку «Allow write access» не ставьте). Затем укажите SSH, какой ключ использовать для GitHub:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/monituj_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
```

Склонируйте проект в `/srv/monituj`:

```bash
sudo mkdir -p /srv/monituj && sudo chown deploy:deploy /srv/monituj
```

```bash
git clone git@github.com:vladzakrevskyi/monituj.pl.git /srv/monituj
```

```bash
cd /srv/monituj
```

### Шаг 6. Файл `.env`

Создайте его из шаблона для продакшена:

```bash
cp deploy/env.production.example .env && chmod 600 .env
```

Сгенерируйте секретный ключ и пароль базы:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

```bash
openssl rand -hex 24
```

Заполните файл:

```bash
nano .env
```

Что важно:

| Переменная | Значение |
|---|---|
| `COMPOSE_FILE` | Оставьте `docker-compose.prod.yml` — тогда простая команда `docker compose` в этой папке всегда работает с продакшен-стеком |
| `DJANGO_SECRET_KEY` | Первая сгенерированная строка. Никому не показывать и не коммитить |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `monituj.pl,www.monituj.pl` |
| `CSRF_TRUSTED_ORIGINS` | `https://monituj.pl,https://www.monituj.pl` |
| `SITE_URL` | `https://monituj.pl` — из него строятся все ссылки в письмах |
| `POSTGRES_PASSWORD` | Вторая строка (только буквы и цифры — пароль вставляется в URL подключения) |
| `EMAIL_*` | Данные SMTP. Порт 587 + `EMAIL_USE_TLS=True` — самый частый вариант |
| `DEFAULT_FROM_EMAIL` | Отправитель, например `Monituj <no-reply@monituj.pl>`. Домен должен совпадать с доменом, настроенным у SMTP-провайдера |
| `LEGAL_*` | Реквизиты фирмы. Пустые значения на юридических страницах подсвечиваются как «[uzupełnij: …]» |
| `LEGAL_BACKUP_DAYS` | Сколько дней хранятся бэкапы. Должно совпадать с `KEEP_DAYS` в скрипте бэкапов (шаг 11) — эта цифра указана в политике конфиденциальности |

Значения со пробелами (адрес фирмы) пишутся без кавычек.

### Шаг 7. Первый запуск

```bash
docker compose up -d --build
```

Первая сборка занимает несколько минут. При каждом старте контейнер `web` сам применяет миграции базы и собирает статику.

Проверьте, что все пять контейнеров работают (`State: running`, у `db` — `healthy`):

```bash
docker compose ps
```

Проверьте логи на ошибки:

```bash
docker compose logs --tail=50 web worker beat
```

Проверьте, что приложение отвечает изнутри сервера (редирект 301 на https — это нормально):

```bash
curl -sI -H "Host: monituj.pl" http://127.0.0.1:8000/ | head -1
```

### Шаг 8. nginx

```bash
sudo apt install -y nginx
```

```bash
sudo cp /srv/monituj/deploy/nginx/monituj.conf /etc/nginx/sites-available/monituj.conf
```

Если домен другой — поменяйте `server_name` в этом файле. Включите сайт и отключите стандартную заглушку:

```bash
sudo ln -s /etc/nginx/sites-available/monituj.conf /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Что делает конфиг:

- проксирует всё на `127.0.0.1:8000`;
- разрешает загрузку файлов до 25 МБ (в приложении лимит 20 МБ);
- передаёт приложению реальный IP посетителя. Заголовок `X-Forwarded-For` **перезаписывается**, а не дополняется: по этому IP работают лимиты (просьба без аккаунта, демо), и посетитель не должен иметь возможности его подделать.

### Шаг 9. HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
```

```bash
sudo certbot --nginx -d monituj.pl -d www.monituj.pl --redirect -m twoj@email.pl --agree-tos --no-eff-email
```

certbot сам добавит в конфиг nginx блок с сертификатом и редирект с http на https. Сертификат продлевается автоматически; проверка продления:

```bash
sudo certbot renew --dry-run
```

Откройте https://monituj.pl — должна открыться главная страница. Проверка из консоли:

```bash
curl -s https://monituj.pl/api/health/
```

Ожидаемый ответ: `{"success": true, "data": {"status": "ok"}}`.

> В продакшене включён HSTS с `includeSubDomains` и `preload`: браузеры запомнят, что домен и **все его поддомены** открываются только по HTTPS. Если на поддоменах есть что-то без HTTPS — сначала переведите их на HTTPS.

### Шаг 10. Администратор и проверка писем

Создайте суперпользователя для панели `/admin/`:

```bash
docker compose exec web python manage.py createsuperuser
```

Отправьте тестовое письмо на свой адрес:

```bash
docker compose exec web python manage.py sendtestemail twoj@email.pl
```

Если письмо не пришло — смотрите `docker compose logs web` и данные SMTP в `.env`. После изменения `.env` перезапустите контейнеры:

```bash
docker compose up -d
```

Чтобы письма не попадали в спам, у SMTP-провайдера настройте для домена **SPF**, **DKIM** и **DMARC** (провайдер покажет, какие DNS-записи добавить). Минимальная DMARC-запись: TXT `_dmarc.monituj.pl` → `v=DMARC1; p=none; rua=mailto:twoj@email.pl`.

Затем пройдите весь путь руками:

1. Регистрация → письмо с подтверждением → вход.
2. Добавить клиента (свой второй email) → создать просьбу → письмо со ссылкой.
3. Открыть ссылку, загрузить PDF → в панели файл появился → принять или отклонить.
4. Проверить `/demo/` и `/wyslij-prosbe/`.

### Шаг 11. Бэкапы

Скрипт `deploy/backup.sh` каждый раз делает дамп базы и архив загруженных файлов, а бэкапы старше `KEEP_DAYS` дней удаляет.

```bash
sudo mkdir -p /var/backups/monituj && sudo chown deploy:deploy /var/backups/monituj
```

Пробный запуск:

```bash
/srv/monituj/deploy/backup.sh && ls -lh /var/backups/monituj
```

Ежедневный запуск в 3:30 через cron:

```bash
crontab -e
```

Добавьте строку (срок хранения должен совпадать с `LEGAL_BACKUP_DAYS`):

```
30 3 * * * KEEP_DAYS=30 /srv/monituj/deploy/backup.sh >> /srv/monituj/backup.log 2>&1
```

**Копируйте бэкапы с сервера.** Бэкап, который лежит на том же сервере, не спасёт, если сервер пропадёт. Самый простой вариант — ежедневный `rsync` или `rclone` в отдельное хранилище (Storage Box, S3-совместимое хранилище в ЕС). Бэкапы содержат персональные данные и документы клиентов: храните их только в ЕС и с ограниченным доступом.

#### Восстановление из бэкапа

```bash
cd /srv/monituj && docker compose stop web worker beat
```

База (подставьте имя файла):

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < /var/backups/monituj/db_2026-09-24_0330.dump
```

Файлы:

```bash
docker run --rm -v monituj_storage:/data -v /var/backups/monituj:/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/storage_2026-09-24_0330.tar.gz -C /data"
```

```bash
docker compose start web worker beat
```

### Шаг 12. Обновление сайта

На своём компьютере закоммитьте и запушьте изменения, затем на сервере:

```bash
cd /srv/monituj && ./deploy/backup.sh
```

```bash
git pull
```

```bash
docker compose up -d --build
```

Миграции применятся автоматически при старте `web`. Во время пересоздания контейнера сайт недоступен несколько секунд.

Откат на предыдущую версию: `git log --oneline`, затем `git checkout <коммит>` и `docker compose up -d --build`. Если новая версия меняла базу (миграции), вместе с кодом восстановите и базу из бэкапа, сделанного перед обновлением.

Раз в пару месяцев стоит обновлять образы PostgreSQL и Redis (в пределах тех же версий 16 и 7):

```bash
docker compose pull db redis && docker compose up -d
```

Очистка старых образов после обновлений:

```bash
docker image prune -f
```

---

## Эксплуатация

### Полезные команды

Все команды — из `/srv/monituj`.

| Что | Команда |
|---|---|
| Состояние контейнеров | `docker compose ps` |
| Логи в реальном времени | `docker compose logs -f web worker beat` |
| Перезапуск всего | `docker compose restart` |
| Остановка | `docker compose down` (данные в томах сохраняются) |
| Django shell | `docker compose exec web python manage.py shell` |
| Консоль PostgreSQL | `docker compose exec db psql -U monituj monituj` |
| Место на диске | `df -h` и `docker system df` |
| Логи nginx | `sudo tail -f /var/log/nginx/error.log` |

> **Никогда не запускайте `docker compose down -v`** — флаг `-v` удаляет тома, то есть базу и все загруженные файлы.

### Мониторинг

Подключите бесплатный внешний мониторинг доступности (UptimeRobot, Better Stack и т. п.) на адрес `https://monituj.pl/api/health/` — он пришлёт письмо, если сайт перестанет отвечать.

### Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `502 Bad Gateway` | Контейнер `web` не запущен или ещё стартует. `docker compose ps`, `docker compose logs web` |
| `400 Bad Request` на всех страницах | Домена нет в `ALLOWED_HOSTS` |
| `403 CSRF verification failed` при отправке форм | В `CSRF_TRUSTED_ORIGINS` нет `https://` адреса сайта |
| Бесконечный редирект | В nginx нет `proxy_set_header X-Forwarded-Proto $scheme;` |
| `413 Request Entity Too Large` при загрузке | Не применён `client_max_body_size` — проверьте конфиг nginx и сделайте `sudo systemctl reload nginx` |
| Не приходят письма | Данные SMTP в `.env`, `docker compose logs worker web`, записи SPF/DKIM у домена |
| Не уходят напоминания, файлы не удаляются по сроку | Не работает `beat` или `worker`: `docker compose ps`, `docker compose logs beat worker` |
| В письмах ссылки на `localhost` | Неверный `SITE_URL` в `.env` |
| Юридические страницы показывают «[uzupełnij: …]» | Не заполнены переменные `LEGAL_*` |

### Чек-лист перед запуском для клиентов

- [ ] `DEBUG=False`, свой `DJANGO_SECRET_KEY`, сложный `POSTGRES_PASSWORD`.
- [ ] HTTPS работает, http редиректит на https.
- [ ] Тестовое письмо дошло и не попало в спам (SPF, DKIM, DMARC настроены).
- [ ] Все переменные `LEGAL_*` заполнены, тексты Regulamin, Polityka prywatności и Umowa powierzenia проверены юристом.
- [ ] Бэкапы делаются по cron и копируются за пределы сервера, восстановление проверено хотя бы раз.
- [ ] `KEEP_DAYS` в cron совпадает с `LEGAL_BACKUP_DAYS`.
- [ ] Настроен внешний мониторинг `/api/health/`.
- [ ] Вход на сервер только по SSH-ключу, ufw включён.
