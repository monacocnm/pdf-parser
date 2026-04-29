from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from parser import parse_catalog_pdf

import os
import json
import base64
import fitz
import requests


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "pdf-parser is live!"}


@app.post("/parse-catalog")
async def parse_catalog(file: UploadFile = File(...)):
    contents = await file.read()
    result = parse_catalog_pdf(contents)
    return result


def limpar_json_ia(texto: str):
    if not texto:
        return []

    texto = texto.strip()

    if texto.startswith("```json"):
        texto = texto.replace("```json", "").replace("```", "").strip()

    if texto.startswith("```"):
        texto = texto.replace("```", "").strip()

    try:
        data = json.loads(texto)
    except Exception:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "produtos" in data:
        return data["produtos"]

    return []


@app.post("/parse-catalog-vision")
async def parse_catalog_vision(
    file: UploadFile = File(...),
    max_pages: int = Query(0, description="0 = processar todas as páginas")
):
    try:
        openai_key = os.getenv("OPENAI_API_KEY")

        if not openai_key:
            return {
                "status": "error",
                "message": "OPENAI_API_KEY não configurada no Render"
            }

        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        produtos_finais = []

        total_pages = len(doc)
        pages_to_process = total_pages if max_pages == 0 else min(max_pages, total_pages)

        for page_index in range(pages_to_process):
            page = doc[page_index]

            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            prompt = """
Extraia os produtos desta imagem de catálogo.

Cada produto normalmente possui:
- código
- preço
- nome
- quantidade por caixa

Retorne APENAS JSON válido neste formato:

{
  "produtos": [
    {
      "codigo": "Q-12-1",
      "nome": "Coleira guia refletiva",
      "preco": 8,
      "quantidade_caixa": 360
    }
  ]
}

Regras:
- Não invente produtos.
- Se não encontrar código, ignore o item.
- Preço deve ser número.
- Quantidade por caixa deve ser número inteiro.
- Remova "CX", "R$", "PC/CX" do nome.
- Preserve nomes comerciais limpos.
"""

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "temperature": 0
                },
                timeout=120
            )

            if response.status_code != 200:
                produtos_finais.append({
                    "erro_pagina": page_index + 1,
                    "status_code": response.status_code,
                    "detalhe": response.text
                })
                continue

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            produtos_pagina = limpar_json_ia(content)

            for produto in produtos_pagina:
                if not isinstance(produto, dict):
                    continue

                codigo = produto.get("codigo")
                nome = produto.get("nome")

                if not codigo or not nome:
                    continue

                produtos_finais.append({
                    "codigo": str(codigo).strip(),
                    "nome": str(nome).strip(),
                    "preco": produto.get("preco", 0),
                    "quantidade_caixa": produto.get("quantidade_caixa")
                })

        doc.close()

        return produtos_finais

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
