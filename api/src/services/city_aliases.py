"""Alias tables for normalizing carrier-spoken locations to canonical cities/states.

Carriers on the phone rarely give clean ``City, ST`` input. They say ``DFW``,
``LA``, ``the bay``, ``Big D``, etc. This module maps the top ~50 US freight
hubs (plus state-code variants) to canonical ``(city, state_code)`` tuples and
exposes light normalisation helpers.

The matcher in :mod:`api.src.services.load_matcher` calls :func:`normalize_location`
on both the carrier's input and on each candidate load's origin/destination so
the scoring step compares apples to apples.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalLocation:
    """A parsed location.

    ``city`` is the canonical title-cased city name (e.g. ``"Los Angeles"``).
    ``state`` is the two-letter USPS code (e.g. ``"CA"``). Either may be
    ``None`` if the input was state-only or city-only.
    """

    city: str | None
    state: str | None


# Two-letter USPS codes -> full state names. Used so the matcher can accept
# either form from the carrier ("California" or "CA").
US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District Of Columbia",
}

# Reverse map: full state name (lowercased) -> two-letter code.
STATE_NAME_TO_CODE: dict[str, str] = {v.lower(): k for k, v in US_STATES.items()}

# Top ~50 US freight hubs. Keys are lowercase aliases (airport codes, common
# abbreviations, nicknames, city-only forms). Values are the canonical
# ``(city, state_code)`` pair as it appears in the loads table.
#
# Every load city in :file:`data/seed_loads.json` is represented here, plus
# additional aliases for the hubs carriers most commonly reference.
CITY_ALIASES: dict[str, tuple[str, str]] = {
    # Texas
    "dallas": ("Dallas", "TX"),
    "dfw": ("Dallas", "TX"),
    "big d": ("Dallas", "TX"),
    "dallas fort worth": ("Dallas", "TX"),
    "fort worth": ("Dallas", "TX"),
    "houston": ("Houston", "TX"),
    "hou": ("Houston", "TX"),
    "iah": ("Houston", "TX"),
    "h-town": ("Houston", "TX"),
    "laredo": ("Laredo", "TX"),
    "lrd": ("Laredo", "TX"),
    "san antonio": ("San Antonio", "TX"),
    "sat": ("San Antonio", "TX"),
    "austin": ("Austin", "TX"),
    "el paso": ("El Paso", "TX"),
    # Georgia / Southeast
    "atlanta": ("Atlanta", "GA"),
    "atl": ("Atlanta", "GA"),
    "the atl": ("Atlanta", "GA"),
    "savannah": ("Savannah", "GA"),
    # Florida
    "miami": ("Miami", "FL"),
    "mia": ("Miami", "FL"),
    "jacksonville": ("Jacksonville", "FL"),
    "jax": ("Jacksonville", "FL"),
    "tampa": ("Tampa", "FL"),
    "tpa": ("Tampa", "FL"),
    "orlando": ("Orlando", "FL"),
    "orl": ("Orlando", "FL"),
    # California
    "los angeles": ("Los Angeles", "CA"),
    "la": ("Los Angeles", "CA"),
    "lax": ("Los Angeles", "CA"),
    "long beach": ("Los Angeles", "CA"),
    "san francisco": ("San Francisco", "CA"),
    "sf": ("San Francisco", "CA"),
    "sfo": ("San Francisco", "CA"),
    "the bay": ("San Francisco", "CA"),
    "oakland": ("Oakland", "CA"),
    "oak": ("Oakland", "CA"),
    "sacramento": ("Sacramento", "CA"),
    "sac": ("Sacramento", "CA"),
    "smf": ("Sacramento", "CA"),
    "fresno": ("Fresno", "CA"),
    "fat": ("Fresno", "CA"),
    "san diego": ("San Diego", "CA"),
    "san": ("San Diego", "CA"),
    # Illinois / Midwest
    "chicago": ("Chicago", "IL"),
    "chi": ("Chicago", "IL"),
    "ord": ("Chicago", "IL"),
    "chicagoland": ("Chicago", "IL"),
    "indianapolis": ("Indianapolis", "IN"),
    "indy": ("Indianapolis", "IN"),
    "ind": ("Indianapolis", "IN"),
    "detroit": ("Detroit", "MI"),
    "dtw": ("Detroit", "MI"),
    "cleveland": ("Cleveland", "OH"),
    "cle": ("Cleveland", "OH"),
    "columbus": ("Columbus", "OH"),
    "cmh": ("Columbus", "OH"),
    "cincinnati": ("Cincinnati", "OH"),
    "cvg": ("Cincinnati", "OH"),
    "minneapolis": ("Minneapolis", "MN"),
    "msp": ("Minneapolis", "MN"),
    "twin cities": ("Minneapolis", "MN"),
    "kansas city": ("Kansas City", "MO"),
    "kc": ("Kansas City", "MO"),
    "mci": ("Kansas City", "MO"),
    "st louis": ("St. Louis", "MO"),
    "st. louis": ("St. Louis", "MO"),
    "saint louis": ("St. Louis", "MO"),
    "stl": ("St. Louis", "MO"),
    # Tennessee / Kentucky / Alabama
    "memphis": ("Memphis", "TN"),
    "mem": ("Memphis", "TN"),
    "nashville": ("Nashville", "TN"),
    "nsh": ("Nashville", "TN"),
    "bna": ("Nashville", "TN"),
    "louisville": ("Louisville", "KY"),
    "sdf": ("Louisville", "KY"),
    "birmingham": ("Birmingham", "AL"),
    "bhm": ("Birmingham", "AL"),
    # Northeast
    "new york": ("New York", "NY"),
    "new york city": ("New York", "NY"),
    "nyc": ("New York", "NY"),
    "ny": ("New York", "NY"),
    "jfk": ("New York", "NY"),
    "lga": ("New York", "NY"),
    "newark": ("Newark", "NJ"),
    "ewr": ("Newark", "NJ"),
    "boston": ("Boston", "MA"),
    "bos": ("Boston", "MA"),
    "beantown": ("Boston", "MA"),
    "philadelphia": ("Philadelphia", "PA"),
    "philly": ("Philadelphia", "PA"),
    "phl": ("Philadelphia", "PA"),
    "pittsburgh": ("Pittsburgh", "PA"),
    "pit": ("Pittsburgh", "PA"),
    "baltimore": ("Baltimore", "MD"),
    "bwi": ("Baltimore", "MD"),
    "washington": ("Washington", "DC"),
    "dc": ("Washington", "DC"),
    "dca": ("Washington", "DC"),
    # Mountain West / Southwest
    "denver": ("Denver", "CO"),
    "den": ("Denver", "CO"),
    "mile high": ("Denver", "CO"),
    "salt lake city": ("Salt Lake City", "UT"),
    "slc": ("Salt Lake City", "UT"),
    "salt lake": ("Salt Lake City", "UT"),
    "phoenix": ("Phoenix", "AZ"),
    "phx": ("Phoenix", "AZ"),
    "albuquerque": ("Albuquerque", "NM"),
    "abq": ("Albuquerque", "NM"),
    "las vegas": ("Las Vegas", "NV"),
    "vegas": ("Las Vegas", "NV"),
    "las": ("Las Vegas", "NV"),
    "reno": ("Reno", "NV"),
    "rno": ("Reno", "NV"),
    "boise": ("Boise", "ID"),
    "boi": ("Boise", "ID"),
    "oklahoma city": ("Oklahoma City", "OK"),
    "okc": ("Oklahoma City", "OK"),
    # Pacific Northwest
    "seattle": ("Seattle", "WA"),
    "sea": ("Seattle", "WA"),
    "sea-tac": ("Seattle", "WA"),
    "portland": ("Portland", "OR"),
    "pdx": ("Portland", "OR"),
    "rose city": ("Portland", "OR"),
    # The Carolinas
    "charlotte": ("Charlotte", "NC"),
    "clt": ("Charlotte", "NC"),
    "queen city": ("Charlotte", "NC"),
    "raleigh": ("Raleigh", "NC"),
    "rdu": ("Raleigh", "NC"),
    # Gulf
    "new orleans": ("New Orleans", "LA"),
    "nola": ("New Orleans", "LA"),
    "msy": ("New Orleans", "LA"),
}


# State adjacency for the 20 most common lanes. Two-letter USPS codes only.
# This is a hand-curated subset, not a full national adjacency graph — it
# covers the routes the seed data emphasizes (Texas triangle, Gulf, Southeast,
# Midwest, West Coast, Mountain West, Northeast).
STATE_ADJACENCY: dict[str, set[str]] = {
    # Texas triangle / Gulf
    "TX": {"OK", "AR", "LA", "NM"},
    "OK": {"TX", "AR", "KS", "MO", "NM", "CO"},
    "AR": {"TX", "OK", "LA", "MS", "TN", "MO"},
    "LA": {"TX", "AR", "MS"},
    "MS": {"LA", "AR", "TN", "AL"},
    "AL": {"MS", "TN", "GA", "FL"},
    "GA": {"AL", "TN", "NC", "SC", "FL"},
    "FL": {"AL", "GA"},
    # Southeast / Mid-Atlantic
    "TN": {"MS", "AL", "GA", "NC", "VA", "KY", "MO", "AR"},
    "NC": {"GA", "SC", "TN", "VA"},
    "SC": {"GA", "NC"},
    "KY": {"TN", "VA", "WV", "OH", "IN", "IL", "MO"},
    "VA": {"NC", "TN", "KY", "WV", "MD", "DC"},
    # Midwest
    "MO": {"AR", "OK", "KS", "NE", "IA", "IL", "KY", "TN"},
    "IL": {"MO", "IA", "WI", "IN", "KY"},
    "IN": {"IL", "KY", "OH", "MI"},
    "OH": {"IN", "MI", "PA", "WV", "KY"},
    "MI": {"IN", "OH", "WI"},
    "WI": {"MN", "IA", "IL", "MI"},
    "MN": {"WI", "IA", "SD", "ND"},
    "IA": {"MN", "WI", "IL", "MO", "NE", "SD"},
    "KS": {"MO", "OK", "CO", "NE"},
    "NE": {"KS", "MO", "IA", "SD", "WY", "CO"},
    # Mountain West / Southwest
    "CO": {"WY", "NE", "KS", "OK", "NM", "UT"},
    "NM": {"CO", "OK", "TX", "AZ", "UT"},
    "AZ": {"CA", "NV", "UT", "NM"},
    "UT": {"NV", "ID", "WY", "CO", "NM", "AZ"},
    "NV": {"CA", "OR", "ID", "UT", "AZ"},
    "WY": {"MT", "SD", "NE", "CO", "UT", "ID"},
    "ID": {"WA", "OR", "NV", "UT", "WY", "MT"},
    # Pacific
    "CA": {"OR", "NV", "AZ"},
    "OR": {"WA", "CA", "NV", "ID"},
    "WA": {"OR", "ID"},
    # Northeast
    "PA": {"OH", "WV", "MD", "NJ", "NY", "DE"},
    "NJ": {"PA", "NY", "DE"},
    "NY": {"NJ", "PA", "CT", "MA", "VT"},
    "MA": {"NY", "CT", "RI", "NH", "VT"},
    "CT": {"NY", "MA", "RI"},
    "RI": {"MA", "CT"},
    "MD": {"PA", "WV", "VA", "DE", "DC"},
    "DE": {"PA", "NJ", "MD"},
    "DC": {"MD", "VA"},
    "WV": {"PA", "MD", "VA", "KY", "OH"},
}


def states_are_adjacent(a: str | None, b: str | None) -> bool:
    """Return True if states ``a`` and ``b`` share a border per :data:`STATE_ADJACENCY`."""
    if not a or not b:
        return False
    a = a.upper()
    b = b.upper()
    if a == b:
        return False
    return b in STATE_ADJACENCY.get(a, set())


def _norm_token(s: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation that's safe to drop."""
    return " ".join(s.lower().strip().replace(".", "").split())


def normalize_location(raw: str | None) -> CanonicalLocation:
    """Parse a free-form location string into a :class:`CanonicalLocation`.

    Accepts ``"City, ST"``, ``"City, State"``, just a city alias (e.g. ``"DFW"``,
    ``"the bay"``), or just a state (``"Texas"`` / ``"TX"``). Splits on commas,
    normalises whitespace + case, and consults :data:`CITY_ALIASES` /
    :data:`US_STATES`.

    The matcher relies on this returning *something* sensible even for garbage
    input — when nothing matches, the city portion is preserved verbatim
    (title-cased) so a downstream string-equality check on canonical city names
    can still succeed for cities the alias table doesn't enumerate.
    """
    if not raw:
        return CanonicalLocation(city=None, state=None)

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return CanonicalLocation(city=None, state=None)

    if len(parts) == 1:
        token = _norm_token(parts[0])

        # 1. City-alias hit
        if token in CITY_ALIASES:
            city, state = CITY_ALIASES[token]
            return CanonicalLocation(city=city, state=state)

        # 2. Two-letter state code
        if len(token) == 2 and token.upper() in US_STATES:
            return CanonicalLocation(city=None, state=token.upper())

        # 3. Full state name
        if token in STATE_NAME_TO_CODE:
            return CanonicalLocation(city=None, state=STATE_NAME_TO_CODE[token])

        # 4. Unknown city — pass it through title-cased so downstream
        #    equality still works against canonical city strings.
        return CanonicalLocation(city=parts[0].strip().title(), state=None)

    # "City, ST" or "City, State" form — last token is the state.
    city_raw = ", ".join(parts[:-1]).strip()
    state_raw = _norm_token(parts[-1])

    city_token = _norm_token(city_raw)

    state_code: str | None = None
    if len(state_raw) == 2 and state_raw.upper() in US_STATES:
        state_code = state_raw.upper()
    elif state_raw in STATE_NAME_TO_CODE:
        state_code = STATE_NAME_TO_CODE[state_raw]

    # Prefer the alias table's canonical city when it knows about this input,
    # but only override the state if the carrier didn't already supply one.
    if city_token in CITY_ALIASES:
        canonical_city, canonical_state = CITY_ALIASES[city_token]
        return CanonicalLocation(
            city=canonical_city,
            state=state_code or canonical_state,
        )

    # Title-case the raw city so unknown-but-spelled-out cities still compare.
    return CanonicalLocation(city=city_raw.title(), state=state_code)
