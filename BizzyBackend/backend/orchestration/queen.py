from __future__ import annotations

import re
from typing import List
from backend.orchestration.bedrock import classify, InferenceUnavailable
from backend.agents.specialists import customer_bee, finance_bee, inventory_bee, sales_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel
from backend.orchestration.localization import localize_response


AGENT_REGISTRY = {
    "sales": sales_bee,
    "customer": customer_bee,
    "finance": finance_bee,
    "inventory": inventory_bee,
}


def _heuristic_intents(question: str) -> list[str]:
    """Deterministic domain routing for known business terminology."""
    text = question.lower()

    customer_terms = (
        "complaint",
        "defect",
        "enquiry",
        "enquiries",
        "feedback",
        "refund",
        "returned",
        "customer return",
        "leads",
        "billing",
    )
    finance_terms = (
        "invoice",
        "invoices",
        "cash",
        "receivable",
        "receivables",
        "operating expense",
        "operating expenses",
        "rent",
        "utilities",
        "payroll",
        "payment receipt",
        "financial refund amount issued",
    )
    inventory_terms = (
        "stock",
        "inventory",
        "supplier",
        "suppliers",
        "replenish",
        "replenishment",
        "reorder",
        "reordering",
        "warehouse",
        "unfulfilled",
        "availability",
        "purchase order",
        "purchase orders",
        "stockout",
        "stockouts",
        "units left",
        "on hand",
    )
    explicit_sales_terms = (
        "revenue",
        "gross margin",
        "gross profit",
        "sales volume",
        "sales channel",
        "sales invoice",
        "sales velocity",
        "top-selling",
        "top selling",
        "best-selling",
        "best selling",
        "pricing",
        "sales return",
        "sales returns",
    )

    def contains(term: str) -> bool:
        return bool(re.search(rf"\b{re.escape(term)}\b", text))

    selected: set[str] = set()
    if any(contains(term) for term in customer_terms):
        selected.add("customer")
    if contains("lead") and not (contains("lead time") or contains("lead times")):
        selected.add("customer")
    if any(contains(term) for term in ("support enquiry", "support ticket", "customer support")):
        selected.add("customer")
    if any(contains(term) for term in finance_terms):
        selected.add("finance")
    if any(contains(term) for term in inventory_terms):
        selected.add("inventory")
    if "unit" in text and "left" in text:
        selected.add("inventory")
    if any(contains(term) for term in explicit_sales_terms):
        selected.add("sales")
    if contains("enough inventory") and (contains("best-selling") or contains("top-selling")):
        selected.discard("sales")

    if any(term in text for term in ("销售", "收入", "营收", "毛利", "销量", "销售渠道", "畅销")):
        selected.add("sales")
    if any(term in text for term in ("库存", "缺货", "断货", "补货", "采购", "供应商", "仓库", "在途")):
        selected.add("inventory")
    if any(term in text for term in ("投诉", "客诉", "客户反馈", "售后", "退款", "退货", "客户咨询")):
        selected.add("customer")
    if any(term in text for term in ("发票", "现金流", "应收", "逾期", "运营费用", "付款", "财务")):
        selected.add("finance")

    customer_conversation = any(contains(term) for term in ("enquiry", "enquiries", "lead", "complaint"))
    if ("sale" in text or "sales" in text) and not customer_conversation:
        selected.add("sales")

    return [name for name in AGENT_REGISTRY if name in selected]


# Selects which agents to run based on the question
def intent_classifier(question: str) -> List[str]:
    """Uses LLM (or fallback heuristic) to determine which specialist agents are needed."""
    heuristic = _heuristic_intents(question)
    if heuristic:
        return heuristic
    try:
        return classify(question)
    except InferenceUnavailable:
        return []

# Runs the selected specialist agents and returns their results
def run_specialists(question: str, language: str = "en") -> tuple[list[str], list[AgentResponse]]:
    # 1. Intent understanding & routing
    selected_agents = intent_classifier(question)

    # 2. Parallel or sequential execution of chosen specialist bees
    results = []
    if not selected_agents:
        return [], [AgentResponse(
            agent="queen", status=AgentStatus.PARTIAL,
            summary="Unable to determine the requested analysis. Please ask about sales, invoices, inventory or customer enquiries. Deterministic dashboard views remain available.",
            confidence=0.0,
        )]
    for name in selected_agents:
        agent_fn = AGENT_REGISTRY[name]
        results.append(localize_response(agent_fn(question=question), language))

    causal_sales_terms = (
        "why",
        "drop",
        "decline",
        "fell",
        "fall",
        "下降",
        "下跌",
        "减少",
        "为什么",
    )
    sales_result = next((result for result in results if result.agent == "sales"), None)
    should_check_inventory = (
        sales_result is not None
        and "inventory" not in selected_agents
        and any(term in question.lower() for term in causal_sales_terms)
        and any(
            action.type == "investigate_stock_availability"
            for action in sales_result.recommended_actions
        )
    )
    if should_check_inventory:
        selected_agents.append("inventory")
        results.append(
            localize_response(
                inventory_bee(question="stock availability related to sales decline"),
                language,
            )
        )

    return selected_agents, results
