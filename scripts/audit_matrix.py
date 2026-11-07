"""Audit the exact Matrix assets without collecting fares or guessing missing photos.

Run with --online to GET and decode remote images. Exit 1 means incomplete.
The JSON report separates missing, broken, unchecked and ready slots.
"""
import _path  # noqa: F401

import argparse
import io
import json
from pathlib import Path

import requests
from PIL import Image

from core import config, queries
from core.db import get_conn


def inspect_photo(asset, slot, online=False):
    url = asset.get(f"{slot}_url")
    result = {"url": url, "status": "missing"}
    if not url:
        return result
    if not asset.get(f"{slot}_credit") or not asset.get(f"{slot}_link"):
        return {**result, "status": "missing_attribution"}
    try:
        if url.startswith("/app/static/"):
            path = config.ROOT / "static" / url.removeprefix("/app/static/")
            if not path.resolve().is_relative_to((config.ROOT / "static").resolve()):
                raise ValueError("Image escapes static directory")
            data = path.read_bytes()
        elif online:
            response = requests.get(url, timeout=15, headers={"User-Agent": config.settings.HTTP_USER_AGENT})
            response.raise_for_status()
            data = response.content
        else:
            return {**result, "status": "unchecked_remote"}
        with Image.open(io.BytesIO(data)) as photo:
            result["dimensions"] = list(photo.size)
            photo.verify()
        result["status"] = "decodes"
    except (requests.RequestException, OSError, ValueError) as error:
        result.update(status="broken", error=str(error))
    return result


def audit(conn, online=False):
    rows = []
    for card in queries.matrix(conn):
        code = card["iata"]
        asset = queries.airline_photo_asset(conn, code)
        slots = {slot: inspect_photo(asset, slot, online) for slot in ("exterior", "interior", "seat", "food")}
        slots["grid_exterior"] = inspect_photo(card["asset"], "exterior", online)
        rows.append({"airline": code, "name": card["name"], "photos": slots,
                     "complete": all(p["status"] == "decodes" for p in slots.values()),
                     "visual_review_required": True})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/matrix_audit.json"))
    args = parser.parse_args()
    with get_conn() as conn:
        report = audit(conn, args.online)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for row in report:
        print(row["airline"], " ".join(f"{k}={v['status']}" for k, v in row["photos"].items()))
    raise SystemExit(0 if all(row["complete"] for row in report) else 1)
