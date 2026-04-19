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

    name = re.sub(r'[,$()/\*\-]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = clean_name(name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def is_valid_name(name: str) -> bool:
    if not name:
        return False

    words = [w for w in name.split() if w]

    if len(words) < 2:
        return False

    if len(name) < 10:
        return False

    bad_words = {"DE", "PARA", "COM", "SEM", "E", "EM", "A", "O", "DA", "DO"}
    if all(w in bad_words for w in words):
        return False

    if words[-1] in bad_words:
        return False

    # evita nomes só com siglas/quebras estranhas
    if sum(len(w) == 1 for w in words) >= max(2, len(words) // 2):
        return False

    return True


# =========================
# REGEX BASE
# =========================

CODE_RE = re.compile(r'\b[A-Z]{1,4}\d?(?:-[A-Z0-9]+)+\b')
PRICE_RE = re.compile(r'R\$\s*([\d]+(?:,\d+)?)')
QTY_RE = re.compile(r'(\d+)\s*PC\s*/?\s*CX', re.IGNORECASE)


def build_product(codigo, nome, preco, quantidade):
    nome = normalize_name(nome)

    if not codigo or not nome:
        return None

    # 🔥 detecta nome incompleto
    palavras = nome.split()

    if palavras and palavras[-1] in {"D", "PL", "F", "C", "X"}:
        return None  # descarta, provavelmente linha quebrada

    if len(palavras) < 3:
        return None

    return {
        "codigo": codigo,
        "nome": nome,
        "preco": preco if preco is not None else 0,
        "quantidade_caixa": quantidade
    }


# =========================
# MÉTODO A — leitura simples
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

                nome_parts = []
                quantidade = None

                for j in range(i + 1, min(i + 4, len(lines))):
                    current = lines[j]

                    if CODE_RE.search(current) and PRICE_RE.search(current):
                        break

                    qty_match = QTY_RE.search(current)
                    if qty_match:
                        quantidade = int(qty_match.group(1))
                    else:
                        nome_parts.append(current)

                nome = " ".join(nome_parts)
                p = build_product(codigo, nome, preco, quantidade)
                if p:
                    products.append(p)

    return products


# =========================
# MÉTODO B — texto linear
# =========================

def extract_method_text(doc):
    products = []

    for page in doc:
        text = page.get_text("text")
        chunks = [clean_text(c) for c in text.split("\n") if c.strip()]

        for i, line in enumerate(chunks):
            code_match = CODE_RE.search(line)
            price_match = PRICE_RE.search(line)

            if code_match and price_match:
                codigo = code_match.group(0)
                preco = float(price_match.group(1).replace(",", "."))

                nome_parts = []
                quantidade = None

                for j in range(i + 1, min(i + 5, len(chunks))):
                    nxt = chunks[j]

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
# MÉTODO C — leitura por blocos
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

        parsed_blocks.sort(key=lambda x: (round(x["y0"] / 10), x["x0"]))

        for blk in parsed_blocks:
            code_match = CODE_RE.search(blk["text"])
            price_match = PRICE_RE.search(blk["text"])

            if code_match and price_match:
                codigo = code_match.group(0)
                preco = float(price_match.group(1).replace(",", "."))

                nome_parts = []
                quantidade = None

                for other in parsed_blocks:
                    same_column = abs(other["x0"] - blk["x0"]) < 140
                    below = 0 < (other["y0"] - blk["y1"]) < 180

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
# MERGE INTELIGENTE
# =========================

def score_name(name: str) -> int:
    name = normalize_name(name)
    if not name:
        return -999

    score = 0
    score += min(len(name), 80)

    words = [w for w in name.split() if w]
    score += len(words) * 5

    if len(words) <= 1:
        score -= 20

    bad_tokens = {"X", "C", "D", "F", "H", "L", "M", "N", "R", "S", "A"}
    if any(w in bad_tokens for w in words):
        score -= 10

    if re.search(r"\b\d+\b", name):
        score -= 8

    bad_endings = {"DE", "PARA", "COM", "SEM", "E", "EM", "A", "O", "DA", "DO"}
    if words and words[-1] in bad_endings:
        score -= 15

    vowels = len(re.findall(r"[AEIOUÁÉÍÓÚÃÕÂÊÔ]", name))
    if vowels < max(2, len(name) // 10):
        score -= 8

    if not is_valid_name(name):
        score -= 50

    return score


def choose_best_name(names):
    cleaned = []

    for n in names:
        nn = normalize_name(n)
        if nn and is_valid_name(nn):
            cleaned.append(nn)

    if not cleaned:
        # fallback: se todos forem ruins, pega o menos ruim
        fallback = [normalize_name(n) for n in names if normalize_name(n)]
        if not fallback:
            return ""
        return max(list(dict.fromkeys(fallback)), key=score_name)

    unique = list(dict.fromkeys(cleaned))
    best = max(unique, key=score_name)
    return best


def choose_best_price(prices):
    valid = [p for p in prices if isinstance(p, (int, float)) and p > 0]
    if not valid:
        return 0
    return Counter(valid).most_common(1)[0][0]


def choose_best_quantity(qtys):
    valid = [q for q in qtys if isinstance(q, int) and q > 0]
    if not valid:
        return None
    return Counter(valid).most_common(1)[0][0]


def merge_produtos(*runs):
    agrupados = defaultdict(list)

    for run in runs:
        for item in run:
            codigo = item.get("codigo")
            if not codigo:
                continue
            agrupados[codigo].append(item)

    resultado = []

    for codigo, itens in agrupados.items():
        nomes = [i.get("nome", "") for i in itens]
        precos = [i.get("preco") for i in itens]
        quantidades = [i.get("quantidade_caixa") for i in itens]

        nome_final = choose_best_name(nomes)
        preco_final = choose_best_price(precos)
        quantidade_final = choose_best_quantity(quantidades)

        # 🔴 FILTRO FORTE (NOVO)
        if not nome_final:
            continue

        if len(nome_final) < 12:
            continue

        palavras = nome_final.split()

        if len(palavras) < 3:
            continue

        # remove nomes tipo "X", "E", etc
        if all(len(p) <= 2 for p in palavras):
            continue

        # remove nomes com muita sujeira
        if sum(len(p) == 1 for p in palavras) >= 2:
            continue

        resultado.append({
            "codigo": codigo,
            "nome": nome_final,
            "preco": preco_final,
            "quantidade_caixa": quantidade_final,
        })

    resultado.sort(key=lambda x: x["codigo"])
    return resultado


# =========================
# FUNÇÃO PRINCIPAL
# =========================

def parse_catalog_pdf(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_a = extract_method_a(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_b = extract_method_text(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result_c = extract_method_blocks(doc)
    doc.close()

    final = merge_produtos(result_a, result_b, result_c)
    return final
