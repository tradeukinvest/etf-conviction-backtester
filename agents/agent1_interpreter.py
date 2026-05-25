"""Agent 1: Interprets natural language allocation → ETF list with weights."""

import json
import re
import anthropic

ETF_MAP = {
    # US equity
    "us equity": "VOO", "us": "VOO", "s&p 500": "SPY", "sp500": "SPY",
    "nasdaq": "QQQ", "tech": "QQQ", "technology": "QQQ",
    "small cap": "IWM", "mid cap": "IJH", "value": "VTV", "growth": "VUG",
    # International equity
    "france": "EWQ", "brazil": "EWZ", "japan": "EWJ",
    "china": "MCHI", "chinese": "MCHI",
    "europe": "VGK", "european": "VGK",
    "emerging markets": "EEM", "emerging": "EEM",
    "international": "VGK",
    "india": "INDA", "korea": "EWY", "taiwan": "EWT",
    "germany": "EWG", "uk": "EWU", "canada": "EWC",
    "italy": "EWI", "italian": "EWI",
    "spain": "EWP", "spain": "EWP",
    "australia": "EWA", "mexico": "EWW",
    "latin america": "ILF",
    # Currencies → equity proxies (proxy rule: currency → related equity ETF)
    "yen": "EWJ",           # Japanese yen → Japan equity
    "yuan": "MCHI",         # Chinese yuan → China equity
    "renminbi": "MCHI",
    "euro": "VGK",          # Euro → Europe equity
    "pound": "EWU",         # GBP → UK equity
    "dollar": "VOO",        # USD strength → US equity
    # Sectors
    "industry": "XLI", "industrial": "XLI",
    "airlines": "JETS", "airline": "JETS", "aviation": "JETS",
    "waste management": "EVX", "waste": "EVX", "environmental services": "EVX",
    "military": "ITA", "defense": "ITA", "aerospace": "ITA",
    "ai": "BOTZ", "robotics": "BOTZ", "artificial intelligence": "BOTZ",
    "healthcare": "XLV", "health": "XLV", "pharma": "XLV", "biotech": "XBI",
    "financials": "XLF", "banks": "KBE", "finance": "XLF",
    "real estate": "VNQ", "reits": "VNQ", "reit": "VNQ",
    "utilities": "XLU", "consumer": "XLY", "consumer staples": "XLP",
    "materials": "XLB", "industrials": "XLI", "communication": "XLC",
    "semiconductor": "SOXX", "semiconductors": "SOXX", "chips": "SOXX",
    "clean energy": "ICLN", "renewable": "ICLN", "solar": "TAN",
    "crypto": "BITO", "bitcoin": "BITO", "blockchain": "BLOK",
    # Commodities → producer ETFs (proxy rule: commodity ETF → equity producer ETF)
    "gold": "GDX", "gold miners": "GDX",
    "silver": "SIL", "silver miners": "SIL",
    "oil": "XLE", "crude": "XLE",
    "energy": "XLE",
    "copper": "COPX",
    "mining": "GDX", "metals": "XME",
    "agriculture": "MOO", "food": "MOO",
    "lithium": "LIT",
    # Dividend / income
    "dividend": "VYM", "dividends": "VYM", "dividend growth": "DGRO",
    "high dividend": "VYM", "income": "VYM", "yield": "VYM",
    # Growth styles
    "us growth": "VUG", "large cap growth": "VUG", "mega cap growth": "MGK",
    "us value": "VTV", "large cap value": "VTV",
    "us large cap": "VOO", "s&p 500": "SPY",
    # Thematic
    "gold miners": "GDX", "junior gold miners": "GDXJ",
    "clean energy": "ICLN", "renewable energy": "ICLN", "solar": "TAN",
    "wind": "FAN", "water": "PHO", "infrastructure": "PAVE",
    "nuclear": "NLR", "uranium": "URA", "nuclear energy": "NLR",
    "genomics": "ARKG", "cloud": "SKYY", "cybersecurity": "CIBR",
    "esports": "ESPO", "social media": "SOCL",
    "japan": "EWJ", "japanese": "EWJ",
    "vietnam": "VNM", "greece": "GREK", "turkey": "TUR",
    "pacific": "VPL", "asia": "AAXJ", "asia pacific": "VPL",
    "brazil": "EWZ", "argentina": "ARGT",
    # Bonds → equity proxies (proxy rule: bond ETF → financial/credit equity proxy)
    "bonds": "XLF", "bond": "XLF",
    "investment grade": "XLF",
    "high yield": "XLF",
    "treasuries": "XLF", "treasury": "XLF",
    "fixed income": "XLF",
    "muni": "MUB", "municipal": "MUB",
    "tips": "TIP", "inflation protected": "TIP",
    "em bonds": "EMB", "emerging market bonds": "EMB",
    # ── Additional country mappings ───────────────────────────────────────────
    "singapore": "EWS", "hong kong": "EWH", "sweden": "EWD",
    "switzerland": "EWL", "netherlands": "EWN", "swiss": "EWL",
    "poland": "EPOL", "chile": "ECH", "thailand": "THD",
    "malaysia": "EWM", "israel": "EIS", "south africa": "EZA",
    "philippines": "EPHE", "indonesia": "EIDO",
    "denmark": "EDEN", "danish": "EDEN",
    "norway": "NORW", "norwegian": "NORW",
    "austria": "EWO", "new zealand": "ENZL",
    "saudi arabia": "KSA", "saudi": "KSA",
    "belgium": "EWK", "belgian": "EWK",
    "frontier markets": "FM", "frontier": "FM",
    # ── Global / multi-region ────────────────────────────────────────────────
    "global": "ACWI", "all country": "ACWI", "acwi": "ACWI",
    "all world": "VT", "world": "VT", "total world": "VT",
    "international ex-us": "VXUS", "ex-us": "VXUS",
    "asia ex japan": "AAXJ", "asia pacific": "VPL",
    # ── Spot crypto (2024 ETFs) ───────────────────────────────────────────────
    "spot bitcoin": "IBIT", "spot btc": "IBIT", "ibit": "IBIT",
    "ethereum": "ETHA", "eth": "ETHA", "ether": "ETHA",
    # ── Commodities / resources ───────────────────────────────────────────────
    "palladium": "PALL", "platinum": "PPLT",
    "corn": "CORN", "wheat": "WEAT",
    "soybean": "SOYB", "soybeans": "SOYB",
    "timber": "WOOD", "forestry": "WOOD",
    "rare earth": "REMX", "rare earths": "REMX",
    "natural resources": "GUNR", "upstream resources": "GUNR",
    "agribusiness producers": "VEGI", "agri producers": "VEGI",
    "carbon": "KRBN", "carbon credits": "KRBN",
    "commodity": "PDBC", "commodities basket": "PDBC",
    # ── Thematic ─────────────────────────────────────────────────────────────
    "fintech": "FINX", "payments": "IPAY", "mobile payments": "IPAY",
    "gaming": "ESPO", "video games": "ESPO", "esports": "ESPO",
    "space": "ARKX", "space exploration": "ARKX",
    "e-commerce": "EBIZ", "ecommerce": "EBIZ",
    "online retail": "ONLN",
    "telemedicine": "EDOC", "digital health": "EDOC",
    "autonomous": "IDRV", "self-driving": "IDRV", "autonomous vehicles": "IDRV",
    "electric vehicles": "DRIV", "ev": "DRIV",
    "iot": "SNSR", "internet of things": "SNSR",
    "cannabis": "MSOS", "marijuana": "MSOS", "weed": "MSOS",
    "sports betting": "BETZ", "igaming": "BETZ", "gambling": "BETZ",
    "bdc": "BIZD", "business development": "BIZD", "business development companies": "BIZD",
    "health tech": "HTEC", "healthcare technology": "HTEC",
    # ── Alternatives / overlays ───────────────────────────────────────────────
    "managed futures": "DBMF", "trend following": "DBMF",
    "covered call": "DIVO", "options income": "DIVO",
    "volatility": "VIXY", "vix": "VIXY",
    "tail risk": "TAIL", "tail hedge": "TAIL",
    # ── US factor / style expansions ─────────────────────────────────────────
    "total market": "VTI", "us total market": "VTI",
    "mega cap": "MGK", "mega cap growth": "MGK",
    "equal weight": "RSP", "s&p equal weight": "RSP",
    "momentum": "MTUM", "low volatility": "USMV",
    "quality factor": "QUAL", "quality": "QUAL",
    "dividend aristocrats": "NOBL",
    "dividend appreciation": "VIG", "dividend growth": "DGRO",
    "high dividend yield": "VYM", "schwab dividend": "SCHD",
    "small cap value": "VBR", "small cap growth": "VBK",
    "large cap value": "VTV", "large cap growth": "VUG",
    # ── Preferred / income ────────────────────────────────────────────────────
    "preferred stock": "PFFD", "preferred": "PFFD",
    # ── Bond type expansions ──────────────────────────────────────────────────
    "aggregate bond": "AGG", "total bond": "BND",
    "long treasury": "TLT", "long term treasury": "TLT",
    "short treasury": "SHY", "short term treasury": "SHY",
    "convertible": "CWB", "convertible bond": "CWB", "convertibles": "CWB",
    "cash": "BIL", "t-bills": "BIL", "tbills": "BIL", "money market": "SGOV",
    # ── Sector expansions ────────────────────────────────────────────────────
    "pharmaceutical": "XLV", "drug": "XLV", "drugs": "XLV",
    "biomedical": "XBI", "biopharma": "XBI",
    "regional banks": "KRE", "community banks": "KRE",
    "large banks": "KBWB",
}


def _parse_allocation(prompt: str) -> list[dict]:
    """Parse 'X% theme, Y% theme' patterns from prompt."""
    # Match patterns like "50% US equity", "50% Gold", etc.
    pattern = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*([^,\n]+)', prompt, re.IGNORECASE)
    if not pattern:
        return []
    results = []
    for pct, theme in pattern:
        theme = theme.strip().lower().rstrip('.,;')
        results.append({"theme": theme, "weight": float(pct) / 100.0})
    return results


def _resolve_etf_with_claude(theme: str) -> str:
    """Fallback: use Claude to resolve an unknown theme to an ETF ticker."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        system=(
            "You are an ETF resolver. Given an investment theme, return ONLY the "
            "single best matching US-listed ETF ticker symbol (e.g. 'QQQ'). "
            "No explanation, no punctuation, just the ticker."
        ),
        messages=[{"role": "user", "content": f"Best ETF for: {theme}"}],
    )
    return response.content[0].text.strip().upper()


def run(prompt: str) -> list[dict]:
    """
    Parse allocation prompt and resolve each theme to an ETF.

    Returns: [{"etf": "VOO", "weight": 0.5, "theme": "us equity"}, ...]
    """
    allocations = _parse_allocation(prompt)

    if not allocations:
        # Ask Claude to parse the whole thing as structured JSON
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=(
                "Parse an investment allocation description into a JSON list. "
                "Return ONLY valid JSON: [{\"theme\": str, \"weight\": float}, ...] "
                "where weights are decimals summing to 1.0. No explanation."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract JSON array from response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            allocations = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse allocation from: {prompt}")

    # Normalize weights to sum to 1.0
    total = sum(a["weight"] for a in allocations)
    for a in allocations:
        a["weight"] = a["weight"] / total

    # Resolve themes to ETFs
    resolved = []
    unresolved_themes = []
    for alloc in allocations:
        theme = alloc["theme"].lower().strip()
        etf = ETF_MAP.get(theme)
        if etf:
            resolved.append({"etf": etf, "weight": alloc["weight"], "theme": alloc["theme"]})
        else:
            # Check partial matches
            matched = None
            for key, val in ETF_MAP.items():
                if key in theme or theme in key:
                    matched = val
                    break
            if matched:
                resolved.append({"etf": matched, "weight": alloc["weight"], "theme": alloc["theme"]})
            else:
                unresolved_themes.append(alloc)

    # Use Claude for any unresolved themes
    if unresolved_themes:
        print(f"  Resolving {len(unresolved_themes)} unknown theme(s) with Claude...")
        for alloc in unresolved_themes:
            etf = _resolve_etf_with_claude(alloc["theme"])
            print(f"  '{alloc['theme']}' → {etf}")
            resolved.append({"etf": etf, "weight": alloc["weight"], "theme": alloc["theme"]})

    return resolved
