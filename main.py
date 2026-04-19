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
