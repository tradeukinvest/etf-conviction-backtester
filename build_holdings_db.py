#!/usr/bin/env python3
"""
One-time script: build holdings.db (SQLite) for all major ETFs.

Schema:
  etf_info     — ticker, name, theme, asset_class, proxy_rule
  top_holdings — etf, stock, start_date, end_date (NULL = still current)

Run:
    python3.11 build_holdings_db.py

Progress saves after each ETF. Safe to stop and resume.
"""

import json
import sqlite3
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))

CACHE_DIR = Path(__file__).parent / "cache"
DB_PATH   = CACHE_DIR / "holdings.db"

# ── ETF metadata ───────────────────────────────────────────────────────────────
ETF_META = {
    # US broad
    "VOO":  ("Vanguard S&P 500 ETF",               "US Large Cap",           "EQD",        None),
    "SPY":  ("SPDR S&P 500 ETF",                   "US Large Cap",           "EQD",        None),
    "IVV":  ("iShares Core S&P 500 ETF",           "US Large Cap",           "EQD",        None),
    "VTI":  ("Vanguard Total Stock Market ETF",     "US Total Market",        "EQD",        None),
    "QQQ":  ("Invesco NASDAQ-100 ETF",              "US Tech / Nasdaq",       "EQD",        None),
    "IWM":  ("iShares Russell 2000 ETF",            "US Small Cap",           "EQD",        None),
    "IJH":  ("iShares Core S&P Mid-Cap ETF",        "US Mid Cap",             "EQD",        None),
    # US factors
    "VTV":  ("Vanguard Value ETF",                  "US Value",               "EQD",        None),
    "VUG":  ("Vanguard Growth ETF",                 "US Growth",              "EQD",        None),
    "VIG":  ("Vanguard Dividend Appreciation ETF",  "US Dividend Growth",     "EQD",        None),
    "SCHD": ("Schwab US Dividend Equity ETF",       "US High Dividend",       "EQD",        None),
    # US sectors
    "XLF":  ("Financial Select Sector SPDR",        "US Financials",          "EQD",        "Bonds → Financials proxy"),
    "XLE":  ("Energy Select Sector SPDR",           "US Energy",              "EQD",        None),
    "XLV":  ("Health Care Select Sector SPDR",      "US Healthcare",          "EQD",        None),
    "XLI":  ("Industrial Select Sector SPDR",       "US Industrials",         "EQD",        "Waste/Industrial proxy"),
    "XLK":  ("Technology Select Sector SPDR",       "US Technology",          "EQD",        None),
    "XLB":  ("Materials Select Sector SPDR",        "US Materials",           "EQD",        None),
    "XLU":  ("Utilities Select Sector SPDR",        "US Utilities",           "EQD",        None),
    "XLY":  ("Consumer Discret. Select Sector SPDR","US Consumer Discretionary","EQD",      None),
    "XLP":  ("Consumer Staples Select Sector SPDR", "US Consumer Staples",    "EQD",        None),
    "XLC":  ("Communication Services Select SPDR",  "US Communication",       "EQD",        None),
    # Commodities → equity producer proxies
    "GDX":  ("VanEck Gold Miners ETF",              "Gold",                   "GOLD",       "Gold physical (GLD/IAU) → GDX gold miners"),
    "SIL":  ("Global X Silver Miners ETF",          "Silver",                 "COMMO",      "Silver physical → SIL silver miners"),
    "COPX": ("Global X Copper Miners ETF",          "Copper",                 "COMMO",      "Copper → COPX copper miners"),
    "XME":  ("SPDR S&P Metals & Mining ETF",        "Metals & Mining",        "COMMO",      None),
    "NLR":  ("VanEck Uranium+Nuclear ETF",          "Nuclear Energy / Uranium","COMMO",     None),
    "LIT":  ("Global X Lithium & Battery Tech ETF", "Lithium / EV batteries", "COMMO",      None),
    # Thematic
    "ITA":  ("iShares U.S. Aerospace & Defense ETF","Defense / Military",     "EQD",        None),
    "BOTZ": ("Global X Robotics & AI ETF",          "AI / Robotics",          "EQD",        None),
    "SOXX": ("iShares Semiconductor ETF",           "Semiconductors",         "EQD",        None),
    "XBI":  ("SPDR S&P Biotech ETF",                "Biotech",                "EQD",        None),
    "ICLN": ("iShares Global Clean Energy ETF",     "Clean Energy",           "EQD",        None),
    "TAN":  ("Invesco Solar ETF",                   "Solar Energy",           "EQD",        None),
    "BITO": ("ProShares Bitcoin Strategy ETF",      "Bitcoin / Crypto",       "COMMO",      None),
    # Real estate
    "VNQ":  ("Vanguard Real Estate ETF",            "US Real Estate",         "REALESTATE", None),
    # International broad
    "EFA":  ("iShares MSCI EAFE ETF",               "Developed Markets ex-US","EQD",        None),
    "EEM":  ("iShares MSCI Emerging Markets ETF",   "Emerging Markets",       "EQD",        None),
    "VGK":  ("Vanguard FTSE Europe ETF",            "Europe",                 "EQD",        None),
    # Country ETFs
    "EWJ":  ("iShares MSCI Japan ETF",              "Japan",                  "EQD",        "JPY currency proxy"),
    "MCHI": ("iShares MSCI China ETF",              "China",                  "EQD",        "CNY/Yuan proxy"),
    "INDA": ("iShares MSCI India ETF",              "India",                  "EQD",        None),
    "EWZ":  ("iShares MSCI Brazil ETF",             "Brazil",                 "EQD",        None),
    "EWG":  ("iShares MSCI Germany ETF",            "Germany",                "EQD",        None),
    "EWU":  ("iShares MSCI United Kingdom ETF",     "United Kingdom",         "EQD",        "GBP proxy"),
    "EWC":  ("iShares MSCI Canada ETF",             "Canada",                 "EQD",        None),
    "EWQ":  ("iShares MSCI France ETF",             "France",                 "EQD",        None),
    "EWY":  ("iShares MSCI South Korea ETF",        "South Korea",            "EQD",        None),
    "EWT":  ("iShares MSCI Taiwan ETF",             "Taiwan",                 "EQD",        None),
    "EWA":  ("iShares MSCI Australia ETF",          "Australia",              "EQD",        None),
    "EWW":  ("iShares MSCI Mexico ETF",             "Mexico",                 "EQD",        None),
    "ILF":  ("iShares Latin America 40 ETF",        "Latin America",          "EQD",        None),
    # US broad & factors (batch 2)
    "VB":   ("Vanguard Small-Cap ETF",              "US Small Cap",           "EQD",        None),
    "VO":   ("Vanguard Mid-Cap ETF",                "US Mid Cap",             "EQD",        None),
    "ITOT": ("iShares Core S&P Total US Market ETF","US Total Market",        "EQD",        None),
    "RSP":  ("Invesco S&P 500 Equal Weight ETF",    "US Equal Weight",        "EQD",        None),
    "USMV": ("iShares MSCI USA Min Vol Factor ETF", "US Low Volatility",      "EQD",        None),
    "MTUM": ("iShares MSCI USA Momentum Factor ETF","US Momentum",            "EQD",        None),
    "QUAL": ("iShares MSCI USA Quality Factor ETF", "US Quality",             "EQD",        None),
    "SPLV": ("Invesco S&P 500 Low Volatility ETF",  "US Low Volatility",      "EQD",        None),
    "NOBL": ("ProShares S&P 500 Dividend Aristocrats ETF","US Dividend Aristocrats","EQD",  None),
    "DVY":  ("iShares Select Dividend ETF",         "US High Dividend",       "EQD",        None),
    "VYM":  ("Vanguard High Dividend Yield ETF",    "US High Dividend",       "EQD",        None),
    # ARK funds
    "ARKK": ("ARK Innovation ETF",                  "Disruptive Innovation",  "EQD",        None),
    "ARKG": ("ARK Genomic Revolution ETF",          "Genomics / Biotech",     "EQD",        None),
    "ARKW": ("ARK Next Generation Internet ETF",    "Internet / Fintech",     "EQD",        None),
    "ARKF": ("ARK Fintech Innovation ETF",          "Fintech",                "EQD",        None),
    # US thematic (batch 2)
    "CIBR": ("First Trust NASDAQ Cybersecurity ETF","Cybersecurity",          "EQD",        None),
    "CLOU": ("Global X Cloud Computing ETF",        "Cloud Computing",        "EQD",        None),
    "FINX": ("Global X FinTech ETF",               "Fintech",                "EQD",        None),
    "HERO": ("Global X Video Games & Esports ETF",  "Gaming / Esports",       "EQD",        None),
    "DRIV": ("Global X Autonomous & Electric Vehicles ETF","EV / Autonomous",  "EQD",        None),
    "JETS": ("US Global Jets ETF",                  "Airlines",               "EQD",        None),
    "KRE":  ("SPDR S&P Regional Banking ETF",       "US Regional Banks",      "EQD",        None),
    "SMH":  ("VanEck Semiconductor ETF",            "Semiconductors",         "EQD",        None),
    "GDXJ": ("VanEck Junior Gold Miners ETF",       "Junior Gold Miners",     "GOLD",       "Gold → GDXJ junior miners"),
    "XLRE": ("Real Estate Select Sector SPDR",      "US Real Estate",         "REALESTATE", None),
    "MOO":  ("VanEck Agribusiness ETF",             "Agribusiness",           "EQD",        None),
    "REMX": ("VanEck Rare Earth/Strategic Metals ETF","Rare Earths",          "COMMO",      None),
    "ROBO": ("ROBO Global Robotics & Automation ETF","Robotics",              "EQD",        None),
    # International (batch 2)
    "VWO":  ("Vanguard FTSE Emerging Markets ETF",  "Emerging Markets",       "EQD",        None),
    "IEMG": ("iShares Core MSCI Emerging Markets ETF","Emerging Markets",     "EQD",        None),
    "FXI":  ("iShares China Large-Cap ETF",         "China Large Cap",        "EQD",        "CNY proxy alt"),
    "KWEB": ("KraneShares CSI China Internet ETF",  "China Internet",         "EQD",        None),
    "EWS":  ("iShares MSCI Singapore ETF",          "Singapore",              "EQD",        None),
    "EWH":  ("iShares MSCI Hong Kong ETF",          "Hong Kong",              "EQD",        None),
    "EWD":  ("iShares MSCI Sweden ETF",             "Sweden",                 "EQD",        None),
    "EWI":  ("iShares MSCI Italy ETF",              "Italy",                  "EQD",        None),
    "EWP":  ("iShares MSCI Spain ETF",              "Spain",                  "EQD",        None),
    "EWN":  ("iShares MSCI Netherlands ETF",        "Netherlands",            "EQD",        None),
    "EWL":  ("iShares MSCI Switzerland ETF",        "Switzerland",            "EQD",        None),
    "EPOL": ("iShares MSCI Poland ETF",             "Poland",                 "EQD",        None),
    "ECH":  ("iShares MSCI Chile ETF",              "Chile",                  "EQD",        None),
    "THD":  ("iShares MSCI Thailand ETF",           "Thailand",               "EQD",        None),
    "EWM":  ("iShares MSCI Malaysia ETF",           "Malaysia",               "EQD",        None),
    "EIS":  ("iShares MSCI Israel ETF",             "Israel",                 "EQD",        None),
    "EZA":  ("iShares MSCI South Africa ETF",       "South Africa",           "EQD",        None),
    "EPHE": ("iShares MSCI Philippines ETF",        "Philippines",            "EQD",        None),
    "EIDO": ("iShares MSCI Indonesia ETF",          "Indonesia",              "EQD",        None),
    # Vanguard sector equivalents (same holdings as SPDR XL* series)
    "VHT":  ("Vanguard Health Care ETF",            "US Healthcare",          "EQD",        None),
    "VGT":  ("Vanguard Information Technology ETF", "US Technology",          "EQD",        None),
    "VFH":  ("Vanguard Financials ETF",             "US Financials",          "EQD",        None),
    "VDE":  ("Vanguard Energy ETF",                 "US Energy",              "EQD",        None),
    "VPU":  ("Vanguard Utilities ETF",              "US Utilities",           "EQD",        None),
    "VCR":  ("Vanguard Consumer Discretionary ETF", "US Consumer Discretionary","EQD",      None),
    "VDC":  ("Vanguard Consumer Staples ETF",       "US Consumer Staples",    "EQD",        None),
    "VAW":  ("Vanguard Materials ETF",              "US Materials",           "EQD",        None),
    "VIS":  ("Vanguard Industrials ETF",            "US Industrials",         "EQD",        None),
    "VOX":  ("Vanguard Communication Services ETF", "US Communication",       "EQD",        None),
    # Physical commodity & currency ETFs (proxy rules for backtester)
    "GLD":  ("SPDR Gold Trust",                     "Gold Physical",          "GOLD",       "Physical gold → GDX gold miners proxy"),
    "IAU":  ("iShares Gold Trust",                  "Gold Physical",          "GOLD",       "Physical gold → GDX gold miners proxy"),
    "SLV":  ("iShares Silver Trust",                "Silver Physical",        "COMMO",      "Physical silver → SIL silver miners proxy"),
    "USO":  ("United States Oil Fund",              "Oil / Crude",            "COMMO",      "WTI crude futures → XLE energy proxy"),
    "UNG":  ("United States Natural Gas Fund",      "Natural Gas",            "COMMO",      "NG futures → XLE energy proxy"),
    "DBC":  ("Invesco DB Commodity Index Fund",     "Diversified Commodity",  "COMMO",      "Commodity basket → XLE proxy"),
    "FXE":  ("Invesco CurrencyShares Euro ETF",     "Euro Currency",          "COMMO",      "EUR → VGK Europe equity proxy"),
    "FXY":  ("Invesco CurrencyShares Yen ETF",      "Japanese Yen",           "COMMO",      "JPY → EWJ Japan equity proxy"),
    # Schwab equivalents
    "SCHG": ("Schwab US Large-Cap Growth ETF",      "US Growth",              "EQD",        None),
    "SCHV": ("Schwab US Large-Cap Value ETF",       "US Value",               "EQD",        None),
    "SCHA": ("Schwab US Small-Cap ETF",             "US Small Cap",           "EQD",        None),
    "SCHF": ("Schwab International Equity ETF",     "Developed Markets ex-US","EQD",        None),
    "SCHE": ("Schwab Emerging Markets ETF",         "Emerging Markets",       "EQD",        None),
    # More thematic
    "BLOK": ("Amplify Transformational Data Sharing ETF","Blockchain",        "COMMO",      None),
    "HACK": ("ETFMG Prime Cyber Security ETF",      "Cybersecurity",          "EQD",        None),
    "IBB":  ("iShares Nasdaq Biotechnology ETF",    "Biotech",                "EQD",        None),
    "KBE":  ("SPDR S&P Bank ETF",                  "US Banks",               "EQD",        None),
    "URA":  ("Global X Uranium ETF",               "Uranium",                "COMMO",      "Uranium miners, CCJ top"),
    "SILJ": ("ETFMG Prime Junior Silver ETF",       "Junior Silver Miners",   "COMMO",      "Junior silver → SIL proxy"),
    "VBR":  ("Vanguard Small-Cap Value ETF",        "US Small Cap Value",     "EQD",        None),
    "VBK":  ("Vanguard Small-Cap Growth ETF",       "US Small Cap Growth",    "EQD",        None),
    "SCHH": ("Schwab US REIT ETF",                  "US Real Estate",         "REALESTATE", None),
    "IYR":  ("iShares US Real Estate ETF",          "US Real Estate",         "REALESTATE", None),
    # World / Global
    "ACWI": ("iShares MSCI ACWI ETF",              "Global All-Cap",         "EQD",        None),
    "VT":   ("Vanguard Total World Stock ETF",      "Global All-Cap",         "EQD",        None),
    "VXUS": ("Vanguard Total International Stock ETF","International All-Cap","EQD",        None),
    "VEU":  ("Vanguard FTSE All-World ex-US ETF",  "International ex-US",    "EQD",        None),
    "GXC":  ("SPDR S&P China ETF",                 "China All-Cap",          "EQD",        None),
    # More country ETFs
    "EDEN": ("iShares MSCI Denmark ETF",            "Denmark",                "EQD",        None),
    "NORW": ("Global X MSCI Norway ETF",            "Norway",                 "EQD",        None),
    "EWO":  ("iShares MSCI Austria ETF",            "Austria",                "EQD",        None),
    "INDY": ("iShares India 50 ETF",               "India Large Cap",        "EQD",        None),
    "KSA":  ("iShares MSCI Saudi Arabia ETF",       "Saudi Arabia",           "EQD",        None),
    "EWK":  ("iShares MSCI Belgium ETF",            "Belgium",                "EQD",        None),
    "TWN":  ("First Trust NASDAQ Technology ETF",   "Taiwan Tech",            "EQD",        None),
    # ── Requested specifically ────────────────────────────────────────────────
    "EPI":  ("WisdomTree India Earnings ETF",        "India Earnings",         "EQD",        None),
    "EVX":  ("VanEck Environmental Services ETF",    "Environmental Services", "EQD",        None),
    "SRET": ("Global X SuperDividend REIT ETF",      "High Dividend REITs",    "REALESTATE", None),
    "SGDM": ("Sprott Gold Miners ETF",               "Gold Miners",            "GOLD",       "Gold → SGDM large miners"),
    "EMLC": ("VanEck EM Local Currency Bond ETF",    "EM Local Currency Bond", "BOND",       "EM local currency → EEM proxy"),
    "KHYB": ("KraneShares Asia Pacific High Yield Bond ETF","Asia HY Bond",   "BOND",       "Asia HY bonds → FXI proxy"),
    # Mum's portfolio ETFs
    "IWF":  ("iShares Russell 1000 Growth ETF",      "US Large Cap Growth",    "EQD",        None),
    "VPL":  ("Vanguard FTSE Pacific ETF",            "Asia-Pacific",           "EQD",        None),
    # ── US Broad / Russell family ─────────────────────────────────────────────
    "IWB":  ("iShares Russell 1000 ETF",             "US Large Cap",           "EQD",        None),
    "IWD":  ("iShares Russell 1000 Value ETF",       "US Large Cap Value",     "EQD",        None),
    "IWO":  ("iShares Russell 2000 Growth ETF",      "US Small Cap Growth",    "EQD",        None),
    "IWN":  ("iShares Russell 2000 Value ETF",       "US Small Cap Value",     "EQD",        None),
    "MDY":  ("SPDR S&P MidCap 400 ETF",              "US Mid Cap",             "EQD",        None),
    "SPYG": ("SPDR Portfolio S&P 500 Growth ETF",    "US Large Cap Growth",    "EQD",        None),
    "SPYV": ("SPDR Portfolio S&P 500 Value ETF",     "US Large Cap Value",     "EQD",        None),
    "SPMD": ("SPDR Portfolio S&P MidCap 400 ETF",    "US Mid Cap",             "EQD",        None),
    "SPSM": ("SPDR Portfolio S&P 600 Small Cap ETF", "US Small Cap",           "EQD",        None),
    "MGK":  ("Vanguard Mega Cap Growth ETF",         "US Mega Cap Growth",     "EQD",        None),
    "MGV":  ("Vanguard Mega Cap Value ETF",          "US Mega Cap Value",      "EQD",        None),
    "VV":   ("Vanguard Large-Cap ETF",               "US Large Cap",           "EQD",        None),
    "VONV": ("Vanguard Russell 1000 Value ETF",      "US Large Cap Value",     "EQD",        None),
    "VONG": ("Vanguard Russell 1000 Growth ETF",     "US Large Cap Growth",    "EQD",        None),
    "VTWO": ("Vanguard Russell 2000 ETF",            "US Small Cap",           "EQD",        None),
    "ESGV": ("Vanguard ESG US Stock ETF",            "US ESG",                 "EQD",        None),
    "QQQM": ("Invesco NASDAQ 100 ETF (Retail)",      "US Tech / Nasdaq",       "EQD",        None),
    "ONEQ": ("Fidelity NASDAQ Composite ETF",        "US Tech / Nasdaq",       "EQD",        None),
    # ── US Dividend & Income ──────────────────────────────────────────────────
    "SDY":  ("SPDR S&P Dividend ETF",               "US High Dividend",        "EQD",        None),
    "HDV":  ("iShares Core High Dividend ETF",       "US High Dividend",        "EQD",        None),
    "DGRO": ("iShares Core Dividend Growth ETF",     "US Dividend Growth",      "EQD",        None),
    "PFF":  ("iShares Preferred & Income Securities ETF","US Preferred Stock",  "EQD",        None),
    "DGRW": ("WisdomTree US Quality Dividend Growth Fund","US Dividend Growth", "EQD",        None),
    "JEPI": ("JPMorgan Equity Premium Income ETF",   "US Covered Call Income",  "EQD",        None),
    "JEPQ": ("JPMorgan Nasdaq Equity Premium Income ETF","Nasdaq Covered Call","EQD",        None),
    "QYLD": ("Global X NASDAQ 100 Covered Call ETF", "Nasdaq Covered Call",    "EQD",        None),
    "XYLD": ("Global X S&P 500 Covered Call ETF",   "S&P 500 Covered Call",    "EQD",        None),
    "DLN":  ("WisdomTree US LargeCap Dividend Fund", "US Large Cap Dividend",   "EQD",        None),
    "TDIV": ("First Trust NASDAQ Technology Dividend ETF","Tech Dividend",      "EQD",        None),
    "COWZ": ("Pacer US Cash Cows 100 ETF",           "US Free Cash Flow",       "EQD",        None),
    "CALF": ("Pacer US Small Cap Cash Cows 100 ETF", "US Small Cap FCF",        "EQD",        None),
    # ── US Thematic – Tech/Innovation ─────────────────────────────────────────
    "SKYY": ("First Trust Cloud Computing ETF",      "Cloud Computing",         "EQD",        None),
    "WCLD": ("WisdomTree Cloud Computing ETF",       "Cloud Computing",         "EQD",        None),
    "FDN":  ("First Trust Dow Jones Internet ETF",   "Internet",                "EQD",        None),
    "IPAY": ("ETFMG Prime Mobile Payments ETF",      "Mobile Payments",         "EQD",        None),
    "ARKX": ("ARK Space Exploration & Innovation ETF","Space",                  "EQD",        None),
    "ESPO": ("VanEck Video Gaming & eSports ETF",    "Gaming / eSports",        "EQD",        None),
    "NERD": ("Roundhill Video Games & eSports ETF",  "Gaming / eSports",        "EQD",        None),
    "SOCL": ("Global X Social Media ETF",            "Social Media",            "EQD",        None),
    "EBIZ": ("Global X E-Commerce ETF",              "E-Commerce",              "EQD",        None),
    "ONLN": ("ProShares Online Retail ETF",          "Online Retail",           "EQD",        None),
    "GNOM": ("Global X Genomics & Biotechnology ETF","Genomics",                "EQD",        None),
    "EDOC": ("Global X Telemedicine ETF",            "Digital Health",          "EQD",        None),
    "IDRV": ("iShares Self-Driving EV & Tech ETF",   "Autonomous Vehicles",     "EQD",        None),
    "KARS": ("KraneShares Electric Vehicles ETF",    "Electric Vehicles",       "EQD",        None),
    "KOMP": ("SPDR S&P Kensho New Economies ETF",    "Disruptive Innovation",   "EQD",        None),
    "HAIL": ("SPDR S&P Kensho Smart Mobility ETF",   "Smart Mobility",          "EQD",        None),
    "AIQ":  ("Global X Artificial Intelligence ETF", "Artificial Intelligence", "EQD",        None),
    "IRBO": ("iShares Robotics and AI Multisector ETF","Robotics / AI",         "EQD",        None),
    "CHAT": ("Roundhill Generative AI & Technology ETF","Generative AI",        "EQD",        None),
    # ── US Clean Energy / ESG ────────────────────────────────────────────────
    "QCLN": ("First Trust NASDAQ Clean Edge Green Energy ETF","Clean Energy",   "EQD",        None),
    "ACES": ("ALPS Clean Energy ETF",                "Clean Energy",            "EQD",        None),
    "FAN":  ("First Trust Global Wind Energy ETF",   "Wind Energy",             "EQD",        None),
    "PHO":  ("Invesco Water Resources ETF",          "Water",                   "EQD",        None),
    "FIW":  ("First Trust Water ETF",               "Water",                   "EQD",        None),
    "CGW":  ("Invesco S&P Global Water ETF",         "Water",                   "EQD",        None),
    "PAVE": ("Global X US Infrastructure Development ETF","Infrastructure",     "EQD",        None),
    "ESGD": ("iShares MSCI EAFE ESG Select ETF",    "International ESG",        "EQD",        None),
    "ESGE": ("iShares MSCI EM ESG Select ETF",      "EM ESG",                  "EQD",        None),
    "SUSA": ("iShares MSCI USA ESG Select ETF",     "US ESG",                  "EQD",        None),
    "CNRG": ("SPDR S&P Kensho Clean Power ETF",     "Clean Power",             "EQD",        None),
    # ── Resources / Commodities extras ───────────────────────────────────────
    "WOOD": ("iShares Global Timber & Forestry ETF", "Timber / Forestry",       "COMMO",      None),
    "PICK": ("iShares MSCI Global Metals & Mining ETF","Global Metals & Mining","COMMO",      None),
    "PALL": ("Aberdeen Physical Palladium ETF",      "Palladium",               "COMMO",      "Palladium → auto sector proxy"),
    "PPLT": ("Aberdeen Physical Platinum ETF",       "Platinum",                "COMMO",      "Platinum → mining proxy"),
    "CORN": ("Teucrium Corn ETF",                    "Corn / Agriculture",       "COMMO",      "Corn futures → ADM agribusiness proxy"),
    "WEAT": ("Teucrium Wheat ETF",                   "Wheat / Agriculture",      "COMMO",      "Wheat futures → ADM proxy"),
    "SOYB": ("Teucrium Soybean ETF",                 "Soybean / Agriculture",    "COMMO",      "Soybean futures → ADM proxy"),
    "GOAU": ("US Global GO GOLD and Precious Metal Miners ETF","Gold Miners",   "GOLD",       None),
    "RING": ("iShares MSCI Global Gold Miners ETF",  "Gold Miners",             "GOLD",       None),
    "SGDJ": ("Sprott Junior Gold Miners ETF",        "Junior Gold Miners",       "GOLD",       None),
    "CPER": ("United States Copper ETF",             "Copper Physical",          "COMMO",      "Copper → COPX proxy"),
    # ── Bond / Fixed Income ───────────────────────────────────────────────────
    "AGG":  ("iShares Core US Aggregate Bond ETF",   "US Aggregate Bond",        "BOND",       "US bonds → XLF financial proxy"),
    "BND":  ("Vanguard Total Bond Market ETF",       "US Total Bond",            "BOND",       "US bonds → XLF financial proxy"),
    "TLT":  ("iShares 20+ Year Treasury Bond ETF",   "US Long-Term Treasury",    "BOND",       "Long treasury → XLU utility proxy"),
    "IEF":  ("iShares 7-10 Year Treasury Bond ETF",  "US Intermediate Treasury", "BOND",       "Mid treasury → XLU utility proxy"),
    "SHY":  ("iShares 1-3 Year Treasury Bond ETF",   "US Short-Term Treasury",   "BOND",       "Short treasury → XLF financial proxy"),
    "GOVT": ("iShares US Treasury Bond ETF",         "US Treasury",              "BOND",       "US treasury → XLU proxy"),
    "VGLT": ("Vanguard Long-Term Treasury ETF",      "US Long-Term Treasury",    "BOND",       "Long treasury → XLU proxy"),
    "VGIT": ("Vanguard Intermediate-Term Treasury ETF","US Intermediate Treasury","BOND",      "Mid treasury → XLU proxy"),
    "VGSH": ("Vanguard Short-Term Treasury ETF",     "US Short-Term Treasury",   "BOND",       "Short treasury → XLF proxy"),
    "LQD":  ("iShares Investment Grade Corporate Bond ETF","IG Corporate Bond",  "BOND",       "IG bonds → XLF financial proxy"),
    "HYG":  ("iShares High Yield Corporate Bond ETF","High Yield Bond",          "BOND",       "HY bonds → XLF financial proxy"),
    "JNK":  ("SPDR Bloomberg High Yield Bond ETF",   "High Yield Bond",          "BOND",       "HY bonds → XLF financial proxy"),
    "BKLN": ("Invesco Senior Loan ETF",              "Senior Loans",             "BOND",       "Floating rate loans → XLF proxy"),
    "VCSH": ("Vanguard Short-Term Corporate Bond ETF","Short Corp Bond",          "BOND",       "Corp bonds → XLF proxy"),
    "VCIT": ("Vanguard Intermediate-Term Corporate Bond ETF","Mid Corp Bond",    "BOND",       "Corp bonds → XLF proxy"),
    "VCLT": ("Vanguard Long-Term Corporate Bond ETF","Long Corp Bond",           "BOND",       "Corp bonds → XLF proxy"),
    "TIP":  ("iShares TIPS Bond ETF",                "Inflation-Protected Bond", "BOND",       "TIPS → GLD/XLU inflation proxy"),
    "VTIP": ("Vanguard Short-Term Inflation-Protected Securities ETF","Short TIPS","BOND",     "Short TIPS → XLU proxy"),
    "SCHP": ("Schwab US TIPS ETF",                   "Inflation-Protected Bond", "BOND",       "TIPS → GLD/XLU proxy"),
    "EMB":  ("iShares JP Morgan USD EM Bond ETF",    "EM USD Bond",              "BOND",       "EM bonds → EEM equity proxy"),
    "PCY":  ("Invesco EM Sovereign Debt ETF",        "EM Sovereign Bond",        "BOND",       "EM sovereign → EEM proxy"),
    "MUB":  ("iShares National Muni Bond ETF",       "US Municipal Bond",        "BOND",       "Muni bonds → XLU proxy"),
    "HYD":  ("VanEck High Yield Muni ETF",           "High Yield Muni Bond",     "BOND",       "HY muni → XLF proxy"),
    "VTEB": ("Vanguard Tax-Exempt Bond ETF",         "US Muni Bond",             "BOND",       "Muni bonds → XLU proxy"),
    "BNDX": ("Vanguard Total International Bond ETF","International Bond",       "BOND",       "Intl bonds → EFA proxy"),
    "BWX":  ("SPDR Bloomberg International Treasury Bond ETF","Intl Treasury",   "BOND",       "Intl treasury → EFA proxy"),
    "IGOV": ("iShares International Treasury Bond ETF","Intl Treasury",          "BOND",       "Intl treasury → EFA proxy"),
    "PGX":  ("Invesco Preferred ETF",                "Preferred Stock",          "BOND",       "Preferred stock → XLF proxy"),
    "PFF":  ("iShares Preferred & Income Securities ETF","Preferred Stock",       "BOND",       "Preferred → XLF proxy"),
    "FLOT": ("iShares Floating Rate Bond ETF",       "Floating Rate Bond",       "BOND",       "Floating rate → XLF proxy"),
    "SGOV": ("iShares 0-3 Month Treasury Bond ETF",  "Ultra Short Treasury",     "BOND",       "Cash equivalent → XLF proxy"),
    "BIL":  ("SPDR Bloomberg 1-3 Month T-Bill ETF",  "Ultra Short Treasury",     "BOND",       "T-bills → XLF proxy"),
    "JPST": ("JPMorgan Ultra-Short Income ETF",      "Ultra Short Bond",         "BOND",       "Ultra short → XLF proxy"),
    "ANGL": ("VanEck Fallen Angel High Yield Bond ETF","Fallen Angel Bond",      "BOND",       "Fallen angels → XLF proxy"),
    "CWB":  ("SPDR Bloomberg Convertible Securities ETF","Convertible Bond",      "BOND",       "Convert bonds → XLK proxy"),
    # ── International / Regional ─────────────────────────────────────────────
    "AAXJ": ("iShares MSCI All Country Asia ex Japan ETF","Asia ex Japan",        "EQD",        None),
    "EMXC": ("iShares MSCI Emerging Markets ex China ETF","EM ex China",          "EQD",        None),
    "EEMV": ("iShares MSCI EM Min Vol Factor ETF",   "EM Low Volatility",        "EQD",        None),
    "DEM":  ("WisdomTree Emerging Markets High Dividend Fund","EM Dividend",       "EQD",        None),
    "FM":   ("iShares Frontier and Select EM ETF",   "Frontier Markets",         "EQD",        None),
    "VNM":  ("VanEck Vietnam ETF",                   "Vietnam",                  "EQD",        None),
    "ENZL": ("iShares MSCI New Zealand ETF",          "New Zealand",             "EQD",        None),
    "FLBR": ("Franklin FTSE Brazil ETF",             "Brazil",                   "EQD",        None),
    "FLIN": ("Franklin FTSE India ETF",              "India",                    "EQD",        None),
    "FLKR": ("Franklin FTSE South Korea ETF",        "South Korea",              "EQD",        None),
    "GREK": ("Global X MSCI Greece ETF",             "Greece",                   "EQD",        None),
    "TUR":  ("iShares MSCI Turkey ETF",              "Turkey",                   "EQD",        None),
    "ARGT": ("Global X MSCI Argentina ETF",          "Argentina",                "EQD",        None),
    "EWZS": ("iShares MSCI Brazil Small-Cap ETF",    "Brazil Small Cap",         "EQD",        None),
    "REET": ("iShares Global REIT ETF",              "Global Real Estate",        "REALESTATE", None),
    "REM":  ("iShares Mortgage Real Estate ETF",     "Mortgage REITs",            "REALESTATE", None),
    "MORT": ("VanEck Mortgage REIT Income ETF",      "Mortgage REITs",            "REALESTATE", None),
    "DXJ":  ("WisdomTree Japan Hedged Equity Fund",  "Japan Hedged",              "EQD",        "JPY hedged Japan equity"),
    "HEDJ": ("WisdomTree Europe Hedged Equity Fund",  "Europe Hedged",            "EQD",        "EUR hedged Europe equity"),
    "HEFA": ("iShares Currency Hedged MSCI EAFE ETF","EAFE Hedged",              "EQD",        "Currency hedged developed markets"),
    "BBCA": ("JPMorgan BetaBuilders Canada ETF",     "Canada",                   "EQD",        None),
    "BBEU": ("JPMorgan BetaBuilders Europe ETF",     "Europe",                   "EQD",        None),
    "BBJP": ("JPMorgan BetaBuilders Japan ETF",      "Japan",                    "EQD",        None),
    "BBEM": ("JPMorgan BetaBuilders EM ETF",         "Emerging Markets",          "EQD",        None),
    "AVUS": ("Avantis US Equity ETF",                "US Total Market",           "EQD",        None),
    "AVEM": ("Avantis Emerging Markets Equity ETF",  "Emerging Markets",          "EQD",        None),
    "AVDE": ("Avantis International Equity ETF",     "International",             "EQD",        None),
    "AVUV": ("Avantis US Small Cap Value ETF",       "US Small Cap Value",        "EQD",        None),
    "COWZ": ("Pacer US Cash Cows 100 ETF",           "US Free Cash Flow",         "EQD",        None),
    "FNDE": ("Schwab Fundamental EM Large Company ETF","EM Fundamental",          "EQD",        None),
    "KBWB": ("Invesco KBW Bank ETF",                 "US Large Banks",            "EQD",        None),
    "IAT":  ("iShares US Regional Banks ETF",        "US Regional Banks",         "EQD",        None),
    "QQMG": ("Invesco NASDAQ Next Gen 100 ETF",      "US Mid-Cap Tech",           "EQD",        None),
    "WOOD": ("iShares Global Timber & Forestry ETF", "Timber / Forestry",         "COMMO",      None),
    "GLTR": ("Aberdeen Physical Precious Metals Basket ETF","Precious Metals",    "COMMO",      "Physical gold/silver/platinum basket → GDX proxy"),
    # ── Developed Markets broad ──────────────────────────────────────────────
    "VEA":  ("Vanguard FTSE Developed Markets ETF",     "Developed Markets ex-US","EQD",        None),
    # ── Quality / Factor ─────────────────────────────────────────────────────
    "MOAT": ("VanEck Morningstar Wide Moat ETF",        "US Quality / Wide Moat", "EQD",        None),
    # ── US High Dividend ─────────────────────────────────────────────────────
    "SPYD": ("SPDR Portfolio S&P 500 High Dividend ETF","US High Dividend",        "EQD",        None),
    # ── Thematic / Mag7 ──────────────────────────────────────────────────────
    "MAGS": ("Roundhill Magnificent Seven ETF",         "US Mega Cap Tech",        "EQD",        None),
    # ── Spot Crypto ETFs (2024) ───────────────────────────────────────────────
    "IBIT": ("iShares Bitcoin Trust ETF",                "Bitcoin Spot",          "COMMO",      "Spot BTC → BITO futures proxy for pre-2024 data"),
    "FBTC": ("Fidelity Wise Origin Bitcoin ETF",         "Bitcoin Spot",          "COMMO",      "Spot BTC → BITO futures proxy for pre-2024 data"),
    "ETHA": ("iShares Ethereum Trust ETF",               "Ethereum Spot",         "COMMO",      "Spot ETH → BITO crypto proxy"),
    # ── Covered Call / Options Income ────────────────────────────────────────
    "DIVO": ("Amplify CWP Enhanced Dividend Income ETF", "Covered Call Income",   "EQD",        None),
    "NVDY": ("YieldMax NVDA Option Income ETF",          "Single-Stock Covered Call","EQD",     "NVDA covered call → QQQ tech proxy"),
    "TSLY": ("YieldMax TSLA Option Income ETF",          "Single-Stock Covered Call","EQD",     "TSLA covered call → XLY consumer disc proxy"),
    "RYLD": ("Global X Russell 2000 Covered Call ETF",  "Covered Call Income",   "EQD",        None),
    "TLTW": ("iShares 20+ Year Treasury Bond BuyWrite ETF","Long Treasury Covered Call","BOND", "TLT covered call → TLT bond proxy"),
    # ── Managed Futures / Alternatives ───────────────────────────────────────
    "DBMF": ("iMGP DBi Managed Futures Strategy ETF",   "Managed Futures",       "COMMO",      "Trend-following → XLE/GLD commodity proxy"),
    "KMLM": ("KFA Mount Lucas Index Strategy ETF",      "Managed Futures",       "COMMO",      "Trend-following → XLE/GLD commodity proxy"),
    "TAIL": ("Cambria Tail Risk ETF",                   "Tail Risk Hedge",       "BOND",       "Tail hedge → TLT/GLD safe haven proxy"),
    "VIXY": ("ProShares VIX Short-Term Futures ETF",    "VIX / Volatility",      "COMMO",      "VIX futures → inverse equity proxy"),
    # ── Commodities extras ────────────────────────────────────────────────────
    "PDBC": ("Invesco Optimum Yield Diversified Commodity No K-1 ETF","Diversified Commodity","COMMO","Commodity basket → XLE/GLD proxy"),
    "GUNR": ("FlexShares Global Upstream Natural Resources ETF","Natural Resources","COMMO",   None),
    "VEGI": ("iShares MSCI Agriculture Producers ETF",  "Agribusiness Producers","COMMO",      "Agri producers → MOO proxy"),
    "KRBN": ("KraneShares Global Carbon Strategy ETF",  "Carbon Credits",        "COMMO",      "Carbon → ICLN clean energy proxy"),
    # ── Thematic extras ───────────────────────────────────────────────────────
    "SNSR": ("Global X Internet of Things ETF",         "Internet of Things",    "EQD",        None),
    "WCBR": ("WisdomTree Cybersecurity Fund",           "Cybersecurity",         "EQD",        None),
    "HTEC": ("ROBO Global Healthcare Technology & Innovation ETF","Health Tech",  "EQD",        None),
    "BETZ": ("Roundhill Sports Betting & iGaming ETF",  "Sports Betting / iGaming","EQD",      None),
    "MSOS": ("AdvisorShares Pure US Cannabis ETF",      "Cannabis / Marijuana",  "EQD",        None),
    # ── Income / Credit ───────────────────────────────────────────────────────
    "BIZD": ("VanEck BDC Income ETF",                  "Business Development Companies","EQD", "BDCs → XLF financial proxy"),
    "PFFD": ("Global X US Preferred ETF",              "Preferred Stock",        "BOND",       "Preferred → XLF proxy"),
    # ── Fidelity sector ETFs ──────────────────────────────────────────────────
    "FTEC": ("Fidelity MSCI Information Technology ETF","US Technology",         "EQD",        None),
    "FHLC": ("Fidelity MSCI Health Care ETF",          "US Healthcare",          "EQD",        None),
}

ETF_LIST = list(ETF_META.keys())


# ── DB setup ───────────────────────────────────────────────────────────────────
def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS etf_info (
            ticker      TEXT PRIMARY KEY,
            name        TEXT,
            theme       TEXT,
            asset_class TEXT,
            proxy_rule  TEXT
        );

        CREATE TABLE IF NOT EXISTS top_holdings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            etf         TEXT NOT NULL,
            stock       TEXT NOT NULL,
            start_date  TEXT NOT NULL,
            end_date    TEXT,
            FOREIGN KEY (etf) REFERENCES etf_info(ticker)
        );

        CREATE INDEX IF NOT EXISTS idx_th_etf   ON top_holdings(etf);
        CREATE INDEX IF NOT EXISTS idx_th_stock ON top_holdings(stock);
    """)
    conn.commit()


def upsert_etf_info(conn: sqlite3.Connection):
    conn.executemany(
        "INSERT OR REPLACE INTO etf_info VALUES (?,?,?,?,?)",
        [(t, *m) for t, m in ETF_META.items()]
    )
    conn.commit()


def etf_done(conn: sqlite3.Connection, etf: str) -> bool:
    row = conn.execute("SELECT 1 FROM top_holdings WHERE etf=? LIMIT 1", (etf,)).fetchone()
    return row is not None


def save_periods(conn: sqlite3.Connection, etf: str, periods: list[dict]):
    conn.execute("DELETE FROM top_holdings WHERE etf=?", (etf,))
    conn.executemany(
        "INSERT INTO top_holdings (etf, stock, start_date, end_date) VALUES (?,?,?,?)",
        [(etf, p["stock"], p["start_date"], p.get("end_date")) for p in periods]
    )
    conn.commit()


# ── Compress raw holdings → periods ───────────────────────────────────────────
def to_periods(holdings: list[dict]) -> list[dict]:
    """
    Convert a list of {date, ticker} records into holding periods:
    [{stock, start_date, end_date}]  — end_date=None means still current.
    """
    if not holdings:
        return []
    sorted_h = sorted(holdings, key=lambda x: x["date"])
    periods = []
    prev_ticker = None
    period_start = None

    for h in sorted_h:
        t = h["ticker"]
        if t != prev_ticker:
            if prev_ticker is not None:
                periods.append({
                    "stock":      prev_ticker,
                    "start_date": period_start,
                    "end_date":   h["date"],
                })
            prev_ticker  = t
            period_start = h["date"]

    if prev_ticker:
        periods.append({
            "stock":      prev_ticker,
            "start_date": period_start,
            "end_date":   None,  # still current
        })
    return periods


# ── EDGAR fetch ────────────────────────────────────────────────────────────────
def fetch_from_edgar(etf: str) -> list[dict]:
    from edgar import Company, set_identity, find_fund
    from datetime import datetime
    from agents.agent2_holdings import _load_cusip_cache, _save_cusip_cache, openfigi_lookup, SEED_HOLDINGS

    set_identity("ETF Holdings DB Builder backtester@example.com")
    cusip_cache = _load_cusip_cache()
    results = []
    seen_quarters: set[str] = set()
    target_series_id = None

    try:
        fc = find_fund(etf)
        target_series_id = fc.series.series_id
        company = Company(fc.series.fund_company.cik)
    except Exception:
        try:
            company = Company(etf)
        except Exception as e:
            print(f"    Could not find {etf}: {e}")
            return []

    try:
        filings = list(company.get_filings(form="NPORT-P"))
    except Exception as e:
        print(f"    Could not get filings: {e}")
        return []

    print(f"    {len(filings)} filings")
    cache_dirty = False

    for filing in filings:
        if len(results) >= 40:
            break
        try:
            filing_date = getattr(filing, "filing_date", None) or getattr(filing, "date", None)
            if not filing_date:
                continue
            if hasattr(filing_date, "strftime"):
                date_ym = filing_date.strftime("%Y-%m")
                date_obj = filing_date
            else:
                date_obj = datetime.strptime(str(filing_date)[:10], "%Y-%m-%d")
                date_ym = str(filing_date)[:7]

            if date_ym in seen_quarters:
                continue

            fund = filing.data_object()

            if target_series_id:
                try:
                    gi = fund.general_info
                    if gi and gi.series_id and gi.series_id != target_series_id:
                        continue
                except Exception:
                    pass

            investments = getattr(fund, "investments", None)
            if not investments:
                continue

            top = sorted(investments, key=lambda x: (x.pct_value or 0), reverse=True)[0]
            ticker = top.ticker or None

            if not ticker and top.cusip:
                ticker = openfigi_lookup(str(top.cusip), cusip_cache)
                cache_dirty = True

            if not ticker:
                ticker = SEED_HOLDINGS.get((etf, date_ym))

            if ticker:
                seen_quarters.add(date_ym)
                results.append({
                    "date":   date_obj.strftime("%Y-%m-%d") if hasattr(date_obj, "strftime") else str(date_obj)[:10],
                    "ticker": str(ticker).strip().upper(),
                })
        except Exception:
            continue

    if cache_dirty:
        _save_cusip_cache(cusip_cache)

    return sorted(results, key=lambda x: x["date"])


def seed_holdings(etf: str) -> list[dict]:
    from agents.agent2_holdings import SEED_HOLDINGS
    return sorted(
        [{"date": f"{ym}-28", "ticker": tkr}
         for (e, ym), tkr in SEED_HOLDINGS.items() if e == etf],
        key=lambda x: x["date"]
    )


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    CACHE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    upsert_etf_info(conn)

    todo = [e for e in ETF_LIST if not etf_done(conn, e)]
    done = len(ETF_LIST) - len(todo)
    print(f"Holdings DB: {done} ETFs already built, {len(todo)} to fetch")
    print(f"DB: {DB_PATH}\n")

    if not todo:
        print("All done.")
        conn.close()
        return

    for i, etf in enumerate(todo):
        print(f"[{i+1}/{len(todo)}] {etf}  ({ETF_META.get(etf, ('?','?','?',None))[1]})")
        t0 = time.time()

        # Use seed data first if we have full coverage — avoids slow EDGAR for large ETF families
        seed = seed_holdings(etf)
        if len(seed) > 0:
            holdings = seed
            src = "seed"
        else:
            holdings = fetch_from_edgar(etf)
            if not holdings:
                holdings = seed
                src = "seed (partial)"
            else:
                src = "edgar"

        periods = to_periods(holdings)
        if periods:
            save_periods(conn, etf, periods)
            print(f"    {len(periods)} holding periods from {src} ({time.time()-t0:.0f}s)")
            for p in periods:
                end = p['end_date'] or 'present'
                print(f"      {p['stock']:8}  {p['start_date']} → {end}")
        else:
            print(f"    No data ({time.time()-t0:.0f}s)")

        time.sleep(0.5)

    conn.close()
    print(f"\nDone. DB saved → {DB_PATH}")
    print(f"Query it: python3.11 query_db.py \"SELECT * FROM etf_info\"")


if __name__ == "__main__":
    main()
