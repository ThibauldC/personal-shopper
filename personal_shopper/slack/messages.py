from personal_shopper.recipes.models import Recipe


def build_recipe_blocks(recipes: list[Recipe], offered_ids: list[int]) -> list[dict]:
    """Build Slack Block Kit blocks for recipe options in Dutch."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Jouw receptopties voor deze week",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    for recipe, offered_id in zip(recipes, offered_ids):
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{recipe.url}|{recipe.title}>*",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Selecteer", "emoji": True},
                    "value": str(offered_id),
                    "action_id": "select_recipe",
                    "style": "primary",
                },
            }
        )

        meta_parts: list[str] = []
        if recipe.prep_time_min is not None:
            meta_parts.append(f"⏱ {recipe.prep_time_min} min")
        if recipe.servings is not None:
            meta_parts.append(f"👥 {recipe.servings} personen")

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": " | ".join(meta_parts) if meta_parts else "_Geen details_",
                    }
                ],
            }
        )

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_Klik op 'Selecteer' om een of meerdere recepten te kiezen._",
            },
        }
    )

    return blocks
