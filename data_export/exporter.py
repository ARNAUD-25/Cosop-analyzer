"""
data_export/exporter.py
------------------------
Exporte les partenaires vers un fichier Excel (.xlsx).
Aucune logique de traitement ici — seulement de l'export.

3 feuilles :
  1. Summary      → chiffres clés
  2. Partner List → tous les partenaires avec leurs détails
  3. By Category  → tableau croisé par catégorie
"""

import io
import pandas as pd


def export_to_excel(partners: list[dict]) -> bytes:
    """
    Prend la liste des partenaires.
    Retourne les bytes d'un fichier Excel prêt à télécharger.
    """

    # io.BytesIO = fichier en mémoire (pas besoin de sauvegarder sur disque)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        # ── Feuille 1 : Summary ───────────────────────────────────────────
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

        # ── Feuille 2 : Partner List ──────────────────────────────────────
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

        # ── Feuille 3 : By Category ───────────────────────────────────────
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

    # Remettre le curseur au début avant de lire les bytes
    output.seek(0)
    return output.read()
