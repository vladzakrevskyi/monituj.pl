# Monituj

**Monituj pilnuje Twoich dokumentów i terminów.**

Monituj to polska usługa dla firm, które regularnie potrzebują dokumentów od swoich klientów: biur rachunkowych, działów kadr, kancelarii prawnych, pośredników kredytowych czy firm budowlanych. To nie jest „kolejny sposób na przesłanie pliku”, tylko narzędzie, które porządkuje cały proces zbierania dokumentów:

- firma raz przygotowuje prośbę z listą potrzebnych dokumentów i terminem;
- klient dostaje zabezpieczony link i przesyła pliki bez zakładania konta;
- Monituj sam przypomina klientowi o brakujących dokumentach według harmonogramu;
- firma widzi w panelu, u kogo czego brakuje, i akceptuje albo odrzuca pliki, podając powód;
- po upływie wybranego okresu przechowywania pliki są automatycznie i trwale usuwane, a obie strony dostają powiadomienie.

Cały interfejs, wiadomości e-mail i dokumenty prawne są w języku polskim.

## Funkcje

| Obszar | Co potrafi |
|---|---|
| Klienci | Lista z wyszukiwarką i filtrami, liczba aktywnych próśb i brakujących dokumentów, wszystkie dokumenty klienta na jednej stronie |
| Prośby | Lista dokumentów, termin, opcjonalne hasło do linku, wybór okresu przechowywania plików (do 365 dni) |
| Link publiczny `/d/<token>/` | Przesyłanie plików przez klienta bez konta, przeciąganie i upuszczanie, kontrola typu i rozmiaru (do 20 MB), usunięcie własnego pliku przed akceptacją |
| Weryfikacja | Akceptacja lub odrzucenie dokumentu z podaniem powodu – klient dostaje e-mail i może przesłać plik ponownie |
| Przypomnienia | Automatyczne według harmonogramu (pierwsze po N dniach, potem co N dni, maksymalnie N razy, o wybranej godzinie) oraz ręczne; w panelu widać daty wszystkich kolejnych przypomnień |
| Przechowywanie | Automatyczne usuwanie plików po okresie przechowywania; w historii zostaje tylko informacja „plik usunięty” |
| Historia | Dziennik zdarzeń każdej prośby (utworzenie, otwarcie linku przez klienta, przesłanie pliku, decyzje, przypomnienia) |
| Panel | Statystyki: aktywne prośby, brakujące i dostarczone dokumenty, wysłane przypomnienia, ostatnia aktywność |
| Bez konta | `/wyslij-prosbe/` – jedna prośba dziennie bez rejestracji. Nadawca potwierdza prośbę linkiem z maila (dopiero wtedy trafia ona do odbiorcy) i dostaje konto bez hasła: stały link `/dostep/<token>/` otwiera zwykły panel ze wszystkimi jego prośbami. Po ustawieniu hasła limit znika |
| Odbiorca | Jeden stały link `/moje-prosby/<token>/` z listą wszystkich próśb wysłanych na jego adres – od wszystkich nadawców; jest w każdym e-mailu do odbiorcy |
| Zamykanie | Prośbę można zamknąć (i otworzyć ponownie): przypomnienia stają, a odbiorca nie może już przesyłać plików |
| Demo | `/demo/` – każdy odwiedzający dostaje osobne, tymczasowe konto z przykładowymi danymi (usuwane po 24 godzinach, bez wysyłki e-maili) |
| Konto | Rejestracja z potwierdzeniem adresu e-mail, zmiana hasła i adresu e-mail z potwierdzeniem, usunięcie konta z potwierdzeniem mailowym (wszystkie dane są usuwane od razu) |
| E-maile | Wiadomości HTML w stylu strony oraz wersja tekstowa. Wszystkie wychodzą z `no-reply@monituj.pl`; odpowiedź klienta na e-mail dotyczący prośby trafia do firmy, która o dokumenty prosi, a odpowiedzi na pozostałe wiadomości – na `kontakt@monituj.pl` |
| Kontakt | Formularz na `/kontakt/`: wiadomość trafia na `kontakt@monituj.pl` (odpowiedź idzie prosto do nadawcy), nadawca dostaje potwierdzenie; ochrona przed botami i limit wiadomości na adres IP |
| Dokumenty prawne | Regulamin, Polityka prywatności, Polityka cookies, Umowa powierzenia przetwarzania danych – dane firmy są pobierane ze zmiennych środowiskowych |

## Technologie

- **Python 3.14, Django 6.1** – szablony renderowane po stronie serwera i trochę czystego JavaScriptu, bez frameworków frontendowych;
- **PostgreSQL 16** – baza danych;
- **Redis 7 + Celery** – wysyłka e-maili i zadania w tle;
- **Gunicorn + WhiteNoise** – aplikacja i pliki statyczne na produkcji;
- **nginx + Let's Encrypt** – HTTPS na serwerze;
- **Docker Compose** – cały stos na serwerze uruchamiany jednym poleceniem.

Bezpieczeństwo: hasła hashowane algorytmem Argon2, restrykcyjny CSP (`'self'`, bez skryptów i stylów inline), HSTS, bezpieczne ciasteczka, weryfikacja zawartości przesyłanych plików (libmagic), prywatny magazyn plików poza katalogiem publicznym, limity zapytań na adres IP, dziennik audytu.

### Struktura projektu

```
apps/
  accounts/       użytkownicy, logowanie, rejestracja, ustawienia, usuwanie konta
  clients/        klienci
  requests/       prośby, pozycje, link publiczny, prośba bez konta
  documents/      przesyłanie, weryfikacja i przechowywanie plików, usuwanie po terminie
  reminders/      przypomnienia ręczne i automatyczne
  notifications/  wysyłka e-maili i ich rejestr
  audit/          dziennik zdarzeń
  demo/           tymczasowe konta demonstracyjne
  common/         elementy wspólne: strony marketingowe i prawne, middleware, typografia
config/           ustawienia (base / dev / prod), adresy URL, Celery
templates/        szablony HTML stron i e-maili
static/           CSS i JS
deploy/           konfiguracja nginx, szablon .env dla produkcji, skrypt kopii zapasowych
tests/            testy (pytest)
```

### Zadania w tle (Celery beat, co godzinę)

| Zadanie | Co robi |
|---|---|
| `send_automatic_reminders` | Wysyła automatyczne przypomnienia, których termin nadszedł |
| `anonymize_expired_documents` | Usuwa pliki po okresie przechowywania i powiadamia obie strony |
| `delete_unconfirmed_requests` | Usuwa prośby bez konta niepotwierdzone w ciągu 48 godzin (i konta bez hasła utworzone tylko dla nich) |
| `delete_expired_demo_accounts` | Usuwa konta demo starsze niż 24 godziny |

Bez działających kontenerów `worker` i `beat` strona działa, ale przypomnienia nie są wysyłane, a pliki nie są usuwane po terminie. Na produkcji oba uruchamiają się automatycznie razem ze stroną.

---

## Praca lokalna

Potrzebny jest Python 3.14 oraz Docker (dla PostgreSQL i Redisa) albo lokalnie zainstalowane PostgreSQL i Redis.

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

W pliku `.env` ustaw `DJANGO_SECRET_KEY` (dowolny długi ciąg znaków) i ewentualnie dane SMTP. Jeśli e-maile mają być wypisywane w konsoli zamiast wysyłane, ustaw `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.

```bash
docker compose up -d db redis
```

```bash
python manage.py migrate
```

```bash
python manage.py runserver
```

Strona: http://localhost:8000. Zadania w tle (w osobnych terminalach):

```bash
celery -A config worker -l info
```

```bash
celery -A config beat -l info
```

Testy i linter:

```bash
pytest -q
```

```bash
ruff check . && ruff format --check .
```

> Plik `docker-compose.yml` służy wyłącznie do pracy lokalnej: wystawia porty bazy danych i Redisa na zewnątrz i uruchamia `runserver`. Na serwerze używany jest `docker-compose.prod.yml`.

---

## Wdrożenie na serwerze VPS – krok po kroku

Poniżej pełna droga od czystego serwera do działającej strony `https://monituj.pl`. Wszędzie zamiast `monituj.pl` wpisz swoją domenę, a zamiast `1.2.3.4` – adres IP serwera.

**Jak to działa na serwerze:**

```
Internet ──443──▶ nginx (na serwerze, HTTPS, Let's Encrypt)
                    │
                    ▼  127.0.0.1:8000
          ┌──────── Docker Compose ──────────────────────────┐
          │ web (gunicorn + Django)   worker (Celery)        │
          │ beat (harmonogram)        db (PostgreSQL)        │
          │ redis                     wolumeny:              │
          │                           postgres_data (baza),  │
          │                           storage (pliki)        │
          └──────────────────────────────────────────────────┘
```

Na zewnątrz otwarte są tylko porty 22, 80 i 443. Baza danych, Redis i sama aplikacja nie są dostępne z internetu.

### Krok 0. Czego potrzebujesz

- **Serwer VPS**: Ubuntu 24.04 LTS, co najmniej 2 vCPU, 2 GB RAM, 40 GB SSD. Serwer najlepiej wybrać **w UE** (klienci są z Polski, dane podlegają RODO) – kraj serwerowni trzeba potem wpisać w `LEGAL_HOSTING_LOCATION`.
- **Domenę** i dostęp do jej ustawień DNS.
- **Konto SMTP** do wysyłki e-maili: serwis transakcyjny (np. Brevo, Mailgun, Postmark, Amazon SES) albo poczta u hostingodawcy. Potrzebne są: serwer, port, login i hasło.
- **Dane firmy** do dokumentów prawnych: nazwa, adres, NIP, REGON, KRS/CEIDG, adres e-mail do kontaktu.
- **Kod w repozytorium Git.** Jeśli projekt nie jest jeszcze wypchnięty, zrób to na swoim komputerze:

```bash
git add -A && git commit -m "Monituj v1" && git push -u origin main
```

### Krok 1. DNS

U rejestratora domeny dodaj rekordy:

| Typ | Nazwa | Wartość |
|---|---|---|
| A | `@` | `1.2.3.4` |
| A | `www` | `1.2.3.4` |
| AAAA | `@`, `www` | adres IPv6 serwera (jeśli jest) |

Sprawdzenie (propagacja może potrwać od kilku minut do kilku godzin):

```bash
dig +short monituj.pl
```

### Krok 2. Pierwsze logowanie i użytkownik do wdrożeń

Zaloguj się na serwer jako root (dane dostaniesz od hostingodawcy):

```bash
ssh root@1.2.3.4
```

Zaktualizuj system i utwórz użytkownika `deploy`:

```bash
apt update && apt upgrade -y
```

```bash
adduser deploy
```

```bash
usermod -aG sudo deploy
```

Skopiuj swój klucz SSH dla tego użytkownika. Polecenie wykonujesz **na swoim komputerze**; jeśli nie masz klucza, najpierw uruchom `ssh-keygen -t ed25519`:

```bash
ssh-copy-id deploy@1.2.3.4
```

Sprawdź logowanie kluczem **w nowym oknie terminala**:

```bash
ssh deploy@1.2.3.4
```

### Krok 3. Zabezpieczenie serwera

Wszystkie kolejne polecenia wykonujesz na serwerze jako użytkownik `deploy`.

**Wyłączenie logowania hasłem i jako root.** Otwórz konfigurację SSH:

```bash
sudo nano /etc/ssh/sshd_config
```

Ustaw (i odkomentuj) linie:

```
PermitRootLogin no
PasswordAuthentication no
```

Zrestartuj SSH. Nie zamykaj bieżącej sesji, dopóki nie sprawdzisz logowania w nowym oknie:

```bash
sudo systemctl restart ssh
```

**Zapora sieciowa** – otwieramy tylko SSH, HTTP i HTTPS:

```bash
sudo ufw allow OpenSSH
```

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

```bash
sudo ufw enable
```

**Automatyczne aktualizacje bezpieczeństwa:**

```bash
sudo apt install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
```

**Ochrona przed zgadywaniem haseł SSH:**

```bash
sudo apt install -y fail2ban
```

**Plik wymiany (swap)** – na serwerze z 2 GB RAM budowanie obrazu bez niego może się nie udać:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Strefa czasowa** (dla logów; aplikacja zawsze działa w strefie `Europe/Warsaw`):

```bash
sudo timedatectl set-timezone Europe/Warsaw
```

### Krok 4. Instalacja Dockera

Z oficjalnego repozytorium Dockera:

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

Pozwól użytkownikowi `deploy` korzystać z Dockera bez sudo:

```bash
sudo usermod -aG docker deploy
```

Wyloguj się z serwera (`exit`) i zaloguj ponownie, żeby uprawnienia grupy zaczęły działać. Sprawdzenie:

```bash
docker run --rm hello-world
```

> Docker sam zarządza regułami iptables, a porty opublikowane przez kontenery **omijają ufw**. Dlatego w `docker-compose.prod.yml` aplikacja nasłuchuje tylko na `127.0.0.1:8000`, a baza danych i Redis w ogóle nie mają portów na zewnątrz. Nie dodawaj tam sekcji `ports:` bez `127.0.0.1:`.

### Krok 5. Kod na serwerze

Jeśli repozytorium jest prywatne, daj serwerowi klucz tylko do odczytu (deploy key):

```bash
ssh-keygen -t ed25519 -C "monituj-vps" -f ~/.ssh/monituj_deploy -N ""
```

```bash
cat ~/.ssh/monituj_deploy.pub
```

Skopiuj wynik polecenia i dodaj go w serwisie z repozytorium:

- **GitHub:** repozytorium → **Settings → Deploy keys → Add deploy key** (nie zaznaczaj „Allow write access”);
- **GitLab:** projekt → **Settings → Repository → Deploy keys** (bez uprawnień do zapisu).

Wskaż SSH, którego klucza ma używać (dla GitLaba zamień `github.com` na `gitlab.com`):

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/monituj_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
```

Sklonuj projekt do katalogu `/srv/monituj` (podaj adres swojego repozytorium):

```bash
sudo mkdir -p /srv/monituj && sudo chown deploy:deploy /srv/monituj
```

```bash
git clone git@github.com:vladzakrevskyi/monituj.pl.git /srv/monituj
```

```bash
cd /srv/monituj
```

### Krok 6. Plik `.env`

Utwórz go z szablonu produkcyjnego:

```bash
cp deploy/env.production.example .env && chmod 600 .env
```

Wygeneruj klucz tajny i hasło do bazy danych:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

```bash
openssl rand -hex 24
```

Uzupełnij plik:

```bash
nano .env
```

Najważniejsze zmienne:

| Zmienna | Wartość |
|---|---|
| `COMPOSE_FILE` | Zostaw `docker-compose.prod.yml` – dzięki temu zwykłe `docker compose` w tym katalogu zawsze działa na stosie produkcyjnym |
| `DJANGO_SECRET_KEY` | Pierwszy wygenerowany ciąg. Nikomu go nie pokazuj i nie commituj |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `monituj.pl,www.monituj.pl` |
| `CSRF_TRUSTED_ORIGINS` | `https://monituj.pl,https://www.monituj.pl` |
| `SITE_URL` | `https://monituj.pl` – na tej podstawie budowane są wszystkie linki w e-mailach |
| `POSTGRES_PASSWORD` | Drugi wygenerowany ciąg (tylko litery i cyfry – hasło trafia do adresu URL połączenia) |
| `EMAIL_*` | Dane SMTP. Najczęściej port 587 i `EMAIL_USE_TLS=True` |
| `DEFAULT_FROM_EMAIL` | Nadawca wszystkich wiadomości, np. `Monituj <no-reply@monituj.pl>`. Domena musi być skonfigurowana u dostawcy SMTP |
| `CONTACT_EMAIL` | `kontakt@monituj.pl` – tu trafiają wiadomości z formularza kontaktowego i odpowiedzi na e-maile systemowe. Ta skrzynka musi istnieć i odbierać pocztę |
| `LEGAL_*` | Dane firmy. Puste wartości są wyróżniane na stronach prawnych jako „[uzupełnij: …]” |
| `MAINTENANCE_MODE`, `MAINTENANCE_ALLOWED_IPS` | Tryb serwisowy – patrz sekcja „Tryb serwisowy” niżej. Domyślnie wyłączony |
| `LEGAL_BACKUP_DAYS` | Liczba dni przechowywania kopii zapasowych. Musi być równa `KEEP_DAYS` w skrypcie kopii (krok 11) – ta liczba jest podana w polityce prywatności |

Wartości ze spacjami (np. adres firmy) wpisuj bez cudzysłowów.

### Krok 7. Pierwsze uruchomienie

```bash
docker compose up -d --build
```

Pierwsze budowanie obrazu trwa kilka minut. Przy każdym starcie kontener `web` sam wykonuje migracje bazy danych i zbiera pliki statyczne.

Sprawdź, czy wszystkie pięć kontenerów działa (`running`, a `db` ma status `healthy`):

```bash
docker compose ps
```

Przejrzyj logi pod kątem błędów:

```bash
docker compose logs --tail=50 web worker beat
```

Sprawdź, czy aplikacja odpowiada wewnątrz serwera (przekierowanie 301 na https jest prawidłowe):

```bash
curl -sI -H "Host: monituj.pl" http://127.0.0.1:8000/ | head -1
```

### Krok 8. nginx

```bash
sudo apt install -y nginx
```

```bash
sudo cp /srv/monituj/deploy/nginx/monituj.conf /etc/nginx/sites-available/monituj.conf
```

Jeśli masz inną domenę, zmień `server_name` w tym pliku. Włącz stronę i wyłącz domyślną:

```bash
sudo ln -s /etc/nginx/sites-available/monituj.conf /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Co robi ta konfiguracja:

- przekazuje cały ruch do `127.0.0.1:8000`;
- pozwala przesyłać pliki do 25 MB (limit w aplikacji to 20 MB);
- przekazuje aplikacji prawdziwy adres IP odwiedzającego. Nagłówek `X-Forwarded-For` jest **nadpisywany**, a nie uzupełniany: na podstawie tego adresu działają limity (prośba bez konta, demo), więc odwiedzający nie może go podrobić.

### Krok 9. HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
```

```bash
sudo certbot --nginx -d monituj.pl -d www.monituj.pl --redirect -m twoj@email.pl --agree-tos --no-eff-email
```

certbot sam doda do konfiguracji nginx certyfikat i przekierowanie z http na https. Certyfikat odnawia się automatycznie; test odnowienia:

```bash
sudo certbot renew --dry-run
```

Otwórz https://monituj.pl – powinna pojawić się strona główna. Sprawdzenie z konsoli:

```bash
curl -s https://monituj.pl/api/health/
```

Oczekiwana odpowiedź: `{"success": true, "data": {"status": "ok"}}`.

> Na produkcji włączony jest HSTS z opcjami `includeSubDomains` i `preload`: przeglądarki zapamiętają, że domena i **wszystkie jej subdomeny** otwierają się tylko przez HTTPS. Jeśli na subdomenach działa coś bez HTTPS, najpierw przenieś to na HTTPS.

### Krok 10. Administrator i test e-maili

Utwórz konto administratora do panelu `/admin/`:

```bash
docker compose exec web python manage.py createsuperuser
```

Wyślij testowy e-mail na swój adres:

```bash
docker compose exec web python manage.py sendtestemail twoj@email.pl
```

Jeśli wiadomość nie dotarła, sprawdź `docker compose logs web` i dane SMTP w `.env`. Po każdej zmianie `.env` odtwórz kontenery:

```bash
docker compose up -d
```

Żeby wiadomości nie trafiały do spamu, skonfiguruj dla domeny u dostawcy SMTP rekordy **SPF**, **DKIM** i **DMARC** (dostawca pokaże, jakie rekordy DNS dodać). Minimalny rekord DMARC: TXT `_dmarc.monituj.pl` → `v=DMARC1; p=none; rua=mailto:twoj@email.pl`.

Następnie przejdź ręcznie cały proces:

1. Rejestracja → e-mail z potwierdzeniem → logowanie.
2. Dodanie klienta (swój drugi adres e-mail) → utworzenie prośby → e-mail z linkiem.
3. Otwarcie linku i przesłanie pliku PDF → plik widoczny w panelu → akceptacja albo odrzucenie.
4. Sprawdzenie `/demo/` i `/wyslij-prosbe/`.

### Krok 11. Kopie zapasowe

Skrypt `deploy/backup.sh` robi zrzut bazy danych i archiwum przesłanych plików, a kopie starsze niż `KEEP_DAYS` dni usuwa.

```bash
sudo mkdir -p /var/backups/monituj && sudo chown deploy:deploy /var/backups/monituj
```

Próbne uruchomienie:

```bash
/srv/monituj/deploy/backup.sh && ls -lh /var/backups/monituj
```

Codzienne uruchamianie o 3:30 przez cron:

```bash
crontab -e
```

Dodaj linię (okres przechowywania musi być równy `LEGAL_BACKUP_DAYS`):

```
30 3 * * * KEEP_DAYS=30 /srv/monituj/deploy/backup.sh >> /srv/monituj/backup.log 2>&1
```

**Kopiuj kopie zapasowe poza serwer.** Kopia leżąca na tym samym serwerze nie pomoże, jeśli serwer przestanie istnieć. Najprostsze rozwiązanie to codzienny `rsync` lub `rclone` do osobnego magazynu (Storage Box, magazyn zgodny z S3 w UE). Kopie zawierają dane osobowe i dokumenty klientów: przechowuj je wyłącznie w UE i z ograniczonym dostępem.

#### Przywracanie z kopii

```bash
cd /srv/monituj && docker compose stop web worker beat
```

Baza danych (podaj nazwę pliku):

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < /var/backups/monituj/db_2026-09-24_0330.dump
```

Pliki:

```bash
docker run --rm -v monituj_storage:/data -v /var/backups/monituj:/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/storage_2026-09-24_0330.tar.gz -C /data"
```

```bash
docker compose start web worker beat
```

### Krok 12. Aktualizacja strony

Zatwierdź i wypchnij zmiany na swoim komputerze, a potem na serwerze:

```bash
cd /srv/monituj && ./deploy/backup.sh
```

```bash
git pull
```

```bash
docker compose up -d --build
```

Migracje wykonają się automatycznie przy starcie kontenera `web`. Podczas odtwarzania kontenera strona jest niedostępna przez kilka sekund.

Powrót do poprzedniej wersji: `git log --oneline`, następnie `git checkout <commit>` i `docker compose up -d --build`. Jeśli nowa wersja zmieniała bazę danych (migracje), razem z kodem przywróć też bazę z kopii wykonanej przed aktualizacją.

Co kilka miesięcy warto zaktualizować obrazy PostgreSQL i Redisa (w obrębie tych samych wersji 16 i 7):

```bash
docker compose pull db redis && docker compose up -d
```

Usuwanie starych obrazów po aktualizacjach:

```bash
docker image prune -f
```

---

## Utrzymanie

### Przydatne polecenia

Wszystkie polecenia uruchamiasz z katalogu `/srv/monituj`.

| Co | Polecenie |
|---|---|
| Stan kontenerów | `docker compose ps` |
| Logi na żywo | `docker compose logs -f web worker beat` |
| Restart wszystkiego | `docker compose restart` |
| Zatrzymanie | `docker compose down` (dane w wolumenach zostają) |
| Konsola Django | `docker compose exec web python manage.py shell` |
| Konsola PostgreSQL | `docker compose exec db psql -U monituj monituj` |
| Miejsce na dysku | `df -h` oraz `docker system df` |
| Logi nginx | `sudo tail -f /var/log/nginx/error.log` |

> **Nigdy nie uruchamiaj `docker compose down -v`** – flaga `-v` usuwa wolumeny, czyli bazę danych i wszystkie przesłane pliki.

### Tryb serwisowy (maintenance mode)

Na czas prac (np. większej migracji danych) możesz pokazać odwiedzającym stronę „Prace techniczne” (HTTP 503). W pliku `.env` ustaw:

```
MAINTENANCE_MODE=True
MAINTENANCE_ALLOWED_IPS=83.12.34.56,2a01:4f8::1,10.0.0.0/24
```

`MAINTENANCE_ALLOWED_IPS` to lista adresów oddzielonych przecinkami – pojedyncze IPv4 i IPv6 albo całe zakresy. Osoby z tych adresów widzą serwis normalnie, z pomarańczowym paskiem przypominającym, że tryb serwisowy jest włączony. Swój adres sprawdzisz poleceniem `curl -4 ifconfig.me` (lub `-6` dla IPv6). Zmiana zaczyna działać po odtworzeniu kontenerów:

```bash
docker compose up -d
```

Wyłączenie: `MAINTENANCE_MODE=False` i ponownie `docker compose up -d`. Adres `/api/health/` działa także w trybie serwisowym. Zadania w tle (przypomnienia, usuwanie plików po terminie) nie są wstrzymywane.

### Monitoring

Podłącz darmowy zewnętrzny monitoring dostępności (UptimeRobot, Better Stack itp.) pod adres `https://monituj.pl/api/health/` – dostaniesz e-mail, gdy strona przestanie odpowiadać.

### Najczęstsze problemy

| Objaw | Przyczyna i rozwiązanie |
|---|---|
| `502 Bad Gateway` | Kontener `web` nie działa albo jeszcze startuje. `docker compose ps`, `docker compose logs web` |
| `400 Bad Request` na wszystkich stronach | Domeny nie ma w `ALLOWED_HOSTS` |
| `403 CSRF verification failed` przy wysyłaniu formularzy | W `CSRF_TRUSTED_ORIGINS` brakuje adresu strony z `https://` |
| Nieskończone przekierowanie | W nginx brakuje `proxy_set_header X-Forwarded-Proto $scheme;` |
| `413 Request Entity Too Large` przy przesyłaniu pliku | Nie działa `client_max_body_size` – sprawdź konfigurację nginx i wykonaj `sudo systemctl reload nginx` |
| E-maile nie dochodzą | Dane SMTP w `.env`, `docker compose logs worker web`, rekordy SPF/DKIM domeny |
| Przypomnienia nie wychodzą, pliki nie są usuwane po terminie | Nie działa `beat` albo `worker`: `docker compose ps`, `docker compose logs beat worker` |
| Linki w e-mailach prowadzą do `localhost` | Błędny `SITE_URL` w `.env` |
| Strony prawne pokazują „[uzupełnij: …]” | Nie uzupełniono zmiennych `LEGAL_*` |

### Lista kontrolna przed udostępnieniem klientom

- [ ] `DEBUG=False`, własny `DJANGO_SECRET_KEY`, silne `POSTGRES_PASSWORD`.
- [ ] HTTPS działa, http przekierowuje na https.
- [ ] Testowy e-mail dotarł i nie trafił do spamu (SPF, DKIM i DMARC skonfigurowane).
- [ ] Wszystkie zmienne `LEGAL_*` są uzupełnione, a Regulamin, Polityka prywatności i Umowa powierzenia zostały sprawdzone przez prawnika.
- [ ] Kopie zapasowe wykonują się przez cron i są kopiowane poza serwer; przywracanie zostało przetestowane przynajmniej raz.
- [ ] `KEEP_DAYS` w cronie jest równe `LEGAL_BACKUP_DAYS`.
- [ ] Skonfigurowany jest zewnętrzny monitoring `/api/health/`.
- [ ] Logowanie na serwer tylko kluczem SSH, ufw jest włączony.
