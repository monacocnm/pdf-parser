import fitz
import re
from collections import defaultdict, Counter


CODE_RE = re.compile(r"\b[A-Z]{1,4}\d?(?:-[A-Z0-9]+)+\b")
PRICE_RE = re.compile(r"R\$\s*([0-9]+(?:[.,][0-9]{1,2})?)", re.IGNORECASE)
QTY_RE = re.compile(r"([0-9]{1,5})\s*PC\s*/?\s*CX", re.IGNORECASE)

BAD_ENDINGS = {"D", "E", "F", "PL", "COM", "DE", "PARA", "SEM", "A", "O", "DA", "DO"}
BAD_WORDS = {"DE", "PARA", "COM", "SEM", "E", "EM", "A", "O", "DA", "DO"}


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_name(name: str) -> str:
    name = clean_text(name)

    name = re.sub(r"R\$\s*[0-9]+(?:[.,][0-9]{1,2})?", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[0-9]{1,5}\s*PC\s*/?\s*CX", "", name, flags=re.IGNORECASE)
    name = CODE_RE.sub("", name)

    name = re.sub(r"^[^A-Z0-9]+", "", name)
    name = re.sub(r"[^A-Z0-9]+$", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


def parse_price(text: str):
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def parse_qty(text: str):
    if not text:
        return None
    m = QTY_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def is_valid_name(name: str) -> bool:
    if not name:
        return False

    words = [w for w in name.split() if w]

    if len(words) < 2:
        return False

    if len(name) < 10:
        return False

    if all(w in BAD_WORDS for w in words):
        return False

    if words[-1] in BAD_ENDINGS:
        return False

    if sum(len(w) == 1 for w in words) >= 2:
        return False

    return True


def score_name(name: str) -> int:
    name = normalize_name(name)
    if not name:
        return -999

    words = name.split()
    score = len(name) + len(words) * 5

    if len(words) <= 1:
        score -= 20

    if words and words[-1] in BAD_ENDINGS:
        score -= 20

    if re.search(r"\b[0-9]+\b", name):
        score -= 5

    return score


def choose_best_name(names):
    cleaned = []

    for n in names:
        nn = normalize_name(n)
        if nn and is_valid_name(nn):
            cleaned.append(nn)

    if not cleaned:
        fallback = [normalize_name(n) for n in names if normalize_name(n)]
        if not fallback:
            return ""
        unique = list(dict.fromkeys(fallback))
        return max(unique, key=score_name)

    unique = list(dict.fromkeys(cleaned))
    return max(unique, key=score_name)


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


def build_product(codigo, nome, preco=None, quantidade=None):
    if not codigo:
        return None

    nome = normalize_name(nome)

    if not is_valid_name(nome):
        return None

    return {
        "codigo": codigo,
        "nome": nome,
        "preco": preco if preco is not None else 0,
        "quantidade_caixa": quantidade
    }


def cut_mixed_product_name(nome: str) -> str:
    """
    Corta somente quando houver novo bloco de produto com CX,
    mas preserva PC/CX.
    Ex:
      'CX MINI PROJETOR CX LOCALIZADOR DE PEIXES' -> 'MINI PROJETOR'
      '70PC/CX MINI PROJETOR' -> mantém
    """
    if not nome:
        return ""

    nome = clean_text(nome)

    # divide por CX somente quando NÃO vier depois de PC/
    partes = re.split(r'(?<!PC/)\bCX\b', nome)
    partes_limpas = [p.strip(" -:;,.()") for p in partes if p.strip(" -:;,.()")]

    if len(partes_limpas) > 1:
        nome = partes_limpas[0]
    elif partes_limpas:
        nome = partes_limpas[0]
    else:
        nome = nome.strip()

    nome = re.sub(r'^\bCX\b\s*', '', nome).strip()
    return nome


def extract_method_text(doc):
    produtos = []

    for page in doc:
        lines = [clean_text(x) for x in page.get_text("text").splitlines() if clean_text(x)]

        for i, line in enumerate(lines):
            code_match = CODE_RE.search(line)
            if not code_match:
                continue

            codigo = code_match.group(0)
            preco = parse_price(line)
            quantidade = parse_qty(line)

            nome_parts = []

            for j in range(i, min(i + 6, len(lines))):
                current = lines[j]

                if j > i and CODE_RE.search(current):
                    break

                if j > i and ("R$" in current and "CX" in current):
                    break

                q = parse_qty(current)
                if q and not quantidade:
                    quantidade = q

                candidate = normalize_name(current)

                if not candidate:
                    continue

                if candidate == codigo:
                    continue

                if len(candidate) > 120:
                    continue

                if sum(c.isdigit() for c in candidate) > 8:
                    continue

                if len(candidate.split()) < 2:
                    continue

                nome_parts.append(candidate)

            nome = " ".join(dict.fromkeys(nome_parts))
            nome = cut_mixed_product_name(nome)

            p = build_product(codigo, nome, preco, quantidade)
            if p:
                produtos.append(p)

    return produtos


def extract_method_blocks(doc):
    produtos = []

    for page in doc:
        blocks = page.get_text("blocks")
        parsed = []

        for b in blocks:
            try:
                x0, y0, x1, y1, text = b[:5]
                txt = clean_text(text)
                if not txt:
                    continue
                parsed.append({
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "text": txt,
                })
            except Exception:
                continue

        parsed.sort(key=lambda x: (round(x["y0"] / 10), x["x0"]))

        for blk in parsed:
            code_match = CODE_RE.search(blk["text"])
            if not code_match:
                continue

            codigo = code_match.group(0)
            preco = parse_price(blk["text"])
            quantidade = parse_qty(blk["text"])

            nome_parts = []

            for other in parsed:
                same_column = abs(other["x0"] - blk["x0"]) < 140
                below = 0 <= (other["y0"] - blk["y0"]) < 180

                if not (same_column and below):
                    continue

                if other["text"] == blk["text"]:
                    candidate = normalize_name(other["text"])
                    if candidate:
                        nome_parts.append(candidate)
                    continue

                if CODE_RE.search(other["text"]) and parse_price(other["text"]) is not None:
                    continue

                q = parse_qty(other["text"])
                if q and not quantidade:
                    quantidade = q
                else:
                    candidate = normalize_name(other["text"])
                    if not candidate:
                        continue
                    if len(candidate) > 120:
                        continue
                    if candidate.count("CX") > 2:
                        continue
                    if len(candidate.split()) < 2:
                        continue
                    nome_parts.append(candidate)

            nome = " ".join(dict.fromkeys(nome_parts))
            nome = cut_mixed_product_name(nome)

            p = build_product(codigo, nome, preco, quantidade)
            if p:
                produtos.append(p)

    return produtos


def extract_method_words(doc):
    produtos = []

    for page in doc:
        text = clean_text(page.get_text("text"))

        for match in CODE_RE.finditer(text):
            codigo = match.group(0)
            start = match.start()
            snippet = text[start:start + 180]

            preco = parse_price(snippet)
            quantidade = parse_qty(snippet)

            nome = normalize_name(snippet)
            nome = cut_mixed_product_name(nome)

            p = build_product(codigo, nome, preco, quantidade)
            if p:
                produtos.append(p)

    return produtos


def merge_produtos(*runs):
    agrupados = defaultdict(list)

    for run in runs:
        for item in run:
            codigo = item.get("codigo")
            if codigo:
                agrupados[codigo].append(item)

    resultado = []

    for codigo, itens in agrupados.items():
        nomes = [cut_mixed_product_name(i.get("nome", "")) for i in itens]
        precos = [i.get("preco") for i in itens]
        quantidades = [i.get("quantidade_caixa") for i in itens]

        nome_final = choose_best_name(nomes)
        preco_final = choose_best_price(precos)
        quantidade_final = choose_best_quantity(quantidades)

        if not is_valid_name(nome_final):
            continue

        palavras = nome_final.split()
        if len(palavras) < 2 or len(nome_final) < 10:
            continue

        resultado.append({
            "codigo": codigo,
            "nome": nome_final,
            "preco": preco_final,
            "quantidade_caixa": quantidade_final,
        })

    resultado.sort(key=lambda x: x["codigo"])
    return resultado


def parse_catalog_pdf(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    r1 = extract_method_words(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    r2 = extract_method_text(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    r3 = extract_method_blocks(doc)
    doc.close()

    return merge_produtos(r1, r2, r3)
