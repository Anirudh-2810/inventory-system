"""Product model for inventory management."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class Product:
    """Represents a product in the inventory system."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    sku: str = ""
    barcode: str = ""
    description: str = ""
    category: str = ""
    unit_price: float = 0.0
    cost_price: float = 0.0
    quantity: int = 0
    reorder_level: int = 0
    supplier: str = ""
    owner_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_low_stock(self) -> bool:
        """Check if product is at or below reorder level."""
        return self.quantity <= self.reorder_level

    @property
    def profit_margin(self) -> float:
        """Calculate profit margin percentage."""
        if self.cost_price <= 0:
            return 0.0
        return ((self.unit_price - self.cost_price) / self.cost_price) * 100

    @property
    def total_value(self) -> float:
        """Calculate total inventory value for this product."""
        return self.quantity * self.unit_price

    def to_dict(self) -> dict:
        """Convert product to dictionary for serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'sku': self.sku,
            'barcode': self.barcode,
            'description': self.description,
            'category': self.category,
            'unit_price': self.unit_price,
            'cost_price': self.cost_price,
            'quantity': self.quantity,
            'reorder_level': self.reorder_level,
            'supplier': self.supplier,
            'owner_id': self.owner_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Product':
        """Create product from dictionary."""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            sku=data.get('sku', ''),
            barcode=data.get('barcode', ''),
            description=data.get('description', ''),
            category=data.get('category', ''),
            unit_price=data.get('unit_price', 0.0),
            cost_price=data.get('cost_price', 0.0),
            quantity=data.get('quantity', 0),
            reorder_level=data.get('reorder_level', 0),
            supplier=data.get('supplier', ''),
            owner_id=data.get('owner_id', ''),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else datetime.now()
        )