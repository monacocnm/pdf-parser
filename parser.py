import fitz
import re
from collections import defaultdict, Counter

CODE_RE = re.compile(r"\b[A-Z]{1,4}(?:-[A-Z0-9]+)+\b")
PRICE_RE = re.compile(r"R\$\s*([0-9]+(?:[.,][0-9]{1,2})?)", re.IGNORECASE)
QTY_RE = re.compile(r"([0-9]{1,5})\s*PC\s*/?\s*CX", re.IGNORECASE)

BAD_WORDS = {"DE", "PARA", "COM", "SEM", "E", "EM", "A", "O", "DA", "DO"}


def clean_text(text):
    return re.sub(r"\s+", " ", text.upper().strip())


def normalize_name(name):
    name = clean_text(name)

    name = PRICE_RE.sub("", name)
    name = QTY_RE.sub("", name)
    name = CODE_RE.sub("", name)

    # remove lixo no início (R$, números etc)
    name = re.sub(r"^[^A-Z]+", "", name)

    name = re.sub(r"\s+", " ", name).strip()
    return name


def parse_price(text):
    m = PRICE_RE.search(text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def parse_qty(text):
    m = QTY_RE.search(text)
    if not m:
        return None
    return int(m.group(1))


# 🔥 NOVA FUNÇÃO MELHORADA
def cut_mixed_product_name(nome):
    if not nome:
        return ""

    nome = clean_text(nome)

    # 1️⃣ corta quando aparece outro produto via palavras-chave
    triggers = [
        "SUPORTE", "CAMERA", "LUMINARIA", "PROJETOR", "BALANCA",
        "KIT", "MINI", "LANTERNA", "FONE", "GARRAFA", "CAIXA",
        "MOUSE", "TECLADO", "CANETA", "CABIDE", "BOLSA", "ROBO"
    ]

    words = nome.split()
    positions = [i for i, w in enumerate(words) if w in triggers]

    if len(positions) >= 2:
        nome = " ".join(words[:positions[1]])

    # 2️⃣ remove lixo tipo "(4", "(2"
    nome = re.sub(r"\([^\)]*", "", nome)

    # 3️⃣ remove excesso numérico no começo
    nome = re.sub(r"^[0-9\s,.\-]+", "", nome)

    return nome.strip()


def is_valid_name(nome):
    if not nome:
        return False

    words = nome.split()

    if len(words) < 2:
        return False

    if len(nome) < 8:
        return False

    if all(w in BAD_WORDS for w in words):
        return False

    if re.match(r"^[0-9\s]+$", nome):
        return False

    return True


def choose_best(lista):
    lista = [x for x in lista if x]
    if not lista:
        return ""

    return Counter(lista).most_common(1)[0][0]


def build_product(codigo, nome, preco, quantidade):
    nome = cut_mixed_product_name(normalize_name(nome))

    if not is_valid_name(nome):
        return None

    return {
        "codigo": codigo,
        "nome": nome,
        "preco": preco or 0,
        "quantidade_caixa": quantidade
    }


# 🔥 MÉTODO PRINCIPAL DE EXTRAÇÃO
def extract(doc):
    produtos = []

    for page in doc:
        lines = page.get_text("text").splitlines()
        lines = [clean_text(l) for l in lines if clean_text(l)]

        for i, line in enumerate(lines):
            code_match = CODE_RE.search(line)
            if not code_match:
                continue

            codigo = code_match.group(0)
            preco = parse_price(line)
            quantidade = parse_qty(line)

            nome_parts = []

            for j in range(i, min(i + 5, len(lines))):
                current = lines[j]

                if j > i and CODE_RE.search(current):
                    break

                q = parse_qty(current)
                if q and not quantidade:
                    quantidade = q

                candidate = normalize_name(current)

                if candidate and candidate != codigo:
                    nome_parts.append(candidate)

            nome = " ".join(dict.fromkeys(nome_parts))

            produto = build_product(codigo, nome, preco, quantidade)
            if produto:
                produtos.append(produto)

    return produtos


def merge_produtos(lista):
    agrupado = defaultdict(list)

    for item in lista:
        agrupado[item["codigo"]].append(item)

    resultado = []

    for codigo, itens in agrupado.items():
        nomes = [i["nome"] for i in itens]
        precos = [i["preco"] for i in itens]
        quantidades = [i["quantidade_caixa"] for i in itens]

        nome = choose_best(nomes)
        preco = choose_best(precos)
        quantidade = choose_best(quantidades)

        if not is_valid_name(nome):
            continue

        resultado.append({
            "codigo": codigo,
            "nome": nome,
            "preco": preco,
            "quantidade_caixa": quantidade
        })

    return sorted(resultado, key=lambda x: x["codigo"])


def parse_catalog_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    produtos = extract(doc)

    doc.close()

    return merge_produtos(produtos)
