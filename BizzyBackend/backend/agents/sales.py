from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.tools import demo_data
from backend.tools.sales_tools import SalesSummary, summarise_sales

logger = logging.getLogger(__name__)


def _money(amount: Decimal) -> float:
    return float(round(amount, 2))


def _breakdown(items: list[str]) -> str:
    return " | ".join(items)


def _confidence(summary: SalesSummary) -> float:
    return round(0.6 + 0.35 * summary.coverage, 2)


def _question_intent(question: str | None) -> str:
    if not question:
        return "overview"
    text = question.lower()
    if any(term in text for term in ("gross margin", "margin", "profitability", "毛利", "利润率")):
        return "category_margin"
    if any(term in text for term in ("channel", "web", "retail", "b2b", "marketplace", "渠道")):
        return "channel_performance"
    if any(
        term in text
        for term in ("top 5", "top five", "top-selling", "best-selling", "top selling", "前五", "畅销")
    ):
        return "top_products"
    if any(term in text for term in ("sales velocity", "low sales", "slow-moving", "slow moving", "销售速度", "滞销")):
        return "product_velocity"
    if any(
        term in text
        for term in (
            "why",
            "drop",
            "decline",
            "fell",
            "fall",
            "lost",
            "shortage",
            "stockout",
            "为什么",
            "下降",
            "下跌",
            "减少",
            "损失",
            "缺货",
        )
    ):
        return "decline_analysis"
    return "revenue_summary"


def _describe(summary: SalesSummary, window_days: int, intent: str) -> str:
    if intent == "channel_performance":
        channels = sorted(summary.channels, key=lambda channel: (-channel.recent_revenue, channel.channel))
        if not channels:
            return "No channel sales were recorded in the requested reporting period."
        top = channels[0]
        return (
            f"{top.channel} generated the most revenue in {summary.recent.label}: "
            f"SGD {top.recent_revenue:,.2f}."
        )
    if intent == "top_products":
        products = summary.top_products(5)
        if not products:
            return "No revenue-generating products were found in the requested reporting period."
        return (
            f"The top revenue-generating product was {products[0].product} ({products[0].product_id}) "
            f"at SGD {products[0].recent_revenue:,.2f}; {len(products)} products are included in the ranking."
        )
    if intent == "category_margin":
        categories = [category for category in summary.categories if category.margin_pct is not None]
        if not categories:
            return "Category margin cannot be calculated because product-category or cost data is unavailable."
        best = max(categories, key=lambda category: (category.margin_pct or 0.0, category.category))
        return (
            f"Overall gross margin was {summary.recent_gross_margin_pct:.2f}%. "
            f"{best.category} had the highest category margin at {best.margin_pct:.2f}%."
        )
    if intent == "product_velocity":
        products = sorted(summary.products, key=lambda product: (product.recent_units, product.product_id))
        if not products:
            return "No product sales velocity data was available for the requested reporting period."
        slowest = products[0]
        return (
            f"{slowest.product} ({slowest.product_id}) had the lowest recent sales velocity "
            f"at {slowest.recent_units} units over {window_days} days."
        )

    pct = summary.revenue_change_pct
    baseline = f"SGD {summary.baseline_revenue:,.2f}"
    recent = f"SGD {summary.recent_revenue:,.2f}"
    if pct is None:
        return f"No sales were recorded in the baseline window {summary.baseline.label}; the change cannot be calculated."
    if pct == 0:
        return f"Revenue was flat versus the previous {window_days} days ({recent})."

    direction = "fell" if pct < 0 else "rose"
    text = f"Revenue {direction} {abs(pct):.1f}% versus the previous {window_days} days (from {baseline} to {recent})."
    top = summary.top_decliner
    if intent in {"overview", "decline_analysis"} and pct < 0 and top is not None:
        text += f" {top.product} ({top.product_id}) accounts for {summary.share_of_decline_pct(top):.1f}% of the decline"
        if top.recent_units == 0 and top.last_sale_date is not None:
            text += f" and has had no sales since {top.last_sale_date.isoformat()}"
        text += (
            f". The product-level decomposition attributes SGD {summary.volume_effect:,.2f} "
            f"to volume and SGD {summary.price_mix_effect:,.2f} to price/mix"
        )
        text += "."
    return text


def _evidence(summary: SalesSummary, intent: str) -> list[Evidence]:
    evidence = [
        Evidence(metric="analysis_intent", value=intent),
        Evidence(metric="baseline_period", value=summary.baseline.label, source="sales.csv"),
        Evidence(metric="recent_period", value=summary.recent.label, source="sales.csv"),
    ]
    if intent in {"overview", "revenue_summary", "decline_analysis"}:
        evidence += [
            Evidence(
                metric="baseline_revenue_sgd",
                value=_money(summary.baseline_revenue),
                unit="SGD",
                period=summary.baseline.label,
                source="sales.csv",
            ),
            Evidence(
                metric="recent_revenue_sgd",
                value=_money(summary.recent_revenue),
                unit="SGD",
                period=summary.recent.label,
                source="sales.csv",
            ),
            Evidence(
                metric="revenue_change_sgd",
                value=_money(summary.revenue_change),
                unit="SGD",
                period=f"{summary.baseline.label} vs {summary.recent.label}",
                source="sales.csv",
            ),
            Evidence(metric="baseline_units", value=summary.baseline_units, unit="units", period=summary.baseline.label),
            Evidence(metric="recent_units", value=summary.recent_units, unit="units", period=summary.recent.label),
        ]
        if summary.revenue_change_pct is not None:
            evidence.append(Evidence(metric="revenue_change_pct", value=summary.revenue_change_pct, unit="percent"))

    channels = sorted(summary.channels, key=lambda channel: (-channel.recent_revenue, channel.channel))
    if channels and intent in {"overview", "channel_performance"}:
        evidence += [
            Evidence(metric="top_channel", value=channels[0].channel, period=summary.recent.label),
            Evidence(
                metric="top_channel_recent_revenue_sgd",
                value=_money(channels[0].recent_revenue),
                unit="SGD",
                period=summary.recent.label,
            ),
            Evidence(
                metric="recent_revenue_by_channel_sgd",
                value=_breakdown([f"{channel.channel}: {channel.recent_revenue:,.2f}" for channel in channels]),
                unit="SGD",
                period=summary.recent.label,
                source="sales.csv",
            ),
            Evidence(
                metric="channel_performance_details",
                value=[
                    {
                        "channel": channel.channel,
                        "baseline_revenue_sgd": _money(channel.baseline_revenue),
                        "recent_revenue_sgd": _money(channel.recent_revenue),
                        "revenue_change_sgd": _money(channel.recent_revenue - channel.baseline_revenue),
                    }
                    for channel in channels
                ],
                period=f"{summary.baseline.label} vs {summary.recent.label}",
                source="sales.csv",
            ),
        ]

    top_products = summary.top_products(5)
    baseline_top_products = summary.baseline_top_products(5)
    if (top_products or baseline_top_products) and intent in {"overview", "top_products"}:
        evidence += [
            Evidence(
                metric="top_products_recent_revenue_sgd",
                value=_breakdown(
                    [f"{product.product_id} {product.product}: {product.recent_revenue:,.2f}" for product in top_products]
                ),
                unit="SGD",
                period=summary.recent.label,
                source="sales.csv",
            ),
            Evidence(
                metric="top_product_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "recent_revenue_sgd": _money(product.recent_revenue),
                        "recent_units": product.recent_units,
                    }
                    for product in top_products
                ],
                period=summary.recent.label,
                source="sales.csv",
            ),
            Evidence(
                metric="baseline_top_product_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "baseline_revenue_sgd": _money(product.baseline_revenue),
                        "baseline_units": product.baseline_units,
                    }
                    for product in baseline_top_products
                ],
                period=summary.baseline.label,
                source="sales.csv",
            ),
        ]

    categories = sorted(
        (category for category in summary.categories if category.margin_pct is not None),
        key=lambda category: (-(category.margin_pct or 0.0), category.category),
    )
    if intent in {"overview", "category_margin"}:
        if summary.recent_gross_margin_pct is not None:
            evidence.append(
                Evidence(
                    metric="recent_gross_margin_pct",
                    value=summary.recent_gross_margin_pct,
                    unit="percent",
                    period=summary.recent.label,
                )
            )
    if categories and intent in {"overview", "category_margin"}:
        evidence += [
            Evidence(
                metric="recent_gross_margin_pct_by_category",
                value=_breakdown([f"{category.category}: {category.margin_pct:.2f}%" for category in categories]),
                unit="percent",
                period=summary.recent.label,
                source="sales.csv + products.csv",
            ),
            Evidence(
                metric="category_margin_details",
                value=[
                    {
                        "category": category.category,
                        "revenue_sgd": _money(category.revenue),
                        "cogs_sgd": _money(category.cogs),
                        "gross_margin_pct": category.margin_pct,
                    }
                    for category in categories
                ],
                period=summary.recent.label,
                source="sales.csv + products.csv",
            ),
        ]

    if intent == "product_velocity":
        products = sorted(summary.products, key=lambda product: (product.recent_units, product.product_id))
        window_days = (summary.recent.end - summary.recent.start).days + 1
        evidence += [
            Evidence(
                metric="recent_units_by_product",
                value=_breakdown(
                    [f"{product.product_id} {product.product}: {product.recent_units}" for product in products]
                ),
                unit="units",
                period=summary.recent.label,
                source="sales.csv",
            ),
            Evidence(
                metric="product_velocity_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "recent_units": product.recent_units,
                        "avg_daily_units": round(product.recent_units / window_days, 2),
                        "recent_revenue_sgd": _money(product.recent_revenue),
                    }
                    for product in products
                ],
                period=summary.recent.label,
                source="sales.csv",
            ),
        ]

    if intent in {"overview", "revenue_summary", "decline_analysis"}:
        evidence.append(
            Evidence(
                metric="product_performance_details",
                value=[
                    {
                        "product_id": product.product_id,
                        "product": product.product,
                        "baseline_revenue_sgd": _money(product.baseline_revenue),
                        "recent_revenue_sgd": _money(product.recent_revenue),
                        "revenue_change_sgd": _money(product.revenue_change),
                        "baseline_units": product.baseline_units,
                        "recent_units": product.recent_units,
                    }
                    for product in sorted(summary.products, key=lambda item: item.product_id)
                ],
                period=f"{summary.baseline.label} vs {summary.recent.label}",
                source="sales.csv",
            )
        )

    top = summary.top_decliner
    if top is not None and intent in {"overview", "decline_analysis"}:
        evidence += [
            Evidence(metric="focus_product_id", value=top.product_id),
            Evidence(metric="focus_product", value=top.product),
            Evidence(
                metric="focus_product_revenue_change_sgd",
                value=_money(top.revenue_change),
                unit="SGD",
                period=f"{summary.baseline.label} vs {summary.recent.label}",
            ),
            Evidence(
                metric="focus_product_share_of_decline_pct",
                value=summary.share_of_decline_pct(top),
                unit="percent",
            ),
            Evidence(metric="volume_effect_sgd", value=_money(summary.volume_effect), unit="SGD"),
            Evidence(metric="price_mix_effect_sgd", value=_money(summary.price_mix_effect), unit="SGD"),
        ]
        if top.last_sale_date is not None:
            evidence.append(Evidence(metric="focus_product_last_sale_date", value=top.last_sale_date.isoformat()))

    if summary.stopped_selling and intent in {"overview", "decline_analysis"}:
        evidence.append(
            Evidence(
                metric="products_with_no_recent_sales",
                value=", ".join(product.product_id for product in summary.stopped_selling),
            )
        )
    return evidence


def _recommended_actions(summary: SalesSummary, intent: str) -> list[RecommendedAction]:
    if intent not in {"overview", "decline_analysis", "revenue_summary"}:
        return [
            RecommendedAction(
                type="review_sales_analysis",
                risk_level=RiskLevel.GREEN,
                reason=f"The requested {intent.replace('_', ' ')} analysis is ready for review.",
                parameters={"analysis_intent": intent},
            )
        ]
    top = summary.top_decliner
    if summary.revenue_change >= 0 or top is None:
        return [
            RecommendedAction(
                type="monitor_sales_trend",
                risk_level=RiskLevel.GREEN,
                reason="No negative revenue movement requiring intervention was detected.",
            )
        ]
    if top.recent_units == 0:
        return [
            RecommendedAction(
                type="investigate_stock_availability",
                risk_level=RiskLevel.GREEN,
                reason=f"{top.product_id} stopped selling and drove the largest revenue decline.",
                parameters={"product_id": top.product_id},
                expected_impact={"revenue_gap_sgd": abs(_money(top.revenue_change))},
            )
        ]
    return [
        RecommendedAction(
            type="review_product_performance",
            risk_level=RiskLevel.GREEN,
            reason=f"{top.product_id} drove the largest revenue decline.",
            parameters={"product_id": top.product_id, "analysis_intent": intent},
        )
    ]


def sales_bee(
    question: str | None = None,
    as_of: date | None = None,
    window_days: int = 7,
    data_dir: Path | None = None,
) -> AgentResponse:
    as_of = as_of or demo_data.as_of_date()
    data_dir = data_dir or demo_data.DATA_DIR
    intent = _question_intent(question)
    try:
        summary = summarise_sales(data_dir, as_of, window_days)
    except (FileNotFoundError, duckdb.Error):
        logger.warning("Sales Bee could not read sales data from %s", data_dir, exc_info=True)
        return AgentResponse(
            agent="sales",
            status=AgentStatus.FAILED,
            summary="Sales data is unavailable, so revenue trends could not be calculated.",
            confidence=0.0,
        )

    return AgentResponse(
        agent="sales",
        status=AgentStatus.PARTIAL if summary.revenue_change_pct is None else AgentStatus.SUCCESS,
        summary=_describe(summary, window_days, intent),
        evidence=_evidence(summary, intent),
        confidence=_confidence(summary),
        recommended_actions=_recommended_actions(summary, intent),
    )
