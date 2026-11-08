"""The trust check: only numbers and names from the plan's facts get through."""

from app.explain.check import MAX_WHY_CHARS, check, numbers_in

FACTS = '{"in": {"name": "João Pedro", "club": "Chelsea", "costs_m": 7.8}, "out": {"name": "Gibbs-White"}, "gain": 5.2, "this_gameweek": "GW12", "rivals_owning": "8 of 11", "managers": 1250}'
KNOWN = {"João Pedro", "Gibbs-White", "White", "Haaland", "Chelsea", "Arsenal", "CHE"}


def test_numbers_are_read_like_a_person_would() -> None:
    assert numbers_in("+5.2 pts, £7.8m, GW12, 8/11, 1,250 managers, 75%") == {5.2, 7.8, 12, 8, 11, 1250, 75}
    assert numbers_in("No numbers here.") == set()


def test_text_using_only_the_facts_passes() -> None:
    why = "João Pedro (£7.8m) gains you 5.2 expected points from GW12, and 8 of your 11 rivals own him. Gibbs-White doesn't."
    assert check(why, "Chelsea's form could dip.", FACTS, KNOWN) == []


def test_a_number_not_in_the_facts_fails() -> None:
    problems = check("João Pedro gains you 6.1 expected points.", "Fine.", FACTS, KNOWN)
    assert problems == ["'why' uses the number 6.1, which isn't in the facts."]


def test_rounding_matches_the_facts() -> None:
    assert check("A 5.20 point gain.", "None.", FACTS, KNOWN) == []


def test_a_player_or_club_not_in_the_facts_fails() -> None:
    problems = check("Bring in João Pedro, not Haaland.", "Arsenal away is tough.", FACTS, KNOWN)
    assert "'why' mentions Haaland, who isn't in the facts." in problems
    assert "'watch_out' mentions Arsenal, who isn't in the facts." in problems


def test_part_of_an_allowed_name_is_not_a_new_name() -> None:
    # "White" is a different player, but here it's only part of "Gibbs-White".
    assert check("Gibbs-White has tough games.", "None.", FACTS, KNOWN) == []


def test_unknown_words_are_not_flagged() -> None:
    assert check("Your squad looks strong.", "Rotation risk.", FACTS, KNOWN) == []


def test_empty_or_long_text_fails() -> None:
    assert check("", "x", FACTS, KNOWN)
    assert check("a" * (MAX_WHY_CHARS + 1), "x", FACTS, KNOWN)
