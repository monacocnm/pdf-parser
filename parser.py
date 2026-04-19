import fitz
import re
from collections import defaultdict, Counter


# =========================
# LIMPEZA
# =========================

def clean_text(text: str) -> str:
    text = text.upper()
    text = re.sub(r"\s+", " ", text)
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

    if len(name) < 4:
        return ""

    return name


# =========================
# EXTRAÇÃO BASE
# =========================

CODE_RE = re.compile(r'\b[A-Z]{1,3}\d?(?:-[A-Z0-9]+)+\b')
PRICE_RE = re.compile(r'R\$\s*([\d]+(?:,\d+)?)')
QTY_RE = re.compile(r'(\d+)\s*PC\s*/?\s*CX', re.IGNORECASE)


def build_product(codigo, nome, preco, quantidade):
    nome = clean_name(nome)
    if not codigo or not nome:
        return None

    return {
        "codigo": codigo,
        "nome": nome,
        "preco": preco if preco is not None else 0,
        "quantidade_caixa": quantidade
    }


# =========================
# MÉTODO A — parser atual
# =========================

def extract_method_a(doc):
    products = []

    for page in doc:
        text = page.get_text("text")
        lines = [clean_text(l) for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            code_match = CODE_RE.search(line)
            price_match = PRICE_RE.search(line)

            if code_match and price_match:
                codigo = code_match.group(0)
                preco = float(price_match.group(1).replace(",", "."))

                nome = ""
                quantidade = None

                if i + 1 < len(lines):
                    nome = lines[i + 1]

                if i + 2 < len(lines):
                    qty_match = QTY_RE.search(lines[i + 2])
                    if qty_match:
                        quantidade = int(qty_match.group(1))

                p = build_product(codigo, nome, preco, quantidade)
                if p:
                    products.append(p)

    return products


# =========================
# MÉTODO B — text linear
# =========================

def extract_method_text(doc):
    products = []

    for page in doc:
        text = page.get_text("text")
        chunks = text.split("\n")

        for i, line in enumerate(chunks):
            line = clean_text(line)

            code_match = CODE_RE.search(line)
            price_match = PRICE_RE.search(line)

            if code_match and price_match:
                codigo = code_match.group(0)
                preco = float(price_match.group(1).replace(",", "."))

                nome_parts = []
                quantidade = None

                for j in range(i + 1, min(i + 4, len(chunks))):
                    nxt = clean_text(chunks[j])

                    if CODE_RE.search(nxt) and PRICE_RE.search(nxt):
                        break

                    qty_match = QTY_RE.search(nxt)
                    if qty_match:
                        quantidade = int(qty_match.group(1))
                    else:
                        nome_parts.append(nxt)

                nome = " ".join(nome_parts)
                p = build_product(codigo, nome, preco, quantidade)
                if p:
                    products.append(p)

    return products


# =========================
# MÉTODO C — blocks
# =========================

def extract_method_blocks(doc):
    products = []

    for page in doc:
        blocks = page.get_text("blocks")
        parsed_blocks = []

        for b in blocks:
            x0, y0, x1, y1, text = b[:5]
            txt = clean_text(text)
            if not txt:
                continue

            parsed_blocks.append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": txt
            })

        parsed_blocks.sort(key=lambda x: (x["y0"], x["x0"]))

        for i, blk in enumerate(parsed_blocks):
            code_match = CODE_RE.search(blk["text"])
            price_match = PRICE_RE.search(blk["text"])

            if code_match and price_match:
                codigo = code_match.group(0)
                preco = float(price_match.group(1).replace(",", "."))

                nome_parts = []
                quantidade = None

                for other in parsed_blocks:
                    same_column = abs(other["x0"] - blk["x0"]) < 120
                    below = 0 < (other["y0"] - blk["y1"]) < 160

                    if same_column and below:
                        if CODE_RE.search(other["text"]) and PRICE_RE.search(other["text"]):
                            continue

                        qty_match = QTY_RE.search(other["text"])
                        if qty_match:
                            quantidade = int(qty_match.group(1))
                        else:
                            nome_parts.append(other["text"])

                nome = " ".join(nome_parts)
                p = build_product(codigo, nome, preco, quantidade)
                if p:
                    products.append(p)

    return products


# =========================
# CONSOLIDAÇÃO
# =========================

def score_name(name: str) -> int:
    if not name:
        return 0

    score = len(name)

    if re.search(r'\bPARA\b', name):
        score += 2
    if re.search(r'\bDE\b', name):
        score += 1
    if re.search(r'^[A-Z0-9\s]+$', name):
        score += 1
    if re.search(r'\bR\b|\bX\b', name):
        score -= 3

    return score

def choose_best_name(names):
    valid = [n for n in names if n and len(n) >= 4]
    if not valid:
        return ""

    valid = sorted(valid, key=score_name, reverse=True)
    return valid[0]

def choose_best_numeric(values):
    valid = [v for v in values if v not in (None, 0, 0.0)]
    if not valid:
        return None
    return Counter(valid).most_common(1)[0][0]

def consolidate_products(*lists_of_products):
    grouped = defaultdict(list)

    for lst in lists_of_products:
        for p in lst:
            grouped[p["codigo"]].append(p)

    final = []

    for codigo, items in grouped.items():
        nomes = [i["nome"] for i in items]
        precos = [i["preco"] for i in items]
        quantidades = [i["quantidade_caixa"] for i in items]

        nome_final = choose_best_name(nomes)
        preco_final = choose_best_numeric(precos)
        qtd_final = choose_best_numeric(quantidades)

        if nome_final:
            final.append({
                "codigo": codigo,
                "nome": nome_final,
                "preco": preco_final if preco_final is not None else 0,
                "quantidade_caixa": qtd_final
            })

    final.sort(key=lambda x: x["codigo"])
    return final


# =========================
# ORQUESTRADOR
# =========================

def parse_catalog_pdf(pdf_bytes: bytes):

    # método A
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_a = extract_method_a(doc)
    doc.close()

    # método B
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_b = extract_method_text(doc)
    doc.close()

    # método C
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_c = extract_method_blocks(doc)
    doc.close()

    final = consolidate_products(result_a, result_b, result_c)
    return final
