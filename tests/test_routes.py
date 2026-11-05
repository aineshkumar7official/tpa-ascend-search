import pytest

from sources.reviews import parse_route


@pytest.mark.parametrize("text,origin,dest", [
    ("Tampa to New York via Atlanta", {"TPA"}, {"JFK", "LGA", "EWR"}),
    ("Tampa to Atlanta", {"TPA"}, {"ATL"}),
    ("Boston to Tampa", {"BOS"}, {"TPA"}),
    ("TPA to DEN", {"TPA"}, {"DEN"}),
    ("Chicago - Tampa", {"ORD", "MDW"}, {"TPA"}),
    ("Washington to Tampa via Charlotte", {"DCA", "IAD", "BWI"}, {"TPA"}),
    ("Nowhere", set(), set()),
    (None, set(), set()),
])
def test_parse_route(text, origin, dest):
    assert parse_route(text) == (origin, dest)
