import pytest
from castelino.triggers.speech.scorer import score_sentence, load_lexicon

LEX = load_lexicon("hawkish_dovish_v1")

def test_neutral_sentence_scores_near_zero():
    s = score_sentence("Today the Committee met to discuss policy.", lexicon=LEX)
    assert -0.05 <= s <= 0.05

def test_hawkish_phrase_scores_positive():
    s = score_sentence("Further firming may be warranted.", lexicon=LEX)
    assert s > 0.5

def test_dovish_phrase_scores_negative():
    s = score_sentence("We will be patient and remain accommodative.", lexicon=LEX)
    assert s < -0.5

def test_clipped_to_unit_range():
    s = score_sentence(
        "Further firming further tightening additional firming remain restrictive.",
        lexicon=LEX,
    )
    assert -1.0 <= s <= 1.0

def test_hedging_dampens_magnitude():
    bare = score_sentence("Further firming is warranted.", lexicon=LEX)
    hedged = score_sentence("Further firming may be warranted.", lexicon=LEX)
    assert abs(hedged) < abs(bare)


from castelino.triggers.speech.scorer import score_speech


def test_score_speech_filters_neutral_sentences():
    sentences = [
        "Good morning, everyone.",                    # neutral
        "Today the Committee met.",                   # neutral
        "Further firming may be warranted.",          # hawkish
        "Inflation persistent and elevated.",         # hawkish
    ]
    result = score_speech(sentences, lexicon=LEX)
    assert result.n_policy_sentences >= 1
    assert result.score > 0.2


def test_score_speech_zero_when_no_policy_sentences():
    result = score_speech(["Hello.", "Good to be here."], lexicon=LEX)
    assert result.score == 0.0
    assert result.n_policy_sentences == 0


def test_split_sentences_handles_abbreviations():
    from castelino.triggers.speech.scorer import split_sentences
    text = "The U.S. economy grew. Inflation cooled. Mr. Powell spoke."
    out = split_sentences(text)
    assert len(out) == 3
    assert out[0].startswith("The U.S.")
