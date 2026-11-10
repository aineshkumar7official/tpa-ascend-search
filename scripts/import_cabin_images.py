"""Copy the hand-picked photos in "Ascend Search Images/" into static/airlines/ and data/cabins.json.

    python scripts/import_cabin_images.py            # resize + copy, update cabins.json, refresh cached assets

Each photo goes to one slot: cabin, seat or food (the Cabin experience tiles), freebie (the airline page's Freebie
box) or gallery (extra photos on the airline page). An airline|aircraft key is used when the photo shows that
aircraft, so flights on it get it first; airline|* covers every other flight. Files that were in the wrong folder,
duplicates and business-class meals are in SKIPPED with the reason, and are not imported.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "Ascend Search Images"
STATIC = ROOT / "static" / "airlines"
CABINS = ROOT / "data" / "cabins.json"
MAX_SIDE = 1600
UNCONFIRMED = "source to be confirmed"

# (folder, file, airline|aircraft key, slot, credit). Credit: the airline for its own press/marketing photos,
# the watermark when there is one, otherwise UNCONFIRMED.
PHOTOS = [
    ("Aeromexico", "Aeromexico-737-MAX-cabin.avif", "AM|Boeing 737 MAX 8", "cabin", "Aeroméxico"),
    ("Aeromexico", "Aeromexico-737-MAX-cabin.avif", "AM|*", "cabin", "Aeroméxico"),
    ("Aeromexico", "still_I.avif", "AM|*", "seat", "Aeroméxico"),
    ("Aeromexico", "61a542351f8b8c00195ab333.webp", "AM|*", "food", UNCONFIRMED),
    ("Aeromexico", "2024AM_7879.webp", "AM|*", "freebie", "Aeroméxico"),

    ("Air Canada", "Air-Canada-737-MAX-8-Economy-Class-Review-6.jpeg", "AC|Boeing 737 MAX 8", "cabin", UNCONFIRMED),
    ("Air Canada", "Air-Canada-737-MAX-8-Economy-Class-Review-12.jpeg", "AC|Boeing 737 MAX 8", "seat", UNCONFIRMED),
    ("Air Canada", "Air-Canada-737-MAX-8-Economy-Class-Review-6.jpeg", "AC|*", "cabin", UNCONFIRMED),
    ("Air Canada", "Air-Canada-737-MAX-8-Economy-Class-Review-12.jpeg", "AC|*", "seat", UNCONFIRMED),
    ("Air Canada", "fb-snack-trio.jpg", "AC|*", "food", "Air Canada"),

    ("Alaska Airlines", "18-NOV-2023_-_AS1219_LAX-SEA_(N459AS_-_B737-900ER)_(02).jpg", "AS|Boeing 737-900ER", "cabin", UNCONFIRMED),
    ("Alaska Airlines", "16-NOV-2023_-_AS1214_SEA-LAX_(N214AK_-_B737-900ER)_(03).jpg", "AS|Boeing 737-900ER", "seat", UNCONFIRMED),
    ("Alaska Airlines", "18-NOV-2023_-_AS1219_LAX-SEA_(N459AS_-_B737-900ER)_(02).jpg", "AS|*", "cabin", UNCONFIRMED),
    ("Alaska Airlines", "16-NOV-2023_-_AS1214_SEA-LAX_(N214AK_-_B737-900ER)_(03).jpg", "AS|*", "seat", UNCONFIRMED),
    ("Alaska Airlines", "snack-basket-flat-lay_02.jpg", "AS|*", "food", "Alaska Airlines"),
    ("Alaska Airlines", "20250319_as_legend_fulton0409_9f11b1.jpg", "AS|*", "freebie", "Alaska Airlines"),

    ("American Airlines", "AA_04_21_Library_NarrowBody_Main_Cabin_004001.jpg", "AA|*", "seat", "American Airlines"),
    ("American Airlines", "Pasted 2026-11-10 at 17.09.22.png", "AA|*", "cabin", "American Airlines"),
    ("American Airlines", "American_Airlines_in-flight_snack_in_economy_class_from_MIA_to_PHL.jpeg", "AA|*", "food", UNCONFIRMED),
    ("American Airlines", "041526-trading-cards-set-front.jpg", "AA|*", "freebie", "American Airlines"),

    ("Avelo Airlines", "Avelo Boeing NG 737-800 Interior.jpg", "XP|*", "cabin", "Avelo Airlines"),
    ("Avelo Airlines", "Avelo Boeing NG 737-800 Interior 3.jpg", "XP|*", "seat", "Avelo Airlines"),

    ("Avianca Airlines", "Pasted 2026-11-07 at 18.29.11.png", "AV|*", "cabin", "Avianca"),
    ("Avianca Airlines", "Pasted 2026-11-07 at 18.28.38.png", "AV|*", "seat", "Avianca"),
    ("Avianca Airlines", "Screenshot 2026-11-07 at 18.27.31.png", "AV|*", "food", "Avianca"),

    ("Breeze Airways", "62a243414d337600198685bf.webp", "MX|Airbus A220-300", "cabin", UNCONFIRMED),
    ("Breeze Airways", "62a243414d337600198685bf.webp", "MX|*", "cabin", UNCONFIRMED),
    ("Breeze Airways", "images.jpeg", "MX|Airbus A220-300", "seat", UNCONFIRMED),
    ("Breeze Airways", "images.jpeg", "MX|*", "seat", UNCONFIRMED),
    ("Breeze Airways", "images (1).jpeg", "MX|*", "food", UNCONFIRMED),
    ("Breeze Airways", "20260220_143134+(1).webp", "MX|*", "freebie", UNCONFIRMED),

    ("British Airways", "130705NM_NewAircraft-0029-640x427.jpg", "BA|*", "cabin", "British Airways"),
    ("British Airways", "britishairways_21686666131362-700x467.avif", "BA|*", "seat", "British Airways"),
    ("British Airways", "images.jpeg", "BA|*", "food", UNCONFIRMED),

    ("Cayman Airways", "images.jpeg", "KX|*", "cabin", "Cayman Airways"),
    ("Cayman Airways", "images (1).jpeg", "KX|*", "food", "Cayman Airways"),

    ("Copa Airlines", "copa-737-economy-extra-legroom-seats.jpg", "CM|*", "cabin", UNCONFIRMED),
    ("Copa Airlines", "images.jpeg", "CM|*", "seat", "Copa Airlines"),

    ("Delta Airlines", "738-cabin-view.jpg", "DL|Boeing 737", "cabin", UNCONFIRMED),
    ("Delta Airlines", "images (1).jpeg", "DL|Boeing 737", "seat", UNCONFIRMED),
    ("Delta Airlines", "Delta-737-900-Economy-Class-Review-57.jpeg", "DL|Boeing 737-900ER", "cabin", UNCONFIRMED),
    ("Delta Airlines", "A321 interior 2.jpg.webp", "DL|Airbus A321", "cabin", "Delta Air Lines"),
    ("Delta Airlines", "A321 interior 3.jpg.webp", "DL|Airbus A321", "seat", "Delta Air Lines"),
    ("Delta Airlines", "dal_a321_neo-438.jpg.webp", "DL|Airbus A321neo", "cabin", "Delta Air Lines"),
    ("Delta Airlines", "a330_900neo-interior7.jpg.webp", "DL|Airbus A330-900neo", "cabin", "Delta Air Lines"),
    ("Delta Airlines", "738-cabin-view.jpg", "DL|*", "cabin", UNCONFIRMED),
    ("Delta Airlines", "images (1).jpeg", "DL|*", "seat", UNCONFIRMED),
    ("Delta Airlines", "fandb_snacks_1.jpg", "DL|*", "food", "Delta Air Lines"),
    ("Delta Airlines", "TAL-delta-trading-cards-spread-DTLTCS1223-31d806f3f73b4b61abfb4710bc6fe336.jpg", "DL|*", "freebie", UNCONFIRMED),
    ("Delta Airlines", "737-800_9.jpg", "DL|*", "gallery", UNCONFIRMED),

    ("Discover Airlines", "Discover Airlines_Intercont_Eco.jpg", "4Y|*", "cabin", "Discover Airlines"),
    ("Discover Airlines", "Discover Airlines_Economy_Legroom.jpg", "4Y|*", "seat", "Discover Airlines"),
    ("Discover Airlines", "img.jpg", "4Y|*", "food", "Discover Airlines"),
    ("Discover Airlines", "images.jpeg", "4Y|*", "freebie", "Discover Airlines"),  # the free Discover cookies

    ("Edelweiss Airlines", "edelweiss_a350_economy_class_cabin_overview.jpg", "WK|*", "cabin", "Edelweiss"),
    ("Edelweiss Airlines", "edelweiss_a350_economy_class_seats.jpg", "WK|*", "seat", "Edelweiss"),
    ("Edelweiss Airlines", "foodonboardeconomy_009.jpg", "WK|*", "food", "Edelweiss"),
    ("Edelweiss Airlines", "food_onboard_biberli.jpg", "WK|*", "gallery", "Edelweiss"),

    ("Jetblue", "JetBlue-Core-Cabin-(A220).jpg", "B6|Airbus A220-300", "cabin", "JetBlue"),
    ("Jetblue", "JetBlue-A320-Seat-back-Screens.JPG", "B6|Airbus A320", "seat", "JetBlue"),
    ("Jetblue", "JetBlue-Core-Cabin-Lighting.jpg", "B6|*", "cabin", "JetBlue"),
    ("Jetblue", "JetBlue-Core-Seatings.jpg", "B6|*", "seat", "JetBlue"),
    ("Jetblue", "Snack-Service.jpg", "B6|*", "food", "JetBlue"),
    ("Jetblue", "JetBlue-Core-Rows.jpg", "B6|*", "gallery", "JetBlue"),
    ("Jetblue", "JetBlue-Core-Seatback.jpg", "B6|*", "gallery", "JetBlue"),

    ("Porter Airlines", "Porter_images_4.jpg", "PD|*", "cabin", "Porter Airlines"),
    ("Porter Airlines", "Onboard_4.jpg", "PD|*", "seat", "Porter Airlines"),
    ("Porter Airlines", "Onboard_1.jpg", "PD|*", "food", "Porter Airlines"),
    ("Porter Airlines", "Onboard_2.jpg", "PD|*", "gallery", "Porter Airlines"),
    ("Porter Airlines", "Onboard_3.jpg", "PD|*", "gallery", "Porter Airlines"),

    ("Southwest", "SWAInterior-1.jpg", "WN|*", "cabin", "Southwest Airlines"),
    ("Southwest", "Southwest offers premium seating with extra legroom options.jpg", "WN|*", "seat", "Southwest Airlines"),
    ("Southwest", "snacks-september-2026.jpg", "WN|*", "food", "Southwest Airlines"),
    ("Southwest", "LibertyOne_TradingCardFinal_Front.webp", "WN|*", "freebie", "Southwest Airlines"),
    ("Southwest", "Southwest launches new commercial initiatives to enhance Customer Experience.jpg", "WN|*", "gallery", "Southwest Airlines"),
    ("Southwest", "SWAInterior-2.jpg", "WN|*", "gallery", "Southwest Airlines"),
    ("Southwest", "Southwest unveils plan for Even Better carrier.jpg", "WN|*", "gallery", "Southwest Airlines"),

    ("SunCountry_Images", "Sun-Country_Aircraft_Rear-1.jpg", "SY|*", "cabin", "Sun Country Airlines"),
    ("SunCountry_Images", "Sun-Country_Aircraft_Front.jpg", "SY|*", "seat", "Sun Country Airlines"),
    ("SunCountry_Images", "images.jpeg", "SY|*", "food", "Sun Country Airlines"),

    ("United Airlines", "United-Airlines-737-900-Economy-Class-Review-5.jpeg", "UA|Boeing 737-900ER", "cabin", UNCONFIRMED),
    ("United Airlines", "United-Next-737-800-Interior.jpeg", "UA|*", "cabin", UNCONFIRMED),
    ("United Airlines", "images.jpeg", "UA|*", "seat", UNCONFIRMED),
    ("United Airlines", "Pasted 2026-11-07 at 18.58.50.png", "UA|*", "food", "United Airlines"),
    ("United Airlines", "images (2).jpeg", "UA|*", "freebie", UNCONFIRMED),
    ("United Airlines", "united_airlines_737-800_economy_review_LAX-SAN_30.jpg", "UA|*", "gallery", "SANspotter"),
    ("United Airlines", "images (1).jpeg", "UA|*", "gallery", UNCONFIRMED),

    ("Virgin Atlantic", "images.jpeg", "VS|*", "cabin", UNCONFIRMED),
    ("Virgin Atlantic", "Pasted 2026-11-07 at 19.04.02.png", "VS|*", "seat", UNCONFIRMED),
    ("Virgin Atlantic", "Mile-High-Tea-Breakfast.webp", "VS|*", "food", UNCONFIRMED),
    ("Virgin Atlantic", "images (1).jpeg", "VS|*", "gallery", UNCONFIRMED),

    ("Westjet", "westjet_737-700-SAN-YCC_trip_report_08.jpg", "WS|*", "seat", "SANspotter"),
    ("Westjet", "Screenshot 2026-11-07 at 19.02.54.png", "WS|*", "food", UNCONFIRMED),
    ("Westjet", "1737768115946.jpeg", "WS|*", "freebie", UNCONFIRMED),

    ("Frontier Airlines", "Pasted 2026-11-10 at 17.14.06.png", "F9|*", "freebie", UNCONFIRMED),
]

# Not imported, with why. Frontier's three photos were already in static/airlines/F9 (F9|*).
SKIPPED = {
    "Aeromexico/50-standard.jpg": "Breeze seat (same file as Breeze Airways/images.jpeg, confirmed Breeze)",
    "Air Canada/Screenshot 2026-11-07 at 18.43.07.png": "business-class meal (menu text says 'classe affaires')",
    "British Airways/copashowpassv2.png": "Copa ShowPass seatback, not British Airways",
    "Delta Airlines/images.jpeg": "Copa ShowPass seatback, not Delta",
    "Delta Airlines/summerfb2025_west-core.jpg": "premium-cabin meal, not economy",
    "Jetblue/Snack-Service 2.jpg": "duplicate of Snack-Service.jpg",
    "Porter Airlines/Porter_images_4 (1).jpg": "duplicate of Porter_images_4.jpg",
}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def convert(src, dest):
    im = ImageOps.exif_transpose(Image.open(src))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=82, optimize=True)


def main():
    cabins = json.loads(CABINS.read_text())
    done = {}
    for folder, name, key, slot, credit in PHOTOS:
        src = SRC / folder / name
        airline, aircraft = key.split("|", 1)
        if src not in done:
            dest = STATIC / airline / f"{slug(Path(name).stem)[:60]}.jpg"
            convert(src, dest)
            done[src] = dest
        photo = {"image_url": "/app/static/" + done[src].relative_to(ROOT / "static").as_posix(),
                 "credit": f"Photo: {credit}", "source_page": None}
        entry = cabins.setdefault(key, {})
        if slot == "gallery":
            gallery = entry.setdefault("gallery", [])
            if photo["image_url"] not in [g["image_url"] for g in gallery]:
                gallery.append(photo)
        else:
            entry[slot] = photo
    CABINS.write_text(json.dumps(cabins, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(done)} photos copied, {len(PHOTOS)} slots filled, {len(SKIPPED)} skipped")

    from bots import enricher
    from core.db import get_conn
    conn = get_conn()
    airlines = {k.split("|")[0] for _, _, k, _, _ in PHOTOS}
    keys = [r[0] for r in conn.execute("SELECT asset_key FROM assets")]
    refreshed = 0
    for k in keys:
        airline, aircraft = k.split("|", 1)
        if airline in airlines:
            enricher.get_asset(conn, airline, None if aircraft == "Unknown" else aircraft, refresh=True)
            refreshed += 1
    print(f"{refreshed} cached photo sets refreshed")


if __name__ == "__main__":
    main()
