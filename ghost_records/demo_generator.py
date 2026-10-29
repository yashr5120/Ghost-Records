"""Demo data generator producing synthetic CSVs and SQLite database with seeded anomalies."""

import sqlite3
from pathlib import Path

import pandas as pd

from ghost_records.config import CONFIG

# Explicit Ground Truth Registry for Seeded Anomalies
SEEDED_ANOMALY_REGISTRY = {
    "customers": {
        "exact_duplicates": 2,  # Rows 3 and 4 (CUST-103)
        "duplicate_identifiers": 2,  # CUST-105 appears twice with differing names
        "missing_required_values": 2,  # CUST-110 and CUST-111 have empty/whitespace email
        "invalid_dates": 2,  # CUST-115 ("INVALID-DATE-9999"), CUST-116 ("2024/31/12")
        "numeric_outliers": 1,  # CUST-120 has lifetime_spend = 950000.0 (IQR outlier)
        "negative_values": 0,
    },
    "products": {
        "exact_duplicates": 0,
        "duplicate_identifiers": 0,
        "missing_required_values": 1,  # PROD-08 has blank SKU
        "invalid_dates": 0,
        "negative_values": 2,  # PROD-09 stock_quantity = -15, PROD-10 unit_price = -49.99
        "numeric_outliers": 0,
    },
    "orders": {
        "exact_duplicates": 2,  # ORD-508 duplicated identically
        "duplicate_identifiers": 2,  # ORD-510 appears twice with conflicting quantities
        "orphaned_foreign_keys_customer": 2,  # ORD-501 (CUST-9999), ORD-502 (CUST-8888)
        "orphaned_foreign_keys_product": 2,  # ORD-503 (PROD-999), ORD-504 (PROD-888)
        "missing_required_values": 1,  # ORD-520 has null customer_id
        "invalid_dates": 1,  # ORD-515 has order_date = "2024-99-99"
        "negative_values": 1,  # ORD-518 has quantity = -5
    },
}


def generate_customers_df() -> pd.DataFrame:
    """Generate synthetic customers dataset with seeded anomalies."""
    records = [
        {"customer_id": "CUST-101", "name": "Elena Rostova", "email": "elena.r@example.com", "created_date": "2023-01-15", "country": "US", "lifetime_spend": 450.0},
        {"customer_id": "CUST-102", "name": "Marcus Vance", "email": "marcus.v@example.com", "created_date": "2023-02-10", "country": "UK", "lifetime_spend": 320.5},
        # Exact duplicate pair (Row 2 & 3)
        {"customer_id": "CUST-103", "name": "Alice Smith", "email": "alice.smith@example.com", "created_date": "2023-03-01", "country": "CA", "lifetime_spend": 120.0},
        {"customer_id": "CUST-103", "name": "Alice Smith", "email": "alice.smith@example.com", "created_date": "2023-03-01", "country": "CA", "lifetime_spend": 120.0},
        {"customer_id": "CUST-104", "name": "David Kim", "email": "d.kim@example.com", "created_date": "2023-03-12", "country": "KR", "lifetime_spend": 890.0},
        # Conflicting identifier duplicate (CUST-105 has two different names)
        {"customer_id": "CUST-105", "name": "Bob Vance", "email": "bob@vancerefrig.com", "created_date": "2023-04-05", "country": "US", "lifetime_spend": 560.0},
        {"customer_id": "CUST-105", "name": "Bob Vance Refrigeration", "email": "bob.corp@vancerefrig.com", "created_date": "2023-04-05", "country": "US", "lifetime_spend": 560.0},
        {"customer_id": "CUST-106", "name": "Chloe Bennett", "email": "chloe.b@example.com", "created_date": "2023-04-20", "country": "GB", "lifetime_spend": 210.0},
        {"customer_id": "CUST-107", "name": "Raj Patel", "email": "raj.patel@example.com", "created_date": "2023-05-11", "country": "IN", "lifetime_spend": 670.0},
        {"customer_id": "CUST-108", "name": "Sofia Garcia", "email": "sofia.g@example.com", "created_date": "2023-06-01", "country": "ES", "lifetime_spend": 415.0},
        {"customer_id": "CUST-109", "name": "Tariq Mansour", "email": "tariq.m@example.com", "created_date": "2023-06-18", "country": "AE", "lifetime_spend": 530.0},
        # Missing required values (empty string and None)
        {"customer_id": "CUST-110", "name": "Grace Hopper", "email": "", "created_date": "2023-07-04", "country": "US", "lifetime_spend": 750.0},
        {"customer_id": "CUST-111", "name": "Ada Lovelace", "email": None, "created_date": "2023-07-15", "country": "UK", "lifetime_spend": 980.0},
        {"customer_id": "CUST-112", "name": "Lucas Meyer", "email": "lucas.m@example.com", "created_date": "2023-08-01", "country": "DE", "lifetime_spend": 340.0},
        {"customer_id": "CUST-113", "name": "Hannah Abbott", "email": "hannah.a@example.com", "created_date": "2023-08-19", "country": "US", "lifetime_spend": 280.0},
        {"customer_id": "CUST-114", "name": "Kenji Sato", "email": "kenji.s@example.com", "created_date": "2023-09-02", "country": "JP", "lifetime_spend": 610.0},
        # Invalid date strings
        {"customer_id": "CUST-115", "name": "Nora Thorne", "email": "nora.t@example.com", "created_date": "INVALID-DATE-9999", "country": "AU", "lifetime_spend": 190.0},
        {"customer_id": "CUST-116", "name": "Leo Valenti", "email": "leo.v@example.com", "created_date": "2024/31/12", "country": "IT", "lifetime_spend": 420.0},
        {"customer_id": "CUST-117", "name": "Ingrid Berg", "email": "ingrid.b@example.com", "created_date": "2023-10-10", "country": "SE", "lifetime_spend": 510.0},
        {"customer_id": "CUST-118", "name": "Mateo Silva", "email": "mateo.s@example.com", "created_date": "2023-11-05", "country": "BR", "lifetime_spend": 390.0},
        {"customer_id": "CUST-119", "name": "Amira Nour", "email": "amira.n@example.com", "created_date": "2023-11-28", "country": "EG", "lifetime_spend": 460.0},
        # Extreme statistical outlier
        {"customer_id": "CUST-120", "name": "Tycoon Ghost", "email": "tycoon@phantomcorp.io", "created_date": "2023-12-01", "country": "US", "lifetime_spend": 950000.0},
        {"customer_id": "CUST-121", "name": "Liam Scott", "email": "liam.s@example.com", "created_date": "2023-12-14", "country": "NZ", "lifetime_spend": 310.0},
        {"customer_id": "CUST-122", "name": "Yuki Tanaka", "email": "yuki.t@example.com", "created_date": "2024-01-08", "country": "JP", "lifetime_spend": 580.0},
    ]
    return pd.DataFrame(records)


def generate_products_df() -> pd.DataFrame:
    """Generate synthetic products dataset with seeded anomalies."""
    records = [
        {"product_id": "PROD-01", "sku": "SKU-AUDIO-01", "title": "Ghost Echo Headphones", "unit_price": 149.99, "stock_quantity": 45, "is_active": "true"},
        {"product_id": "PROD-02", "sku": "SKU-AUDIO-02", "title": "Phantom Noise Mic", "unit_price": 89.50, "stock_quantity": 30, "is_active": "true"},
        {"product_id": "PROD-03", "sku": "SKU-PERIPH-01", "title": "Specter Mechanical Keyboard", "unit_price": 129.00, "stock_quantity": 60, "is_active": "true"},
        {"product_id": "PROD-04", "sku": "SKU-PERIPH-02", "title": "Wraith Gaming Mouse", "unit_price": 69.99, "stock_quantity": 80, "is_active": "true"},
        {"product_id": "PROD-05", "sku": "SKU-DISPLAY-01", "title": "Banshee UltraWide 34\"", "unit_price": 499.00, "stock_quantity": 15, "is_active": "true"},
        {"product_id": "PROD-06", "sku": "SKU-CABLE-01", "title": "Braided USB-C Cable 2m", "unit_price": 19.99, "stock_quantity": 200, "is_active": "true"},
        {"product_id": "PROD-07", "sku": "SKU-DESK-01", "title": "Haunted Oak Desk Mat", "unit_price": 34.00, "stock_quantity": 110, "is_active": "true"},
        # Blank / missing SKU
        {"product_id": "PROD-08", "sku": "", "title": "Cryptic Unlabeled Widget", "unit_price": 25.00, "stock_quantity": 50, "is_active": "true"},
        # Negative stock quantity
        {"product_id": "PROD-09", "sku": "SKU-ERROR-09", "title": "Deficit Memory Stick", "unit_price": 45.00, "stock_quantity": -15, "is_active": "true"},
        # Negative unit price
        {"product_id": "PROD-10", "sku": "SKU-ERROR-10", "title": "Subsidized Promo Dongle", "unit_price": -49.99, "stock_quantity": 25, "is_active": "false"},
        {"product_id": "PROD-11", "sku": "SKU-LIGHT-01", "title": "Apparition RGB Lightbar", "unit_price": 79.99, "stock_quantity": 40, "is_active": "true"},
        {"product_id": "PROD-12", "sku": "SKU-POWER-01", "title": "Poltergeist 100W GaN Charger", "unit_price": 59.99, "stock_quantity": 75, "is_active": "true"},
    ]
    return pd.DataFrame(records)


def generate_orders_df() -> pd.DataFrame:
    """Generate synthetic orders dataset with seeded anomalies."""
    records = [
        {"order_id": "ORD-500", "customer_id": "CUST-101", "product_id": "PROD-01", "order_date": "2024-02-01", "quantity": 1, "total_amount": 149.99, "status": "completed"},
        # Orphan customer references (CUST-9999 and CUST-8888 do not exist in customers)
        {"order_id": "ORD-501", "customer_id": "CUST-9999", "product_id": "PROD-02", "order_date": "2024-02-02", "quantity": 2, "total_amount": 179.00, "status": "pending"},
        {"order_id": "ORD-502", "customer_id": "CUST-8888", "product_id": "PROD-03", "order_date": "2024-02-03", "quantity": 1, "total_amount": 129.00, "status": "shipped"},
        # Orphan product references (PROD-999 and PROD-888 do not exist in products)
        {"order_id": "ORD-503", "customer_id": "CUST-102", "product_id": "PROD-999", "order_date": "2024-02-04", "quantity": 1, "total_amount": 250.00, "status": "completed"},
        {"order_id": "ORD-504", "customer_id": "CUST-104", "product_id": "PROD-888", "order_date": "2024-02-05", "quantity": 3, "total_amount": 99.00, "status": "shipped"},
        {"order_id": "ORD-505", "customer_id": "CUST-106", "product_id": "PROD-04", "order_date": "2024-02-06", "quantity": 1, "total_amount": 69.99, "status": "completed"},
        {"order_id": "ORD-506", "customer_id": "CUST-107", "product_id": "PROD-05", "order_date": "2024-02-07", "quantity": 1, "total_amount": 499.00, "status": "completed"},
        {"order_id": "ORD-507", "customer_id": "CUST-108", "product_id": "PROD-06", "order_date": "2024-02-08", "quantity": 2, "total_amount": 39.98, "status": "shipped"},
        # Exact duplicate pair (Row 8 & 9)
        {"order_id": "ORD-508", "customer_id": "CUST-109", "product_id": "PROD-07", "order_date": "2024-02-09", "quantity": 1, "total_amount": 34.00, "status": "completed"},
        {"order_id": "ORD-508", "customer_id": "CUST-109", "product_id": "PROD-07", "order_date": "2024-02-09", "quantity": 1, "total_amount": 34.00, "status": "completed"},
        # Duplicate identifier with conflicting quantities
        {"order_id": "ORD-510", "customer_id": "CUST-112", "product_id": "PROD-01", "order_date": "2024-02-10", "quantity": 1, "total_amount": 149.99, "status": "completed"},
        {"order_id": "ORD-510", "customer_id": "CUST-112", "product_id": "PROD-01", "order_date": "2024-02-10", "quantity": 4, "total_amount": 599.96, "status": "pending"},
        {"order_id": "ORD-511", "customer_id": "CUST-113", "product_id": "PROD-02", "order_date": "2024-02-11", "quantity": 1, "total_amount": 89.50, "status": "shipped"},
        {"order_id": "ORD-512", "customer_id": "CUST-114", "product_id": "PROD-03", "order_date": "2024-02-12", "quantity": 2, "total_amount": 258.00, "status": "completed"},
        {"order_id": "ORD-513", "customer_id": "CUST-117", "product_id": "PROD-04", "order_date": "2024-02-13", "quantity": 1, "total_amount": 69.99, "status": "completed"},
        {"order_id": "ORD-514", "customer_id": "CUST-118", "product_id": "PROD-05", "order_date": "2024-02-14", "quantity": 1, "total_amount": 499.00, "status": "completed"},
        # Invalid date format
        {"order_id": "ORD-515", "customer_id": "CUST-119", "product_id": "PROD-06", "order_date": "2024-99-99", "quantity": 1, "total_amount": 19.99, "status": "completed"},
        {"order_id": "ORD-516", "customer_id": "CUST-121", "product_id": "PROD-07", "order_date": "2024-02-16", "quantity": 2, "total_amount": 68.00, "status": "completed"},
        {"order_id": "ORD-517", "customer_id": "CUST-122", "product_id": "PROD-11", "order_date": "2024-02-17", "quantity": 1, "total_amount": 79.99, "status": "shipped"},
        # Negative quantity
        {"order_id": "ORD-518", "customer_id": "CUST-101", "product_id": "PROD-12", "order_date": "2024-02-18", "quantity": -5, "total_amount": -299.95, "status": "cancelled"},
        {"order_id": "ORD-519", "customer_id": "CUST-102", "product_id": "PROD-01", "order_date": "2024-02-19", "quantity": 1, "total_amount": 149.99, "status": "completed"},
        # Missing required foreign key
        {"order_id": "ORD-520", "customer_id": None, "product_id": "PROD-02", "order_date": "2024-02-20", "quantity": 1, "total_amount": 89.50, "status": "pending"},
        {"order_id": "ORD-521", "customer_id": "CUST-104", "product_id": "PROD-03", "order_date": "2024-02-21", "quantity": 1, "total_amount": 129.00, "status": "completed"},
    ]
    return pd.DataFrame(records)


def write_demo_files(output_dir: Path = CONFIG.demo_dir) -> dict[str, Path]:
    """Write synthetic customers, products, orders CSVs and a demo SQLite database."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cust_df = generate_customers_df()
    prod_df = generate_products_df()
    orders_df = generate_orders_df()

    cust_path = output_dir / "customers.csv"
    prod_path = output_dir / "products.csv"
    orders_path = output_dir / "orders.csv"
    db_path = output_dir / "ghost_store_demo.sqlite"

    cust_df.to_csv(cust_path, index=False)
    prod_df.to_csv(prod_path, index=False)
    orders_df.to_csv(orders_path, index=False)

    # Also build SQLite database with declared schema
    conn = sqlite3.connect(str(db_path))
    cust_df.to_sql("customers", conn, if_exists="replace", index=False)
    prod_df.to_sql("products", conn, if_exists="replace", index=False)
    orders_df.to_sql("orders", conn, if_exists="replace", index=False)
    conn.close()

    return {
        "customers_csv": cust_path,
        "products_csv": prod_path,
        "orders_csv": orders_path,
        "sqlite_db": db_path,
    }


if __name__ == "__main__":
    paths = write_demo_files()
    print("Demo files successfully written:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
