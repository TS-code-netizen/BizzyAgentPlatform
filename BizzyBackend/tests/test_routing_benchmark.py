"""Team benchmark: which specialist Bees Queen Bee should invoke for each question.

Opt-in while routing is being tuned, so it does not fail the regular suite:
    BIZZY_RUN_ROUTING_BENCHMARK=1 pytest tests/test_routing_benchmark.py
"""

from __future__ import annotations

import os

import pytest

from backend.orchestration.queen import intent_classifier

S, C, F, I = "sales", "customer", "finance", "inventory"

BENCHMARK: list[tuple[str, set[str]]] = [
    ("What was our total sales revenue and unit volume for the past week?", {S}),
    ("Why did our weekly sales revenue drop compared to the baseline period?", {S}),
    ("Which sales channels generated the most revenue between Web, Retail, and B2B?", {S}),
    ("Can you give me a summary of our top 5 revenue-generating products?", {S}),
    ("How does our current gross margin compare across our product categories?", {S}),
    ("Which product has the highest defect complaint rate and how many units were affected?", {C}),
    ("Are there any high-intent customer sales enquiries that remain unanswered?", {C}),
    ("What is the total financial refund impact resulting from customer product returns?", {C}),
    ("How many open support enquiries are currently waiting for a response?", {C}),
    ("What are the most common complaint reasons reported by customers in feedback?", {C}),
    ("How many invoices are currently overdue and what is the total outstanding amount in SGD?", {F}),
    ("What is our current closing cash balance as of the reporting date?", {F}),
    ("How much did we spend on operating expenses like rent, utilities, and payroll this month?", {F}),
    ("Can you provide an aging summary of our unpaid customer receivables?", {F}),
    ("What is our net cash flow trend over the past three calendar months?", {F}),
    ("Are there any products currently out of stock or below their reorder threshold?", {I}),
    ("What is the total FIFO stock valuation of our warehouse inventory right now?", {I}),
    ("How many unfulfilled unit orders occurred for Product A (PRD001) during the stockout?", {I}),
    ("Which suppliers have the longest lead times for stock replenishment?", {I}),
    ("Do we have enough inventory on hand for our top 10 best-selling items?", {I}),
    ("Why did our sales revenue decline this week and is it linked to stock shortages?", {S, I}),
    ("Which of our top best-selling products are at risk of running out of stock soon?", {S, I}),
    ("How many sales were lost or unfulfilled because Product A (PRD001) was out of stock?", {S, I}),
    ("Which products have high inventory valuation but low sales velocity?", {S, I}),
    ("Do we need to place new purchase orders to support our current sales revenue targets?", {S, I}),
    ("Are product quality defect complaints causing stock returns that affect our current inventory valuation?", {C, I}),
    ("Which suppliers supply the products with the highest customer complaint defect rates?", {C, I}),
    ("Do we have enough replacement stock available to resolve returned defective items for PRD007?", {C, I}),
    ("Are customer enquiries about product availability correlated with our out-of-stock items?", {C, I}),
    ("Should we pause reordering from specific suppliers who have high customer defect complaint rates?", {C, I}),
    ("How much of our recent sales revenue is still locked in unpaid or overdue customer invoices?", {F, S}),
    ("What is our gross profit margin after subtracting operating expenses and sales returns?", {F, S}),
    ("Are customer payment receipts keeping up with our weekly sales invoice generation?", {F, S}),
    ("How does our net cash flow compare against our total realized sales revenue this month?", {F, S}),
    ("Which customer segments represent the highest unpaid overdue invoice risk relative to their sales volume?", {F, S}),
    ("What is the total financial refund amount issued to customers due to product quality complaints?", {C, F}),
    ("Are customer complaints about billing or incorrect invoices causing delays in invoice payments?", {C, F}),
    ("How much cash flow are we losing from high-intent customer leads that were never answered or converted?", {C, F}),
    ("Do customers with overdue invoices also have open support enquiries or negative feedback?", {C, F}),
    (
        "Comprehensive Business Health Check: Summarize our sales revenue, customer complaint defect rates, "
        "overdue invoice risk, and stockout levels.",
        {S, C, F, I},
    ),
]

pytestmark = pytest.mark.skipif(
    os.getenv("BIZZY_RUN_ROUTING_BENCHMARK") != "1",
    reason="opt-in routing benchmark; set BIZZY_RUN_ROUTING_BENCHMARK=1",
)


@pytest.mark.parametrize(
    ("question", "expected"),
    BENCHMARK,
    ids=[f"{index:02d}-{'+'.join(sorted(expected))}" for index, (_, expected) in enumerate(BENCHMARK, 1)],
)
def test_queen_routes_benchmark_question(question: str, expected: set[str]) -> None:
    assert set(intent_classifier(question)) == expected
