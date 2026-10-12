# high_level_api.py
import os
import requests

BASE_URL = os.getenv("VLM_BASE_URL")  # University-hosted Qwen VLM endpoint (VPN only)

def generate(prompt: str, reasoning: bool = False) -> str:
    response = requests.post(f"{BASE_URL}/generate", data={"prompt": prompt, "reasoning": reasoning})
    return response.json().get("result", "No result returned")

def generate_vision(prompt: str, image_path: str, fast: bool = False) -> str:
    with open(image_path, "rb") as img:
        files = {"file": img}
        data = {"prompt": prompt, "fast": str(fast).lower()}
        response = requests.post(f"{BASE_URL}/generate_vision", data=data, files=files)
    return response.json().get("result", "No result returned")


prompt = "Analyze the image and describe its contents in detail."
prompt2 = "Analyze the image and count the number of each product. Provide the result in a JSON format."
prompt3 = """Your task is to act as a meticulous data entry specialist for a hardware store inventory. Analyze the provided image of a plumbing parts aisle and extract the product information.

First, identify the different categories of products visible on the shelves (e.g., Brass Fittings, Faucet Cartridges).

For each distinct product you can clearly identify, extract the following details:
- description: The name or description of the product from its packaging.
- price: The price listed on the white tag for that item. Extract it as a string.
- type: The specific type of part (e.g., 'Adapter', 'Elbow', 'Connector', 'Cap', 'Cartridge').
Next, analyze the informational sign at the bottom of the image. Extract its main title and the different types of mechanisms it illustrates.

Finally, structure all of this information into a single JSON object using the precise schema below. If a piece of information for a product is not legible or visible, omit the key."""

image_path = "images/IMG_0434.jpeg"
image_path2 = "images/IMG_0436.jpeg"
print(generate_vision(prompt3, image_path2, fast=False))
