"""Full guides on the most searched ready templates' pages (/szablony/<slug>/):
people search "lista dokumentów do kredytu hipotecznego" and expect more
than the list - where each document comes from, what to watch, the usual
questions. The template's list stays in template_library.py; this adds the
text around it. Facts as of 2026 in Poland - checked before changing, as in
template_library.py: these pages are read as advice."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Guide:
    # The date the text was last checked - on the page and in the schema.
    updated: str
    intro: tuple
    # (document, where to get it, what to watch) - in the list's order.
    documents: tuple
    # (question, answer)
    faq: tuple
    # A closing paragraph under the documents.
    tip: str = ""

    @property
    def updated_on(self):
        return date.fromisoformat(self.updated)

    @property
    def faq_items(self):
        """As the site's FAQ list and schema take them."""
        return [{"q": question, "a": answer} for question, answer in self.faq]


GUIDES = {
    "kredyt-hipoteczny": Guide(
        updated="2026-10-29",
        intro=(
            "Bank ocenia dwie rzeczy: czy stać Cię na spłatę i czy nieruchomość "
            "jest dobrym zabezpieczeniem. Dlatego dokumenty do kredytu "
            "hipotecznego dzielą się na dochodowe - zaświadczenia, wyciągi, PIT - "
            "i dotyczące nieruchomości - umowa przedwstępna, księga wieczysta, "
            "wycena.",
            "Najwięcej czasu traci się nie w banku, ale na zbieraniu kompletu: "
            "jeden brakujący dokument wstrzymuje cały wniosek, a zaświadczenia "
            "mają krótką ważność. Poniżej każdy dokument po kolei - skąd go "
            "wziąć i na co uważać.",
        ),
        documents=(
            (
                "Zaświadczenie o zatrudnieniu i zarobkach",
                "Wystawia pracodawca, zwykle dział kadr albo biuro rachunkowe "
                "firmy. Wiele banków ma własny druk - zapytaj o niego, zanim "
                "poprosisz pracodawcę.",
                "Banki najczęściej przyjmują zaświadczenie nie starsze niż 30 dni. "
                "Nie zamawiaj go za wcześnie, bo przy dłuższej procedurze trzeba "
                "będzie prosić o nowe.",
            ),
            (
                "Wyciągi z konta z ostatnich 3-6 miesięcy",
                "Pobierzesz je jako PDF z bankowości internetowej, z każdego "
                "konta, na które wpływa wynagrodzenie.",
                "Bank sprawdza na nich, czy pensja wpływa regularnie i jakie masz "
                "stałe obciążenia. Wyciąg musi obejmować pełne miesiące, a nie "
                "tylko zrzut ekranu z historią.",
            ),
            (
                "Zeznanie PIT za ostatni rok",
                "Zeznanie i Urzędowe Poświadczenie Odbioru (UPO) pobierzesz z "
                "e-Urzędu Skarbowego (podatki.gov.pl).",
                "Przy działalności gospodarczej bank zwykle chce zeznań za dwa "
                "lata i bieżącej KPiR albo ewidencji przychodów - o dokładny "
                "okres zapytaj doradcę.",
            ),
            (
                "Zaświadczenia o niezaleganiu z US i ZUS",
                "Zaświadczenie z urzędu skarbowego zamówisz w e-Urzędzie "
                "Skarbowym (opłata skarbowa 21 zł), z ZUS - bezpłatnie przez "
                "PUE/eZUS. Urząd ma na wydanie zaświadczenia do 7 dni.",
                "Potrzebne tylko przy działalności gospodarczej. Zamów je od razu "
                "- to dokument, na który najczęściej się czeka.",
            ),
            (
                "Umowa przedwstępna albo rezerwacyjna",
                "Podpisujesz ją ze sprzedającym albo z deweloperem. Na rynku "
                "pierwotnym bank poprosi też o umowę deweloperską i prospekt "
                "informacyjny.",
                "W umowie powinny być: cena, dane nieruchomości z numerem księgi "
                "wieczystej, termin umowy końcowej i informacja, że zakup będzie "
                "finansowany kredytem.",
            ),
            (
                "Numer księgi wieczystej nieruchomości",
                "Znajdziesz go w umowie przedwstępnej albo dostaniesz od "
                "sprzedającego. Treść księgi bank sprawdza sam w elektronicznych "
                "księgach wieczystych (ekw.ms.gov.pl).",
                "Warto samemu zajrzeć do księgi przed podpisaniem umowy: dział "
                "III pokazuje ograniczenia, a dział IV - hipoteki.",
            ),
            (
                "Potwierdzenie wkładu własnego",
                "Wyciąg pokazujący zgromadzone środki albo potwierdzenie wpłaty "
                "zadatku lub zaliczki sprzedającemu.",
                "Rekomendacja S Komisji Nadzoru Finansowego zakłada wkład własny "
                "co najmniej 20% wartości nieruchomości albo 10% z dodatkowym "
                "zabezpieczeniem, np. ubezpieczeniem niskiego wkładu.",
            ),
        ),
        tip=(
            "Oprócz tych dokumentów bank zleci albo poprosi o operat szacunkowy - "
            "wycenę nieruchomości przez rzeczoznawcę. Dowodu osobistego nie "
            "wysyłaj mailem: pokażesz go w banku albo potwierdzisz tożsamość w "
            "aplikacji banku."
        ),
        faq=(
            (
                "Jak długo ważne są dokumenty do kredytu hipotecznego?",
                "Zaświadczenie o zarobkach i zaświadczenia o niezaleganiu banki "
                "przyjmują zwykle do 30 dni od wystawienia. Wyciągi i PIT nie "
                "tracą ważności, ale muszą obejmować ostatni okres.",
            ),
            (
                "Czy bank potrzebuje odpisu z księgi wieczystej?",
                "Zwykle nie - wystarczy numer księgi, a bank sprawdza ją sam w "
                "systemie elektronicznych ksiąg wieczystych.",
            ),
            (
                "Ile trwa zebranie dokumentów do kredytu?",
                "Najczęściej od kilku dni do dwóch tygodni. Najdłużej czeka się "
                "na zaświadczenia z urzędu skarbowego i na umowę przedwstępną.",
            ),
            (
                "Jak doradca kredytowy może szybciej zebrać dokumenty od klienta?",
                "Wysłać listę z terminem i przypomnieniami w jednym miejscu - "
                "klient przesyła pliki z telefonu, a doradca widzi, czego "
                "brakuje. Tak działa ta lista w Monituj.",
            ),
        ),
    ),
    "sprzedaz-mieszkania": Guide(
        updated="2026-10-29",
        intro=(
            "Do sprzedaży mieszkania potrzebujesz dokumentów, które potwierdzą "
            "trzy rzeczy: że jesteś właścicielem, że mieszkanie nie ma długów i "
            "obciążeń oraz jakie ma parametry. Notariusz poprosi o nie przed "
            "aktem, a kupujący - często już przy umowie przedwstępnej.",
            "Część dokumentów wydają urzędy i wspólnota, więc warto zamówić je z "
            "wyprzedzeniem. Poniżej każdy dokument: skąd go wziąć i na co uważać.",
        ),
        documents=(
            (
                "Podstawa nabycia mieszkania",
                "Akt notarialny zakupu, umowa darowizny albo postanowienie sądu "
                "lub akt poświadczenia dziedziczenia. Kopię (wypis) aktu wyda "
                "notariusz, który go sporządził.",
                "Przy mieszkaniu z rynku pierwotnego - umowa sprzedaży od "
                "dewelopera. Przy spadku notariusz sprawdzi też, czy złożono "
                "zgłoszenie do urzędu skarbowego.",
            ),
            (
                "Numer księgi wieczystej",
                "Jest w akcie notarialnym. Treść księgi sprawdzisz bezpłatnie w "
                "elektronicznych księgach wieczystych (ekw.ms.gov.pl).",
                "Spółdzielcze własnościowe prawo do lokalu może nie mieć księgi - "
                "wtedy dokumentem jest zaświadczenie ze spółdzielni.",
            ),
            (
                "Zaświadczenie o braku zaległości w opłatach",
                "Wydaje zarządca wspólnoty mieszkaniowej albo spółdzielnia.",
                "Kupujący chce mieć pewność, że nie przejmie długów za czynsz i "
                "media. Notariusze zwykle oczekują dokumentu wydanego niedawno.",
            ),
            (
                "Zaświadczenie o osobach zameldowanych",
                "Wydaje urząd gminy (wydział ewidencji ludności), opłata "
                "skarbowa 17 zł.",
                "Kupujący zwykle oczekuje, że w dniu wydania mieszkania nikt "
                "nie będzie w nim zameldowany - wymelduj się wcześniej.",
            ),
            (
                "Świadectwo charakterystyki energetycznej",
                "Sporządza je osoba wpisana do centralnego rejestru "
                "charakterystyki energetycznej budynków.",
                "Od 28 kwietnia 2023 r. trzeba je przekazać kupującemu przy "
                "sprzedaży. Świadectwo jest ważne 10 lat.",
            ),
            (
                "Zaświadczenie ze spółdzielni o prawie do lokalu",
                "Wydaje spółdzielnia mieszkaniowa.",
                "Tylko przy spółdzielczym własnościowym prawie do lokalu. "
                "Zaświadczenie potwierdza, komu przysługuje prawo i czy nie ma "
                "zadłużenia.",
            ),
        ),
        tip=(
            "Sprzedajesz mieszkanie przed upływem 5 lat, licząc od końca roku, w "
            "którym je kupiłeś? Wtedy trzeba złożyć PIT-39 i może pojawić się "
            "podatek - chyba że skorzystasz z ulgi mieszkaniowej. Szczegóły "
            "sprawdź z doradcą podatkowym albo w biurze rachunkowym."
        ),
        faq=(
            (
                "Jakie dokumenty są potrzebne do sprzedaży mieszkania u notariusza?",
                "Podstawa nabycia, numer księgi wieczystej, zaświadczenia o braku "
                "zaległości w opłatach i o osobach zameldowanych, świadectwo "
                "charakterystyki energetycznej oraz dowody osobiste stron.",
            ),
            (
                "Czy świadectwo energetyczne jest obowiązkowe przy sprzedaży?",
                "Tak - od 28 kwietnia 2023 r. sprzedający przekazuje je "
                "kupującemu. Świadectwo jest ważne 10 lat.",
            ),
            (
                "Jak długo ważne są zaświadczenia do sprzedaży mieszkania?",
                "Przepisy nie podają jednego terminu, ale notariusze i banki "
                "kupujących zwykle oczekują dokumentów wydanych w ostatnich "
                "tygodniach. Zamów je, gdy znasz już datę aktu.",
            ),
            (
                "Jak pośrednik może zebrać dokumenty od sprzedającego?",
                "Wysłać mu tę listę z terminem - sprzedający przesyła skany z "
                "telefonu, a Monituj sam przypomina o tym, czego jeszcze brakuje.",
            ),
        ),
    ),
    "dokumenty-nowego-pracownika": Guide(
        updated="2026-10-29",
        intro=(
            "Dokumenty do zatrudnienia pracownika określa Kodeks pracy i "
            "rozporządzenie o dokumentacji pracowniczej. Pracodawca może żądać "
            "tylko tego, co jest potrzebne - kwestionariusza, świadectw pracy, "
            "dokumentów o wykształceniu i orzeczenia lekarskiego.",
            "Dobrze zebrane dokumenty przed pierwszym dniem pracy oznaczają "
            "poprawny wymiar urlopu, zgłoszenie do ZUS na czas i pierwszą "
            "wypłatę bez poprawek. Poniżej każdy dokument po kolei.",
        ),
        documents=(
            (
                "Kwestionariusz osobowy",
                "Wzór przekazuje pracodawca. Pracownik podaje w nim m.in. adres "
                "zamieszkania, numer PESEL i dane kontaktowe.",
                "Kwestionariusz zawiera tylko dane, o które pracodawca może "
                "pytać na podstawie art. 22¹ Kodeksu pracy - inne informacje "
                "pracownik podaje dobrowolnie.",
            ),
            (
                "Świadectwa pracy",
                "Pracownik ma je od poprzednich pracodawców. Zgubione świadectwo "
                "można zamówić ponownie u byłego pracodawcy.",
                "Pracodawca może wymagać świadectw z bieżącego roku "
                "kalendarzowego. Starsze przydają się do ustalenia stażu: po 10 "
                "latach pracy urlop rośnie z 20 do 26 dni.",
            ),
            (
                "Dyplom lub świadectwo ukończenia szkoły",
                "Oryginał do wglądu, a do akt kopia albo odpis.",
                "Okres nauki wlicza się do stażu urlopowego: szkoła średnia "
                "ogólnokształcąca - 4 lata, średnia zawodowa - do 5 lat, szkoła "
                "policealna - 6 lat, studia wyższe - 8 lat.",
            ),
            (
                "Orzeczenie lekarskie z badań wstępnych",
                "Skierowanie wystawia pracodawca, badanie przeprowadza lekarz "
                "medycyny pracy. Koszt ponosi pracodawca.",
                "Bez aktualnego orzeczenia o braku przeciwwskazań pracodawca nie "
                "może dopuścić pracownika do pracy.",
            ),
            (
                "Oświadczenie PIT-2",
                "Druk wypełnia pracownik, jeśli chce, żeby płatnik stosował kwotę "
                "zmniejszającą podatek.",
                "Kwota zmniejszająca podatek to 300 zł miesięcznie. Można ją "
                "podzielić między maksymalnie trzech płatników (1/12, 1/24 albo "
                "1/36 kwoty rocznej).",
            ),
            (
                "Numer rachunku bankowego do wypłaty wynagrodzenia",
                "Pracownik podaje go w kwestionariuszu albo w osobnym oświadczeniu.",
                "Wynagrodzenie jest wypłacane na konto, chyba że pracownik "
                "złoży wniosek o wypłatę do rąk własnych.",
            ),
            (
                "Dane członków rodziny do ubezpieczenia zdrowotnego",
                "Imię, nazwisko, PESEL i stopień pokrewieństwa - podaje pracownik.",
                "Pracodawca zgłasza członków rodziny do ZUS na druku ZUS ZCNA w "
                "ciągu 7 dni od otrzymania informacji.",
            ),
            (
                "Uprawnienia i certyfikaty zawodowe",
                "Np. świadectwa kwalifikacyjne SEP, uprawnienia UDT, prawo jazdy - "
                "przedstawia pracownik.",
                "Tylko jeśli są wymagane na danym stanowisku.",
            ),
        ),
        tip=(
            "Pracodawca może poprosić o okazanie dowodu osobistego, żeby "
            "potwierdzić tożsamość, ale do akt nie potrzebuje jego kopii. Nie "
            "proś pracowników o skan dowodu mailem."
        ),
        faq=(
            (
                "Jakie dokumenty są potrzebne do zatrudnienia pracownika w 2026?",
                "Kwestionariusz osobowy, świadectwa pracy z bieżącego roku, "
                "dokumenty o wykształceniu, orzeczenie lekarskie z badań "
                "wstępnych, a dobrowolnie PIT-2 i dane członków rodziny do "
                "ubezpieczenia.",
            ),
            (
                "Kto płaci za badania wstępne?",
                "Pracodawca - wystawia skierowanie i pokrywa koszt badania u "
                "lekarza medycyny pracy.",
            ),
            (
                "Czy pracodawca może żądać kopii dowodu osobistego?",
                "Nie - może poprosić o okazanie dowodu, ale kopia nie jest "
                "potrzebna w aktach osobowych.",
            ),
            (
                "Jak zebrać dokumenty od nowego pracownika przed pierwszym dniem?",
                "Wysłać mu listę z terminem - pracownik przesyła dokumenty z "
                "telefonu, a przypomnienia o brakach wychodzą same.",
            ),
        ),
    ),
    "dokumenty-ksiegowe-za-miesiac": Guide(
        updated="2026-10-29",
        intro=(
            "Co miesiąc biuro rachunkowe potrzebuje od klienta kompletu "
            "dokumentów, żeby zdążyć z VAT, zaliczkami na podatek i ZUS. Od 2026 "
            "r. faktury krajowe trafiają do KSeF, więc lista się zmieniła - ale "
            "nie zniknęła: wyciągi, faktury spoza KSeF, raporty z kasy i umowy "
            "nadal przychodzą od klienta.",
            "Terminy są stałe: zaliczki na PIT i CIT oraz składki ZUS do 20. "
            "dnia miesiąca (spółki płacą ZUS do 15.), JPK_V7 i VAT do 25. "
            "Dlatego większość biur prosi o dokumenty do 10. dnia.",
        ),
        documents=(
            (
                "Wyciągi bankowe",
                "PDF z bankowości internetowej - ze wszystkich rachunków "
                "firmowych, za pełny miesiąc. Wiele programów księgowych "
                "przyjmuje też plik do importu (np. MT940).",
                "Wyciąg to podstawa do rozliczenia płatności i sprawdzenia, czy "
                "każda faktura została zapłacona.",
            ),
            (
                "Faktury kosztowe spoza KSeF",
                "Faktury od zagranicznych dostawców, faktury uproszczone i "
                "paragony z NIP, bilety.",
                "Faktur krajowych wystawionych w KSeF klient nie musi przesyłać - "
                "biuro pobiera je z KSeF samo, jeśli ma nadane uprawnienia.",
            ),
            (
                "Faktury sprzedaży spoza KSeF",
                "Np. faktury z kasy fiskalnej albo wystawione w trybie awaryjnym.",
                "Faktury wystawione w trybie awaryjnym trzeba później dosłać do "
                "KSeF - biuro sprawdzi, czy to się stało.",
            ),
            (
                "Raport miesięczny z kasy fiskalnej",
                "Drukuje go kasa albo pobierzesz go z kasy online.",
                "Potrzebny, jeśli firma sprzedaje osobom prywatnym na kasie.",
            ),
            (
                "Umowy zawarte w miesiącu",
                "Nowe albo zmienione umowy najmu, leasingu, pożyczki, zlecenia i "
                "o dzieło.",
                "Umowa zlecenia czy o dzieło to także składki albo podatek do "
                "rozliczenia - biuro musi o niej wiedzieć w miesiącu zawarcia.",
            ),
            (
                "Dokumenty importu i eksportu",
                "Zgłoszenia celne i dokumenty przewozowe (CMR).",
                "Potrzebne do rozliczenia importu, eksportu, WNT i WDT oraz "
                "stawki 0% VAT.",
            ),
            (
                "Ewidencja przebiegu pojazdu",
                "Prowadzi ją klient - kierowca zapisuje każdy wyjazd.",
                "Tylko jeśli firma odlicza 100% VAT od samochodu (wymaga to też "
                "zgłoszenia VAT-26).",
            ),
        ),
        tip=(
            "Najwygodniej wysłać tę listę jako prośbę cykliczną: wychodzi sama "
            "na początku każdego miesiąca z nazwą właściwego miesiąca, a klient "
            "dostaje przypomnienia, dopóki nie dośle kompletu."
        ),
        faq=(
            (
                "Do kiedy klient powinien dostarczyć dokumenty do biura rachunkowego?",
                "Najczęściej do 10. dnia następnego miesiąca - tak, żeby biuro "
                "zdążyło z zaliczkami i ZUS do 20. oraz z JPK_V7 do 25. Dokładny "
                "termin zapisuje się w umowie z biurem.",
            ),
            (
                "Czy po wejściu KSeF trzeba przesyłać faktury do biura?",
                "Faktur krajowych wystawionych w KSeF nie - biuro pobiera je z "
                "KSeF. Nadal trzeba przesyłać wyciągi, faktury zagraniczne, "
                "paragony z NIP, raporty z kasy i umowy.",
            ),
            (
                "Jak przypominać klientom o dokumentach bez dzwonienia?",
                "Wysłać listę z terminem i automatycznymi przypomnieniami - "
                "Monituj przypomina klientowi o brakach, a biuro widzi, kto ma "
                "już komplet.",
            ),
        ),
    ),
}


def get(slug):
    return GUIDES.get(slug)
