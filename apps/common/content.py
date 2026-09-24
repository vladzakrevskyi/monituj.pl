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
            "przypomnienie, co ile dni je powtarzać, ile razy maksymalnie i o "
            "której godzinie. Monituj wysyła je sam i przestaje, gdy dotrze komplet "
            "dokumentów. W panelu widzisz dokładne daty kolejnych przypomnień."
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
            "Tak – jedną dziennie. Wypełniasz krótki formularz, a link trafia do "
            "odbiorcy. Konto daje panel ze statusami, listę klientów i prośby bez "
            "dziennego limitu."
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
