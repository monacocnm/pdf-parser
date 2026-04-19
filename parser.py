import fitz
import re

CODE_RE = re.compile(r'\b([A-Z]{1,3}\d?(?:-[A-Z0-9]+)+|[A-Z]{1,3}-\d+(?:-\d+)*)\b')
PRICE_RE = re.compile(r'R\$\s*(\d+(?:,\d{1,2})?)')
QTY_RE = re.compile(r'(\d{1,4})\s*PC\s*/?\s*CX', re.IGNORECASE)

IGNORE_PREFIXES = (
    "OBS", "PEDIDOS", "IMAGENS", "NÚMEROS", "THOR", "CONSULTAR",
    "PRODUTOS SUJEITOS", "O SITE", "RUA", "VALORES"
)

def clean_text(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_ignored(text: str) -> bool:
    upper = clean_text(text).upper()
    return any(upper.startswith(p) for p in IGNORE_PREFIXES)

def clean_name(name: str) -> str:
    name = clean_text(name)

    # remove preços dentro do nome
    name = re.sub(r'\b\d+\s*,\s*\d+\b', '', name)

    # remove códigos misturados no nome
    name = re.sub(r'\b[A-Z]{1,3}\d?(?:-[A-Z0-9]+)+\b', '', name)

    # remove lixo comum
    name = re.sub(r'[,$()]', '', name)
    name = re.sub(r'\bPC\s*/?\s*CX\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCX\b', '', name, flags=re.IGNORECASE)

    # normaliza espaços
    name = re.sub(r'\s+', ' ', name).strip()

    # descarta nomes inválidos
    if len(name) < 5:
        return ""

    if re.fullmatch(r'[\d\s,\.]+', name):
        return ""

    return name

def extract_products(pdf_path):
    doc = fitz.open(pdf_path)
    products = []

    for page in doc:
        blocks = page.get_text("blocks")
        page_items = []

        for b in blocks:
            x0, y0, x1, y1, text = b[:5]
            text = clean_text(text)

            if not text or is_ignored(text):
                continue

            code_match = CODE_RE.search(text)
            price_match = PRICE_RE.search(text)
            qty_match = QTY_RE.search(text)

            if code_match or price_match or qty_match:
                page_items.append({
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "text": text,
                    "code": code_match.group(1) if code_match else None,
                    "price": float(price_match.group(1).replace(",", ".")) if price_match else None,
                    "qty": int(qty_match.group(1)) if qty_match else None,
                })

        page_items.sort(key=lambda i: (round(i["y0"] / 20), i["x0"]))

        used = set()

        for i, item in enumerate(page_items):
            if i in used:
                continue

            code = item["code"]
            price = item["price"]
            qty = item["qty"]
            name_parts = []

            if not code or price is None:
                continue

            for j, other in enumerate(page_items):
                if j == i or j in used:
                    continue

                same_column = abs(other["x0"] - item["x0"]) < 120
                below = 0 < (other["y0"] - item["y1"]) < 140

                if same_column and below:
                    if other["code"] and other["price"] is not None:
                        continue

                    if other["qty"] is not None and qty is None:
                        qty = other["qty"]
                        used.add(j)
                        continue

                    txt = other["text"]
                    if "R$" not in txt and "PC/CX" not in txt.upper():
                        name_parts.append(txt)
                        used.add(j)

            name = clean_name(" ".join(name_parts))

            # fallback: tenta extrair nome do próprio bloco
            if not name:
                temp = item["text"]
                temp = temp.replace(code, "")
                temp = re.sub(r'R\$\s*\d+(?:,\d{1,2})?', "", temp)
                temp = re.sub(r'\bCX\b', "", temp, flags=re.IGNORECASE)
                name = clean_name(temp)

            if code and price is not None and name:
                products.append({
                    "codigo": code,
                    "nome": name,
                    "preco": price,
                    "quantidade_caixa": qty
                })

            used.add(i)

    # remove duplicados por código, mantendo o mais completo
    dedup = {}
    for p in products:
        code = p["codigo"]
        score = len(p["nome"]) + (10 if p["quantidade_caixa"] else 0)
        if code not in dedup or score > dedup[code]["_score"]:
            dedup[code] = {**p, "_score": score}

    final_products = []
    for v in dedup.values():
        v.pop("_score", None)
        final_products.append(v)

    return final_products
