from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data
from backend.tools.inventory_tools import (
    InventoryStatus,
    ProductStock,
    ReorderSimulation,
    StockRisk,
    assess_inventory,
    simulate_reorder,
)

logger = logging.getLogger(__name__)


def _money(amount: Decimal) -> float:
    return float(round(amount, 2))


def _breakdown(items: list[str]) -> str:
    return " | ".join(items)


def _cover(product: ProductStock) -> str:
    return "no recent demand" if product.days_of_cover is None else f"{product.days_of_cover:.1f} days"


def _stock_line(product: ProductStock) -> str:
    return (
        f"{product.product_id}: {product.avg_daily_units_sold:.1f} units/day sold, "
        f"{product.current_stock} in stock, {_cover(product)} of cover ({product.risk.value})"
    )


def _confidence(status: InventoryStatus) -> float:
    return round(0.6 + 0.35 * status.coverage, 2)


def _question_intent(question: str | None) -> str:
    if not question:
        return "overview"
    text = question.lower()
    if any(
        term in text for term in ("what if", "what-if", "scenario", "increase by", "increase ", "如果", "假设", "增加")
    ) and ("%" in text or "％" in text):
        return "what_if"
    if any(term in text for term in ("valuation", "stock value", "inventory value", "fifo", "估值", "库存价值")):
        return "inventory_valuation"
    if any(term in text for term in ("supplier", "lead time", "replenishment time", "供应商", "交期")):
        return "supplier_lead_times"
    if any(term in text for term in ("unfulfilled", "lost sale", "lost revenue", "stockout", "未满足", "损失", "断货")):
        return "stockout_impact"
    if any(term in text for term in ("purchase order", "reorder", "place new", "order quantity", "采购", "补货", "下单")):
        return "reorder_recommendation"
    if any(
        term in text
        for term in ("top 10", "top ten", "best-selling", "top-selling", "enough inventory", "前十", "畅销", "库存够")
    ):
        return "top_seller_cover"
    return "stock_risk"


def _requested_product_id(question: str | None) -> str | None:
    if not question:
        return None
    match = re.search(r"\bPRD\s*0*(\d+)\b", question, re.IGNORECASE)
    if match:
        return f"PRD{int(match.group(1)):03d}"
    if "product a" in question.lower():
        return "PRD001"
    return None


def _demand_uplift_pct(question: str | None) -> float:
    if not question:
        return 0.0
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*[%％]", question)
    return float(match.group(1)) if match else 0.0


def _requested_order_qty(question: str | None) -> int | None:
    if not question:
        return None
    match = re.search(r"\b(?:order|purchase|buy)\s+(\d+)\s*(?:units?)?", question, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _describe(
    status: InventoryStatus,
    window_days: int,
    intent: str,
    focus: ProductStock | None,
    simulation: ReorderSimulation | None,
) -> str:
    if intent == "inventory_valuation":
        return f"Total FIFO warehouse inventory value is SGD {status.total_stock_value:,.2f} as of {status.as_of.isoformat()}."
    if intent == "supplier_lead_times":
        suppliers = status.longest_lead_time_suppliers(3)
        if not suppliers:
            return "Supplier lead-time data is unavailable."
        return f"{suppliers[0][0]} has the longest recorded replenishment lead time at {suppliers[0][1]} days."
    if intent == "top_seller_cover":
        top_sellers = status.top_sellers(10)
        at_risk = [product for product in top_sellers if product.risk is not StockRisk.OK]
        return (
            f"{len(at_risk)} of the {len(top_sellers)} best-selling products do not have enough stock "
            "to cover their supplier lead time."
        )
    if intent == "reorder_recommendation":
        if focus is None or focus.risk is StockRisk.OK:
            return "No purchase order is currently recommended because stock covers supplier lead times."
        if focus.order_qty_is_provisional:
            return (
                f"{focus.product} ({focus.product_id}) has an existing delivery expected on "
                f"{focus.next_expected_receipt_date.isoformat()}, but its incoming quantity is unknown. "
                f"The additional order estimate of {focus.suggested_order_qty} units is provisional and "
                "must not become a purchase order until the inbound quantity is verified."
            )
        return (
            f"A draft purchase order of {focus.suggested_order_qty} units is recommended for "
            f"{focus.product} ({focus.product_id}); human approval is required."
        )
    if intent == "what_if" and simulation is not None and focus is not None:
        cover = (
            "unknown"
            if simulation.days_of_cover_after_receipt is None
            else f"{simulation.days_of_cover_after_receipt:.1f} days"
        )
        return (
            f"Under a {simulation.demand_uplift_pct:.1f}% demand change, ordering {simulation.order_qty} units of "
            f"{focus.product_id} would provide about {cover} of cover after receipt."
        )

    if focus is None:
        return f"Current stock covers supplier lead times for all {len(status.products)} tracked products."

    if focus.risk is StockRisk.OK:
        return (
            f"{focus.product} ({focus.product_id}) has {focus.current_stock} units in stock and about "
            f"{focus.days_of_cover:.1f} days of cover, which covers its {focus.lead_time_days}-day supplier lead time."
        )

    if focus.risk is StockRisk.OUT_OF_STOCK:
        text = f"{focus.product} ({focus.product_id}) is out of stock (0 units; reorder level {focus.reorder_level})."
        if focus.recent_unfulfilled_units:
            text += f" {focus.recent_unfulfilled_units} units of demand went unfulfilled in the last {window_days} days"
            if focus.recent_lost_revenue is not None:
                text += f" (about SGD {focus.recent_lost_revenue:,.2f} in lost sales)"
            text += "."
        if focus.next_expected_receipt_date is not None:
            text += f" The next delivery is expected on {focus.next_expected_receipt_date.isoformat()}."
        others = len(status.out_of_stock) - 1 + len(status.at_risk)
    else:
        text = (
            f"{focus.product} ({focus.product_id}) has about {focus.days_of_cover:.1f} days of stock "
            f"against a {focus.lead_time_days}-day supplier lead time."
        )
        others = len(status.at_risk) - 1

    if others > 0:
        text += f" {others} other {'product' if others == 1 else 'products'} may run out before replenishment arrives."
    if intent == "stock_risk" and status.at_or_below_reorder:
        text += (
            f" {len(status.at_or_below_reorder)} products are at or below their static reorder level; "
            "the risk classification separately checks whether stock can cover supplier lead time."
        )
    return text


def _focus_evidence(focus: ProductStock, as_of: date, period: str) -> list[Evidence]:
    evidence = [
        Evidence(metric="product_id", value=focus.product_id),
        Evidence(metric="product", value=focus.product),
        Evidence(metric="stock_risk", value=focus.risk.value),
        Evidence(metric="current_stock", value=focus.current_stock, unit="units", source="inventory.csv"),
        Evidence(metric="reorder_level", value=focus.reorder_level, unit="units", source="inventory.csv"),
        Evidence(metric="lead_time_days", value=focus.lead_time_days, unit="days", source="inventory.csv"),
        Evidence(metric="supplier", value=focus.supplier),
        Evidence(
            metric="avg_daily_demand_units",
            value=round(focus.avg_daily_demand, 2),
            unit="units/day",
            period=period,
            source="inventory_history.csv",
        ),
    ]
    if focus.days_of_cover is not None:
        evidence.append(Evidence(metric="days_of_cover", value=round(focus.days_of_cover, 1)))
    projected_stockout = focus.projected_stockout_date(as_of)
    if projected_stockout is not None:
        evidence.append(Evidence(metric="projected_stockout_date", value=projected_stockout.isoformat()))
    evidence.append(
        Evidence(
            metric="recent_unfulfilled_demand_units",
            value=focus.recent_unfulfilled_units,
            unit="units",
            period=period,
            source="inventory_history.csv",
        )
    )
    if focus.first_recent_unfulfilled_date is not None:
        evidence.append(
            Evidence(metric="first_recent_unfulfilled_date", value=focus.first_recent_unfulfilled_date.isoformat())
        )
    if focus.recent_lost_revenue is not None:
        evidence.append(Evidence(metric="recent_lost_revenue_sgd", value=_money(focus.recent_lost_revenue)))
    if focus.next_expected_receipt_date is not None:
        evidence.append(
            Evidence(metric="next_expected_receipt_date", value=focus.next_expected_receipt_date.isoformat())
        )
        if focus.incoming_qty is None:
            evidence.append(Evidence(metric="incoming_qty_status", value="unknown"))
    if focus.incoming_qty is not None:
        evidence.append(Evidence(metric="incoming_qty", value=focus.incoming_qty, unit="units"))
    projected = focus.projected_lost_revenue(as_of)
    if focus.risk is StockRisk.OUT_OF_STOCK and projected is not None:
        evidence.append(Evidence(metric="projected_lost_revenue_sgd_until_restock", value=_money(projected)))
    evidence.append(Evidence(metric="suggested_order_qty", value=focus.suggested_order_qty, unit="units"))
    evidence.append(Evidence(metric="suggested_order_qty_is_provisional", value=focus.order_qty_is_provisional))
    return evidence


def _evidence(
    status: InventoryStatus,
    intent: str,
    focus: ProductStock | None,
    simulation: ReorderSimulation | None,
) -> list[Evidence]:
    period = f"{status.recent_start.isoformat()}/{status.as_of.isoformat()}"
    evidence = [
        Evidence(metric="analysis_intent", value=intent),
        Evidence(metric="as_of_date", value=status.as_of.isoformat(), source="inventory.csv"),
        Evidence(metric="recent_period", value=period, source="inventory_history.csv"),
    ]
    if intent in {"overview", "stock_risk", "stockout_impact", "reorder_recommendation"}:
        evidence += [
            Evidence(metric="out_of_stock_product_count", value=len(status.out_of_stock), unit="products"),
            Evidence(metric="at_risk_product_count", value=len(status.at_risk), unit="products"),
            Evidence(
                metric="at_or_below_reorder_product_count",
                value=len(status.at_or_below_reorder),
                unit="products",
            ),
            Evidence(
                metric="at_or_below_reorder_products",
                value=[product.product_id for product in status.at_or_below_reorder],
                source="inventory.csv",
            ),
            Evidence(
                metric="stock_risk_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "current_stock": product.current_stock,
                        "reorder_level": product.reorder_level,
                        "at_or_below_reorder_level": product.at_or_below_reorder_level,
                        "avg_daily_demand": round(product.avg_daily_demand, 2),
                        "days_of_cover": (
                            None if product.days_of_cover is None else round(product.days_of_cover, 1)
                        ),
                        "lead_time_days": product.lead_time_days,
                        "risk": product.risk.value,
                        "projected_stockout_date": (
                            None
                            if product.projected_stockout_date(status.as_of) is None
                            else product.projected_stockout_date(status.as_of).isoformat()
                        ),
                    }
                    for product in status.products
                ],
                period=status.as_of.isoformat(),
                source="inventory.csv + inventory_history.csv",
            ),
        ]
    if status.out_of_stock and intent in {"overview", "stock_risk", "stockout_impact", "reorder_recommendation"}:
        evidence.append(
            Evidence(metric="out_of_stock_products", value=", ".join(p.product_id for p in status.out_of_stock))
        )
    if status.at_risk and intent in {"overview", "stock_risk", "reorder_recommendation"}:
        evidence += [
            Evidence(metric="at_risk_products", value=", ".join(p.product_id for p in status.at_risk)),
            Evidence(
                metric="at_risk_stock_units",
                value=_breakdown([f"{p.product_id}: {p.current_stock}" for p in status.at_risk]),
                unit="units",
            ),
        ]
    if status.reorder_candidates and intent in {"overview", "reorder_recommendation"}:
        evidence += [
            Evidence(metric="reorder_candidate_count", value=len(status.reorder_candidates), unit="products"),
            Evidence(
                metric="provisional_reorder_candidate_count",
                value=len(status.provisional_reorder_candidates),
                unit="products",
            ),
            Evidence(metric="total_suggested_order_units", value=status.total_suggested_order_units, unit="units"),
            Evidence(
                metric="reorder_recommendation_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "supplier_id": product.supplier_id,
                        "supplier": product.supplier,
                        "current_stock": product.current_stock,
                        "suggested_order_qty": product.suggested_order_qty,
                        "risk": product.risk.value,
                        "next_expected_receipt_date": (
                            None
                            if product.next_expected_receipt_date is None
                            else product.next_expected_receipt_date.isoformat()
                        ),
                        "incoming_qty": product.incoming_qty,
                        "suggested_order_qty_is_provisional": product.order_qty_is_provisional,
                        "recent_lost_revenue_sgd": (
                            None
                            if product.recent_lost_revenue is None
                            else _money(product.recent_lost_revenue)
                        ),
                    }
                    for product in status.reorder_candidates
                ],
                period=status.as_of.isoformat(),
                source="inventory.csv + inventory_history.csv + products.csv",
            ),
        ]
    if intent in {"overview", "inventory_valuation"}:
        evidence += [
            Evidence(
                metric="total_stock_value_sgd",
                value=_money(status.total_stock_value),
                unit="SGD",
                period=status.as_of.isoformat(),
                source="inventory.csv",
            )
        ]

    top_sellers = status.top_sellers(10)
    if top_sellers and intent in {"overview", "top_seller_cover"}:
        evidence += [
            Evidence(
                metric="top_sellers_stock_cover",
                value=_breakdown([_stock_line(product) for product in top_sellers]),
                period=period,
                source="inventory.csv + inventory_history.csv",
            ),
            Evidence(
                metric="top_sellers_at_risk_count",
                value=sum(1 for product in top_sellers if product.risk is not StockRisk.OK),
                unit="products",
            ),
            Evidence(
                metric="top_seller_stock_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "avg_daily_units_sold": round(product.avg_daily_units_sold, 2),
                        "current_stock": product.current_stock,
                        "days_of_cover": (
                            None if product.days_of_cover is None else round(product.days_of_cover, 1)
                        ),
                        "lead_time_days": product.lead_time_days,
                        "risk": product.risk.value,
                    }
                    for product in top_sellers
                ],
                period=period,
                source="inventory.csv + inventory_history.csv",
            ),
        ]
    if intent in {"overview", "inventory_valuation"}:
        evidence += [
            Evidence(
                metric="highest_stock_value_products",
                value=_breakdown(
                    [
                        f"{p.product_id} {p.product}: SGD {p.stock_value:,.2f}, {_cover(p)} of cover"
                        for p in status.highest_stock_value(3)
                    ]
                ),
                unit="SGD",
                source="inventory.csv",
            ),
            Evidence(
                metric="inventory_value_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "stock_value_sgd": _money(product.stock_value),
                        "current_stock": product.current_stock,
                        "avg_daily_units_sold": round(product.avg_daily_units_sold, 2),
                        "days_of_cover": (
                            None if product.days_of_cover is None else round(product.days_of_cover, 1)
                        ),
                    }
                    for product in status.highest_stock_value(len(status.products))
                ],
                period=status.as_of.isoformat(),
                source="inventory.csv + inventory_history.csv",
            ),
        ]
    if intent in {"overview", "supplier_lead_times"}:
        evidence += [
            Evidence(
                metric="longest_lead_time_suppliers",
                value=_breakdown(
                    [f"{supplier}: {days} days" for supplier, days in status.longest_lead_time_suppliers(3)]
                ),
                unit="days",
                source="inventory.csv",
            ),
            Evidence(
                metric="supplier_lead_time_details",
                value=[
                    {"supplier": supplier, "lead_time_days": days}
                    for supplier, days in status.longest_lead_time_suppliers(len(status.products))
                ],
                source="inventory.csv",
            ),
        ]

    if focus is not None and intent in {
        "overview",
        "stock_risk",
        "stockout_impact",
        "reorder_recommendation",
        "what_if",
    }:
        evidence += _focus_evidence(focus, status.as_of, period)
    if simulation is not None:
        evidence += [
            Evidence(metric="simulation_order_qty", value=simulation.order_qty, unit="units"),
            Evidence(metric="simulation_demand_uplift_pct", value=simulation.demand_uplift_pct, unit="percent"),
            Evidence(
                metric="simulation_effective_daily_demand",
                value=round(simulation.effective_daily_demand, 2),
                unit="units/day",
            ),
            Evidence(
                metric="simulation_stock_on_arrival",
                value=round(simulation.stock_on_arrival, 2),
                unit="units",
            ),
            Evidence(
                metric="simulation_expected_lost_units_before_receipt",
                value=round(simulation.expected_lost_units_before_receipt, 2),
                unit="units",
            ),
        ]
        if simulation.days_of_cover_after_receipt is not None:
            evidence.append(
                Evidence(
                    metric="simulation_days_of_cover_after_receipt",
                    value=round(simulation.days_of_cover_after_receipt, 1),
                    unit="days",
                )
            )
        if simulation.expected_lost_revenue_before_receipt is not None:
            evidence.append(
                Evidence(
                    metric="simulation_expected_lost_revenue_before_receipt_sgd",
                    value=_money(simulation.expected_lost_revenue_before_receipt),
                    unit="SGD",
                )
            )
    return evidence


def _recommended_actions(
    status: InventoryStatus,
    intent: str,
    focus: ProductStock | None,
    simulation: ReorderSimulation | None,
) -> list[RecommendedAction]:
    if focus is None:
        return [
            RecommendedAction(
                type="monitor_stock_levels",
                risk_level=RiskLevel.GREEN,
                reason="Current stock covers supplier lead times for all tracked products.",
            )
        ]
    if focus.risk is StockRisk.OK:
        return [
            RecommendedAction(
                type="monitor_stock_levels",
                risk_level=RiskLevel.GREEN,
                reason=(
                    f"{focus.product_id} has enough stock to cover its current supplier lead time; "
                    "no purchase order is proposed."
                ),
                parameters={"product_id": focus.product_id},
            )
        ]
    if intent in {"inventory_valuation", "supplier_lead_times", "top_seller_cover"}:
        return [
            RecommendedAction(
                type="review_inventory_analysis",
                risk_level=RiskLevel.GREEN,
                reason=f"The requested {intent.replace('_', ' ')} analysis is ready for review.",
                parameters={"analysis_intent": intent},
            )
        ]

    simulation = simulation or simulate_reorder(focus, status.as_of)
    if focus.order_qty_is_provisional:
        return [
            RecommendedAction(
                type="verify_inbound_quantity",
                risk_level=RiskLevel.AMBER,
                reason=(
                    f"{focus.product_id} has an expected receipt but no inbound quantity. "
                    "Creating another purchase order before verification could duplicate replenishment."
                ),
                parameters={
                    "product_id": focus.product_id,
                    "supplier_id": focus.supplier_id,
                    "existing_receipt_date": focus.next_expected_receipt_date.isoformat(),
                    "provisional_additional_order_qty": simulation.order_qty,
                },
                expected_impact={
                    "decision_blocked_until": "incoming_quantity_verified",
                    "demand_uplift_pct": simulation.demand_uplift_pct,
                },
            )
        ]

    parameters: dict[str, object] = {
        "product_id": focus.product_id,
        "supplier_id": focus.supplier_id,
        "supplier": focus.supplier,
        "quantity": simulation.order_qty,
        "proposed_order_earliest_arrival": (
            status.as_of + timedelta(days=focus.lead_time_days)
        ).isoformat(),
    }
    if focus.next_expected_receipt_date is not None:
        parameters["existing_receipt_date"] = focus.next_expected_receipt_date.isoformat()
    expected_impact: dict[str, object] = {
        "days_of_cover_after_receipt": (
            None
            if simulation.days_of_cover_after_receipt is None
            else round(simulation.days_of_cover_after_receipt, 1)
        ),
        "demand_uplift_pct": simulation.demand_uplift_pct,
    }
    if focus.projected_lost_revenue(status.as_of) is not None:
        expected_impact["revenue_at_risk_until_restock_sgd"] = _money(
            focus.projected_lost_revenue(status.as_of) or Decimal(0)
        )
    return [
        RecommendedAction(
            type="prepare_purchase_order",
            risk_level=RiskLevel.AMBER,
            reason=(
                f"{focus.product_id} is {focus.risk.value.replace('_', ' ')} and current stock does not cover "
                "supplier lead time; this creates a draft only and requires human approval."
            ),
            parameters=parameters,
            expected_impact=expected_impact,
        )
    ]


def inventory_bee(
    question: str | None = None,
    as_of: date | None = None,
    window_days: int = 7,
    data_dir: Path | None = None,
) -> AgentResponse:
    as_of = as_of or demo_data.as_of_date()
    data_dir = data_dir or demo_data.DATA_DIR
    intent = _question_intent(question)
    try:
        status = assess_inventory(data_dir, as_of, window_days)
    except (FileNotFoundError, duckdb.Error):
        logger.warning("Inventory Bee could not read inventory data from %s", data_dir, exc_info=True)
        return AgentResponse(
            agent="inventory",
            status=AgentStatus.FAILED,
            summary="Inventory data is unavailable, so stock risk could not be assessed.",
            confidence=0.0,
        )

    requested_product_id = _requested_product_id(question)
    focus = status.by_product_id(requested_product_id) if requested_product_id else status.focus
    if requested_product_id and focus is None:
        return AgentResponse(
            agent="inventory",
            status=AgentStatus.PARTIAL,
            summary=f"No inventory record was found for {requested_product_id}.",
            evidence=[
                Evidence(metric="requested_product_id", value=requested_product_id),
                Evidence(metric="as_of_date", value=status.as_of.isoformat(), source="inventory.csv"),
            ],
            confidence=_confidence(status),
        )
    simulation = None
    if focus is not None and intent in {"reorder_recommendation", "what_if"}:
        try:
            simulation = simulate_reorder(
                focus,
                status.as_of,
                order_qty=_requested_order_qty(question),
                demand_uplift_pct=_demand_uplift_pct(question),
            )
        except ValueError:
            logger.warning("Inventory Bee ignored invalid what-if parameters in question %r", question)

    return AgentResponse(
        agent="inventory",
        status=AgentStatus.SUCCESS if status.coverage > 0 else AgentStatus.PARTIAL,
        summary=_describe(status, window_days, intent, focus, simulation),
        evidence=_evidence(status, intent, focus, simulation),
        confidence=_confidence(status),
        recommended_actions=_recommended_actions(status, intent, focus, simulation),
    )
