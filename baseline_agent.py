"""
AI Support Agent

This module coordinates:
1. Conversation context
2. Knowledge-base retrieval through RAG
3. Order lookup through order_tool
4. Safety and privacy rules
5. Human handoff decisions

The LLM can be connected later.
"""

from rag import build_rag_index, search_knowledge_base
from order_tool import lookup_order


# ============================================================
# AGENT CLASS
# ============================================================

class SupportAgent:

    def __init__(self):
        """
        Initialize the agent.

        We build the RAG index once when the agent starts
        instead of rebuilding it for every user question.
        """

        print("Loading knowledge base...")

        self.chunks, self.embeddings = build_rag_index()

        # Conversation history for this session.
        self.history = []

        # Store the most recently mentioned order ID.
        self.current_order_id = None

        print(
            f"Loaded {len(self.chunks)} knowledge chunks."
        )


    # ========================================================
    # CONVERSATION HISTORY
    # ========================================================

    def add_message(self, role, content):
        """
        Add a message to the current conversation.
        """

        self.history.append(
            {
                "role": role,
                "content": content
            }
        )


    def get_recent_history(self, limit=6):
        """
        Return only recent conversation messages.

        We don't want unrelated old information to remain
        active forever.
        """

        return self.history[-limit:]


    # ========================================================
    # ORDER ID DETECTION
    # ========================================================

    def extract_order_id(self, message):
        """
        Detect an order ID such as ORD-1001.

        Returns None when no order ID is present.
        """

        import re

        match = re.search(
            r"\bORD-\d+\b",
            message.upper()
        )

        if match:
            return match.group(0)

        return None


    # ========================================================
    # ORDER QUESTION DETECTION
    # ========================================================

    def is_order_question(self, message):
            

    # If an order ID is explicitly present, this is
    # definitely an order-related request.
        if self.extract_order_id(message):
            return True

        order_keywords = [
        "order",
        "shipment",
        "shipped",
        "shipping",
        "delivery",
        "delivered",
        "arrive",
        "tracking",
        "track",
        "cancel my order",
        "where is my package",
        "where is my parcel",
        "where is it"
    ]

        message_lower = message.lower()

        return any(
        keyword in message_lower
        for keyword in order_keywords
    )


    # ========================================================
    # POLICY QUESTION DETECTION
    # ========================================================

    def is_policy_question(self, message):
        """
        Determine whether the question likely requires
        knowledge-base retrieval.
        """

        policy_keywords = [
            "return",
            "refund",
            "exchange",
            "warranty",
            "shipping",
            "ship",
            "international",
            "canada",
            "delivery",
            "cancel",
            "cancellation",
            "final sale",
            "gift card",
            "price adjustment",
            "membership",
            "trailplus",
            "care",
            "damaged",
            "wrong item"
        ]

        message_lower = message.lower()

        return any(
            keyword in message_lower
            for keyword in policy_keywords
        )


    # ========================================================
    # SENSITIVE REQUEST DETECTION
    # ========================================================

    def is_sensitive_request(self, message):
        """
        Detect requests for information that must never
        be exposed to customers.
        """

        sensitive_keywords = [
            "system prompt",
            "hidden prompt",
            "instructions",
            "secret",
            "api key",
            "api keys",
            "password",
            "customer email",
            "customer address",
            "risk score",
            "internal note",
            "internal notes",
            "warehouse note"
        ]

        message_lower = message.lower()

        return any(
            keyword in message_lower
            for keyword in sensitive_keywords
        )


    # ========================================================
    # ORDER LOOKUP
    # ========================================================

    def get_order(self, order_id):
        """
        Safely perform an order lookup.

        Only sanitized information returned by
        lookup_order() should be passed to the user.
        """

        if not order_id:
            return {
                "found": False,
                "needs_order_id": True,
                "message": (
                    "Please provide your order ID "
                    "(for example, ORD-1001)."
                )
            }

        result = lookup_order(
            order_id
        )

        if not result.get("found"):

            return {
                "found": False,
                "needs_order_id": False,
                "message": "I couldn't find that order."
            }

        self.current_order_id = result[
            "order_id"
        ]

        return result


    # ========================================================
    # RAG SEARCH
    # ========================================================

    def search_policy(self, question):
        """
        Search the knowledge base for company-specific
        information.
        """

        return search_knowledge_base(
            query=question,
            chunks=self.chunks,
            embeddings=self.embeddings,
            top_k=5
        )


    # ========================================================
    # SAFE RESPONSE GENERATION
    # ========================================================

    def respond_without_llm(self, message):
        """
        Temporary deterministic response layer.

        This allows us to test the application's tools and
        safety behavior before connecting an LLM.
        """

        # ----------------------------------------------------
        # Security / privacy
        # ----------------------------------------------------

        if self.is_sensitive_request(message):

            response = (
                "I can't provide system instructions, "
                "secrets, or internal customer information."
            )

            self.add_message(
                "user",
                message
            )

            self.add_message(
                "assistant",
                response
            )

            return {
                "answer": response,
                "sources": [],
                "handoff": False,
                "tool_used": None
            }


        # ----------------------------------------------------
        # Detect explicit order ID
        # ----------------------------------------------------

        order_id = self.extract_order_id(
            message
        )

        if order_id:

            self.current_order_id = order_id


        # ----------------------------------------------------
        # Order question
        # ----------------------------------------------------

        if self.is_order_question(message):

            # If no ID is present, use previous order context.
            if not order_id:

                order_id = self.current_order_id


            # Still no ID.
            if not order_id:

                response = (
                    "Sure. Please provide your order ID "
                    "(for example, ORD-1001), and I'll "
                    "check the current order status."
                )

                self.add_message(
                    "user",
                    message
                )

                self.add_message(
                    "assistant",
                    response
                )

                return {
                    "answer": response,
                    "sources": [],
                    "handoff": False,
                    "tool_used": None
                }


            # Actually perform the lookup.
            order_result = self.get_order(
                order_id
            )


            if not order_result.get("found"):

                response = (
                    "I couldn't find that order. "
                    "Please check the order ID and try again."
                )

                self.add_message(
                    "user",
                    message
                )

                self.add_message(
                    "assistant",
                    response
                )

                return {
                    "answer": response,
                    "sources": [],
                    "handoff": False,
                    "tool_used": "lookup_order"
                }


            # ------------------------------------------------
            # Build customer-safe response.
            # ------------------------------------------------

            order_status = order_result.get(
                "status"
            )

            customer_name = order_result.get(
                "customer_name"
            )

            answer = (
                f"Order {order_result['order_id']} "
                f"for {customer_name} is currently "
                f"{order_status}."
            )


            # Only mention delivery information when
            # it actually exists.
            estimated_delivery = order_result.get(
                "estimated_delivery"
            )

            if estimated_delivery:

                answer += (
                    f" The estimated delivery is "
                    f"{estimated_delivery}."
                )


            customer_safe_message = (
                order_result.get(
                    "customer_safe_message"
                )
            )

            if customer_safe_message:

                answer += (
                    f" {customer_safe_message}"
                )


            self.add_message(
                "user",
                message
            )

            self.add_message(
                "assistant",
                answer
            )

            return {
                "answer": answer,
                "sources": [],
                "handoff": False,
                "tool_used": "lookup_order"
            }


        # ----------------------------------------------------
        # Policy question
        # ----------------------------------------------------

        if self.is_policy_question(message):

            rag_result = self.search_policy(
                message
            )


            # ------------------------------------------------
            # Insufficient evidence
            # ------------------------------------------------

            if rag_result.get("abstain"):

                response = (
                    "I don't have enough reliable information "
                    "in the available company documentation "
                    "to answer that confidently. "
                    "A support representative should review "
                    "this for you."
                )

                self.add_message(
                    "user",
                    message
                )

                self.add_message(
                    "assistant",
                    response
                )

                return {
                    "answer": response,
                    "sources": [],
                    "handoff": True,
                    "tool_used": "rag"
                }


            # ------------------------------------------------
            # Conflict
            # ------------------------------------------------

            if rag_result.get("conflicts"):

                response = (
                    "I found conflicting information in the "
                    "current company documentation, so I don't "
                    "want to give you an unreliable answer. "
                    "A support representative should review "
                    "this for you."
                )

                self.add_message(
                    "user",
                    message
                )

                self.add_message(
                    "assistant",
                    response
                )

                return {
                    "answer": response,
                    "sources": rag_result.get(
                        "citations",
                        []
                    ),
                    "handoff": True,
                    "tool_used": "rag"
                }


            # ------------------------------------------------
            # Evidence found
            # ------------------------------------------------

            top_result = rag_result[
                "results"
            ][0]

            answer = (
                "Based on the company documentation:\n\n"
                + top_result["text"]
            )

            self.add_message(
                "user",
                message
            )

            self.add_message(
                "assistant",
                answer
            )

            return {
                "answer": answer,
                "sources": rag_result.get(
                    "citations",
                    []
                ),
                "handoff": False,
                "tool_used": "rag"
            }


        # ----------------------------------------------------
        # Unknown question
        # ----------------------------------------------------

        response = (
            "I'm not sure I have enough information to "
            "answer that accurately. Could you provide "
            "a little more detail?"
        )

        self.add_message(
            "user",
            message
        )

        self.add_message(
            "assistant",
            response
        )

        return {
            "answer": response,
            "sources": [],
            "handoff": False,
            "tool_used": None
        }


# ============================================================
# CLI
# ============================================================

def main():

    print("=" * 70)
    print("ASTER & ROW AI SUPPORT AGENT")
    print("=" * 70)

    print(
        "\nType 'exit' to quit."
    )

    agent = SupportAgent()

    while True:

        try:

            user_message = input(
                "\nYou: "
            ).strip()

        except KeyboardInterrupt:

            print(
                "\nGoodbye!"
            )

            break


        if not user_message:
            continue


        if user_message.lower() in {
            "exit",
            "quit"
        }:

            print(
                "Goodbye!"
            )

            break


        result = agent.respond_without_llm(
            user_message
        )


        print(
            "\nAgent:"
        )

        print(
            result["answer"]
        )


        if result["sources"]:

            print(
                "\nSources:"
            )

            for source in result[
                "sources"
            ]:

                print(
                    f"- {source}"
                )


        if result["handoff"]:

            print(
                "\nHuman handoff recommended: YES"
            )


if __name__ == "__main__":

    main()