from __future__ import annotations

import math
from typing import Any

from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


def _evidence_map(result: AgentResponse) -> dict[str, object]:
    return {item.metric: item.value for item in result.evidence}


def _sales_inventory_link(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], float] | None:
    sales_evidence = _evidence_map(sales)
    inventory_evidence = _evidence_map(inventory)
    sales_product = sales_evidence.get("focus_product_id")
    inventory_product = inventory_evidence.get("product_id")
    if not sales_product or sales_product != inventory_product:
        return None

    decline = sales_evidence.get("focus_product_revenue_change_sgd")
    lost_revenue = inventory_evidence.get("recent_lost_revenue_sgd")
    if not isinstance(decline, (int, float)) or not isinstance(lost_revenue, (int, float)):
        return None

    decline_amount = abs(float(decline))
    explained_pct = 0.0 if not decline_amount else round(float(lost_revenue) / decline_amount * 100, 2)
    same_period = sales_evidence.get("recent_period") == inventory_evidence.get("recent_period")
    last_sale = sales_evidence.get("focus_product_last_sale_date")
    first_unfulfilled = inventory_evidence.get("first_recent_unfulfilled_date")
    timeline_aligned = bool(last_sale and first_unfulfilled and str(first_unfulfilled) > str(last_sale))
    amount_aligned = abs(float(lost_revenue) - decline_amount) <= 0.01

    relationship = "strongly_supported" if same_period and timeline_aligned and amount_aligned else "supported"
    wording = "strongly supports" if relationship == "strongly_supported" else "supports"
    summary = (
        f"The combined evidence {wording} a stockout-related explanation for the sales decline. "
        f"{sales_product} contributed SGD {decline_amount:,.2f} of lost revenue while inventory records show "
        f"SGD {float(lost_revenue):,.2f} of unfulfilled demand in the same analysis"
        f"{' period' if same_period else ''} ({explained_pct:.1f}% of the product revenue gap). "
        "This is evidence-based correlation, not proof of causation."
    )
    evidence = [
        Evidence(metric="linked_product_id", value=sales_product),
        Evidence(metric="sales_decline_sgd", value=decline_amount, unit="SGD"),
        Evidence(metric="stockout_lost_revenue_sgd", value=float(lost_revenue), unit="SGD"),
        Evidence(metric="stockout_explained_decline_pct", value=explained_pct, unit="percent"),
        Evidence(metric="relationship_assessment", value=relationship),
        Evidence(metric="period_aligned", value=same_period),
        Evidence(metric="timeline_aligned", value=timeline_aligned),
        Evidence(metric="amount_aligned", value=amount_aligned),
    ]
    confidence = round(min(sales.confidence, inventory.confidence), 2)
    return summary, evidence, confidence


def _detail_rows(evidence: dict[str, object], metric: str) -> list[dict[str, Any]]:
    value = evidence.get(metric)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _top_seller_stock_risk(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    sales_evidence = _evidence_map(sales)
    current_rows = _detail_rows(sales_evidence, "top_product_details")
    baseline_rows = _detail_rows(sales_evidence, "baseline_top_product_details")
    candidates: dict[object, dict[str, Any]] = {}
    for row in current_rows:
        candidates[row.get("product_id")] = {**row, "current_top_seller": True}
    for row in baseline_rows:
        product_id = row.get("product_id")
        candidates[product_id] = {
            **candidates.get(product_id, {}),
            **row,
            "baseline_top_seller": True,
        }
    sales_rows = list(candidates.values())
    stock_rows = _detail_rows(_evidence_map(inventory), "top_seller_stock_details")
    if not stock_rows:
        stock_rows = _detail_rows(_evidence_map(inventory), "stock_risk_details")
    stock_by_product = {row.get("product_id"): row for row in stock_rows}
    linked = []
    for sale in sales_rows:
        stock = stock_by_product.get(sale.get("product_id"))
        if stock and stock.get("risk") != "ok":
            linked.append({**sale, **stock})
    if not linked:
        return None

    product_ids = [str(row["product_id"]) for row in linked]
    summary = (
        f"{len(linked)} of the {len(sales_rows)} current or baseline top revenue products are at stock risk: "
        f"{', '.join(product_ids)}. These products should be prioritised because shortages may interrupt "
        "revenue from current best sellers."
    )
    evidence = [Evidence(metric="top_sellers_at_stock_risk", value=linked)]
    action = RecommendedAction(
        type="prioritise_top_seller_replenishment",
        risk_level=RiskLevel.GREEN,
        reason="The products are both top revenue generators and unable to cover supplier lead time.",
        parameters={"product_ids": product_ids},
    )
    return summary, evidence, action


def _high_value_low_velocity(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    velocity_rows = _detail_rows(_evidence_map(sales), "product_velocity_details")
    value_rows = _detail_rows(_evidence_map(inventory), "inventory_value_details")
    if not velocity_rows or not value_rows:
        return None

    sample_size = min(len(velocity_rows), len(value_rows))
    cutoff = max(1, math.ceil(sample_size / 2))
    low_velocity_ids = {
        row.get("product_id")
        for row in sorted(velocity_rows, key=lambda row: (float(row.get("avg_daily_units", 0)), row.get("product_id")))[
            :cutoff
        ]
    }
    high_value_rows = sorted(
        value_rows,
        key=lambda row: (-float(row.get("stock_value_sgd", 0)), row.get("product_id")),
    )[:cutoff]
    velocity_by_product = {row.get("product_id"): row for row in velocity_rows}
    linked = [
        {**row, **velocity_by_product[row.get("product_id")]}
        for row in high_value_rows
        if row.get("product_id") in low_velocity_ids
    ][:5]
    if not linked:
        return None

    product_ids = [str(row["product_id"]) for row in linked]
    summary = (
        f"{', '.join(product_ids)} {'has' if len(product_ids) == 1 else 'have'} both relatively high inventory "
        "value and low recent sales velocity, indicating working-capital or slow-moving-stock risk."
    )
    evidence = [
        Evidence(
            metric="high_value_low_velocity_products",
            value=linked,
            source="sales.csv + inventory.csv + inventory_history.csv",
        )
    ]
    action = RecommendedAction(
        type="review_slow_moving_inventory",
        risk_level=RiskLevel.GREEN,
        reason="High-value inventory is moving slowly relative to the rest of the catalogue.",
        parameters={"product_ids": product_ids},
    )
    return summary, evidence, action


def _replenishment_support(
    sales: AgentResponse,
    inventory: AgentResponse,
) -> tuple[str, list[Evidence], RecommendedAction] | None:
    sales_rows = _detail_rows(_evidence_map(sales), "product_performance_details")
    reorder_rows = _detail_rows(_evidence_map(inventory), "reorder_recommendation_details")
    if not reorder_rows:
        return None

    sales_by_product = {row.get("product_id"): row for row in sales_rows}
    linked = [{**sales_by_product.get(row.get("product_id"), {}), **row} for row in reorder_rows]
    linked.sort(
        key=lambda row: (
            row.get("risk") != "out_of_stock",
            -float(row.get("recent_lost_revenue_sgd") or 0),
            -float(row.get("recent_revenue_sgd") or 0),
            row.get("product_id"),
        )
    )
    product_ids = [str(row["product_id"]) for row in linked]
    total_units = sum(int(row.get("suggested_order_qty") or 0) for row in linked)
    provisional_count = sum(bool(row.get("suggested_order_qty_is_provisional")) for row in linked)
    summary = (
        f"Yes. {len(linked)} products need replenishment to protect current sales activity, with "
        f"{total_units} suggested units in total. {product_ids[0]} is the first priority based on stock risk "
        f"and revenue impact. {provisional_count} recommendation(s) require inbound-quantity verification. "
        "Purchase orders must remain drafts until approved."
    )
    evidence = [
        Evidence(metric="replenishment_priorities", value=linked),
        Evidence(metric="replenishment_total_suggested_units", value=total_units, unit="units"),
        Evidence(metric="provisional_replenishment_count", value=provisional_count, unit="products"),
    ]
    action = RecommendedAction(
        type="review_purchase_order_bundle",
        risk_level=RiskLevel.AMBER,
        reason="The proposed quantities affect supplier commitments and require human approval.",
        parameters={
            "product_ids": product_ids,
            "total_suggested_units": total_units,
            "provisional_product_ids": [
                row["product_id"] for row in linked if row.get("suggested_order_qty_is_provisional")
            ],
        },
    )
    return summary, evidence, action


def _legacy_evidence_guidance(question: str, results: list[AgentResponse]) -> AgentResponse | None:
    """Support older metric-level evidence without changing modern cross-agent analysis."""
    legacy_metrics = {
        "latest_revenue", "current_stock", "reorder_level",
        "complaint_rate_pct", "unanswered_leads", "overdue_invoice_count",
        "overdue_amount_sgd", "revenue_change_pct",
    }
    modern_metrics = {
        "focus_product_id", "focus_product_revenue_change_sgd",
        "top_product_details", "baseline_top_product_details",
        "product_velocity_details", "product_performance_details",
        "reorder_recommendation_details", "inventory_value_details",
        "top_seller_stock_details", "stock_risk_details",
    }
    observed = {item.metric for result in results for item in result.evidence}
    # The full specialists also emit generic metrics such as current_stock.
    # Never let the older metric-based rules override their richer analysis.
    if observed & modern_metrics or not observed & legacy_metrics:
        return None

    usable = [result for result in results if result.status != AgentStatus.FAILED]
    if not usable:
        return AgentResponse(
            agent="advisor", status=AgentStatus.PARTIAL,
            summary="No usable specialist results were available.",
            evidence=[], confidence=0.0, recommended_actions=[],
        )

    # Conflicting measurements must not be silently collapsed into a dict.
    for result in usable:
        changes = [
            float(item.value) for item in result.evidence
            if result.agent == "sales" and item.metric == "revenue_change_pct"
            and isinstance(item.value, (int, float))
        ]
        if any(change < 0 for change in changes) and any(change > 0 for change in changes):
            return AgentResponse(
                agent="advisor", status=AgentStatus.PARTIAL,
                summary="Sales direction is conflicting; withhold recommendations pending verification.",
                evidence=[item for r in usable for item in r.evidence],
                confidence=min(r.confidence for r in usable),
                recommended_actions=[],
            )

    by_agent = {result.agent: _evidence_map(result) for result in usable}
    actions: list[RecommendedAction] = []
    findings: list[str] = []
    sales = by_agent.get("sales", {})
    inventory = by_agent.get("inventory", {})
    customer = by_agent.get("customer", {})
    finance = by_agent.get("finance", {})

    def add(action: str, agent: str, metric: str, reason: str) -> None:
        actions.append(RecommendedAction(
            type=f"{action}__{agent}.{metric}", risk_level=RiskLevel.GREEN,
            reason=reason,
        ))

    # Revenue alone does not establish a decline; recommend reviewing the
    # sales specialist's reported decline rather than asserting causation.
    sales_result = next((r for r in usable if r.agent == "sales"), None)
    if sales_result and (
        (isinstance(sales.get("revenue_change_pct"), (int, float))
         and sales["revenue_change_pct"] < 0)
        or ("declin" in sales_result.summary.lower() or "fell" in sales_result.summary.lower())
    ):
        metric = "revenue_change_pct" if "revenue_change_pct" in sales else "latest_revenue"
        if metric in sales:
            add("review_sales_decline", "sales", metric,
                "Review the reported decline against verified sales evidence.")
            findings.append("Sales reported a decline")

    stock = inventory.get("current_stock")
    reorder = inventory.get("reorder_level")
    if isinstance(stock, (int, float)) and isinstance(reorder, (int, float)) and stock < reorder:
        add("review_inventory_shortage", "inventory", "current_stock",
            "Stock is below the recorded reorder level.")
        findings.append("Inventory is below its reorder level")

    if isinstance(customer.get("complaint_rate_pct"), (int, float)) and customer["complaint_rate_pct"] > 0:
        add("review_customer_complaints", "customer", "complaint_rate_pct",
            "Review reported complaints before drawing conclusions.")
        findings.append("Customer complaints warrant review")
    if isinstance(customer.get("unanswered_leads"), (int, float)) and customer["unanswered_leads"] > 0:
        add("review_pending_enquiries", "customer", "unanswered_leads",
            "Review outstanding customer enquiries.")
        findings.append("Pending enquiries warrant review")

    if (
        isinstance(finance.get("overdue_amount_sgd"), (int, float))
        and finance["overdue_amount_sgd"] > 0
        and isinstance(finance.get("overdue_invoice_count"), (int, float))
        and finance["overdue_invoice_count"] > 0
    ):
        add("review_financial_exposure", "finance", "overdue_amount_sgd",
            "Overdue invoice count and amount both support a review.")
        findings.append("Overdue invoices warrant review")

    status = (AgentStatus.PARTIAL if any(r.status != AgentStatus.SUCCESS for r in results)
              else AgentStatus.SUCCESS)
    if not findings:
        summary = "No significant problems identified from the supplied evidence."
    else:
        summary = "; ".join(findings) + ". These findings may be related but the available evidence does not establish causation."
    return AgentResponse(
        agent="advisor", status=status, summary=summary,
        evidence=[item for r in usable for item in r.evidence],
        confidence=min(r.confidence for r in usable),
        recommended_actions=actions,
    )


def advisor_bee(question: str, specialist_results: list[AgentResponse]) -> AgentResponse:
    """Synthesizes outputs from all executed specialists into prioritized guidance."""
    if not specialist_results:
        return AgentResponse(
            agent="advisor", status=AgentStatus.PARTIAL,
            summary="No usable specialist results were available.",
            evidence=[], confidence=0.0, recommended_actions=[],
        )
    legacy = _legacy_evidence_guidance(question, specialist_results)
    if legacy is not None:
        return legacy
    if all(result.status == AgentStatus.FAILED for result in specialist_results):
        return AgentResponse(
            agent="advisor", status=AgentStatus.PARTIAL,
            summary="No usable specialist results were available.",
            evidence=[], confidence=0.0, recommended_actions=[],
        )
    results_by_agent = {result.agent: result for result in specialist_results}
    sales = results_by_agent.get("sales")
    inventory = results_by_agent.get("inventory")
    if sales is not None and inventory is not None:
        text = question.lower()
        insight = None
        if any(
            term in text
            for term in ("best-selling", "best selling", "top-selling", "top selling", "畅销")
        ):
            insight = _top_seller_stock_risk(sales, inventory)
        elif ("inventory" in text or "库存" in text) and any(
            term in text for term in ("low sales", "sales velocity", "slow-moving", "销售速度", "滞销")
        ):
            insight = _high_value_low_velocity(sales, inventory)
        elif any(
            term in text
            for term in ("purchase order", "purchase orders", "reorder", "replenish", "采购", "补货", "下单")
        ):
            insight = _replenishment_support(sales, inventory)

        confidence = round(min(sales.confidence, inventory.confidence), 2)
        if insight is None and any(
            term in text
            for term in ("decline", "drop", "fell", "fall", "lost", "linked", "下降", "下跌", "损失", "关联")
        ):
            linked = _sales_inventory_link(sales, inventory)
            if linked is not None:
                summary, evidence, confidence = linked
                insight = (
                    summary,
                    evidence,
                    RecommendedAction(
                        type="prioritise_revenue_recovery",
                        risk_level=RiskLevel.GREEN,
                        reason="Sales and inventory evidence identify the same product and matching revenue gap.",
                        parameters={"product_id": _evidence_map(sales).get("focus_product_id")},
                    ),
                )

        if insight is not None:
            summary, evidence, action = insight
            additional_results = [
                result for result in specialist_results if result.agent not in {"sales", "inventory"}
            ]
            if additional_results:
                summary += " Additional specialist findings: " + " | ".join(
                    f"[{result.agent.upper()}]: {result.summary}" for result in additional_results
                )
                for result in additional_results:
                    evidence.extend(result.evidence)
            return AgentResponse(
                agent="advisor",
                status=AgentStatus.SUCCESS,
                summary=summary,
                evidence=evidence,
                confidence=round(
                    min([confidence, *(result.confidence for result in additional_results)]),
                    2,
                ),
                recommended_actions=[action],
            )

    evidence = []
    agent_summaries = []
    for result in specialist_results:
        agent_summaries.append(f"[{result.agent.upper()}]: {result.summary}")
        evidence.extend(result.evidence)

    summary_text = (
        f"Advisor analysis for '{question}': " + " | ".join(agent_summaries)
    )

    return AgentResponse(
        agent="advisor",
        status=AgentStatus.SUCCESS,
        summary=summary_text,
        evidence=evidence,
        confidence=min((result.confidence for result in specialist_results), default=0.0),
        recommended_actions=[],
    )
