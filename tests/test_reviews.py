import pandas as pd

from sources.reviews import read_table, rows_from_csv, unslug


def test_unslug():
    assert unslug("delta-air-lines") == "delta air lines"
    assert unslug("tampa,_fl_to_atlanta") == "tampa, fl to atlanta"
    assert unslug("Delta Air Lines") == "Delta Air Lines"
    assert unslug("  ") is None
    assert unslug(float("nan")) is None


def test_reads_slugged_xlsx(tmp_path):
    path = tmp_path / "reviews.xlsx"
    pd.DataFrame([{
        "airline": "delta-air-lines", "route": "tampa_to_atlanta", "seat_type": "economy_class",
        "overall": 8, "date": "2025-03-01", "content": "Trip Verified | Friendly crew and on time.",
    }]).to_excel(path, index=False)
    assert len(read_table(path)) == 1
    (row,) = rows_from_csv(path, today=pd.Timestamp("2026-01-01").date())
    assert row["airline_name"] == "Delta Air Lines"
    assert row["route_text"] == "tampa to atlanta"
    assert row["cabin"] == "Economy Class"
    assert row["body"] == "Friendly crew and on time."
    assert row["review_date"] == "2025-03-01"
