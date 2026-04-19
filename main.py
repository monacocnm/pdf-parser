from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import re

app = FastAPI()

# ✅ CORS liberado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# FUNÇÕES DE LIMPEZA
# =========================

def clean_text(text: str) -> str:
    text = text.upper()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_name(name: str) -> str:
    name = clean_text(name)

    name = re.sub(r'\b\d+\s*,\s*\d+\b', '', name)
    name = re.sub(r'\b[A-Z]{1,3}\d?(?:-[A-Z0-9]+)+\b', '', name)
    name = re.sub(r'\b\d+\s*PC\s*/?\s*CX\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b\d+\s*PC/?\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCX\b', '', name, flags=re.IGNORECASE)

    name = re.sub(r'^[\d\s,\.]+', '', name)
    name = re.sub(r'[\d\s,\.]+$', '', name)

    name = re.sub(r'[,$()/]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    if len(name) < 5:
        return ""

    if re.fullmatch(r'[\d\s,\.]+', name):
        return ""

    return name


def extract_products(text):
    products = []

    pattern = re.compile(
        r'([A-Z0-9\-]+)\s+CX\s*R\$\s*([\d,]+)\s+(.*?)\s*\((\d+)\s*PC\/CX\)',
        re.DOTALL
    )

    matches = pattern.findall(text)

    for m in matches:
        codigo = m[0].strip()
        preco = float(m[1].replace(",", "."))
        nome = clean_name(m[2])
        quantidade = int(m[3])

        if not nome:
            continue

        products.append({
            "codigo": codigo,
            "nome": nome,
            "preco": preco,
            "quantidade_caixa": quantidade
        })

    return products


# =========================
# ROTAS
# =========================

@app.get("/")
def home():
    return {"message": "pdf-parser is live!"}


@app.post("/parse-catalog")
async def parse_catalog(file: UploadFile = File(...)):
    contents = await file.read()

    doc = fitz.open(stream=contents, filetype="pdf")

    full_text = ""

    for page in doc:
        full_text += page.get_text("text") + "\n"

    products = extract_products(full_text)

    return products
