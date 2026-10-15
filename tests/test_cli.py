"""The three questions the command line has to answer."""

from festival.cli import main


def test_programme_keeps_the_late_show_on_the_previous_day(capsys) -> None:
    assert main(["programme", "2027-06-11"]) == 0
    output = capsys.readouterr().out
    assert "After Hours" in output
    assert "Sat 01:00-02:00" in output


def test_the_next_morning_is_another_day(capsys) -> None:
    assert main(["programme", "2027-06-12"]) == 0
    output = capsys.readouterr().out
    assert "Stand-up Lab" in output
    assert "After Hours" not in output


def test_artists_are_listed_with_their_shows(capsys) -> None:
    assert main(["artists"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[2].startswith("Élodie Marchal")
    assert "3 shows" in lines[2]


def test_now_shows_the_stage_and_the_next_three(capsys) -> None:
    assert main(["now", "--at", "2027-06-11T21:00"]) == 0
    output = capsys.readouterr().out
    assert "At 2027-06-11 21:00" in output
    assert "Tall Tales" in output
    assert "Straight Face" in output
    assert "Late Laughs" in output
    assert "After Hours" in output


def test_a_bad_day_is_a_sentence(capsys) -> None:
    assert main(["programme", "Friday"]) == 1
    assert "not a day" in capsys.readouterr().err
