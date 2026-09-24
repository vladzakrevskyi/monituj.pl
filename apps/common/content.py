"""Marketing copy shared between the landing page and the dedicated pages
(FAQ teaser vs full FAQ, "Dla kogo" teaser vs full page)."""

from apps.documents.validation import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE

_EXTENSIONS = ", ".join(sorted(ext.upper() for ext in ALLOWED_EXTENSIONS))
_MAX_MB = MAX_UPLOAD_SIZE // (1024 * 1024)

FAQ_CATEGORIES = [
    ("firma", "Dla Twojej firmy"),
    ("klient", "Dla Twoich klientów"),
    ("dane", "Bezpieczeństwo i dane"),
    ("konto", "Konto i koszty"),
]

FAQ = [
    {
        "category": "firma",
        "home": True,
        "q": "Czym Monituj różni się od dysku w chmurze albo maila?",
        "a": (
            "Dysk i mail tylko przechowują pliki – to Ty musisz pamiętać, czego "
            "brakuje, i przypominać klientom. Monituj prowadzi listę potrzebnych "
            "dokumentów, sam wysyła przypomnienia według ustalonego harmonogramu, "
            "pokazuje status każdego dokumentu i usuwa pliki po ustalonym czasie."
        ),
    },
    {
        "category": "firma",
        "home": True,
        "q": "Jak działają automatyczne przypomnienia?",
        "a": (
            "Dla każdej prośby ustawiasz, po ilu dniach wysłać pierwsze "
            "przypomnienie, co ile dni je powtarzać i ile razy maksymalnie. "
            "Przypomnienia wychodzą o tej godzinie, o której wysłałeś prośbę – "
            "według zegara odbiorcy – i przestają, gdy dotrze komplet dokumentów. "
            "W panelu widzisz dokładne daty kolejnych przypomnień."
        ),
    },
    {
        "category": "firma",
        "home": False,
        "q": "Czy mogę przypomnieć klientowi ręcznie?",
        "a": (
            "Tak. W każdej chwili wyślesz przypomnienie jednym kliknięciem – "
            "niezależnie od automatycznego harmonogramu."
        ),
    },
    {
        "category": "firma",
        "home": False,
        "q": "Co, jeśli dokument jest nieczytelny albo niewłaściwy?",
        "a": (
            "Odrzucasz go jednym kliknięciem i podajesz powód. Klient dostaje email "
            "z informacją, co poprawić, i może od razu przesłać nową wersję."
        ),
    },
    {
        "category": "klient",
        "home": True,
        "q": "Czy mój klient musi zakładać konto?",
        "a": (
            "Nie. Klient dostaje email z unikalnym linkiem, otwiera listę "
            "dokumentów w przeglądarce i przesyła pliki. Niczego nie instaluje i "
            "nie zakłada konta."
        ),
    },
    {
        "category": "klient",
        "home": False,
        "q": "Jakie pliki może przesłać klient?",
        "a": (
            f"{_EXTENSIONS} – do {_MAX_MB} MB na plik. Każdy plik sprawdzamy także "
            "pod kątem rzeczywistego typu zawartości, a nie tylko rozszerzenia."
        ),
    },
    {
        "category": "klient",
        "home": False,
        "q": "Skąd klient wie, że dokument dotarł?",
        "a": (
            "Po każdym przesłaniu klient dostaje potwierdzenie z listą dokumentów, "
            "które jeszcze zostały. Gdy komplet dotrze, otrzymuje osobną wiadomość, "
            "a przypomnienia wyłączają się same."
        ),
    },
    {
        "category": "dane",
        "home": True,
        "q": "Jak długo przechowujecie dokumenty?",
        "a": (
            "Tyle, ile ustawisz dla danej prośby: 30, 90 lub 180 dni, rok albo "
            "własny okres – maksymalnie 365 dni od przesłania pliku. Potem plik "
            "jest trwale usuwany, a Ty i Twój klient dostajecie o tym powiadomienie."
        ),
    },
    {
        "category": "dane",
        "home": False,
        "q": "Czy dokumenty moich klientów są bezpieczne?",
        "a": (
            "Każda prośba ma unikalny, trudny do odgadnięcia link, który możesz "
            "dodatkowo zabezpieczyć hasłem. Pliki trafiają do niepublicznego "
            "magazynu z kontrolą dostępu, połączenie jest szyfrowane, a hasła kont "
            "przechowujemy wyłącznie w postaci skrótu."
        ),
    },
    {
        "category": "dane",
        "home": False,
        "q": "Kto jest administratorem danych moich klientów?",
        "a": (
            "Ty. Monituj przetwarza dane Twoich klientów wyłącznie w Twoim imieniu, "
            "na podstawie umowy powierzenia przetwarzania danych, którą zawierasz, "
            "akceptując Regulamin."
        ),
    },
    {
        "category": "konto",
        "home": False,
        "q": "Ile kosztuje Monituj?",
        "a": (
            "Obecnie korzystanie z Monituj jest bezpłatne. Jeśli wprowadzimy płatne "
            "plany, poinformujemy Cię co najmniej 30 dni wcześniej i nic nie "
            "zostanie pobrane bez Twojej zgody."
        ),
    },
    {
        "category": "konto",
        "home": False,
        "q": "Czy mogę wysłać prośbę bez zakładania konta?",
        "a": (
            "Tak – jedną dziennie. Wypełniasz krótki formularz, potwierdzasz go "
            "linkiem z maila i prośba trafia do odbiorcy. Dostajesz też stały "
            "link do panelu: zobaczysz w nim wszystkie swoje prośby, pobierzesz "
            "pliki, zmienisz ustawienia albo zamkniesz prośbę. Gdy ustawisz "
            "hasło, dzienny limit znika."
        ),
    },
    {
        "category": "konto",
        "home": False,
        "q": "Jak usunąć konto?",
        "a": (
            "W Ustawieniach, w sekcji „Usunięcie konta”. Podajesz hasło, a my "
            "wysyłamy link potwierdzający na Twój adres email. Po kliknięciu "
            "usuwamy konto, klientów, prośby i wszystkie pliki od razu. "
            "Automatyczne przypomnienia przestają wychodzić, a odbiorcy "
            "otwartych próśb dostają informację, że prośba jest nieaktualna."
        ),
    },
]

_ICON_LEDGER = '<path d="M4 4h12l4 4v12H4z"/><path d="M8 12h8M8 16h5M8 8h4"/>'
_ICON_SCALES = (
    '<path d="M12 3v18M7 21h10"/><path d="M5 7h14"/>'
    '<path d="M5 7l-3 7a3 3 0 006 0L5 7zM19 7l-3 7a3 3 0 006 0l-3-7z"/>'
)
_ICON_PEOPLE = (
    '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0113 0"/>'
    '<path d="M16 4.5a3.5 3.5 0 010 7M21.5 20a6.5 6.5 0 00-4-6"/>'
)
_ICON_HOUSE = (
    '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>'
)
_ICON_BRIEFCASE = (
    '<rect x="3" y="7" width="18" height="13" rx="2"/>'
    '<path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2M3 13h18"/>'
)

SEGMENTS = [
    {
        "slug": "biura-rachunkowe",
        "title": "Biura rachunkowe",
        "icon": _ICON_LEDGER,
        "teaser": (
            "Comiesięczne faktury i wyciągi od klientów na czas, bez ręcznej pogoni."
        ),
        "problem": (
            "Co miesiąc ta sama pogoń: faktury, wyciągi, raporty. Część klientów "
            "wysyła wszystko na czas, reszta – na ostatnią chwilę, w kilku mailach. "
            "A termin rozliczenia się nie przesuwa."
        ),
        "solution": (
            "Tworzysz prośbę na dany miesiąc z listą dokumentów i terminem. Monituj "
            "sam przypomina klientom, a Ty w panelu widzisz, kto jest gotowy do "
            "księgowania, a kogo trzeba jeszcze dopilnować."
        ),
        "examples": [
            "Faktury sprzedaży",
            "Faktury kosztowe",
            "Wyciągi bankowe",
            "Raport kasowy",
            "Dokumenty kadrowe do listy płac",
        ],
    },
    {
        "slug": "kancelarie",
        "title": "Kancelarie prawne",
        "icon": _ICON_SCALES,
        "teaser": "Komplet dokumentów do sprawy w jednym miejscu, z historią wpływu.",
        "problem": (
            "Do sprawy potrzebujesz kompletu dokumentów, a klient odsyła je na raty, "
            "różnymi kanałami. Trudno ustalić, co już jest, a czego wciąż brakuje."
        ),
        "solution": (
            "Jedna prośba na sprawę – z listą, terminem i opcjonalnym hasłem "
            "dostępu. Każdy dokument ma status, a historia pokazuje, kiedy co "
            "wpłynęło."
        ),
        "examples": [
            "Pełnomocnictwo",
            "Umowy i aneksy",
            "Korespondencja z kontrahentem",
            "Odpis z KRS",
            "Dokumenty dowodowe",
        ],
    },
    {
        "slug": "kadry",
        "title": "Kadry i HR",
        "icon": _ICON_PEOPLE,
        "teaser": "Akta nowego pracownika kompletne przed pierwszym dniem pracy.",
        "problem": (
            "Nowy pracownik to lista dokumentów, które muszą trafić do akt przed "
            "pierwszym dniem pracy. Pilnowanie tego mailami i telefonami zabiera "
            "czas całemu działowi."
        ),
        "solution": (
            "Wysyłasz pracownikowi link z listą dokumentów. Monituj przypomina o "
            "brakach, a Ty wiesz, czego jeszcze brakuje w aktach – bez szukania "
            "załączników w skrzynce."
        ),
        "examples": [
            "Świadectwa pracy",
            "Orzeczenie lekarskie",
            "Kwestionariusz osobowy",
            "Dyplomy i certyfikaty",
            "Oświadczenia pracownika",
        ],
    },
    {
        "slug": "posrednictwo",
        "title": "Nieruchomości, kredyty i ubezpieczenia",
        "icon": _ICON_HOUSE,
        "teaser": "Wniosek rusza, gdy dotrze komplet – bez telefonów do klienta.",
        "problem": (
            "Wniosek stoi, bo klient nie przysłał jednego zaświadczenia. Każdy "
            "dzień zwłoki to ryzyko, że transakcja się opóźni albo przepadnie."
        ),
        "solution": (
            "Lista dokumentów do wniosku z terminem i automatycznymi "
            "przypomnieniami. Widzisz dokładnie, czego brakuje, a klient wie, co "
            "ma jeszcze przesłać."
        ),
        "examples": [
            "Zaświadczenie o dochodach",
            "Wyciągi z konta",
            "Akt notarialny",
            "Dotychczasowa polisa",
            "Dokumenty nieruchomości",
        ],
    },
    {
        "slug": "b2b",
        "title": "Firmy usługowe i B2B",
        "icon": _ICON_BRIEFCASE,
        "teaser": "Onboarding klientów i kontrahentów bez blokujących braków.",
        "problem": (
            "Rozpoczęcie współpracy blokuje brak jednego dokumentu od klienta albo "
            "kontrahenta, a o brakach dowiadujesz się dopiero przy realizacji."
        ),
        "solution": (
            "Standardowa lista dokumentów dla każdego nowego klienta, termin i "
            "przypomnienia. Proces wygląda tak samo za każdym razem i nikt nie musi "
            "o nim pamiętać."
        ),
        "examples": [
            "Umowa i załączniki",
            "Dane rejestrowe firmy",
            "Pełnomocnictwa",
            "Certyfikaty i uprawnienia",
            "Formularze onboardingowe",
        ],
    },
]


# Each industry also has its own page (/dla-kogo/<slug>/), written around
# what people there actually search for.
SEGMENT_PAGES = {
    "biura-rachunkowe": {
        "seo_name": "Dokumenty od klientów biura rachunkowego",
        "seo_description": (
            "Faktury, wyciągi i raporty od klientów przed terminem VAT i JPK – "
            "bez maili i telefonów. Monituj sam przypomina klientom biura "
            "rachunkowego o brakach."
        ),
        "h1": "Dokumenty od klientów biura rachunkowego – na czas, bez pogoni",
        "lead": (
            "Co miesiąc ta sama sytuacja: zbliża się termin rozliczenia, a "
            "połowa klientów jeszcze nie przysłała faktur i wyciągów. Monituj "
            "wysyła każdemu klientowi listę dokumentów za dany miesiąc i sam "
            "przypomina o brakach – Ty tylko księgujesz to, co już dotarło."
        ),
        "pains": [
            "Dziesiątki maili i telefonów „prześlij, proszę, wyciąg za wrzesień”.",
            "Dokumenty spływają na ostatnią chwilę, w kilku wiadomościach naraz.",
            "Trudno powiedzieć, którzy klienci są gotowi do zamknięcia miesiąca.",
        ],
        "benefits": [
            "Każdy klient dostaje tę samą, jasną listę dokumentów na dany miesiąc.",
            "Przypomnienia wychodzą same, aż dotrze komplet – nie musisz pamiętać.",
            "W panelu od razu widzisz, kto ma braki i czego dokładnie brakuje.",
        ],
        "checklist": [
            "Faktury sprzedaży",
            "Faktury kosztowe",
            "Wyciągi bankowe ze wszystkich rachunków",
            "Raport kasowy",
            "Dokumenty importu i WNT",
            "Umowy zawarte w miesiącu",
            "Listy obecności i dokumenty do listy płac",
            "Potwierdzenia zapłaty podatków i ZUS",
        ],
        "faq": [
            {
                "q": "Czy mogę co miesiąc wysyłać klientom tę samą listę?",
                "a": (
                    "Tak. Tworzysz prośbę na dany miesiąc z listą dokumentów i "
                    "terminem przed Twoim terminem rozliczenia. Klient zawsze "
                    "dostaje tę samą, przewidywalną listę, a Ty widzisz, kto ją "
                    "już zamknął."
                ),
            },
            {
                "q": "Czy klient biura musi instalować aplikację albo zakładać konto?",
                "a": (
                    "Nie. Klient dostaje email z linkiem, otwiera listę w "
                    "przeglądarce i przesyła pliki – także z telefonu, np. zdjęcie "
                    "faktury. Wszystkie prośby od Twojego biura ma pod jednym "
                    "stałym linkiem."
                ),
            },
            {
                "q": "Co z danymi klientów biura i RODO?",
                "a": (
                    "Administratorem danych jest Twoje biuro, a Monituj przetwarza "
                    "je w Twoim imieniu na podstawie umowy powierzenia. Pliki są "
                    "automatycznie usuwane po okresie, który ustawisz – pobierz je "
                    "wcześniej do swojego programu księgowego."
                ),
            },
        ],
    },
    "kadry": {
        "seo_name": "Dokumenty do akt nowego pracownika",
        "seo_description": (
            "Świadectwa pracy, badania, kwestionariusz osobowy – komplet do akt "
            "przed pierwszym dniem pracy. Monituj sam przypomina o brakach."
        ),
        "h1": "Komplet dokumentów od nowego pracownika przed pierwszym dniem",
        "lead": (
            "Nowy pracownik to lista dokumentów, które muszą trafić do akt "
            "osobowych, zanim zacznie pracę. Zamiast pilnować tego mailami i "
            "telefonami, wysyłasz mu jeden link z listą – Monituj przypomina o "
            "brakach, a Ty widzisz, czego jeszcze brakuje w aktach."
        ),
        "pains": [
            "Pracownik obiecuje dosłać dokumenty „w poniedziałek” – i zapomina.",
            "Skany przychodzą na różne skrzynki, część jest nieczytelna.",
            "Przed pierwszym dniem pracy nie wiadomo, czy akta są kompletne.",
        ],
        "benefits": [
            "Jedna lista dokumentów dla każdej nowej osoby – zawsze ten sam proces.",
            "Nieczytelny skan odrzucasz jednym kliknięciem z informacją, co poprawić.",
            "Widzisz komplet akt przed pierwszym dniem pracy, bez szukania w poczcie.",
        ],
        "checklist": [
            "Kwestionariusz osobowy",
            "Świadectwa pracy z poprzednich miejsc",
            "Orzeczenie lekarskie o zdolności do pracy",
            "Zaświadczenie o szkoleniu BHP",
            "Dyplomy i certyfikaty",
            "Numer rachunku bankowego do wynagrodzenia",
            "Oświadczenie do celów podatkowych (PIT-2)",
            "Dane członków rodziny do ZUS",
        ],
        "faq": [
            {
                "q": "Czy mogę wysłać listę dokumentów przed podpisaniem umowy?",
                "a": (
                    "Tak. Prośbę wysyłasz, kiedy chcesz – na przykład zaraz po "
                    "przyjęciu oferty. Ustawiasz termin przed pierwszym dniem "
                    "pracy, a przypomnienia wychodzą same."
                ),
            },
            {
                "q": "Jak chronione są dokumenty pracowników?",
                "a": (
                    "Każda prośba ma unikalny link, który możesz dodatkowo "
                    "zabezpieczyć hasłem. Pliki trafiają do prywatnego magazynu i "
                    "są automatycznie usuwane po okresie, który ustawisz – "
                    "zdążysz przenieść je do akt."
                ),
            },
            {
                "q": "Czy pracownik musi zakładać konto?",
                "a": (
                    "Nie. Otwiera link z maila i przesyła pliki w przeglądarce, "
                    "także z telefonu. Po każdym przesłaniu dostaje potwierdzenie "
                    "z listą tego, co jeszcze zostało."
                ),
            },
        ],
    },
    "kancelarie": {
        "seo_name": "Dokumenty od klientów kancelarii prawnej",
        "seo_description": (
            "Pełnomocnictwa, umowy, dowody – komplet dokumentów do sprawy w "
            "jednym miejscu, z historią wpływu. Monituj przypomina klientom "
            "kancelarii o brakach."
        ),
        "h1": "Komplet dokumentów do sprawy – bez dopytywania klienta",
        "lead": (
            "Do sprawy potrzebujesz kompletu dokumentów, a klient przysyła je na "
            "raty, różnymi kanałami. Monituj zbiera je w jednej prośbie, z "
            "terminem, statusem każdego dokumentu i historią tego, kiedy co "
            "wpłynęło."
        ),
        "pains": [
            "Dokumenty do sprawy przychodzą mailem, komunikatorem i pocztą.",
            "Trudno ustalić, co już jest, a czego wciąż brakuje przed terminem.",
            "Przypominanie klientowi zabiera czas, który powinien iść na sprawę.",
        ],
        "benefits": [
            "Jedna prośba na sprawę z listą, terminem i opcjonalnym hasłem dostępu.",
            "Każdy dokument ma status, a historia pokazuje, kiedy co wpłynęło.",
            "Przypomnienia wysyłają się same – do skutku albo do zamknięcia prośby.",
        ],
        "checklist": [
            "Pełnomocnictwo",
            "Umowy i aneksy",
            "Korespondencja z drugą stroną",
            "Odpis z KRS lub wpis do CEIDG",
            "Dokumenty dowodowe",
            "Faktury i potwierdzenia płatności",
            "Dokument tożsamości (skan)",
        ],
        "faq": [
            {
                "q": "Czy mogę zabezpieczyć prośbę hasłem?",
                "a": (
                    "Tak. Hasło wysyłamy klientowi osobną wiadomością, a bez niego "
                    "link do prośby się nie otworzy."
                ),
            },
            {
                "q": "Skąd wiem, kiedy klient przesłał dokument?",
                "a": (
                    "Każda prośba ma historię zdarzeń: otwarcie linku, przesłanie "
                    "pliku, akceptacja, odrzucenie, przypomnienia – z datą i "
                    "godziną."
                ),
            },
            {
                "q": "Co, jeśli dokument jest niekompletny?",
                "a": (
                    "Odrzucasz go z podaniem powodu. Klient dostaje email z "
                    "informacją, co poprawić, i przesyła nową wersję pod tym "
                    "samym linkiem."
                ),
            },
        ],
    },
    "posrednictwo": {
        "seo_name": "Dokumenty do kredytu i ubezpieczenia",
        "seo_description": (
            "Zaświadczenia, wyciągi i dokumenty nieruchomości do wniosku – w "
            "komplecie i na czas. Monituj sam przypomina klientowi, czego "
            "jeszcze brakuje."
        ),
        "h1": "Wniosek kredytowy rusza, gdy dotrze komplet dokumentów",
        "lead": (
            "Wniosek stoi, bo klient nie przysłał jednego zaświadczenia – a "
            "każdy dzień zwłoki to ryzyko, że transakcja się opóźni. Monituj "
            "wysyła klientowi listę dokumentów do wniosku i przypomina o brakach, "
            "a Ty wiesz, kiedy możesz ruszać."
        ),
        "pains": [
            "Wniosek czeka tygodniami na jedno zaświadczenie o dochodach.",
            "Klient nie wie, które dokumenty już przesłał, a których brakuje.",
            "Każdy telefon z przypomnieniem to czas odebrany innym klientom.",
        ],
        "benefits": [
            "Lista dokumentów do wniosku z terminem i automatycznymi przypomnieniami.",
            "Klient na bieżąco widzi, co już przesłał i czego jeszcze brakuje.",
            "Ty widzisz komplet w panelu i od razu składasz wniosek.",
        ],
        "checklist": [
            "Zaświadczenie o zatrudnieniu i dochodach",
            "Wyciągi z konta za ostatnie 3–6 miesięcy",
            "Umowa przedwstępna lub rezerwacyjna",
            "Odpis księgi wieczystej",
            "Akt notarialny",
            "Dotychczasowa polisa",
            "Dokumenty dochodowe firmy (PIT, KPiR)",
        ],
        "faq": [
            {
                "q": "Czy klient może przesłać dokumenty z telefonu?",
                "a": (
                    "Tak. Link działa w każdej przeglądarce, także na telefonie – "
                    "klient może od razu zrobić zdjęcie dokumentu i je przesłać."
                ),
            },
            {
                "q": "Jak często klient dostaje przypomnienia?",
                "a": (
                    "Tak, jak ustawisz: np. pierwsze po 2 dniach, potem co 3 dni, "
                    "maksymalnie 3 razy. Przypomnienia wyłączają się same, gdy "
                    "dotrze komplet."
                ),
            },
            {
                "q": "Jak długo przechowywane są dokumenty klienta?",
                "a": (
                    "Tyle, ile ustawisz dla prośby – maksymalnie rok. Potem pliki "
                    "są trwale usuwane, a Ty i klient dostajecie powiadomienie."
                ),
            },
        ],
    },
    "b2b": {
        "seo_name": "Dokumenty przy onboardingu klienta B2B",
        "seo_description": (
            "Umowy, dane rejestrowe, pełnomocnictwa – ta sama lista dokumentów "
            "dla każdego nowego klienta, z terminem i automatycznymi "
            "przypomnieniami."
        ),
        "h1": "Onboarding klienta bez blokujących braków w dokumentach",
        "lead": (
            "Rozpoczęcie współpracy blokuje brak jednego dokumentu, a o brakach "
            "dowiadujesz się dopiero przy realizacji. Z Monituj każdy nowy klient "
            "dostaje tę samą listę dokumentów z terminem, a przypomnienia "
            "pilnują reszty."
        ),
        "pains": [
            "Start projektu przesuwa się, bo brakuje podpisanej umowy lub danych.",
            "Każdy handlowiec zbiera dokumenty po swojemu, w swojej skrzynce.",
            "O brakach dowiadujesz się, gdy jest już za późno.",
        ],
        "benefits": [
            "Standardowa lista dokumentów dla każdego nowego klienta.",
            "Ten sam proces w całej firmie, niezależnie od tego, kto prowadzi klienta.",
            "Przypomnienia wychodzą same, a Ty widzisz braki przed startem projektu.",
        ],
        "checklist": [
            "Podpisana umowa i załączniki",
            "Dane rejestrowe firmy (KRS/CEIDG, NIP)",
            "Pełnomocnictwa i reprezentacja",
            "Certyfikaty i uprawnienia",
            "Formularz onboardingowy",
            "Dane do faktur i kontakt do księgowości",
        ],
        "faq": [
            {
                "q": "Czy mogę używać tej samej listy dla każdego klienta?",
                "a": (
                    "Tak. Każdą prośbę tworzysz z tą samą, sprawdzoną listą "
                    "dokumentów – dzięki temu onboarding wygląda tak samo "
                    "niezależnie od tego, kto go prowadzi."
                ),
            },
            {
                "q": "Czy kontrahent musi się rejestrować?",
                "a": (
                    "Nie. Dostaje email z linkiem i przesyła dokumenty w "
                    "przeglądarce. Wszystkie prośby od Twojej firmy ma pod jednym "
                    "stałym linkiem."
                ),
            },
            {
                "q": "Czy widzę, które dokumenty są jeszcze do sprawdzenia?",
                "a": (
                    "Tak. Każdy dokument ma status: brak, dostarczony, "
                    "zaakceptowany albo odrzucony z podanym powodem."
                ),
            },
        ],
    },
}

for _segment in SEGMENTS:
    _segment.update(SEGMENT_PAGES[_segment["slug"]])
