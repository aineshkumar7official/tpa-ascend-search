from sources.flights_serpapi import remaining, spend


def test_budget_of_two(conn):
    assert spend(conn, "serpapi", budget=2)
    assert spend(conn, "serpapi", budget=2)
    assert not spend(conn, "serpapi", budget=2)
    assert remaining(conn, budget=2) == 0


def test_providers_are_separate(conn):
    assert spend(conn, "serpapi", budget=1)
    assert spend(conn, "ignav", budget=1)
