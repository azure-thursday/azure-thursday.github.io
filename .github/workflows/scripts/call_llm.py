import os
import openai

with open("docs/documentation.md", "r", encoding="utf-8") as f:
    doc_content = f.read()

client = openai.AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version="2024-02-15-preview",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
)

response = client.chat.completions.create(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": f"Here is the documentation content:\n{doc_content}\n\nSummarize the latest documentation changes. If needed, update the documentation to reflect the latest code changes in this PR. Respond with the completely updated documentation, and nothing else."
        }
    ]
)

# Write the LLM's response to docs/documentation.md
with open("docs/documentation.md", "w", encoding="utf-8") as f:
    f.write(response.choices[0].message.content)

print("Documentation updated.")