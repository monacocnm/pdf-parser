from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from parser import parse_catalog_pdf

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

import fitz  # PyMuPDF

@app.post("/parse-catalog-vision")
async def parse_catalog_vision(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        pages_info = []

        for i, page in enumerate(doc):
            text = page.get_text("text")

            pages_info.append({
                "page": i + 1,
                "chars": len(text),
                "preview": text[:200]  # só preview
            })

        return {
            "status": "ok",
            "pages": len(pages_info),
            "debug": pages_info[:3]  # só primeiras páginas
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
