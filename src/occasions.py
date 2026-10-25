"""التقويم الهجري والمناسبات الدينية.

التاريخ الهجري بيتجاب من AlAdhan (تقويم أم القرى) ولو فشل بنحسبه بالحساب الجدولي.
config.json → "hijri_offset": لو التقويم المصري مختلف يوم عن أم القرى (مثلاً -1 أو 1).
"""
import datetime as dt
from zoneinfo import ZoneInfo

from .common import DATA, http_get, load_json

TZ = ZoneInfo("Africa/Cairo")
MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان",
          "شوال", "ذو القعدة", "ذو الحجة"]


def cairo_now():
    return dt.datetime.now(TZ)


def _tabular(d):
    """الحساب الهجري الجدولي (دقته ±١ يوم) – احتياطي بس."""
    jd = d.toordinal() + 1721424.5  # julian day at midnight
    jd = int(jd + 0.5)
    l_ = jd - 1948440 + 10632
    n = (l_ - 1) // 10631
    l_ = l_ - 10631 * n + 354
    j = ((10985 - l_) // 5316) * ((50 * l_) // 17719) + (l_ // 5670) * ((43 * l_) // 15238)
    l_ = l_ - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l_) // 709
    day = l_ - (709 * m) // 24
    y = 30 * n + j - 30
    return y, m, day


def hijri(date=None, offset=0):
    date = (date or cairo_now().date()) + dt.timedelta(days=offset)
    try:
        h = http_get(f"https://api.aladhan.com/v1/gToH/{date:%d-%m-%Y}", timeout=20).json()["data"]["hijri"]
        return int(h["year"]), int(h["month"]["number"]), int(h["day"])
    except Exception as e:  # noqa: BLE001
        print(f"  hijri api failed ({type(e).__name__}) – using tabular calendar")
        return _tabular(date)


def data():
    return load_json(DATA / "occasions.json")


def today(cfg, date=None):
    """يرجّع المناسبة (أو الجمعة) لليوم ده، أو None."""
    date = date or cairo_now().date()
    y, m, d = hijri(date, cfg.get("hijri_offset", 0))
    occ_data = data()
    best = None
    for o in occ_data["occasions"]:
        if not o.get("enabled", True):
            continue
        if o["month"] != "*" and o["month"] != m:
            continue
        if m in o.get("exclude_months", []):
            continue
        if o["from"] <= d <= o["to"] and (best is None or o["priority"] > best["priority"]):
            best = o
    friday = date.weekday() == 4
    ctx = {"date": date.isoformat(), "hijri": [y, m, d], "hijri_text": f"{d} {MONTHS[m - 1]} {y}هـ",
           "friday": friday, "occasion": best}
    # الجمعة: لو مفيش مناسبة أهم (أولوية ≥ ٢٠) الجمعة هي اللي تتنشر
    if friday and (best is None or best["priority"] < 20):
        ctx["occasion"] = {**occ_data["friday"], "priority": 15}
    return ctx


def item(key):
    return {"id": key, **data()["library"][key]}

