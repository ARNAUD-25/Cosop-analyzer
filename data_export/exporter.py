"""
Exports to an Excel file (.xlsx)

3 sheets:
  1. Summary      
  2. Partner List 
  3. By Category 
"""

import io
import pandas as pd


def export_to_excel(partners: list[dict]) -> bytes:
    """
    Takes the list of partners.
    Returns the bytes of an Excel file ready for download.
    """

    # io.BytesIO = in-memory file (no need to save to disk)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        # ── Sheet 1: Summary ──
        summary_data = {
            "Field": [
                "Total Partners",
                "Active Partners",
                "Potential Partners",
                "Unknown Status",
                "Number of Categories",
            ],
            "Value": [
                len(partners),
                sum(1 for p in partners if p.get("status") == "Active"),
                sum(1 for p in partners if p.get("status") == "Potential"),
                sum(1 for p in partners if p.get("status") == "Unknown"),
                len(set(p.get("category", "Other") for p in partners)),
            ],
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

        # ── Sheet 2: List of partners ──
        rows = []
        for p in partners:
            rows.append({
                "Name":         p.get("name", ""),
                "Category":     p.get("category", ""),
                "Status":       p.get("status", ""),
                "Roles":        ", ".join(p.get("roles") or []),
                "Sectors":      ", ".join(p.get("sectors") or []),
                "Mentions":     p.get("mention_count", 0),
                "First Page":   p.get("first_page", ""),
                "Description":  p.get("description", ""),
            })

        df_partners = pd.DataFrame(rows)
        df_partners.to_excel(writer, sheet_name="Partner List", index=False)

        # ── Sheet 3: By Category ──
        if not df_partners.empty:
            by_category = (
                df_partners
                .groupby("Category")
                .agg(
                    Count=("Name", "count"),
                    Avg_Mentions=("Mentions", "mean"),
                )
                .reset_index()
                .sort_values("Count", ascending=False)
            )
            by_category["Avg_Mentions"] = by_category["Avg_Mentions"].round(1)
            by_category.to_excel(writer, sheet_name="By Category", index=False)

    # Reset cursor to the beginning before reading bytes
    output.seek(0)
    return output.read()
