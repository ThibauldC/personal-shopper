from pydantic import BaseModel, Field


class Recipe(BaseModel):
    title: str
    url: str
    prep_time_min: int | None = None
    servings: int | None = None
    image_url: str | None = None
    keywords: list[str] = Field(default_factory=list)
    recipe_category: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    raw_metadata: dict = Field(default_factory=dict)
