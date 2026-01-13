"""Manage user-specific email categories"""

from __future__ import annotations

import sqlite3

from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.utils.categories import DEFAULT_CATEGORIES


class CategoryManager:
    """Manages email categories using centralized database connection pool"""

    def __init__(self):
        """Initialize category manager (schema managed by database.py)"""
        # No initialization needed - schema is managed centrally

    def get_categories(self, user_id: str = "default") -> list[dict]:
        """Get active categories for a user"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name, description, color
                FROM categories
                WHERE user_id = ? AND is_active = 1
                ORDER BY name
            """,
                (user_id,),
            )

            categories = [
                {"name": row[0], "description": row[1], "color": row[2]}
                for row in cursor.fetchall()
            ]

        # If no categories exist, return defaults
        if not categories:
            self._initialize_default_categories(user_id)
            return DEFAULT_CATEGORIES

        return categories

    def _initialize_default_categories(self, user_id: str):
        """Initialize user with default categories"""
        with db_transaction() as conn:
            for cat in DEFAULT_CATEGORIES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO categories (user_id, name, description, color)
                    VALUES (?, ?, ?, ?)
                """,
                    (user_id, cat["name"], cat["description"], cat["color"]),
                )

    def add_category(
        self,
        name: str,
        description: str = "",
        color: str = "#808080",
        user_id: str = "default",
    ) -> bool:
        """
        Add a new custom category

        Side Effects:
        - Writes to `categories` table in shopq.db
        - Makes category available for future classifications
        - Committed immediately via db_transaction
        """
        try:
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO categories (user_id, name, description, color)
                    VALUES (?, ?, ?, ?)
                """,
                    (user_id, name, description, color),
                )
            return True
        except sqlite3.IntegrityError:
            return False  # Category already exists

    def get_category_names(self, user_id: str = "default") -> list[str]:
        """Get just the category names (for LLM prompt)"""
        categories = self.get_categories(user_id)
        return [cat["name"] for cat in categories]

    def get_prompt_context(self, user_id: str = "default") -> str:
        """Generate category list for LLM prompt"""
        categories = self.get_categories(user_id)

        lines = []
        for cat in categories:
            lines.append(f"- {cat['name']}: {cat['description']}")

        return "\n".join(lines)
