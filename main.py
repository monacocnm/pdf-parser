from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from parser import parse_catalog_pdf

import os
import json
import base64
import fitz
import requests
import gc
import re


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
    return parse_catalog_pdf(contents)


def limpar_json_ia(texto: str):
    if not texto:
        return []

    texto = texto.strip()
    inicio = texto.find("{")
    fim = texto.rfind("}")

    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim + 1]

    try:
        data = json.loads(texto)
    except Exception:
        print("ERRO JSON IA:", texto)
        return []

    if isinstance(data, dict) and "produtos" in data:
        return data["produtos"]

    if isinstance(data, list):
        return data

    return []


def normalizar_preco(valor):
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor)
    texto = texto.replace("R$", "").replace(" ", "")
    texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return None


def normalizar_quantidade(valor):
    if valor is None:
        return None

    if isinstance(valor, int):
        return valor

    texto = str(valor)
    nums = re.findall(r"\d+", texto)

    if not nums:
        return None

    return int(nums[0])


def normalizar_nome(nome: str):
    if not nome:
        return ""

    nome = str(nome).strip()
    nome = re.sub(r"\s+", " ", nome)

    correcoes = {
        "pivot": "bivolt",
        "proyector": "projetor",
        "projeyor": "projetor",
        "bluetooh": "bluetooth",
        "portatil": "portátil",
        "cotoveloeira": "cotoveleira",
    }

    texto = nome.lower()

    for errado, certo in correcoes.items():
        texto = texto.replace(errado, certo)

    return texto.title()


def produto_valido(produto, ignorar_lista):
    codigo = str(produto.get("codigo", "")).strip()
    nome = str(produto.get("nome", "")).strip()
    preco = normalizar_preco(produto.get("preco"))
    quantidade = normalizar_quantidade(produto.get("quantidade_caixa"))

    if not codigo or not nome:
        return None

    texto_check = f"{codigo} {nome}".lower()

    for palavra in ignorar_lista:
        if palavra and palavra.lower().strip() in texto_check:
            return None

    if preco is None or preco <= 0:
        return None

    if quantidade is None or quantidade <= 0:
        return None

    return {
        "codigo": codigo,
        "nome": normalizar_nome(nome),
        "preco": preco,
        "quantidade_caixa": quantidade,
    }


def chamar_ia(openai_key: str, img_base64: str, modo_bloco: bool):
    if modo_bloco:
        contexto = "A imagem contém UM ÚNICO bloco de produto, ou pode estar vazia."
    else:
        contexto = "A imagem contém uma página inteira de catálogo com vários produtos."

    prompt = f"""
Você está analisando catálogo de produtos.

{contexto}

Extraia produtos com:
- código
- nome
- preço
- quantidade por caixa

Retorne APENAS JSON válido neste formato:

{{
  "produtos": [
    {{
      "codigo": "YA24014",
      "nome": "Bola Yoga com Bomba",
      "preco": 30,
      "quantidade_caixa": 50
    }}
  ]
}}

REGRAS:
- Não invente produtos.
- Não misture produtos diferentes.
- Ignore cabeçalhos, categorias e textos promocionais.
- Ignore itens sem preço.
- Ignore itens marcados apenas como reposição.
- O nome não deve conter código, preço, CX ou quantidade.
- Preço deve ser número.
- Quantidade deve ser número inteiro.
"""

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json",
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
                            },
                        },
                    ],
                }
            ],
            "temperature": 0,
        },
        timeout=120,
    )

    if response.status_code != 200:
        print("ERRO OPENAI:", response.text)
        return []

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    print("RESPOSTA IA:", content)

    return limpar_json_ia(content)


@app.post("/parse-catalog-vision")
async def parse_catalog_vision(
    file: UploadFile = File(...),

    start_page: int = Query(1),
    max_pages: int = Query(1),

    layout: str = Query("blocos"),
    colunas: int = Query(3),
    linhas: int = Query(2),

    top_crop_pct: float = Query(0.0),
    bottom_crop_pct: float = Query(0.0),

    ignorar_palavras: str = Query("reposicao,reposição,novidades,categoria")
):
    try:
        openai_key = os.getenv("OPENAI_API_KEY")

        if not openai_key:
            return {
                "status": "error",
                "message": "OPENAI_API_KEY não configurada no Render",
            }

        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        total_pages = len(doc)

        start_index = max(start_page - 1, 0)
        end_index = min(start_index + max_pages, total_pages)

        ignorar_lista = [
            p.strip().lower()
            for p in ignorar_palavras.split(",")
            if p.strip()
        ]

        produtos_por_codigo = {}

        for page_index in range(start_index, end_index):
            page = doc[page_index]
            page_rect = page.rect

            usable_y0 = page_rect.y0 + (page_rect.height * top_crop_pct)
            usable_y1 = page_rect.y1 - (page_rect.height * bottom_crop_pct)

            usable_rect = fitz.Rect(
                page_rect.x0,
                usable_y0,
                page_rect.x1,
                usable_y1,
            )

            print(f"Processando página {page_index + 1} layout={layout}")

            if layout == "pagina_inteira":
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(1.5, 1.5),
                    clip=usable_rect,
                    alpha=False,
                )

                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                del img_bytes

                produtos_ia = chamar_ia(
                    openai_key=openai_key,
                    img_base64=img_base64,
                    modo_bloco=False,
                )

                del img_base64
                del pix
                gc.collect()

                for item in produtos_ia:
                    produto = produto_valido(item, ignorar_lista)
                    if produto:
                        produtos_por_codigo[produto["codigo"]] = produto

            else:
                block_width = usable_rect.width / colunas
                block_height = usable_rect.height / linhas

                for row in range(linhas):
                    for col in range(colunas):
                        rect = fitz.Rect(
                            usable_rect.x0 + col * block_width,
                            usable_rect.y0 + row * block_height,
                            usable_rect.x0 + (col + 1) * block_width,
                            usable_rect.y0 + (row + 1) * block_height,
                        )

                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(1.5, 1.5),
                            clip=rect,
                            alpha=False,
                        )

                        img_bytes = pix.tobytes("png")

                        if len(img_bytes) < 15000:
                            del img_bytes
                            del pix
                            continue

                        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                        del img_bytes

                        produtos_ia = chamar_ia(
                            openai_key=openai_key,
                            img_base64=img_base64,
                            modo_bloco=True,
                        )

                        del img_base64
                        del pix
                        gc.collect()

                        for item in produtos_ia:
                            produto = produto_valido(item, ignorar_lista)
                            if produto:
                                produtos_por_codigo[produto["codigo"]] = produto

        doc.close()
        gc.collect()

        return list(produtos_por_codigo.values())

    except Exception as e:
        print("ERRO GERAL:", str(e))
        return {
            "status": "error",
            "message": str(e),
        }
