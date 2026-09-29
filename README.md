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
| Przypomnienia | Automatyczne według harmonogramu (pierwsze po N dniach, potem co N dni, maksymalnie N razy) oraz ręczne. Wychodzą o tej godzinie, o której wysłano prośbę, według zegara odbiorcy (strefy czasowe nadawcy i odbiorcy są wykrywane z przeglądarki; noc przesuwana na 8:00–20:00). W panelu widać daty wszystkich kolejnych przypomnień |
| Przechowywanie | Automatyczne usuwanie plików po okresie przechowywania; w historii zostaje tylko informacja „plik usunięty” |
| Historia | Dziennik zdarzeń każdej prośby (utworzenie, otwarcie linku przez klienta, przesłanie pliku, decyzje, przypomnienia) |
| Panel | Statystyki: aktywne prośby, brakujące i dostarczone dokumenty, wysłane przypomnienia, ostatnia aktywność |
| Bez konta | `/wyslij-prosbe/` – jedna prośba dziennie bez rejestracji. Nadawca potwierdza prośbę linkiem z maila (dopiero wtedy trafia ona do odbiorcy) i dostaje konto bez hasła: stały link `/dostep/<token>/` otwiera zwykły panel ze wszystkimi jego prośbami. Po ustawieniu hasła limit znika |
| Odbiorca | Jeden stały link `/moje-prosby/<token>/` – panel z prośbami wysłanymi na jego adres przez wszystkich nadawców (do uzupełnienia i zakończone); jest w każdym e-mailu do odbiorcy. Użytkownik z kontem (także bez hasła) widzi te same prośby w panelu w zakładce „Otrzymane” |
| Zamykanie | Prośbę można zamknąć (i otworzyć ponownie): przypomnienia stają, a odbiorca nie może już przesyłać plików |
| Demo | `/demo/` – każdy odwiedzający dostaje osobne, tymczasowe konto z przykładowymi danymi (usuwane po 24 godzinach, bez wysyłki e-maili) |
| Konto | Rejestracja z potwierdzeniem adresu e-mail, zmiana hasła i adresu e-mail z potwierdzeniem, usunięcie konta z potwierdzeniem mailowym (wszystkie dane są usuwane od razu) |
| E-maile | Wiadomości HTML w stylu strony oraz wersja tekstowa. Wszystkie wychodzą z `no-reply@monituj.pl`; odpowiedź klienta na e-mail dotyczący prośby trafia do firmy, która o dokumenty prosi, a odpowiedzi na pozostałe wiadomości – na `kontakt@monituj.pl` |
| Kontakt | Formularz na `/kontakt/`: wiadomość trafia na `kontakt@monituj.pl` (odpowiedź idzie prosto do nadawcy), nadawca dostaje potwierdzenie; ochrona przed botami i limit wiadomości na adres IP |
| Plany i płatności | Płaci się za liczbę **próśb w toku** (wysłanych, niezamkniętych, czekających na dokumenty): Free 3, Start 20, Biuro 75, Pro 250 – miesięcznie albo rocznie. Nowe konto ma 30 dni płatnego planu bez karty – tego, który wybrano w Cenniku przed rejestracją (`/rejestracja/?plan=pro`, także przez Google), domyślnie Biuro – potem Free. Po potwierdzeniu adresu konto z wybranym planem trafia od razu na „Plan i płatności”. Płatność przez Stripe (Checkout, portal klienta), zakładka „Plan i płatności” w panelu. Po przekroczeniu limitu nic się nie zatrzymuje – blokowane jest tylko wysłanie nowej prośby. Plany i ceny: `apps/billing/plans.py` |
| Dokumenty prawne | Regulamin, Polityka prywatności, Polityka cookies, Umowa powierzenia przetwarzania danych – dane firmy są pobierane ze zmiennych środowiskowych |

## Technologie

- **Python 3.14, Django 6.1** – szablony renderowane po stronie serwera i trochę czystego JavaScriptu, bez frameworków frontendowych;
- **PostgreSQL 16** – baza danych;
- **Redis 7 + Celery** – wysyłka e-maili i zadania w tle;
- **Gunicorn + WhiteNoise** – aplikacja i pliki statyczne na produkcji;
- **nginx + Let's Encrypt** – HTTPS na serwerze;
- **Docker Compose** – cały stos na serwerze uruchamiany jednym poleceniem.

Bezpieczeństwo: logowanie dopiero po potwierdzeniu adresu e-mail, limity prób logowania, resetów hasła, wysyłanych e-maili i przesyłanych plików, hasła hashowane algorytmem Argon2, restrykcyjny CSP (`'self'`, bez skryptów i stylów inline), HSTS, bezpieczne ciasteczka, weryfikacja zawartości przesyłanych plików (libmagic), prywatny magazyn plików poza katalogiem publicznym, limity zapytań na adres IP, dziennik audytu.

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
deploy/           konfiguracja nginx, szablon .env dla produkcji
tests/            testy (pytest)
```

### SEO

- **Główna fraza:** „zbieranie dokumentów od klientów”, obok „przypomnienia o dokumentach” i „brakujące dokumenty”. Wokół tego zbudowane są tytuły, opisy, nagłówki i treści.
- **Metadane** wszystkich publicznych stron są w jednym miejscu: `apps/common/seo.py` (opis do 155 znaków, obrazek Open Graph, dane schema.org). Każdy tytuł ma format „Nazwa strony | monituj.pl” i mieści się w 60 znakach; hasło „Przestań gonić klientów o dokumenty” jest w opisach, nagłówkach i obrazkach, nie w tytułach.
- **Linki:** każdy `<a>` ma atrybut `title` – niejednoznaczne (logo, „Otwórz”, paginacja) opisane w szablonach, pozostałe uzupełniane automatycznie tekstem linku (`apps/common/link_titles.py`), także w e-mailach. Strona, której tam nie ma, dostaje `noindex` – nowa podstrona jest prywatna, dopóki świadomie jej nie dodasz.
- **Treści SEO:** strony branż `/dla-kogo/<branża>/` (treść w `apps/common/content.py`, `SEGMENT_PAGES`) i poradnik `/poradnik/jak-zbierac-dokumenty-od-klientow/`.
- **Dla wyszukiwarek:** `/robots.txt`, `/sitemap.xml`, dane strukturalne JSON-LD (Organization, WebSite, SoftwareApplication, FAQPage, BreadcrumbList, Article), nagłówek `X-Robots-Tag: noindex` dla panelu, API i linków z tokenem.
- **Dla asystentów AI:** `/llms.txt` (skrót) i `/llms-full.txt` (pełny opis z FAQ).
- **Ikony i podglądy:** favicony, ikony aplikacji, `site.webmanifest` i obrazki 1200×630 dla social mediów w `static/images/`. Po zmianie tekstów wygeneruj je ponownie: `.venv/bin/python scripts/brand_images.py`.
- **Google Tag Manager i cookies:** GTM włącza zmienna `GTM_ID` (np. `GTM-NWZ96857`), a narzędzia uruchamiane przez GTM wymienia `TRACKING_SERVICES` (np. `ga4,meta_pixel`; dostępne: `ga4`, `google_ads`, `meta_pixel`, `clarity`, `linkedin`). Z tej listy powstają kategorie w banerze cookies (niezbędne, analityczne, marketingowe, funkcjonalne – pokazywane tylko te, które mają narzędzie), okno „Ustawienia cookies”, tabele w Polityce cookies, sekcje w Polityce prywatności i wpisy w CSP. Opisy narzędzi są w `apps/common/cookies.py` – nowe narzędzie dopisujesz tam (dostawca, cel, cookies, domeny do CSP) i dodajesz do `TRACKING_SERVICES`. Po każdej zmianie listy odwiedzający są pytani o zgodę ponownie; zgoda wygasa też po 12 miesiącach.
  - GTM wczytuje się tylko na publicznych stronach (nigdy w panelu ani na linkach z tokenem) i dopiero po zgodzie na co najmniej jedną kategorię (Google Consent Mode v2, `static/js/consent.js`).
  - Kategorie przekładają się na typy zgód: analityczne → `analytics_storage`, marketingowe → `ad_storage`, `ad_user_data`, `ad_personalization`, funkcjonalne → `personalization_storage`. Tagi Google czytają je same; innym tagom ustaw w GTM „Ustawienia zgody → Wymagaj dodatkowej zgody” z typem ich kategorii. Przy każdej decyzji do `dataLayer` trafia też zdarzenie `cookie_consent_update` (np. `cookie_consent.marketing = true`) do użycia w regułach.
  - Wycofanie zgody usuwa cookies danej kategorii z domeny Serwisu i przeładowuje stronę, żeby zatrzymać działające tagi.
  - Tagi dodawaj z wbudowanych szablonów GTM albo z galerii szablonów – własne „Custom HTML” zablokuje CSP.
- **Po wdrożeniu:** dodaj domenę w [Google Search Console](https://search.google.com/search-console) i Bing Webmaster Tools (tokeny w `GOOGLE_SITE_VERIFICATION` / `BING_SITE_VERIFICATION`), zgłoś `https://monituj.pl/sitemap.xml` i sprawdź podgląd linku np. w debuggerze Facebooka lub LinkedIn Post Inspector. `SITE_URL` musi być adresem `https://` – z niego powstają adresy kanoniczne.

### Kontrola zależności

Dependabot (`.github/dependabot.yml`) co tydzień proponuje aktualizacje pakietów i obrazów Dockera. Znane podatności w zależnościach sprawdzisz lokalnie:

```bash
pip-audit -r requirements/prod.txt
```

### Zadania w tle (Celery beat)

| Zadanie | Co robi |
|---|---|
| `send_automatic_reminders` (co 5 minut) | Wysyła automatyczne przypomnienia, których termin nadszedł |
| `send_upload_emails` (co minutę) | Wysyła nadawcy e-mail o nowych dokumentach – gdy klient przestanie przesyłać pliki na minutę, jeden e-mail zbiera wszystkie (najpóźniej po 10 minutach). Pomija dokumenty, które nadawca już zobaczył w panelu, i prośby zakończone e-mailem „komplet dokumentów” |
| `anonymize_expired_documents` | Usuwa pliki po okresie przechowywania i powiadamia obie strony |
| `delete_unconfirmed_requests` | Usuwa prośby bez konta niepotwierdzone w ciągu 48 godzin (i konta bez hasła utworzone tylko dla nich) |
| `delete_old_cookie_consents` (raz dziennie) | Usuwa wpisy rejestru zgód na cookies starsze niż 3 lata |
| `delete_expired_demo_accounts` | Usuwa konta demo starsze niż 24 godziny |
| `delete_old_throttle_events` | Czyści stare wpisy limitów (logowanie, e-maile, przesyłanie plików) |
| `send_notices` (co minutę) | E-maile o zmianach planu i alerty płatności dla zespołu (kolejka `BillingNotice`) |
| `billing.daily` (co godzinę) | E-maile o końcu okresu próbnego (7 dni i 1 dzień przed, oraz po zakończeniu) i czyszczenie obsłużonych zdarzeń Stripe |

Bez działających kontenerów `worker` i `beat` strona działa, ale przypomnienia i e-maile o nowych dokumentach nie są wysyłane, a pliki nie są usuwane po terminie. Na produkcji oba uruchamiają się automatycznie razem ze stroną.

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

Strona: http://localhost:8000. Zadania w tle – faktury VAT, e-maile o planach, przypomnienia – potrzebują Redisa i Celery. Bez Dockera Redis najprościej z Homebrew (raz):

```bash
brew install redis && brew services start redis
```

Celery (worker razem z harmonogramem, w osobnym terminalu; po zmianie kodu lub `.env` uruchom go ponownie – nie przeładowuje się sam). Na macOS worker działa w jednym procesie (pula `solo`, ustawiona w `config/celery.py`), bo domyślna pula prefork nie działa tam z Celery:

```bash
celery -A config worker -B -l info
```

Webhooki Stripe lokalnie (trzeci terminal):

```bash
stripe listen --forward-to localhost:8000/stripe/webhook/ --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.paused,customer.subscription.resumed,invoice.paid,invoice.payment_failed,charge.refunded,charge.dispute.created
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
| `ERROR_EMAIL` | Adres, na który przychodzą błędy strony i zadań w tle (puste = `CONTACT_EMAIL`), zob. „Monitoring” |
| `CONTACT_EMAIL` | `kontakt@monituj.pl` – tu trafiają wiadomości z formularza kontaktowego i odpowiedzi na e-maile systemowe. Ta skrzynka musi istnieć i odbierać pocztę |
| `LEGAL_*` | Dane firmy. Puste wartości są wyróżniane na stronach prawnych jako „[uzupełnij: …]” |
| `MAINTENANCE_MODE`, `MAINTENANCE_ALLOWED_IPS` | Tryb serwisowy – patrz sekcja „Tryb serwisowy” niżej. Domyślnie wyłączony |
| `ADMIN_URL`, `ADMIN_ALLOWED_IPS` | Adres panelu administratora i adresy IP, z których jest dostępny (zob. krok 10). Na serwerze ustaw oba |
| `LEGAL_TERMS_DATE`, `LEGAL_DPA_DATE`, `LEGAL_PRIVACY_DATE`, `LEGAL_COOKIES_DATE`, `LEGAL_WITHDRAWAL_DATE` | Wersje dokumentów prawnych – data, od której obowiązuje treść każdego z nich (zob. „Zmiana dokumentów prawnych”). Puste = pierwsze wersje |
| `LEGAL_BACKUP_DAYS` | Liczba dni przechowywania kopii zapasowych u hostingu (krok 11), np. `7` – ta liczba jest podana w polityce prywatności |
| `DOCUMENTS_ENCRYPTION_KEY` | **Wymagany.** Klucz główny szyfrujący przesłane dokumenty (zob. „Szyfrowanie dokumentów”). Wygeneruj na serwerze: `python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` i **zapisz kopię poza serwerem** |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Logowanie przez Google (opcjonalnie, zob. „Logowanie przez Google” w kroku 10). Puste = przyciski Google się nie pokazują |

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
- przekazuje aplikacji prawdziwy adres IP odwiedzającego. Nagłówek `X-Forwarded-For` jest **nadpisywany**, a nie uzupełniany: na podstawie tego adresu działają limity (prośba bez konta, demo), więc odwiedzający nie może go podrobić;
- wpuszcza do `/admin/` tylko adresy z listy `allow` – **dopisz tam swój adres IP** (sprawdzisz go poleceniem `curl ifconfig.me` na swoim komputerze), inaczej panel administratora będzie zamknięty także dla Ciebie. Jeśli zmienisz `ADMIN_URL`, zmień też ścieżkę w `location`.

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

Panel administratora jest chroniony na trzy sposoby:

- `ADMIN_ALLOWED_IPS` w `.env` – adresy (albo zakresy, np. `83.12.34.0/24`), z których w ogóle widać panel; wszyscy inni dostają 404, jakby panelu nie było. Działa w aplikacji, niezależnie od nginx;
- `ADMIN_URL` – adres panelu (domyślnie `admin/`); ustaw coś trudnego do zgadnięcia, np. `zaplecze-7f3k2/`. Tego adresu nie ma w `robots.txt`;
- limit prób logowania: po 5 nieudanych próbach na jeden login albo 10 z jednego adresu logowanie jest blokowane na 15 minut, a każda próba trafia do dziennika zdarzeń.

Utwórz konto administratora (panel pod adresem `ADMIN_URL`, domyślnie `/admin/`):

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

#### Logowanie przez Google (opcjonalnie)

1. W [Google Cloud Console](https://console.cloud.google.com/) utwórz projekt, a w nim **APIs & Services → OAuth consent screen**: typ *External*, nazwa „Monituj”, logo, adres kontaktowy, linki do `https://monituj.pl/polityka-prywatnosci/` i `https://monituj.pl/regulamin/`, domena `monituj.pl` (zweryfikowana w Search Console). Zakresy: tylko `openid` i `email`. Na koniec **Publish app** – bez tego zalogują się tylko konta testowe.
2. **Credentials → Create credentials → OAuth client ID**, typ *Web application*. W **Authorized redirect URIs** wpisz dokładnie `https://monituj.pl/logowanie/google/powrot/` (to `SITE_URL` + `/logowanie/google/powrot/`; lokalnie: `http://localhost:8000/logowanie/google/powrot/`). *Authorized JavaScript origins* nie są potrzebne.
3. Client ID i Client secret wpisz w `.env` jako `GOOGLE_OAUTH_CLIENT_ID` i `GOOGLE_OAUTH_CLIENT_SECRET`, potem `docker compose up -d`. Sekret trzymaj tylko w `.env` na serwerze.

Jak to działa i dlaczego jest bezpieczne (szczegóły w `apps/accounts/google.py` i `apps/accounts/google_auth.py`):

- przepływ *authorization code* z PKCE, jednorazowym `state` powiązanym z sesją przeglądarki i `nonce`; podpis tokenu ID sprawdzany kluczami Google, razem z wystawcą, odbiorcą i ważnością;
- konto jest rozpoznawane po stałym identyfikatorze konta Google, nie po adresie e-mail;
- adres, który już ma konto w Monituj: przy Gmailu i Google Workspace konta łączą się od razu, przy innych adresach dopiero po kliknięciu linku z maila w tej samej przeglądarce; o każdym połączeniu właściciel dostaje e-mail;
- konto założone przez kogoś, kto nigdy nie potwierdził adresu, przejmuje właściciel skrzynki – hasło ustawione przez tamtą osobę przestaje działać;
- nowe konto przez Google wymaga akceptacji Regulaminu i Polityki prywatności, jak przy rejestracji hasłem;
- połączenie Google z istniejącym kontem w Ustawieniach wymaga podania hasła (konto bez hasła potwierdza to linkiem z maila) – przejęta sesja nie wystarczy, żeby dopiąć własne Google; po resecie hasła strona pokazuje, które konto Google jest podłączone;
- konto z Google może w każdej chwili ustawić hasło (Ustawienia albo „Nie pamiętasz hasła?”) i logować się na oba sposoby; Google można odłączyć tylko, gdy konto ma hasło.

### Krok 11. Kopie zapasowe

Kopie zapasowe robi hosting: codziennie między północą a 3:00 zapisuje cały serwer i przechowuje 7 ostatnich kopii (wliczając kopie zrobione ręcznie). Przywracasz je w panelu hostingu – cały serwer wraca do stanu z wybranego dnia.

W `.env` ustaw `LEGAL_BACKUP_DAYS=7`. Ta liczba trafia do Polityki prywatności, Regulaminu, Umowy powierzenia i maila po usunięciu konta, więc musi odpowiadać rzeczywistej rotacji kopii. Jeśli zmienisz plan kopii u hostingu, zmień też tę wartość.

### Krok 12. Aktualizacja strony

Zatwierdź i wypchnij zmiany na swoim komputerze, potem na serwerze **jedno polecenie**:

```bash
/srv/monituj/deploy/deploy.sh
```

Skrypt po kolei:

1. robi kopię bazy danych do `/srv/monituj-backups/` (starsze niż `LEGAL_BACKUP_DAYS` dni usuwa – tyle obiecuje Polityka prywatności); jeśli istnieje `deploy/backup.sh`, uruchamia go dodatkowo;
2. pobiera najnowszy `main` z GitHuba (tylko fast-forward – odmówi, jeśli na serwerze ktoś zmienił pliki z repozytorium);
3. buduje nowy obraz i sprawdza ustawienia (`check --deploy`) – zły wpis w `.env` zatrzymuje aktualizację, zanim cokolwiek zostanie podmienione;
4. wykonuje migracje i uruchamia nowe kontenery `web`, `worker`, `beat`;
5. sprawdza, czy strona odpowiada (`/api/health/`);
6. uruchamia `post_deploy`: synchronizuje Stripe (produkty, ceny, VAT, portal, zdarzenia webhooka), zapisuje obowiązujące wersje dokumentów prawnych w archiwum, dopisuje do kolejki faktury VAT za płatności, których webhook zaginął, i wypisuje raport – tryby Stripe / inFakt / GUS, tryb serwisowy, puste dane firmy, zaległe faktury i e-maile;
7. jeśli przed stroną stoi Cloudflare, przypomina o liście adresów w nginx.

Przy błędzie zatrzymuje się i wypisuje, jak wrócić do poprzedniej wersji (i jak przywrócić zrobioną właśnie kopię bazy). Opcje: `--skip-backup` (gdy kopia się nie udaje), `--update-images` (nowsze obrazy PostgreSQL i Redisa w obrębie tych samych wersji). Podczas podmiany kontenerów strona jest niedostępna przez kilka sekund.

Powrót do poprzedniej wersji: `git log --oneline`, następnie `git checkout <commit>` i `docker compose up -d --build`. Jeśli nowa wersja zmieniała bazę danych (migracje), przywróć też kopię bazy zrobioną przez skrypt (polecenie wypisuje on sam przy błędzie) albo kopię całego serwera w panelu hostingu. Po powrocie wróć na gałąź: `git checkout main`.

Co kilka miesięcy warto zaktualizować obrazy PostgreSQL i Redisa (w obrębie tych samych wersji 16 i 7): `deploy/deploy.sh --update-images`. Stare obrazy skrypt usuwa sam.

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

### Cloudflare przed serwerem

Gdy strona stoi za Cloudflare, nginx widzi adresy Cloudflare zamiast adresów odwiedzających – a z adresu IP korzysta tryb serwisowy, lista adresów panelu administratora i limity prób (logowanie, rejestracja, formularze). Prawdziwy adres podaje Cloudflare w nagłówku `CF-Connecting-IP`; nginx przyjmuje go **tylko od serwerów Cloudflare** (moduł `real_ip`), więc nikt, kto łączy się z serwerem z pominięciem Cloudflare, nie podrobi swojego adresu. Aplikacja niczego nie zmienia – dostaje od nginx już prawdziwy adres.

1. Plik z adresami Cloudflare (i odświeżanie raz w miesiącu). Skrypt działa jako root, więc najpierw jego kopia trafia do `/usr/local/sbin` – tam może pisać tylko root. (Z `/srv/monituj` go nie uruchamiaj: te pliki może zmienić użytkownik `deploy`, a root wykonałby cudzy kod.)

```bash
sudo install -o root -g root -m 755 /srv/monituj/deploy/nginx/update-cloudflare-ips.sh /usr/local/sbin/update-cloudflare-ips
```

```bash
sudo /usr/local/sbin/update-cloudflare-ips
```

```bash
echo "0 4 1 * * root /usr/local/sbin/update-cloudflare-ips >> /var/log/cloudflare-ips.log 2>&1" | sudo tee /etc/cron.d/cloudflare-ips
```

   Jeśli skrypt w repozytorium kiedyś się zmieni, powtórz polecenie `install`.

2. W `/etc/nginx/sites-available/monituj.conf`, w każdym bloku `server { … }` obsługującym stronę (także w tym z `listen 443`), dopisz:

```
include /etc/nginx/snippets/cloudflare-real-ip.conf;
```

   i w `location` ustaw `proxy_set_header X-Forwarded-For $remote_addr;` (nadpisuje nagłówek – jak w `deploy/nginx/monituj.conf`).

3. Sprawdź i przeładuj:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

4. Sprawdzenie: w trybie serwisowym strona „Prace techniczne” pokazuje „Twój adres IP” – teraz Twój, a nie Cloudflare (`172.64…`, `104.…`, `2606:4700…`).

W Cloudflare ustaw SSL/TLS na **Full (strict)**. Dodatkowo możesz w zaporze (ufw) wpuszczać ruch na porty 80 i 443 tylko z adresów Cloudflare – wtedy serwera nie da się obejść.

### Tryb serwisowy (maintenance mode)

Na czas prac (np. większej migracji danych) możesz pokazać odwiedzającym stronę „Prace techniczne” (HTTP 503). W pliku `.env` ustaw:

```
MAINTENANCE_MODE=True
MAINTENANCE_ALLOWED_IPS=83.12.34.56,2a01:4f8::1,10.0.0.0/24
```

`MAINTENANCE_ALLOWED_IPS` to lista adresów oddzielonych przecinkami – pojedyncze IPv4 i IPv6 albo całe zakresy. Osoby z tych adresów widzą serwis normalnie, z pomarańczowym paskiem przypominającym, że tryb serwisowy jest włączony. Najprościej: otwórz stronę w trybie serwisowym – pod komunikatem widać „Twój adres IP”, dokładnie ten, który widzi serwis (dla IPv6 także sieć `/64`). Domowy adres IPv6 zmienia się w obrębie tej sieci, więc wpisz całą sieć, np. `2a01:110f:1234:5678::/64`. Przeglądarka często łączy się przez IPv6, nawet gdy `curl -4 ifconfig.me` pokazuje adres IPv4. Zmiana w `.env` zaczyna działać dopiero po odtworzeniu kontenerów (`docker compose restart` jej nie wczyta):

```bash
docker compose up -d --force-recreate web
```

Wyłączenie: `MAINTENANCE_MODE=False` i ponownie `docker compose up -d`. Adres `/api/health/` i webhooki płatności (`/stripe/webhook/`, `/infakt/webhook/`) działają także w trybie serwisowym – zakupy i zmiany planu zapisują się od razu. Zadania w tle (przypomnienia, usuwanie plików po terminie) nie są wstrzymywane.

### Szyfrowanie dokumentów

Pliki przesłane przez klientów leżą w wolumenie Dockera `monituj_storage` (na serwerze: `/var/lib/docker/volumes/monituj_storage/_data/`) pod losowymi nazwami i są **zaszyfrowane** (AES-256-GCM, osobny klucz dla każdego pliku). Klucze plików są w bazie danych, zaszyfrowane kluczem głównym `DOCUMENTS_ENCRYPTION_KEY`, który jest tylko w `.env`. Skopiowany dysk, wolumen albo kopia zapasowa hostingu bez tego klucza jest bezużyteczna. Szczegóły: `apps/documents/encryption.py`.

- **Zapisz klucz poza serwerem** (menedżer haseł). Bez niego żadnego dokumentu nie da się odczytać – nie ma „resetu”.
- Bez klucza strona produkcyjna się nie uruchomi – to celowe.
- Pliki zapisane przed włączeniem szyfrowania zaszyfruje polecenie (można przerwać i uruchomić ponownie):

```bash
docker compose exec web python manage.py encrypt_documents
```

- Zmiana klucza głównego (np. gdy ktoś mógł go poznać): nowy klucz wpisz w `DOCUMENTS_ENCRYPTION_KEY`, stary w `DOCUMENTS_ENCRYPTION_OLD_KEYS`, `docker compose up -d`, potem:

```bash
docker compose exec web python manage.py rewrap_document_keys
```

  Na koniec usuń stary klucz z `DOCUMENTS_ENCRYPTION_OLD_KEYS` i ponownie `docker compose up -d`.
- Szyfrowanie chroni przed wyciekiem dysku i kopii zapasowych, nie przed przejęciem działającego serwera (klucz jest w jego `.env`) – dlatego nadal ważne są aktualizacje i zabezpieczenia z kroku 3.

Każde pobranie dokumentu jest zapisywane w dzienniku zdarzeń (kto: nadawca czy odbiorca, kiedy, adres IP) i widoczne w historii prośby.

### Płatności (Stripe)

Dane do faktury (osoba prywatna albo firma z NIP i adres) klient podaje w panelu – „Plan i płatności” → „Dane do faktury” – **zanim zapłaci**; bez nich zakup i zmiana planu są zablokowane. Polska firma podaje **tylko NIP**: nazwę i adres Monituj pobiera z bazy REGON GUS (API BIR 1.1 – każda firma, także spoza VAT) i nie da się ich zmienić; status VAT dochodzi z wykazu podatników VAT Ministerstwa Finansów (`wl-api.mf.gov.pl`). NIP musi mieć poprawną sumę kontrolną, MF nie może go odrzucić, a firma nie może mieć zakończonej działalności. Dane wpisuje się ręcznie tylko dla firmy zagranicznej albo gdy żaden rejestr jej nie zna (lub chwilowo nie odpowiada). Limit: 20 sprawdzeń NIP na godzinę na konto.

GUS: `GUS_MODE=test` używa publicznego klucza testowego GUS i **zanonimizowanych danych testowych** (np. „ul. Test-Krucza”) – tylko lokalnie. Na produkcji: bezpłatny klucz z https://api.stat.gov.pl/Home/RegonApi (przychodzi e-mailem), potem `GUS_MODE=production` i `GUS_API_KEY=...`. Bez klucza działa sam wykaz MF (tylko firmy zarejestrowane do VAT; pozostałe wpisują dane ręcznie). Z tych danych powstaje faktura VAT, a Monituj kopiuje je też do klienta w Stripe; w portalu Stripe edycja danych klienta jest wyłączona (po zmianie uruchom ponownie `stripe_setup`).

Płatności obsługuje Stripe: klient płaci na stronie Stripe Checkout, a kartę, faktury, zmianę planu i rezygnację ma w portalu klienta Stripe (przycisk w zakładce „Plan i płatności”). Monituj nie widzi danych kart. Stan subskrypcji trafia do Monituj przez webhook `/stripe/webhook/` (tabela `BillingAccount`, podgląd w `/admin/` → „Płatności”).

**Sandbox i live.** `.env` ma dwa komplety kluczy, a `STRIPE_MODE` wybiera, który działa:

```
STRIPE_MODE=sandbox
STRIPE_SANDBOX_SECRET_KEY=sk_test_...
STRIPE_SANDBOX_WEBHOOK_SECRET=whsec_...
STRIPE_LIVE_SECRET_KEY=sk_live_...
STRIPE_LIVE_WEBHOOK_SECRET=whsec_...
```

Przełączenie to zmiana jednej linii i `docker compose up -d`. Klucz live wpisany w miejsce sandboxa (i odwrotnie) zatrzyma start strony. Subskrypcje z sandboxa nie działają w trybie live – każdy tryb ma własnych klientów w Stripe. W sandboxie panel pokazuje kartę testową `4242 4242 4242 4242`.

**Pierwsze uruchomienie (osobno dla każdego trybu):**

1. Stripe Dashboard → Developers → API keys: skopiuj *Secret key* do `.env` i uruchom ponownie kontenery.
2. Utwórz produkty, ceny, stawkę VAT i ustawienia portalu:

```bash
docker compose exec web python manage.py stripe_setup
```

   Na serwerze (publiczny `https://` w `SITE_URL`) od razu zarejestruj webhook – polecenie wypisze `whsec_...` do wpisania w `.env`:

```bash
docker compose exec web python manage.py stripe_setup --create-webhook
```

   Lokalnie webhook przekazuje Stripe CLI (sekret `whsec_...` wypisze samo polecenie):

```bash
stripe listen --forward-to localhost:8000/stripe/webhook/ --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.paused,customer.subscription.resumed,invoice.paid,invoice.payment_failed,charge.refunded,charge.dispute.created
```

3. W Stripe Dashboard → Settings → Billing: włącz e-maile o nieudanych płatnościach (faktury i potwierdzenia płatności wyłącz – patrz „Faktury VAT” niżej), a w *Subscriptions and emails → Manage failed payments* ustaw ponawianie (np. przez 2 tygodnie), a potem **anulowanie** subskrypcji – wtedy konto samo wraca do planu Free.
4. Settings → Business → Public details: nazwa firmy, adres i NIP na fakturach.

Saldo klienta (kredyt po zmianie na tańszy plan albo z rocznej na miesięczną) Monituj odczytuje ze Stripe przy każdej synchronizacji (`BillingAccount.credit`) i pokazuje w „Plan i płatności”. Kody rabatowe są wyłączone – zwroty liczone są od cen z cennika.

Zmiana ceny: popraw `apps/billing/plans.py`, wdróż i uruchom ponownie `stripe_setup` – powstanie nowa cena w Stripe (dla nowych zamówień); trwające subskrypcje zachowują starą, dopóki ich nie zmienisz w Stripe. Regulamin wymaga uprzedzenia klientów o podwyżce 30 dni wcześniej.

Okres próbny: każde nowe konto ma 30 dni wybranego planu (`BillingAccount.trial_plan`, domyślnie Biuro). Przedłużenie – w `/admin/` → „Płatności” zmień `trial_ends_at` i wyczyść `trial_notices`.

Usunięcie konta najpierw anuluje w Stripe wszystkie subskrypcje tego użytkownika (pytając Stripe, nie lokalną kopię); jeśli Stripe nie odpowiada, konto nie jest usuwane (link można użyć ponownie). Potem – zgodnie z Regulaminem (§ 5a) – Monituj sam zwraca na kartę niewykorzystaną część opłaty (cena planu brutto × pozostała część okresu) i saldo po zmianie na tańszy plan, a klienta w Stripe czyści z danych osobowych (imię/nazwa, e-mail, adres, NIP, karty). O **każdym** usunięciu konta przychodzi alert na `CONTACT_EMAIL` (e-mail konta, plan); przy zwrocie – z kwotą i numerem faktury, do której trzeba **wystawić w inFakt fakturę korygującą**. Nieudany zwrot nie blokuje usunięcia konta – alert mówi wtedy, co zwrócić ręcznie. Tak samo saldo, które zostało po zakończeniu subskrypcji (np. po zmianie na tańszy plan i anulowaniu), wraca na kartę automatycznie. Gdy to Ty rozwiązujesz umowę z klientem (§ 11), zwróć niewykorzystaną część ręcznie w Stripe.

Konsumenci: e-mail „Plan … jest aktywny” jest też potwierdzeniem umowy (art. 21 ustawy o prawach konsumenta) – zawiera termin na odstąpienie i żądanie rozpoczęcia usługi, a w załączniku `Monituj-regulamin.html` (Regulamin, umowa powierzenia i formularz odstąpienia w wersji z dnia zamówienia). Oświadczenie o odstąpieniu przychodzi na adres kontaktowy – **potwierdź jego otrzymanie e-mailem**, anuluj subskrypcję w Stripe i zwróć część za dni, które nie minęły (dni do odstąpienia są płatne, jeśli klient zaznaczył żądanie rozpoczęcia usługi).

E-maile o zmianach planu (zakup, zmiana, anulowanie, wznowienie, koniec, nieudana płatność) trafiają do kolejki `BillingNotice` i wysyła je zadanie `send_notices` co minutę. Zwroty zrobione ręcznie w Stripe, spory (chargeback) i podwójne subskrypcje trafiają jako alert na `CONTACT_EMAIL` – plan klienta sam się wtedy nie zmienia, zdecyduj w Stripe. Konta z większą liczbą próśb w toku niż limit: `/admin/` → „Płatności” → filtr „Ponad limit”. Zapis zgody na rozpoczęcie usługi przed upływem 14 dni (`CheckoutConsent`) zostaje po usunięciu konta i jest kasowany po 6 latach. `past_due` (Stripe ponawia płatność) utrzymuje plan najwyżej 14 dni.

### Faktury VAT (inFakt)

Po każdej udanej płatności w Stripe (pierwszej, zmianie planu i każdym odnowieniu) Monituj wystawia w inFakt fakturę VAT oznaczoną jako zapłacona kartą – na firmę, jeśli klient podał w Checkout NIP, w przeciwnym razie na osobę prywatną – i wysyła ją klientowi e-mailem z PDF w załączniku. Klient ma wszystkie faktury w panelu („Plan i płatności” → „Faktury VAT”). Kwota na fakturze = kwota pobrana przez Stripe (od brutto).

```
INFAKT_MODE=sandbox
INFAKT_SANDBOX_API_KEY=...
INFAKT_SANDBOX_WEBHOOK_SECRET=...
INFAKT_LIVE_API_KEY=...
INFAKT_LIVE_WEBHOOK_SECRET=...
INFAKT_SEND_TO_KSEF=False
```

1. Klucz API: inFakt → Ustawienia → Inne opcje → API → „Wygeneruj nowy klucz” z uprawnieniami **api:invoices:read** i **api:invoices:write** (nic więcej). Sandbox: konto na https://konto.sandbox-infakt.pl/rejestracja.
2. Webhook (przyspiesza, ale nie jest konieczny – zadanie co minutę i tak sprawdza status): inFakt → Integracje → Webhooki → adres `https://monituj.pl/infakt/webhook/`, zdarzenia `async_invoice_creation_success` i `async_invoice_creation_error`. Skopiuj „sekretny klucz” do `INFAKT_<MODE>_WEBHOOK_SECRET`, uruchom ponownie kontenery i kliknij „Zweryfikuj”. Lokalnie inFakt nie dotrze do `localhost` – wystarczy samo zadanie.
3. `INFAKT_SEND_TO_KSEF=True`, gdy w inFakt jest włączona integracja z KSeF.
4. Klient ma widzieć tylko fakturę z inFakt, nie dokumenty Stripe:
   - portal klienta Stripe nie pokazuje historii „faktur” (ustawia to `stripe_setup` – uruchom go ponownie po aktualizacji);
   - Stripe Dashboard → Settings → Billing → **Customer emails**: wyłącz „Send finalized invoices and credit notes to customers” i „Successful payments” (potwierdzenia płatności); zostaw e-maile o nieudanych płatnościach i wygasających kartach;
   - Settings → Business → **Customer emails** → „Successful payments”: wyłącz, jeśli jest włączone.

Zadanie `issue_invoices` (co minutę) tworzy fakturę w inFakt, sprawdza wynik i wysyła e-mail; co godzinę `billing.daily` dopisuje zapłacone faktury Stripe z ostatnich 3 dni, których webhook nie dotarł. Gdy inFakt odrzuci dane, faktura dostaje status „Błąd” (`/admin/` → „Faktury VAT”), a na `CONTACT_EMAIL` idzie alert – popraw przyczynę i użyj akcji „Wystaw ponownie” albo wystaw ją ręcznie. Zwroty i spory wymagają faktury korygującej – wystaw ją w inFakt (alert przychodzi automatycznie).

### Zmiana dokumentów prawnych

Każdy dokument ma **własną wersję** – datę, od której obowiązuje jego treść. Daty są w `.env` (`2026-10-01` albo `01.10.2026`; puste = pierwsze wersje z 29.09.2026):

```
LEGAL_TERMS_DATE=        # Regulamin
LEGAL_DPA_DATE=          # umowa powierzenia
LEGAL_PRIVACY_DATE=      # Polityka prywatności
LEGAL_COOKIES_DATE=      # Polityka cookies
LEGAL_WITHDRAWAL_DATE=   # strona „Odstąpienie od umowy”
```

Zmiana Polityki prywatności nie zmienia wersji Regulaminu. Zła data zatrzyma start strony (z komunikatem, która zmienna).

**Archiwum treści.** Każda obowiązująca treść każdego dokumentu (dokładnie tak, jak widać ją na stronie, z danymi z `.env`) jest zapisywana w tabeli `LegalVersion` – przy pierwszej akceptacji, przy każdym zakupie i co godzinę (zadanie `archive_legal_documents`). Podgląd: `/admin/` → „Wersje dokumentów” (tylko do odczytu, nie da się usunąć). Wiersz jest rozpoznawany po skrócie treści (SHA-256), więc zmiana tekstu **bez zmiany daty** też trafia do archiwum – a na `CONTACT_EMAIL` przychodzi alert „zmieniona treść bez nowej daty” (tak samo po zmianie danych w `.env`, które widać w dokumentach, np. dostawcy hostingu).

**Akceptacje.** Każda akceptacja Regulaminu, umowy powierzenia i Polityki prywatności jest zapisywana w `LegalAcceptance`: dokument, jego wersja, **link do dokładnej treści w archiwum**, data, sposób (rejestracja hasłem, Google, prośba bez konta, akceptacja nowej wersji), IP i przeglądarka. Podgląd: `/admin/` → „Zgody i akceptacje”. Zakup planu zapisuje w `CheckoutConsent.documents` wersje i skróty Regulaminu, umowy powierzenia i strony odstąpienia – ten zapis zostaje 6 lat, także po usunięciu konta, więc warunki zakupu da się pokazać zawsze.

Gdy zmieniasz dokument:

1. Zmień treść w `templates/legal/`, wdróż i ustaw nową datę tego dokumentu w `.env` na serwerze (`docker compose up -d`). Regulamin i umowa powierzenia: data **co najmniej 14 dni w przód** (tak obiecują). Polityka prywatności i cookies: może obowiązywać od razu. Nowa treść jest widoczna na stronie od wdrożenia. Jeśli zapomnisz o dacie, archiwum i tak zapisze nową treść, a na `CONTACT_EMAIL` przyjdzie alert.
2. Jeśli zmienił się Regulamin, umowa powierzenia albo Polityka prywatności, wyślij użytkownikom informację – każdy dostanie listę tylko tych dokumentów, które się zmieniły:

```bash
docker compose exec web python manage.py notify_legal_update --changes "Krótko: co się zmienia." --dry-run
```

```bash
docker compose exec web python manage.py notify_legal_update --changes "Krótko: co się zmienia."
```

   Polecenie można uruchomić ponownie – nikt nie dostanie maila dwa razy o tych samych wersjach.
3. Od daty nowej wersji każdy zalogowany użytkownik przed wejściem do panelu zobaczy stronę „Zaktualizowaliśmy dokumenty” z listą zmienionych dokumentów i musi je zaakceptować (Ustawienia – w tym usunięcie konta – pozostają dostępne). Konta demo są pomijane.

Poprawka literówki bez zmiany sensu: można zostawić datę – archiwum i tak zapisze nową treść (przyjdzie alert, który wtedy zignoruj).

Decyzje z banera cookies trafiają do anonimowego rejestru `CookieConsent` (losowy identyfikator z przeglądarki, wybór, wersja banera, data – bez IP). Wpisy starsze niż 3 lata usuwa zadanie `delete_old_cookie_consents`.

### Monitoring

Podłącz darmowy zewnętrzny monitoring dostępności (UptimeRobot, Better Stack itp.) pod adres `https://monituj.pl/api/health/` – dostaniesz e-mail, gdy strona przestanie odpowiadać.

**Błędy** przychodzą e-mailem na `ERROR_EMAIL` (puste = `CONTACT_EMAIL`), temat „[Monituj] Błąd: …”: strona, która się wysypała (500), nieudane zadanie w tle (e-maile, przypomnienia, faktury) i każdy błąd zapisany przez Monituj (np. nieudany zwrot w Stripe). W wiadomości jest opis, miejsce w kodzie, adres strony i id użytkownika – **bez danych z formularzy**, bo mogą zawierać dane klientów. Ten sam błąd przychodzi najwyżej raz na 10 minut, a najwięcej 20 wiadomości na godzinę. Pełne logi: `docker compose logs --tail 200 web worker`.

**Dziennik zdarzeń** (`AuditLog`): wpisy konta są przechowywane, dopóki konto istnieje, i znikają razem z nim. Wpisy niezwiązane z żadnym kontem (nieudane logowania na nieistniejące adresy, wejścia w linki usuniętych próśb) codzienne zadanie `delete_old_audit_entries` usuwa po 12 miesiącach – tak mówi Polityka prywatności.

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
| „Płatności są chwilowo niedostępne” | Brak klucza `STRIPE_<MODE>_SECRET_KEY` albo nie uruchomiono `stripe_setup` w tym trybie – `docker compose logs web` |
| Po płatności plan się nie zmienia | Webhook: zły `STRIPE_<MODE>_WEBHOOK_SECRET` albo adres – Stripe Dashboard → Developers → Webhooks pokazuje błędy dostaw |

### Lista kontrolna przed udostępnieniem klientom

- [ ] `DEBUG=False`, własny `DJANGO_SECRET_KEY`, silne `POSTGRES_PASSWORD`.
- [ ] HTTPS działa, http przekierowuje na https.
- [ ] Testowy e-mail dotarł i nie trafił do spamu (SPF, DKIM i DMARC skonfigurowane).
- [ ] Wszystkie zmienne `LEGAL_*` są uzupełnione, a Regulamin, Polityka prywatności i Umowa powierzenia zostały sprawdzone przez prawnika.
- [ ] Kopie zapasowe u hostingu są włączone; przywracanie zostało przetestowane przynajmniej raz.
- [ ] `DOCUMENTS_ENCRYPTION_KEY` jest ustawiony, a jego kopia leży poza serwerem.
- [ ] `ADMIN_URL` i `ADMIN_ALLOWED_IPS` są ustawione, a w nginx w `location /admin/` jest Twój adres IP.
- [ ] `LEGAL_BACKUP_DAYS` odpowiada liczbie dni przechowywania kopii u hostingu.
- [ ] Jeśli włączasz logowanie przez Google: aplikacja OAuth jest opublikowana, a adres przekierowania zgadza się z `SITE_URL`.
- [ ] Skonfigurowany jest zewnętrzny monitoring `/api/health/`.
- [ ] Płatności: `STRIPE_MODE=live`, klucz i webhook trybu live w `.env`, `stripe_setup --create-webhook` uruchomione, testowy zakup i anulowanie przeszły; e-maile i ponawianie płatności ustawione w Stripe (README „Płatności”).
- [ ] Logowanie na serwer tylko kluczem SSH, ufw jest włączony.
