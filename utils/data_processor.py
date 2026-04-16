import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataProcessor:
    def __init__(self):
        self.required_columns = ["Контрагент", "товар", "цена", "скидка", "условия поставки"]
        self.optional_columns: List[str] = []

    def validate_dataframe(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        missing_columns = [col for col in self.required_columns if col not in df.columns]
        if missing_columns:
            logger.error("Missing required columns: %s", missing_columns)
            return False, missing_columns
        return True, []

    def load_excel_file(self, file_path: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix == ".xls":
                df = pd.read_excel(file_path, engine="xlrd")
            elif suffix in (".xlsx", ".xlsm"):
                df = pd.read_excel(file_path, engine="openpyxl")
            else:
                return None, (
                    f"Неподдерживаемый формат «{suffix}». Используйте .xlsx, .xlsm или .xls."
                )
        except Exception as e:
            logger.exception("Error loading Excel file")
            return None, f"Не удалось прочитать файл: {e}"

        df.columns = df.columns.astype(str).str.strip()
        ok, missing = self.validate_dataframe(df)
        if not ok:
            return None, "Отсутствуют обязательные колонки: " + ", ".join(missing)

        df = self.clean_dataframe(df)
        before = len(df)
        df = df.dropna(subset=["цена"])
        dropped = before - len(df)
        if dropped:
            logger.warning("Dropped %s rows with invalid or empty price", dropped)
        if df.empty:
            return None, "Нет строк с заполненной числовой ценой в колонке «цена»."

        return df, None

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df_clean = df.copy()
        df_clean.columns = df_clean.columns.astype(str).str.strip()

        df_clean["цена"] = pd.to_numeric(df_clean["цена"], errors="coerce")
        df_clean["скидка"] = pd.to_numeric(df_clean["скидка"], errors="coerce")

        df_clean["цена_со_скидкой"] = df_clean["цена"] * (1 - df_clean["скидка"].fillna(0) / 100)

        df_clean["Контрагент"] = df_clean["Контрагент"].astype(str).str.strip()
        df_clean["товар"] = df_clean["товар"].astype(str).str.strip()
        df_clean["условия поставки"] = df_clean["условия поставки"].astype(str).str.strip()

        return df_clean

    def prepare_analysis_data(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []

        for i, (_, row) in enumerate(df.iterrows(), start=1):
            discount = float(row["скидка"]) if not pd.isna(row["скидка"]) else 0.0
            price = float(row["цена"]) if not pd.isna(row["цена"]) else 0.0
            if "цена_со_скидкой" in row and not pd.isna(row["цена_со_скидкой"]):
                price_with_discount = float(row["цена_со_скидкой"])
            else:
                price_with_discount = price * (1 - discount / 100)

            proposal = {
                "id": i,
                "контрагент": row["Контрагент"],
                "товар": row["товар"],
                "цена": price,
                "скидка": discount,
                "условия_поставки": row["условия поставки"],
                "цена_со_скидкой": price_with_discount,
            }
            proposals.append(proposal)

        return proposals

    def get_summary_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        def to_float(value: Any) -> float:
            try:
                if pd.isna(value):
                    return 0.0
                return float(value)
            except (ValueError, TypeError):
                return 0.0

        stats: Dict[str, Any] = {
            "total_proposals": len(df),
            "unique_contractors": df["Контрагент"].nunique(),
            "unique_products": df["товар"].nunique(),
            "avg_price": to_float(df["цена"].mean()),
            "avg_discount": to_float(df["скидка"].mean()),
            "min_price": to_float(df["цена"].min()),
            "max_price": to_float(df["цена"].max()),
        }

        if "цена_со_скидкой" in df.columns:
            stats["avg_price_with_discount"] = to_float(df["цена_со_скидкой"].mean())
            stats["min_price_with_discount"] = to_float(df["цена_со_скидкой"].min())
            stats["max_price_with_discount"] = to_float(df["цена_со_скидкой"].max())

        return stats
