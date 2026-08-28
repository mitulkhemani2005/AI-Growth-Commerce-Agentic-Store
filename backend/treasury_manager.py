import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

TREASURY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "treasury.json"))
_lock = threading.RLock()


class TreasuryManager:
    """
    Thread-safe Treasury & Bank Balance Manager for the CEO and Store Owner.
    Tracks live bank balance, wholesale inventory acquisition spending,
    sales revenues earned, agent salaries disbursed, and realized net profit.
    """
    def __init__(self, file_path: str = TREASURY_FILE):
        self.file_path = file_path
        self._default_balance = float(os.environ.get("CEO_BANK_BALANCE", "1000.0"))
        self._ensure_file()


    def _ensure_file(self):
        with _lock:
            if not os.path.exists(self.file_path):
                data = {
                    "bank_balance": self._default_balance,
                    "initial_bank_balance": self._default_balance,
                    "total_sales_revenue": 0.0,
                    "total_inventory_spend": 0.0,
                    "total_salaries_paid": 0.0,
                    "total_refunds_deducted": 0.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "transactions": [
                        {
                            "id": f"tx_{uuid.uuid4().hex[:8]}",
                            "type": "INITIAL_CAPITAL",
                            "amount": self._default_balance,
                            "balance_after": self._default_balance,
                            "description": f"Initial Store Capital & CEO Bank Balance configured from .env (₹{self._default_balance:,.2f})",
                            "actor": "System / Store Owner",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    ]
                }
                self._write_treasury(data)

    def _read_treasury(self) -> Dict[str, Any]:
        with _lock:
            if not os.path.exists(self.file_path):
                self._ensure_file()
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {
                    "bank_balance": self._default_balance,
                    "initial_bank_balance": self._default_balance,
                    "total_sales_revenue": 0.0,
                    "total_inventory_spend": 0.0,
                    "total_salaries_paid": 0.0,
                    "total_refunds_deducted": 0.0,
                    "transactions": []
                }

    def _write_treasury(self, data: Dict[str, Any]) -> None:
        with _lock:
            tmp_file = f"{self.file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_file, self.file_path)
            except Exception:
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except Exception:
                        pass
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """Returns high-level treasury metrics, cash flows, and profit calculation."""
        with _lock:
            t = self._read_treasury()
            balance = float(t.get("bank_balance", 0.0))
            init_balance = float(t.get("initial_bank_balance", self._default_balance))
            revenue = float(t.get("total_sales_revenue", 0.0))
            inv_spend = float(t.get("total_inventory_spend", 0.0))
            salaries = float(t.get("total_salaries_paid", 0.0))
            refunds = float(t.get("total_refunds_deducted", 0.0))

            # Profit Formulas:
            # Gross Profit = Sales Revenue - Cost of Goods Sold/Acquired
            gross_profit = revenue - inv_spend
            # Net Realized Profit = Gross Profit - Salaries Paid - Refunds
            net_profit = revenue - inv_spend - salaries - refunds
            
            # Net Balance Change
            net_cash_flow = balance - init_balance
            roi_pct = (net_profit / inv_spend * 100) if inv_spend > 0 else 0.0

            return {
                "success": True,
                "currency": "INR",
                "bank_balance": round(balance, 2),
                "initial_bank_balance": round(init_balance, 2),
                "total_sales_revenue": round(revenue, 2),
                "total_inventory_spend": round(inv_spend, 2),
                "total_wholesale_stock_spend": round(inv_spend, 2),
                "total_salaries_paid": round(salaries, 2),
                "total_salary_expenses": round(salaries, 2),
                "total_refunds_deducted": round(refunds, 2),
                "total_refunds_issued": round(refunds, 2),
                "gross_profit": round(gross_profit, 2),
                "net_profit": round(net_profit, 2),
                "net_cash_flow": round(net_cash_flow, 2),
                "roi_percentage": round(roi_pct, 2),
                "roi_pct": round(roi_pct, 2),
                "gross_profit_margin_pct": round((gross_profit / revenue * 100) if revenue > 0 else 0.0, 1),
                "transaction_count": len(t.get("transactions", [])),
                "transactions": t.get("transactions", [])[:30],
                "recent_transactions": t.get("transactions", [])[:10]
            }


    def spend_for_stock(
        self,
        product_id: str,
        product_name: str,
        quantity: int,
        base_price: float,
        actor: str = "CEO Agent"
    ) -> Dict[str, Any]:
        """
        Deducts wholesale inventory acquisition cost from CEO Bank Balance at BASE_PRICE.
        Fails if treasury funds are insufficient.
        """
        with _lock:
            t = self._read_treasury()
            total_cost = round(base_price * quantity, 2)
            balance = float(t.get("bank_balance", 0.0))

            if balance < total_cost:
                return {
                    "success": False,
                    "error": f"Insufficient Treasury Bank Balance! Required: ₹{total_cost:,.2f} ({quantity}x @ ₹{base_price:,.2f}), Available: ₹{balance:,.2f}.",
                    "current_balance": balance,
                    "required_cost": total_cost,
                    "deficit": round(total_cost - balance, 2)
                }

            new_balance = round(balance - total_cost, 2)
            t["bank_balance"] = new_balance
            t["total_inventory_spend"] = round(float(t.get("total_inventory_spend", 0.0)) + total_cost, 2)

            tx = {
                "id": f"tx_{uuid.uuid4().hex[:8]}",
                "type": "STOCK_PURCHASE",
                "amount": total_cost,
                "balance_after": new_balance,
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
                "unit_cost": base_price,
                "description": f"Acquired {quantity} units of '{product_name}' at wholesale Base Price ₹{base_price:,.2f}/unit.",
                "actor": actor,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            tx_list = t.get("transactions", [])
            tx_list.insert(0, tx)
            t["transactions"] = tx_list[:500]

            self._write_treasury(t)

            return {
                "success": True,
                "message": f"Successfully acquired {quantity} units of '{product_name}' for ₹{total_cost:,.2f}. New bank balance: ₹{new_balance:,.2f}.",
                "total_cost": total_cost,
                "new_balance": new_balance,
                "transaction": tx
            }

    def deposit_sales(
        self,
        amount: float,
        order_id: str,
        items_summary: str = "",
        customer: str = "Customer"
    ) -> Dict[str, Any]:
        """
        Deposits customer or AI Buyer purchase payments directly into the CEO Bank Balance.
        """
        with _lock:
            t = self._read_treasury()
            amount_clean = round(float(amount), 2)
            balance = float(t.get("bank_balance", 0.0))
            new_balance = round(balance + amount_clean, 2)

            t["bank_balance"] = new_balance
            t["total_sales_revenue"] = round(float(t.get("total_sales_revenue", 0.0)) + amount_clean, 2)

            tx = {
                "id": f"tx_{uuid.uuid4().hex[:8]}",
                "type": "SALES_REVENUE",
                "amount": amount_clean,
                "balance_after": new_balance,
                "order_id": order_id,
                "customer": customer,
                "description": f"Received payment of ₹{amount_clean:,.2f} for Order #{order_id} ({customer}). {items_summary}".strip(),
                "actor": "Payment Gateway / AP2",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            tx_list = t.get("transactions", [])
            tx_list.insert(0, tx)
            t["transactions"] = tx_list[:500]

            self._write_treasury(t)

            return {
                "success": True,
                "deposited_amount": amount_clean,
                "new_balance": new_balance,
                "transaction": tx
            }

    def deduct_refund(
        self,
        amount: float,
        order_id: str,
        reason: str = "Customer Return / Refund",
        actor: str = "Finance Manager Agent"
    ) -> Dict[str, Any]:
        """
        Deducts processed refund from CEO Bank Balance when return/cancellation is approved.
        """
        with _lock:
            t = self._read_treasury()
            amount_clean = round(float(amount), 2)
            balance = float(t.get("bank_balance", 0.0))
            new_balance = round(balance - amount_clean, 2)

            t["bank_balance"] = new_balance
            t["total_refunds_deducted"] = round(float(t.get("total_refunds_deducted", 0.0)) + amount_clean, 2)

            tx = {
                "id": f"tx_{uuid.uuid4().hex[:8]}",
                "type": "REFUND_EXPENSE",
                "amount": amount_clean,
                "balance_after": new_balance,
                "order_id": order_id,
                "description": f"Refund of ₹{amount_clean:,.2f} issued for Order #{order_id} ({reason}).",
                "actor": actor,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            tx_list = t.get("transactions", [])
            tx_list.insert(0, tx)
            t["transactions"] = tx_list[:500]

            self._write_treasury(t)

            return {
                "success": True,
                "refunded_amount": amount_clean,
                "new_balance": new_balance,
                "transaction": tx
            }

    def deduct_salary(
        self,
        agent_name: str,
        amount: float,
        period_info: str = "Payroll Cycle",
        actor: str = "CEO Agent"
    ) -> Dict[str, Any]:
        """
        Deducts negotiated agent salary payment from CEO Bank Balance.
        """
        with _lock:
            t = self._read_treasury()
            amount_clean = round(float(amount), 2)
            balance = float(t.get("bank_balance", 0.0))

            if balance < amount_clean:
                return {
                    "success": False,
                    "error": f"Insufficient Treasury funds to pay {agent_name}'s salary of ₹{amount_clean:,.2f}. Current balance: ₹{balance:,.2f}."
                }

            new_balance = round(balance - amount_clean, 2)
            t["bank_balance"] = new_balance
            t["total_salaries_paid"] = round(float(t.get("total_salaries_paid", 0.0)) + amount_clean, 2)

            tx = {
                "id": f"tx_{uuid.uuid4().hex[:8]}",
                "type": "SALARY_PAYOUT",
                "amount": amount_clean,
                "balance_after": new_balance,
                "agent_name": agent_name,
                "description": f"Paid salary of ₹{amount_clean:,.2f} to {agent_name} ({period_info}).",
                "actor": actor,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            tx_list = t.get("transactions", [])
            tx_list.insert(0, tx)
            t["transactions"] = tx_list[:500]

            self._write_treasury(t)

            return {
                "success": True,
                "agent_name": agent_name,
                "salary_paid": amount_clean,
                "new_balance": new_balance,
                "transaction": tx
            }

    def get_transactions(self, limit: int = 50, tx_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with _lock:
            t = self._read_treasury()
            txs = t.get("transactions", [])
            if tx_type:
                txs = [x for x in txs if x.get("type") == tx_type]
            return txs[:limit]

    def reset_treasury(self, new_balance: Optional[float] = None) -> Dict[str, Any]:
        """Resets the treasury ledger and initializes starting balance."""
        with _lock:
            starting = float(new_balance) if new_balance is not None else float(os.environ.get("CEO_BANK_BALANCE", "1000.0"))
            data = {

                "bank_balance": starting,
                "initial_bank_balance": starting,
                "total_sales_revenue": 0.0,
                "total_inventory_spend": 0.0,
                "total_salaries_paid": 0.0,
                "total_refunds_deducted": 0.0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "transactions": [
                    {
                        "id": f"tx_{uuid.uuid4().hex[:8]}",
                        "type": "INITIAL_CAPITAL",
                        "amount": starting,
                        "balance_after": starting,
                        "description": f"Treasury reset to starting capital of ₹{starting:,.2f}.",
                        "actor": "Store Owner",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            }
            self._write_treasury(data)
            return {"success": True, "bank_balance": starting, "message": f"Treasury reset to ₹{starting:,.2f}."}


treasury_manager = TreasuryManager()
