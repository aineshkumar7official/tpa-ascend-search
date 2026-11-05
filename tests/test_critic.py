from datetime import date

from bots import critic

TODAY = date(2026, 10, 22)


def _review(conn, origin=None, dest=None, rating=8, sentiment=0.6, body="Great crew, lots of legroom",
            review_date="2026-05-01"):
    conn.execute(
        """INSERT INTO reviews(airline_name, airline_iata, origin_iata, dest_iata, cabin, rating_10,
                               review_date, body, sentiment) VALUES ('Delta','DL',?,?,'Economy Class',?,?,?,?)""",
        (origin, dest, rating, review_date, body, sentiment),
    )


def test_falls_back_to_airline(conn):
    for _ in range(2):
        _review(conn, "TPA", "JFK,LGA,EWR")
    for _ in range(10):
        _review(conn)
    key, s = critic.summarize(conn, "DL", "JFK", today=TODAY)
    assert s["match_level"] == "airline" and key == "DL|*"
    assert s["review_count"] == 12
    assert s["stars_5"] == 4.0
    assert "crew" in s["highlight_pros"] and "legroom" in s["highlight_pros"]


def test_route_level_matches_either_direction(conn):
    _review(conn, "TPA", "JFK,LGA,EWR")
    _review(conn, "JFK,LGA,EWR", "TPA")
    _review(conn, "TPA", "JFK,LGA,EWR", rating=4)
    key, s = critic.summarize(conn, "DL", "LGA", today=TODAY)
    assert s["match_level"] == "route" and key == "DL|LGA" and s["review_count"] == 3


def test_none_when_sparse(conn):
    _review(conn)
    key, s = critic.summarize(conn, "DL", "ATL", today=TODAY)
    assert s["match_level"] == "none" and s["review_count"] == 0 and s["stars_5"] is None


def test_old_airline_reviews_ignored(conn):
    for _ in range(10):
        _review(conn, review_date="2020-01-01")
    _, s = critic.summarize(conn, "DL", "ATL", today=TODAY)
    assert s["match_level"] == "none"
