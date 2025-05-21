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
            "content": f"Here is the documentation content:\n{doc_content}\n\nSummarize the latest documentation changes."
        },
        {"role": "user", "content": "Summarize the latest code changes in this PR and if needed, update the documentation to reflect those changes. Respond with the completely updated documentation, but restrict your response to that."}
    ]
)

print(response.choices[0].message.content)