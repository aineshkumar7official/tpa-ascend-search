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
