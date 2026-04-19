from collections import defaultdict, Counter
import re


def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.upper().strip()
    name = re.sub(r"\s+", " ", name)

    # remove lixo comum
    name = re.sub(r"\bCX\b", "", name)
    name = re.sub(r"\bPC\/?CX\b", "", name)
    name = re.sub(r"\b\d+\s*PC\/?CX\b", "", name)
    name = re.sub(r"\b\d+\b$", "", name)
    name = re.sub(r"^[\W\d]+", "", name)
    name = re.sub(r"[\W]+$", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


def score_name(name: str) -> int:
    name = normalize_name(name)
    if not name:
        return -999

    score = 0

    # comprimento ajuda
    score += min(len(name), 80)

    # mais palavras costuma ser melhor
    words = [w for w in name.split() if w]
    score += len(words) * 5

    # penaliza nomes muito curtos
    if len(words) <= 1:
        score -= 20

    # penaliza lixo comum
    bad_tokens = {
        "X", "C", "D", "F", "H", "L", "M", "N", "R", "S", "A"
    }
    if any(w in bad_tokens for w in words):
        score -= 10

    # penaliza números soltos no nome
    if re.search(r"\b\d+\b", name):
        score -= 8

    # penaliza nome truncado terminando em palavras ruins
    bad_endings = {
        "DE", "PARA", "COM", "SEM", "E", "EM", "A", "O", "DA", "DO"
    }
    if words and words[-1] in bad_endings:
        score -= 15

    # penaliza poucas vogais, sinal de OCR ruim
    vowels = len(re.findall(r"[AEIOUÁÉÍÓÚÃÕÂÊÔ]", name))
    if vowels < max(2, len(name) // 10):
        score -= 8

    return score


def choose_best_name(names: list[str]) -> str:
    cleaned = []
    for n in names:
        nn = normalize_name(n)
        if nn:
            cleaned.append(nn)

    if not cleaned:
        return ""

    # remove duplicados preservando ordem
    unique = list(dict.fromkeys(cleaned))

    # escolhe pelo score
    best = max(unique, key=score_name)
    return best


def choose_best_price(prices: list):
    valid = [p for p in prices if isinstance(p, (int, float)) and p > 0]
    if not valid:
        return 0

    # prioriza valor mais frequente
    freq = Counter(valid).most_common(1)[0][0]
    return freq


def choose_best_quantity(qtys: list):
    valid = [q for q in qtys if isinstance(q, int) and q > 0]
    if not valid:
        return None

    freq = Counter(valid).most_common(1)[0][0]
    return freq


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

        if not nome_final:
            continue

        resultado.append({
            "codigo": codigo,
            "nome": nome_final,
            "preco": preco_final,
            "quantidade_caixa": quantidade_final,
        })

    resultado.sort(key=lambda x: x["codigo"])
    return resultado
