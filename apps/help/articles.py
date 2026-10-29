"""Centrum pomocy: short answers for people who are not technical.

Every article answers one question the way people ask it, in a few steps
named exactly as the buttons in the panel are. A light markup: **bold**,
[[slug]] / [[slug|text]] - a link to another article (apps/help/templatetags).
Keywords are the words people search with that the text itself may lack."""

from dataclasses import dataclass, field

from apps.billing.plans import BIURO, FREE, PRO, START, TRIAL_DAYS
from apps.documents.images import MAX_PIXELS
from apps.documents.validation import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE
from apps.requests.services import (
    NEW_ACCOUNT_AGE,
    NEW_ACCOUNT_RECIPIENTS,
    OUTBOUND_PER_DAY_NEW_ACCOUNT,
)

_MAX_MB = MAX_UPLOAD_SIZE // (1024 * 1024)
_MAX_MPX = MAX_PIXELS // 1_000_000
_EXTENSIONS = ", ".join(sorted(ext.upper() for ext in ALLOWED_EXTENSIONS))


@dataclass(frozen=True)
class Category:
    slug: str
    title: str
    description: str
    icon: str
    # "recipient": written for the sender's client, not for the panel's user.
    audience: str = "sender"


@dataclass(frozen=True)
class Article:
    slug: str
    category: str
    title: str
    summary: str
    steps: list = field(default_factory=list)
    body: list = field(default_factory=list)
    tips: list = field(default_factory=list)
    # (URL name, button label) - where in the panel to do it.
    panel: tuple = ()
    related: list = field(default_factory=list)
    keywords: str = ""
    # Shown on the help home as a popular question.
    popular: bool = False


CATEGORIES = [
    Category(
        "pierwsze-kroki",
        "Pierwsze kroki",
        "Jak działa Monituj i jak wysłać pierwszą prośbę.",
        "flag",
    ),
    Category(
        "prosby",
        "Prośby o dokumenty",
        "Wysyłanie, szablony, prośby co miesiąc, zmiany.",
        "mail",
    ),
    Category(
        "dokumenty",
        "Dokumenty od klientów",
        "Sprawdzanie, akceptowanie, pobieranie plików.",
        "file",
    ),
    Category(
        "przypomnienia",
        "Przypomnienia",
        "Kiedy wychodzą, jak je zmienić i wyłączyć.",
        "bell",
    ),
    Category(
        "pytania",
        "Pytania do klientów",
        "„Co to za przelew?” - pytanie, odpowiedź, rozmowa.",
        "question",
    ),
    Category(
        "klienci",
        "Klienci",
        "Dodawanie, import z Excela, karta klienta.",
        "user",
    ),
    Category(
        "kalendarz",
        "Kalendarz i „Na dziś”",
        "Terminy, przypomnienia dla siebie, kalendarz w telefonie.",
        "calendar",
    ),
    Category(
        "zespol",
        "Praca w zespole",
        "Zapraszanie współpracowników i ich uprawnienia.",
        "users",
    ),
    Category(
        "konto",
        "Konto i bezpieczeństwo",
        "Hasło, adres e-mail, logowanie, nazwa dla klientów.",
        "lock",
    ),
    Category(
        "plan",
        "Plan i płatności",
        "Limity, okres próbny, faktury, zmiana planu.",
        "card",
    ),
    Category(
        "problemy",
        "Coś nie działa",
        "Klient nie dostał maila, plik się nie przesyła, logowanie.",
        "alert",
    ),
    Category(
        "dla-klientow",
        "Dla Twoich klientów",
        "Dostałeś prośbę o dokumenty? Tu wyjaśniamy, co zrobić.",
        "upload",
        audience="recipient",
    ),
]


ARTICLES = [
    # --- Pierwsze kroki ---------------------------------------------------------
    Article(
        "jak-dziala-monituj",
        "pierwsze-kroki",
        "Jak działa Monituj w minutę",
        "Wysyłasz klientowi listę dokumentów, których potrzebujesz. Klient "
        "przesyła je z linku w mailu, bez zakładania konta, a Monituj sam mu "
        "przypomina, dopóki nie przyśle wszystkiego.",
        steps=[
            "**Ty** tworzysz prośbę: co ma przysłać, kto i do kiedy.",
            "**Klient** dostaje e-mail z linkiem. Otwiera go w przeglądarce - "
            "także w telefonie - i przesyła pliki.",
            "**Monituj** przypomina mu o brakach, aż dotrze komplet. Ty "
            "dostajesz e-mail, gdy coś przyjdzie.",
            "**Ty** sprawdzasz dokumenty i klikasz **Zaakceptuj** albo "
            "**Odrzuć** z powodem - wtedy klient wie, co poprawić.",
        ],
        tips=[
            "Klient niczego nie instaluje i nie zakłada konta.",
            "Zamiast dokumentu możesz też zadać pytanie, np. „Co to za "
            "przelew?” - [[zadaj-pytanie]].",
        ],
        related=["pierwsza-prosba", "co-widzi-klient", "menu-panelu"],
        keywords="co to jest monituj opis zasada działania wprowadzenie start",
        popular=True,
    ),
    Article(
        "zaloz-konto",
        "pierwsze-kroki",
        "Jak założyć konto",
        f"Rejestracja trwa minutę. Przez pierwsze {TRIAL_DAYS} dni masz plan "
        f"{BIURO.name} za darmo, bez podawania karty.",
        steps=[
            "Kliknij **Zacznij za darmo** na stronie głównej.",
            "Wpisz adres e-mail i hasło (dwa razy) i zaznacz zgody. Możesz też "
            "kliknąć **Zarejestruj się przez Google**.",
            "Otwórz e-mail od Monituj i kliknij link - to potwierdza Twój adres. "
            "Od razu jesteś zalogowany.",
            "W panelu zobaczysz **Pierwsze kroki** - przeprowadzą Cię przez "
            "dodanie klienta i pierwszą prośbę.",
        ],
        tips=[
            "Nie ma maila? Zajrzyj do folderu Spam albo Oferty. Na stronie "
            "„Sprawdź swoją skrzynkę” możesz wysłać link jeszcze raz.",
            f"Po okresie próbnym, jeśli nie wybierzesz planu, konto przejdzie "
            f"na bezpłatny {FREE.name}. Nic nie zostanie pobrane, dane zostają.",
        ],
        panel=("accounts:register", "Załóż konto"),
        related=["pierwsza-prosba", "okres-probny", "nie-moge-sie-zalogowac"],
        keywords="rejestracja rejestrować zarejestrować nowe konto zapisać się",
    ),
    Article(
        "pierwsza-prosba",
        "pierwsze-kroki",
        "Jak wysłać prośbę o dokumenty",
        "Wybierasz, czego potrzebujesz, od kogo i na kiedy - i klikasz "
        "**Wyślij prośbę**. Reszta dzieje się sama.",
        steps=[
            "Kliknij **Nowa prośba** (pomarańczowy przycisk w menu po lewej).",
            "Za pierwszym razem wpisz, jak przedstawić Cię klientowi - np. "
            "nazwę biura. Klient zobaczy ją w mailu.",
            "**Czego potrzebujesz?** Najprościej wybierz gotowy szablon, np. "
            "„Dokumenty księgowe za miesiąc” - lista wypełni się sama. Możesz "
            "też wpisywać dokumenty po jednym i naciskać Enter.",
            "**Od kogo?** Zacznij pisać nazwę klienta albo wpisz adres e-mail "
            "nowego - Monituj doda go do klientów.",
            "**Na kiedy?** Wybierz termin: 7 dni, 14 dni, do 10. dnia miesiąca, "
            "konkretną datę albo bez terminu.",
            "Kliknij **Wyślij prośbę**. Klient od razu dostaje e-mail z linkiem.",
        ],
        tips=[
            "Pod przyciskiem widzisz zdanie, co dokładnie wyślemy - sprawdź je "
            "przed kliknięciem.",
            "**Więcej ustawień** to przypomnienia, czas przechowywania plików i "
            "hasło. Domyślne ustawienia są dobre na start.",
            "Po wysłaniu na stronie prośby kliknij **Zobacz, co widzi klient**.",
        ],
        panel=("requests:create", "Nowa prośba"),
        related=["szablony", "prosba-do-wielu", "prosba-co-miesiac", "co-widzi-klient"],
        keywords="jak wysłać prośbę nowa prośba poprosić o dokumenty lista dokumentów "
        "utworzyć stworzyć zamówić faktury wyciągi",
        popular=True,
    ),
    Article(
        "co-widzi-klient",
        "pierwsze-kroki",
        "Co widzi Twój klient",
        "Klient dostaje e-mail z Twoją nazwą i przyciskiem do prośby. Po "
        "kliknięciu widzi listę dokumentów i przy każdym przycisk **Wybierz "
        "plik**. Bez logowania i bez instalowania czegokolwiek.",
        steps=[
            "Otwórz prośbę w panelu i kliknij **Zobacz, co widzi klient**.",
            "Strona otworzy się tak, jak zobaczy ją klient. U góry zobaczysz "
            "pasek „Tak tę stronę widzi Twój klient” - to tylko dla Ciebie.",
        ],
        tips=[
            "Twoje wejście nie liczy się jako otwarcie linku przez klienta.",
            "Jeśli coś tam prześlesz, trafi to do prośby tak, jakby przesłał to "
            "klient - możesz potem to usunąć.",
            "Klientowi możesz wysłać link do naszej pomocy: [[jak-przeslac-dokumenty]]",
        ],
        related=["jak-przeslac-dokumenty", "nazwa-dla-klientow", "pierwsza-prosba"],
        keywords="podgląd klienta strona klienta link odbiorca jak wygląda",
    ),
    Article(
        "menu-panelu",
        "pierwsze-kroki",
        "Co jest w menu panelu",
        "Krótko o każdej zakładce w menu po lewej stronie.",
        body=[
            "**Panel** - co czeka na Ciebie (dokumenty do sprawdzenia, "
            "odpowiedzi klientów, prośby po terminie) i co się ostatnio działo.",
            "**Klienci** - lista osób i firm, od których zbierasz dokumenty. "
            "Kliknij nazwę, a zobaczysz wszystko o kliencie.",
            "**Prośby** - wszystkie wysłane prośby o dokumenty i ich status.",
            "**Zestawienie** - wszyscy klienci i ostatnie miesiące: kto ma "
            "komplet, komu czegoś brakuje.",
            "**Pytania** - pytania do klientów i ich odpowiedzi.",
            "**Kalendarz** - terminy klientów i Twoje własne przypomnienia.",
            "**Szablony** - gotowe listy dokumentów do ponownego użycia.",
            "**Otrzymane** - prośby, które ktoś inny wysłał na Twój adres.",
            "**Powiadomienia** - co i kiedy przesłali Twoi klienci.",
            "**Zespół**, **Plan i płatności**, **Ustawienia** - konto, osoby "
            "i płatności.",
        ],
        tips=[
            "Na telefonie menu otwiera ikona z trzema kreskami w lewym górnym "
            "rogu. Jeśli menu się nie mieści, na dole pojawia się strzałka - "
            "przewiń w dół.",
        ],
        related=["jak-dziala-monituj", "statusy-prosby", "otrzymane"],
        keywords="menu zakładki nawigacja gdzie jest panel boczne",
    ),
    Article(
        "wyprobuj-bez-konta",
        "pierwsze-kroki",
        "Jak wypróbować Monituj bez zakładania konta",
        "Są dwa sposoby: konto demonstracyjne z gotowymi danymi albo jedna "
        "prawdziwa prośba wysłana bez rejestracji.",
        steps=[
            "**Demo**: kliknij **Wypróbuj demo** na stronie głównej. Dostajesz "
            "własne konto z przykładowymi klientami i prośbami. Maile nie są "
            "wysyłane, a konto znika po 24 godzinach.",
            "**Prośba bez konta**: kliknij **Wyślij prośbę bez konta**, wypełnij "
            "krótki formularz i potwierdź go linkiem z maila. Prośba trafi do "
            "odbiorcy, a Ty dostaniesz stały link do panelu z tą prośbą.",
        ],
        tips=[
            "Bez konta wyślesz jedną prośbę dziennie. Gdy ustawisz hasło, ten "
            "limit znika.",
        ],
        panel=("pages:demo", "Wypróbuj demo"),
        related=["zaloz-konto", "jak-dziala-monituj"],
        keywords="demo test próba bez rejestracji gość",
    ),
    # --- Prośby ------------------------------------------------------------------
    Article(
        "szablony",
        "prosby",
        "Szablony, czyli lista bez przepisywania",
        "Szablon to zapisana lista dokumentów z terminem i ustawieniami. "
        "Wybierasz go w nowej prośbie i zostaje tylko wskazać klienta.",
        steps=[
            "Gotowe szablony dla biur rachunkowych, kadr, kancelarii i innych "
            "branż są w zakładce **Szablony** - kliknij **Użyj**.",
            "Własny szablon zapiszesz na trzy sposoby: zaznacz **Zapisz jako "
            "szablon** przy wysyłaniu prośby, kliknij **Zapisz jako szablon** "
            "na stronie wysłanej prośby albo **Nowy szablon** w zakładce "
            "Szablony.",
            "W nowej prośbie wybierz szablon z listy **Zacznij od szablonu**.",
        ],
        tips=[
            "Gotowy szablon możesz **Zapisać jako mój** i dopasować do siebie.",
            f"Liczba własnych szablonów zależy od planu: {FREE.name} "
            f"{FREE.templates}, {START.name} {START.templates}, {BIURO.name} "
            f"{BIURO.templates}, {PRO.name} {PRO.templates}. Gotowe szablony "
            "się nie liczą.",
            "W nazwie możesz wpisać **{miesiąc}** - Monituj wstawi właściwy "
            "miesiąc, np. „Dokumenty za październik 2026”.",
        ],
        panel=("requests:templates", "Szablony"),
        related=["pierwsza-prosba", "prosba-co-miesiac"],
        keywords="szablon wzór lista gotowa zapisać listę powtarzać",
    ),
    Article(
        "prosba-do-wielu",
        "prosby",
        "Jedna prośba do wielu klientów",
        "W polu **Od kogo?** możesz wybrać kilku klientów albo wkleić kilka "
        "adresów e-mail. Każdy dostanie osobną prośbę z własnym linkiem.",
        steps=[
            "W nowej prośbie, w polu **Od kogo?**, wybierz pierwszego klienta.",
            "Zacznij pisać kolejną nazwę i wybierz następnego - albo wklej listę "
            "adresów e-mail oddzielonych przecinkami lub nowymi liniami.",
            "Nowym adresom możesz od razu nadać nazwę (nie trzeba).",
            "Kliknij **Wyślij prośbę**.",
        ],
        tips=[
            "Każdy klient widzi tylko swoje dokumenty.",
            "Każdy klient to osobna prośba w toku, także w limicie planu - "
            "[[plany-i-limity]].",
        ],
        panel=("requests:create", "Nowa prośba"),
        related=["prosba-co-miesiac", "import-klientow"],
        keywords="kilku klientów wielu naraz masowo wszystkim zbiorczo",
    ),
    Article(
        "prosba-co-miesiac",
        "prosby",
        "Jak wysyłać prośbę co miesiąc automatycznie",
        "Prośba cykliczna wychodzi sama, np. 1. dnia każdego miesiąca, do "
        "wybranych klientów - z tą samą listą i nazwą z właściwym miesiącem.",
        steps=[
            "W nowej prośbie zaznacz **Powtarzaj automatycznie**.",
            "Wybierz, jak często: codziennie, co tydzień, co 2 tygodnie albo co "
            "miesiąc - i którego dnia.",
            "Kliknij **Wstaw {miesiąc} do nazwy**, żeby nazwa miała właściwy "
            "miesiąc, np. „Dokumenty za październik 2026”.",
            "Ustaw termin, np. **Do 10. dnia miesiąca**.",
            "Kliknij przycisk zapisu. Jeśli chcesz, zaznacz, żeby pierwsza "
            "wysyłka wyszła od razu.",
        ],
        tips=[
            "Wysyłka wypadająca w weekend albo święto przesuwa się na najbliższy "
            "dzień roboczy (jeśli to zaznaczysz).",
            "Na liście **Prośby** prośba cykliczna ma oznaczenie „Cykliczna”. "
            "Kliknij datę obok, żeby wysłać teraz, wstrzymać albo zmienić "
            "harmonogram.",
            "Jeśli prośba nie zmieści się w limicie planu, nie wyjdzie - "
            "dostaniesz o tym e-mail.",
        ],
        panel=("requests:create", "Nowa prośba"),
        related=["szablony", "prosba-do-wielu", "kalendarz"],
        keywords="cyklicznie co miesiąc automatycznie powtarzać comiesięczna "
        "harmonogram regularnie co tydzień",
        popular=True,
    ),
    Article(
        "bez-pliku",
        "prosby",
        "Gdy klient ma coś zrobić, a nie przesłać plik",
        "Niektóre sprawy nie są plikiem, np. „Nadaj biuru uprawnienia w "
        "KSeF”. Oznacz taką pozycję jako **Bez pliku** - klient kliknie tylko "
        "**Zrobione**.",
        steps=[
            "W nowej prośbie dodaj pozycję do listy dokumentów.",
            "Przy tej pozycji kliknij **Bez pliku**.",
            "Wyślij prośbę. Klient zobaczy przy tej pozycji przycisk "
            "**Zrobione** zamiast przesyłania pliku.",
        ],
        tips=[
            "Monituj przypomina o takiej pozycji tak samo jak o dokumentach.",
            "Potwierdzenie klienta akceptujesz albo odsyłasz z wyjaśnieniem, co "
            "się nie zgadza.",
        ],
        related=["pierwsza-prosba", "sprawdz-dokumenty"],
        keywords="bez pliku zrobione potwierdzenie ksef uprawnienia "
        "pełnomocnictwo czynność",
    ),
    Article(
        "haslo-do-prosby",
        "prosby",
        "Jak zabezpieczyć prośbę hasłem",
        "Link do prośby i tak jest trudny do odgadnięcia. Przy szczególnie "
        "poufnych dokumentach możesz dodać hasło - klient dostanie je w "
        "osobnym mailu.",
        steps=[
            "W nowej prośbie rozwiń **Więcej ustawień**.",
            "Wpisz hasło w polu hasła.",
            "Wyślij prośbę. Klient dostanie dwa maile: z linkiem i z hasłem.",
        ],
        tips=[
            "Hasło można ustawić w prośbie do jednego klienta, która nie "
            "powtarza się automatycznie.",
        ],
        related=["haslo-odbiorcy", "bezpieczenstwo-odbiorcy"],
        keywords="hasło zabezpieczyć poufne ochrona dostęp",
    ),
    Article(
        "czego-nie-prosic",
        "prosby",
        "Dlaczego nie mogę poprosić o PIN, BLIK albo hasło do banku",
        "Takich danych biuro nigdy nie potrzebuje od klienta, a oszuści zawsze "
        "o nie proszą. Dlatego prośby o nie blokujemy, dopóki konto nie ma "
        "opłaconego planu.",
        body=[
            "Zablokowane są prośby o: kod PIN, kod BLIK, kod SMS, kod CVV, "
            "numer karty płatniczej i hasło albo login do banku - w nazwie "
            "prośby, opisie, liście dokumentów i pytaniu.",
            "Zwykłe dokumenty przechodzą bez przeszkód: wyciąg z karty "
            "kredytowej, token KSeF, hasło do programu księgowego.",
            "Potrzebujesz dostępu do konta bankowego klienta? Klient może dać "
            "Ci go w swoim banku jako pełnomocnictwo albo dostęp tylko do "
            "odczytu - bez przekazywania hasła.",
            "Z tego samego powodu nie przejdzie nazwa nadawcy przypominająca "
            "bank, urząd albo Monituj - zobacz [[nazwa-dla-klientow]].",
        ],
        tips=[
            "Uważasz, że to pomyłka? Napisz do nas - sprawdzimy to.",
        ],
        related=["nazwa-dla-klientow", "pierwszy-tydzien", "pierwsza-prosba"],
        keywords="pin blik kod sms cvv numer karty hasło do banku login "
        "zablokowane wyłudzenie nie mogę wysłać prośby oszustwo phishing",
    ),
    Article(
        "zmien-zamknij-usun",
        "prosby",
        "Jak zmienić, zamknąć albo usunąć prośbę",
        "Wszystko robisz na stronie prośby - przyciski są u góry.",
        steps=[
            "**Edytuj** - zmienisz nazwę, opis, termin, przypomnienia i czas "
            "przechowywania plików.",
            "**Zamknij prośbę** - kończysz zbieranie. Przypomnienia przestają "
            "wychodzić, klient nie może już przesyłać plików, a prośba zostaje w "
            "historii. Możesz ją **Otworzyć ponownie**.",
            "**Usuń** - prośba znika razem z plikami i historią, a link u "
            "klienta przestaje działać. Tego nie da się cofnąć.",
        ],
        tips=[
            "Listy dokumentów w wysłanej prośbie nie zmienisz. Jeśli czegoś "
            "brakuje, wyślij nową prośbę albo zadaj pytanie.",
            "Kilka próśb naraz usuniesz, zaznaczając je na liście **Prośby**.",
        ],
        panel=("requests:list", "Prośby"),
        related=["statusy-prosby", "edytuj-usun-klienta"],
        keywords="edycja zmienić termin zamknąć usunąć skasować anulować "
        "otworzyć ponownie",
    ),
    Article(
        "statusy-prosby",
        "prosby",
        "Co oznaczają statusy próśb",
        "Status przy prośbie mówi, na jakim etapie jest zbieranie dokumentów.",
        body=[
            "**Nic nie przesłano** - klient jeszcze niczego nie wysłał.",
            "**W trakcie** - część dokumentów dotarła, części brakuje.",
            "**Kompletny** - wszystko dotarło. Przypomnienia się wyłączyły.",
            "**Po terminie** - termin minął, a czegoś wciąż brakuje.",
            "**Zamknięta** - zakończyłeś zbieranie ręcznie.",
        ],
        tips=[
            "Przy pojedynczych dokumentach statusy to: Brak, Dostarczony, "
            "Zaakceptowany, Odrzucony i Nie dotyczy.",
            "Klienci na liście **Klienci** mają podobne statusy: „Nic nie "
            "przesłał”, „W trakcie”, „Wszystko dostarczone”.",
        ],
        related=["sprawdz-dokumenty", "zmien-zamknij-usun"],
        keywords="status statusy co znaczy w trakcie kompletny po terminie "
        "nic nie przesłano brak",
    ),
    Article(
        "zestawienie",
        "prosby",
        "Zestawienie miesięczne, czyli kto jeszcze nie przysłał",
        "W **Zestawieniu** widzisz wszystkich klientów i ostatnie miesiące: kto "
        "ma komplet, komu ile brakuje, kto jest po terminie. Jednym "
        "przyciskiem przypomnisz wszystkim, którym czegoś brakuje.",
        steps=[
            "Kliknij **Zestawienie** w menu.",
            "Kliknij nazwę miesiąca nad tabelą - u góry zobaczysz jego "
            "podsumowanie, np. „34 z 52 klientów ma komplet”.",
            "Kliknij kolorowe pole przy kliencie, żeby otworzyć jego prośbę.",
            "Kliknij **Przypomnij wszystkim, którym czegoś brakuje** - każdy taki "
            "klient dostanie przypomnienie e-mailem.",
        ],
        body=[
            "**Komplet** (zielone) - wszystko dotarło.",
            "**Brakuje 2** (żółte) - część dotarła, części brakuje.",
            "**Nic nie przysłał** albo **po terminie** (czerwone) - tu warto "
            "zadzwonić.",
            "**Zamknięta** (szare) - zakończyłeś zbieranie ręcznie.",
        ],
        tips=[
            "Miesiąc to miesiąc wysłania prośby - prośba „Dokumenty za "
            "wrzesień” wysłana 1 października jest w kolumnie października.",
            "Zaznacz **Tylko klienci, którym czegoś brakuje**, żeby zostawić na "
            "liście tylko tych, na których czekasz.",
            "Klient, któremu przypomnienie wyszło w ciągu ostatniej godziny, "
            "zostanie pominięty.",
        ],
        panel=("requests:overview", "Zestawienie"),
        related=["statusy-prosby", "przypomnij-teraz", "prosba-co-miesiac"],
        keywords="zestawienie zamknięcie miesiąca kto nie przysłał tabela "
        "podsumowanie przypomnij wszystkim braki miesiąc",
        popular=True,
    ),
    Article(
        "otrzymane",
        "prosby",
        "Prośby wysłane do Ciebie (zakładka Otrzymane)",
        "Jeśli ktoś inny (np. Twoja księgowa) wyśle prośbę albo pytanie na "
        "Twój adres e-mail, zobaczysz je w zakładce **Otrzymane**.",
        steps=[
            "Kliknij **Otrzymane** w menu.",
            "Otwórz prośbę i prześlij pliki albo odpowiedz na pytanie - tak samo "
            "jak z linku w mailu.",
        ],
        tips=[
            "Są tu także prośby wysłane, zanim założyłeś konto.",
        ],
        panel=("requests:received", "Otrzymane"),
        related=["jak-przeslac-dokumenty"],
        keywords="otrzymane prośby do mnie ktoś poprosił mnie",
    ),
    # --- Dokumenty -----------------------------------------------------------
    Article(
        "sprawdz-dokumenty",
        "dokumenty",
        "Jak sprawdzić i zaakceptować dokumenty",
        "Gdy klient coś prześle, dostaniesz e-mail, a w **Panelu** pojawi się "
        "to w „Do zrobienia”. Sprawdzasz plik i klikasz **Zaakceptuj**.",
        steps=[
            "Otwórz prośbę - z maila, z **Panelu** albo z listy **Prośby**.",
            "W **Liście dokumentów** kliknij nazwę pliku, żeby go pobrać i obejrzeć.",
            "Wszystko w porządku? Kliknij **Zaakceptuj**.",
            "Jest kilka dokumentów do sprawdzenia? Kliknij **Zaakceptuj "
            "wszystkie** nad listą.",
        ],
        tips=[
            "Dokument jest zły? Zobacz [[odrzuc-dokument]].",
            "Gdy wszystkie dokumenty dotrą, przypomnienia wyłączają się same, "
            "a klient dostaje potwierdzenie.",
        ],
        panel=("accounts:panel", "Panel"),
        related=["odrzuc-dokument", "pobierz-pliki", "powiadomienia"],
        keywords="akceptować zaakceptować sprawdzić przejrzeć dokumenty "
        "zatwierdzić odebrać",
        popular=True,
    ),
    Article(
        "odrzuc-dokument",
        "dokumenty",
        "Jak poprosić klienta o poprawiony dokument",
        "Kliknij **Odrzuć** przy dokumencie i napisz, co jest nie tak. Klient "
        "dostanie e-mail z Twoim wyjaśnieniem i prześle nową wersję.",
        steps=[
            "Otwórz prośbę i znajdź dokument na **Liście dokumentów**.",
            "Kliknij **Odrzuć**.",
            "Wpisz powód, np. „Zdjęcie jest nieostre, proszę o skan”.",
            "Kliknij **Odrzuć dokument**. Przypomnienia o tym dokumencie "
            "znowu będą wychodzić.",
        ],
        tips=[
            "Pisz konkretnie - klient zobaczy dokładnie Twój tekst.",
        ],
        related=["sprawdz-dokumenty", "nie-mam-dokumentu"],
        keywords="odrzucić odrzucenie poprawka zły dokument nieczytelny "
        "nieostry błędny ponownie",
    ),
    Article(
        "nie-mam-dokumentu",
        "dokumenty",
        "Klient nie ma dokumentu",
        "Klient może zaznaczyć, że dokumentu nie ma - np. w tym miesiącu nie "
        "było kosztów. Przypomnienia o nim ustają, a Ty decydujesz, czy to "
        "w porządku.",
        steps=[
            "Dostaniesz powiadomienie, że klient nie ma dokumentu, razem z powodem.",
            "Na stronie prośby przy tym dokumencie kliknij **Zaakceptuj**, "
            "jeśli to w porządku.",
            "Jeśli jednak go potrzebujesz, kliknij **Jednak potrzebuję** i "
            "wyjaśnij dlaczego - klient dostanie e-mail.",
        ],
        tips=[
            "Sam też możesz oznaczyć dokument jako zbędny przyciskiem **Nie "
            "dotyczy** - Monituj przestanie o niego przypominać.",
            "W prośbie cyklicznej dotyczy to tylko danego miesiąca.",
        ],
        related=["sprawdz-dokumenty", "nie-mam"],
        keywords="nie mam dokumentu nie dotyczy brak kosztów nie było",
    ),
    Article(
        "pobierz-pliki",
        "dokumenty",
        "Jak pobrać pliki, także wszystkie naraz",
        "Pojedynczy plik pobierzesz, klikając jego nazwę. Wszystkie pliki "
        "prośby - przyciskiem **Pobierz wszystko (ZIP)**.",
        steps=[
            "Otwórz prośbę.",
            "Kliknij **Pobierz wszystko (ZIP)** u góry strony.",
            "W archiwum każdy dokument z listy ma swój folder.",
        ],
        tips=[
            "Zdjęcia z iPhone'a (HEIC) zapisujemy jako JPG, żeby otwierały się "
            "wszędzie.",
            "Pobierz pliki, zanim minie czas przechowywania - potem są "
            "usuwane. Zobacz [[przechowywanie]].",
        ],
        related=["przechowywanie", "sprawdz-dokumenty"],
        keywords="pobrać ściągnąć zip archiwum wszystkie pliki zapisać na dysk "
        "gdzie są pliki",
    ),
    Article(
        "przechowywanie",
        "dokumenty",
        "Jak długo przechowujemy pliki",
        "Tyle, ile ustawisz dla prośby: 30, 90 lub 180 dni, rok albo własny "
        "okres (najwyżej 365 dni) od przesłania pliku. Potem plik jest trwale "
        "usuwany.",
        steps=[
            "Czas ustawiasz w nowej prośbie w **Więcej ustawień** - domyślnie 90 dni.",
            "W wysłanej prośbie zmienisz go przez **Edytuj**.",
        ],
        tips=[
            "Przed usunięciem plików Ty i klient dostajecie wiadomość.",
            "Monituj nie jest archiwum - pobrane pliki zapisz u siebie.",
        ],
        related=["pobierz-pliki", "bezpieczenstwo-odbiorcy"],
        keywords="przechowywanie usuwanie plików ile dni retencja archiwum rodo",
    ),
    Article(
        "powiadomienia",
        "dokumenty",
        "Skąd wiem, że klient coś przesłał",
        "Dostajesz e-mail kilka minut po tym, jak klient prześle pliki - "
        "jeden zbiorczy, a nie osobny przy każdym pliku.",
        body=[
            "W **Panelu** przesłane dokumenty pojawiają się w „Do zrobienia”.",
            "Zakładka **Powiadomienia** pokazuje wszystko, co przesłali "
            "klienci, od najnowszych - liczba przy niej to nowe pozycje.",
            "Jeśli klient zaznaczy „Nie mam tego dokumentu” albo odpowie na "
            "pytanie, też się o tym dowiesz.",
        ],
        tips=[
            "Nie dostajesz maili? Zobacz [[nie-dostaje-maili]].",
        ],
        panel=("notifications:list", "Powiadomienia"),
        related=["sprawdz-dokumenty", "mail-na-dzis"],
        keywords="powiadomienie email informacja przesłał nowy dokument skąd wiem",
    ),
    # --- Przypomnienia -------------------------------------------------------
    Article(
        "jak-dzialaja-przypomnienia",
        "przypomnienia",
        "Jak działają przypomnienia",
        "Monituj sam wysyła klientowi przypomnienia o brakujących "
        "dokumentach, dopóki nie przyśle wszystkiego. Nie musisz o tym "
        "pamiętać.",
        body=[
            "Standardowo pierwsze przypomnienie wychodzi po 2 dniach, kolejne co "
            "3 dni, najwyżej 3 razy.",
            "Jeśli prośba ma termin, Monituj przypomni też 2 dni przed terminem "
            "i w dniu terminu - chyba że dzień wcześniej wyszło już inne "
            "przypomnienie.",
            "Przypomnienia wychodzą o tej godzinie, o której wysłałeś prośbę, "
            "według zegara klienta, w godzinach 8:00-20:00.",
            "Przestają, gdy dotrze komplet, gdy klient zaznaczy, że dokumentu "
            "nie ma, albo gdy zamkniesz prośbę.",
        ],
        tips=[
            "Na stronie prośby, w karcie **Przypomnienia**, widzisz dokładne "
            "daty kolejnych przypomnień.",
        ],
        related=["ustawienia-przypomnien", "przypomnij-teraz"],
        keywords="przypomnienia monity kiedy jak często automatyczne",
        popular=True,
    ),
    Article(
        "ustawienia-przypomnien",
        "przypomnienia",
        "Jak zmienić albo wyłączyć przypomnienia",
        "Przy każdej prośbie wybierasz, jak często przypominać - albo "
        "wyłączasz przypomnienia.",
        steps=[
            "W nowej prośbie rozwiń **Więcej ustawień** (w wysłanej kliknij "
            "**Edytuj**).",
            "Wybierz: **Łagodne** (pierwsze po 3 dniach, potem co 5, najwyżej "
            "2 razy), **Standardowe** (po 2 dniach, co 3, najwyżej 3 razy), "
            "**Częste** (po dniu, co 2, najwyżej 5 razy), **Własne** albo **Bez "
            "przypomnień**.",
            "Zapisz.",
        ],
        tips=[
            "Te same ustawienia możesz zapisać w szablonie.",
        ],
        related=["jak-dzialaja-przypomnienia", "szablony"],
        keywords="wyłączyć przypomnienia zmienić częstotliwość rzadziej "
        "częściej ustawienia",
    ),
    Article(
        "przypomnij-teraz",
        "przypomnienia",
        "Jak przypomnieć klientowi od razu",
        "Na stronie prośby kliknij **Wyślij przypomnienie teraz**. Klient "
        "dostanie e-mail z listą tego, czego brakuje.",
        steps=[
            "Otwórz prośbę.",
            "W karcie **Przypomnienia** kliknij **Wyślij przypomnienie teraz**.",
        ],
        tips=[
            "Ręczne przypomnienie wyślesz raz na godzinę dla jednej prośby.",
            "Link możesz też wysłać jeszcze raz - kartą **Link dla klienta** - "
            "np. na inny adres.",
        ],
        related=["jak-dzialaja-przypomnienia", "klient-nie-dostal-maila"],
        keywords="ręcznie przypomnieć teraz ponaglić monit",
    ),
    # --- Pytania -------------------------------------------------------------
    Article(
        "zadaj-pytanie",
        "pytania",
        "Jak zadać klientowi pytanie",
        "Gdy coś się nie zgadza - np. „Co to za przelew 1 250 zł z 12.09?” - "
        "zapytaj w Monituj zamiast w mailu. Klient odpowie z linku, a Monituj "
        "przypomni mu, dopóki nie odpowie.",
        steps=[
            "Kliknij **Pytania** w menu, a potem **Zadaj pytanie**.",
            "Wybierz klienta.",
            "Wpisz pytanie - konkretnie: kwota, data, kontrahent.",
            "W **Notatce dla siebie** zapisz, po co pytasz, np. „Do VAT za "
            "wrzesień”. Klient jej nie widzi.",
            "Wybierz, do kiedy potrzebujesz odpowiedzi, i kliknij **Wyślij pytanie**.",
        ],
        tips=[
            "Klient może odpowiedzieć tekstem i dołączyć plik, np. zdjęcie faktury.",
            f"Pytania nie zajmują miejsc próśb - mają osobny limit "
            f"({FREE.name} {FREE.open_questions}, {START.name} "
            f"{START.open_questions}, {BIURO.name} {BIURO.open_questions}, "
            f"{PRO.name} {PRO.open_questions} pytań czekających na odpowiedź).",
        ],
        panel=("requests:question-create", "Zadaj pytanie"),
        related=["odpowiedz-przyszla", "karta-klienta"],
        keywords="pytanie zapytać wyjaśnić przelew operacja niejasna",
        popular=True,
    ),
    Article(
        "odpowiedz-przyszla",
        "pytania",
        "Co zrobić, gdy klient odpowie na pytanie",
        "Dostaniesz e-mail z odpowiedzią i Twoją notatką. Jeśli odpowiedź "
        "wystarcza, kliknij **Wyjaśnione**. Jeśli nie - dopytaj w tej samej "
        "rozmowie.",
        steps=[
            "Otwórz pytanie - z maila, z **Panelu** albo z zakładki **Pytania** "
            "(liczba przy niej to odpowiedzi do sprawdzenia).",
            "Przeczytaj rozmowę - wszystkie pytania i odpowiedzi są po kolei, "
            "jak w czacie.",
            "Wystarczy? Kliknij **Wyjaśnione** - sprawa jest zamknięta.",
            "Potrzebujesz więcej? Wpisz pytanie uzupełniające i kliknij **Wyślij "
            "klientowi**. Przypomnienia wrócą, dopóki nie odpowie.",
        ],
        tips=[
            "Nic się nie nadpisuje - poprzednie odpowiedzi zostają.",
        ],
        panel=("requests:questions", "Pytania"),
        related=["zadaj-pytanie"],
        keywords="odpowiedź wyjaśnione dopytać rozmowa czat zamknąć pytanie",
    ),
    # --- Klienci -------------------------------------------------------------
    Article(
        "dodaj-klienta",
        "klienci",
        "Jak dodać klienta",
        "Wystarczy nazwa i adres e-mail. Klienta możesz też dodać od razu w "
        "nowej prośbie - wpisując jego adres.",
        steps=[
            "Kliknij **Klienci** w menu, a potem **Dodaj klienta**.",
            "Wpisz nazwę (np. „Piekarnia Kowalski”) i adres e-mail.",
            "Jeśli chcesz, dodaj telefon, NIP i notatkę.",
            "Zapisz.",
        ],
        tips=[
            "Masz wielu klientów? [[import-klientow|Zaimportuj ich z Excela]].",
        ],
        panel=("clients:create", "Dodaj klienta"),
        related=["import-klientow", "karta-klienta"],
        keywords="nowy klient dodać kontrahent odbiorca firma osoba",
    ),
    Article(
        "import-klientow",
        "klienci",
        "Jak zaimportować klientów z Excela",
        "Wczytaj plik CSV albo Excel (XLSX) - np. eksport kontrahentów z "
        "programu księgowego. Przed zapisem zobaczysz, kto zostanie dodany.",
        steps=[
            "Kliknij **Klienci**, a potem **Importuj z pliku**.",
            "Wybierz plik. Kolumny z nazwą, e-mailem, telefonem, NIP-em i "
            "uwagami rozpoznamy same.",
            "Sprawdź podgląd i zatwierdź import.",
        ],
        tips=[
            "Klientów, których już masz, nie zdublujemy.",
            "Import jest w każdym planie.",
        ],
        panel=("clients:import", "Importuj z pliku"),
        related=["dodaj-klienta", "prosba-do-wielu"],
        keywords="import excel csv xlsx plik lista kontrahentów program "
        "księgowy wczytać wielu",
    ),
    Article(
        "karta-klienta",
        "klienci",
        "Karta klienta, czyli wszystko o kliencie",
        "Kliknij nazwę klienta na liście **Klienci**. Zobaczysz otwarte "
        "sprawy, notatki zespołu i całą historię.",
        body=[
            "**Otwarte sprawy** - pytania bez odpowiedzi (i od jak dawna czekają), "
            "odpowiedzi do sprawdzenia i brakujące dokumenty.",
            "**Notatki** - np. „dzwoniła w sprawie leasingu”. Widzi je Twój "
            "zespół, klient nigdy.",
            "**Przypomnij mi** - przypomnienie dla siebie, które pojawi się w "
            "kalendarzu.",
            "**Historia** - prośby, pytania, przesłane dokumenty i "
            "przypomnienia, od najnowszych.",
        ],
        tips=[
            "Z karty od razu wyślesz klientowi nową prośbę albo zadasz pytanie.",
        ],
        panel=("clients:list", "Klienci"),
        related=["dodaj-klienta", "kalendarz", "zadaj-pytanie"],
        keywords="karta klienta historia notatki szczegóły klienta",
    ),
    Article(
        "edytuj-usun-klienta",
        "klienci",
        "Jak zmienić dane klienta albo go usunąć",
        "Dane zmienisz na karcie klienta. Usunięcie klienta kasuje też "
        "wszystkie jego prośby, pliki i historię.",
        steps=[
            "Otwórz kartę klienta i kliknij **Edytuj**, żeby zmienić nazwę albo "
            "adres e-mail.",
            "Żeby usunąć klienta, skorzystaj z akcji na liście **Klienci**.",
        ],
        tips=[
            "Usuniętych danych nie da się przywrócić. Tak spełnisz prośbę "
            "klienta o usunięcie jego danych (RODO).",
            "W zespole usuwać klientów może tylko właściciel konta.",
        ],
        panel=("clients:list", "Klienci"),
        related=["karta-klienta", "zmien-zamknij-usun"],
        keywords="zmienić email klienta usunąć klienta edytować rodo dane",
    ),
    # --- Kalendarz -----------------------------------------------------------
    Article(
        "kalendarz",
        "kalendarz",
        "Kalendarz i przypomnienia dla siebie",
        "W **Kalendarzu** widzisz terminy klientów, terminy odpowiedzi na "
        "pytania, dni wysyłki próśb cyklicznych i własne przypomnienia.",
        steps=[
            "Kliknij **Kalendarz** w menu.",
            "Żeby dodać przypomnienie dla siebie, wpisz w **Przypomnij mi**, "
            "co masz zrobić, wybierz dzień i (jeśli chcesz) klienta.",
            "Kliknij **Dodaj przypomnienie**. Gdy zrobisz, odhacz je.",
        ],
        tips=[
            "Kalendarz pokazuje Twoje sprawy z klientami. Terminów ustawowych "
            "(ZUS, VAT, JPK) nie pokazuje.",
        ],
        panel=("agenda:calendar", "Kalendarz"),
        related=["kalendarz-w-telefonie", "mail-na-dzis"],
        keywords="kalendarz terminy przypomnij mi zadanie notatka termin",
    ),
    Article(
        "kalendarz-w-telefonie",
        "kalendarz",
        "Kalendarz w telefonie, Google albo Outlooku",
        "Kalendarz Monituj możesz mieć w swoim kalendarzu - terminy pojawią "
        "się tam same.",
        steps=[
            "W **Kalendarzu** kliknij **Pokaż link do kalendarza** i skopiuj go.",
            "**Google**: w Kalendarzu Google przy „Inne kalendarze” kliknij "
            "plus, wybierz **Z adresu URL** i wklej link.",
            "**iPhone**: otwórz link w telefonie i potwierdź subskrypcję.",
            "**Outlook**: dodaj kalendarz z internetu (subskrypcja z sieci Web) "
            "i wklej link.",
        ],
        tips=[
            "Link jest tajny - nie wysyłaj go nikomu.",
            "Google odświeża takie kalendarze co kilka godzin, więc nowe terminy "
            "mogą pojawić się z opóźnieniem.",
        ],
        panel=("agenda:calendar", "Kalendarz"),
        related=["kalendarz", "mail-na-dzis"],
        keywords="google calendar iphone outlook telefon subskrypcja ics "
        "synchronizacja",
    ),
    Article(
        "mail-na-dzis",
        "kalendarz",
        "Poranny e-mail „Na dziś”",
        "W dni robocze o 7:30 dostajesz krótki e-mail: Twoje przypomnienia, "
        "terminy na dziś i jutro, prośby po terminie, długo czekające pytania "
        "i to, co dotarło od wczoraj.",
        body=[
            "Jeśli nic nie czeka, maila nie ma.",
            "Wyłączysz go w **Kalendarzu**, w karcie „Poranny e-mail „Na dziś””.",
        ],
        panel=("agenda:calendar", "Kalendarz"),
        related=["kalendarz", "powiadomienia"],
        keywords="na dziś poranny mail codzienny podsumowanie wyłączyć 7:30",
    ),
    # --- Zespół --------------------------------------------------------------
    Article(
        "zapros-do-zespolu",
        "zespol",
        "Jak zaprosić współpracownika",
        "Współpracownik dostaje e-mail z zaproszeniem, ustawia własne hasło "
        "i pracuje na tych samych klientach i prośbach co Ty.",
        steps=[
            "Kliknij **Zespół** w menu.",
            "Wpisz adres e-mail tej osoby i kliknij **Wyślij zaproszenie**.",
            "Link w zaproszeniu jest ważny 7 dni.",
        ],
        tips=[
            f"Plan {START.name} to {START.seats} osoby, {BIURO.name} - "
            f"{BIURO.seats}, {PRO.name} - {PRO.seats} (razem z Tobą). W okresie "
            f"próbnym zaprosisz do {BIURO.seats} osób.",
            "W historii prośby widać, kto co zrobił.",
        ],
        panel=("accounts:team", "Zespół"),
        related=["uprawnienia-zespolu", "przelaczanie-kont"],
        keywords="zespół współpracownik pracownik zaprosić dodać osobę "
        "użytkownika konto dla pracownika",
    ),
    Article(
        "uprawnienia-zespolu",
        "zespol",
        "Co może osoba z zespołu",
        "Pracuje na tych samych klientach, prośbach, szablonach i dokumentach "
        "co Ty. Planem, płatnościami i zespołem zarządza tylko właściciel.",
        body=[
            "Osoba z zespołu ma własne hasło, może włączyć weryfikację "
            "dwuetapową i logować się przez Google.",
            "Nie widzi planu i płatności, nie zmienia zespołu i nie może usunąć konta.",
            "Usuwa pojedyncze prośby, ale nie może usuwać wielu naraz ani "
            "klientów z całą historią.",
            "Jeśli usuniesz kogoś z zespołu, wszystko, co zrobił, zostaje u Ciebie.",
        ],
        panel=("accounts:team", "Zespół"),
        related=["zapros-do-zespolu", "przelaczanie-kont"],
        keywords="uprawnienia rola dostęp co może właściciel pracownik",
    ),
    Article(
        "przelaczanie-kont",
        "zespol",
        "Jak przełączać się między zespołami",
        "Jedna osoba może mieć własne konto i należeć do kilku zespołów. "
        "Przełączasz się w menu, a dane są zawsze oddzielone.",
        steps=[
            "Kliknij nazwę konta na górze menu po lewej.",
            "Wybierz konto albo zespół, w którym chcesz pracować.",
        ],
        related=["zapros-do-zespolu", "uprawnienia-zespolu"],
        keywords="przełączyć konto zespół inne biuro kilka kont",
    ),
    # --- Konto ---------------------------------------------------------------
    Article(
        "nazwa-dla-klientow",
        "konto",
        "Jak klient rozpozna, że prośba jest od Ciebie",
        "Klient widzi w mailu i na stronie Twoją nazwę i adres e-mail. Nazwę "
        "ustawisz w **Ustawieniach**.",
        steps=[
            "Kliknij **Ustawienia** w menu.",
            "W **Danych konta** wpisz **Nazwę widoczną dla klientów**, np. "
            "„Biuro Rachunkowe Kowalska”.",
            "Masz płatny plan na fakturę firmową? Zaznacz **Pokazuj odbiorcom "
            "nazwę firmy i NIP** - pobieramy je z rejestru, więc nie da się "
            "ich podrobić.",
            "Zapisz.",
        ],
        tips=[
            "Nazwy przypominające bank, urząd albo Monituj nie przejdą - także "
            "zapisane z cyframi czy myślnikami. Tak chronimy Twoich klientów "
            "przed oszustami. Zobacz [[czego-nie-prosic]].",
        ],
        panel=("accounts:settings", "Ustawienia"),
        related=["logo", "co-widzi-klient", "klient-nie-dostal-maila"],
        keywords="nazwa firmy nadawca od kogo nip podpis jak się przedstawić",
    ),
    Article(
        "logo",
        "konto",
        "Jak dodać logo, które zobaczą klienci",
        "Twoje logo pojawi się na stronie prośby i w mailach do klientów - od "
        "razu widzą, od kogo jest prośba. Pokazujemy je w płatnych planach i w "
        "okresie próbnym.",
        steps=[
            "Kliknij **Ustawienia** w menu.",
            "W karcie **Logo dla klientów** wybierz plik z logo (PNG, JPG albo "
            "WebP, do 3 MB).",
            "Kliknij **Zapisz logo**. Podgląd pokaże, jak zobaczą je klienci.",
        ],
        tips=[
            "Najlepiej wygląda logo poziome, na przezroczystym tle. Puste brzegi "
            "przytniemy sami.",
            "W planie Free logo zostaje zapisane, ale klienci go nie widzą - "
            "wróci, gdy wybierzesz płatny plan.",
            "Logo usuniesz przyciskiem **Usuń logo**.",
        ],
        panel=("accounts:settings", "Ustawienia"),
        related=["nazwa-dla-klientow", "co-widzi-klient"],
        keywords="logo logotyp znak firmy branding wygląd maili strona klienta",
    ),
    Article(
        "zmien-haslo-email",
        "konto",
        "Jak zmienić hasło albo adres e-mail",
        "Oba zmienisz w **Ustawieniach**. Dla bezpieczeństwa zmianę "
        "potwierdzasz linkiem z maila.",
        steps=[
            "Kliknij **Ustawienia**.",
            "**Hasło**: wpisz obecne i nowe hasło, a potem kliknij link w "
            "mailu. Zostaniesz wylogowany ze wszystkich urządzeń - zaloguj się "
            "nowym hasłem.",
            "**Adres e-mail**: wpisz nowy adres i obecne hasło, a potem kliknij "
            "link wysłany na nowy adres.",
        ],
        tips=[
            "Nie pamiętasz hasła? Na stronie logowania kliknij **Nie pamiętasz "
            "hasła?**.",
        ],
        panel=("accounts:settings", "Ustawienia"),
        related=["nie-moge-sie-zalogowac", "weryfikacja-dwuetapowa"],
        keywords="zmiana hasła zmienić email adres login nowe hasło",
    ),
    Article(
        "logowanie-google",
        "konto",
        "Logowanie przez Google",
        "Możesz logować się kontem Google zamiast hasła - przy rejestracji "
        "albo później, łącząc konta w **Ustawieniach**.",
        steps=[
            "Na stronie logowania kliknij **Zaloguj się przez Google**.",
            "Masz już konto z hasłem? W **Ustawieniach**, w sekcji **Logowanie "
            "przez Google**, połącz konta.",
        ],
        panel=("accounts:settings", "Ustawienia"),
        related=["zmien-haslo-email", "weryfikacja-dwuetapowa"],
        keywords="google gmail logowanie bez hasła sso",
    ),
    Article(
        "weryfikacja-dwuetapowa",
        "konto",
        "Jak włączyć weryfikację dwuetapową",
        "Przy logowaniu oprócz hasła podajesz kod - z aplikacji w telefonie "
        "albo z maila. Samo hasło nie wystarczy wtedy, żeby ktoś wszedł na "
        "Twoje konto.",
        steps=[
            "W **Ustawieniach** znajdź **Weryfikację dwuetapową** i włącz ją.",
            "Wybierz sposób: **aplikacja** (np. Google Authenticator) albo "
            "**kod e-mailem**.",
            "Aplikacja: zeskanuj kod QR telefonem i wpisz 6 cyfr. E-mail: wpisz "
            "kod, który przyszedł na Twój adres.",
            "Przy aplikacji zapisz **kody zapasowe** w bezpiecznym miejscu - "
            "przydadzą się, gdy zgubisz telefon.",
        ],
        tips=[
            "Przy logowaniu możesz zaznaczyć **Zapamiętaj to urządzenie na 30 dni**.",
        ],
        panel=("accounts:two-factor", "Weryfikacja dwuetapowa"),
        related=["nie-moge-sie-zalogowac", "zmien-haslo-email"],
        keywords="2fa weryfikacja dwuetapowa kod sms authenticator "
        "bezpieczeństwo kody zapasowe",
    ),
    Article(
        "usun-konto",
        "konto",
        "Jak usunąć konto",
        "W **Ustawieniach**, w sekcji **Usunięcie konta**. Usuwamy konto, "
        "klientów, prośby i wszystkie pliki od razu.",
        steps=[
            "Najpierw pobierz pliki, których potrzebujesz - [[pobierz-pliki]].",
            "W **Ustawieniach** przewiń do **Usunięcia konta** i podaj hasło.",
            "Kliknij link w mailu, który wyślemy - dopiero wtedy konto znika.",
        ],
        tips=[
            "Odbiorcy otwartych próśb dostaną informację, że prośba jest nieaktualna.",
            "Tego nie da się cofnąć.",
        ],
        panel=("accounts:settings", "Ustawienia"),
        related=["zmien-anuluj-plan", "pobierz-pliki"],
        keywords="usunąć konto skasować rezygnacja zamknąć konto rodo",
    ),
    # --- Plan ----------------------------------------------------------------
    Article(
        "plany-i-limity",
        "plan",
        "Plany i limity, czyli co to jest prośba w toku",
        "Płacisz za liczbę próśb w toku, czyli takich, na które wciąż czekasz. "
        "Zakończone i zamknięte się nie liczą.",
        body=[
            f"**{FREE.name}** - 0 zł, do {FREE.active_requests} próśb w toku.",
            f"**{START.name}** - {START.monthly // 100} zł netto miesięcznie, "
            f"do {START.active_requests} próśb.",
            f"**{BIURO.name}** - {BIURO.monthly // 100} zł netto miesięcznie, "
            f"do {BIURO.active_requests} próśb.",
            f"**{PRO.name}** - {PRO.monthly // 100} zł netto miesięcznie, do "
            f"{PRO.active_requests} próśb.",
            "Przy płatności rocznej 2 miesiące są gratis. Przypomnienia, "
            "klienci, gotowe szablony i import są w każdym planie.",
        ],
        tips=[
            "Prośba do kilku klientów to kilka próśb - po jednej na klienta.",
            "Pytania do klientów mają osobny limit i nie zajmują miejsc próśb.",
            "Ile miejsc zostało, widzisz na dole menu po lewej.",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["limit-planu", "zaplac-faktura", "okres-probny"],
        keywords="cena cennik ile kosztuje plan limit prośby w toku free start "
        "biuro pro abonament",
    ),
    Article(
        "okres-probny",
        "plan",
        "Okres próbny",
        f"Nowe konto ma {TRIAL_DAYS} dni płatnego planu za darmo (domyślnie "
        f"{BIURO.name}), bez podawania karty.",
        body=[
            "Ile dni zostało, widzisz w **Planie i płatnościach**.",
            f"Jeśli po okresie próbnym nie wybierzesz planu, konto przejdzie na "
            f"bezpłatny {FREE.name}. Nic nie zostanie pobrane, a dane zostają.",
            "Przed końcem okresu próbnego wyślemy Ci przypomnienie.",
            "W pierwszym tygodniu, zanim wybierzesz płatny plan, obowiązują "
            "mniejsze limity wysyłki. Zobacz [[pierwszy-tydzien]].",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["plany-i-limity", "pierwszy-tydzien", "zaplac-faktura"],
        keywords="okres próbny trial za darmo 30 dni test darmowy",
    ),
    Article(
        "pierwszy-tydzien",
        "plan",
        "Limity w pierwszym tygodniu",
        f"Przez pierwsze {NEW_ACCOUNT_AGE.days} dni, dopóki nie opłacisz "
        f"planu, wyślesz do {OUTBOUND_PER_DAY_NEW_ACCOUNT} wiadomości dziennie "
        f"i prośby do {NEW_ACCOUNT_RECIPIENTS} różnych osób. Po opłaceniu "
        "planu te limity od razu znikają.",
        body=[
            "Wiadomości to zaproszenia do prośby, linki wysłane ręcznie i "
            "przypomnienia wysłane przyciskiem. Automatyczne przypomnienia "
            "do klientów, którym już wysłałeś prośbę, wychodzą normalnie.",
            f"Do tych samych {NEW_ACCOUNT_RECIPIENTS} osób możesz wysyłać "
            "kolejne prośby bez ograniczeń - liczą się tylko nowe adresy.",
            "Dlaczego? Oszuści zakładają darmowe konta, żeby rozsyłać "
            "fałszywe prośby. Te limity ich zatrzymują, a biuru na start "
            "zwykle wystarczają.",
            f"Po {NEW_ACCOUNT_AGE.days} dniach limity same rosną. Jeśli "
            "potrzebujesz więcej od razu, opłać plan albo napisz do nas.",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["okres-probny", "limit-planu", "prosba-do-wielu"],
        keywords="limit maili wiadomości dziennie odbiorców nowe konto "
        "pierwszy tydzień nie mogę wysłać zablokowane 20 okres próbny",
    ),
    Article(
        "zaplac-faktura",
        "plan",
        "Jak zapłacić i gdzie są faktury",
        "Płacisz kartą z góry za miesiąc albo rok. Fakturę VAT dostajesz "
        "mailem po każdej płatności, a wszystkie znajdziesz w **Planie i "
        "płatnościach**.",
        steps=[
            "Kliknij **Plan i płatności** w menu.",
            "Uzupełnij **Dane do faktury**. Dla firmy wystarczy NIP - kliknij "
            "**Sprawdź NIP**, a nazwę i adres pobierzemy z rejestru.",
            "Wybierz plan i okres (miesięcznie albo rocznie) i kliknij "
            "**Zamawiam i płacę**.",
            "Faktury pobierzesz w sekcji **Faktury VAT** (**Pobierz PDF**).",
        ],
        tips=[
            "Kartę zmienisz przyciskiem **Karta i subskrypcja**.",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["zmien-anuluj-plan", "plany-i-limity"],
        keywords="płatność zapłacić karta faktura vat nip rachunek paragon stripe",
    ),
    Article(
        "zmien-anuluj-plan",
        "plan",
        "Jak zmienić albo anulować plan",
        "Plan zmienisz albo anulujesz w każdej chwili w **Planie i "
        "płatnościach**. Po anulowaniu plan działa do końca opłaconego okresu.",
        steps=[
            "Kliknij **Plan i płatności**.",
            "Żeby zmienić plan, wybierz inny i potwierdź.",
            "Żeby anulować, kliknij **Karta i subskrypcja** i anuluj subskrypcję.",
            "Zmieniłeś zdanie? Kliknij **Wznów subskrypcję**.",
        ],
        tips=[
            f"Po zakończeniu płatnego planu konto przechodzi na {FREE.name} - "
            "dane zostają.",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["zaplac-faktura", "usun-konto"],
        keywords="anulować subskrypcję zrezygnować zmienić plan obniżyć "
        "podwyższyć wypowiedzieć",
    ),
    # --- Problemy ------------------------------------------------------------
    Article(
        "klient-nie-dostal-maila",
        "problemy",
        "Klient mówi, że nie dostał maila",
        "Najczęściej mail trafił do spamu albo w adresie jest literówka. "
        "Link do prośby możesz też wysłać klientowi sam.",
        steps=[
            "Poproś klienta, żeby zajrzał do folderów Spam, Oferty i Powiadomienia.",
            "Sprawdź adres e-mail klienta na stronie prośby. Jeśli jest błędny, "
            "popraw go na karcie klienta.",
            "W karcie **Link dla klienta** kliknij **Wyślij link** - możesz "
            "wpisać inny adres.",
            "Albo skopiuj link i wyślij go klientowi SMS-em lub komunikatorem - "
            "działa tak samo.",
        ],
        tips=[
            "W historii prośby zobaczysz „Klient otworzył link”, gdy go otworzy.",
        ],
        related=["przypomnij-teraz", "nazwa-dla-klientow"],
        keywords="nie dostał maila spam nie przyszło nie widzi wiadomości "
        "nie doszło link",
        popular=True,
    ),
    Article(
        "nie-dostaje-maili",
        "problemy",
        "Nie dostaję maili z Monituj",
        "Sprawdź folder Spam i dodaj nasz adres do kontaktów - wtedy maile "
        "będą trafiać do skrzynki odbiorczej.",
        steps=[
            "Zajrzyj do folderów Spam, Oferty i Powiadomienia.",
            "Oznacz wiadomość od Monituj jako „To nie spam” i dodaj nadawcę do "
            "kontaktów.",
            "Sprawdź w **Ustawieniach**, czy Twój adres e-mail jest poprawny.",
        ],
        tips=[
            "Wszystko, co przesłali klienci, widzisz też w zakładce **Powiadomienia**.",
        ],
        related=["powiadomienia", "zmien-haslo-email"],
        keywords="nie dostaję maili spam powiadomienia nie przychodzą",
    ),
    Article(
        "nie-moge-sie-zalogowac",
        "problemy",
        "Nie mogę się zalogować",
        "Najczęściej pomaga ustawienie nowego hasła albo potwierdzenie adresu e-mail.",
        steps=[
            "Nie pamiętasz hasła? Na stronie logowania kliknij **Nie pamiętasz "
            "hasła?** i ustaw nowe z linku w mailu.",
            "Widzisz komunikat o potwierdzeniu adresu? Kliknij link w mailu od "
            "Monituj (sprawdź też Spam) - wyślemy go jeszcze raz przy próbie "
            "logowania.",
            "Zakładałeś konto przez Google? Kliknij **Zaloguj się przez Google**.",
            "Nie masz telefonu z aplikacją do kodów? Użyj kodu zapasowego.",
        ],
        tips=[
            "Po kilku nieudanych próbach logowanie blokuje się na 15 minut - "
            "to ochrona przed włamaniem.",
        ],
        panel=("accounts:login", "Logowanie"),
        related=["zmien-haslo-email", "weryfikacja-dwuetapowa"],
        keywords="logowanie nie mogę się zalogować zapomniałem hasła reset "
        "hasła zablokowane",
    ),
    Article(
        "plik-sie-nie-przesyla",
        "problemy",
        "Plik się nie przesyła",
        f"Przyjmujemy pliki {_EXTENSIONS} do {_MAX_MB} MB każdy. Każdy plik "
        "sprawdza też skaner antywirusowy. Pod polem pojawia się komunikat, "
        "co poszło nie tak - poniżej wyjaśniamy, co zrobić.",
        steps=[
            "Sprawdź, czy plik nie jest większy niż " + f"{_MAX_MB} MB. Zdjęcia "
            "większe niż to zmniejszamy same jeszcze przed wysłaniem.",
            "Sprawdź format. Plik ZIP albo RAR rozpakuj i prześlij pliki osobno.",
            "Zdjęcia z telefonu są w porządku, także z iPhone'a (HEIC).",
            "Sprawdź połączenie z internetem i spróbuj jeszcze raz.",
        ],
        body=[
            "**Plik został zablokowany przez skaner antywirusowy** - w pliku "
            "jest wirus albo coś, co go przypomina. Sprawdź komputer programem "
            "antywirusowym. Jeśli dokument jest w porządku, zapisz go "
            "ponownie (np. jako PDF) i wyślij jeszcze raz.",
            "**Plik zawiera makra** - arkusz albo dokument Worda z makrami. "
            "Makra to najczęstszy sposób, w jaki wirusy trafiają do biur, więc "
            "takich plików nie przyjmujemy. W Excelu wybierz **Plik → Zapisz "
            "jako** i typ **Skoroszyt programu Excel (.xlsx)** albo **PDF**; w "
            "Wordzie - **Dokument programu Word (.docx)** albo **PDF**.",
            "**Plik jest uszkodzony albo nie jest dokumentem Office** - plik "
            "ma końcówkę .docx lub .xlsx, ale w środku jest coś innego. Otwórz "
            "go i zapisz ponownie albo wyślij jako PDF.",
            "**Nie możemy teraz sprawdzić pliku** - skaner chwilowo nie "
            "odpowiada. Nic nie musisz robić - spróbuj ponownie za kilka minut.",
            f"**Zdjęcie ma zbyt dużą rozdzielczość** - zdjęcie PNG albo z "
            f"iPhone'a ma ponad {_MAX_MPX} megapikseli. Zrób zrzut ekranu albo "
            "zapisz zdjęcie jako JPG i prześlij ponownie.",
        ],
        tips=[
            "Prośba zamknięta przez nadawcę nie przyjmuje już plików.",
        ],
        related=["z-telefonu", "jak-przeslac-dokumenty"],
        keywords="nie da się przesłać błąd uploadu za duży plik format zip pdf "
        "rozmiar wirus antywirus zablokowany makra makro xlsm uszkodzony "
        "rozdzielczość skaner",
    ),
    Article(
        "limit-planu",
        "problemy",
        "Nie mogę wysłać nowej prośby",
        "Najpewniej wykorzystałeś limit próśb w toku w swoim planie. Nic się "
        "nie zatrzymuje - przypomnienia wychodzą, a klienci przesyłają pliki.",
        steps=[
            "Sprawdź licznik na dole menu po lewej, np. „3 z 3 próśb w toku”.",
            "Zamknij prośby, na które już nie czekasz - zwalniają miejsce.",
            "Albo wybierz większy plan w **Planie i płatnościach**.",
        ],
        tips=[
            "Konto ma mniej niż tydzień i komunikat mówi o liczbie odbiorców "
            "albo wiadomości? Zobacz [[pierwszy-tydzien]].",
            "Komunikat mówi o „próbie wyłudzenia”? Zobacz [[czego-nie-prosic]].",
        ],
        panel=("billing:plan", "Plan i płatności"),
        related=["plany-i-limity", "pierwszy-tydzien", "zmien-zamknij-usun"],
        keywords="limit nie mogę wysłać zablokowane brak miejsca przekroczony",
    ),
    # --- Dla klientów --------------------------------------------------------
    Article(
        "jak-przeslac-dokumenty",
        "dla-klientow",
        "Dostałem prośbę o dokumenty. Co teraz?",
        "Otwórz link z maila i przy każdym dokumencie kliknij **Wybierz "
        "plik**. Nie musisz zakładać konta ani niczego instalować.",
        steps=[
            "Otwórz e-mail z prośbą i kliknij przycisk z linkiem.",
            "Zobaczysz listę dokumentów, o które prosi nadawca.",
            "Przy dokumencie kliknij **Wybierz plik** (albo przeciągnij plik na "
            "pole) i wybierz plik z komputera lub telefonu.",
            "Plik przesyła się od razu - przy dokumencie pojawi się "
            "„Dostarczony”. Nie trzeba niczego zatwierdzać.",
            "Powtórz przy kolejnych dokumentach. Możesz wracać do linku, ile "
            "razy chcesz.",
        ],
        tips=[
            "Po przesłaniu dostaniesz e-mail z potwierdzeniem i listą tego, "
            "czego jeszcze brakuje.",
            "Do jednego dokumentu możesz dodać kilka plików - także kilka naraz.",
            "Masz coś, czego nie ma na liście? Zobacz [[inny-dokument]].",
            "Nie masz któregoś dokumentu? Zobacz [[nie-mam]].",
        ],
        related=["z-telefonu", "nie-mam", "pomylka"],
        keywords="jak przesłać dokumenty wysłać dokumenty link prośba co zrobić "
        "dostałem maila odbiorca klient załączyć",
        popular=True,
    ),
    Article(
        "z-telefonu",
        "dla-klientow",
        "Jak przesłać dokument z telefonu",
        "Otwórz link z maila w telefonie. Po kliknięciu **Wybierz plik** "
        "możesz zrobić zdjęcie dokumentu albo wybrać plik z telefonu.",
        steps=[
            "Otwórz e-mail z prośbą w telefonie i kliknij link.",
            "Przy dokumencie kliknij **Wybierz plik**.",
            "Wybierz **Zrób zdjęcie** (albo „Aparat”) i sfotografuj dokument - "
            "albo wybierz zdjęcie lub plik z telefonu.",
        ],
        tips=[
            "Rób zdjęcie przy dobrym świetle, z góry, tak żeby cały dokument "
            "był widoczny i ostry.",
            "Zdjęcia z iPhone'a są w porządku - zamieniamy je na JPG.",
            "Dokument ma kilka stron? [[kilka-stron|Sfotografuj każdą - "
            "połączymy je w jeden PDF]].",
        ],
        related=["kilka-stron", "jak-przeslac-dokumenty", "plik-sie-nie-przesyla"],
        keywords="telefon komórka zdjęcie aparat smartfon iphone android sfotografować",
        popular=True,
    ),
    Article(
        "kilka-stron",
        "dla-klientow",
        "Jak przesłać dokument, który ma kilka stron",
        "Zrób zdjęcie każdej strony - połączymy je w jeden plik PDF, w "
        "kolejności, w jakiej je zrobiłeś.",
        steps=[
            "Przy dokumencie kliknij **Zrób zdjęcia stron - połączymy je w jeden "
            "PDF**.",
            "Zrób zdjęcie pierwszej strony (albo wybierz zdjęcia z telefonu).",
            "Kliknij **+ Dodaj kolejną stronę** i sfotografuj następną. Powtórz "
            "dla wszystkich stron.",
            "Sprawdź miniatury. Złe zdjęcie usuniesz krzyżykiem.",
            "Kliknij **Wyślij jako PDF**.",
        ],
        tips=[
            "Połączymy najwyżej 15 stron naraz. Dłuższy dokument wyślij w częściach.",
            "Masz już gotowy plik PDF? Prześlij go zwykłym przyciskiem **Wybierz "
            "plik**.",
        ],
        related=["z-telefonu", "jak-przeslac-dokumenty"],
        keywords="kilka stron wiele stron jeden plik pdf połączyć zdjęcia "
        "skan skanować wyciąg strony",
        popular=True,
    ),
    Article(
        "inny-dokument",
        "dla-klientow",
        "Chcę przesłać coś, czego nie ma na liście",
        "Pod listą dokumentów kliknij **+ Dodaj inny dokument**, napisz, co "
        "to jest, i wybierz plik. Nadawca zobaczy go na swojej liście.",
        steps=[
            "Przewiń stronę prośby pod listę dokumentów.",
            "Kliknij **+ Dodaj inny dokument**.",
            "Wpisz, co to za dokument, np. „Faktura za paliwo z 14.10”.",
            "Wybierz plik i kliknij **Prześlij**.",
        ],
        tips=[
            "Do jednej prośby możesz dodać najwyżej 10 dokumentów spoza listy.",
        ],
        related=["jak-przeslac-dokumenty", "kilka-stron"],
        keywords="dodatkowy dokument inny plik nie ma na liście coś jeszcze "
        "dodać więcej",
    ),
    Article(
        "nie-mam",
        "dla-klientow",
        "Nie mam jednego z dokumentów",
        "Kliknij **Nie mam tego dokumentu** pod dokumentem i wybierz powód. "
        "Nadawca dostanie informację, a przypomnienia o tym dokumencie ustaną.",
        steps=[
            "Pod dokumentem kliknij **Nie mam tego dokumentu**.",
            "Wybierz powód: **W tym okresie go nie było**, **Ten dokument mnie "
            "nie dotyczy** - albo wpisz własny i kliknij **Wyślij**.",
        ],
        tips=[
            "Pomyłka? Kliknij **Cofnij - jednak go mam** i prześlij plik.",
            "Jeśli nadawca jednak będzie potrzebował dokumentu, dostaniesz "
            "e-mail z wyjaśnieniem.",
            "Przy pozycji, która nie jest plikiem (np. nadanie uprawnień), "
            "klikasz **Zrobione**, gdy to zrobisz.",
        ],
        related=["jak-przeslac-dokumenty", "przypomnienia-odbiorcy"],
        keywords="nie mam dokumentu brak nie dotyczy nie było zrobione",
    ),
    Article(
        "pomylka",
        "dla-klientow",
        "Przesłałem zły plik",
        "Możesz go usunąć przyciskiem **Usuń** obok pliku i przesłać właściwy - "
        "dopóki nadawca go nie zaakceptował.",
        steps=[
            "Otwórz link do prośby na tym samym urządzeniu, z którego przesyłałeś "
            "plik.",
            "Obok pliku kliknij **Usuń**.",
            "Prześlij właściwy plik.",
        ],
        tips=[
            "Nie widzisz przycisku **Usuń**? Plik mógł zostać już "
            "zaakceptowany albo przesłany z innego urządzenia. Napisz wtedy do "
            "nadawcy - jego adres jest u góry strony.",
        ],
        related=["jak-przeslac-dokumenty", "nie-widze-plikow"],
        keywords="zły plik pomyłka usunąć plik zamienić poprawić błędny",
    ),
    Article(
        "odpowiedz-na-pytanie",
        "dla-klientow",
        "Jak odpowiedzieć na pytanie",
        "Otwórz link z maila, wpisz odpowiedź i kliknij **Wyślij odpowiedź**. "
        "Możesz też dołączyć plik, np. zdjęcie faktury.",
        steps=[
            "Kliknij link w mailu z pytaniem.",
            "Wpisz odpowiedź w polu **Twoja odpowiedź**.",
            "Jeśli chcesz, dołącz plik.",
            "Kliknij **Wyślij odpowiedź**.",
        ],
        tips=[
            "Chcesz coś dopisać? Wejdź w ten sam link - Twoja odpowiedź i "
            "kolejne pytania są w jednej rozmowie.",
        ],
        related=["jak-przeslac-dokumenty", "wszystkie-moje-prosby"],
        keywords="odpowiedzieć pytanie odpowiedź przelew wyjaśnić",
    ),
    Article(
        "haslo-odbiorcy",
        "dla-klientow",
        "Strona prosi o hasło",
        "Nadawca zabezpieczył prośbę hasłem. Hasło przyszło w osobnym mailu, "
        "zaraz po mailu z linkiem.",
        steps=[
            "Znajdź drugi e-mail z tą prośbą - z hasłem (sprawdź też Spam).",
            "Wpisz hasło na stronie i kliknij przycisk, żeby otworzyć prośbę.",
        ],
        tips=[
            "Nie masz maila z hasłem? Napisz do nadawcy - jego adres jest w "
            "mailu z prośbą.",
        ],
        related=["jak-przeslac-dokumenty", "bezpieczenstwo-odbiorcy"],
        keywords="hasło prosi o hasło zabezpieczona nie mam hasła",
    ),
    Article(
        "wszystkie-moje-prosby",
        "dla-klientow",
        "Gdzie są wszystkie moje prośby",
        "W mailach od Monituj jest link „Wszystkie Twoje prośby” - prowadzi do "
        "jednej strony ze wszystkimi prośbami i pytaniami wysłanymi na Twój "
        "adres, od wszystkich nadawców.",
        body=[
            "Pytania są w osobnej sekcji, prośby o dokumenty w osobnej.",
            "Zapisz ten link w zakładkach przeglądarki - zawsze znajdziesz tam "
            "aktualną listę.",
        ],
        related=["jak-przeslac-dokumenty", "nie-widze-plikow"],
        keywords="wszystkie prośby lista moje prośby gdzie znaleźć zgubiłem link",
    ),
    Article(
        "nie-widze-plikow",
        "dla-klientow",
        "Nie widzę plików, które już przesłałem",
        "Dla bezpieczeństwa pokazujemy tylko pliki przesłane z tego urządzenia "
        "w ostatnich 2 tygodniach. Pozostałe zobaczysz po potwierdzeniu, że "
        "to Ty.",
        steps=[
            "Na stronie prośby kliknij **Wyślij mi link do moich plików**.",
            "Otwórz e-mail i kliknij link - zobaczysz wszystkie swoje pliki.",
        ],
        tips=[
            "Nadawca widzi wszystkie Twoje pliki - nic nie zginęło.",
            "Tak chronimy Twoje dokumenty, gdyby ktoś dostał link od Ciebie.",
        ],
        related=["pomylka", "wszystkie-moje-prosby"],
        keywords="nie widzę plików zniknęły pliki inne urządzenie przesłane wcześniej "
        "gdzie są moje pliki",
    ),
    Article(
        "przypomnienia-odbiorcy",
        "dla-klientow",
        "Dlaczego dostaję przypomnienia i jak je zatrzymać",
        "Przypomnienia wychodzą, dopóki brakuje dokumentów. Zatrzymasz je, "
        "przesyłając dokumenty albo zaznaczając, że któregoś nie masz.",
        body=[
            "Przypomnienie o dokumencie ustaje, gdy go prześlesz albo klikniesz "
            "**Nie mam tego dokumentu**.",
            "Gdy dotrze komplet, przypomnienia wyłączą się same i dostaniesz "
            "potwierdzenie.",
            "Przypomnienia przestają też, gdy nadawca zamknie prośbę.",
        ],
        tips=[
            "Masz pytania do nadawcy? Odpowiedz na jego e-mail albo napisz na "
            "adres widoczny na stronie prośby.",
        ],
        related=["nie-mam", "jak-przeslac-dokumenty"],
        keywords="przypomnienia zatrzymać za dużo maili wypisać się spam "
        "przestać dostawać",
    ),
    Article(
        "bezpieczenstwo-odbiorcy",
        "dla-klientow",
        "Czy przesyłanie dokumentów jest bezpieczne?",
        "Tak. Pliki są szyfrowane i widzi je tylko nadawca prośby. Po czasie "
        "ustalonym przez nadawcę są trwale usuwane.",
        body=[
            "Każda prośba ma unikalny, trudny do odgadnięcia link. Nadawca może "
            "go dodatkowo zabezpieczyć hasłem.",
            "Pliki są szyfrowane na dysku, a połączenie jest szyfrowane.",
            "Każdy przesłany plik sprawdza skaner antywirusowy, zanim trafi "
            "do nadawcy.",
            "Administratorem Twoich danych jest nadawca prośby. Monituj "
            "przechowuje je tylko w jego imieniu.",
            "Przed usunięciem plików dostaniesz wiadomość.",
        ],
        tips=[
            "Nie przekazuj linku do prośby osobom, które nie powinny widzieć "
            "Twoich dokumentów.",
            "Prośba wydaje Ci się podejrzana? Zobacz [[podejrzana-prosba]].",
        ],
        related=["podejrzana-prosba", "haslo-odbiorcy", "nie-widze-plikow"],
        keywords="bezpieczeństwo bezpieczne rodo dane osobowe szyfrowanie "
        "kto widzi oszustwo antywirus",
    ),
    Article(
        "podejrzana-prosba",
        "dla-klientow",
        "Prośba wydaje się podejrzana. Jak to sprawdzić i zgłosić?",
        "Sprawdź, od kogo jest prośba. Jeśli ktoś się pod kogoś podszywa albo "
        "prosi o hasła czy kody, kliknij **Zgłoś nadużycie** na dole maila "
        "albo strony prośby.",
        body=[
            "W mailu i na stronie prośby zawsze widać nazwę nadawcy i jego "
            "adres e-mail („Od: …”). Prawdziwe biuro pisze ze swojego adresu - "
            "nie z przypadkowej skrzynki.",
            "Uważaj, gdy prośba: przychodzi od kogoś, kogo nie znasz; dotyczy "
            "„weryfikacji konta” albo „blokady”; pogania i straszy; prosi o "
            "hasło, kod PIN, BLIK, SMS albo numer karty. Żadne biuro "
            "rachunkowe nie potrzebuje takich danych.",
            "Monituj nigdy nie prosi o hasła ani kody. Nie musisz zakładać konta "
            "ani instalować programów, żeby przesłać dokumenty.",
        ],
        steps=[
            "Kliknij **Zgłoś nadużycie** na dole maila z prośbą albo na dole "
            "strony prośby.",
            "Wybierz, co jest nie tak, i jeśli chcesz, dopisz kilka słów.",
            "Kliknij **Wyślij zgłoszenie**. Sprawdzimy nadawcę i zablokujemy "
            "konto, jeśli to oszustwo.",
        ],
        tips=[
            "Do czasu wyjaśnienia nie przesyłaj tej osobie dokumentów.",
            "Podałeś już hasło, kod albo dane karty? Od razu zadzwoń do "
            "swojego banku i zmień hasło.",
            "Znasz nadawcę, ale coś się nie zgadza? Zadzwoń do niego na znany "
            "Ci numer i zapytaj, czy to on wysłał prośbę.",
        ],
        related=["bezpieczenstwo-odbiorcy", "jak-przeslac-dokumenty"],
        keywords="oszustwo podejrzana prośba phishing wyłudzenie fałszywy mail "
        "zgłoś nadużycie spam bank urząd blik pin hasło nie znam nadawcy",
    ),
]


BY_SLUG = {article.slug: article for article in ARTICLES}
CATEGORY_BY_SLUG = {category.slug: category for category in CATEGORIES}


def in_category(slug):
    return [article for article in ARTICLES if article.category == slug]


def popular():
    return [article for article in ARTICLES if article.popular]
