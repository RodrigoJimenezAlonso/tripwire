import pytest

from tripwire.judge.numbers import extract, grade, matches, unit_multiplier


@pytest.mark.parametrize("text", [
    "Net sales were CHF 11,201.3 mn [sika-ar-2025 p.6].",
    "Sika's net sales reached CHF 11.2 billion in 2025.",
    "Net sales: 11’201.3 million",
    "11201 mn",
])
def test_same_figure_written_differently(text):
    assert matches(text, 11201.3, "CHF mn")


def test_wrong_figure_from_chart_axis_is_rejected():
    assert not matches("Net sales were CHF 11,000 mn.", 11201.3, "CHF mn")


def test_percentages_and_unicode_minus():
    assert matches("Net sales changed by –4.8% versus 2024.", -4.8, "%")
    assert not matches("Net sales changed by 4.8% versus 2024.", -4.8, "%")


def test_usd_billion_gold_vs_million_answer():
    assert matches("Group net income was USD 4,800 million.", 4.8, "USD bn")


def test_rounded_headline_figure_is_accepted():
    # Swiss Re's own highlights write 4,762 mn as "USD 4.8 billion"
    assert matches("Group net income was USD 4.8 billion.", 4762, "USD mn")
    assert not matches("Group net income was USD 4.7 billion.", 4762, "USD mn")


def test_too_coarse_rounding_is_rejected():
    assert not matches("Net sales were CHF 11 billion.", 11201.3, "CHF mn")
    assert not matches("Return on equity was 20%.", 19.6, "%")


def test_nearby_trap_value_is_rejected():
    # basic EPS 6.51 vs diluted 6.50: two decimals stated, so no rounding slack
    assert matches("Basic EPS was CHF 6.51.", 6.51, "CHF/share")
    assert not matches("Basic EPS was CHF 6.50.", 6.51, "CHF/share")


def test_trillion_answer_for_billion_gold():
    assert matches("Invested assets were USD 7.0 trillion.", 7005, "USD bn")


def test_unit_multiplier():
    assert unit_multiplier("CHF mn") == 1e6
    assert unit_multiplier("USD bn") == 1e9
    assert unit_multiplier("%") == 1.0


def test_extract_keeps_scale_when_given():
    assert extract("USD 4.8 billion") == [(4.8, 1e9)]
    assert extract("CHF 1,045.3") == [(1045.3, None)]


def test_grades():
    assert grade("Net profit was CHF 1,045.3 mn.", 1045.3, "CHF mn") == "correct"
    assert grade("Net profit was CHF 1,100 mn.", 1045.3, "CHF mn") == "wrong"
    assert grade("This information is not in the reports.", 1045.3, "CHF mn") == "abstained"
    # a year alone is not a stated figure
    assert grade("In 2025 profit decreased.", 1045.3, "CHF mn") == "no_number"
