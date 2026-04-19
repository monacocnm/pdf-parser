from fastapi import FastAPI, UploadFile, File
import shutil
from parser import extract_products

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.post("/parse-catalog")
async def parse_catalog(file: UploadFile = File(...)):
    path = f"/tmp/{file.filename}"

    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    products = extract_products(path)

    return products
