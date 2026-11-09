"""A small fictional world: the companies that sell and buy, where they are, and what they sell.

Every company name is made up by combining words from the lists below; none is taken from a real
business, and well-known brand names are left out of the lists. A match with a real business would be a
coincidence, and every invoice also carries a test-only VAT number and a visible synthetic-sample marker.
"""

import random
from dataclasses import dataclass
from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict

from ledgerlens_datagen.vat import vat_number_for

Trade = Literal["office", "it", "cleaning", "maintenance", "hospitality", "printing", "logistics"]
NumberStyle = Literal["dashed", "slashed", "plain"]

# How many companies a world has. They both sell and buy.
WORLD_SIZE = 40


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Address(_Record):
    """A Saudi national address, in English and Arabic."""

    building_number: str  # 4 digits (ZATCA rule BR-KSA-37)
    street_en: str
    street_ar: str
    district_en: str
    district_ar: str
    city_en: str
    city_ar: str
    postal_code: str  # 5 digits


class Company(_Record):
    name_en: str
    name_ar: str
    vat_number: str
    trade: Trade
    address: Address
    # Companies number their invoices differently, so the extractor sees more than one format.
    number_style: NumberStyle
    abbreviation: str

    def invoice_number(self, year: int, sequence: int) -> str:
        match self.number_style:
            case "dashed":
                return f"{self.abbreviation}-{year}-{sequence:06d}"
            case "slashed":
                return f"{self.abbreviation}/{year % 100:02d}/{sequence:05d}"
            case "plain":
                return f"{sequence:08d}"
            case _:  # pragma: no cover (unreachable: mypy fails here if a new style isn't handled above)
                assert_never(self.number_style)


class World(_Record):
    companies: tuple[Company, ...]


@dataclass(frozen=True)
class Item:
    """Something a company sells, with its price range in whole riyals and how it's counted."""

    en: str
    ar: str
    min_price: int
    max_price: int
    unit: Literal["each", "hour", "kg"]
    max_quantity: int


# Name parts: (English, Arabic). An Arabic company name reads form, root, trade: شركة سحاب للطباعة.
# The trade starts with لـ ("for"), as Saudi trade names do; with the article ال it becomes لل.
FORMS = (("Co.", "شركة"), ("Est.", "مؤسسة"))
ROOTS = (
    ("Sahab", "سحاب"),
    ("Rimal", "رمال"),
    ("Najm", "نجم"),
    ("Sidr", "سدر"),
    ("Areen", "عرين"),
    ("Fajr", "فجر"),
    ("Durrah", "درة"),
    ("Marjan", "مرجان"),
    ("Yasmin", "ياسمين"),
    ("Ghaith", "غيث"),
    ("Waha", "واحة"),
    ("Barq", "برق"),
    ("Nada", "ندى"),
    ("Shams", "شمس"),
    ("Diyar", "ديار"),
    ("Jood", "جود"),
    ("Hadeer", "هدير"),
    ("Afaq", "آفاق"),
    ("Nibras", "نبراس"),
    ("Ruba", "ربى"),
)
TRADES: dict[Trade, tuple[str, str]] = {
    "office": ("Office Supplies", "للوازم المكتبية"),
    "it": ("IT Solutions", "لحلول تقنية المعلومات"),
    "cleaning": ("Cleaning Services", "لخدمات النظافة"),
    "maintenance": ("Maintenance", "للصيانة"),
    "hospitality": ("Hospitality Supplies", "لمستلزمات الضيافة"),
    "printing": ("Printing", "للطباعة"),
    "logistics": ("Logistics", "للخدمات اللوجستية"),
}

# Real city names with a fitting first digit for the postal code; the streets and districts are common
# generic names, combined at random.
CITIES = (
    ("Riyadh", "الرياض", "1"),
    ("Jeddah", "جدة", "2"),
    ("Makkah", "مكة المكرمة", "2"),
    ("Dammam", "الدمام", "3"),
    ("Khobar", "الخبر", "3"),
    ("Madinah", "المدينة المنورة", "4"),
)
DISTRICTS = (
    ("Al Rawdah", "الروضة"),
    ("Al Salam", "السلام"),
    ("Al Nuzha", "النزهة"),
    ("Al Aziziyah", "العزيزية"),
    ("Al Shati", "الشاطئ"),
    ("Al Faisaliyah", "الفيصلية"),
    ("Al Nakheel", "النخيل"),
    ("Al Rabwah", "الربوة"),
)
STREETS = (
    ("Al Ward Street", "شارع الورد"),
    ("Al Ilm Street", "شارع العلم"),
    ("Al Thaqafa Street", "شارع الثقافة"),
    ("Al Huda Street", "شارع الهدى"),
    ("Al Amal Street", "شارع الأمل"),
    ("Al Sharq Street", "شارع الشرق"),
    ("Al Bahr Street", "شارع البحر"),
    ("Al Nour Street", "شارع النور"),
)

CATALOGUE: dict[Trade, tuple[Item, ...]] = {
    "office": (
        Item("A4 copy paper, carton of 5 reams", "ورق تصوير A4، كرتون 5 رزم", 95, 140, "each", 40),
        Item("Ballpoint pens, box of 50", "أقلام حبر جاف، علبة 50 قلماً", 25, 60, "each", 20),
        Item("Black laser toner cartridge", "خرطوشة حبر ليزر سوداء", 180, 420, "each", 10),
        Item("Archive box files, pack of 10", "ملفات أرشيف، عبوة 10 ملفات", 45, 90, "each", 15),
        Item("Whiteboard markers, pack of 12", "أقلام سبورة بيضاء، عبوة 12 قلماً", 20, 45, "each", 20),
    ),
    "it": (
        Item("14-inch laptop", "حاسب محمول 14 بوصة", 2800, 5200, "each", 12),
        Item("27-inch monitor", "شاشة 27 بوصة", 750, 1600, "each", 12),
        Item("Wireless keyboard and mouse set", "طقم لوحة مفاتيح وفأرة لاسلكي", 90, 260, "each", 25),
        Item("Office software licence, 1 year", "ترخيص برنامج مكتبي لمدة سنة", 250, 650, "each", 50),
        Item("24-port network switch", "محول شبكة 24 منفذاً", 600, 1900, "each", 4),
    ),
    "cleaning": (
        Item("Office cleaning, monthly contract", "تنظيف المكاتب، عقد شهري", 2500, 9000, "each", 1),
        Item("Glass facade cleaning visit", "زيارة تنظيف الواجهات الزجاجية", 400, 1200, "each", 3),
        Item("Hand soap, 5-litre can", "صابون أيدي، جالون 5 لترات", 25, 55, "each", 20),
        Item("Paper towels, carton of 24 rolls", "مناشف ورقية، كرتون 24 لفة", 60, 130, "each", 20),
        Item("Floor disinfectant, 4 litres", "مطهر أرضيات، 4 لترات", 30, 70, "each", 20),
    ),
    "maintenance": (
        Item("Air conditioner maintenance visit", "زيارة صيانة مكيفات", 150, 450, "each", 6),
        Item("Technician labour, per hour", "أجور فني، بالساعة", 80, 180, "hour", 12),
        Item("Split AC filter", "فلتر مكيف سبليت", 35, 90, "each", 30),
        Item("LED panel light, 60 by 60 cm", "لوحة إنارة LED مقاس 60 في 60 سم", 45, 120, "each", 40),
        Item("Water pump repair", "إصلاح مضخة مياه", 300, 1100, "each", 2),
    ),
    "hospitality": (
        Item("Arabic coffee, per kg", "قهوة عربية، بالكيلوغرام", 60, 140, "kg", 10),
        Item("Bottled water, carton of 40", "مياه معبأة، كرتون 40 عبوة", 14, 30, "each", 60),
        Item("Dates, per kg", "تمر، بالكيلوغرام", 35, 120, "kg", 30),
        Item("Tea, box of 100 bags", "شاي، علبة 100 كيس", 12, 35, "each", 30),
        Item("Packed meal box", "وجبة معبأة", 18, 45, "each", 200),
    ),
    "printing": (
        Item("Business cards, 500 pieces", "بطاقات عمل، 500 بطاقة", 60, 180, "each", 20),
        Item("A4 brochures, 1000 copies", "مطويات A4، 1000 نسخة", 450, 1200, "each", 5),
        Item("Roll-up banner", "لوحة إعلانية رول أب", 150, 380, "each", 10),
        Item("Letterhead, 1000 sheets", "ورق مراسلات رسمي، 1000 ورقة", 250, 600, "each", 5),
        Item("Large-format poster", "ملصق بمقاس كبير", 40, 140, "each", 30),
    ),
    "logistics": (
        Item("Local delivery trip", "رحلة توصيل داخل المدينة", 80, 350, "each", 20),
        Item("Freight, per kg", "شحن بضائع، بالكيلوغرام", 2, 6, "kg", 800),
        Item("Pallet storage, per month", "تخزين منصة نقالة، شهرياً", 45, 120, "each", 40),
        Item("Packing materials", "مواد تغليف", 30, 150, "each", 20),
        Item("Forklift hire, per hour", "استئجار رافعة شوكية، بالساعة", 90, 220, "hour", 10),
    ),
}


def build_world(seed: int, size: int = WORLD_SIZE) -> World:
    """The same seed always gives the same companies, with the same serials and VAT numbers."""
    rng = random.Random(f"ledgerlens-datagen/{seed}/world")
    names = [(root, trade) for root in ROOTS for trade in TRADES]
    chosen = rng.sample(names, size)
    return World(
        companies=tuple(_company(rng, serial, root, trade) for serial, (root, trade) in enumerate(chosen, start=1))
    )


def _company(rng: random.Random, serial: int, root: tuple[str, str], trade: Trade) -> Company:
    form_en, form_ar = rng.choice(FORMS)
    trade_en, trade_ar = TRADES[trade]
    city_en, city_ar, postal_prefix = rng.choice(CITIES)
    district_en, district_ar = rng.choice(DISTRICTS)
    street_en, street_ar = rng.choice(STREETS)
    styles: tuple[NumberStyle, ...] = ("dashed", "slashed", "plain")
    return Company(
        name_en=f"{root[0]} {trade_en} {form_en}",
        name_ar=f"{form_ar} {root[1]} {trade_ar}",
        vat_number=vat_number_for(serial),
        trade=trade,
        address=Address(
            building_number=str(rng.randint(1000, 9999)),
            street_en=street_en,
            street_ar=street_ar,
            district_en=district_en,
            district_ar=district_ar,
            city_en=city_en,
            city_ar=city_ar,
            postal_code=f"{postal_prefix}{rng.randint(0, 9999):04d}",
        ),
        number_style=rng.choice(styles),
        abbreviation=root[0][:3].upper(),
    )
