from korea_service_record import citations


def test_navy_dsm_uses_the_supplied_department_of_the_navy_form():
    facts = {
        "country": 602,
        "rank": "Lieutenant Commander",
        "name": "Edward G. Meyer III",
        "unit": "Carrier Air Wing 11",
        "earned_raw": "1951.04.18",
    }
    certificate = citations.certificate(
        "en", 602031, facts, "1951.04.18", [])

    assert certificate["template"] == "Navy_dsm"
    assert certificate["header"] == "DEPARTMENT OF THE NAVY"
    assert certificate["pre"] == [
        "TO ALL WHO SHALL SEE THESE PRESENTS, GREETINGS, THIS IS TO CERTIFY THAT",
        "THE SECRETARY OF THE NAVY HAS ON THIS DAY AWARDED THE",
    ]
    assert certificate["title"] == "DISTINGUISHED SERVICE MEDAL"
    assert certificate["to"] == "TO"
    assert certificate["name"] == "LIEUTENANT COMMANDER EDWARD G. MEYER III"
    assert certificate["service"] == ""
    assert certificate["reason"] == (
        "FOR DISTINGUISHED AND EXCEPTIONAL SERVICE TO THE UNITED STATES OF "
        "AMERICA WHILE SERVING AS COMMANDING OFFICER OF THE CARRIER AIR WING 11 "
        "DURING COMBAT OPERATIONS IN KOREA."
    )
    assert certificate["given"] == [
        "GIVEN UNDER MY HAND IN THE CITY OF WASHINGTON, DC",
        "THIS 18TH DAY OF APRIL 1951",
    ]
    assert certificate["signer"] == "Francis P. Matthews"
