import streamlit as st

from src.rag import ask

st.set_page_config(
    page_title="Finsight",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Finsight")
st.caption("AI Financial Analyst")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if "sources" in message:
            with st.expander("Sources"):
                for source in message["sources"]:
                    st.write(
                        f"📄 {source['source']} | "
                        f"{source.get('company', 'unknown')} "
                        f"{source.get('period', '')}"
                    )

# User input
question = st.chat_input(
    "Ask about your financial documents..."
)

if question:
    # Show user message
    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):
        st.markdown(question)

    # Generate answer
    with st.chat_message("assistant"):
        with st.spinner("Analyzing documents..."):
            answer, sources = ask(question)

        st.markdown(answer)

        with st.expander("Sources"):
            for source in sources:
                st.write(
                    f"📄 {source['source']} | "
                    f"{source.get('company', 'unknown')} "
                    f"{source.get('period', '')}"
                )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
        }
    )