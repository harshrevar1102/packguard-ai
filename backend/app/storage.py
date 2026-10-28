import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from app.config import DATA_DIR
from app.models import Product, Analysis, ArtworkVersion


class StorageService:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.products_dir = self.data_dir / "products"
        self.products_dir.mkdir(parents=True, exist_ok=True)

    def _get_product_dir(self, product_id: str) -> Path:
        return self.products_dir / product_id

    def list_products(self) -> List[Product]:
        products = []
        if not self.products_dir.exists():
            return []
        
        for p_dir in self.products_dir.iterdir():
            if p_dir.is_dir():
                meta_file = p_dir / "product.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            products.append(Product(**data))
                    except Exception:
                        continue
        # Sort by updated_at descending
        products.sort(key=lambda p: p.updated_at, reverse=True)
        return products

    def get_product(self, product_id: str) -> Optional[Product]:
        meta_file = self._get_product_dir(product_id) / "product.json"
        if not meta_file.exists():
            return None
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Product(**data)
        except Exception:
            return None

    def find_product_by_name(self, name: str) -> Optional[Product]:
        name_clean = name.strip().lower()
        for p in self.list_products():
            if p.name.strip().lower() == name_clean:
                return p
        return None

    def save_product(self, product: Product) -> None:
        p_dir = self._get_product_dir(product.id)
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "analyses").mkdir(parents=True, exist_ok=True)
        (p_dir / "versions").mkdir(parents=True, exist_ok=True)
        (p_dir / "uploads").mkdir(parents=True, exist_ok=True)

        meta_file = p_dir / "product.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(product.model_dump_json(indent=2))

    def delete_product(self, product_id: str) -> bool:
        p_dir = self._get_product_dir(product_id)
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)
            return True
        return False

    def save_analysis(self, analysis: Analysis) -> None:
        p_dir = self._get_product_dir(analysis.product_id)
        analyses_dir = p_dir / "analyses"
        analyses_dir.mkdir(parents=True, exist_ok=True)

        analysis_file = analyses_dir / f"{analysis.id}.json"
        with open(analysis_file, "w", encoding="utf-8") as f:
            f.write(analysis.model_dump_json(indent=2))

        # Update product's analysis list and updated_at
        product = self.get_product(analysis.product_id)
        if product:
            if analysis.id not in product.analysis_ids:
                product.analysis_ids.append(analysis.id)
            product.updated_at = analysis.timestamp
            self.save_product(product)

    def get_analysis(self, product_id: str, analysis_id: str) -> Optional[Analysis]:
        analysis_file = self._get_product_dir(product_id) / "analyses" / f"{analysis_id}.json"
        if not analysis_file.exists():
            return None
        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Analysis(**data)
        except Exception:
            return None

    def get_analyses_for_product(self, product_id: str) -> List[Analysis]:
        analyses = []
        p_dir = self._get_product_dir(product_id)
        analyses_dir = p_dir / "analyses"
        if not analyses_dir.exists():
            return []
        
        for af in analyses_dir.glob("*.json"):
            try:
                with open(af, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    analyses.append(Analysis(**data))
            except Exception:
                continue
        analyses.sort(key=lambda a: a.timestamp, reverse=True)
        return analyses

    def get_previous_analysis(self, product_id: str, current_analysis_id: Optional[str] = None) -> Optional[Analysis]:
        analyses = self.get_analyses_for_product(product_id)
        if not analyses:
            return None
        if current_analysis_id:
            analyses = [a for a in analyses if a.id != current_analysis_id]
        if not analyses:
            return None
        return analyses[0]

    def delete_analysis(self, product_id: str, analysis_id: str) -> bool:
        analysis_file = self._get_product_dir(product_id) / "analyses" / f"{analysis_id}.json"
        if analysis_file.exists():
            analysis_file.unlink(missing_ok=True)
            
            # Remove from product
            product = self.get_product(product_id)
            if product and analysis_id in product.analysis_ids:
                product.analysis_ids.remove(analysis_id)
                self.save_product(product)
            return True
        return False


storage = StorageService()
