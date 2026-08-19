# tests/test_heuristics.py
# Purpose: statistical detector unit tests — direction, floors, robustness.


from app.core.heuristics import heuristic_score


def _uniform(units=14):
    return " ".join(["The quick brown fox jumps over the lazy dog again."] * units)


def _varied():
    sentences = [
        "He ran.",
        "After a long and exhausting journey through the mountains, the small group finally reached the remote village.",
        "Why?",
        "Nobody knew, and nobody asked.",
        "The dog barked.",
        "It was, to everyone's surprise, completely silent afterwards.",
    ]
    return " ".join(sentences * 3)


def test_uniform_text_scores_higher_than_varied():
    assert heuristic_score(_uniform()) > heuristic_score(_varied())


def test_short_text_returns_neutral():
    assert heuristic_score("Just a few words here.") == 50.0


def test_dense_transitions_score_high():
    with_t = ("Moreover, the goalkeeper cleared the ball swiftly. Furthermore, the striker missed "
              "the penalty kick. In addition, the referee consulted the replay monitor. Consequently, "
              "the crowd erupted in protest. Nevertheless, the captain kept his composure. "
              "In conclusion, the match ended in a draw. Therefore, both teams advanced to the next "
              "round. Overall, the tournament surprised every analyst. ")
    without_t = ("The goalkeeper cleared the ball swiftly. The striker missed the penalty kick. "
                 "The referee consulted the replay monitor. The crowd erupted in protest. "
                 "The captain kept his composure. The match ended in a draw. Both teams advanced "
                 "to the next round. The tournament surprised every analyst. ")
    assert heuristic_score(with_t) > heuristic_score(without_t)


def test_score_bounds():
    assert 0 <= heuristic_score(_uniform()) <= 100
    assert 0 <= heuristic_score("") <= 100


def test_punctuation_variety_lowers_score():
    plain = "One two three four five six seven eight nine ten eleven twelve."
    rich = "One, two: three — four; five? six! seven… eight (nine) 'ten' \"eleven\" twelve."
    assert heuristic_score(rich) < heuristic_score(plain)


def test_repetition_raises_score():
    repetitive = "error occurred error occurred error occurred error occurred error occurred " * 4
    assert heuristic_score(repetitive) > 60