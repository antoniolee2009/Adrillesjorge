"""
Leads: candidatos a Deputado Estadual (Brasil, eleições 2026) que têm
Instagram declarado no TSE mas NÃO têm site próprio declarado.

Fonte oficial: Portal de Dados Abertos do TSE
https://dadosabertos.tse.jus.br/dataset/candidatos-2026

Como rodar:
    pip install pandas requests
    python leads_deputados_estaduais.py

Saída:
    leads_deputados_estaduais.csv  -> nome, partido, UF, cargo, instagram, todas_redes
"""

import io
import re
import zipfile
import unicodedata

import pandas as pd
import requests

ANO = 2026

URL_CANDIDATOS = f"https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ANO}.zip"
URL_REDES_SOCIAIS = f"https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/rede_social_candidato_{ANO}.zip"

# Domínios que consideramos "rede social" (não contam como site próprio)
DOMINIOS_REDE_SOCIAL = [
    "instagram.com", "facebook.com", "fb.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "tiktok.com", "linkedin.com", "kwai.com",
    "threads.net", "t.me", "telegram.me", "whatsapp.com", "wa.me",
]


def normalizar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.upper().strip()


def baixar_csv_do_zip(url: str) -> pd.DataFrame:
    print(f"Baixando: {url}")
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    # Pega o(s) .csv de dentro do zip (arquivos do TSE costumam vir em latin-1, separados por ';')
    csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    dfs = []
    for name in csv_names:
        with zf.open(name) as f:
            try:
                df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, low_memory=False)
            except Exception:
                f.seek(0)
                df = pd.read_csv(f, sep=";", encoding="utf-8", dtype=str, low_memory=False)
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]


def achar_coluna(df: pd.DataFrame, *pistas: str) -> str | None:
    """Acha a primeira coluna cujo nome contenha qualquer uma das pistas (case-insensitive)."""
    for col in df.columns:
        col_up = col.upper()
        if any(p.upper() in col_up for p in pistas):
            return col
    return None


def eh_link_de_site_proprio(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    url_low = url.lower()
    return not any(dominio in url_low for dominio in DOMINIOS_REDE_SOCIAL)


def main():
    df_cand = baixar_csv_do_zip(URL_CANDIDATOS)
    df_redes = baixar_csv_do_zip(URL_REDES_SOCIAIS)

    col_cargo = achar_coluna(df_cand, "DS_CARGO")
    col_sq = achar_coluna(df_cand, "SQ_CANDIDATO")
    col_nome = achar_coluna(df_cand, "NM_URNA_CANDIDATO", "NM_CANDIDATO")
    col_uf = achar_coluna(df_cand, "SG_UF")
    col_partido = achar_coluna(df_cand, "SG_PARTIDO")
    col_situacao = achar_coluna(df_cand, "DS_SITUACAO_CANDIDATURA", "DS_SIT_TOT_TURNO")

    col_sq_redes = achar_coluna(df_redes, "SQ_CANDIDATO")
    col_url = achar_coluna(df_redes, "DS_URL", "URL")

    faltando = [n for n, c in [
        ("cargo", col_cargo), ("sq_candidato (candidatos)", col_sq),
        ("nome", col_nome), ("uf", col_uf), ("partido", col_partido),
        ("sq_candidato (redes)", col_sq_redes), ("url", col_url),
    ] if c is None]
    if faltando:
        print("ATENÇÃO: não encontrei automaticamente estas colunas:", faltando)
        print("Colunas disponíveis em candidatos:", list(df_cand.columns))
        print("Colunas disponíveis em redes sociais:", list(df_redes.columns))
        return

    # Filtra só Deputado Estadual
    df_dep = df_cand[df_cand[col_cargo].apply(normalizar) == "DEPUTADO ESTADUAL"].copy()
    print(f"Candidatos a Deputado Estadual encontrados: {len(df_dep)}")

    # Agrupa redes sociais por candidato
    redes_por_sq = df_redes.groupby(col_sq_redes)[col_url].apply(list)

    linhas = []
    for _, row in df_dep.iterrows():
        sq = row[col_sq]
        urls = redes_por_sq.get(sq, [])
        tem_instagram = any("instagram.com" in str(u).lower() for u in urls)
        tem_site_proprio = any(eh_link_de_site_proprio(u) for u in urls)

        if tem_instagram and not tem_site_proprio:
            instagram_url = next(u for u in urls if "instagram.com" in str(u).lower())
            linhas.append({
                "nome_urna": row.get(col_nome),
                "partido": row.get(col_partido),
                "uf": row.get(col_uf),
                "situacao": row.get(col_situacao) if col_situacao else None,
                "instagram": instagram_url,
                "todas_redes": " | ".join(str(u) for u in urls),
            })

    df_leads = pd.DataFrame(linhas)
    df_leads.sort_values(["uf", "partido", "nome_urna"], inplace=True)
    df_leads.to_csv("leads_deputados_estaduais.csv", index=False, encoding="utf-8-sig")

    print(f"\nLeads encontrados: {len(df_leads)}")
    print("Salvo em leads_deputados_estaduais.csv")


if __name__ == "__main__":
    main()
