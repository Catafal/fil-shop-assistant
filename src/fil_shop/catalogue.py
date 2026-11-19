"""Original synthetic Fil catalogue. Measurements describe garments, not body sizing."""

PRODUCTS = [
    {"id": "fil-01", "name": "Camisa Brisa", "description": "Camisa lleugera de lli i cotó.",
     "category": "shirt", "occasion_tags": ["wedding", "casual"],
     "style_tags": ["relaxed", "lightweight"], "price_cents": 5900,
     "fit_notes": "Tall recte. Compara el contorn de pit de la peça amb una camisa que et vagi bé.",
     "colours": ["ivory", "navy"], "chest": 108, "length": 72},
    {"id": "fil-02", "name": "Camisa Riu", "description": "Camisa de lli amb coll obert.",
     "category": "shirt", "occasion_tags": ["wedding", "casual"],
     "style_tags": ["relaxed", "linen"], "price_cents": 6900,
     "fit_notes": "Tall ample i espatlla relaxada; la talla habitual és només un punt de partida.",
     "colours": ["sage", "ivory"], "chest": 114, "length": 73},
    {"id": "fil-03", "name": "Camisa Nit", "description": "Camisa de popelín de cotó.",
     "category": "shirt", "occasion_tags": ["wedding", "dinner"],
     "style_tags": ["tailored", "minimal"], "price_cents": 7900,
     "fit_notes": "Tall entallat. Si prefereixes folgança, contrasta la mida de pit de la peça.",
     "colours": ["black", "navy"], "chest": 104, "length": 72},
    {"id": "fil-04", "name": "Top Alba", "description": "Top fluid de viscosa amb màniga curta.",
     "category": "top", "occasion_tags": ["wedding", "dinner"],
     "style_tags": ["fluid", "lightweight"], "price_cents": 4900,
     "fit_notes": "Caiguda fluida, sense ajustar la cintura. Consulta llargada i contorn de pit.",
     "colours": ["ivory", "terracotta"], "chest": 102, "length": 62},
    {"id": "fil-05", "name": "Top Ona", "description": "Top recte de lyocell amb coll rodó.",
     "category": "top", "occasion_tags": ["wedding", "casual"],
     "style_tags": ["minimal", "soft"], "price_cents": 5500,
     "fit_notes": "Tall recte; compara les mides de la peça amb un top propi, sense assumir ajust.",
     "colours": ["sage", "black"], "chest": 100, "length": 64},
    {"id": "fil-06", "name": "Jaqueta Mar", "description": "Jaqueta de lli sense estructura rígida.",
     "category": "jacket", "occasion_tags": ["wedding", "dinner"],
     "style_tags": ["unstructured", "lightweight"], "price_cents": 10900,
     "fit_notes": "Tall relaxat per portar sobre una camisa; comprova l'espai de pit amb la capa inferior.",
     "colours": ["navy", "ivory"], "chest": 116, "length": 71},
    {"id": "fil-07", "name": "Jaqueta Terra", "description": "Jaqueta lleugera de cotó amb butxaques.",
     "category": "jacket", "occasion_tags": ["wedding", "casual"],
     "style_tags": ["relaxed", "textured"], "price_cents": 11900,
     "fit_notes": "Tall recte; la llargada és de la peça, no una recomanació basada en l'alçada.",
     "colours": ["terracotta", "sage"], "chest": 112, "length": 70},
    {"id": "fil-08", "name": "Jaqueta Núvol", "description": "Jaqueta curta de cotó suau.",
     "category": "jacket", "occasion_tags": ["wedding", "dinner"],
     "style_tags": ["cropped", "soft"], "price_cents": 9900,
     "fit_notes": "Tall curt i ample; consulta la llargada abans de triar la talla.",
     "colours": ["ivory", "navy"], "chest": 110, "length": 60},
]


def product_records():
    for source in PRODUCTS:
        product = {k: v for k, v in source.items() if k not in ("colours", "chest", "length")}
        product["image_path"] = f"/products/{source['id']}.svg"
        product["garment_measurements"] = {
            size: {"chest_cm": source["chest"] + delta, "length_cm": source["length"] + delta // 4}
            for size, delta in [("S", -4), ("M", 0), ("L", 4)]
        }
        variants = []
        for size in ("S", "M", "L"):
            for colour in source["colours"]:
                sku = f"{source['id'].replace('-', '').upper()}-{size}-{colour.upper()}"
                # One explicitly unavailable service fixture enables native fault evidence.
                available = sku != "FIL08-M-IVORY"
                stock = 1 if sku == "FIL01-M-NAVY" else 3
                if sku == "FIL03-L-BLACK":
                    stock = 0
                variants.append((sku, source["id"], size, colour, stock, int(available)))
        yield product, variants
