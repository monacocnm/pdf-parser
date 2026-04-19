import fitz
import re
from collections import defaultdict


def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.upper()
    name = re.sub(r"\s+", " ", name)
    name = name.strip()

    return name


def score_name(name: str) -> int:
    return len(name)


def is_valid_name(name: str) -> bool:
    if not name:
        return False

    words = name.split()

    if len(words) < 3:
        return False

    if len(name) < 12:
        return False

    # palavras ruins
    bad_words = {"DE", "PARA", "COM", "SEM", "E", "EM", "A", "O"}

    if all(w in bad_words for w in words):
        return False

    # 🔥 nome truncado no final
    if words[-1] in {"D", "E", "F", "PL", "COM", "DE"}:
        return False

    return True


def choose_best_name(names):
    cleaned = []

    for n in names:
        nn = normalize_name(n)
        if nn and is_valid_name(nn):
            cleaned.append(nn)

    if not cleaned:
        return ""

    unique = list(dict.fromkeys(cleaned))
    return max(unique, key=score_name)


def choose_best_price(prices):
    prices = [p for p in prices if p]
    return prices[0] if prices else 0


def choose_best_quantity(qtys):
    qtys = [q for q in qtys if q]
    return qtys[0] if qtys else None


def extract_method_text(doc):
    produtos = []

    for page in doc:
        text = page.get_text()
        linhas = text.split("\n")

        for linha in linhas:
            match = re.search(r"([A-Z]-\d+(?:-\d+)*)", linha)

            if match:
                codigo = match.group(1)

                preco_match = re.search(r"(\d+[.,]?\d*)", linha)
                preco = float(preco_match.group(1)) if preco_match else None

                nome = linha.replace(codigo, "").strip()

                produtos.append({
                    "codigo": codigo,
                    "nome": nome,
                    "preco": preco,
                    "quantidade_caixa": None
                })

    return produtos


def extract_method_blocks(doc):
    produtos = []

    for page in doc:
        blocks = page.get_text("blocks")

        for b in blocks:
            texto = b[4]

            match = re.search(r"([A-Z]-\d+(?:-\d+)*)", texto)

            if match:
                codigo = match.group(1)

                preco_match = re.search(r"(\d+[.,]?\d*)", texto)
                preco = float(preco_match.group(1)) if preco_match else None

                nome = texto.replace(codigo, "").strip()

                produtos.append({
                    "codigo": codigo,
                    "nome": nome,
                    "preco": preco,
                    "quantidade_caixa": None
                })

    return produtos


def extract_method_a(doc):
    produtos = []

    for page in doc:
        words = page.get_text("words")

        for w in words:
            texto = w[4]

            match = re.match(r"([A-Z]-\d+(?:-\d+)*)", texto)

            if match:
                codigo = match.group(1)

                produtos.append({
                    "codigo": codigo,
                    "nome": texto,
                    "preco": None,
                    "quantidade_caixa": None
                })

    return produtos


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

        # 🔥 FILTRO FINAL
        if not nome_final:
            continue

        palavras = nome_final.split()

        if len(palavras) < 3:
            continue

        if len(nome_final) < 12:
            continue

        if all(len(p) <= 2 for p in palavras):
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
    r1 = extract_method_a(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    r2 = extract_method_text(doc)
    doc.close()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    r3 = extract_method_blocks(doc)
    doc.close()

    final = merge_produtos(r1, r2, r3)
    return final
