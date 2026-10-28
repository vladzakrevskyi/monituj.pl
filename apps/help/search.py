"""Search in the Centrum pomocy - for questions typed the way people ask
them: "jak wyslac fakture klientowi", without Polish letters, any word form.

Words are compared by their beginning, so "faktury", "fakturę" and "faktura"
find each other; a few synonyms bridge the words people use and the ones the
articles do."""

import re
import unicodedata
from functools import lru_cache

from apps.help.articles import ARTICLES, CATEGORY_BY_SLUG

RESULTS = 8

# Words that say nothing about the subject.
STOPWORDS = {
    "a",
    "aby",
    "albo",
    "ale",
    "bo",
    "by",
    "byc",
    "co",
    "czy",
    "dla",
    "do",
    "gdzie",
    "i",
    "ich",
    "jak",
    "jaki",
    "jakie",
    "jest",
    "jesli",
    "juz",
    "ktory",
    "ktora",
    "ktore",
    "lub",
    "ma",
    "mam",
    "moge",
    "moj",
    "moja",
    "moje",
    "mi",
    "mnie",
    "na",
    "nie",
    "o",
    "od",
    "po",
    "przez",
    "sie",
    "sa",
    "ta",
    "tak",
    "te",
    "ten",
    "to",
    "tu",
    "w",
    "we",
    "z",
    "za",
    "ze",
    "zeby",
    "moze",
    "mozna",
    "trzeba",
    "chce",
    "chcialbym",
    "chcialabym",
    "prosze",
}

# A word people use -> words the articles use.
SYNONYMS = {
    "plik": ["dokument"],
    "pliki": ["dokument"],
    "dokument": ["plik"],
    "zalacznik": ["plik", "dokument"],
    "monit": ["przypomnienie"],
    "ponaglenie": ["przypomnienie"],
    "odbiorca": ["klient"],
    "kontrahent": ["klient"],
    "pracownik": ["zespol", "wspolpracownik"],
    "wyslac": ["wyslij"],
    "skasowac": ["usunac"],
    "wykasowac": ["usunac"],
    "cena": ["plan", "kosztuje"],
    "koszt": ["plan", "kosztuje"],
    "abonament": ["plan", "subskrypcja"],
    "rachunek": ["faktura"],
    "login": ["logowanie", "zalogowac"],
    "komorka": ["telefon"],
    "smartfon": ["telefon"],
    "excel": ["import"],
    "termin": ["kalendarz"],
}

_NOT_DECOMPOSED = str.maketrans({"ł": "l", "Ł": "l"})


def normalize(text):
    """Lower case, no Polish letters, no punctuation."""
    text = (text or "").translate(_NOT_DECOMPOSED).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _stem(word):
    """The part that stays across Polish word forms."""
    if len(word) <= 4:
        return word
    return word[: max(4, len(word) - 2)]


def query_terms(query):
    """[(stem, alternative stems)] for the words that matter."""
    terms = []
    for word in normalize(query).split():
        if word in STOPWORDS or len(word) < 2:
            continue
        alternatives = {_stem(word)}
        alternatives.update(_stem(normalize(s)) for s in SYNONYMS.get(word, []))
        terms.append(alternatives)
    return terms[:8]


def _plain(text):
    """Without the article markup."""
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).replace("-", " "), text)
    return text.replace("**", "")


@lru_cache(maxsize=1)
def _index():
    """Each article's words by where they are: title counts most."""
    index = []
    for article in ARTICLES:
        category = CATEGORY_BY_SLUG[article.category]
        fields = {
            "title": article.title,
            "keywords": f"{article.keywords} {category.title}",
            "summary": _plain(article.summary),
            "text": _plain(" ".join([*article.steps, *article.body, *article.tips])),
        }
        words = {name: set(normalize(text).split()) for name, text in fields.items()}
        # The whole question, word for word, in the title or the keywords.
        phrases = f" {normalize(fields['title'])} {normalize(fields['keywords'])} "
        index.append((article, words, phrases))
    return index


WEIGHTS = {"title": 6, "keywords": 4, "summary": 3, "text": 1}


def _matches(words, alternatives):
    return any(word.startswith(stem) for word in words for stem in alternatives)


def search(query, limit=RESULTS):
    """The articles that best answer the question, best first."""
    terms = query_terms(query)
    if not terms:
        return []
    phrase = f" {normalize(query)} "
    scored = []
    for article, fields, phrases in _index():
        score, matched = 0, 0
        for alternatives in terms:
            best = max(
                (
                    weight
                    for name, weight in WEIGHTS.items()
                    if _matches(fields[name], alternatives)
                ),
                default=0,
            )
            score += best
            matched += bool(best)
        if not matched:
            continue
        # An article that has every word beats one that has a few.
        score *= matched / len(terms)
        if matched == len(terms):
            score += 5
        if len(phrase.split()) > 1 and phrase in phrases:
            score += 15
        scored.append((score, article))
    scored.sort(key=lambda pair: -pair[0])
    return [article for _, article in scored[:limit]]
