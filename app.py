import streamlit as st
from agent import SupportAgent


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Aster & Row AI Support",
    page_icon="🤖",
    layout="centered"
)


# ============================================================
# SESSION STATE
# ============================================================

# Create the actual SupportAgent only once.
# This preserves conversation context across Streamlit reruns.
if "agent" not in st.session_state:
    st.session_state.agent = SupportAgent(debug=True)


# Store messages that should be displayed in the GUI.
if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("⚙️ Aster & Row")

    st.write("AI Customer Support Agent")

    st.divider()

    st.subheader("Agent Status")

    st.success("🟢 Online")

    st.divider()

    # --------------------------------------------------------
    # CLEAR CONVERSATION
    # --------------------------------------------------------

    if st.button(
        "🗑️ Clear Conversation",
        use_container_width=True
    ):

        # Clear displayed conversation
        st.session_state.messages = []

        # Create a fresh agent so its internal history
        # is also cleared.
        st.session_state.agent = SupportAgent(
            debug=True
        )

        st.rerun()

    st.divider()

    st.caption(
        "Reliable RAG Support Agent"
    )

    st.caption(
        "Aster & Row Assignment Demo"
    )


# ============================================================
# MAIN HEADER
# ============================================================

st.title("🤖 Aster & Row AI Support")

st.caption(
    "Reliable RAG-powered customer support"
)


# ============================================================
# WELCOME MESSAGE
# ============================================================

if len(st.session_state.messages) == 0:

    st.info(
        "👋 Hello! I'm the Aster & Row support assistant.\n\n"
        "You can ask me about:\n"
        "- Returns and refunds\n"
        "- Shipping\n"
        "- Products\n"
        "- Warranty\n"
        "- Order status"
    )


# ============================================================
# DISPLAY PREVIOUS CONVERSATION
# ============================================================

for message in st.session_state.messages:

    role = message["role"]

    with st.chat_message(role):

        # Display message
        st.markdown(
            message["content"]
        )

        # ----------------------------------------------------
        # SOURCES
        # ----------------------------------------------------

        if role == "assistant":

            sources = message.get(
                "sources",
                []
            )

            if sources:

                with st.expander(
                    "📚 Sources"
                ):

                    for source in sources:

                        st.write(
                            f"• {source}"
                        )

            # ------------------------------------------------
            # HUMAN HANDOFF
            # ------------------------------------------------

            handoff = message.get(
                "handoff",
                False
            )

            if handoff:

                st.warning(
                    "👤 Human handoff recommended"
                )

            else:

                st.caption(
                    "👤 Human handoff: No"
                )


# ============================================================
# CHAT INPUT
# ============================================================

user_input = st.chat_input(
    "Ask Aster & Row something..."
)


# ============================================================
# PROCESS USER MESSAGE
# ============================================================

if user_input:

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )


    # --------------------------------------------------------
    # DISPLAY USER MESSAGE
    # --------------------------------------------------------

    with st.chat_message("user"):

        st.markdown(
            user_input
        )


    # --------------------------------------------------------
    # GENERATE ASSISTANT RESPONSE
    # --------------------------------------------------------

    with st.chat_message("assistant"):

        with st.spinner(
            "Searching knowledge base..."
        ):

            try:

                # ==================================================
                # IMPORTANT:
                # Your agent.py contains SupportAgent.respond()
                # NOT agent.invoke()
                # ==================================================

                result = (
                    st.session_state.agent.respond(
                        user_input
                    )
                )


                # ==================================================
                # HANDLE AGENT RESULT
                # ==================================================

                if isinstance(result, dict):

                    answer = (
                        result.get("answer")
                        or result.get("response")
                        or result.get("output")
                        or "I couldn't generate a response."
                    )

                    sources = result.get(
                        "sources",
                        []
                    )

                    handoff = result.get(
                        "handoff",
                        False
                    )

                else:

                    # Safety fallback if the agent returns
                    # a plain string.
                    answer = str(result)

                    sources = []

                    handoff = False


                # ==================================================
                # DISPLAY ANSWER
                # ==================================================

                st.markdown(
                    answer
                )


                # ==================================================
                # DISPLAY SOURCES
                # ==================================================

                if sources:

                    with st.expander(
                        "📚 Sources"
                    ):

                        for source in sources:

                            st.write(
                                f"• {source}"
                            )


                # ==================================================
                # DISPLAY HUMAN HANDOFF
                # ==================================================

                if handoff:

                    st.warning(
                        "👤 Human handoff recommended"
                    )

                else:

                    st.caption(
                        "👤 Human handoff: No"
                    )


                # ==================================================
                # SAVE ASSISTANT RESPONSE
                # ==================================================

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": sources,
                        "handoff": handoff
                    }
                )


            # ======================================================
            # ERROR HANDLING
            # ======================================================

            except Exception as e:

                error_message = (
                    "Sorry, I encountered an error while "
                    "processing your request. Please try again "
                    "or contact human support."
                )


                # Display safe customer-facing message
                st.error(
                    error_message
                )


                # Save error response
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": error_message,
                        "sources": [],
                        "handoff": True
                    }
                )


                # ------------------------------------------------
                # DEBUG INFORMATION
                # ------------------------------------------------

                with st.expander(
                    "🔧 Debug information"
                ):

                    st.code(
                        str(e)
                    )