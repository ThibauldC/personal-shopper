import pytest

from personal_shopper.recipes.models import Recipe
from personal_shopper.slack.messages import build_recipe_blocks


@pytest.fixture
def recipes():
    return [
        Recipe(
            title="Pasta Pesto",
            url="https://example.com/r/R001",
            prep_time_min=25,
            servings=4,
            image_url="https://img.example.com/pasta.jpg",
        ),
        Recipe(
            title="Groentecurry",
            url="https://example.com/r/R002",
        ),
    ]


@pytest.fixture
def offered_ids():
    return [1, 2]


class TestBuildRecipeBlocks:
    def test_returns_list(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        assert isinstance(blocks, list)

    def test_contains_header(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        headers = [b for b in blocks if b.get("type") == "header"]
        assert len(headers) == 1

    def test_header_text_dutch(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        header = next(b for b in blocks if b.get("type") == "header")
        assert "week" in header["text"]["text"].lower()

    def test_recipe_titles_in_sections(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b.get("type") == "section" and "text" in b and "accessory" in b
        ]
        combined = " ".join(section_texts)
        assert "Pasta Pesto" in combined
        assert "Groentecurry" in combined

    def test_recipe_urls_in_sections(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        section_texts = " ".join(
            b["text"]["text"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        )
        assert "example.com/r/R001" in section_texts
        assert "example.com/r/R002" in section_texts

    def test_select_buttons_count(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        ]
        assert len(buttons) == 2

    def test_button_action_id(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        for b in blocks:
            if b.get("type") == "section" and "accessory" in b:
                assert b["accessory"]["action_id"] == "select_recipe"

    def test_button_values_match_offered_ids(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        values = [
            b["accessory"]["value"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        ]
        assert values == ["1", "2"]

    def test_button_text_dutch(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        for b in blocks:
            if b.get("type") == "section" and "accessory" in b:
                assert b["accessory"]["text"]["text"] == "Selecteer"

    def test_button_style_primary(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        for b in blocks:
            if b.get("type") == "section" and "accessory" in b:
                assert b["accessory"]["style"] == "primary"

    def test_context_blocks_count(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        contexts = [b for b in blocks if b.get("type") == "context"]
        assert len(contexts) == len(recipes)

    def test_prep_time_in_context(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        context_texts = " ".join(
            b["elements"][0]["text"]
            for b in blocks
            if b.get("type") == "context"
        )
        assert "25 min" in context_texts

    def test_servings_in_context(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        context_texts = " ".join(
            b["elements"][0]["text"]
            for b in blocks
            if b.get("type") == "context"
        )
        assert "4 personen" in context_texts

    def test_missing_metadata_fallback(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        context_texts = [
            b["elements"][0]["text"]
            for b in blocks
            if b.get("type") == "context"
        ]
        assert any("Geen details" in t for t in context_texts)

    def test_contains_dividers(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        dividers = [b for b in blocks if b.get("type") == "divider"]
        assert len(dividers) >= 1

    def test_footer_instruction_dutch(self, recipes, offered_ids):
        blocks = build_recipe_blocks(recipes, offered_ids)
        footer_texts = [
            b["text"]["text"]
            for b in blocks
            if b.get("type") == "section" and "accessory" not in b and "text" in b
        ]
        combined = " ".join(footer_texts)
        assert "Selecteer" in combined or "kiezen" in combined

    def test_empty_recipes(self):
        blocks = build_recipe_blocks([], [])
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_single_recipe(self):
        recipe = Recipe(title="Soep", url="https://example.com/r/R001", prep_time_min=15)
        blocks = build_recipe_blocks([recipe], [42])
        buttons = [b for b in blocks if b.get("type") == "section" and "accessory" in b]
        assert len(buttons) == 1
        assert buttons[0]["accessory"]["value"] == "42"
