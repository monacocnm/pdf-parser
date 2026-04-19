from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import traceback
from parser import extract_products

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.post("/parse-catalog")
async def parse_catalog(file: UploadFile = File(...)):
    try:
        path = f"/tmp/{file.filename}"

        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        products = extract_products(path)
        return products

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "trace": traceback.format_exc()
            }
        )
