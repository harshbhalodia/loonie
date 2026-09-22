"""Default data seeded for a brand-new user."""
from app.models import WealthCategoryGroup

# Mirrors the previous hardcoded CategoryGroup enum so behavior is unchanged out of the box.
# is_essential=True groups count toward the liquidity/runway "essential spend" calculation.
DEFAULT_CATEGORY_GROUPS = [
    ("Fixed", "#2f6d4f", True),
    ("Variable", "#a15c07", True),
    ("Adhoc", "#b3261e", False),
    ("Investments", "#275475", False),
    ("New Investments", "#6d4fa1", False),
    ("Income", "#1f4d38", False),
]


def seed_default_category_groups(db, user_id: str) -> None:
    for order, (name, color, is_essential) in enumerate(DEFAULT_CATEGORY_GROUPS):
        db.add(
            WealthCategoryGroup(
                user_id=user_id,
                name=name,
                color=color,
                sort_order=order,
                is_essential=is_essential,
            )
        )
    db.commit()
