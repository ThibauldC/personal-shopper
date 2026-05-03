from pydantic import BaseModel


class Recipe(BaseModel):
    title: str
    url: str
    prep_time_min: int | None = None
    servings: int | None = None
    image_url: str | None = None
    keywords: list[str] = []
    recipe_category: str | None = None
    ingredients: list[str] = []
    raw_metadata: dict = {}
