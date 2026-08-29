"""
Script sederhana untuk test koneksi ke watsonx.ai (model Granite).
Jalankan: python test_watsonx_connection.py

Pastikan .env sudah berisi:
WATSONX_API_KEY=...
WATSONX_PROJECT_ID=...
WATSONX_URL=https://us-south.ml.cloud.ibm.com
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("WATSONX_API_KEY")
PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
URL = os.getenv("WATSONX_URL")

MODEL_ID = os.getenv("MODEL_ID")


def main():
    missing = [name for name, val in [
        ("WATSONX_API_KEY", API_KEY),
        ("WATSONX_PROJECT_ID", PROJECT_ID),
        ("WATSONX_URL", URL),
    ] if not val]

    if missing:
        print(f"❌ Environment variable belum lengkap di .env: {', '.join(missing)}")
        sys.exit(1)

    print(f"URL      : {URL}")
    print(f"Project  : {PROJECT_ID}")
    print(f"Model    : {MODEL_ID}")
    print("Mengirim test prompt ke Granite...\n")

    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        credentials = Credentials(url=URL, api_key=API_KEY)

        model = ModelInference(
            model_id=MODEL_ID,
            credentials=credentials,
            project_id=PROJECT_ID,
            params={"max_new_tokens": 50},
        )

        response = model.generate_text(
            "Jawab dalam satu kalimat pendek: apa itu Home Assistant?"
        )

        print("✅ Koneksi berhasil!")
        print(f"Response dari Granite: {response}")

    except Exception as e:
        print(f"❌ Koneksi GAGAL: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()