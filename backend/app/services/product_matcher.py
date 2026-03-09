"""Product deduplication service.

Uses fuzzy matching (rapidfuzz) to identify and merge duplicate product
entries coming from different flyers, chains and OCR extractions.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Product

logger = logging.getLogger(__name__)


def is_valid_ean(code: str | None) -> bool:
    """Check if a string looks like a valid EAN-8 or EAN-13."""
    return bool(code and code.isdigit() and len(code) in (8, 13))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 85  # similarity >= 85 % ⇒ treat as the same product
BRAND_MATCH_THRESHOLD = 85  # threshold when brands match exactly

# ---------------------------------------------------------------------------
# Italian plural → singular stemming map (grocery nouns)
# ---------------------------------------------------------------------------
_ITALIAN_STEM_MAP: dict[str, str] = {
    # -chi / -che → -co / -ca
    "finocchi": "finocchio", "carciofi": "carciofo", "pistacchi": "pistacchio",
    "ravanelli": "ravanello", "broccoli": "broccolo", "fagioli": "fagiolo",
    "fagiolini": "fagiolino", "piselli": "pisello",
    # -i → -o (masc)
    "pomodori": "pomodoro", "biscotti": "biscotto", "grissini": "grissino",
    "cracker": "cracker", "cornetti": "cornetto", "croissant": "croissant",
    "wurstel": "wurstel", "würstel": "wurstel",
    "tortellini": "tortellino", "ravioli": "raviolo", "cannelloni": "cannellone",
    "rigatoni": "rigatone", "fusilli": "fusillo", "maccheroni": "maccherone",
    "paccheri": "pacchero", "bucatini": "bucatino", "cappelletti": "cappelletto",
    "panini": "panino", "taralli": "tarallo", "salatini": "salatino",
    "rotoloni": "rotolone", "tovaglioli": "tovagliolo", "fazzoletti": "fazzoletto",
    "pannolini": "pannolino",
    # -e → -a (fem)
    "zucchine": "zucchina", "melanzane": "melanzana", "banane": "banana",
    "mele": "mela", "pere": "pera", "arance": "arancia", "fragole": "fragola",
    "pesche": "pesca", "ciliegie": "ciliegia", "albicocche": "albicocca",
    "cipolle": "cipolla", "carote": "carota", "patate": "patata",
    "olive": "oliva", "sardine": "sardina", "acciughe": "acciuga",
    "vongole": "vongola", "cozze": "cozza",
    "merendine": "merendina", "caramelle": "caramella",
    "fettine": "fettina", "polpette": "polpetta",
    "salsicce": "salsiccia", "bistecche": "bistecca",
    "uova": "uovo",
    # -i → -e (fem plural)
    "lasagne": "lasagna", "penne": "penna", "farfalle": "farfalla",
    "tagliatelle": "tagliatella", "orecchiette": "orecchietta",
    "linguine": "linguina", "fettuccine": "fettuccina",
    # irregular / invariable
    "funghi": "fungo", "limoni": "limone", "peperoni": "peperone",
    "spinaci": "spinacio", "ceci": "cece", "lenticchie": "lenticchia",
    "mandorle": "mandorla", "noci": "noce", "nocciole": "nocciola",
    "arachidi": "arachide", "gamberetti": "gamberetto", "gamberi": "gambero",
    "calamari": "calamaro",
}

# ---------------------------------------------------------------------------
# Abbreviation expansion map (token-level, keys are lowercase)
# ---------------------------------------------------------------------------
_ABBREVIATION_MAP: dict[str, str] = {
    "parz.": "parzialmente", "parz": "parzialmente",
    "screm.": "scremato", "screm": "scremato",
    "surg.": "surgelato", "surg": "surgelato",
    "conf.": "confezionato",
    "bio": "biologico",
    "aut.": "autunnale",
    "det.": "detersivo",
    "ammorb.": "ammorbidente",
    "dec.": "decaffeinato",
    "int.": "integrale",
    "orig.": "originale",
    "class.": "classico",
    # Receipt-specific abbreviations
    "yog.": "yogurt", "yog": "yogurt",
    "mozz.": "mozzarella", "mozz": "mozzarella",
    "prosc.": "prosciutto", "prosc": "prosciutto",
    "form.": "formaggio", "form": "formaggio",
    "bisc.": "biscotti", "bisc": "biscotti",
    "sacc.": "sacchetto",
    "compost.": "compostabile",
    "buf.": "bufala", "buf": "bufala",
    "camp.": "campana", "camp": "campana",
    "fres.": "fresco", "fres": "fresco",
    "pol.": "pollo", "pol": "pollo",
    "tac.": "tacchino", "tac": "tacchino",
    "sug.": "sugo", "sug": "sugo",
    "marg.": "margherita", "marg": "margherita",
    "ins.": "insalata", "ins": "insalata",
    "lat.": "latte", "lat": "latte",
    "pan.": "pane", "pan": "pane",
    "bev.": "bevanda", "bev": "bevanda",
    "acq.": "acqua", "acq": "acqua",
    "nat.": "naturale", "nat": "naturale",
    "friz.": "frizzante", "friz": "frizzante",
    "cap.": "capelli",
    "bag.": "bagnoschiuma", "bag": "bagnoschiuma",
    "dent.": "dentifricio", "dent": "dentifricio",
    "cart.": "carta",
    "mul.": "muller", "mul": "muller",
    "dan.": "danone", "dan": "danone",
    "grec.": "greco", "grec": "greco",
    "mag.": "magro", "mag": "magro",
    "med.": "medio",
    "pic.": "piccolo",
    "gra.": "grande",
    "riso.": "risotto",
    "past.": "pasta",
    "tom.": "pomodoro",
    "lav.": "lavaggio",
    "conc.": "concentrato",
    "prec.": "precotto",
    "affet.": "affettato", "affet": "affettato",
    "cot.": "cotto", "cot": "cotto",
    "crud.": "crudo", "crud": "crudo",
}

# Multi-token abbreviation expansions (applied before tokenizing)
_MULTI_TOKEN_ABBREVS: dict[str, str] = {
    "s/glutine": "senza glutine",
    "s/lattosio": "senza lattosio",
    "p.s.": "parzialmente scremato",
    "a.q.": "alta qualita",
    "o.v.": "olio vergine",
    "e.v.": "extra vergine",
}

# ---------------------------------------------------------------------------
# Private-label prefixes (chain own-brand product lines)
# ---------------------------------------------------------------------------
PRIVATE_LABEL_PREFIXES: list[str] = [
    # Esselunga
    "esselunga bio", "esselunga naturama", "esselunga top",
    "esselunga equilibrio", "esselunga",
    # Coop
    "coop vivi verde", "coop origine", "coop fior fiore",
    "coop bene si", "coop solidal", "coop crescendo", "coop",
    # Lidl
    "milbona", "italiamo", "combino", "cien", "freeway",
    "solevita", "favorina", "deluxe",
    # Iperal
    "via verde bio", "primia", "vale",
]

# Italian food-variant words that DISTINGUISH products (not stopwords).
# If these appear only in one name, the products are likely different.
_VARIANT_WORDS: set[str] = {
    # Flavors / ingredients
    "basilico", "limone", "arancia", "fragola", "vaniglia", "cioccolato",
    "pistacchio", "nocciola", "caffè", "caffe", "menta", "pesca",
    "frutti", "bosco", "miele", "zenzero", "aglio", "peperoncino",
    "pomodoro", "funghi", "tartufo", "olive", "capperi", "tonno",
    "prosciutto", "salmone", "formaggio", "mozzarella",
    # Variants
    "bio", "integrale", "integrali", "classico", "classica",
    "originale", "light", "zero", "senza", "glutine",
    "decaffeinato", "decaf",
    # Private-label product lines
    "top", "smart", "naturama", "premium", "selection",
    # Milk / dairy specifics
    "montagna", "parzialmente", "scremato",
    # Sizes / quantities that matter
    "mini", "maxi", "grande", "piccolo", "famiglia",
}

# Italian stopwords commonly seen in product names on flyers
_STOPWORDS: set[str] = {
    "di", "del", "della", "delle", "dei", "degli", "da", "al", "alla",
    "alle", "il", "lo", "la", "le", "gli", "i", "un", "una", "uno",
    "con", "per", "in", "su", "tra", "fra", "e", "o", "ed",
}

# Unit normalisation map  (raw form -> canonical)
_UNIT_MAP: dict[str, str] = {
    "grammi": "g",
    "gr": "g",
    "gr.": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilogrammi": "kg",
    "litri": "l",
    "litro": "l",
    "lt": "l",
    "lt.": "l",
    "ml": "ml",
    "millilitri": "ml",
    "cl": "cl",
    "centilitri": "cl",
    "pezzi": "pz",
    "pz": "pz",
    "pz.": "pz",
    "conf": "conf",
    "conf.": "conf",
    "confezione": "conf",
    "confezioni": "conf",
    "rotoli": "rotoli",
    "rotolo": "rotoli",
    "capsule": "caps",
    "caps": "caps",
}

# Common Italian supermarket brand aliases (lowercase variant -> canonical)
BRAND_ALIASES: dict[str, str] = {
    # Pasta & bakery
    "mulino bianco": "Mulino Bianco",
    "mulinobianco": "Mulino Bianco",
    "barilla": "Barilla",
    "de cecco": "De Cecco",
    "divella": "Divella",
    "voiello": "Voiello",
    "rummo": "Rummo",
    "garofalo": "Garofalo",
    "la molisana": "La Molisana",
    "agnesi": "Agnesi",
    "buitoni": "Buitoni",
    "giovanni rana": "Giovanni Rana",
    "rana": "Giovanni Rana",
    # Dairy & cheese
    "galbani": "Galbani",
    "parmalat": "Parmalat",
    "granarolo": "Granarolo",
    "muller": "Muller",
    "müller": "Muller",
    "danone": "Danone",
    "yomo": "Yomo",
    "philadelphia": "Philadelphia",
    "president": "Président",
    "président": "Président",
    "kraft": "Kraft",
    "vallelata": "Vallelata",
    "nonno nanni": "Nonno Nanni",
    "santa lucia": "Santa Lucia",
    # Meat & deli
    "amadori": "Amadori",
    "aia": "Aia",
    "beretta": "Beretta",
    "rovagnati": "Rovagnati",
    "negroni": "Negroni",
    "fiorucci": "Fiorucci",
    "citterio": "Citterio",
    # Canned & preserves
    "rio mare": "Rio Mare",
    "rio-mare": "Rio Mare",
    "star": "Star",
    "cirio": "Cirio",
    "mutti": "Mutti",
    "valfrutta": "Valfrutta",
    "de rica": "De Rica",
    "pomì": "Pomi",
    "pomi": "Pomi",
    # Beverages
    "cocacola": "Coca-Cola",
    "coca cola": "Coca-Cola",
    "coca-cola": "Coca-Cola",
    "pepsi": "Pepsi",
    "san benedetto": "San Benedetto",
    "san pellegrino": "San Pellegrino",
    "sanpellegrino": "San Pellegrino",
    "levissima": "Levissima",
    "sant'anna": "Sant'Anna",
    "sant anna": "Sant'Anna",
    "yoga": "Yoga",
    "santal": "Santal",
    "schweppes": "Schweppes",
    "fanta": "Fanta",
    "sprite": "Sprite",
    # Coffee & tea
    "lavazza": "Lavazza",
    "illy": "Illy",
    "kimbo": "Kimbo",
    "borbone": "Borbone",
    "nescafé": "Nescafe",
    "nescafe": "Nescafe",
    "bialetti": "Bialetti",
    # Snacks & sweets
    "ferrero": "Ferrero",
    "nutella": "Ferrero",
    "kinder": "Kinder",
    "loacker": "Loacker",
    "pavesi": "Pavesi",
    "pan di stelle": "Pan di Stelle",
    "oro saiwa": "Oro Saiwa",
    "ringo": "Ringo",
    # Condiments & oils
    "barilla pesto": "Barilla",
    "knorr": "Knorr",
    "calvé": "Calve",
    "calve": "Calve",
    "de nigris": "De Nigris",
    "monini": "Monini",
    "carapelli": "Carapelli",
    "bertolli": "Bertolli",
    "farchioni": "Farchioni",
    # Frozen
    "findus": "Findus",
    "4 salti in padella": "Findus",
    "orogel": "Orogel",
    "birdseye": "Birds Eye",
    # Hygiene & cleaning
    "scottex": "Scottex",
    "regina": "Regina",
    "dash": "Dash",
    "dixan": "Dixan",
    "ace": "ACE",
    "napisan": "Napisan",
    "swiffer": "Swiffer",
    "fairy": "Fairy",
    "finish": "Finish",
    "dove": "Dove",
    "pantene": "Pantene",
    "garnier": "Garnier",
    "colgate": "Colgate",
    "oral-b": "Oral-B",
    "oral b": "Oral-B",
    "neutromed": "Neutromed",
    "borotalco": "Borotalco",
    "viakal": "Viakal",
    "lysoform": "Lysoform",
    # Baby & pet
    "pampers": "Pampers",
    "huggies": "Huggies",
    "mellin": "Mellin",
    "plasmon": "Plasmon",
    "whiskas": "Whiskas",
    "felix": "Felix",
    "sheba": "Sheba",
    "purina": "Purina",
    # Private labels
    "esselunga": "Esselunga",
    "iperal": "Iperal",
}

# Compound brands where the sub-brand is more specific than the parent.
# "parent sub" → "Sub" (canonical sub-brand)
COMPOUND_BRANDS: dict[str, str] = {
    "barilla mulino bianco": "Mulino Bianco",
    "barilla pavesi": "Pavesi",
    "barilla pan di stelle": "Pan di Stelle",
    "barilla ringo": "Ringo",
    "barilla wasa": "Wasa",
    "ferrero kinder": "Kinder",
    "ferrero nutella": "Nutella",
    "ferrero rocher": "Ferrero Rocher",
    "kraft philadelphia": "Philadelphia",
    "mondelez oreo": "Oreo",
    "unilever knorr": "Knorr",
    "unilever dove": "Dove",
    "p&g dash": "Dash",
    "p&g fairy": "Fairy",
    "p&g swiffer": "Swiffer",
    "nestle nescafe": "Nescafe",
    "nestlé nescafé": "Nescafe",
}

# ---------------------------------------------------------------------------
# Category keyword mapping (name tokens → category)
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Pasta e Riso": [
        "penne", "spaghetti", "fusilli", "rigatoni", "farfalle", "linguine",
        "pasta", "lasagne", "gnocchi", "tagliatelle", "maccheroni", "bucatini",
        "paccheri", "orecchiette", "tortellini", "ravioli", "riso", "risotto",
        "arborio", "basmati", "carnaroli",
    ],
    "Bevande": [
        "birra", "succo", "cola", "aranciata", "energy", "drink", "sprite",
        "fanta", "schweppes", "gassosa", "chinotto", "limonata", "the freddo",
        "te freddo", "acqua",
    ],
    "Latticini": [
        "latte", "yogurt", "panna", "burro", "ricotta", "mascarpone",
        "kefir", "skyr", "uova", "stracchino",
    ],
    "Salumi e Formaggi": [
        "parmigiano", "mozzarella", "gorgonzola", "provolone", "pecorino",
        "formaggio", "stracchino", "emmental", "edamer", "grana padano",
        "asiago", "fontina", "taleggio", "brie", "camembert",
        "prosciutto", "salame", "mortadella", "bresaola", "speck",
        "coppa", "pancetta", "guanciale", "wurstel", "würstel",
    ],
    "Pane e Cereali": [
        "pane", "grissini", "cracker", "fette biscottate", "focaccia",
        "cereali", "muesli", "corn flakes", "gallette", "pancarré",
        "piadina", "wrap",
    ],
    "Carne": [
        "pollo", "manzo", "maiale", "vitello", "tacchino", "hamburger",
        "salsiccia", "agnello", "coniglio", "scottona", "fettine",
        "arrosto", "bistecca", "carpaccio", "polpette",
        "bresaola", "cotoletta", "spiedini",
    ],
    "Pesce": [
        "salmone", "merluzzo", "gamberi", "pesce", "orata", "branzino",
        "vongole", "cozze", "calamari", "polpo", "tonno fresco",
        "trota", "sogliola", "platessa",
    ],
    "Frutta e Verdura": [
        "mele", "banane", "arance", "fragole", "uva", "pere", "kiwi",
        "ananas", "limoni", "pesche", "albicocche", "ciliegie",
        "insalata", "pomodori", "zucchine", "carote", "patate", "cipolla",
        "melanzane", "peperoni", "broccoli", "cavolfiore", "spinaci",
        "rucola", "lattuga", "finocchi", "carciofi", "funghi",
    ],
    "Surgelati": [
        "surgelat", "frozen", "4 salti", "sofficini", "bastoncini",
        "pizza surgelata", "gelato", "ghiacciolo",
    ],
    "Dolci e Snack": [
        "cioccolat", "torta", "biscott", "merendina", "nutella", "wafer",
        "crostata", "croissant", "brioche", "plumcake", "muffin",
        "patatine", "pop corn", "taralli", "salatini", "snack",
        "caramelle", "chewing gum", "gomme",
        "cioccolatini", "praline", "panettone", "pandoro", "colomba",
    ],
    "Caffe e Te": [
        "caffè", "caffe", "espresso", "capsule caffè", "capsule caffe",
        "cialde", "te ", "tè ", "tisana", "camomilla", "infuso",
    ],
    "Condimenti e Conserve": [
        "pelati", "passata", "sugo", "conserva", "pesto", "ragù", "ragu",
        "olio", "aceto", "sale fino", "sale grosso", "pepe",
        "maionese", "ketchup", "senape", "salsa", "dado",
        "tonno", "legumi", "marmellata", "confettura", "miele",
    ],
    "Igiene Personale": [
        "shampoo", "bagnodoccia", "bagnoschiuma", "dentifricio",
        "deodorante", "sapone mani", "crema viso", "crema corpo",
        "rasoio", "assorbent", "salvaslip", "cotton fioc",
        "gel doccia", "schiuma", "salviette",
    ],
    "Pulizia Casa": [
        "detersivo", "ammorbidente", "candeggina", "sgrassatore", "spugna",
        "carta igienica", "tovaglioli", "pellicola", "alluminio",
        "sacchetti spazzatura", "anticalcare",
        "sacchetti", "panno", "rotolone", "fazzoletti",
    ],
    "Alcolici": [
        "vino rosso", "vino bianco", "prosecco", "spumante", "champagne",
        "grappa", "amaro", "limoncello", "vodka", "gin", "rum", "whisky",
    ],
    "Neonati e Infanzia": [
        "pannolini", "latte crescita", "omogenizzat", "pastina bimbi",
    ],
    "Pet Care": [
        "cibo gatti", "cibo cani", "croccantini", "umido gatto",
        "umido cane", "lettiera",
    ],
}

# Brand → likely category (used as fallback when keyword matching fails)
BRAND_TO_CATEGORY: dict[str, str] = {
    "Barilla": "Pasta e Riso",
    "De Cecco": "Pasta e Riso",
    "Divella": "Pasta e Riso",
    "Voiello": "Pasta e Riso",
    "Rummo": "Pasta e Riso",
    "Garofalo": "Pasta e Riso",
    "La Molisana": "Pasta e Riso",
    "Agnesi": "Pasta e Riso",
    "Giovanni Rana": "Pasta e Riso",
    "Lavazza": "Caffe e Te",
    "Illy": "Caffe e Te",
    "Kimbo": "Caffe e Te",
    "Borbone": "Caffe e Te",
    "Nescafe": "Caffe e Te",
    "Granarolo": "Latticini",
    "Parmalat": "Latticini",
    "Muller": "Latticini",
    "Danone": "Latticini",
    "Yomo": "Latticini",
    "Galbani": "Salumi e Formaggi",
    "Philadelphia": "Salumi e Formaggi",
    "Nonno Nanni": "Salumi e Formaggi",
    "Beretta": "Salumi e Formaggi",
    "Rovagnati": "Salumi e Formaggi",
    "Negroni": "Salumi e Formaggi",
    "Citterio": "Salumi e Formaggi",
    "Coca-Cola": "Bevande",
    "Pepsi": "Bevande",
    "Fanta": "Bevande",
    "Sprite": "Bevande",
    "Schweppes": "Bevande",
    "San Benedetto": "Bevande",
    "Yoga": "Bevande",
    "Santal": "Bevande",
    "Levissima": "Acqua",
    "San Pellegrino": "Acqua",
    "Sant'Anna": "Acqua",
    "Findus": "Surgelati",
    "Orogel": "Surgelati",
    "Amadori": "Carne",
    "Aia": "Carne",
    "Rio Mare": "Pesce",
    "Mulino Bianco": "Dolci e Snack",
    "Pavesi": "Dolci e Snack",
    "Kinder": "Dolci e Snack",
    "Loacker": "Dolci e Snack",
    "Cirio": "Condimenti e Conserve",
    "Mutti": "Condimenti e Conserve",
    "Valfrutta": "Condimenti e Conserve",
    "Pomi": "Condimenti e Conserve",
    "Knorr": "Condimenti e Conserve",
    "Star": "Condimenti e Conserve",
    "Monini": "Condimenti e Conserve",
    "Carapelli": "Condimenti e Conserve",
    "Bertolli": "Condimenti e Conserve",
    "Dash": "Pulizia Casa",
    "Dixan": "Pulizia Casa",
    "ACE": "Pulizia Casa",
    "Fairy": "Pulizia Casa",
    "Finish": "Pulizia Casa",
    "Swiffer": "Pulizia Casa",
    "Scottex": "Pulizia Casa",
    "Regina": "Pulizia Casa",
    "Dove": "Igiene Personale",
    "Pantene": "Igiene Personale",
    "Garnier": "Igiene Personale",
    "Colgate": "Igiene Personale",
    "Oral-B": "Igiene Personale",
    "Neutromed": "Igiene Personale",
    "Borotalco": "Igiene Personale",
    "Pampers": "Neonati e Infanzia",
    "Plasmon": "Neonati e Infanzia",
    "Mellin": "Neonati e Infanzia",
    "Whiskas": "Pet Care",
    "Felix": "Pet Care",
    "Sheba": "Pet Care",
    "Purina": "Pet Care",
}

# Private-label brand names (chain own-brands)
PRIVATE_LABELS: set[str] = {"Esselunga", "Iperal", "Coop", "Lidl"}


class ProductMatcher:
    """Finds existing products by fuzzy-matching or creates new ones."""

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stem_italian(token: str) -> str:
        """Return singular form of an Italian grocery noun, or the token itself."""
        return _ITALIAN_STEM_MAP.get(token, token)

    @staticmethod
    def _expand_abbreviations(text: str) -> str:
        """Expand common Italian grocery abbreviations in text.

        Handles multi-token abbreviations first (e.g. "s/glutine" → "senza glutine"),
        then single-token abbreviations are handled per-token in normalize_text().
        """
        lower = text.lower()
        for abbrev, expansion in _MULTI_TOKEN_ABBREVS.items():
            if abbrev in lower:
                # Case-insensitive replacement
                idx = lower.find(abbrev)
                text = text[:idx] + expansion + text[idx + len(abbrev):]
                lower = text.lower()
        return text

    @staticmethod
    def _strip_private_label(name: str) -> str:
        """Remove private-label prefixes from a product name."""
        name_lower = name.lower().strip()
        for prefix in PRIVATE_LABEL_PREFIXES:
            if name_lower.startswith(prefix):
                rest = name[len(prefix):].lstrip(" ,-–")
                if rest and len(rest) >= 3:
                    return rest
        return name

    @staticmethod
    def normalize_text(text: str) -> str:
        """Lowercase, strip accents, expand abbreviations, stem Italian plurals,
        remove stopwords and normalise units."""
        if not text:
            return ""

        text = text.lower().strip()

        # Expand multi-token abbreviations first
        text = ProductMatcher._expand_abbreviations(text)

        # Collapse multiple spaces / tabs
        text = re.sub(r"\s+", " ", text)

        # Normalise units, expand single-token abbreviations, stem Italian, remove stopwords
        tokens: list[str] = []
        for token in text.split():
            # Check single-token abbreviation first
            expanded = _ABBREVIATION_MAP.get(token)
            if expanded:
                token = expanded
            canonical = _UNIT_MAP.get(token)
            if canonical:
                tokens.append(canonical)
            elif token not in _STOPWORDS:
                tokens.append(ProductMatcher._stem_italian(token))

        return " ".join(tokens)

    @staticmethod
    def _strip_brand(name: str, brand: str | None) -> str:
        """Remove brand name from the beginning of a product name.

        Esselunga embeds brand in the name (e.g. "Granarolo Latte Intero UHT
        1 L") while Iperal keeps brand separate.  Stripping it before matching
        greatly improves cross-source dedup.
        """
        if not brand or not name:
            return name
        name_lower = name.lower()
        brand_lower = brand.lower().strip()

        # Build brand variants: original + hyphen/space swapped
        brand_variants = {brand_lower}
        brand_variants.add(brand_lower.replace("-", " "))
        brand_variants.add(brand_lower.replace(" ", "-"))

        # Strip brand at beginning of name (possibly followed by comma/dash)
        for bv in brand_variants:
            for sep in ["", ",", " -", " –"]:
                prefix = bv + sep
                if name_lower.startswith(prefix):
                    cleaned = name[len(prefix):].lstrip(" ,.-–")
                    if cleaned:
                        return cleaned
        return name

    @staticmethod
    def _strip_units(text: str) -> str:
        """Remove unit/weight/volume patterns from text for cleaner matching.

        Strips patterns like '500g', '1 L', '1000 ml', '1,5 kg', '6 x 1,5 l'.
        """
        # Remove multi-pack patterns: "6 x 1,5 l", "4x500 ml"
        text = re.sub(
            r"\b\d+\s*x\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l)\b",
            "", text, flags=re.IGNORECASE,
        )
        # Remove simple unit patterns: "500g", "1 L", "1000 ml", "1,5 kg"
        text = re.sub(
            r"\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pz|pezzi|conf)\b",
            "", text, flags=re.IGNORECASE,
        )
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def extract_brand_from_name(raw_name: str) -> tuple[str | None, str]:
        """Split ``"Brand - Product Name"`` into (brand, product_name).

        Tiendeo and other sources format names as ``"Barilla - Penne Rigate 500g"``.
        Returns ``(None, raw_name)`` when no separator is found.
        """
        if not raw_name:
            return None, raw_name

        # Pattern: "Brand - Product" (with surrounding spaces around the dash)
        if " - " in raw_name:
            parts = raw_name.split(" - ", 1)
            brand_candidate = parts[0].strip()
            product_name = parts[1].strip()
            # Only treat as brand if the left part is short-ish (≤ 4 words)
            if brand_candidate and len(brand_candidate.split()) <= 4 and product_name:
                return brand_candidate, product_name

        return None, raw_name.strip()

    @staticmethod
    def normalize_brand(brand: str | None) -> str | None:
        """Return canonical brand name or the original (title-cased).

        Also resolves compound brands (e.g. "Barilla Mulino Bianco" → "Mulino Bianco").
        Treats "Null"/"null"/empty as None.
        """
        if not brand:
            return None
        stripped = brand.strip()
        if stripped.lower() in ("null", "none", ""):
            return None
        key = stripped.lower()
        # Check compound brands first
        compound = COMPOUND_BRANDS.get(key)
        if compound:
            return compound
        return BRAND_ALIASES.get(key, stripped.title())

    # ------------------------------------------------------------------
    # New harmonisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_brand_from_product_name(name: str) -> str | None:
        """Try to identify a brand from the first words of a product name.

        Checks 1-word, 2-word and 3-word prefixes against BRAND_ALIASES.
        Returns the canonical brand or None.
        """
        if not name:
            return None
        words = name.strip().split()
        # Try longest prefix first (3 words, 2 words, 1 word)
        for n in (3, 2, 1):
            if len(words) >= n:
                candidate = " ".join(words[:n]).lower()
                if candidate in BRAND_ALIASES:
                    return BRAND_ALIASES[candidate]
        return None

    @staticmethod
    def categorize_by_keywords(name: str, brand: str | None = None) -> str | None:
        """Return a category based on keyword matching in name (and optionally brand).

        Checks multi-word keywords first, then single-word. Returns None if no match.
        Falls back to BRAND_TO_CATEGORY if keyword matching fails.
        """
        if not name:
            return None
        text = name.lower()

        # Try keyword matching (prefer longer keywords first for specificity)
        best_category = None
        best_keyword_len = 0
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text and len(kw) > best_keyword_len:
                    best_category = category
                    best_keyword_len = len(kw)

        if best_category:
            return best_category

        # Fallback: use brand → category hint
        if brand:
            canonical = BRAND_ALIASES.get(brand.lower().strip(), brand.strip().title())
            return BRAND_TO_CATEGORY.get(canonical)

        return None

    @staticmethod
    def clean_product_name(
        name: str,
        brand: str | None = None,
        *,
        strip_brand: bool = False,
    ) -> str:
        """Clean a product name: normalise units, title-case.

        Steps:
          1. Optionally strip brand from beginning of name
          2. Normalise unit formats ("500 G" → "500g", "1,5 L" → "1.5l")
          3. Title-case with Italian preposition exceptions
          4. Clean up whitespace and punctuation

        By default the brand is NOT stripped from the saved name — the brand
        prefix is only removed internally for fuzzy-match scoring.
        """
        if not name:
            return name

        # 1. Optionally strip brand prefix
        if strip_brand:
            cleaned = ProductMatcher._strip_brand(name, brand)
        else:
            cleaned = name

        # 2. Normalise unit patterns in the name
        # "500 G" → "500g", "1,5 L" → "1.5l", "1000 ML" → "1000ml"
        def _norm_unit(m: re.Match) -> str:
            num = m.group(1).replace(",", ".")
            unit = m.group(2).lower()
            return f"{num}{unit}"

        cleaned = re.sub(
            r"(\d+(?:[.,]\d+)?)\s+(g|kg|ml|cl|l)\b",
            _norm_unit,
            cleaned,
            flags=re.IGNORECASE,
        )

        # 3. Normalise multi-pack: "6 X 1,5 L" → "6x1.5l"
        def _norm_multipack(m: re.Match) -> str:
            count = m.group(1)
            num = m.group(2).replace(",", ".")
            unit = m.group(3).lower()
            return f"{count}x{num}{unit}"

        cleaned = re.sub(
            r"(\d+)\s*[Xx]\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|cl|l)\b",
            _norm_multipack,
            cleaned,
        )

        # 4. Clean whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 5. Title-case with Italian preposition exceptions
        _lowercase_words = {
            "di", "del", "della", "delle", "dei", "degli", "da", "al", "alla",
            "alle", "il", "lo", "la", "le", "gli", "i", "un", "una", "uno",
            "con", "per", "in", "su", "tra", "fra", "e", "o", "ed", "n.",
        }
        words = cleaned.split()
        result = []
        for idx, word in enumerate(words):
            # Skip unit-like tokens (e.g. "500g", "1.5l")
            if re.match(r"^\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?(?:g|kg|ml|cl|l|pz)$", word, re.IGNORECASE):
                result.append(word.lower())
            elif idx == 0:
                # Always capitalise first word
                result.append(word.capitalize())
            elif word.lower() in _lowercase_words:
                result.append(word.lower())
            else:
                result.append(word.capitalize())

        return " ".join(result)

    # ------------------------------------------------------------------
    # Fuzzy matching
    # ------------------------------------------------------------------

    @staticmethod
    def fuzzy_match(
        name1: str,
        name2: str,
        brand1: str | None = None,
        brand2: str | None = None,
    ) -> float:
        """Return a similarity score (0-100) for two product names.

        When both brands are known and match, strip the brand from names and
        use ``token_set_ratio`` (robust to one name being a subset of the
        other, e.g. "Latte Intero" ⊂ "Latte Intero UHT a Lunga Conservazione").

        Otherwise fall back to ``token_sort_ratio`` which handles word-order
        differences common in OCR output.
        """
        # Clean names: strip private labels, brand and unit patterns
        c1 = ProductMatcher._strip_units(ProductMatcher._strip_brand(
            ProductMatcher._strip_private_label(name1), brand1))
        c2 = ProductMatcher._strip_units(ProductMatcher._strip_brand(
            ProductMatcher._strip_private_label(name2), brand2))

        n1 = ProductMatcher.normalize_text(c1)
        n2 = ProductMatcher.normalize_text(c2)
        if not n1 or not n2:
            return 0.0

        cb1 = ProductMatcher.normalize_brand(brand1) if brand1 else None
        cb2 = ProductMatcher.normalize_brand(brand2) if brand2 else None
        brands_match = cb1 and cb2 and cb1 == cb2
        brands_conflict = cb1 and cb2 and cb1 != cb2

        sort_score = fuzz.token_sort_ratio(n1, n2)

        # When brands are explicitly different, cap score to prevent false
        # merges of generic names (e.g. "Acqua Naturale" from two brands)
        if brands_conflict:
            return min(sort_score, 70.0)

        if brands_match:
            set_score = fuzz.token_set_ratio(n1, n2)

            t1 = set(n1.split())
            t2 = set(n2.split())

            # Guard against overly-generic short names (< 2 significant tokens)
            shorter = n1 if len(n1) < len(n2) else n2
            longer = n2 if len(n1) < len(n2) else n1
            sig_tokens = [t for t in shorter.split() if len(t) > 2]
            if len(sig_tokens) < 2:
                # Too short to trust token_set_ratio alone — dampen it
                set_score = min(set_score, sort_score + 15)

            # Guard against subset matches where the shorter name covers
            # less than 55% of the longer name.
            # e.g. "Latte Fresco" (12 ch) vs "Latte Fresco Intero 100%
            # Italiano Alta Qualità" (42 ch) → ratio 0.28 → different products
            len_ratio = len(shorter) / len(longer) if longer else 1.0
            if len_ratio < 0.55:
                set_score = min(set_score, sort_score)

            # Guard against generic overlap: if the shorter name's
            # product-identifying tokens (alphabetic, len>3) have low
            # overlap with the other name, token_set_ratio is misleading.
            # e.g. "latte 100% italiano" vs "olio extra vergine oliva 100%
            # italiano" share generic tokens but are different products.
            shorter_tokens = t1 if len(n1) < len(n2) else t2
            longer_tokens = t2 if len(n1) < len(n2) else t1
            product_tokens = [
                t for t in shorter_tokens if len(t) > 3 and t.isalpha()
            ]
            if product_tokens:
                overlap = sum(1 for t in product_tokens if t in longer_tokens)
                overlap_ratio = overlap / len(product_tokens)
                if overlap_ratio <= 0.5:
                    # Half or fewer product-identifying tokens match —
                    # these are different products sharing generic words
                    set_score = min(set_score, sort_score + 10)

            # Penalize when one name has variant-distinguishing words
            # that the other doesn't (e.g. "basilico", "integrale", "bio").
            # Use stems (first 6 chars) so "integrale"/"integrali" are
            # treated as the same variant, not different ones.
            diff1 = t1 - t2  # tokens only in name1
            diff2 = t2 - t1  # tokens only in name2
            var1_stems = {w[:6] for w in diff1 if w in _VARIANT_WORDS}
            var2_stems = {w[:6] for w in diff2 if w in _VARIANT_WORDS}
            # Only penalize when a variant stem appears in ONE side only
            unmatched_variants = var1_stems.symmetric_difference(var2_stems)
            if unmatched_variants:
                penalty = 25.0 * len(unmatched_variants)
                return max(sort_score - penalty, set_score - penalty, 0.0)

            return max(sort_score, set_score)

        return sort_score

    # ------------------------------------------------------------------
    # Database look-ups
    # ------------------------------------------------------------------

    async def find_matching_product(
        self,
        name: str,
        brand: str | None = None,
        *,
        category: str | None = None,
        session: AsyncSession | None = None,
    ) -> Optional[Product]:
        """Search existing products and return the best fuzzy match.

        If a *brand* is supplied the search is restricted to products that
        share the same canonical brand first; if nothing is found it falls
        back to a brand-agnostic search.

        If *category* is supplied and the candidate product also has a category,
        mismatched categories cap the score at 70 (below threshold) to prevent
        cross-category false merges (e.g. "Infuso Finocchio" tea vs "Finocchi"
        vegetable).

        Returns ``None`` when no product scores above the match threshold.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            canonical_brand = self.normalize_brand(brand)

            # Pre-filter: use significant tokens from the name (after
            # stripping private labels, brand and units) to narrow candidates via SQL ILIKE.
            cleaned = self._strip_units(self._strip_brand(
                self._strip_private_label(name), brand))
            tokens = self.normalize_text(cleaned).split()
            significant = [t for t in tokens if len(t) > 3][:3]

            # Fetch candidates – restrict to same brand when available
            if canonical_brand:
                stmt = select(Product).where(Product.brand == canonical_brand)
                if significant:
                    stmt = stmt.where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                result = await session.execute(stmt)
                candidates: list[Product] = list(result.scalars().all())

                # If no candidates with that brand, widen to token-only search
                if not candidates and significant:
                    stmt = select(Product).where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                    result = await session.execute(stmt)
                    candidates = list(result.scalars().all())
            else:
                if significant:
                    stmt = select(Product).where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                else:
                    stmt = select(Product)
                result = await session.execute(stmt)
                candidates = list(result.scalars().all())

            if not candidates:
                return None

            best_score: float = 0.0
            best_product: Product | None = None

            for product in candidates:
                score = self.fuzzy_match(
                    name, product.name,
                    brand1=brand, brand2=product.brand,
                )

                # Category guard: if both have a category and they differ,
                # cap score to prevent cross-category false merges
                if (
                    category
                    and product.category
                    and category != product.category
                    and category != "Supermercato"
                    and product.category != "Supermercato"
                ):
                    score = min(score, 70.0)

                # Give a bonus when brands match exactly
                if canonical_brand and product.brand == canonical_brand:
                    score = min(score + 5, 100.0)

                if score > best_score:
                    best_score = score
                    best_product = product

            # Use a lower threshold when brands match (the brand-aware
            # token_set_ratio already ensures quality)
            threshold = MATCH_THRESHOLD
            if (
                canonical_brand
                and best_product is not None
                and best_product.brand == canonical_brand
            ):
                threshold = BRAND_MATCH_THRESHOLD

            if best_score >= threshold and best_product is not None:
                logger.info(
                    "Matched '%s' -> '%s' (score=%.1f, threshold=%d)",
                    name,
                    best_product.name,
                    best_score,
                    threshold,
                )
                return best_product

            logger.debug(
                "No match for '%s' (best score=%.1f)", name, best_score
            )
            return None
        finally:
            if close_session:
                await session.close()

    async def find_receipt_match(
        self,
        name: str,
        *,
        category: str | None = None,
        session: AsyncSession | None = None,
    ) -> Optional[Product]:
        """Match a receipt item name to a catalog product.

        Optimised for the noisy, abbreviated names found on Italian receipts.
        Uses a lower match threshold (65) and shorter token minimum (>2 chars)
        to compensate for truncation.  Does NOT create new products.
        """
        RECEIPT_THRESHOLD = 65

        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            cleaned = self._strip_units(self._strip_brand(
                self._strip_private_label(name), None))
            tokens = self.normalize_text(cleaned).split()
            # Use shorter tokens (>2 chars) and more of them (up to 5)
            significant = [t for t in tokens if len(t) > 2][:5]

            if not significant:
                return None

            stmt = select(Product).where(
                or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
            )
            result = await session.execute(stmt)
            candidates: list[Product] = list(result.scalars().all())

            if not candidates:
                return None

            best_score: float = 0.0
            best_product: Product | None = None

            for product in candidates:
                score = self.fuzzy_match(name, product.name)

                # Category guard
                if (
                    category
                    and product.category
                    and category != product.category
                    and category != "Supermercato"
                    and product.category != "Supermercato"
                ):
                    score = min(score, 60.0)

                if score > best_score:
                    best_score = score
                    best_product = product

            if best_score >= RECEIPT_THRESHOLD and best_product is not None:
                logger.info(
                    "Receipt match '%s' -> '%s' (score=%.1f)",
                    name, best_product.name, best_score,
                )
                return best_product

            logger.debug(
                "No receipt match for '%s' (best=%.1f)", name, best_score
            )
            return None
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Product enrichment on re-match
    # ------------------------------------------------------------------

    @staticmethod
    def _enrich_product(product: Product, raw_data: dict, now) -> None:
        """Fill in missing fields on a matched product from new raw data.

        Updates ``last_seen_at`` and fills blanks for category, subcategory,
        image_url, and unit — but never overwrites existing good data.
        """
        product.last_seen_at = now

        # Fill category if currently missing or generic
        new_cat = raw_data.get("category")
        if new_cat and (not product.category or product.category == "Supermercato"):
            product.category = new_cat
        # Keyword categorization fallback if still missing
        if not product.category or product.category == "Supermercato":
            kw_cat = ProductMatcher.categorize_by_keywords(
                product.name, product.brand
            )
            if kw_cat:
                product.category = kw_cat
        if not product.category:
            product.category = "Altro"

        new_sub = raw_data.get("subcategory")
        if new_sub and (not product.subcategory or product.subcategory == "Supermercato"):
            product.subcategory = new_sub

        # Fill image if missing
        new_img = raw_data.get("image_url")
        if new_img and not product.image_url:
            product.image_url = new_img

        # Fill unit if missing
        new_unit = raw_data.get("unit")
        if new_unit and not product.unit:
            product.unit = new_unit

        # Backfill barcode if the incoming data has a valid one and product lacks one
        new_barcode = raw_data.get("barcode")
        if is_valid_ean(new_barcode) and not product.barcode:
            product.barcode = new_barcode

    # ------------------------------------------------------------------
    # Create-or-match entry point
    # ------------------------------------------------------------------

    async def create_or_match_product(
        self,
        raw_data: dict,
        *,
        session: AsyncSession | None = None,
    ) -> Product:
        """Return an existing :class:`Product` or create a new one.

        ``raw_data`` is expected to carry at least a ``name`` key.  Optional
        keys: ``brand``, ``category``, ``subcategory``, ``unit``, ``barcode``,
        ``image_url``.
        """
        name: str = raw_data.get("name", "").strip()
        brand: str | None = raw_data.get("brand")

        if not name:
            raise ValueError("Product name is required in raw_data")

        # Reject garbage product names
        _GARBAGE_NAMES = {"-", ".", "N/A", "n/a", "--", "...", ""}
        if len(name) < 2 or name in _GARBAGE_NAMES:
            raise ValueError(f"Product name is garbage: '{name}'")

        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            now = datetime.now(timezone.utc)
            source = raw_data.get("source")

            # --- 1. Exact barcode look-up (fastest) ---
            barcode = raw_data.get("barcode")
            if barcode and not is_valid_ean(barcode):
                barcode = None  # discard non-EAN codes (e.g. Esselunga internal)
            if barcode:
                stmt = select(Product).where(Product.barcode == barcode)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    logger.info(
                        "Barcode match '%s' -> product %s", barcode, existing.id
                    )
                    self._enrich_product(existing, raw_data, now)
                    await session.commit()
                    return existing

            # --- 2. Fuzzy name match ---
            category = raw_data.get("category")
            matched = await self.find_matching_product(
                name, brand, category=category, session=session
            )
            if matched is not None:
                # Barcode conflict guard: if both have valid EANs but they differ,
                # these are different products despite similar names
                if (
                    barcode
                    and is_valid_ean(barcode)
                    and matched.barcode
                    and is_valid_ean(matched.barcode)
                    and barcode != matched.barcode
                ):
                    logger.info(
                        "Barcode conflict: incoming '%s' vs existing '%s' on product %s — creating new",
                        barcode,
                        matched.barcode,
                        matched.id,
                    )
                    matched = None  # fall through to create new product
                else:
                    self._enrich_product(matched, raw_data, now)
                    await session.commit()
                    return matched

            # --- 3. Create new product ---
            canonical_brand = self.normalize_brand(brand)
            category = raw_data.get("category")
            if not category or category == "Supermercato":
                category = self.categorize_by_keywords(name, canonical_brand)
            if not category:
                category = "Altro"
            product = Product(
                id=uuid.uuid4(),
                name=name.strip(),
                brand=canonical_brand,
                category=category,
                subcategory=raw_data.get("subcategory"),
                unit=raw_data.get("unit"),
                barcode=barcode,
                image_url=raw_data.get("image_url"),
                source=source,
                last_seen_at=now,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)

            logger.info("Created new product %s – '%s'", product.id, product.name)
            return product
        except Exception:
            await session.rollback()
            raise
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Batch barcode dedup
    # ------------------------------------------------------------------

    @classmethod
    async def merge_barcode_duplicates(cls) -> int:
        """Find products sharing the same valid barcode and merge them.

        Keeps the product with the most offers as canonical.
        Reassigns all offers from duplicates to the canonical product.
        Deletes the duplicate product rows.
        Returns the number of products merged (removed).
        """
        from sqlalchemy import delete, func, text, update

        from app.models.offer import Offer
        from app.models.user import UserWatchlist

        merged = 0

        async with async_session() as session:
            # Find barcodes shared by multiple products
            stmt = text(
                "SELECT barcode, array_agg(id) AS ids "
                "FROM products "
                "WHERE barcode ~ '^[0-9]{8}$' OR barcode ~ '^[0-9]{13}$' "
                "GROUP BY barcode "
                "HAVING count(*) > 1"
            )
            result = await session.execute(stmt)
            rows = result.fetchall()

            for barcode_val, product_ids in rows:
                # Count offers per product to pick canonical (most offers)
                counts = {}
                for pid in product_ids:
                    cnt_result = await session.execute(
                        select(func.count(Offer.id)).where(Offer.product_id == pid)
                    )
                    counts[pid] = cnt_result.scalar() or 0

                # Canonical = most offers, oldest as tiebreaker
                sorted_pids = sorted(
                    product_ids,
                    key=lambda pid: (-counts[pid], str(pid)),
                )
                canonical_id = sorted_pids[0]
                duplicate_ids = sorted_pids[1:]

                if not duplicate_ids:
                    continue

                # Reassign offers
                await session.execute(
                    update(Offer)
                    .where(Offer.product_id.in_(duplicate_ids))
                    .values(product_id=canonical_id)
                )

                # Reassign watchlist entries (skip if user already watches canonical)
                existing_wl = await session.execute(
                    select(UserWatchlist.user_id).where(
                        UserWatchlist.product_id == canonical_id
                    )
                )
                existing_user_ids = {row[0] for row in existing_wl.fetchall()}

                if existing_user_ids:
                    await session.execute(
                        delete(UserWatchlist).where(
                            UserWatchlist.product_id.in_(duplicate_ids),
                            UserWatchlist.user_id.in_(existing_user_ids),
                        )
                    )

                await session.execute(
                    update(UserWatchlist)
                    .where(UserWatchlist.product_id.in_(duplicate_ids))
                    .values(product_id=canonical_id)
                )

                # Enrich canonical with data from duplicates
                canonical_result = await session.execute(
                    select(Product).where(Product.id == canonical_id)
                )
                canonical = canonical_result.scalar_one()

                for dup_id in duplicate_ids:
                    dup_result = await session.execute(
                        select(Product).where(Product.id == dup_id)
                    )
                    dup = dup_result.scalar_one_or_none()
                    if not dup:
                        continue
                    if not canonical.image_url and dup.image_url:
                        canonical.image_url = dup.image_url
                    if (not canonical.category or canonical.category == "Supermercato") and dup.category:
                        canonical.category = dup.category
                    if not canonical.subcategory and dup.subcategory:
                        canonical.subcategory = dup.subcategory
                    if not canonical.unit and dup.unit:
                        canonical.unit = dup.unit

                # Delete duplicates
                await session.execute(
                    delete(Product).where(Product.id.in_(duplicate_ids))
                )
                merged += len(duplicate_ids)

                logger.info(
                    "Barcode dedup '%s': kept %s, merged %d duplicates",
                    barcode_val, canonical_id, len(duplicate_ids),
                )

            await session.commit()

        logger.info("Barcode dedup complete: %d products merged.", merged)
        return merged
