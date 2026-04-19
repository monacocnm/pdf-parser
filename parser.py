import fitz
import re

def extract_products(pdf_path):
    doc = fitz.open(pdf_path)
    products = []

    for page in doc:
        blocks = page.get_text("blocks")

        for b in blocks:
            text = b[4]

            if "CX R$" in text:
                lines = text.split("\n")

                codigo = None
                preco = None
                nome = ""
                qtd = None

                for line in lines:

                    match = re.search(r'([A-Z0-9\-]+).*R\$(\d+,\d+)', line)
                    if match:
                        codigo = match.group(1)
                        preco = float(match.group(2).replace(",", "."))

                    match_qtd = re.search(r'(\d+)PC/CX', line)
                    if match_qtd:
                        qtd = int(match_qtd.group(1))

                    if "R$" not in line and "PC/CX" not in line:
                        if len(line.strip()) > 5:
                            nome += " " + line.strip()

                if codigo and preco:
                    products.append({
                        "codigo": codigo,
                        "nome": nome.strip(),
                        "preco": preco,
                        "quantidade_caixa": qtd
                    })

    return products
