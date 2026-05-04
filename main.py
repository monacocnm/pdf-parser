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


# 🔥 Parser robusto de JSON da IA
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
    start_page: int = Query(1, description="Página inicial (começa em 1)"),
    max_pages: int = Query(1, description="Quantidade de páginas para processar")
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

        # 🔥 Controle de páginas
        start_index = max(start_page - 1, 0)
        end_index = min(start_index + min(max_pages, 5), total_pages)

        for page_index in range(start_index, end_index):
            page = doc[page_index]

            # 🔥 resolução balanceada
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            img_bytes = pix.tobytes("png")

            # 🔥 fallback se imagem ficar muito grande
            if len(img_bytes) > 800000:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                img_bytes = pix.tobytes("png")

            print(f"📄 Página {page_index+1} tamanho:", len(img_bytes))

            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            del img_bytes

            prompt = """
Você está analisando uma página de catálogo de produtos.

A página contém vários produtos organizados em blocos visuais (grade com colunas e linhas).

⚠️ REGRAS IMPORTANTES:

1. Cada produto deve ser extraído separadamente.
2. NÃO misture informações de produtos diferentes.
3. NÃO junte textos de blocos distintos.
4. Cada produto é um bloco independente com:
   - código
   - nome
   - preço
   - quantidade por caixa

---

### IDENTIFICAÇÃO DO PRODUTO

Cada produto normalmente segue este padrão visual:

- Código: formato como "Q-12", "W1-34-1", etc
- Nome: texto descritivo logo abaixo ou próximo da imagem
- Preço: valor com "R$"
- Quantidade: algo como "(100PC/CX)" ou "(30PC/CX)"

---

### REGRAS DE EXTRAÇÃO

✔ Nome do produto:
- NÃO incluir preço
- NÃO incluir código
- NÃO incluir quantidade
- NÃO incluir textos promocionais
- NÃO incluir símbolos estranhos

✔ Preço:
- extrair apenas número (ex: 8.00, 45.00)

✔ Quantidade:
- extrair apenas número (ex: 100, 30)

✔ Código:
- manter exatamente como aparece

---

### MUITO IMPORTANTE

❌ NÃO FAÇA ISSO:
- "Produto1 Produto2 Produto3" (misturado)
- incluir "R$" no nome
- incluir partes de outro produto

✔ CADA ITEM DEVE SER ISOLADO

---

### FORMATO DE SAÍDA (OBRIGATÓRIO)

Retorne apenas JSON válido:

[
  {
    "codigo": "string",
    "nome": "string",
    "preco": number,
    "quantidade_caixa": number
  }
]

---

### VALIDAÇÃO

Se um produto estiver incompleto ou confuso:
→ IGNORE esse produto

Qualidade é mais importante que quantidade.
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
