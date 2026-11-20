#!/usr/bin/env python3
"""
Synthetic Saudi merchant-fraud / AML dataset: 4 linked tables.

  customers.csv     KYC  (one row per customer)
  merchants.csv     KYB  (one row per merchant, CR number, CR director)
  devices.csv       device registry (os, browser, emulator flag ...)
  transactions.csv  checkout -> refund -> payout events, AMLNet-style columns

Column names (step, type, amount, nameOrig, nameDest, oldbalanceOrg, newbalanceOrig,
isFraud, isMoneyLaundering, laundering_typology, hour, day_of_week ...) follow AMLNet v2.0
so the two datasets can be concatenated / joined on nameOrig / nameDest conventions
(C... = customer, M... = merchant). Amounts are SAR, rails are Saudi.

Everything is random. No real people, IBANs, devices, merchants or IPs.
Columns prefixed gt_ are ground truth for evaluation: do NOT use them as model features.

Usage: python gen_saudi_aml_dataset.py --scale 1 --seed 7 --out out
"""
import argparse, hashlib, math, os, random
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- calendar
START = datetime(2025, 10, 13)            # same window as AMLNet v2.0 (13 Oct 2025 -> 27 Apr 2026)
DAYS = 195
END = START + timedelta(days=DAYS)
WHITE_FRIDAY = (datetime(2025, 11, 24), datetime(2025, 12, 2))
PRE_RAMADAN = (datetime(2026, 2, 8), datetime(2026, 2, 18))
RAMADAN = (datetime(2026, 2, 18), datetime(2026, 3, 20))      # approximate, moon-sighting dependent
EID = (datetime(2026, 3, 8), datetime(2026, 3, 21))
HW_NORM = [3, 2, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 5, 5, 6, 7, 8, 9, 10, 10, 8, 5]
HW_RAM = [8, 7, 5, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 7, 9, 10, 10, 9]
DOW_W = [1.0, 1.0, 1.0, 1.15, 1.25, 1.1, 1.0]                  # Mon..Sun (Fri/Sat weekend)

# ----------------------------------------------------------------------------- catalogue
CATS = {
    "groceries":            dict(mcc=5411, w=15, bnpl=.01, refund=.02, n=(3, 8), cross=["charger", "gift_card_steam", "recharge_card_50"]),
    "restaurants_cafes":    dict(mcc=5812, w=14, bnpl=.00, refund=.02, n=(1, 4), cross=[]),
    "fuel_convenience":     dict(mcc=5541, w=5,  bnpl=.00, refund=.01, n=(1, 2), cross=["recharge_card_50"]),
    "apparel":              dict(mcc=5651, w=11, bnpl=.30, refund=.12, n=(1, 3), cross=["perfume_50ml"]),
    "electronics":          dict(mcc=5732, w=8,  bnpl=.38, refund=.06, n=(1, 2), cross=["gift_card_psn", "headphones"]),
    "pharmacy_health":      dict(mcc=5912, w=7,  bnpl=.03, refund=.02, n=(1, 4), cross=["skincare"]),
    "home_furniture":       dict(mcc=5712, w=4,  bnpl=.42, refund=.05, n=(1, 2), cross=[]),
    "travel":               dict(mcc=4722, w=4,  bnpl=.25, refund=.07, n=(1, 2), cross=[]),
    "telecom_digital":      dict(mcc=4814, w=4,  bnpl=.00, refund=.01, n=(1, 2), cross=["gift_card_psn"]),
    "jewelry_gold":         dict(mcc=5944, w=3,  bnpl=.35, refund=.04, n=(1, 2), cross=[]),
    "beauty_perfume":       dict(mcc=5977, w=6,  bnpl=.20, refund=.05, n=(1, 3), cross=[]),
    "digital_gaming":       dict(mcc=5816, w=4,  bnpl=.05, refund=.03, n=(1, 2), cross=[]),
    "education":            dict(mcc=8299, w=3,  bnpl=.15, refund=.02, n=(1, 1), cross=[]),
    "auto_parts":           dict(mcc=5533, w=3,  bnpl=.15, refund=.04, n=(1, 3), cross=[]),
    "entertainment_events": dict(mcc=7999, w=3,  bnpl=.05, refund=.04, n=(1, 3), cross=[]),
    "home_services":        dict(mcc=7349, w=3,  bnpl=.05, refund=.03, n=(1, 1), cross=[]),
}
CAT_L = list(CATS)
ITEMS = {  # name: (true category, typical SAR price)
    "milk_pack": ("groceries", 12), "rice_5kg": ("groceries", 38), "dates_box": ("groceries", 45), "chicken_pack": ("groceries", 28),
    "olive_oil": ("groceries", 55), "coffee_beans": ("groceries", 48), "snack_bundle": ("groceries", 22), "cleaning_set": ("groceries", 35),
    "meal_combo": ("restaurants_cafes", 55), "coffee_drink": ("restaurants_cafes", 18), "dessert_box": ("restaurants_cafes", 40),
    "family_meal": ("restaurants_cafes", 140), "catering_tray": ("restaurants_cafes", 380), "fresh_juice": ("restaurants_cafes", 15),
    "fuel_topup": ("fuel_convenience", 120), "car_wash": ("fuel_convenience", 35), "convenience_snacks": ("fuel_convenience", 15), "engine_oil": ("fuel_convenience", 90),
    "thobe": ("apparel", 280), "abaya": ("apparel", 420), "sneakers": ("apparel", 360), "dress": ("apparel", 310),
    "tshirt": ("apparel", 90), "jeans": ("apparel", 180), "handbag": ("apparel", 520), "kids_set": ("apparel", 150),
    "smartphone": ("electronics", 2800), "laptop": ("electronics", 3600), "headphones": ("electronics", 450), "smartwatch": ("electronics", 1100),
    "tv_55in": ("electronics", 2400), "console_ps5": ("electronics", 1900), "tablet": ("electronics", 1700), "charger": ("electronics", 90),
    "vitamins": ("pharmacy_health", 85), "skincare": ("pharmacy_health", 140), "baby_formula": ("pharmacy_health", 95),
    "thermometer": ("pharmacy_health", 60), "supplements": ("pharmacy_health", 190), "first_aid_kit": ("pharmacy_health", 45),
    "sofa": ("home_furniture", 3200), "bed_frame": ("home_furniture", 2100), "dining_table": ("home_furniture", 2600),
    "curtains": ("home_furniture", 450), "rug": ("home_furniture", 800), "floor_lamp": ("home_furniture", 220), "kitchen_set": ("home_furniture", 600),
    "flight_domestic": ("travel", 650), "flight_intl": ("travel", 2400), "hotel_night": ("travel", 600), "umrah_package": ("travel", 3800), "car_rental": ("travel", 480),
    "recharge_card_50": ("telecom_digital", 50), "recharge_card_100": ("telecom_digital", 100), "data_pack": ("telecom_digital", 120), "home_fiber": ("telecom_digital", 250),
    "gold_ring": ("jewelry_gold", 1400), "gold_necklace": ("jewelry_gold", 4800), "silver_bracelet": ("jewelry_gold", 350),
    "luxury_watch": ("jewelry_gold", 6500), "gold_coin": ("jewelry_gold", 2650), "diamond_earrings": ("jewelry_gold", 5200),
    "perfume_oud": ("beauty_perfume", 650), "perfume_50ml": ("beauty_perfume", 380), "makeup_kit": ("beauty_perfume", 320),
    "bakhoor": ("beauty_perfume", 120), "hair_care": ("beauty_perfume", 150),
    "game_code": ("digital_gaming", 180), "streaming_subscription": ("digital_gaming", 55), "in_game_currency": ("digital_gaming", 100),
    "gift_card_psn": ("digital_gaming", 200), "gift_card_steam": ("digital_gaming", 150),
    "course_fee": ("education", 1200), "textbooks": ("education", 320), "tutoring_pack": ("education", 900), "language_course": ("education", 1500),
    "tires_set": ("auto_parts", 1800), "car_battery": ("auto_parts", 450), "brake_pads": ("auto_parts", 380), "oil_filter": ("auto_parts", 40),
    "event_ticket": ("entertainment_events", 280), "theme_park_pass": ("entertainment_events", 190), "cinema_pack": ("entertainment_events", 120),
    "cleaning_service": ("home_services", 250), "maintenance_visit": ("home_services", 300), "moving_service": ("home_services", 900),
    "prepaid_visa_card": ("prepaid_financial", 500),
}
CAT_ITEMS = {c: [k for k, v in ITEMS.items() if v[0] == c] for c in CATS}
RING_ITEMS = ["gold_coin", "smartphone", "laptop", "console_ps5", "gift_card_psn", "gift_card_steam",
              "prepaid_visa_card", "luxury_watch", "perfume_oud", "tablet"]
RING_MERCHANT_CATS = ["restaurants_cafes", "groceries", "home_services", "entertainment_events", "education"]
ABUSE_MERCHANT_CATS = ["apparel", "beauty_perfume", "digital_gaming", "home_services", "electronics", "entertainment_events"]
SADAD_CATS = {"telecom_digital", "education", "travel", "home_services"}
SEAS_CATS = {"electronics": WHITE_FRIDAY, "apparel": EID, "beauty_perfume": EID, "jewelry_gold": EID,
             "home_furniture": WHITE_FRIDAY, "groceries": PRE_RAMADAN, "restaurants_cafes": PRE_RAMADAN,
             "digital_gaming": WHITE_FRIDAY}

PM_AR = {"mada": "مدى", "visa": "فيزا", "mastercard": "ماستركارد", "apple_pay": "أبل باي", "stc_pay": "STC Pay",
         "sadad": "سداد", "iban_transfer": "تحويل بنكي",
         "bnpl_tabby": "دفع أو تقسيط", "bnpl_tamara": "دفع أو تقسيط", "bnpl_postpay": "دفع أو تقسيط"}
FEE = {"mada": .009, "visa": .021, "mastercard": .021, "apple_pay": .018, "stc_pay": .015, "sadad": .007,
       "bnpl_tabby": .055, "bnpl_tamara": .055, "bnpl_postpay": .055}
COUNTRIES = ["SA", "AE", "US", "GB", "BH", "KW", "EG", "TR", "DE", "IN"]
COUNTRY_W = [.962, .012, .007, .005, .004, .003, .003, .002, .001, .001]
BANKS = ["80", "10", "45", "20", "30", "05", "15", "55", "60", "65"]
BANK_W = [.30, .22, .10, .10, .08, .07, .05, .04, .02, .02]
CITY_CR = {"Riyadh": "1010", "Jeddah": "4030", "Dammam": "2050", "Khobar": "2051", "Makkah": "4031",
           "Madinah": "4650", "Buraidah": "1131", "Abha": "5855", "Tabuk": "3550", "Taif": "4032"}
CITY_L = list(CITY_CR)
CITY_W = [.34, .22, .09, .07, .08, .07, .04, .04, .03, .02]
NAT = ["SA", "EG", "IN", "PK", "YE", "BD", "SD", "PH", "JO", "SY"]
NAT_W = [.68, .06, .05, .05, .04, .03, .03, .02, .02, .02]
OCC = ["employee_private", "employee_government", "self_employed", "student", "business_owner", "retired", "homemaker", "unemployed"]
OCC_W = [.32, .26, .12, .10, .07, .04, .05, .04]
OS_L = ["Android", "iOS", "Windows", "macOS", "Linux"]
OS_W = [.60, .34, .04, .015, .005]
BROWSERS = {
    "Android": [("Chrome", .68), ("Samsung Internet", .14), ("App WebView", .10), ("Firefox", .03), ("Opera", .05)],
    "iOS": [("Safari", .62), ("Chrome", .18), ("App WebView", .20)],
    "Windows": [("Chrome", .62), ("Edge", .28), ("Firefox", .07), ("Opera", .03)],
    "macOS": [("Safari", .55), ("Chrome", .40), ("Firefox", .05)],
    "Linux": [("Chrome", .6), ("Firefox", .4)],
}
OSV = {"Android": (12, 16), "iOS": (17, 26), "Windows": (10, 11), "macOS": (13, 15), "Linux": (0, 0)}
MODELS = {"Android": ["Galaxy S24", "Galaxy A55", "Galaxy A15", "Redmi Note 13", "Pixel 8", "Oppo Reno 11", "Honor 90", "Galaxy S23"],
          "iOS": ["iPhone 12", "iPhone 13", "iPhone 14", "iPhone 15", "iPhone 16", "iPad 10"],
          "Windows": ["Windows PC"], "macOS": ["MacBook Air", "MacBook Pro"], "Linux": ["Linux PC"]}
NAME_A = ["Al Noor", "Najd", "Hijaz", "Tihama", "Al Amal", "Al Wafa", "Al Bayan", "Al Reef", "Qimam", "Rawabi",
          "Sahab", "Al Majd", "Durrat", "Bawabat", "Tamayoz", "Al Fajr", "Mazaya", "Al Ofuq", "Sanabil", "Al Shams"]
NAME_B = {"groceries": ["Supermarket", "Market"], "restaurants_cafes": ["Kitchen", "Cafe"], "fuel_convenience": ["Station", "Convenience"],
          "apparel": ["Fashion", "Boutique"], "electronics": ["Electronics", "Tech"], "pharmacy_health": ["Pharmacy", "Care"],
          "home_furniture": ["Furniture", "Home"], "travel": ["Travel", "Tours"], "telecom_digital": ["Telecom", "Digital"],
          "jewelry_gold": ["Jewelry", "Gold"], "beauty_perfume": ["Perfumes", "Beauty"], "digital_gaming": ["Games", "Digital"],
          "education": ["Academy", "Institute"], "auto_parts": ["Auto Parts", "Motors"], "entertainment_events": ["Events", "Entertainment"],
          "home_services": ["Services", "Maintenance"]}


def H(*p, n=16):
    return hashlib.sha256("|".join(map(str, p)).encode()).hexdigest()[:n]


# ----------------------------------------------------------------------------- global state (set in main)
rnd = rng = None
C = M = None
DEV = []
USED = set()
KEY = [0]
CIDX, MIDX, IBAN2C = {}, {}, {}
HOME_IP = HOME_SUB = MOB_IP = MOB_SUB = None
OPEN = {}


def nk():
    KEY[0] += 1
    return KEY[0]


def R(**kw):
    kw["_key"] = nk()
    return kw


def make_iban(bank=None):
    bank = bank or rnd.choices(BANKS, BANK_W)[0]
    acct = "".join(rnd.choice("0123456789") for _ in range(18))
    bban = bank + acct
    chk = 98 - (int(bban + "281000") % 97)       # SA -> 28 10, then 00
    return f"SA{chk:02d}{bban}", bank


# ----------------------------------------------------------------------------- devices
def add_device(kind, first_seen, os_=None, browser=None, emu=False):
    if os_ is None:
        if kind == "merchant_console":
            os_ = rnd.choices(["Windows", "macOS", "Android"], [.65, .25, .10])[0]
        else:
            os_ = rnd.choices(OS_L, OS_W)[0]
    if browser is None:
        names, w = zip(*BROWSERS[os_])
        browser = rnd.choices(names, w)[0]
    lo, hi = OSV[os_]
    DEV.append(dict(device_kind=kind, os=os_, os_version=f"{os_} {rnd.randint(lo, hi)}" if hi else "Linux",
                    browser=browser, browser_version=rnd.randint(138, 147),
                    device_model="generic_emulator" if emu else rnd.choice(MODELS[os_]),
                    is_emulator=int(emu or rnd.random() < .004),
                    language="en" if emu else rnd.choices(["ar", "en"], [.72, .28])[0],
                    timezone="UTC" if emu and rnd.random() < .6 else "Asia/Riyadh",
                    first_seen=first_seen))
    return len(DEV) - 1


def devinfo(i):
    if i is None:
        return (None, "server", "api_batch")
    d = DEV[i]
    return (f"D{i:07d}", d["os"], d["browser"])


# ----------------------------------------------------------------------------- baskets / payments
def make_basket(cat, pool=None, n_items=None):
    lo, hi = CATS[cat]["n"]
    n = n_items or rnd.randint(lo, hi)
    lines = []
    for _ in range(n):
        if pool is None and CATS[cat]["cross"] and rnd.random() < .04:
            nm = rnd.choice(CATS[cat]["cross"])
        else:
            nm = rnd.choice(pool or CAT_ITEMS[cat])
        base = ITEMS[nm][1]
        price = round(base * math.exp(rnd.gauss(0, .12)), 2)
        r = rnd.random()
        qty = 1 if r < .85 else (2 if r < .97 else 3)
        if base < 60 and rnd.random() < .5:
            qty += rnd.randint(0, 3)
        lines.append((nm, qty, price))
    return lines


def ring_basket():
    for _ in range(50):
        lines = make_basket("electronics", pool=RING_ITEMS, n_items=rnd.choice([1, 1, 2]))
        lines = [(n, 1, p) for n, _, p in lines]
        tot = sum(p for _, _, p in lines)
        if 700 <= tot <= 9500:
            return lines
    return lines


def basket_stats(lines, declared):
    tot = sum(q * p for _, q, p in lines)
    by = defaultdict(float)
    for nm, q, p in lines:
        by[ITEMS[nm][0]] += q * p
    actual = max(by, key=by.get)
    off = sum(v for k, v in by.items() if k != declared)
    return round(tot, 2), actual, (round(off / tot, 3) if tot else 0.0)


def bstr(lines):
    return "|".join(f"{n}:{q}:{p:.2f}" for n, q, p in lines)


def choose_payment(cat, amount, age, force_bnpl=None):
    p = CATS[cat]["bnpl"] * (1.5 if age < 30 else (1.0 if age < 45 else .5))
    if force_bnpl is None:
        force_bnpl = 150 <= amount <= 15000 and rnd.random() < p
    if force_bnpl:
        prov = rnd.choices(["tabby", "tamara", "postpay"], [.42, .46, .12])[0]
        n = 4 if prov in ("tabby", "postpay") else rnd.choices([3, 4, 6, 12], [.15, .45, .30, .10])[0]
        return "bnpl", prov, n
    w = [.62, .22, .08, .08 if cat in SADAD_CATS else 0]
    return rnd.choices(["card", "apple_pay", "stc_pay", "sadad"], w)[0], None, 0


# ----------------------------------------------------------------------------- row builders
def ip_pick(c):
    if rnd.random() < .72:
        i = C["home_ip"][c]
        return HOME_IP[i], HOME_SUB[i // 6]
    i = int(rnd.paretovariate(1.1)) % len(MOB_IP)
    return MOB_IP[i], MOB_SUB[i // 8]


def checkout_row(c, m, ts, ov=None):
    ov = ov or {}
    cat = M["declared_category"][m]
    lines = ov.get("lines") or make_basket(cat)
    amount, actual, off = basket_stats(lines, cat)
    dev = ov["device"] if ov.get("device") is not None else rnd.choice(C["dev"][c])
    did, dos, dbr = devinfo(dev)
    age = int((ts - C["dob"][c]).days / 365.25)
    if ov.get("kind"):
        kind, prov, ninst = ov["kind"], None, 0
    else:
        kind, prov, ninst = choose_payment(cat, amount, age, ov.get("force_bnpl"))
    if kind == "apple_pay" and dos not in ("iOS", "macOS"):
        kind = "card"
    ch, sch = "", ""
    if kind in ("card", "apple_pay", "bnpl"):
        ch, sch = ov.get("card") or rnd.choice(C["cards"][c])
    elif kind == "stc_pay":
        ch, sch = H("wallet", C["customer_id"][c]), "wallet"
    if kind == "bnpl":
        pm, rail = f"bnpl_{prov}", "BNPL"
    elif kind == "card":
        pm, rail = sch, ("MADA" if sch == "mada" else "CARD")
    elif kind == "apple_pay":
        pm, rail = "apple_pay", "APPLE_PAY"
    elif kind == "stc_pay":
        pm, rail = "stc_pay", "WALLET"
    else:
        pm, rail = "sadad", "SADAD"
    iph, sub = ov.get("ip") or ip_pick(c)
    country = ov.get("country") or rnd.choices(COUNTRIES, COUNTRY_W)[0]
    vpn = ov["vpn"] if "vpn" in ov else int(rnd.random() < .008)
    return R(timestamp=ts, type=rail, txn_kind="checkout", is_from_store=0, amount=amount,
             nameOrig=C["customer_id"][c], nameDest=M["merchant_id"][m],
             customer_id=C["customer_id"][c], merchant_id=M["merchant_id"][m],
             payment_method=pm, is_installment=int(kind == "bnpl"), installment_count=ninst,
             installment_provider=prov, card_scheme=sch or None, card_hash=ch or None,
             device_id=did, os=dos, browser=dbr, ip_hash=iph, ip_subnet_hash=sub,
             is_vpn_or_proxy=vpn, origin_country=country,
             basket_items=bstr(lines), basket_actual_category=actual, basket_mismatch_score=off)


def merchant_ctx(m):
    return (devinfo(M["console_dev"][m]), H("mip", M["merchant_id"][m]), H("msub", M["merchant_id"][m]))


def refund_row(ck, ts, frac=1.0, ov=None):
    ov = ov or {}
    m = MIDX[ck["merchant_id"]]
    (did, dos, dbr), iph, sub = merchant_ctx(m)
    kw = dict(timestamp=ts, type=ck["type"], txn_kind="refund", is_from_store=1,
              amount=round(ck["amount"] * frac, 2), nameOrig=ck["merchant_id"], nameDest=ck["customer_id"],
              customer_id=ck["customer_id"], merchant_id=ck["merchant_id"],
              payment_method=ck["payment_method"], is_installment=ck["is_installment"],
              installment_count=ck["installment_count"], installment_provider=ck["installment_provider"],
              card_scheme=ck["card_scheme"], card_hash=ck["card_hash"],
              device_id=did, os=dos, browser=dbr, ip_hash=iph, ip_subnet_hash=sub, is_vpn_or_proxy=0, origin_country="SA",
              basket_items=ck["basket_items"], basket_actual_category=ck["basket_actual_category"],
              basket_mismatch_score=ck["basket_mismatch_score"], _ref=ck["_key"],
              minutes_since_checkout=round((ts - ck["timestamp"]).total_seconds() / 60, 1),
              refund_to_different_instrument=0)
    kw.update(ov)
    return R(**kw)


def payout_row(m, ts, amount, n_cov, dest_id=None, dev=None):
    mid = M["merchant_id"][m]
    iban = M["iban"][m]
    dest = dest_id or IBAN2C.get(iban) or "S" + mid[1:]
    did, dos, dbr = devinfo(dev)
    (_, _, _), iph, sub = merchant_ctx(m)
    return R(timestamp=ts, type="SARIE", txn_kind="payout", is_from_store=1, amount=round(amount, 2),
             nameOrig=mid, nameDest=dest, customer_id=IBAN2C.get(iban), merchant_id=mid,
             payment_method="iban_transfer", is_installment=0, installment_count=0, counterparty_iban=iban,
             device_id=did, os=dos, browser=dbr, ip_hash=iph if dev is not None else None,
             ip_subnet_hash=sub if dev is not None else None, is_vpn_or_proxy=0, origin_country="SA",
             payout_covers_n_checkouts=n_cov)


def p2p_row(src, dst, ts, amount, dev=None, ip=None):
    dev = dev if dev is not None else rnd.choice(C["dev"][src])
    did, dos, dbr = devinfo(dev)
    iph, sub = ip or ip_pick(src)
    return R(timestamp=ts, type="SARIE", txn_kind="p2p_transfer", is_from_store=0, amount=round(amount, 2),
             nameOrig=C["customer_id"][src], nameDest=C["customer_id"][dst], customer_id=C["customer_id"][src],
             payment_method="iban_transfer", is_installment=0, installment_count=0, counterparty_iban=C["iban"][dst],
             device_id=did, os=dos, browser=dbr, ip_hash=iph, ip_subnet_hash=sub, is_vpn_or_proxy=0, origin_country="SA")


def label(row, fraud, ml, typ, stype, sid="", hn=0):
    row.update(isFraud=fraud, isMoneyLaundering=ml, laundering_typology=typ,
               gt_scenario_type=stype, gt_scenario_id=sid, gt_hard_negative=hn)
    return row


# ----------------------------------------------------------------------------- entities
def new_merchant(cat, onboard, role="normal", sid="", iban=None, director=None, cr_issue=None, kyb=None,
                 risk=None, phone=None, email=None, pop=None, city=None):
    i = len(M["merchant_id"])
    mid = f"M{100000000 + i}"
    city = city or rnd.choices(CITY_L, CITY_W)[0]
    cr_issue = cr_issue or onboard - timedelta(days=rnd.uniform(0, 800))
    iban, bank = (iban, iban[6:8]) if iban else make_iban()
    row = dict(
        merchant_id=mid,
        legal_name=f"{rnd.choice(NAME_A)} {rnd.choice(NAME_B[cat])} {rnd.choices(['Est.', 'Co.', 'LLC'], [.5, .2, .3])[0]}",
        legal_form=rnd.choices(["sole_establishment", "llc", "simplified_jsc", "branch_foreign"], [.55, .38, .04, .03])[0],
        city=city, cr_number=CITY_CR[city] + "".join(rnd.choice("0123456789") for _ in range(6)),
        cr_issue_date=cr_issue.date(), cr_expiry_date=(cr_issue + timedelta(days=365 * rnd.choice([1, 2, 3, 5]))).date(),
        cr_status="active", vat_number="3" + "".join(rnd.choice("0123456789") for _ in range(13)) + "3",
        vat_registered=int(rnd.random() < .9), declared_category=cat, mcc=CATS[cat]["mcc"],
        onboarding_date=onboard, kyb_status=kyb or rnd.choices(["verified", "simplified_review", "pending_documents"], [.93, .04, .03])[0],
        kyb_risk_score=risk if risk is not None else round(rnd.betavariate(2, 9), 3),
        kyb_last_review_date=(onboard + timedelta(days=rnd.uniform(0, 90))).date(),
        expected_monthly_volume_sar=int(math.exp(rnd.gauss(10.8, .9))),
        employees_band=rnd.choices(["1-5", "6-20", "21-100", "100+"], [.45, .35, .15, .05])[0],
        has_physical_store=int(rnd.random() < .6),
        email_domain_type=email or rnd.choices(["business", "free_mail"], [.7, .3])[0],
        phone_hash=phone or H("mphone", mid), iban=iban, settlement_bank_code=bank,
        cr_director_id_hash=director or H("dir", mid), cr_director_pep_flag=int(rnd.random() < .01),
        gt_role=role, gt_scenario_id=sid,
        pop=pop if pop is not None else rnd.lognormvariate(0, 1.1), refund_mult=1.0,
        console_dev=add_device("merchant_console", onboard),
        opening=math.exp(rnd.gauss(10.5, .8)))
    for k, v in row.items():
        M[k].append(v)
    MIDX[mid] = i
    return i


def pick(k, newbias=0.0, at=None):
    out = []
    while len(out) < k:
        c = rnd.randrange(len(C["customer_id"]))
        if c in USED:
            continue
        if newbias and at is not None and (at - C["account_open_date"][c]).days > 200 and rnd.random() < newbias:
            continue
        USED.add(c)
        out.append(c)
    return out


def rand_ts(lo):
    d0 = max(lo, START)
    span = (END - d0).total_seconds()
    if span < 2 * 86400:
        return None
    day = d0.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=rnd.randrange(int(span // 86400) - 1))
    return day + timedelta(hours=rnd.choices(range(24), HW_NORM)[0], minutes=rnd.uniform(0, 59.9))


# ----------------------------------------------------------------------------- scenarios
def make_family(f, pool_rows, new_legit, n_base_m):
    sid = f"FAM_{f:03d}"
    mem = pick(rnd.randint(3, 6))
    p = mem[0]
    C["dob"][p] = START - timedelta(days=rnd.uniform(38, 60) * 365.25)
    for c in mem:
        C["city"][c] = C["city"][p]
        C["home_ip"][c] = C["home_ip"][p]
        C["nationality"][c] = C["nationality"][p]
        C["gt_role"][c] = "family_member"
        C["gt_scenario_id"][c] = sid
        if c != p:
            C["dob"][c] = START - timedelta(days=rnd.uniform(18, 32) * 365.25)
    for c in mem:
        C["age"][c] = int((START - C["dob"][c]).days / 365.25)
    shared = add_device("shared_home", START - timedelta(days=rnd.uniform(60, 900)),
                        os_=rnd.choice(["iOS", "Windows", "Android"]))
    for c in mem:
        C["dev"][c].append(shared)
    pcard = C["cards"][p][0]
    for c in mem:
        for _ in range(rnd.randint(5, 20)):
            m = rnd.choice(new_legit) if (new_legit and rnd.random() < .3) else rnd.randrange(n_base_m)
            ts = rand_ts(max(C["account_open_date"][c], M["onboarding_date"][m]))
            if ts is None:
                continue
            ov = {}
            if rnd.random() < .55:
                ov["device"] = shared
            if rnd.random() < .40:
                ov["card"] = pcard
            pool_rows.append(label(checkout_row(c, m, ts, ov), 0, 0, "normal", "hn_family_shared_device", sid, 1))
    for mo in range(6):                      # allowance / sibling transfers
        for kid in mem[1:]:
            ts = START + timedelta(days=30 * mo + rnd.uniform(0, 5), hours=rnd.uniform(8, 22))
            if ts < END:
                pool_rows.append(label(p2p_row(p, kid, ts, rnd.choice([300, 500, 800, 1000, 1500]), dev=shared),
                                       0, 0, "normal", "hn_family_shared_device", sid, 1))
    for _ in range(rnd.randint(2, 6)):
        a, b = rnd.sample(mem, 2)
        ts = rand_ts(START)
        pool_rows.append(label(p2p_row(a, b, ts, rnd.uniform(40, 600)), 0, 0, "normal", "hn_family_shared_device", sid, 1))


def custom_payouts(m, rows, rows_out, win_h=36, dev_p=.6, sid="", ring=True, nominee=None):
    """rapid payouts (every ~36h) covering all checkouts of m in rows. returns list of (payout_row, amount)."""
    rows = sorted(rows, key=lambda r: r["timestamp"])
    t0 = rows[0]["timestamp"]
    groups = defaultdict(list)
    for r in rows:
        groups[int((r["timestamp"] - t0).total_seconds() // (win_h * 3600))].append(r)
    outs = []
    for g in sorted(groups):
        g_rows = groups[g]
        net = sum(r["amount"] * (1 - FEE.get(r["payment_method"], .02)) for r in g_rows)
        ts = g_rows[-1]["timestamp"] + timedelta(hours=rnd.uniform(2, 14))
        if ts >= END:
            continue
        dev = M["console_dev"][m] if rnd.random() < dev_p else None
        pr = payout_row(m, ts, net, len(g_rows), dev=dev)
        pr["minutes_since_checkout"] = round((ts - g_rows[-1]["timestamp"]).total_seconds() / 60, 1)
        outs.append(pr)
    return outs


def make_ring(r, scn_rows):
    sid = f"RING_{r:03d}"
    size = rnd.randint(5, 9)
    t0 = START + timedelta(days=rnd.uniform(14, DAYS - 40), hours=rnd.uniform(0, 24))
    members = pick(size, newbias=.6, at=t0)
    for c in members:                                         # accounts opened shortly before the ring starts
        if rnd.random() < .6 or C["account_open_date"][c] >= t0 - timedelta(days=2):
            C["account_open_date"][c] = t0 - timedelta(days=rnd.uniform(3, 45))
            C["kyc_verified_date"][c] = C["account_open_date"][c] + timedelta(days=rnd.uniform(0, 2))
            C["kyc_level"][c] = rnd.choices(["basic", "standard"], [.7, .3])[0]
        C["gt_role"][c] = "ring_member"
        C["gt_scenario_id"][c] = sid
    k = 2 if size < 7 else rnd.choice([2, 3])
    rnd.shuffle(members)
    clusters = [members[i::k] for i in range(k)]
    emu = rnd.random() < .3
    cdev = [add_device("ring_shared", t0 - timedelta(days=rnd.uniform(1, 30)), emu=emu,
                       os_="Windows" if emu else None) for _ in clusters]
    for cl, d in zip(clusters, cdev):
        for c in cl:
            C["dev"][c].append(d)
    bridges = []                                              # multi-hop: clusters linked by a weaker identifier
    shared_ip_all = H("ipfarm_all", sid)
    for i in range(1, k):
        b = rnd.choice(["card", "phone", "ip"])
        bridges.append(b)
        a, c2 = rnd.choice(clusters[0]), rnd.choice(clusters[i])
        if b == "card":
            C["cards"][c2][0] = C["cards"][a][0]
        elif b == "phone":
            C["phone_hash"][c2] = C["phone_hash"][a]
    ip_cluster = [(H("ipfarm", sid, i), H("farm_sub", sid, 0 if "ip" in bridges else i)) for i in range(k)]
    # merchant, linked back to the ring through IBAN and/or CR director
    mode = r % 3                                              # 0: IBAN only, 1: CR director only, 2: both
    link_iban = mode in (0, 2)
    link_dir = mode in (1, 2)
    nominee = rnd.choice(clusters[0])
    director_c = rnd.choice(members)
    cat = rnd.choice(RING_MERCHANT_CATS)
    onboard = t0 - timedelta(days=rnd.uniform(2, 35))
    revived = rnd.random() < .3
    m_phone = C["phone_hash"][rnd.choice(members)] if rnd.random() < .25 else None
    m = new_merchant(cat, onboard, role="ring_merchant", sid=sid,
                     iban=C["iban"][nominee] if link_iban else None,
                     director=C["national_id_hash"][director_c] if link_dir else None,
                     cr_issue=(onboard - timedelta(days=rnd.uniform(700, 2200))) if revived else (onboard - timedelta(days=rnd.uniform(5, 60))),
                     kyb=rnd.choices(["verified", "simplified_review", "pending_documents"], [.55, .20, .25])[0],
                     risk=round(rnd.uniform(.3, .75), 3), phone=m_phone,
                     email=rnd.choices(["free_mail", "business"], [.7, .3])[0], pop=0.0)
    if rnd.random() < .5:                                     # operator logs into the merchant console from a ring device
        M["console_dev"][m] = rnd.choice(cdev)
    M["expected_monthly_volume_sar"][m] = int(rnd.uniform(15000, 60000))
    active = rnd.uniform(8, 25)
    ck_rows = []
    for ci, cl in enumerate(clusters):
        bursts = [t0 + timedelta(days=rnd.uniform(0, active), hours=rnd.uniform(0, 5)) for _ in range(rnd.randint(2, 4))]
        for c in cl:
            for _ in range(rnd.randint(3, 10)):
                ts = rnd.choice(bursts) + timedelta(minutes=rnd.uniform(0, 150))
                foreign = rnd.random() < .18
                ov = dict(lines=ring_basket() if rnd.random() < .65 else make_basket(cat), force_bnpl=rnd.random() < .7,
                          device=cdev[ci] if rnd.random() < .88 else None,
                          ip=ip_cluster[ci] if rnd.random() < .75 else None,
                          country=rnd.choice(["AE", "TR", "US", "GB", "NL", "DE"]) if foreign else None,
                          vpn=int(foreign and rnd.random() < .7))
                ck_rows.append(label(checkout_row(c, m, ts, ov), 1, 1, "layering", "collusion_ring", sid))
    cover = []
    for _ in range(rnd.randint(8, 35)):                       # honest-looking organic traffic on the same merchant
        c = rnd.randrange(len(C["customer_id"]))
        ts = rand_ts(onboard + timedelta(days=1))
        if ts is None or ts > t0 + timedelta(days=active + 3) or c in members:
            continue
        if ts < C["account_open_date"][c]:
            continue
        cover.append(label(checkout_row(c, m, ts), 0, 0, "normal", "normal", ""))
    scn_rows += ck_rows + cover
    for pr in custom_payouts(m, ck_rows + cover, scn_rows):
        is_ring = True
        label(pr, 1, 1, "integration", "collusion_ring", sid)
        scn_rows.append(pr)
        if link_iban:                                         # nominee redistributes to the other members
            others = [c for c in members if c != nominee]
            recips = rnd.sample(others, min(len(others), rnd.randint(2, 4)))
            tot = pr["amount"] * rnd.uniform(.85, .95)
            cuts = np.random.default_rng(KEY[0]).dirichlet(np.ones(len(recips))) * tot
            for rc, amt in zip(recips, cuts):
                ts = pr["timestamp"] + timedelta(hours=rnd.uniform(.3, 8))
                if ts < END:
                    scn_rows.append(label(p2p_row(nominee, rc, ts, amt, dev=rnd.choice(cdev)),
                                          1, 1, "integration", "collusion_ring", sid))


def make_abuse(a, scn_rows):
    sid = f"ABUSE_{a:03d}"
    t0 = START + timedelta(days=rnd.uniform(10, DAYS - 30))
    accs = pick(rnd.choice([1, 2, 2, 3]), newbias=.3, at=t0)
    for c in accs:
        if C["account_open_date"][c] >= t0 - timedelta(days=2):
            C["account_open_date"][c] = t0 - timedelta(days=rnd.uniform(5, 90))
            C["kyc_verified_date"][c] = C["account_open_date"][c] + timedelta(days=1)
        C["gt_role"][c] = "refund_abuse_accomplice"
        C["gt_scenario_id"][c] = sid
    cat = rnd.choice(ABUSE_MERCHANT_CATS)
    onboard = t0 - timedelta(days=rnd.uniform(15, 220))
    m = new_merchant(cat, onboard, role="refund_abuse_merchant", sid=sid,
                     director=C["national_id_hash"][accs[0]] if rnd.random() < .35 else None,
                     risk=round(rnd.uniform(.2, .6), 3), pop=0.0)
    shared = None
    if len(accs) > 1 and rnd.random() < .5:
        shared = add_device("customer", t0 - timedelta(days=rnd.uniform(1, 20)))
        for c in accs:
            C["dev"][c].append(shared)
    t = t0
    for cyc in range(rnd.randint(4, 14)):
        acc = rnd.choice(accs)
        t += timedelta(hours=rnd.uniform(2, 36))
        if t > END - timedelta(days=2):
            break
        lines = make_basket(cat) if rnd.random() < .6 else ring_basket()
        if sum(q * p for _, q, p in lines) < 300:
            lines = ring_basket()
        foreign = rnd.random() < .3
        ov = dict(lines=lines, kind="card", card=(H("stolen", sid, cyc), rnd.choice(["visa", "mastercard"])),
                  device=shared, country=rnd.choice(["AE", "TR", "US", "GB"]) if foreign else None, vpn=int(foreign))
        ck = checkout_row(acc, m, t, ov)
        label(ck, 1, 0, "normal", "refund_payout_abuse", sid)
        ts_r = t + timedelta(minutes=rnd.uniform(4, 240))
        u = rnd.random()
        if u < .25:                                            # refunded to the original (stolen) card: no instrument switch
            rf = refund_row(ck, ts_r, 1.0)
        elif u < .45:                                          # refund to the accomplice's IBAN instead of a card
            rf = refund_row(ck, ts_r, 1.0, dict(type="SARIE", payment_method="iban_transfer", card_hash=None, card_scheme=None,
                                                  is_installment=0, installment_count=0, installment_provider=None,
                                                  counterparty_iban=C["iban"][acc], refund_to_different_instrument=1))
        else:
            own = C["cards"][acc][0]
            rf = refund_row(ck, ts_r, 1.0, dict(card_hash=own[0], card_scheme=own[1], refund_to_different_instrument=1,
                                                 type="MADA" if own[1] == "mada" else "CARD", payment_method=own[1],
                                                 is_installment=0, installment_count=0, installment_provider=None))
        label(rf, 1, 1, "layering", "refund_payout_abuse", sid)
        ts_p = ts_r + timedelta(minutes=rnd.uniform(15, 300))
        net = ck["amount"] * (1 - FEE.get(ck["payment_method"], .02))
        pr = payout_row(m, ts_p, net, 1, dev=M["console_dev"][m])
        pr["minutes_since_checkout"] = round((ts_p - t).total_seconds() / 60, 1)
        label(pr, 1, 1, "integration", "refund_payout_abuse", sid)
        scn_rows += [ck, rf, pr]


# ----------------------------------------------------------------------------- main
def main():
    global rnd, rng, C, M, HOME_IP, HOME_SUB, MOB_IP, MOB_SUB, OPEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="out")
    ap.add_argument("--rings", type=int, default=None)
    ap.add_argument("--abuse", type=int, default=None)
    ap.add_argument("--families", type=int, default=None)
    ap.add_argument("--seasonal_stores", type=int, default=None)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    rng = np.random.default_rng(a.seed)
    s = a.scale
    n_c, n_base_m, n_base = int(6000 * s), int(700 * s), int(95000 * s)
    n_rings = a.rings if a.rings is not None else int(18 * s)
    n_abuse = a.abuse if a.abuse is not None else int(30 * s)
    n_fam = a.families if a.families is not None else int(120 * s)
    n_hn = a.seasonal_stores if a.seasonal_stores is not None else int(25 * s)
    n_hr = int(15 * s)

    # ---------------- customers (KYC)
    C = defaultdict(list)
    n_hip = int(n_c * 1.4)
    HOME_IP = [H("hip", i) for i in range(n_hip)]
    HOME_SUB = [H("hsub", i) for i in range(n_hip // 6 + 1)]
    n_mob = max(80, n_c // 40)
    MOB_IP = [H("mip_pool", i) for i in range(n_mob)]
    MOB_SUB = [H("msub_pool", i) for i in range(n_mob // 8 + 1)]
    for i in range(n_c):
        cid = f"C{100000000 + i}"
        nat = rnd.choices(NAT, NAT_W)[0]
        age = int(min(75, max(18, rnd.gauss(34, 11))))
        dob = START - timedelta(days=age * 365.25 + rnd.uniform(0, 365))
        if rnd.random() < .06:
            opened = START + timedelta(days=rnd.uniform(0, DAYS - 5))
        else:
            opened = START - timedelta(days=min(5400, rnd.expovariate(1 / 1300) + 30))
        new_acct = opened > START
        income = int(math.exp(rnd.gauss(math.log(8500), .6)))
        iban, bank = make_iban()
        IBAN2C[iban] = cid
        row = dict(customer_id=cid, national_id_hash=H("nid", i), nationality=nat,
                   id_type="national_id" if nat == "SA" else rnd.choices(["iqama", "passport"], [.96, .04])[0],
                   age=age, dob=dob, city=rnd.choices(CITY_L, CITY_W)[0], account_open_date=opened,
                   kyc_level=rnd.choices(["basic", "standard", "full"], [.6, .3, .1] if new_acct else [.1, .55, .35])[0],
                   kyc_status=rnd.choices(["verified", "pending", "expired"], [.96, .02, .02])[0],
                   kyc_verified_date=opened + timedelta(days=rnd.uniform(0, 3)),
                   risk_rating=rnd.choices(["low", "medium", "high"], [.86, .12, .02])[0], pep_flag=int(rnd.random() < .004),
                   occupation=rnd.choices(OCC, OCC_W)[0], monthly_income_sar=income, phone_hash=H("phone", i), iban=iban,
                   bank_code=bank, opening_balance_sar=round(math.exp(rnd.gauss(math.log(income * .8), .8)), 2),
                   gt_role="normal", gt_scenario_id="", activity=rnd.lognormvariate(0, .9),
                   home_ip=rnd.randrange(n_hip))
        for k, v in row.items():
            C[k].append(v)
        nd = rnd.choices([1, 2, 3], [.6, .3, .1])[0]
        C["dev"].append([add_device("customer", opened + timedelta(days=rnd.uniform(0, 30))) for _ in range(nd)])
        cards = [(H("card", i, 0), rnd.choices(["mada", "visa", "mastercard"], [.72, .18, .10])[0])]
        if rnd.random() < .35:
            cards.append((H("card", i, 1), rnd.choices(["visa", "mastercard"], [.55, .45])[0]))
        C["cards"].append(cards)
        CIDX[cid] = i
        OPEN[cid] = row["opening_balance_sar"]

    # ---------------- merchants (KYB)
    M = defaultdict(list)
    cat_w = [CATS[c]["w"] for c in CAT_L]
    for i in range(n_base_m):
        r = rnd.random()
        if r < .70:
            onboard = START - timedelta(days=rnd.uniform(3 * 365, 9 * 365))
        elif r < .92:
            onboard = START - timedelta(days=rnd.uniform(365, 3 * 365))
        else:
            onboard = START + timedelta(days=rnd.uniform(0, DAYS - 20))
        director = None
        if i > 5 and rnd.random() < .06:                       # multi-store owner: shared director, benign
            director = M["cr_director_id_hash"][rnd.randrange(i)]
        elif rnd.random() < .012:                              # owner who is also a customer, benign
            director = C["national_id_hash"][rnd.randrange(n_c)]
        new_merchant(rnd.choices(CAT_L, cat_w)[0], onboard, director=director)
    for m in range(n_base_m):
        OPEN["M" + M["merchant_id"][m][1:]] = M["opening"][m]
    new_legit = [m for m in range(n_base_m) if M["onboarding_date"][m] > START]
    established = [m for m in range(n_base_m) if M["onboarding_date"][m] < START - timedelta(days=3 * 365)]

    # ---------------- seasonal / day / hour distributions
    dayw = np.array([DOW_W[(START + timedelta(days=d)).weekday()] for d in range(DAYS)])
    dayp = []
    for c in CAT_L:
        mult = np.ones(DAYS)
        for d in range(DAYS):
            t = START + timedelta(days=d)
            if WHITE_FRIDAY[0] <= t < WHITE_FRIDAY[1] and c in ("electronics", "apparel", "beauty_perfume", "home_furniture", "digital_gaming", "jewelry_gold"):
                mult[d] *= 2.2
            if PRE_RAMADAN[0] <= t < PRE_RAMADAN[1] and c in ("groceries", "restaurants_cafes"):
                mult[d] *= 1.8
            if EID[0] <= t < EID[1] and c in ("apparel", "jewelry_gold", "beauty_perfume", "restaurants_cafes", "entertainment_events"):
                mult[d] *= 1.9
            if RAMADAN[0] <= t < RAMADAN[1] and c in ("groceries", "restaurants_cafes"):
                mult[d] *= 1.3
        p = dayw * mult
        dayp.append(p / p.sum())
    is_ram = np.array([RAMADAN[0] <= START + timedelta(days=d) < RAMADAN[1] for d in range(DAYS)])
    hwn, hwr = np.array(HW_NORM, float), np.array(HW_RAM, float)
    hwn, hwr = hwn / hwn.sum(), hwr / hwr.sum()

    # ---------------- base checkouts
    mw = np.array(M["pop"][:n_base_m])
    midx = rng.choice(n_base_m, size=n_base, p=mw / mw.sum())
    cw = np.array(C["activity"])
    cidx = rng.choice(n_c, size=n_base, p=cw / cw.sum())
    cat_i = np.array([CAT_L.index(M["declared_category"][m]) for m in midx])
    day = np.zeros(n_base, int)
    for ci in range(len(CAT_L)):
        mask = cat_i == ci
        if mask.any():
            day[mask] = rng.choice(DAYS, size=int(mask.sum()), p=dayp[ci])
    hour = np.where(is_ram[day], rng.choice(24, size=n_base, p=hwr), rng.choice(24, size=n_base, p=hwn))
    sec = rng.integers(0, 3600, size=n_base)
    pool = []
    for j in range(n_base):
        c, m = int(cidx[j]), int(midx[j])
        ts = START + timedelta(days=int(day[j]), hours=int(hour[j]), seconds=int(sec[j]))
        lo = max(C["account_open_date"][c], M["onboarding_date"][m])
        if ts < lo:
            if lo >= END - timedelta(days=1):
                continue
            ts = lo + timedelta(seconds=rnd.uniform(0, (END - lo).total_seconds()))
        pool.append(label(checkout_row(c, m, ts), 0, 0, "normal", "normal"))

    # ---------------- hard negative: families sharing a device (looks like a ring, is not)
    for f in range(n_fam):
        make_family(f, pool, new_legit, n_base_m)

    # ---------------- hard negative: established stores, seasonal spike
    cnt = Counter(r["merchant_id"] for r in pool if r["txn_kind"] == "checkout")
    HN_WIN = {}
    cand = [m for m in established if M["declared_category"][m] in SEAS_CATS]
    for m in rnd.sample(cand, min(n_hn, len(cand))):
        a_, b_ = SEAS_CATS[M["declared_category"][m]]
        HN_WIN[M["merchant_id"][m]] = (a_, b_ + timedelta(days=14))
        M["gt_role"][m] = "seasonal_spike_established_store"
        daily = max(cnt[M["merchant_id"][m]], 40) / DAYS
        for _ in range(int(daily * (b_ - a_).days * rnd.uniform(2.5, 5))):
            c = rnd.randrange(n_c)
            ts = a_ + timedelta(days=rnd.uniform(0, (b_ - a_).days - .01))
            ts = ts.replace(hour=rnd.choices(range(24), HW_NORM)[0], minute=rnd.randrange(60))
            if ts < C["account_open_date"][c] or ts >= END:
                continue
            pool.append(label(checkout_row(c, m, ts), 0, 0, "normal", "hn_seasonal_spike", "", 1))

    # ---------------- hard negative: legit stores with many (fast, same-instrument) refunds
    hr = set()
    for m in rnd.sample([m for m in established if M["declared_category"][m] in ("apparel", "electronics", "beauty_perfume")], n_hr):
        M["refund_mult"][m] = 4.0
        M["gt_role"][m] = "high_refund_legit_store" if M["gt_role"][m] == "normal" else M["gt_role"][m]
        hr.add(M["merchant_id"][m])

    # ---------------- normal refunds
    refunds = []
    for ck in pool:
        if ck["txn_kind"] != "checkout":
            continue
        m = MIDX[ck["merchant_id"]]
        if rnd.random() < CATS[M["declared_category"][m]]["refund"] * M["refund_mult"][m]:
            med = .6 if ck["merchant_id"] in hr else 3.5
            if rnd.random() < .08:                             # quick order cancellation
                ts = ck["timestamp"] + timedelta(minutes=rnd.uniform(5, 120))
            else:
                ts = ck["timestamp"] + timedelta(days=max(.12, rnd.lognormvariate(math.log(med), 1.0)))
            if ts < END:
                rf = refund_row(ck, ts, 1.0 if rnd.random() < .85 else rnd.uniform(.3, .8))
                if rnd.random() < .03:                         # card reissued / closed: legit refund to another instrument
                    rf["refund_to_different_instrument"] = 1
                if ck["merchant_id"] in hr:
                    label(rf, 0, 0, "normal", "hn_high_refund_legit", "", 1)
                else:
                    label(rf, 0, 0, "normal", "normal")
                refunds.append(rf)
    pool += refunds

    # ---------------- weekly settlement payouts for ordinary merchants
    agg = defaultdict(lambda: [0.0, 0])
    for r in pool:
        w = (r["timestamp"] - START).days // 7
        if r["txn_kind"] == "checkout":
            g = agg[(r["merchant_id"], w)]
            g[0] += r["amount"] * (1 - FEE.get(r["payment_method"], .02))
            g[1] += 1
        elif r["txn_kind"] == "refund":
            agg[(r["merchant_id"], w)][0] -= r["amount"]
    for (mid, w), (net, n) in agg.items():
        ts = START + timedelta(days=7 * (w + 1) + 1, hours=6, minutes=rnd.uniform(0, 90))
        if ts < END and net > 100:
            pool.append(label(payout_row(MIDX[mid], ts, net, n), 0, 0, "normal", "normal"))

    # ---------------- attacks
    scn = []
    for r in range(n_rings):
        make_ring(r, scn)
    for a_i in range(n_abuse):
        make_abuse(a_i, scn)

    # ---------------- assemble transactions
    cols = ["_key", "_ref", "timestamp", "type", "txn_kind", "is_from_store", "amount", "nameOrig", "nameDest",
            "customer_id", "merchant_id", "payment_method", "is_installment", "installment_count", "installment_provider",
            "card_scheme", "card_hash", "counterparty_iban", "device_id", "os", "browser", "ip_hash", "ip_subnet_hash",
            "is_vpn_or_proxy", "origin_country", "basket_items", "basket_actual_category", "basket_mismatch_score",
            "refund_to_different_instrument", "minutes_since_checkout", "payout_covers_n_checkouts",
            "isFraud", "isMoneyLaundering", "laundering_typology", "gt_scenario_type", "gt_scenario_id", "gt_hard_negative"]
    df = pd.DataFrame(pool + scn, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "_key"], kind="stable").reset_index(drop=True)
    df.insert(0, "txn_id", [f"T{i + 1:09d}" for i in range(len(df))])
    df["refund_of_txn_id"] = df["_ref"].map(dict(zip(df["_key"], df["txn_id"])))
    df = df.drop(columns=["_key", "_ref"])
    # post-hoc seasonal hard-negative marking (all rows of those stores inside the spike window)
    for mid, (a_, b_) in HN_WIN.items():
        mask = (df.merchant_id == mid) & (df.timestamp >= a_) & (df.timestamp < b_) & (df.gt_hard_negative == 0) & (df.isFraud == 0)
        df.loc[mask, ["gt_scenario_type", "gt_hard_negative"]] = ["hn_seasonal_spike", 1]

    # derived time columns (AMLNet-style)
    df["step"] = ((df.timestamp - START).dt.total_seconds() // 3600).astype(int)
    df["hour"] = df.timestamp.dt.hour
    df["day_of_week"] = df.timestamp.dt.dayofweek
    df["day_of_month"] = df.timestamp.dt.day
    df["month"] = df.timestamp.dt.month
    df["is_weekend_sa"] = df.day_of_week.isin([4, 5]).astype(int)
    df["currency"] = "SAR"
    df["payment_method_ar"] = df.payment_method.map(PM_AR)

    # customer / merchant joins
    cust = pd.DataFrame({k: C[k] for k in ["customer_id", "national_id_hash", "id_type", "nationality", "age", "dob", "city",
                                           "account_open_date", "kyc_level", "kyc_status", "kyc_verified_date", "risk_rating",
                                           "pep_flag", "occupation", "monthly_income_sar", "phone_hash", "iban", "bank_code",
                                           "opening_balance_sar", "gt_role", "gt_scenario_id"]})
    cust["residence_country"] = "SA"
    cust["primary_device_id"] = [f"D{d[0]:07d}" for d in C["dev"]]
    for j in (0, 1):
        cust[f"card_hash_{j + 1}"] = [cs[j][0] if len(cs) > j else None for cs in C["cards"]]
        cust[f"card_scheme_{j + 1}"] = [cs[j][1] if len(cs) > j else None for cs in C["cards"]]
    cust["dob"] = pd.to_datetime(cust.dob).dt.date
    cust["account_open_date"] = pd.to_datetime(cust.account_open_date).dt.date
    cust["kyc_verified_date"] = pd.to_datetime(cust.kyc_verified_date).dt.date
    cust["age"] = [int((START - pd.Timestamp(d).to_pydatetime()).days / 365.25) for d in cust.dob]

    mer_cols = ["merchant_id", "legal_name", "legal_form", "city", "cr_number", "cr_issue_date", "cr_expiry_date", "cr_status",
                "vat_number", "vat_registered", "declared_category", "mcc", "onboarding_date", "kyb_status", "kyb_risk_score",
                "kyb_last_review_date", "expected_monthly_volume_sar", "employees_band", "has_physical_store",
                "email_domain_type", "phone_hash", "iban", "settlement_bank_code", "cr_director_id_hash",
                "cr_director_pep_flag", "gt_role", "gt_scenario_id"]
    mer = pd.DataFrame({k: M[k] for k in mer_cols})
    mer["console_device_id"] = [f"D{d:07d}" for d in M["console_dev"]]
    mer["onboarding_date"] = pd.to_datetime(mer.onboarding_date).dt.date

    cj = cust.set_index("customer_id")
    df["_dob"] = pd.to_datetime(df.customer_id.map(cj.dob))
    df["_open"] = pd.to_datetime(df.customer_id.map(cj.account_open_date))
    df["customer_age"] = np.floor((df.timestamp - df._dob).dt.days / 365.25).astype("Int64")
    df["customer_account_age_days"] = (df.timestamp - df._open).dt.days.astype("Int64")
    df["kyc_level"] = df.customer_id.map(cj.kyc_level)
    mj = mer.set_index("merchant_id")
    df["merchant_declared_category"] = df.merchant_id.map(mj.declared_category)
    df["_onb"] = pd.to_datetime(df.merchant_id.map(mj.onboarding_date))
    df["merchant_age_days"] = (df.timestamp - df._onb).dt.days.astype("Int64")
    df["category"] = df.merchant_declared_category.fillna("p2p_transfer")
    df["category_mismatch_flag"] = (df.basket_mismatch_score >= .5).astype("Int64").where(df.basket_mismatch_score.notna())
    df = df.drop(columns=["_dob", "_open", "_onb"])

    # running balances (origin side). BNPL checkout debits only the first instalment.
    fee = df.payment_method.map(FEE).fillna(0.0).values
    debit = np.where((df.txn_kind == "checkout") & (df.is_installment == 1), df.amount / df.installment_count.clip(lower=1), df.amount)
    credit = np.where(df.txn_kind == "checkout", df.amount * (1 - fee), df.amount)
    idx = np.arange(len(df))
    ok = ~df.nameDest.str.startswith("S").values
    ev = pd.concat([pd.DataFrame({"acct": df.nameOrig.values, "i": idx, "delta": -debit, "orig": True}),
                    pd.DataFrame({"acct": df.nameDest.values[ok], "i": idx[ok], "delta": credit[ok], "orig": False})])
    ev = ev.sort_values("i", kind="stable").reset_index(drop=True)
    ev["cum"] = ev.groupby("acct")["delta"].cumsum()
    acc = pd.DataFrame({"mn": ev.groupby("acct")["cum"].min()})
    acc["open"] = acc.index.map(OPEN)
    acc["open"] = acc["open"].fillna(5000.0)
    acc["eff"] = acc.open + np.maximum(0, -(acc.open + acc.mn)) + 30
    ev["after"] = ev.acct.map(acc.eff) + ev.cum
    ev["before"] = ev.after - ev.delta
    o = ev[ev.orig].sort_values("i")
    df["oldbalanceOrg"] = o.before.values.round(2)
    df["newbalanceOrig"] = o.after.values.round(2)

    out_cols = ["txn_id", "step", "timestamp", "hour", "day_of_week", "day_of_month", "month", "is_weekend_sa",
                "type", "txn_kind", "is_from_store", "amount", "currency", "category", "nameOrig", "nameDest",
                "customer_id", "merchant_id", "oldbalanceOrg", "newbalanceOrig",
                "payment_method", "payment_method_ar", "is_installment", "installment_count", "installment_provider",
                "card_scheme", "card_hash", "counterparty_iban",
                "device_id", "os", "browser", "ip_hash", "ip_subnet_hash", "is_vpn_or_proxy", "origin_country",
                "customer_age", "customer_account_age_days", "kyc_level", "merchant_age_days",
                "merchant_declared_category", "basket_actual_category", "basket_items", "basket_mismatch_score", "category_mismatch_flag",
                "refund_of_txn_id", "minutes_since_checkout", "refund_to_different_instrument", "payout_covers_n_checkouts",
                "isFraud", "isMoneyLaundering", "laundering_typology", "gt_scenario_type", "gt_scenario_id", "gt_hard_negative"]
    df = df[out_cols]
    df["gt_scenario_id"] = df.gt_scenario_id.fillna("")
    for c in ("isFraud", "isMoneyLaundering", "gt_hard_negative"):
        df[c] = df[c].fillna(0).astype(int)
    df["laundering_typology"] = df.laundering_typology.fillna("normal")
    df["gt_scenario_type"] = df.gt_scenario_type.fillna("normal")

    dev = pd.DataFrame(DEV)
    dev.insert(0, "device_id", [f"D{i:07d}" for i in range(len(DEV))])
    dev["first_seen"] = pd.to_datetime(dev.first_seen).dt.date

    os.makedirs(a.out, exist_ok=True)
    cust.to_csv(f"{a.out}/customers.csv", index=False)
    mer.to_csv(f"{a.out}/merchants.csv", index=False)
    dev.to_csv(f"{a.out}/devices.csv", index=False)
    df.to_csv(f"{a.out}/transactions.csv", index=False)
    print(f"customers={len(cust)} merchants={len(mer)} devices={len(dev)} transactions={len(df)}")


if __name__ == "__main__":
    main()
