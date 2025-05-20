import openai
import os

openai.api_type = "azure"
openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT"]  # e.g., "https://<your-resource-name>.openai.azure.com/"
openai.api_version = "2024-02-15-preview"  # Use the API version your deployment supports
openai.api_key = os.environ["AZURE_OPENAI_KEY"]

response = openai.ChatCompletion.create(
    engine=os.environ["AZURE_OPENAI_DEPLOYMENT"],  # The deployment name you created in Azure
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Summarize the latest documentation changes."}
    ]
)
print(response.choices[0].message["content"])