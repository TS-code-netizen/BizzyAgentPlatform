from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

SALES_COLUMN_TYPES = (
    "{'date': 'DATE', 'product_id': 'VARCHAR', 'product': 'VARCHAR', 'quantity': 'INTEGER', "
    "'revenue': 'DECIMAL(14,2)', 'cost_of_goods_sold': 'DECIMAL(14,2)', 'channel': 'VARCHAR'}"
)
PRODUCT_CATEGORY_TYPES = "{'product_id': 'VARCHAR', 'category': 'VARCHAR'}"


def sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}/{self.end.isoformat()}"


def comparison_windows(as_of: date, window_days: int = 7) -> tuple[Window, Window]:
    """Return (baseline, recent): two adjacent, inclusive windows ending on as_of."""
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    recent = Window(as_of - timedelta(days=window_days - 1), as_of)
    baseline = Window(recent.start - timedelta(days=window_days), recent.start - timedelta(days=1))
    return baseline, recent


@dataclass(frozen=True)
class ProductSales:
    product_id: str
    product: str
    baseline_revenue: Decimal
    recent_revenue: Decimal
    baseline_units: int
    recent_units: int
    last_sale_date: date | None

    @property
    def revenue_change(self) -> Decimal:
        return self.recent_revenue - self.baseline_revenue

    @property
    def baseline_average_price(self) -> Decimal | None:
        if not self.baseline_units:
            return None
        return self.baseline_revenue / self.baseline_units

    @property
    def recent_average_price(self) -> Decimal | None:
        if not self.recent_units:
            return None
        return self.recent_revenue / self.recent_units

    @property
    def volume_effect(self) -> Decimal:
        """Revenue change explained by units at the baseline product price."""
        baseline_price = self.baseline_average_price
        if baseline_price is None:
            return self.recent_revenue
        return Decimal(self.recent_units - self.baseline_units) * baseline_price

    @property
    def price_mix_effect(self) -> Decimal:
        """Residual revenue change after the product-level volume effect."""
        return self.revenue_change - self.volume_effect


@dataclass(frozen=True)
class ChannelSales:
    channel: str
    baseline_revenue: Decimal
    recent_revenue: Decimal


@dataclass(frozen=True)
class CategoryMargin:
    category: str
    revenue: Decimal
    cogs: Decimal

    @property
    def margin_pct(self) -> float | None:
        if not self.revenue:
            return None
        return round(float((self.revenue - self.cogs) / self.revenue * 100), 2)


@dataclass(frozen=True)
class SalesSummary:
    baseline: Window
    recent: Window
    baseline_revenue: Decimal
    recent_revenue: Decimal
    recent_cogs: Decimal
    days_with_sales: int
    products: list[ProductSales]
    channels: list[ChannelSales]
    categories: list[CategoryMargin]

    @property
    def revenue_change(self) -> Decimal:
        return self.recent_revenue - self.baseline_revenue

    @property
    def revenue_change_pct(self) -> float | None:
        if not self.baseline_revenue:
            return None
        return round(float((self.recent_revenue / self.baseline_revenue - 1) * 100), 2)

    @property
    def baseline_units(self) -> int:
        return sum(product.baseline_units for product in self.products)

    @property
    def recent_units(self) -> int:
        return sum(product.recent_units for product in self.products)

    @property
    def recent_gross_margin_pct(self) -> float | None:
        # Margin is total gross profit over total revenue, never an average of line percentages.
        if not self.recent_revenue:
            return None
        return round(float((self.recent_revenue - self.recent_cogs) / self.recent_revenue * 100), 2)

    @property
    def volume_effect(self) -> Decimal:
        return sum((product.volume_effect for product in self.products), Decimal(0))

    @property
    def price_mix_effect(self) -> Decimal:
        return self.revenue_change - self.volume_effect

    @property
    def top_decliner(self) -> ProductSales | None:
        decliners = [product for product in self.products if product.revenue_change < 0]
        return min(decliners, key=lambda product: (product.revenue_change, product.product_id), default=None)

    @property
    def stopped_selling(self) -> list[ProductSales]:
        return [product for product in self.products if product.baseline_revenue > 0 and product.recent_units == 0]

    def top_products(self, limit: int = 5) -> list[ProductSales]:
        sellers = [product for product in self.products if product.recent_revenue > 0]
        return sorted(sellers, key=lambda product: (-product.recent_revenue, product.product_id))[:limit]

    def baseline_top_products(self, limit: int = 5) -> list[ProductSales]:
        sellers = [product for product in self.products if product.baseline_revenue > 0]
        return sorted(sellers, key=lambda product: (-product.baseline_revenue, product.product_id))[:limit]

    def share_of_decline_pct(self, product: ProductSales) -> float | None:
        if self.revenue_change >= 0:
            return None
        return round(float(product.revenue_change / self.revenue_change * 100), 2)

    @property
    def coverage(self) -> float:
        total_days = (self.recent.end - self.baseline.start).days + 1
        return self.days_with_sales / total_days


def summarise_sales(data_dir: Path, as_of: date, window_days: int = 7) -> SalesSummary:
    baseline, recent = comparison_windows(as_of, window_days)
    sales_path = data_dir / "sales.csv"
    products_path = data_dir / "products.csv"
    if not sales_path.exists():
        raise FileNotFoundError(f"sales.csv not found in {data_dir}")

    window_params = {
        "baseline_start": baseline.start,
        "baseline_end": baseline.end,
        "recent_start": recent.start,
        "recent_end": recent.end,
    }

    def params(*names: str) -> dict[str, date]:
        return {name: window_params[name] for name in names}

    con = duckdb.connect()
    try:
        con.execute(
            f"""
            CREATE TEMP TABLE sales AS
            SELECT date, product_id, product, quantity, revenue, cost_of_goods_sold, channel
            FROM read_csv({sql_path(sales_path)}, header = true, types = {SALES_COLUMN_TYPES})
            WHERE date <= $recent_end
            """,
            params("recent_end"),
        )
        product_rows = con.execute(
            """
            SELECT * FROM (
                SELECT
                    product_id,
                    arg_max(product, date) AS product,
                    COALESCE(SUM(revenue) FILTER (WHERE date BETWEEN $baseline_start AND $baseline_end), 0) AS baseline_revenue,
                    COALESCE(SUM(revenue) FILTER (WHERE date BETWEEN $recent_start AND $recent_end), 0) AS recent_revenue,
                    COALESCE(SUM(quantity) FILTER (WHERE date BETWEEN $baseline_start AND $baseline_end), 0) AS baseline_units,
                    COALESCE(SUM(quantity) FILTER (WHERE date BETWEEN $recent_start AND $recent_end), 0) AS recent_units,
                    MAX(date) AS last_sale_date
                FROM sales
                GROUP BY product_id
            )
            WHERE baseline_revenue > 0 OR recent_revenue > 0
            ORDER BY product_id
            """,
            window_params,
        ).fetchall()
        channel_rows = con.execute(
            """
            SELECT * FROM (
                SELECT
                    channel,
                    COALESCE(SUM(revenue) FILTER (WHERE date BETWEEN $baseline_start AND $baseline_end), 0) AS baseline_revenue,
                    COALESCE(SUM(revenue) FILTER (WHERE date BETWEEN $recent_start AND $recent_end), 0) AS recent_revenue
                FROM sales
                GROUP BY channel
            )
            WHERE baseline_revenue > 0 OR recent_revenue > 0
            ORDER BY channel
            """,
            window_params,
        ).fetchall()
        recent_cogs, days_with_sales = con.execute(
            """
            SELECT
                COALESCE(SUM(cost_of_goods_sold) FILTER (WHERE date BETWEEN $recent_start AND $recent_end), 0),
                COUNT(DISTINCT date) FILTER (WHERE date BETWEEN $baseline_start AND $recent_end)
            FROM sales
            """,
            params("baseline_start", "recent_start", "recent_end"),
        ).fetchone()
        category_rows = []
        if products_path.exists():
            category_rows = con.execute(
                f"""
                SELECT p.category, SUM(s.revenue), SUM(s.cost_of_goods_sold)
                FROM sales AS s
                JOIN read_csv({sql_path(products_path)}, header = true, types = {PRODUCT_CATEGORY_TYPES}) AS p
                    ON p.product_id = s.product_id
                WHERE s.date BETWEEN $recent_start AND $recent_end
                GROUP BY p.category
                ORDER BY p.category
                """,
                params("recent_start", "recent_end"),
            ).fetchall()
    finally:
        con.close()

    products = [
        ProductSales(
            product_id=product_id,
            product=product,
            baseline_revenue=Decimal(baseline_revenue),
            recent_revenue=Decimal(recent_revenue),
            baseline_units=int(baseline_units),
            recent_units=int(recent_units),
            last_sale_date=last_sale_date,
        )
        for product_id, product, baseline_revenue, recent_revenue, baseline_units, recent_units, last_sale_date in product_rows
    ]
    return SalesSummary(
        baseline=baseline,
        recent=recent,
        baseline_revenue=sum((product.baseline_revenue for product in products), Decimal(0)),
        recent_revenue=sum((product.recent_revenue for product in products), Decimal(0)),
        recent_cogs=Decimal(recent_cogs),
        days_with_sales=int(days_with_sales),
        products=products,
        channels=[
            ChannelSales(channel=channel, baseline_revenue=Decimal(baseline_revenue), recent_revenue=Decimal(recent_revenue))
            for channel, baseline_revenue, recent_revenue in channel_rows
        ],
        categories=[
            CategoryMargin(category=category, revenue=Decimal(revenue), cogs=Decimal(cogs))
            for category, revenue, cogs in category_rows
        ],
    )
