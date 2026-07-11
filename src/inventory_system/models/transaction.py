"""Transaction model for inventory management."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class InventoryTransaction:
    """Represents an inventory transaction (purchase, sale, adjustment)."""

    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str = ""
    quantity_change: int = 0
    transaction_type: str = ""  # 'purchase', 'sale', 'adjustment', 'return'
    notes: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert transaction to dictionary."""
        return {
            'transaction_id': self.transaction_id,
            'product_id': self.product_id,
            'quantity_change': self.quantity_change,
            'transaction_type': self.transaction_type,
            'notes': self.notes,
            'timestamp': self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'InventoryTransaction':
        """Create transaction from dictionary."""
        return cls(
            transaction_id=data.get('transaction_id', str(uuid.uuid4())),
            product_id=data.get('product_id', ''),
            quantity_change=int(data.get('quantity_change', 0)),
            transaction_type=data.get('transaction_type', ''),
            notes=data.get('notes', ''),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.now()
        )