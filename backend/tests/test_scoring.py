import pytest

from app.services.scoring import bayesian_score


def test_few_reviews_do_not_beat_many_reviews():
    c = 4.2
    five_of_two = bayesian_score(2, 5.0, c, 20)
    four8_of_900 = bayesian_score(900, 4.8, c, 20)
    assert four8_of_900 > five_of_two  # contoh dari spesifikasi


def test_formula_values():
    # (v/(v+m))*R + (m/(v+m))*C
    assert bayesian_score(20, 5.0, 3.0, 20) == pytest.approx(4.0)
    assert bayesian_score(0, 5.0, 3.0, 20) == pytest.approx(3.0)  # tanpa ulasan -> prior (C)
    assert bayesian_score(10**9, 4.5, 3.0, 20) == pytest.approx(4.5, abs=1e-6)


def test_unknown_inputs_give_none():
    assert bayesian_score(None, 4.5, 4.0, 20) is None
    assert bayesian_score(10, None, 4.0, 20) is None


def test_m_zero_returns_raw_rating_and_zero_zero_returns_c():
    assert bayesian_score(5, 4.4, 4.0, 0) == pytest.approx(4.4)
    assert bayesian_score(0, 4.4, 4.0, 0) == 4.0


def test_negative_rejected():
    with pytest.raises(ValueError):
        bayesian_score(-1, 4.0, 4.0, 20)


def test_larger_m_pulls_harder_toward_mean():
    a = bayesian_score(10, 5.0, 3.0, 5)
    b = bayesian_score(10, 5.0, 3.0, 50)
    assert a > b > 3.0
