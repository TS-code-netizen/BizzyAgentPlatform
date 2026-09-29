from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path

import duckdb

from backend.tools.sales_tools import sql_path

INVENTORY_COLUMN_TYPES = (
    "{'product_id': 'VARCHAR', 'product': 'VARCHAR', 'current_stock': 'INTEGER', 'reorder_level': 'INTEGER', "
    "'lead_time': 'INTEGER', 'supplier_id': 'VARCHAR', 'supplier': 'VARCHAR', "
    "'next_expected_receipt_date': 'DATE', 'stock_value': 'DECIMAL(14,2)'}"
)
HISTORY_COLUMN_TYPES = "{'date': 'DATE', 'product_id': 'VARCHAR', 'units_sold': 'INTEGER', 'unfulfilled_demand': 'INTEGER'}"
PRODUCT_COLUMN_TYPES = "{'product_id': 'VARCHAR', 'unit_price': 'DECIMAL(14,2)'}"


class StockRisk(str, Enum):
    OUT_OF_STOCK = "out_of_stock"
    AT_RISK = "at_risk"
    OK = "ok"


@dataclass(frozen=True)
class ProductStock:
    product_id: str
    product: str
    supplier_id: str
    supplier: str
    current_stock: int
    reorder_level: int
    lead_time_days: int
    next_expected_receipt_date: date | None
    incoming_qty: int | None
    stock_value: Decimal
    unit_price: Decimal | None
    avg_daily_demand: float
    avg_daily_units_sold: float
    recent_unfulfilled_units: int
    first_recent_unfulfilled_date: date | None
    history_days: int

    @property
    def days_of_cover(self) -> float | None:
        if self.avg_daily_demand <= 0:
            return None
        return self.current_stock / self.avg_daily_demand

    @property
    def at_or_below_reorder_level(self) -> bool:
        return self.current_stock <= self.reorder_level

    @property
    def risk(self) -> StockRisk:
        # Every demo product sits at or below its reorder level, so the threshold alone would flag
        # the whole catalogue; risk means stock cannot last until a new order could arrive.
        if self.current_stock <= 0:
            return StockRisk.OUT_OF_STOCK
        cover = self.days_of_cover
        if cover is not None and cover < self.lead_time_days:
            return StockRisk.AT_RISK
        return StockRisk.OK

    @property
    def recent_lost_revenue(self) -> Decimal | None:
        if self.unit_price is None:
            return None
        return self.unit_price * self.recent_unfulfilled_units

    def days_until_restock(self, as_of: date) -> int:
        # Receipts land before that day's sales, so the delivery day itself is not lost.
        if self.next_expected_receipt_date is not None:
            return max(0, (self.next_expected_receipt_date - as_of).days - 1)
        return self.lead_time_days

    def projected_lost_units(self, as_of: date) -> float:
        if self.risk is not StockRisk.OUT_OF_STOCK:
            return 0.0
        return self.avg_daily_demand * self.days_until_restock(as_of)

    def projected_lost_revenue(self, as_of: date) -> Decimal | None:
        if self.unit_price is None:
            return None
        return self.unit_price * Decimal(str(round(self.projected_lost_units(as_of), 6)))

    def projected_stockout_date(self, as_of: date) -> date | None:
        if self.current_stock <= 0:
            return as_of
        if self.avg_daily_demand <= 0:
            return None
        return as_of + timedelta(days=math.ceil(self.current_stock / self.avg_daily_demand))

    @property
    def order_qty_is_provisional(self) -> bool:
        return self.next_expected_receipt_date is not None and self.incoming_qty is None

    @property
    def suggested_order_qty(self) -> int:
        """Order up to lead-time demand plus the reorder level as a safety buffer."""
        target = self.avg_daily_demand * self.lead_time_days + self.reorder_level
        known_incoming = self.incoming_qty or 0
        return max(0, math.ceil(round(target - self.current_stock - known_incoming, 6)))


@dataclass(frozen=True)
class InventoryStatus:
    as_of: date
    recent_start: date
    lookback_days: int
    products: list[ProductStock]

    @property
    def out_of_stock(self) -> list[ProductStock]:
        items = [product for product in self.products if product.risk is StockRisk.OUT_OF_STOCK]
        return sorted(items, key=lambda product: (-(product.recent_lost_revenue or 0), product.product_id))

    @property
    def at_risk(self) -> list[ProductStock]:
        items = [product for product in self.products if product.risk is StockRisk.AT_RISK]
        return sorted(items, key=lambda product: (product.days_of_cover or 0.0, product.product_id))

    @property
    def focus(self) -> ProductStock | None:
        return next(iter(self.out_of_stock or self.at_risk), None)

    @property
    def reorder_candidates(self) -> list[ProductStock]:
        return self.out_of_stock + self.at_risk

    @property
    def provisional_reorder_candidates(self) -> list[ProductStock]:
        return [product for product in self.reorder_candidates if product.order_qty_is_provisional]

    @property
    def at_or_below_reorder(self) -> list[ProductStock]:
        return sorted(
            (product for product in self.products if product.at_or_below_reorder_level),
            key=lambda product: product.product_id,
        )

    @property
    def total_suggested_order_units(self) -> int:
        return sum(product.suggested_order_qty for product in self.reorder_candidates)

    @property
    def total_stock_value(self) -> Decimal:
        return sum((product.stock_value for product in self.products), Decimal(0))

    def top_sellers(self, limit: int = 10) -> list[ProductStock]:
        sellers = [product for product in self.products if product.avg_daily_units_sold > 0]
        return sorted(sellers, key=lambda product: (-product.avg_daily_units_sold, product.product_id))[:limit]

    def highest_stock_value(self, limit: int = 3) -> list[ProductStock]:
        return sorted(self.products, key=lambda product: (-product.stock_value, product.product_id))[:limit]

    def longest_lead_time_suppliers(self, limit: int = 3) -> list[tuple[str, int]]:
        lead_times: dict[str, int] = {}
        for product in self.products:
            lead_times[product.supplier] = max(lead_times.get(product.supplier, 0), product.lead_time_days)
        return sorted(lead_times.items(), key=lambda item: (-item[1], item[0]))[:limit]

    def by_product_id(self, product_id: str) -> ProductStock | None:
        normalized = product_id.upper()
        return next((product for product in self.products if product.product_id.upper() == normalized), None)

    @property
    def coverage(self) -> float:
        if not self.products:
            return 0.0
        return sum(product.history_days for product in self.products) / (len(self.products) * self.lookback_days)


@dataclass(frozen=True)
class ReorderSimulation:
    product_id: str
    order_qty: int
    demand_uplift_pct: float
    effective_daily_demand: float
    stock_on_arrival: float
    days_of_cover_after_receipt: float | None
    expected_lost_units_before_receipt: float
    expected_lost_revenue_before_receipt: Decimal | None


def simulate_reorder(
    product: ProductStock,
    as_of: date,
    order_qty: int | None = None,
    demand_uplift_pct: float = 0.0,
) -> ReorderSimulation:
    """Project stock cover for a draft order without changing operational data."""
    if demand_uplift_pct <= -100:
        raise ValueError("demand_uplift_pct must be greater than -100")
    demand = round(product.avg_daily_demand * (1 + demand_uplift_pct / 100), 6)
    known_incoming = product.incoming_qty or 0
    suggested_for_scenario = max(
        0,
        math.ceil(
            round(
                demand * product.lead_time_days
                + product.reorder_level
                - product.current_stock
                - known_incoming,
                6,
            )
        ),
    )
    quantity = suggested_for_scenario if order_qty is None else order_qty
    if quantity < 0:
        raise ValueError("order_qty must not be negative")

    demand_until_receipt = round(demand * product.days_until_restock(as_of), 6)
    stock_on_arrival = round(max(0.0, product.current_stock - demand_until_receipt + known_incoming), 6)
    lost_units = round(max(0.0, demand_until_receipt - product.current_stock), 6)
    post_receipt_stock = stock_on_arrival + quantity
    cover = None if demand <= 0 else post_receipt_stock / demand
    lost_revenue = None
    if product.unit_price is not None:
        lost_revenue = product.unit_price * Decimal(str(round(lost_units, 6)))

    return ReorderSimulation(
        product_id=product.product_id,
        order_qty=quantity,
        demand_uplift_pct=demand_uplift_pct,
        effective_daily_demand=demand,
        stock_on_arrival=stock_on_arrival,
        days_of_cover_after_receipt=cover,
        expected_lost_units_before_receipt=lost_units,
        expected_lost_revenue_before_receipt=lost_revenue,
    )


def assess_inventory(
    data_dir: Path,
    as_of: date,
    window_days: int = 7,
    demand_lookback_days: int = 14,
) -> InventoryStatus:
    if window_days < 1 or demand_lookback_days < 1:
        raise ValueError("window_days and demand_lookback_days must be at least 1")
    paths = {name: data_dir / f"{name}.csv" for name in ("inventory", "inventory_history", "products")}
    missing = [path.name for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing {', '.join(missing)} in {data_dir}")

    recent_start = as_of - timedelta(days=window_days - 1)
    lookback_start = as_of - timedelta(days=demand_lookback_days - 1)
    con = duckdb.connect()
    try:
        inventory_columns = {
            row[0]
            for row in con.execute(
                f"DESCRIBE SELECT * FROM read_csv({sql_path(paths['inventory'])}, header = true)"
            ).fetchall()
        }
        incoming_qty_sql = "TRY_CAST(i.incoming_qty AS INTEGER)" if "incoming_qty" in inventory_columns else "NULL"
        rows = con.execute(
            f"""
            WITH history AS (
                SELECT
                    product_id,
                    SUM(units_sold + unfulfilled_demand) AS lookback_demand,
                    SUM(units_sold) AS lookback_units_sold,
                    COUNT(DISTINCT date) AS history_days,
                    COALESCE(SUM(unfulfilled_demand) FILTER (WHERE date >= $recent_start), 0) AS recent_unfulfilled,
                    MIN(date) FILTER (WHERE date >= $recent_start AND unfulfilled_demand > 0)
                        AS first_recent_unfulfilled_date
                FROM read_csv({sql_path(paths['inventory_history'])}, header = true, types = {HISTORY_COLUMN_TYPES})
                WHERE date BETWEEN $lookback_start AND $as_of
                GROUP BY product_id
            )
            SELECT
                i.product_id, i.product, i.supplier_id, i.supplier, i.current_stock, i.reorder_level, i.lead_time,
                i.next_expected_receipt_date, {incoming_qty_sql} AS incoming_qty, i.stock_value, p.unit_price,
                COALESCE(h.lookback_demand, 0), COALESCE(h.lookback_units_sold, 0), COALESCE(h.history_days, 0),
                COALESCE(h.recent_unfulfilled, 0), h.first_recent_unfulfilled_date
            FROM read_csv({sql_path(paths['inventory'])}, header = true, types = {INVENTORY_COLUMN_TYPES}) AS i
            LEFT JOIN read_csv({sql_path(paths['products'])}, header = true, types = {PRODUCT_COLUMN_TYPES}) AS p
                ON p.product_id = i.product_id
            LEFT JOIN history AS h ON h.product_id = i.product_id
            ORDER BY i.product_id
            """,
            {"recent_start": recent_start, "lookback_start": lookback_start, "as_of": as_of},
        ).fetchall()
    finally:
        con.close()

    products = [
        ProductStock(
            product_id=product_id,
            product=product,
            supplier_id=supplier_id,
            supplier=supplier,
            current_stock=int(current_stock),
            reorder_level=int(reorder_level),
            lead_time_days=int(lead_time),
            next_expected_receipt_date=next_receipt,
            incoming_qty=None if incoming_qty is None else int(incoming_qty),
            stock_value=Decimal(stock_value or 0),
            unit_price=None if unit_price is None else Decimal(unit_price),
            avg_daily_demand=(int(lookback_demand) / int(history_days)) if history_days else 0.0,
            avg_daily_units_sold=(int(lookback_units_sold) / int(history_days)) if history_days else 0.0,
            recent_unfulfilled_units=int(recent_unfulfilled),
            first_recent_unfulfilled_date=first_recent_unfulfilled,
            history_days=int(history_days),
        )
        for (
            product_id,
            product,
            supplier_id,
            supplier,
            current_stock,
            reorder_level,
            lead_time,
            next_receipt,
            incoming_qty,
            stock_value,
            unit_price,
            lookback_demand,
            lookback_units_sold,
            history_days,
            recent_unfulfilled,
            first_recent_unfulfilled,
        ) in rows
    ]
    return InventoryStatus(as_of=as_of, recent_start=recent_start, lookback_days=demand_lookback_days, products=products)
