"""Ready request templates ("Gotowe szablony") - three for each industry on
the site (apps/common/content.py SEGMENTS), written for Poland as it is in
2026: KSeF for invoices, UPL-1 and ZUS-PEL for an accounting office, PIT-2
for payroll, the energy certificate for selling a flat.

They live in code, not in the database: everyone can use them, they don't
count towards the plan's templates, and each has a public page
(/szablony/<slug>/) that search engines find. An item is (name, hint): the
name goes on the request's list, the hint explains it on the public page.

Checked by someone who knows the trade before changing the wording here -
these pages are read as advice."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadyTemplate:
    slug: str
    segment: str
    title: str
    # The request's name - {miesiąc} becomes last month, as in recurring ones.
    name: str
    # The note the recipient reads above the list.
    description: str
    items: tuple
    # One of the request form's deadline buttons.
    deadline: str = "14"
    # Worth sending every month (the form suggests "Powtarzaj").
    monthly: bool = False
    # One sentence for the library and the search result (<= 155 chars).
    summary: str = ""

    @property
    def item_names(self):
        return [name for name, _ in self.items]


TEMPLATES = [
    # --- biura rachunkowe ---------------------------------------------------
    ReadyTemplate(
        slug="dokumenty-ksiegowe-za-miesiac",
        segment="biura-rachunkowe",
        title="Dokumenty księgowe za miesiąc",
        name="Dokumenty za {miesiąc}",
        description=(
            "Prześlij proszę dokumenty za miniony miesiąc - najpóźniej do 10. "
            "dnia miesiąca, żebyśmy zdążyli z rozliczeniem VAT, PIT i ZUS. "
            "Faktur, które są w KSeF, nie musisz przesyłać."
        ),
        items=(
            (
                "Wyciągi bankowe",
                "Ze wszystkich rachunków firmowych, za cały miesiąc - najlepiej "
                "PDF z bankowości internetowej.",
            ),
            (
                "Faktury kosztowe spoza KSeF",
                "Np. od zagranicznych dostawców, faktury uproszczone i paragony z NIP.",
            ),
            (
                "Faktury sprzedaży spoza KSeF",
                "Np. faktury z kasy fiskalnej albo wystawione w trybie awaryjnym.",
            ),
            (
                "Raport miesięczny z kasy fiskalnej",
                "Jeśli sprzedajesz na kasie.",
            ),
            (
                "Umowy zawarte w miesiącu",
                "Nowe albo zmienione: najmu, leasingu, pożyczki, zlecenia, o dzieło.",
            ),
            (
                "Dokumenty importu i eksportu",
                "Zgłoszenia celne i dokumenty przewozowe (CMR) - do importu, "
                "eksportu, WNT i WDT.",
            ),
            (
                "Ewidencja przebiegu pojazdu",
                "Jeśli odliczasz 100% VAT od samochodu firmowego.",
            ),
        ),
        deadline="day10",
        monthly=True,
        summary=(
            "Comiesięczna lista dokumentów dla klienta biura rachunkowego: "
            "wyciągi, faktury spoza KSeF, raport z kasy, umowy - termin do 10. "
            "dnia miesiąca."
        ),
    ),
    ReadyTemplate(
        slug="zamkniecie-roku",
        segment="biura-rachunkowe",
        title="Zamknięcie roku",
        name="Dokumenty do zamknięcia roku",
        description=(
            "Na koniec roku potrzebujemy kilku dokumentów, które nie przychodzą "
            "co miesiąc. Prześlij je proszę, żebyśmy mogli zamknąć rok i "
            "przygotować zeznanie roczne."
        ),
        items=(
            (
                "Spis z natury na 31 grudnia",
                "Towary, materiały i wyroby z ilościami i cenami - jeśli masz zapasy.",
            ),
            (
                "Potwierdzenia sald na koniec roku",
                "Od banków, kontrahentów i pożyczkodawców.",
            ),
            (
                "Umowy kredytów, pożyczek i leasingu",
                "Z aktualnym harmonogramem spłat.",
            ),
            (
                "Dokumenty środków trwałych kupionych i sprzedanych w roku",
                "Faktury, umowy sprzedaży albo protokoły likwidacji.",
            ),
            (
                "Informacja o innych dochodach",
                "PIT-11 od pracodawców, najem prywatny, dochody z zagranicy - do "
                "zeznania PIT.",
            ),
            (
                "Dokumenty do ulg i odliczeń",
                "Np. wpłaty na IKZE, darowizny, wydatki na termomodernizację - "
                "jeśli dotyczą.",
            ),
        ),
        deadline="14",
        summary=(
            "Lista dokumentów do zamknięcia roku w biurze rachunkowym: remanent, "
            "potwierdzenia sald, umowy kredytów, środki trwałe i dokumenty do ulg."
        ),
    ),
    ReadyTemplate(
        slug="nowy-klient-biura-rachunkowego",
        segment="biura-rachunkowe",
        title="Nowy klient biura rachunkowego",
        name="Dokumenty na start współpracy",
        description=(
            "Witamy! Żeby przejąć Twoją księgowość, potrzebujemy kilku dokumentów "
            "i pełnomocnictw. Wszystko prześlesz tutaj - bez skanów w mailach."
        ),
        items=(
            ("Podpisana umowa o usługi księgowe", ""),
            (
                "Wydruk z CEIDG albo odpis z KRS",
                "Aktualny - z danymi firmy i sposobem reprezentacji.",
            ),
            (
                "Pełnomocnictwo UPL-1",
                "Do podpisywania i wysyłania deklaracji podatkowych przez biuro.",
            ),
            (
                "Pełnomocnictwo ZUS-PEL",
                "Do rozliczeń z ZUS w imieniu firmy.",
            ),
            (
                "Potwierdzenie nadania biuru uprawnień w KSeF",
                "Żebyśmy mieli dostęp do Twoich faktur w KSeF.",
            ),
            (
                "Dokumentacja od poprzedniego biura",
                "Księgi (KPiR albo księgi rachunkowe), ewidencja środków trwałych "
                "i deklaracje z bieżącego roku.",
            ),
            (
                "Lista rachunków bankowych firmy",
                "Wszystkie rachunki firmowe, także walutowe.",
            ),
        ),
        deadline="7",
        summary=(
            "Dokumenty od nowego klienta biura rachunkowego: umowa, UPL-1, "
            "ZUS-PEL, dostęp do KSeF i dokumentacja od poprzedniego biura."
        ),
    ),
    # --- kadry --------------------------------------------------------------
    ReadyTemplate(
        slug="dokumenty-nowego-pracownika",
        segment="kadry",
        title="Dokumenty nowego pracownika",
        name="Dokumenty do zatrudnienia",
        description=(
            "Cieszymy się, że dołączasz! Prześlij proszę dokumenty potrzebne do "
            "zatrudnienia - najlepiej przed pierwszym dniem pracy."
        ),
        items=(
            (
                "Kwestionariusz osobowy",
                "Wypełniony i podpisany - wzór dostaniesz od nas.",
            ),
            (
                "Świadectwa pracy",
                "Z poprzednich miejsc pracy - od nich zależy wymiar urlopu.",
            ),
            (
                "Dyplom lub świadectwo ukończenia szkoły",
                "Okres nauki wlicza się do stażu, od którego zależy urlop.",
            ),
            (
                "Orzeczenie lekarskie z badań wstępnych",
                "Skierowanie na badania wystawimy my.",
            ),
            (
                "Oświadczenie PIT-2",
                "Jeśli chcesz, żebyśmy stosowali kwotę zmniejszającą podatek.",
            ),
            ("Numer rachunku bankowego do wypłaty wynagrodzenia", ""),
            (
                "Dane członków rodziny do ubezpieczenia zdrowotnego",
                "Jeśli chcesz zgłosić dziecko lub małżonka.",
            ),
            (
                "Uprawnienia i certyfikaty zawodowe",
                "Np. SEP, UDT, prawo jazdy - jeśli są potrzebne na stanowisku.",
            ),
        ),
        deadline="7",
        summary=(
            "Lista dokumentów od nowego pracownika: kwestionariusz osobowy, "
            "świadectwa pracy, badania wstępne, PIT-2 i numer konta."
        ),
    ),
    ReadyTemplate(
        slug="umowa-zlecenia",
        segment="kadry",
        title="Umowa zlecenia",
        name="Dokumenty do umowy zlecenia",
        description=(
            "Prześlij proszę dokumenty potrzebne do zawarcia umowy zlecenia i "
            "zgłoszenia do ZUS."
        ),
        items=(
            (
                "Oświadczenie zleceniobiorcy do celów ZUS",
                "Czy masz inne umowy, zatrudnienie albo firmę - od tego zależą "
                "składki.",
            ),
            (
                "Legitymacja studencka lub zaświadczenie z uczelni",
                "Jeśli jesteś studentem i nie masz 26 lat - wtedy umowa jest "
                "zwolniona ze składek ZUS.",
            ),
            (
                "Oświadczenie PIT-2",
                "Jeśli chcesz, żebyśmy stosowali kwotę zmniejszającą podatek.",
            ),
            ("Numer rachunku bankowego do wypłaty wynagrodzenia", ""),
            ("Orzeczenie lekarskie", "Tylko jeśli wymaga tego rodzaj pracy."),
        ),
        deadline="7",
        summary=(
            "Dokumenty od zleceniobiorcy: oświadczenie do ZUS, legitymacja "
            "studencka do zwolnienia ze składek, PIT-2 i numer konta."
        ),
    ),
    ReadyTemplate(
        slug="zatrudnienie-cudzoziemca",
        segment="kadry",
        title="Zatrudnienie cudzoziemca",
        name="Dokumenty do zatrudnienia cudzoziemca",
        description=(
            "Żeby legalnie powierzyć Ci pracę w Polsce, potrzebujemy kopii "
            "dokumentów pobytowych i podstawy do pracy. Prześlij je proszę "
            "przed rozpoczęciem pracy."
        ),
        items=(
            ("Paszport - strona ze zdjęciem i danymi", ""),
            (
                "Dokument uprawniający do pobytu",
                "Wiza, karta pobytu albo inny dokument - pracodawca musi "
                "przechowywać jego kopię.",
            ),
            (
                "Zezwolenie na pracę albo inna podstawa do pracy",
                "Jeśli masz - np. zezwolenie, oświadczenie o powierzeniu pracy "
                "albo dokument zwalniający z zezwolenia.",
            ),
            ("Potwierdzenie nadania numeru PESEL", "Jeśli masz PESEL."),
            (
                "Kwestionariusz osobowy",
                "Wypełniony i podpisany - wzór dostaniesz od nas.",
            ),
            (
                "Orzeczenie lekarskie z badań wstępnych",
                "Skierowanie na badania wystawimy my.",
            ),
            (
                "Świadectwa pracy lub dyplomy",
                "Jeśli masz - zagraniczne najlepiej z tłumaczeniem.",
            ),
        ),
        deadline="7",
        summary=(
            "Dokumenty do zatrudnienia cudzoziemca w Polsce: paszport, dokument "
            "pobytowy, podstawa do pracy, PESEL i badania wstępne."
        ),
    ),
    # --- kancelarie ---------------------------------------------------------
    ReadyTemplate(
        slug="nowy-klient-kancelarii",
        segment="kancelarie",
        title="Nowy klient kancelarii",
        name="Dokumenty do sprawy",
        description=(
            "Dziękujemy za powierzenie nam sprawy. Prześlij proszę podpisane "
            "dokumenty i wszystko, co jej dotyczy - to pozwoli nam szybko zacząć."
        ),
        items=(
            ("Podpisana umowa o świadczenie pomocy prawnej", ""),
            (
                "Podpisane pełnomocnictwo",
                "Skan - o oryginale porozmawiamy osobno.",
            ),
            (
                "Potwierdzenie zapłaty opłaty skarbowej od pełnomocnictwa",
                "17 zł na rachunek urzędu gminy właściwego dla sądu lub urzędu, "
                "w którym składamy pełnomocnictwo - jeśli opłata jest wymagana.",
            ),
            (
                "Dokumenty dotyczące sprawy",
                "Umowy, faktury, korespondencja, pisma z sądu lub urzędu - "
                "wszystko, co masz.",
            ),
            ("Wydruk z CEIDG albo odpis z KRS", "Jeśli sprawa dotyczy firmy."),
        ),
        deadline="7",
        summary=(
            "Dokumenty od nowego klienta kancelarii: umowa, pełnomocnictwo, "
            "opłata skarbowa 17 zł i dokumenty sprawy."
        ),
    ),
    ReadyTemplate(
        slug="sprawa-spadkowa",
        segment="kancelarie",
        title="Sprawa spadkowa",
        name="Dokumenty do sprawy spadkowej",
        description=(
            "Do stwierdzenia nabycia spadku - w sądzie albo u notariusza - "
            "potrzebujemy aktów stanu cywilnego i informacji o majątku. Prześlij "
            "proszę to, co masz, a resztę pomożemy uzyskać."
        ),
        items=(
            ("Odpis skrócony aktu zgonu spadkodawcy", ""),
            ("Testament", "Jeśli został sporządzony - każda strona."),
            (
                "Odpisy aktów stanu cywilnego spadkobierców",
                "Akty urodzenia, a przy zmianie nazwiska - akty małżeństwa.",
            ),
            (
                "Lista spadkobierców z adresami",
                "Wszystkie osoby, które mogą dziedziczyć.",
            ),
            (
                "Dokumenty majątku spadkowego",
                "Numery ksiąg wieczystych, umowy rachunków bankowych, dowody "
                "rejestracyjne pojazdów.",
            ),
            (
                "Informacja o długach spadkodawcy",
                "Kredyty, pożyczki, zaległości - ważne przy decyzji o przyjęciu "
                "spadku.",
            ),
        ),
        deadline="14",
        summary=(
            "Dokumenty do stwierdzenia nabycia spadku: akt zgonu, testament, akty "
            "stanu cywilnego spadkobierców i dokumenty majątku."
        ),
    ),
    ReadyTemplate(
        slug="windykacja-naleznosci",
        segment="kancelarie",
        title="Windykacja należności",
        name="Dokumenty do windykacji",
        description=(
            "Żeby odzyskać należność - polubownie albo w sądzie - potrzebujemy "
            "dokumentów, które potwierdzają dług i próby jego odzyskania."
        ),
        items=(
            (
                "Umowa z dłużnikiem albo zamówienie",
                "Także mailowe - wszystko, co potwierdza, na co się umówiliście.",
            ),
            ("Niezapłacone faktury", ""),
            (
                "Dowody wykonania usługi lub dostawy",
                "Protokoły odbioru, dokumenty WZ, CMR, potwierdzenia w korespondencji.",
            ),
            (
                "Wezwania do zapłaty i korespondencja z dłużnikiem",
                "Z potwierdzeniem wysłania, jeśli je masz.",
            ),
            (
                "Dane dłużnika",
                "NIP i adres, a dla firmy - wydruk z CEIDG albo odpis z KRS.",
            ),
        ),
        deadline="7",
        summary=(
            "Dokumenty do windykacji należności: umowa lub zamówienie, faktury, "
            "dowody wykonania, wezwania do zapłaty i dane dłużnika."
        ),
    ),
    # --- pośrednictwo -------------------------------------------------------
    ReadyTemplate(
        slug="kredyt-hipoteczny",
        segment="posrednictwo",
        title="Kredyt hipoteczny",
        name="Dokumenty do wniosku o kredyt hipoteczny",
        description=(
            "Do wniosku o kredyt hipoteczny bank potrzebuje dokumentów o "
            "dochodach i nieruchomości. Prześlij je proszę - sprawdzimy komplet, "
            "zanim trafią do banku."
        ),
        items=(
            (
                "Zaświadczenie o zatrudnieniu i zarobkach",
                "Na druku banku albo pracodawcy - zwykle nie starsze niż 30 dni.",
            ),
            (
                "Wyciągi z konta z ostatnich 3-6 miesięcy",
                "Z widocznymi wpływami wynagrodzenia.",
            ),
            (
                "Zeznanie PIT za ostatni rok",
                "Przy działalności - z UPO, razem z KPiR albo ewidencją przychodów.",
            ),
            (
                "Zaświadczenia o niezaleganiu z US i ZUS",
                "Tylko przy działalności gospodarczej.",
            ),
            (
                "Umowa przedwstępna albo rezerwacyjna",
                "Ze sprzedającym albo deweloperem.",
            ),
            ("Numer księgi wieczystej nieruchomości", ""),
            (
                "Potwierdzenie wkładu własnego",
                "Wyciąg ze środkami albo potwierdzenie wpłaty zadatku.",
            ),
        ),
        deadline="7",
        summary=(
            "Lista dokumentów do kredytu hipotecznego: zaświadczenie o zarobkach, "
            "wyciągi, PIT, umowa przedwstępna, księga wieczysta i wkład własny."
        ),
    ),
    ReadyTemplate(
        slug="leasing-dla-firmy",
        segment="posrednictwo",
        title="Leasing dla firmy",
        name="Dokumenty do wniosku leasingowego",
        description=(
            "Do wniosku leasingowego potrzebujemy dokumentów firmy i oferty na "
            "przedmiot leasingu. Przy prostszych umowach część z nich może nie "
            "być potrzebna - damy znać."
        ),
        items=(
            ("Oferta lub faktura proforma przedmiotu leasingu", ""),
            ("Wydruk z CEIDG albo odpis z KRS", ""),
            ("Zeznanie podatkowe za ostatni rok", "PIT albo CIT z UPO."),
            (
                "Dokumenty finansowe za bieżący rok",
                "KPiR, ewidencja przychodów albo bilans i rachunek zysków i strat.",
            ),
            (
                "Zaświadczenia o niezaleganiu z US i ZUS",
                "Jeśli leasingodawca o nie prosi.",
            ),
        ),
        deadline="7",
        summary=(
            "Dokumenty do leasingu dla firmy: oferta przedmiotu, CEIDG lub KRS, "
            "zeznanie podatkowe, dokumenty finansowe i zaświadczenia z US i ZUS."
        ),
    ),
    ReadyTemplate(
        slug="sprzedaz-mieszkania",
        segment="posrednictwo",
        title="Sprzedaż mieszkania",
        name="Dokumenty do sprzedaży mieszkania",
        description=(
            "Żeby przygotować ofertę i spokojnie dojść do umowy u notariusza, "
            "zbierzmy dokumenty mieszkania już teraz."
        ),
        items=(
            (
                "Podstawa nabycia mieszkania",
                "Akt notarialny, postanowienie o nabyciu spadku albo umowa darowizny.",
            ),
            (
                "Numer księgi wieczystej",
                "Jeśli mieszkanie ją ma - spółdzielcze prawo może jej nie mieć.",
            ),
            (
                "Zaświadczenie o braku zaległości w opłatach",
                "Ze wspólnoty albo spółdzielni.",
            ),
            (
                "Zaświadczenie o osobach zameldowanych",
                "Z urzędu gminy - notariusz o nie poprosi.",
            ),
            (
                "Świadectwo charakterystyki energetycznej",
                "Obowiązkowe przy sprzedaży - sporządza je uprawniona osoba.",
            ),
            (
                "Zaświadczenie ze spółdzielni o prawie do lokalu",
                "Tylko przy spółdzielczym własnościowym prawie do lokalu.",
            ),
        ),
        deadline="14",
        summary=(
            "Dokumenty do sprzedaży mieszkania: podstawa nabycia, księga "
            "wieczysta, zaświadczenia ze wspólnoty i gminy, świadectwo energetyczne."
        ),
    ),
    # --- b2b ----------------------------------------------------------------
    ReadyTemplate(
        slug="weryfikacja-kontrahenta",
        segment="b2b",
        title="Weryfikacja nowego kontrahenta",
        name="Dokumenty do rozpoczęcia współpracy",
        description=(
            "Zanim podpiszemy umowę, sprawdzamy każdego nowego kontrahenta. "
            "Prześlij proszę poniższe dokumenty - to jednorazowa formalność."
        ),
        items=(
            (
                "Wydruk z CEIDG albo odpis z KRS",
                "Aktualny - ze sposobem reprezentacji.",
            ),
            (
                "Dane do faktur i numer rachunku bankowego",
                "Rachunek powinien być na białej liście podatników VAT.",
            ),
            (
                "Zaświadczenie o niezaleganiu w podatkach",
                "Z urzędu skarbowego, nie starsze niż 3 miesiące.",
            ),
            (
                "Zaświadczenie o niezaleganiu w ZUS",
                "Nie starsze niż 3 miesiące.",
            ),
            ("Polisa OC działalności", "Jeśli współpraca tego wymaga."),
            (
                "Pełnomocnictwo osoby podpisującej umowę",
                "Jeśli podpisuje ją ktoś spoza reprezentacji z KRS.",
            ),
        ),
        deadline="7",
        summary=(
            "Weryfikacja kontrahenta B2B: KRS lub CEIDG, rachunek z białej listy "
            "VAT, zaświadczenia o niezaleganiu z US i ZUS, polisa OC."
        ),
    ),
    ReadyTemplate(
        slug="weryfikacja-dostawcy-rodo",
        segment="b2b",
        title="Weryfikacja dostawcy pod kątem RODO",
        name="Dokumenty RODO od dostawcy",
        description=(
            "Powierzamy Wam dane osobowe, więc zgodnie z art. 28 RODO musimy "
            "sprawdzić, czy zapewniacie im odpowiednią ochronę."
        ),
        items=(
            ("Podpisana umowa powierzenia przetwarzania danych", ""),
            (
                "Opis środków bezpieczeństwa",
                "Technicznych i organizacyjnych (art. 32 RODO), np. polityka "
                "bezpieczeństwa.",
            ),
            (
                "Lista podprocesorów",
                "Podmioty, którym dalej powierzacie dane, z krajem przetwarzania.",
            ),
            ("Certyfikaty bezpieczeństwa", "Np. ISO/IEC 27001 - jeśli je macie."),
            (
                "Dane kontaktowe inspektora ochrony danych",
                "Jeśli wyznaczyliście IOD.",
            ),
        ),
        deadline="14",
        summary=(
            "Weryfikacja dostawcy pod kątem RODO: umowa powierzenia, środki "
            "bezpieczeństwa z art. 32, lista podprocesorów i certyfikaty."
        ),
    ),
    ReadyTemplate(
        slug="rozliczenie-zlecenia",
        segment="b2b",
        title="Rozliczenie zlecenia lub projektu",
        name="Dokumenty do rozliczenia zlecenia",
        description=(
            "Żeby rozliczyć i zapłacić za wykonane prace, potrzebujemy kompletu "
            "dokumentów odbiorowych."
        ),
        items=(
            ("Podpisany protokół odbioru", ""),
            (
                "Faktura",
                "Wystawiona w KSeF dotrze do nas stamtąd - tutaj prześlij tylko "
                "fakturę spoza KSeF.",
            ),
            (
                "Raport z wykonanych prac",
                "Zakres, terminy i godziny - zgodnie z umową.",
            ),
            ("Dokumentacja powykonawcza", "Jeśli umowa jej wymaga."),
            (
                "Oświadczenie o zapłacie podwykonawcom",
                "Jeśli korzystaliście z podwykonawców.",
            ),
        ),
        deadline="7",
        summary=(
            "Dokumenty do rozliczenia zlecenia B2B: protokół odbioru, faktura, "
            "raport z prac, dokumentacja powykonawcza i oświadczenie o podwykonawcach."
        ),
    ),
]

BY_SLUG = {template.slug: template for template in TEMPLATES}


def get(slug):
    return BY_SLUG.get(slug)


def for_segment(segment_slug):
    return [t for t in TEMPLATES if t.segment == segment_slug]
