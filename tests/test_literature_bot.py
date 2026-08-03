from literature_bot import paper_key, reconstruct_abstract, relevance


def make_work(title: str, abstract_words: list[str], work_type: str = "article"):
    inverted = {word: [index] for index, word in enumerate(abstract_words)}
    return {
        "id": "https://openalex.org/W123",
        "display_name": title,
        "type": work_type,
        "abstract_inverted_index": inverted,
        "keywords": [],
        "topics": [],
    }


def test_reconstruct_abstract():
    inverted = {"acidic": [2], "CO2": [0], "electroreduction": [1]}
    assert reconstruct_abstract(inverted) == "CO2 electroreduction acidic"


def test_accepts_acidic_co2rr():
    work = make_work(
        "Selective CO2 electroreduction in acidic media",
        ["A", "proton", "exchange", "membrane", "suppresses", "hydrogen"],
    )
    accepted, matched = relevance(work)
    assert accepted
    assert "acidic" in matched


def test_rejects_alkaline_only_co2rr():
    work = make_work(
        "CO2 electroreduction in alkaline flow cells",
        ["Potassium", "hydroxide", "improves", "carbon", "monoxide"],
    )
    accepted, _ = relevance(work)
    assert not accepted


def test_uses_normalized_doi_as_key():
    work = {"doi": "https://doi.org/10.1000/ABC.Def", "id": "W1"}
    assert paper_key(work) == "10.1000/abc.def"
