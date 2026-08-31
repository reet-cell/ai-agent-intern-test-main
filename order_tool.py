import json
import re
from pathlib import Path


ORDERS_FILE = Path(__file__).parent / "data" / "orders.json"


def load_orders():
    """Load all orders from the company's JSON file."""
    with open(ORDERS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data["orders"]


def lookup_order(order_id: str):
    """
    Look up an order and return only customer-safe information.
    """

    # Check that an order ID was actually provided
    if not order_id or not order_id.strip():
        return {
            "found": False,
            "error": "missing_order_id",
            "message": "Please provide your order ID."
        }

    # Normalize the order ID
    order_id = order_id.strip().upper()

    # Validate basic order ID format
    if not re.fullmatch(r"ORD-\d{4}", order_id):
        return {
            "found": False,
            "error": "invalid_order_id",
            "message": "The order ID format is invalid. Please provide an ID such as ORD-1001."
        }

    # Load orders
    orders = load_orders()

    # Search for the requested order
    for order in orders:

        if order["order_id"].upper() == order_id:

            # Start with customer-safe information
            result = {
                "found": True,
                "order_id": order["order_id"],
                "customer_name": order["customer"]["name"],
                "membership_tier": order["membership_tier"],
                "items": order["items"],
                "placed_at": order["placed_at"],
                "status": order["status"],
                "status_updated_at": order["status_updated_at"],
                "shipped_at": order["shipped_at"],
                "delivered_at": order["delivered_at"],
                "carrier": order["carrier"],
                "tracking_number": order["tracking_number"],
                "estimated_delivery": order["estimated_delivery"],
                "customer_safe_message": order["customer_safe_message"],
            }

            # Don't expose an ETA for cancelled orders
            if order["status"].lower() == "cancelled":
                result["estimated_delivery"] = None

            return result

    # Order doesn't exist
    return {
        "found": False,
        "error": "order_not_found",
        "message": "Order not found."
    }


if __name__ == "__main__":

    print("Test 1 - normal:")
    print(lookup_order("ORD-1001"))

    print("\nTest 2 - lowercase:")
    print(lookup_order("ord-1001"))

    print("\nTest 3 - spaces:")
    print(lookup_order("  ORD-1001  "))

    print("\nTest 4 - unknown:")
    print(lookup_order("ORD-9999"))

    print("\nTest 5 - missing:")
    print(lookup_order(""))

    print("\nTest 6 - malformed:")
    print(lookup_order("hello"))