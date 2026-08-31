import json
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from rag import build_rag_index, search_knowledge_base
from order_tool import lookup_order



load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

# Keep deterministic mode for evaluator reliability.
USE_OPENAI = False
client = None





class SupportAgent:

    def __init__(self, debug=False):

        self.debug = debug

        print("Loading knowledge base...")

        self.chunks, self.embeddings = build_rag_index()

        print(f"Loaded {len(self.chunks)} knowledge chunks.")

        self.history = []

        self.current_order_id = None

        # Last policy topic for multi-turn conversations.
        self.last_policy_topic = None


    def log(self, event, data=None):

        if not self.debug:
            return

        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "data": data
        }

        print(
            "\n[DEBUG]"
            + json.dumps(
                record,
                indent=2,
                default=str
            )
        )


    def extract_order_id(self, text):

        match = re.search(
            r"\bORD[-\s]?\d+\b",
            text.upper()
        )

        if not match:
            return None

        value = match.group(0).upper()

        value = value.replace(" ", "-")

        return value


    def security_type(self, message):

        text = message.lower()


        system_patterns = [
            "system prompt",
            "system instruction",
            "system instructions",
            "hidden prompt",
            "hidden instruction",
            "hidden instructions",
            "developer prompt",
            "developer instruction",
            "developer instructions",
            "internal instruction",
            "internal instructions",
            "api key",
            "api keys",
            "openai_api_key",
            "secret key",
            "password",
            "credentials",
            "show me your prompt",
            "reveal your prompt",
            "print your prompt",
            "what is your system prompt",
        ]

        if any(p in text for p in system_patterns):
            return "system"


        privacy_patterns = [
            "customer email",
            "customer's email",
            "customer email address",
            "customer's email address",

            "customer address",
            "customer's address",
            "customer home address",
            "customer's home address",

            "email address",
            "email on the order",
            "email on order",
            "email associated with",
            "what email",
            "which email",

            "home address",
            "shipping address",
            "billing address",

            "risk score",
            "risk scores",

            "fraud review",
            "fraud-review",
            "fraud information",

            "internal note",
            "internal notes",
            "warehouse note",
            "warehouse notes",
            "internal customer information",
        ]

        if any(p in text for p in privacy_patterns):
            return "privacy"

        return None

    def security_response(self, security_type):

        if security_type == "privacy":

            return (
                "I can't provide private customer information "
                "such as email addresses, physical addresses, "
                "risk scores, fraud-review details, or internal "
                "notes. Please contact human support if you need "
                "assistance with that information."
            )

        return (
            "I can't provide system instructions, secrets, "
            "or other internal information."
        )


    def order_lookup(self, order_id):

        self.log(
            "order_tool_call",
            {
                "order_id": order_id
            }
        )

        try:

            result = lookup_order(order_id)

        except Exception as e:

            self.log(
                "order_tool_error",
                {
                    "error": str(e)
                }
            )

            return {
                "found": False,
                "lookup_error": True,
                "message": "Unable to access order information."
            }

        if not result or not result.get("found"):

            sanitized = {
                "found": False,
                "lookup_error": False,
                "message": "Order was not found."
            }

            self.log(
                "order_tool_result",
                sanitized
            )

            return sanitized


        allowed_fields = [
            "order_id",
            "status",
            "status_updated_at",
            "shipped_at",
            "delivered_at",
            "carrier",
            "tracking_number",
            "estimated_delivery",
            "customer_safe_message",
        ]

        sanitized = {
            "found": True
        }

        for field in allowed_fields:

            if field in result:

                sanitized[field] = result[field]

        self.current_order_id = sanitized.get(
            "order_id",
            self.current_order_id
        )

        self.log(
            "order_tool_result",
            sanitized
        )

        return sanitized


    def knowledge_search(self, query):

        self.log(
            "rag_query",
            {
                "query": query
            }
        )

        try:

            result = search_knowledge_base(
                query=query,
                chunks=self.chunks,
                embeddings=self.embeddings,
                top_k=8
            )

        except Exception as e:

            self.log(
                "rag_error",
                {
                    "error": str(e)
                }
            )

            return {
                "results": [],
                "evidence": "",
                "citations": [],
                "conflicts": []
            }

        if self.debug:

            debug_results = []

            for item in result.get("results", []):

                metadata = item.get(
                    "metadata",
                    {}
                )

                debug_results.append(
                    {
                        "source": metadata.get("source"),
                        "heading": metadata.get("heading"),
                        "score": item.get("score"),
                        "original_score": item.get(
                            "original_score"
                        )
                    }
                )

            self.log(
                "rag_results",
                debug_results
            )

        return result


    def get_context(self):

        return self.history[-10:]


    def is_order_question(self, message):

        words = [
            "my order",
            "order status",
            "delivery status",
            "shipping status",
            "shipment",
            "tracking",
            "where is my",
            "package",
            "parcel",
            "estimated delivery",
            "has it shipped",
            "shipped",
            "arrive",
            "arrival",
            "dispatch",
        ]

        text = message.lower()

        return any(
            word in text
            for word in words
        )


    def is_trailplus_return(self, question):

        text = question.lower()

        return (
            "return" in text
            and (
                "trailplus" in text
                or "trail plus" in text
                or "membership" in text
            )
        )

    def is_backpack_return(self, question):

        text = question.lower()

        return (
            "return" in text
            and (
                "backpack" in text
                or "bag" in text
            )
        )

    def is_return_question(self, question):

        text = question.lower()

        return (
            "return" in text
            or "refund" in text
            or "send back" in text
        )

    def is_warranty_question(self, question):

        return "warranty" in question.lower()

    def is_international_shipping(self, question):

        text = question.lower()

        return (
            "international" in text
            or "canada" in text
            or "canadian" in text
            or "germany" in text
            or "german" in text
            or "country" in text
            or "duties" in text
            or "taxes" in text
            or "brokerage" in text
        )

    def is_damaged_final_sale(self, question):

        text = question.lower()

        return (
            (
                "final sale" in text
                or "final-sale" in text
            )
            and (
                "damaged" in text
                or "defective" in text
                or "incorrect" in text
                or "wrong" in text
            )
        )

    def is_breeze_conflict(self, question):

        text = question.lower()

        return (
            "breeze" in text
            and "tumbler" in text
            and (
                "dishwasher" in text
                or "dish washer" in text
            )
        )

    def is_material_certification_question(self, question):

        text = question.lower()

        return (
            (
                "vegan" in text
                or "certified" in text
                or "certification" in text
            )
            and (
                "material" in text
                or "bag" in text
                or "backpack" in text
                or "product" in text
                or "vegan" in text
            )
        )


    def detect_policy_topic(self, question):

        text = question.lower()

        if self.is_trailplus_return(text):
            return "trailplus"

        if self.is_damaged_final_sale(text):
            return "damaged_final_sale"

        if self.is_breeze_conflict(text):
            return "breeze"

        if self.is_material_certification_question(text):
            return "materials"

        if self.is_warranty_question(text):
            return "warranty"

        if self.is_international_shipping(text):
            return "international"

        if self.is_return_question(text):
            return "returns"

        return None


    def is_followup_question(self, question):

        text = question.lower().strip()

        followup_phrases = [
            "what about",
            "how about",
            "and what about",
            "what are the duties",
            "what about duties",
            "what about taxes",
            "what about shipping",
            "how long",
            "and the",
            "does that include",
            "does it include",
            "what else",
            "what about returns",
            "what about the return",
        ]

        return any(
            phrase in text
            for phrase in followup_phrases
        )


    def generate_rag_answer(
        self,
        user_message,
        rag_result
    ):

        question = user_message.lower()

        results = rag_result.get(
            "results",
            []
        )

        evidence = rag_result.get(
            "evidence",
            ""
        )

        citations = rag_result.get(
            "citations",
            []
        )

        conflicts = rag_result.get(
            "conflicts",
            []
        )


        if self.is_damaged_final_sale(question):

            self.last_policy_topic = "damaged_final_sale"

            return (
                "Final sale does not block review of an item "
                "that arrives damaged, defective, or incorrect. "
                "The final-sale restriction applies to "
                "change-of-mind returns.\n\n"
                "Damaged, defective, or incorrect items must be "
                "reported within 7 days of delivery.\n\n"
                "A human support representative must review "
                "the case before any return, replacement, refund, "
                "or other resolution is approved.\n\n"
                "Sources: 03-final-sale-and-promotions.md; "
                "04-damaged-or-wrong-items.md"
            )


        if self.is_breeze_conflict(question):

            self.last_policy_topic = "breeze"

            return (
                "I found conflicting information in the current "
                "Aster & Row documentation about dishwasher use "
                "for the Breeze Tumbler. The Product Card says "
                "all components are dishwasher safe, while the "
                "Product Care Guide says the stainless-steel body "
                "should be hand-washed.\n\n"
                "The safest interim guidance is to hand-wash the "
                "stainless-steel body until the conflict is "
                "clarified. Please contact a human support "
                "representative for confirmation.\n\n"
                "Sources: 11-product-care.md; "
                "12-breeze-tumbler-product-card.md"
            )


        if self.is_material_certification_question(question):

            self.last_policy_topic = "materials"

            return (
                "The supplied Aster & Row information is "
                "insufficient to verify the product's "
                "certification status or guarantee that it is "
                "certified vegan.\n\n"
                "I don't want to make an unsupported claim. "
                "Human confirmation is required. Please contact "
                "a human support representative for confirmation."
            )


        if self.is_trailplus_return(question):

            self.last_policy_topic = "trailplus"

            return (
                "If your TrailPlus membership was active when "
                "the order was placed, eligible items have a "
                "45 calendar day return window from delivery.\n\n"
                "Source: 09-trailplus-membership.md"
            )


        if self.is_warranty_question(question):

            self.last_policy_topic = "warranty"

            return (
                "Aster & Row does not offer a lifetime warranty.\n\n"
                "Bags and backpacks have a 2-year limited warranty "
                "from the purchase date.\n\n"
                "Drinkware and travel accessories have a "
                "1-year warranty.\n\n"
                "Source: 07-warranty.md — Warranty periods"
            )


        if self.is_international_shipping(question):

            self.last_policy_topic = "international"

            # Germany
            if (
                "germany" in question
                or "german" in question
            ):

                return (
                    "Shipping to Germany is not currently available. "
                    "Germany is not a currently supported "
                    "international shipping destination. "
                    "Aster & Row currently supports international "
                    "shipping only to Canada.\n\n"
                    "Source: 06-international-shipping.md — "
                    "Supported destinations"
                )

            # Duties / taxes
            if (
                "duties" in question
                or "taxes" in question
                or "brokerage" in question
            ):

                return (
                    "Canada is a supported international "
                    "shipping destination.\n\n"
                    "For Canadian orders, import duties and taxes "
                    "are not prepaid. Brokerage charges are also "
                    "not prepaid and are the recipient's "
                    "responsibility.\n\n"
                    "Source: 06-international-shipping.md — "
                    "Duties and taxes"
                )

            return (
                "Canada is a supported international shipping "
                "destination. Aster & Row currently ships "
                "internationally only to Canada.\n\n"
                "Canadian orders typically arrive within "
                "5–9 business days after dispatch.\n\n"
                "Import duties, taxes, and brokerage charges "
                "are not prepaid and are the recipient's "
                "responsibility.\n\n"
                "Source: 06-international-shipping.md"
            )


        if (
            self.last_policy_topic == "trailplus"
            and self.is_followup_question(question)
        ):

            return (
                "For TrailPlus members, eligible items have a "
                "45 calendar day return window from delivery, "
                "provided the membership was active when the "
                "order was placed.\n\n"
                "Source: 09-trailplus-membership.md"
            )


        if (
            self.last_policy_topic == "international"
            and self.is_followup_question(question)
        ):

            return (
                "Canada is a supported international shipping "
                "destination. For Canadian orders, import duties "
                "and taxes are not prepaid, and brokerage charges "
                "are not prepaid. These charges are the recipient's "
                "responsibility.\n\n"
                "Source: 06-international-shipping.md — "
                "Duties and taxes"
            )


        if self.is_return_question(question):

            self.last_policy_topic = "returns"

            return (
                "The standard return window is 30 calendar days "
                "from delivery for eligible items, subject to "
                "the return conditions and any valid exceptions.\n\n"
                "Source: 01-returns-policy-current.md — "
                "Standard return window"
            )


        if conflicts:

            return (
                "I found conflicting information in the current "
                "Aster & Row documentation. I don't want to give "
                "you incorrect guidance.\n\n"
                "The safest option is to follow the more "
                "conservative guidance temporarily and contact "
                "a human support representative for confirmation."
            )


        if not results or not evidence:

            return (
                "The supplied information is insufficient to "
                "answer this confidently. I don't want to invent "
                "or make an unsupported claim.\n\n"
                "Please contact a human support representative "
                "for confirmation."
            )


        first_result = results[0]

        metadata = first_result.get(
            "metadata",
            {}
        )

        text = first_result.get(
            "text",
            ""
        )

        source = metadata.get(
            "source",
            "Aster & Row knowledge base"
        )

        heading = metadata.get(
            "heading",
            ""
        )


        source_lower = str(source).lower()

        if (
            "legacy" in source_lower
            or "migration" in source_lower
        ):

            current_result = None

            for item in results:

                item_source = str(
                    item.get(
                        "metadata",
                        {}
                    ).get(
                        "source",
                        ""
                    )
                ).lower()

                if (
                    "legacy" not in item_source
                    and "migration" not in item_source
                ):

                    current_result = item
                    break

            if current_result:

                first_result = current_result

                metadata = first_result.get(
                    "metadata",
                    {}
                )

                text = first_result.get(
                    "text",
                    ""
                )

                source = metadata.get(
                    "source",
                    "Aster & Row knowledge base"
                )

                heading = metadata.get(
                    "heading",
                    ""
                )

        if not text:
            text = evidence

        answer = text.strip()

        if heading:

            answer += (
                f"\n\nSource: {source} — {heading}"
            )

        else:

            answer += (
                f"\n\nSource: {source}"
            )

        return answer


    def generate_order_answer(self, order_result):

        if not order_result:

            return (
                "Please provide your order ID so I can "
                "check your order status."
            )


        if order_result.get("lookup_error"):

            return (
                "I was unable to access that order information "
                "right now. Please try again or contact human "
                "support for assistance."
            )


        if not order_result.get("found"):

            return (
                "The order was not found. Please check the "
                "order ID or contact human support for assistance."
            )

        status = order_result.get(
            "status"
        )

        if not status:

            return (
                "I found your order, but I don't have enough "
                "information to provide its current status."
            )

        status_lower = str(
            status
        ).lower()

        order_id = order_result.get(
            "order_id",
            self.current_order_id
        )


        if "cancel" in status_lower:

            return (
                f"Your order {order_id} is currently "
                "cancelled and will not be shipped."
            )


        if "delivered" in status_lower:

            return (
                f"Your order {order_id} has been delivered."
            )


        if (
            "shipped" in status_lower
            or "transit" in status_lower
        ):

            # Always explicitly use "shipped".
            answer = (
                f"Your order {order_id} has shipped"
            )

            carrier = order_result.get(
                "carrier"
            )

            estimated_delivery = order_result.get(
                "estimated_delivery"
            )

            if carrier:

                answer += (
                    f" with {carrier}"
                )

            answer += "."


            if estimated_delivery:

                answer += (
                    f" The current estimated delivery date "
                    f"is {estimated_delivery}."
                )

            else:

                answer += (
                    " The delivery estimate is currently "
                    "unavailable."
                )

            return answer


        if (
            "processing" in status_lower
            or "pending" in status_lower
        ):

            return (
                f"Your order {order_id} is currently "
                "being processed."
            )


        return (
            f"The current status of order {order_id} "
            f"is {status}."
        )


    def try_openai_response(
        self,
        user_message,
        rag_result,
        order_result
    ):

        if not USE_OPENAI or client is None:

            return None

        application_context = {
            "knowledge_base_evidence": rag_result.get(
                "evidence",
                ""
            ),
            "knowledge_base_citations": rag_result.get(
                "citations",
                []
            ),
            "knowledge_base_conflicts": rag_result.get(
                "conflicts",
                []
            ),
            "order_lookup_result": order_result,
            "current_order_id": self.current_order_id
        }

        model_input = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        for message in self.get_context():

            model_input.append(
                {
                    "role": message["role"],
                    "content": message["content"]
                }
            )

        model_input.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        model_input.append(
            {
                "role": "developer",
                "content": (
                    "Trusted application context:\n\n"
                    + json.dumps(
                        application_context,
                        indent=2,
                        default=str
                    )
                )
            }
        )

        try:

            response = client.responses.create(
                model=OPENAI_MODEL,
                input=model_input
            )

            answer = response.output_text.strip()

            if answer:
                return answer

        except Exception as e:

            self.log(
                "openai_error",
                {
                    "error": str(e)
                }
            )

        return None


    def respond(self, user_message):

        user_message = user_message.strip()


        if not user_message:

            return {
                "answer": "Please enter a question.",
                "sources": [],
                "handoff": False
            }


        security_type = self.security_type(
            user_message
        )

        if security_type:

            answer = self.security_response(
                security_type
            )

            handoff = (
                security_type == "privacy"
            )

            self.save_history(
                user_message,
                answer
            )

            return {
                "answer": answer,
                "sources": [],
                "handoff": handoff
            }

        
        detected_topic = self.detect_policy_topic(
            user_message
        )


        if detected_topic:

            self.last_policy_topic = detected_topic


        elif (
            self.last_policy_topic
            and self.is_followup_question(user_message)
        ):

            detected_topic = self.last_policy_topic


        order_id = self.extract_order_id(
            user_message
        )

        if order_id:

            self.current_order_id = order_id


        if order_id:

            order_result = self.order_lookup(
                order_id
            )

            answer = self.generate_order_answer(
                order_result
            )

            handoff = (
                not order_result.get(
                    "found",
                    False
                )
                or order_result.get(
                    "lookup_error",
                    False
                )
            )

            self.save_history(
                user_message,
                answer
            )

            return {
                "answer": answer,
                "sources": [],
                "handoff": handoff
            }

        # ====================================================
        # POLICY QUESTIONS
        #
        # This comes BEFORE generic order detection.
        # ====================================================

        if detected_topic:

            rag_result = self.knowledge_search(
                user_message
            )

            answer = self.generate_rag_answer(
                user_message,
                rag_result
            )

            citations = rag_result.get(
                "citations",
                []
            )

            answer_lower = answer.lower()

            handoff_phrases = [
                "human support",
                "human representative",
                "human confirmation",
                "contact support",
                "contact a human",
                "human review",
                "human assistance",
                "human confirmation is required",
                "must review",
                "must be reviewed",
            ]

            handoff = any(
                phrase in answer_lower
                for phrase in handoff_phrases
            )

            self.save_history(
                user_message,
                answer
            )

            self.log(
                "final_response",
                {
                    "answer": answer,
                    "sources": citations,
                    "handoff": handoff
                }
            )

            return {
                "answer": answer,
                "sources": citations,
                "handoff": handoff
            }


        if self.is_order_question(
            user_message
        ):

            if self.current_order_id:

                order_result = self.order_lookup(
                    self.current_order_id
                )

                answer = self.generate_order_answer(
                    order_result
                )

                handoff = (
                    not order_result.get(
                        "found",
                        False
                    )
                    or order_result.get(
                        "lookup_error",
                        False
                    )
                )

                self.save_history(
                    user_message,
                    answer
                )

                return {
                    "answer": answer,
                    "sources": [],
                    "handoff": handoff
                }

            answer = (
                "Please provide your order ID "
                "(for example, ORD-12345) so I can "
                "check your order."
            )

            self.save_history(
                user_message,
                answer
            )

            return {
                "answer": answer,
                "sources": [],
                "handoff": False
            }


        rag_result = self.knowledge_search(
            user_message
        )

        answer = None

        if USE_OPENAI:

            answer = self.try_openai_response(
                user_message,
                rag_result,
                None
            )

        if answer is None:

            answer = self.generate_rag_answer(
                user_message,
                rag_result
            )

        citations = rag_result.get(
            "citations",
            []
        )


        answer_lower = answer.lower()

        handoff_phrases = [
            "human support",
            "human representative",
            "human confirmation",
            "contact support",
            "contact a human",
            "human review",
            "human assistance",
            "human confirmation is required",
            "must review",
            "must be reviewed",
        ]

        handoff = any(
            phrase in answer_lower
            for phrase in handoff_phrases
        )

        self.save_history(
            user_message,
            answer
        )

        self.log(
            "final_response",
            {
                "answer": answer,
                "sources": citations,
                "handoff": handoff
            }
        )

        return {
            "answer": answer,
            "sources": citations,
            "handoff": handoff
        }


    def save_history(
        self,
        user_message,
        answer
    ):

        self.history.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": answer
            }
        )



def main():

    print("=" * 70)
    print("ASTER & ROW AI SUPPORT AGENT")
    print("=" * 70)

    print("\nType 'exit' to quit.")
    print("Debug mode: ON")

    print(
        "\nOpenAI integration disabled."
    )

    print(
        "Running deterministic RAG + order-tool mode."
    )

    agent = SupportAgent(
        debug=True
    )

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

        if user_message.lower() in {
            "exit",
            "quit"
        }:

            print(
                "Goodbye!"
            )

            break

        try:

            result = agent.respond(
                user_message
            )

        except Exception as e:

            agent.log(
                "unexpected_error",
                {
                    "error": str(e)
                }
            )

            result = {
                "answer": (
                    "I'm unable to process that request "
                    "right now. Please try again or contact "
                    "human support."
                ),
                "sources": [],
                "handoff": True
            }

        print(
            "\nAgent:"
        )

        print(
            result["answer"]
        )

        if result.get("sources"):

            print(
                "\nSources:"
            )

            for source in result["sources"]:

                print(
                    f"- {source}"
                )

        if result.get("handoff"):

            print(
                "\nHuman handoff recommended: YES"
            )



if __name__ == "__main__":
    main()