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
    text = text.replace("\n", " ").replace("  ", " ").strip()
    return re.sub(r"\s+", " ", text)

def is_ignored(text: str) -> bool:
    upper = clean_text(text).upper()
    return any(upper.startswith(p) for p in IGNORE_PREFIXES)

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

            # bloco candidato: precisa ter preço ou quantidade ou código
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

        # ordena por posição visual
        page_items.sort(key=lambda i: (round(i["y0"] / 20), i["x0"]))

        used = set()

        for i, item in enumerate(page_items):
            if i in used:
                continue

            code = item["code"]
            price = item["price"]
            qty = item["qty"]
            name_parts = []

            # só inicia produto se tiver código e preço no mesmo bloco
            if not code or price is None:
                continue

            # procurar blocos próximos abaixo para nome e quantidade
            for j, other in enumerate(page_items):
                if j == i or j in used:
                    continue

                same_column = abs(other["x0"] - item["x0"]) < 120
                below = 0 < (other["y0"] - item["y1"]) < 140

                if same_column and below:
                    # se encontrou outro código+preço, é outro produto
                    if other["code"] and other["price"] is not None:
                        continue

                    if other["qty"] is not None and qty is None:
                        qty = other["qty"]
                        used.add(j)
                        continue

                    # texto de nome
                    txt = other["text"]
                    if "R$" not in txt and "PC/CX" not in txt.upper():
                        name_parts.append(txt)
                        used.add(j)

            name = clean_text(" ".join(name_parts))

            # limpeza de sujeira no nome
            name = re.sub(r'\d+\s*,\s*\d+', '', name)  # remove "8 ,00"
            name = re.sub(r'[,$]', '', name)           # remove lixo
            name = name.strip()

            # descartar nomes ruins
            if len(name) < 4 or name.replace(" ", "").isdigit():
                name = ""
            # fallback: tentar extrair nome do próprio bloco removendo código/preço
            if not name:
                temp = item["text"]
                temp = temp.replace(code, "")
                temp = re.sub(r'R\$\s*\d+(?:,\d{1,2})?', "", temp)
                temp = re.sub(r'CX', "", temp, flags=re.IGNORECASE)
                temp = clean_text(temp)
                if len(temp.split()) >= 2:
                    name = temp

            # filtro final
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
