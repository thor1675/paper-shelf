import pytest

from app import split_sentences


@pytest.mark.parametrize(
    "text, expected",
    [
        ("We propose X. It is fast.", ["We propose X.", "It is fast."]),
        # 略語の後ろでは分けない
        ("As shown in Fig. 3, it works. See Sec. 2 for details.", ["As shown in Fig. 3, it works.", "See Sec. 2 for details."]),
        ("Smith et al. (2020) showed this. We agree.", ["Smith et al. (2020) showed this.", "We agree."]),
        # 小文字で始まる続き（i.e. など）は文の始まりではない
        ("e.g. Negation fails. i.e. Always.", ["e.g. Negation fails. i.e. Always."]),
        ("We propose X. It is fast.", ["We propose X.", "It is fast."]),
        # 1 文字の頭文字（A. Smith）でも分けない
        ("This is by A. Smith and J. Doe. Next.", ["This is by A. Smith and J. Doe.", "Next."]),
        # 小数や小文字の続きでは分けない
        ("The score is 0.5 here. it continues.", ["The score is 0.5 here. it continues."]),
        ("", []),
    ],
)
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected
