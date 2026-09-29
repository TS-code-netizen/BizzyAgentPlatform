from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median

from backend.models.agent import RecommendedAction, RiskLevel
from backend.models.health import AlertSeverity, BusinessAlert, SalesInventoryHealth
from backend.tools.inventory_tools import InventoryStatus, ProductStock, assess_inventory
from backend.tools.sales_tools import SalesSummary, summarise_sales


def _money(value: Decimal) -> float:
    return float(round(value, 2))


def _severity_order(severity: AlertSeverity) -> int:
    return {
        AlertSeverity.CRITICAL: 0,
        AlertSeverity.WARNING: 1,
        AlertSeverity.INFO: 2,
    }[severity]


def _revenue_alert(summary: SalesSummary, as_of: date) -> BusinessAlert | None:
    change_pct = summary.revenue_change_pct
    if change_pct is None or change_pct > -5:
        return None
    focus = summary.top_decliner
    severity = AlertSeverity.CRITICAL if change_pct <= -10 else AlertSeverity.WARNING
    parameters = {} if focus is None else {"product_id": focus.product_id}
    return BusinessAlert(
        alert_id=f"sales-revenue-decline-{as_of.isoformat()}",
        alert_type="revenue_decline",
        severity=severity,
        agent="sales",
        title="Sales revenue is below the baseline period",
        message=(
            f"Revenue fell {abs(change_pct):.1f}% from SGD {summary.baseline_revenue:,.2f} "
            f"to SGD {summary.recent_revenue:,.2f}."
        ),
        as_of=as_of,
        product_id=None if focus is None else focus.product_id,
        metric="revenue_change_pct",
        current_value=change_pct,
        threshold=-5.0,
        recommended_action=RecommendedAction(
            type="investigate_revenue_decline",
            risk_level=RiskLevel.GREEN,
            reason="Revenue has crossed the monitoring threshold versus the adjacent baseline period.",
            parameters=parameters,
            expected_impact={"revenue_gap_sgd": abs(_money(summary.revenue_change))},
        ),
    )


def _stockout_alert(product: ProductStock, as_of: date) -> BusinessAlert:
    projected_loss = product.projected_lost_revenue(as_of)
    expected_impact = {
        "recent_lost_revenue_sgd": (
            None if product.recent_lost_revenue is None else _money(product.recent_lost_revenue)
        ),
        "projected_lost_revenue_until_restock_sgd": (
            None if projected_loss is None else _money(projected_loss)
        ),
    }
    if product.order_qty_is_provisional:
        action = RecommendedAction(
            type="verify_inbound_quantity",
            risk_level=RiskLevel.AMBER,
            reason="An existing receipt has no quantity; another order could duplicate replenishment.",
            parameters={
                "product_id": product.product_id,
                "supplier_id": product.supplier_id,
                "existing_receipt_date": product.next_expected_receipt_date.isoformat(),
                "provisional_additional_order_qty": product.suggested_order_qty,
            },
            expected_impact={"decision_blocked_until": "incoming_quantity_verified", **expected_impact},
        )
    else:
        action = RecommendedAction(
            type="prepare_purchase_order",
            risk_level=RiskLevel.AMBER,
            reason="The product is out of stock while demand is continuing.",
            parameters={
                "product_id": product.product_id,
                "supplier_id": product.supplier_id,
                "quantity": product.suggested_order_qty,
                "proposed_order_earliest_arrival": (
                    as_of + timedelta(days=product.lead_time_days)
                ).isoformat(),
            },
            expected_impact=expected_impact,
        )
    return BusinessAlert(
        alert_id=f"inventory-stockout-{product.product_id}-{as_of.isoformat()}",
        alert_type="stockout",
        severity=AlertSeverity.CRITICAL,
        agent="inventory",
        title=f"{product.product_id} is out of stock",
        message=(
            f"{product.product} has no stock and {product.recent_unfulfilled_units} recent units of "
            "demand were unfulfilled."
        ),
        as_of=as_of,
        product_id=product.product_id,
        metric="current_stock",
        current_value=product.current_stock,
        threshold=1,
        recommended_action=action,
    )


def _stock_risk_alert(product: ProductStock, as_of: date) -> BusinessAlert:
    stockout_date = product.projected_stockout_date(as_of)
    if product.order_qty_is_provisional:
        action = RecommendedAction(
            type="verify_inbound_quantity",
            risk_level=RiskLevel.AMBER,
            reason="An expected receipt exists, but its quantity is unknown.",
            parameters={
                "product_id": product.product_id,
                "supplier_id": product.supplier_id,
                "existing_receipt_date": product.next_expected_receipt_date.isoformat(),
                "provisional_additional_order_qty": product.suggested_order_qty,
            },
        )
    else:
        action = RecommendedAction(
            type="prepare_purchase_order",
            risk_level=RiskLevel.AMBER,
            reason=(
                f"Projected stockout on {stockout_date.isoformat() if stockout_date else 'an unknown date'} "
                "precedes replenishment coverage."
            ),
            parameters={
                "product_id": product.product_id,
                "supplier_id": product.supplier_id,
                "quantity": product.suggested_order_qty,
                "proposed_order_earliest_arrival": (
                    as_of + timedelta(days=product.lead_time_days)
                ).isoformat(),
            },
        )
    return BusinessAlert(
        alert_id=f"inventory-stock-risk-{product.product_id}-{as_of.isoformat()}",
        alert_type="stockout_risk",
        severity=AlertSeverity.WARNING,
        agent="inventory",
        title=f"{product.product_id} may run out before replenishment",
        message=(
            f"{product.product} has {product.current_stock} units and "
            f"{product.days_of_cover:.1f} days of cover against a {product.lead_time_days}-day lead time."
        ),
        as_of=as_of,
        product_id=product.product_id,
        metric="days_of_cover",
        current_value=round(product.days_of_cover or 0, 1),
        threshold=product.lead_time_days,
        recommended_action=action,
    )


def _slow_moving_alerts(status: InventoryStatus) -> list[BusinessAlert]:
    stocked = [product for product in status.products if product.stock_value > 0]
    if not stocked:
        return []
    value_threshold = median(float(product.stock_value) for product in stocked)
    velocity_threshold = median(product.avg_daily_units_sold for product in stocked)
    candidates = [
        product
        for product in stocked
        if float(product.stock_value) >= value_threshold
        and product.avg_daily_units_sold <= velocity_threshold
        and product.risk.value == "ok"
    ]
    candidates.sort(key=lambda product: (-product.stock_value, product.product_id))
    return [
        BusinessAlert(
            alert_id=f"inventory-slow-moving-{product.product_id}-{status.as_of.isoformat()}",
            alert_type="slow_moving_inventory",
            severity=AlertSeverity.INFO,
            agent="inventory",
            title=f"{product.product_id} ties up relatively high inventory value",
            message=(
                f"{product.product} holds SGD {product.stock_value:,.2f} of inventory while selling "
                f"{product.avg_daily_units_sold:.1f} units per day."
            ),
            as_of=status.as_of,
            product_id=product.product_id,
            metric="stock_value_sgd",
            current_value=_money(product.stock_value),
            threshold=round(value_threshold, 2),
            recommended_action=RecommendedAction(
                type="review_slow_moving_inventory",
                risk_level=RiskLevel.GREEN,
                reason="The product combines above-median stock value with below-median sales velocity.",
                parameters={"product_id": product.product_id},
            ),
        )
        for product in candidates[:3]
    ]


def _coverage_alert(
    sales: SalesSummary,
    inventory: InventoryStatus,
    as_of: date,
) -> BusinessAlert | None:
    coverage = min(sales.coverage, inventory.coverage)
    if coverage >= 0.9:
        return None
    return BusinessAlert(
        alert_id=f"data-coverage-{as_of.isoformat()}",
        alert_type="data_quality",
        severity=AlertSeverity.WARNING,
        agent="system",
        title="Analysis data coverage is incomplete",
        message=f"Minimum source coverage is {coverage:.1%}; conclusions should be reviewed before action.",
        as_of=as_of,
        metric="minimum_data_coverage_pct",
        current_value=round(coverage * 100, 1),
        threshold=90.0,
        recommended_action=RecommendedAction(
            type="review_data_pipeline",
            risk_level=RiskLevel.GREEN,
            reason="Missing reporting days reduce confidence in trends and forecasts.",
        ),
    )


def build_sales_inventory_health(
    data_dir: Path,
    as_of: date,
    window_days: int = 7,
) -> SalesInventoryHealth:
    sales = summarise_sales(data_dir, as_of, window_days)
    inventory = assess_inventory(data_dir, as_of, window_days)

    alerts: list[BusinessAlert] = []
    revenue_alert = _revenue_alert(sales, as_of)
    if revenue_alert is not None:
        alerts.append(revenue_alert)
    alerts.extend(_stockout_alert(product, as_of) for product in inventory.out_of_stock)
    alerts.extend(_stock_risk_alert(product, as_of) for product in inventory.at_risk[:5])
    alerts.extend(_slow_moving_alerts(inventory))
    coverage_alert = _coverage_alert(sales, inventory, as_of)
    if coverage_alert is not None:
        alerts.append(coverage_alert)
    alerts.sort(key=lambda alert: (_severity_order(alert.severity), alert.alert_type, alert.alert_id))

    revenue_penalty = min(25.0, max(0.0, -(sales.revenue_change_pct or 0.0)))
    stockout_penalty = min(30.0, len(inventory.out_of_stock) * 15.0)
    risk_ratio = 0.0 if not inventory.products else len(inventory.at_risk) / len(inventory.products)
    stock_risk_penalty = min(20.0, risk_ratio * 20.0)
    minimum_coverage = min(sales.coverage, inventory.coverage)
    coverage_penalty = max(0.0, (0.9 - minimum_coverage) / 0.9 * 10.0)
    score_breakdown = {
        "revenue_trend_penalty": round(revenue_penalty, 1),
        "stockout_penalty": round(stockout_penalty, 1),
        "stock_risk_penalty": round(stock_risk_penalty, 1),
        "data_coverage_penalty": round(coverage_penalty, 1),
    }
    score = max(0, round(100 - sum(score_breakdown.values())))
    health_status = "healthy" if score >= 80 else "watch" if score >= 60 else "at_risk"

    recent_lost_revenue = sum(
        (product.recent_lost_revenue or Decimal(0) for product in inventory.out_of_stock),
        Decimal(0),
    )
    projected_lost_revenue = sum(
        (product.projected_lost_revenue(as_of) or Decimal(0) for product in inventory.out_of_stock),
        Decimal(0),
    )
    metrics = {
        "baseline_revenue_sgd": _money(sales.baseline_revenue),
        "recent_revenue_sgd": _money(sales.recent_revenue),
        "revenue_change_pct": sales.revenue_change_pct,
        "recent_units": sales.recent_units,
        "gross_margin_pct": sales.recent_gross_margin_pct,
        "out_of_stock_product_count": len(inventory.out_of_stock),
        "at_risk_product_count": len(inventory.at_risk),
        "reorder_candidate_count": len(inventory.reorder_candidates),
        "provisional_reorder_candidate_count": len(inventory.provisional_reorder_candidates),
        "total_suggested_order_units": inventory.total_suggested_order_units,
        "total_stock_value_sgd": _money(inventory.total_stock_value),
        "recent_lost_revenue_sgd": _money(recent_lost_revenue),
        "projected_lost_revenue_until_restock_sgd": _money(projected_lost_revenue),
        "sales_data_coverage_pct": round(sales.coverage * 100, 1),
        "inventory_data_coverage_pct": round(inventory.coverage * 100, 1),
    }
    return SalesInventoryHealth(
        score=score,
        status=health_status,
        as_of=as_of,
        score_breakdown=score_breakdown,
        metrics=metrics,
        priority_issues=alerts,
    )

