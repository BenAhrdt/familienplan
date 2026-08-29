from app.api.v1.router import school_event_matches_class


def test_school_event_class_filter_keeps_matching_and_school_wide_events():
    assert school_event_matches_class("3a Elternabend", None, "3A")
    assert school_event_matches_class("Schulfest für alle Klassen", None, "3A")
    assert school_event_matches_class("Schultheater der Länder – Theater AG 4", None, "3A")
    assert school_event_matches_class("Projekttag", None, "3A")


def test_school_event_class_filter_rejects_other_classes_and_understands_groups():
    assert not school_event_matches_class("3c Elternabend", None, "3A")
    assert not school_event_matches_class("4 a/b Klassenfahrt", None, "3A")
    assert school_event_matches_class("3 a/b Ausflug", None, "3A")
    assert school_event_matches_class("Klassenstufe 3 Sportfest", None, "3A")
    assert not school_event_matches_class("Jahrgang 4 Sportfest", None, "3A")
