Aster & Row AI Support Agent

An AI-powered customer support agent for Aster & Row that answers customer queries using the provided knowledge base and handles order-related requests through an order lookup tool.

Features
Knowledge-base powered customer support
Return and warranty policy assistance
International shipping information
TrailPlus membership support
Order status and shipping lookup
Source conflict handling
Human handoff when required
Automated evaluation and regression testing
Tech Stack
Python
RAG (Retrieval-Augmented Generation)
OpenAI API
JSON
Markdown
Setup

Install the required dependencies:

pip install -r requirements.txt

Create a .env file in the project root:

OPENAI_API_KEY=your_api_key

Do not commit the .env file or expose your API key.

Run
python agent.py
Evaluation
python evaluation/test_agent.py

The evaluation suite covers retrieval, order-tool usage, multi-turn conversations, prompt security, privacy, source conflicts, abstention, and human handoff.

Evaluation Results

Overall Score: 52.2%

Visible Cases: 5/15 passed

Original Regression Cases: 7/8 passed

Known Limitations
The agent can only answer questions supported by the available knowledge base.
Some requests may require human support when sufficient information is unavailable.
Conflicting official information may require human confirmation.
Order-related responses depend on the available order lookup tool and data.
Demo

## Demo

## Demo

[Watch the Agent Demo](https://github.com/reet-cell/ai-agent-intern-test-main/blob/main/demo.mp4)
