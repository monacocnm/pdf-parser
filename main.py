from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from parser import parse_catalog_pdf

import os
import json
import base64
import fitz
import requests
import gc


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


# 🔥 Parser robusto
def limpar_json_ia(texto: str):
    if not texto:
        return []

    texto = texto.strip()

    inicio = texto.find("{")
    fim = texto.rfind("}")

    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim+1]

    try:
        data = json.loads(texto)
    except Exception:
        print("❌ ERRO AO PARSEAR JSON:", texto)
        return []

    if isinstance(data, dict) and "produtos" in data:
        return data["produtos"]

    return []


@app.post("/parse-catalog-vision")
async def parse_catalog_vision(
    file: UploadFile = File(...),
    start_page: int = Query(1),
    max_pages: int = Query(1)
):
    try:
        openai_key = os.getenv("OPENAI_API_KEY")

        if not openai_key:
            return {"status": "error", "message": "API KEY não configurada"}

        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        produtos_finais = []

        total_pages = len(doc)

        start_index = max(start_page - 1, 0)
        end_index = min(start_index + max_pages, total_pages)

        for page_index in range(start_index, end_index):
            page = doc[page_index]

            page_rect = page.rect
            width = page_rect.width
            height = page_rect.height

            cols = 3
            rows = 2

            block_width = width / cols
            block_height = height / rows

            for row in range(rows):
                for col in range(cols):

                    rect = fitz.Rect(
                        col * block_width,
                        row * block_height,
                        (col + 1) * block_width,
                        (row + 1) * block_height
                    )

                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(1.5, 1.5),
                        clip=rect,
                        alpha=False
                    )

                    img_bytes = pix.tobytes("png")

                    # 🔥 ignora bloco vazio
                    if len(img_bytes) < 20000:
                        continue

                    print(f"📦 Página {page_index+1} bloco {row}-{col} tamanho:", len(img_bytes))

                    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                    del img_bytes

                    prompt = """
Você está analisando UM ÚNICO produto de catálogo.

⚠️ IMPORTANTE:
Esta imagem contém apenas um produto (ou pode estar vazia).

Extraia apenas se existir produto claro.

Retorne JSON:

{
  "produtos": [
    {
      "codigo": "string",
      "nome": "string",
      "preco": number,
      "quantidade_caixa": number
    }
  ]
}

REGRAS:
- NÃO misturar produtos
- NÃO inventar dados
- Se não tiver produto claro → retornar vazio
- Nome deve ser limpo (sem preço, código ou quantidade)
"""

                    response = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {openai_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "gpt-4o",
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

                    del img_base64
                    del pix
                    gc.collect()

                    if response.status_code != 200:
                        print("❌ ERRO OPENAI:", response.text)
                        continue

                    data = response.json()
                    content = data["choices"][0]["message"]["content"]

                    print("🧠 RESPOSTA IA:", content)

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
        gc.collect()

        return produtos_finais

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
