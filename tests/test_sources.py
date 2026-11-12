from sources import commons, planespotters


def test_planespotters_parse():
    payload = {"photos": [{"thumbnail_large": {"src": "https://t.plnspttrs.net/x.jpg"},
                           "link": "https://www.planespotters.net/photo/1", "photographer": "Jane Doe"}]}
    assert planespotters.parse(payload) == {
        "url": "https://t.plnspttrs.net/x.jpg", "link": "https://www.planespotters.net/photo/1",
        "credit": "© Jane Doe / Planespotters.net", "source": "planespotters"}
    assert planespotters.parse({"photos": []}) is None


def _page(i, title, lic, artist="<a href='x'>Bob</a>"):
    return {"index": i, "title": title, "imageinfo": [{
        "thumburl": f"https://u/{i}.jpg", "descriptionurl": f"https://c/{i}",
        "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}}}]}


def test_commons_license_and_kind_filter():
    payload = {"query": {"pages": {
        "1": _page(1, "File:JetBlue A321neo NC.jpg", "CC BY-NC 2.0"),
        "2": _page(2, "File:JetBlue A321neo cabin.jpg", "CC BY-SA 4.0"),
        "3": _page(3, "File:JetBlue A321neo N2002J.jpg", "CC BY-SA 4.0"),
    }}}
    ext = commons.parse(payload, "exterior")
    assert ext["url"] == "https://u/3.jpg"
    assert ext["credit"] == "Photo: Bob, CC BY-SA 4.0, via Wikimedia Commons"
    assert commons.parse(payload, "interior")["url"] == "https://u/2.jpg"
    assert commons.parse(payload, "exterior", blocked={"File:JetBlue A321neo N2002J.jpg"}) is None


def test_commons_exterior_must_show_whole_plane():
    """Belly / planform shots and close-ups of one part are never used as the livery photo."""
    def page(i, title):
        return {"index": i, "title": title, "imageinfo": [{"url": f"https://u/{i}.jpg", "descriptionurl": "d",
                                                           "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}
    payload = {"query": {"pages": {"1": page(1, "File:JetBlue Airbus A220-300 N3196J planform view.jpg"),
                                   "2": page(2, "File:JetBlue A220 engine close-up.jpg"),
                                   "3": page(3, "File:JetBlue Airbus A220-300 N3044J at TPA.jpg")}}}
    assert commons.parse(payload, "exterior")["url"] == "https://u/3.jpg"
    assert commons.partial_view("https://thumb.wikimedia.org/a/b/JetBlue_Airbus_A220-300_N3196J_planform_view.jpg/960px-x.jpg")
    assert not commons.partial_view("https://thumb.wikimedia.org/x/Frontier_Airbus_A320neo_N354FR_BWI_MD2.jpg")
    assert not commons.partial_view("https://u/Boeing_737_(Scimitar_Winglets)_landing.jpg")


def test_partial_exterior_is_hidden_and_refetched():
    from bots import enricher
    cached = {"asset_key": "B6|Airbus A220-300", "exterior_source": "commons", "fetched_at": "2099-01-01T00:00:00+00:00",
              "exterior_url": "https://thumb/JetBlue_Airbus_A220-300_N3196J_planform_view.jpg"}
    assert enricher.with_curated(cached)["exterior_url"] is None
    assert not enricher._fresh(cached)
