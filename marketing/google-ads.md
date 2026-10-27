# Google Ads для Monituj: тестовая кампания

План на 4 недели теста. Тексты на польском, их можно вставлять в Google Ads как есть.
Длина каждого текста проверена: заголовок до 30 знаков, описание до 90,
быстрая ссылка до 25 (её описание до 35), уточнение до 25.

---

## 0. Сначала подключить отслеживание (до запуска рекламы)

Сайт уже передаёт событие **`sign_up`** в Google Tag Manager, когда человек
зарегистрировался (параметр `method`: `email` или `google`). Событие уходит
только со страницы регистрации и только если посетитель согласился на cookies,
из панели ничего не отправляется.

**В Google Tag Manager:**
1. *Zmienne → Nowa → Zmienna warstwy danych*: имя `method`, название `DLV - method`.
2. *Reguły → Nowa → Zdarzenie niestandardowe*: название события `sign_up`.
3. *Tag → Google Analytics: zdarzenie GA4*: название события `sign_up`,
   параметр `method` = `{{DLV - method}}`, правило `sign_up`.
4. *Tag → Śledzenie konwersji Google Ads*: identyfikator и etykieta konwersji
   из Google Ads (*Cele → Konwersje → Nowa → Witryna*, тип «Rejestracja»),
   правило `sign_up`.
5. *Tag → Łącznik konwersji* (Conversion Linker) на все страницы. Без него
   Google Ads не свяжет регистрацию с кликом по рекламе.
6. Проверить в режиме *Podgląd*: зарегистрироваться тестовым адресом и
   убедиться, что `sign_up` срабатывает. Потом опубликовать контейнер.

**На сервере (это сделать вам самим):** в `.env` поставить
`TRACKING_SERVICES=ga4,google_ads` и перезапустить сайт. Google Ads появится
в баннере cookies и в политике cookies в категории «Marketingowe», и
посетителей спросят о согласии заново. Без этого тег рекламы не должен
работать.

**В GA4:** *Administracja → Zdarzenia* → отметить `sign_up` как *kluczowe*.

> «Отправил первую просьбу» в Google не уйдёт: панель по правилам сайта
> никогда не загружает трекеры. Поэтому на время теста смотрите на это
> внутри Monituj. Почти все новые регистрации будут из рекламы, значит общая
> доля «зарегистрировался → отправил первую просьбу» ≈ доля для рекламы.

---

## 1. Настройки кампании

| Параметр | Значение |
|---|---|
| Тип | **Sieć wyszukiwania** (только поиск). Без Performance Max, без медийной сети, «Partnerzy w sieci wyszukiwania» выключить |
| Цель | Rejestracja (конверсия `sign_up` из шага 0) |
| Ставки | Первые 2 недели: *Maksymalizacja liczby kliknięć* с лимитом CPC 4–5 zł. Когда наберётся 15+ регистраций: *Maksymalizacja liczby konwersji* |
| Бюджет | 30–50 zł в день, тест 4 недели |
| География | Polska, *Obecność: osoby przebywające w lokalizacji* |
| Язык | polski |
| Расписание | пн–пт, 7:00–19:00 (бухгалтеры ищут в рабочее время) |
| Ключевые слова | только во фразовом `"..."` и точном `[...]` соответствии |

---

## 2. Группы объявлений и ключевые слова

### Группа A: «Rozwiązanie» (основная, ~60% бюджета)
Страница: `https://monituj.pl/dla-kogo/biura-rachunkowe/`

```
"program do zbierania dokumentów od klientów"
"zbieranie dokumentów od klientów"
[program do zbierania dokumentów]
"aplikacja do zbierania dokumentów"
"przypomnienia o dokumentach"
"przypominanie klientom o dokumentach"
"program do przypominania klientom"
"portal klienta biuro rachunkowe"
"portal dla klientów biura rachunkowego"
"aplikacja dla biura rachunkowego"
"obieg dokumentów z klientem"
"przesyłanie dokumentów do biura rachunkowego"
```

### Группа B: «Problem» (~25%)
Страница: `https://monituj.pl/`

```
"klient nie przysyła dokumentów"
"jak zbierać dokumenty od klientów"
"jak przypomnieć klientowi o dokumentach"
"brakujące dokumenty od klientów"
"klienci spóźniają się z dokumentami"
"dokumenty od klientów na czas"
```

### Группа C: «KSeF» (~15%, тема сейчас горячая)
Страница: `https://monituj.pl/poradnik/dokumenty-spoza-ksef/`

```
"dokumenty spoza ksef"
"ksef biuro rachunkowe dokumenty"
"jakie dokumenty poza ksef"
"ksef a wyciągi bankowe"
"ksef uprawnienia dla biura rachunkowego"
```

---

## 3. Минус-слова (добавить на уровне кампании)

Отсекают поиск работы, учёбы, шаблонов и людей, которые ищут бухгалтера,
а не программу:

```
praca
oferty pracy
zatrudnię
zatrudnienie księgowej
kurs
szkolenie
studia
egzamin
wzór
wzory
pdf
docx
word
chomikuj
pobierz
druk
formularz
definicja
co to jest
wikipedia
urząd skarbowy
e-urząd
logowanie
aplikacja podatnika
program księgowy
program do faktur
fakturowanie
kpir
pełna księgowość
cennik usług księgowych
biuro rachunkowe cennik
tanie biuro rachunkowe
szukam księgowej
księgowa online
```

> Раз в неделю смотрите *Słowa kluczowe → Wyszukiwane hasła*: всё
> нецелевое добавляйте в минус-слова. В первые две недели это самая
> важная работа в кампании.

> Названия городов (warszawa, kraków, wrocław…) тоже стоит добавить, если в
> поисковых запросах увидите «biuro rachunkowe + город»: это люди ищут
> бухгалтерию, а не программу.

---

## 4. Объявления (Elastyczne reklamy w wyszukiwarce)

Одно объявление на группу. Заголовки и описания одни и те же. Google сам
подбирает сочетания. Закрепите (📌) заголовок 1 на позиции 1.

### Nagłówki (≤ 30 znaków)
```
Koniec z gonieniem klientów      📌 poz. 1
Dokumenty od klientów na czas
Monituj przypomina za Ciebie
Klient bez konta i instalacji
Plan Free za 0 zł
30 dni za darmo, bez karty
Dla biur rachunkowych
Lista braków przy kliencie
Automatyczne przypomnienia
Pytania do klientów z linku
Kalendarz terminów klientów
Dokumenty spoza KSeF
Zbieranie dokumentów online
Wypróbuj demo bez rejestracji
Od 39 zł netto miesięcznie
```

### Teksty reklamy (≤ 90 znaków)
```
Wysyłasz listę dokumentów raz. Monituj sam przypomina klientom o brakach aż do kompletu.
Klient przesyła pliki z linku, bez konta. Ty widzisz, czego brakuje, i akceptujesz.
Pytania do klientów, karta klienta i kalendarz terminów. Plan Free za 0 zł, bez karty.
Wyciągi, paragony, faktury zagraniczne: wszystko spoza KSeF w jednym miejscu.
```

### Ścieżka wyświetlana
`monituj.pl/biuro/dokumenty` (каждая часть не длиннее 15 знаков)

---

## 5. Komponenty (расширения)

### Linki do podstron
| Tekst (≤ 25) | Opis 1 (≤ 35) | Opis 2 (≤ 35) | URL |
|---|---|---|---|
| Jak to działa | Zobacz proces krok po kroku | Film: Monituj w trzy minuty | /jak-to-dziala/ |
| Cennik | Plan Free za 0 zł | Płatne od 39 zł netto/mies. | /cennik/ |
| Demo bez rejestracji | Gotowe konto z przykładami | Wypróbuj w jedno kliknięcie | /demo/ |
| Dla biur rachunkowych | Dokumenty co miesiąc na czas | Gotowa lista na każdy miesiąc | /dla-kogo/biura-rachunkowe/ |

### Rozszerzenia objaśnień (≤ 25)
```
Klient bez konta
30 dni za darmo
Bez karty kredytowej
Umowa powierzenia w cenie
Pliki usuwane po czasie
Przypomnienia bez limitu
```

---

## 6. Как оценить тест через 4 недели

Смотрите не на клики, а на три числа:

1. **Стоимость регистрации** = расход / число `sign_up`.
2. **Активация**: какая доля новых аккаунтов отправила первую просьбу
   (смотреть в Monituj).
3. **Оплаты**: сколько дошли до платного плана после 30 дней пробного периода.

Ориентир: клиент на тарифе Biuro (89 zł/мес.), который остаётся на год,
приносит около 1070 zł. Если платит примерно каждый десятый
зарегистрировавшийся, регистрация должна стоить не больше примерно
**30–50 zł**. Дороже — меняем слова и тексты или останавливаем рекламу.
Дешевле — увеличиваем бюджет.
