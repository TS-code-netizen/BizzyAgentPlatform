from __future__ import annotations

from typing import Any

from backend.models.agent import AgentResponse


def _evidence(response: AgentResponse) -> dict[str, Any]:
    return {item.metric: item.value for item in response.evidence}


def _is_chinese(language: str) -> bool:
    return language.lower().startswith("zh")


def _sales_summary(response: AgentResponse) -> str:
    evidence = _evidence(response)
    intent = evidence.get("analysis_intent")
    change = evidence.get("revenue_change_pct")
    recent = evidence.get("recent_revenue_sgd")
    if intent in {"overview", "revenue_summary", "decline_analysis"} and isinstance(
        change, (int, float)
    ) and isinstance(recent, (int, float)):
        direction = "下降" if change < 0 else "上升"
        text = f"本期收入为 SGD {recent:,.2f}，较基准期{direction} {abs(change):.1f}%。"
        if product_id := evidence.get("focus_product_id"):
            text += f" 主要影响产品为 {product_id}。"
        return text
    if intent == "channel_performance" and "top_channel" in evidence:
        return (
            f"{evidence['top_channel']} 渠道收入最高，为 SGD "
            f"{evidence.get('top_channel_recent_revenue_sgd', 0):,.2f}。"
        )
    if intent == "top_products" and (details := evidence.get("top_product_details")):
        top = details[0]
        return (
            f"收入最高的产品是 {top['product']}（{top['product_id']}），"
            f"本期收入 SGD {top['recent_revenue_sgd']:,.2f}。"
        )
    if intent == "category_margin" and (details := evidence.get("category_margin_details")):
        top = details[0]
        return (
            f"整体毛利率为 {evidence.get('recent_gross_margin_pct', 0):.2f}%；"
            f"{top['category']} 品类毛利率最高，为 {top['gross_margin_pct']:.2f}%。"
        )
    if intent == "product_velocity" and (details := evidence.get("product_velocity_details")):
        slowest = details[0]
        return (
            f"{slowest['product']}（{slowest['product_id']}）近期销售速度最低，"
            f"平均每天 {slowest['avg_daily_units']:.2f} 件。"
        )
    if isinstance(change, (int, float)) and isinstance(recent, (int, float)):
        direction = "下降" if change < 0 else "上升"
        text = f"本期收入为 SGD {recent:,.2f}，较基准期{direction} {abs(change):.1f}%。"
        if product_id := evidence.get("focus_product_id"):
            text += f" 主要影响产品为 {product_id}。"
        return text
    return "销售数据不足，暂时无法完成所需分析。"


def _inventory_summary(response: AgentResponse) -> str:
    evidence = _evidence(response)
    intent = evidence.get("analysis_intent")
    if intent == "overview":
        text = (
            f"当前有 {evidence.get('out_of_stock_product_count', 0)} 个断货商品，"
            f"{evidence.get('at_risk_product_count', 0)} 个商品存在断货风险。"
        )
        if product_id := evidence.get("product_id"):
            text += f" 首要关注 {product_id}，当前库存 {evidence.get('current_stock', 0)} 件。"
        return text
    if intent == "inventory_valuation" and "total_stock_value_sgd" in evidence:
        return f"当前 FIFO 库存总价值为 SGD {evidence['total_stock_value_sgd']:,.2f}。"
    if intent == "supplier_lead_times" and (details := evidence.get("supplier_lead_time_details")):
        top = details[0]
        return f"{top['supplier']} 的补货交期最长，为 {top['lead_time_days']} 天。"
    if intent == "top_seller_cover" and "top_sellers_at_risk_count" in evidence:
        return f"前十畅销商品中有 {evidence['top_sellers_at_risk_count']} 个存在缺货风险。"
    if intent == "what_if" and "simulation_days_of_cover_after_receipt" in evidence:
        return (
            f"情景模拟建议数量为 {evidence['simulation_order_qty']} 件，"
            f"到货后预计可覆盖 {evidence['simulation_days_of_cover_after_receipt']} 天需求。"
        )
    if intent == "reorder_recommendation" and evidence.get("suggested_order_qty_is_provisional"):
        return (
            f"{evidence.get('product_id')} 的暂定追加补货量为 {evidence.get('suggested_order_qty')} 件；"
            "由于在途数量未知，必须先确认到货数量。"
        )
    if product_id := evidence.get("product_id"):
        risk = {
            "out_of_stock": "已经断货",
            "at_risk": "存在断货风险",
            "ok": "库存充足",
        }.get(str(evidence.get("stock_risk")), str(evidence.get("stock_risk")))
        return f"{product_id} 当前库存 {evidence.get('current_stock', 0)} 件，{risk}。"
    return (
        f"当前有 {evidence.get('out_of_stock_product_count', 0)} 个断货商品，"
        f"{evidence.get('at_risk_product_count', 0)} 个商品存在断货风险。"
    )


def _advisor_summary(response: AgentResponse) -> str:
    evidence = _evidence(response)
    if product_id := evidence.get("linked_product_id"):
        return (
            f"销售和库存证据共同支持 {product_id} 的收入下降与缺货相关；"
            f"未满足需求可解释 {evidence.get('stockout_explained_decline_pct', 0):.1f}% 的收入缺口。"
            "这是证据相关性，并非严格因果证明。"
        )
    if products := evidence.get("top_sellers_at_stock_risk"):
        ids = "、".join(str(product["product_id"]) for product in products)
        return f"当前或基准期畅销商品中，{ids} 存在断货风险，应优先检查补货。"
    if products := evidence.get("high_value_low_velocity_products"):
        ids = "、".join(str(product["product_id"]) for product in products)
        return f"{ids} 同时具有较高库存价值和较低销售速度，存在资金占用风险。"
    if products := evidence.get("replenishment_priorities"):
        return (
            f"建议为 {len(products)} 个商品检查补货，"
            f"合计建议数量 {evidence.get('replenishment_total_suggested_units', 0)} 件；"
            f"其中 {evidence.get('provisional_replenishment_count', 0)} 项需要先确认在途数量，采购动作需要审批。"
        )
    return "Advisor 已整合所有专项 Agent 的分析结果，请结合下方证据和建议动作进行决策。"


def localize_response(response: AgentResponse, language: str) -> AgentResponse:
    if not _is_chinese(language):
        return response
    localized = response.model_copy(deep=True)
    if response.agent == "sales":
        localized.summary = _sales_summary(response)
    elif response.agent == "inventory":
        localized.summary = _inventory_summary(response)
    elif response.agent == "advisor":
        localized.summary = _advisor_summary(response)
    elif response.agent == "customer":
        localized.summary = "客户分析已完成；请查看投诉、退款和未回复高意向咨询等证据。"
    elif response.agent == "finance":
        evidence = _evidence(response)
        if evidence.get("analysis_intent") != "overdue_receivables":
            return localized
        localized.summary = (
            f"截至 {evidence.get('as_of_date', '报告日')}，共有 "
            f"{evidence.get('overdue_invoice_count', 0)} 张逾期发票，"
            f"未付余额合计 SGD {evidence.get('overdue_outstanding_sgd', 0):,.2f}。"
        )
    return localized
