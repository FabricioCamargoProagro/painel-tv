# -*- coding: utf-8 -*-
"""
Propósito : gerar o `dados.json` do Painel da TV (operação + meta × realizado numa visão só) a
            partir da planilha de Gestão de Propostas — a mesma que o app de subscrição
            (subscricao-proagroseguros.vercel.app) extrai da API da matriz e sincroniza no OneDrive.
            O JSON leva SÓ agregados: nenhum nome de cliente, CPF/CNPJ, e-mail ou coordenada exata
            (o mapa usa a média das coordenadas por município, arredondada a 0,05°).

Regras (as do Painel Comercial semanal da casa):
  - realizado = só `Situação = Aprovada`; data = `fechaSuscripcionProposta`; 1 linha = 1 apólice;
  - período = ano-calendário da data de hoje (é o ano do BP), SEM a safra do ciclo anterior: a
    apólice de safra (A−1)/A subscrita em A fica fora do ano A (ex.: a 525, soja 2025/2026 de
    jan/2026). É o que o Painel Comercial faz — sem isso jan/2026 sai R$ 30.196 acima dele;
  - mapa: cada município na SEDE municipal (config/municipios_sedes.csv); a coordenada da lavoura
    só entra se o município não for achado (há apólices de GO com ponto caindo no PR);
  - rollover da meta: posição acumulada = Σ(realizado − meta base); saldo rolado = −posição do
    mês anterior; meta ajustada = base + saldo; Δ mês = realizado − base.

Entradas  : --xlsx   planilha gestao_propostas*.xlsx (aba "Propostas")
            --metas  config/metas.json (gerado por 2026-11-10_extrair_metas_painel_comercial.py)
            --hoje   AAAA-MM-DD (opcional; padrão = hoje em America/Sao_Paulo)
            --com-corretoras  inclui o ranking de corretoras (padrão: fora — ver BITACORA)
Saídas    : --saida  painel/dados.json
Como rodar: python -E -P -X utf8 scripts/gerar_dados_tv.py --xlsx "<gestao_propostas.xlsx>" \
                --metas config/metas.json --saida painel/dados.json
Importável: from gerar_dados_tv import ler_planilha, montar_dados  (o router do backend usa assim)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import shutil
import tempfile
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
# pasta de config: a do projeto, ou a indicada em TV_CONFIG_DIR (o pacote do backend usa a própria)
CONFIG = Path(os.environ.get("TV_CONFIG_DIR") or (RAIZ / "config"))
GEOJSON_UF = CONFIG / "br_uf.geojson"
SEDES_CSV = CONFIG / "municipios_sedes.csv"
MALHA_MUN = CONFIG / "municipios_malha.json"   # IBGE, inteiros delta em centésimos de grau
VERSAO = 2

UF_POR_NOME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}
UF_COD = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
# feriados nacionais (sem os pontos facultativos) — para os dias úteis que faltam no mês
FERIADOS = {
    "2026-01-01", "2026-04-03", "2026-04-21", "2026-05-01", "2026-09-07", "2026-10-12",
    "2026-11-02", "2026-11-15", "2026-11-20", "2026-12-25",
    "2027-01-01", "2027-03-26", "2027-04-21", "2027-05-01", "2027-09-07", "2027-10-12",
    "2027-11-02", "2027-11-15", "2027-11-20", "2027-12-25",
}
COLUNAS = {
    "ID Proposta": "id", "Safra": "safra", "Situação": "situacao", "Broker": "broker",
    "Cultura": "cultura", "Município": "municipio", "UF": "uf_nome",
    "Prêmio total (R$)": "premio", "Prêmio pago (R$)": "premio_pago", "I.S. (S.A.)": "is_",
    "Área": "area", "Subvenção Federal": "subv_fed", "Subvenção SP": "subv_est",
    "Longitude": "lon", "Latitude": "lat",
    "fechaSuscripcionProposta": "dt_sub", "fechaCreacion": "dt_criacao",
}
NUMERICAS = ("premio", "premio_pago", "is_", "area", "subv_fed", "subv_est", "lon", "lat")
# grafia da planilha → grafia do arquivo de sedes (o IBGE mudou alguns nomes)
ALIAS_MUNICIPIO = {("SP", "florinea"): "florinia"}


# ----------------------------------------------------------------------------- leitura
def _chave(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _num(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    s = serie.astype("string").str.strip().replace({"-": None, "": None})
    tem_virgula = s.str.contains(",", na=False)
    s = s.mask(tem_virgula, s.str.replace(".", "", regex=False)).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _cultura(nome) -> str:
    k = _chave(nome)
    if k.startswith("milho"):
        if "2" in k:
            return "Milho 2ª safra"
        if "1" in k:
            return "Milho 1ª safra"
        return "Milho"
    return str(nome).strip().capitalize() if nome is not None else "—"


def _carregar_ufs():
    if not GEOJSON_UF.exists():
        return []
    g = json.loads(GEOJSON_UF.read_text(encoding="utf-8"))
    ufs = []
    for f in g["features"]:
        geom = f["geometry"]
        pols = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        aneis = [p[0] for p in pols]
        xs = [x for a in aneis for x, _ in a]
        ys = [y for a in aneis for _, y in a]
        ufs.append((UF_COD[str(f["properties"]["codarea"])], aneis, (min(xs), min(ys), max(xs), max(ys))))
    return ufs


def _dentro(x, y, anel) -> bool:
    ok, j = False, len(anel) - 1
    for i in range(len(anel)):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            ok = not ok
        j = i
    return ok


def _uf_do_ponto(lon, lat, ufs) -> str | None:
    if lon is None or lat is None or not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    for uf, aneis, (x0, y0, x1, y1) in ufs:
        if x0 <= lon <= x1 and y0 <= lat <= y1 and any(_dentro(lon, lat, a) for a in aneis):
            return uf
    return None


def _no_brasil(lon, lat) -> bool:
    return -74.5 <= lon <= -34.0 and -34.5 <= lat <= 6.0


def _carregar_sedes() -> dict:
    """(UF, nome normalizado) -> (lon, lat, código IBGE) da sede municipal."""
    if not SEDES_CSV.exists():
        return {}
    s = pd.read_csv(SEDES_CSV, dtype={"codigo_uf": str, "codigo_ibge": str})
    return {(UF_COD.get(str(r.codigo_uf)), _chave(r.nome)): (float(r.longitude), float(r.latitude), str(r.codigo_ibge))
            for r in s.itertuples()}


def _carregar_malha() -> dict:
    """código IBGE -> contornos do município (como estão no arquivo: [poligono: [anel: [x0,y0,dx,dy,...]]])."""
    if not MALHA_MUN.exists():
        return {}
    return {str(c): p for c, p in json.loads(MALHA_MUN.read_text(encoding="utf-8"))}


def _iso_brasilia(texto: str) -> dt.datetime:
    """ISO → datetime em Brasília. Sem fuso, vale como hora de Brasília — é como a própria tela do
    app de subscrição mostra a `data_geracao` (new Date(iso) num navegador no Brasil)."""
    d = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    br = dt.timezone(dt.timedelta(hours=-3))
    return d.replace(tzinfo=br) if d.tzinfo is None else d.astimezone(br)


def _safra_inicio(s) -> float:
    try:
        return float(str(s).split("/")[0])
    except (ValueError, TypeError):
        return float("nan")


def ler_planilha(caminho: str | Path, aba: str = "Propostas", quando: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Lê a planilha de gestão de propostas e devolve (linhas normalizadas, diagnóstico).

    `quando` (ISO) substitui a hora do arquivo quando ela não diz nada — ex.: a rotina baixa a versão
    do histórico do backend, e a hora que conta é a `data_geracao` dela, não a do download."""
    caminho = Path(caminho)
    tmp = None
    try:
        bruto = pd.read_excel(caminho, sheet_name=aba)
    except PermissionError:                      # aberta no Excel / bloqueio do OneDrive
        tmp = Path(tempfile.gettempdir()) / f"_tv_{caminho.name}"
        shutil.copy2(caminho, tmp)
        bruto = pd.read_excel(tmp, sheet_name=aba)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()

    faltando = [c for c in COLUNAS if c not in bruto.columns]
    df = bruto.rename(columns=COLUNAS)
    for c in COLUNAS.values():
        if c not in df.columns:
            df[c] = None
    df = df[list(COLUNAS.values())].copy()
    df = df[df["id"].notna()]
    for c in NUMERICAS:
        df[c] = _num(df[c])
    for c in ("dt_sub", "dt_criacao"):
        df[c] = pd.to_datetime(df[c].astype("string").str.strip(), format="%d/%m/%Y", errors="coerce")
    df["situacao"] = df["situacao"].astype("string").str.strip()
    df["cultura"] = df["cultura"].map(_cultura)
    df["municipio"] = df["municipio"].astype("string").str.strip()
    df["broker"] = df["broker"].astype("string").str.strip()

    # coordenadas: corrige lat/lon trocadas e descarta o que cai fora do Brasil
    trocadas = descartadas = 0
    lon_ok, lat_ok = [], []
    for lon, lat in zip(df["lon"], df["lat"]):
        if pd.isna(lon) or pd.isna(lat):
            lon_ok.append(None); lat_ok.append(None); continue
        if _no_brasil(lon, lat):
            lon_ok.append(lon); lat_ok.append(lat)
        elif _no_brasil(lat, lon):
            lon_ok.append(lat); lat_ok.append(lon); trocadas += 1
        else:
            lon_ok.append(None); lat_ok.append(None); descartadas += 1
    df["lon"], df["lat"] = lon_ok, lat_ok

    # UF: pelo nome; se vier vazia, pelo ponto (ex.: proposta 462 vem sem UF)
    df["uf"] = df["uf_nome"].map(lambda n: UF_POR_NOME.get(_chave(n)) if _chave(n) else None)
    ufs = _carregar_ufs()
    sem_uf = df["uf"].isna()
    recuperadas = 0
    for i in df.index[sem_uf]:
        uf = _uf_do_ponto(df.at[i, "lon"], df.at[i, "lat"], ufs)
        if uf:
            df.at[i, "uf"] = uf
            recuperadas += 1
    # ponto que não cai na UF declarada não entra no mapa (fica na contagem normalmente)
    fora_da_uf = 0
    for i in df.index:
        lon, lat, uf = df.at[i, "lon"], df.at[i, "lat"], df.at[i, "uf"]
        if lon is not None and uf and ufs and _uf_do_ponto(lon, lat, ufs) not in (uf, None):
            df.at[i, "lon"] = df.at[i, "lat"] = None
            fora_da_uf += 1

    # hora em que a planilha foi gravada (no backend: a última vez que ele incorporou proposta nova);
    # é ESTA a idade que a TV mostra, não a hora do cálculo do JSON
    modificado = dt.datetime.fromtimestamp(caminho.stat().st_mtime, tz=dt.timezone(dt.timedelta(hours=-3)))
    if quando:
        modificado = _iso_brasilia(quando)
    diag = {
        "arquivo": caminho.name, "linhas": int(len(df)), "colunas_faltando": faltando,
        "arquivo_modificado_em": modificado.isoformat(timespec="seconds"),
        "coordenadas_trocadas": trocadas, "coordenadas_descartadas": descartadas,
        "coordenadas_fora_da_uf": fora_da_uf, "uf_pelas_coordenadas": recuperadas,
        "sem_uf": int(df["uf"].isna().sum()),
        "situacoes": {str(k): int(v) for k, v in df["situacao"].value_counts(dropna=False).items()},
        "ultima_subscricao": df["dt_sub"].max().strftime("%Y-%m-%d") if df["dt_sub"].notna().any() else None,
    }
    return df, diag


# ----------------------------------------------------------------------------- agregação
def _r(v, casas=2):
    v = float(v or 0)
    return round(v, casas) if math.isfinite(v) else 0.0


def _dias_uteis(ini: dt.date, fim: dt.date) -> int:
    n, d = 0, ini
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in FERIADOS:
            n += 1
        d += dt.timedelta(days=1)
    return n


def _fim_do_mes(d: dt.date) -> dt.date:
    prox = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return prox - dt.timedelta(days=1)


def _nome_corretora(n: str) -> str:
    n = " ".join(str(n or "").split())
    return n.title().replace(" De ", " de ").replace(" Da ", " da ").replace(" Do ", " do ").replace(" E ", " e ")


def montar_dados(df: pd.DataFrame, metas: dict, hoje: dt.date | None = None,
                 diag: dict | None = None, com_corretoras: bool = False) -> dict:
    """Agrega as propostas no formato que o painel da TV lê. Não leva dado pessoal."""
    hoje = hoje or dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    ano = hoje.year
    meta = metas.get(str(ano)) or {}
    base_m = [float(x) for x in meta.get("premio_mensal", [0] * 12)]
    tem_meta = bool(meta)

    aprov = df[df["situacao"].str.lower().eq("aprovada") & df["dt_sub"].notna()].copy()
    aprov["d"] = aprov["dt_sub"].dt.date
    ini = aprov["safra"].map(_safra_inicio)
    do_ciclo_anterior = (aprov["dt_sub"].dt.year == ano) & ini.notna() & (ini < ano)
    ano_df = aprov[(aprov["dt_sub"].dt.year == ano) & ~do_ciclo_anterior]
    fora_ciclo = aprov[do_ciclo_anterior]

    # --- KPIs do ano
    kpis = {
        "apolices": int(len(ano_df)),
        "premio": _r(ano_df["premio"].sum()),
        "premio_pago_produtor": _r(ano_df["premio_pago"].sum()),
        "subv_federal": _r(ano_df["subv_fed"].sum()),
        "subv_estadual": _r(ano_df["subv_est"].sum()),
        "area_ha": _r(ano_df["area"].sum(), 1),
        "is": _r(ano_df["is_"].sum()),
        "municipios": int(ano_df[["municipio", "uf"]].drop_duplicates().shape[0]),
        "produtores": None,   # contagem de CPF/CNPJ distintos não sai do gerador (dado pessoal)
    }
    kpis["taxa_media"] = _r(kpis["premio"] / kpis["is"] * 100, 2) if kpis["is"] else 0.0
    kpis["meta_premio_ano"] = _r(sum(base_m)) if tem_meta else None
    kpis["meta_apolices_ano"] = int(meta.get("apolices_ano", 0)) if tem_meta else None

    # --- ritmo: último dia com emissão, hoje, 7 dias
    def bloco(mask):
        s = aprov[mask]
        return {"apolices": int(len(s)), "premio": _r(s["premio"].sum())}
    ultimo_dia = aprov["d"].max() if len(aprov) else None
    ritmo = {
        "hoje": bloco(aprov["d"] == hoje),
        "ultimo_dia": (dict(bloco(aprov["d"] == ultimo_dia), data=ultimo_dia.isoformat()) if ultimo_dia else None),
        "ultimos_7_dias": bloco((aprov["d"] > hoje - dt.timedelta(days=7)) & (aprov["d"] <= hoje)),
    }
    sm = ano_df[ano_df["dt_sub"].dt.month == hoje.month]
    ritmo["mes_atual"] = {"apolices": int(len(sm)), "premio": _r(sm["premio"].sum())}
    # série diária dos últimos 30 dias (apólices e prêmio), para a faixa de "ritmo"
    serie = []
    for k in range(29, -1, -1):
        d = hoje - dt.timedelta(days=k)
        s = aprov[aprov["d"] == d]
        serie.append({"d": d.isoformat(), "n": int(len(s)), "p": _r(s["premio"].sum(), 0)})
    ritmo["diario_30d"] = serie

    # --- meses + rollover (mesma conta do Painel Comercial)
    cur = hoje.month - 1
    meses, saldo_fim, pos = [], 0.0, 0.0
    for m in range(12):
        sm = ano_df[ano_df["dt_sub"].dt.month == m + 1]
        real_p, real_n = float(sm["premio"].sum()), int(len(sm))
        fechado, corrente = m < cur, m == cur
        saldo_in = saldo_fim
        meta_aj = base_m[m] + saldo_in
        linha = {"m": m + 1, "status": "fechado" if fechado else ("corrente" if corrente else "futuro"),
                 "meta_base": _r(base_m[m]), "saldo_rolado": _r(saldo_in), "meta_ajustada": _r(meta_aj),
                 "real": _r(real_p), "apolices": real_n,
                 "meta_apolices": int(meta.get("apolices_mensal", [0] * 12)[m]) if tem_meta else None}
        if fechado:
            linha["delta"] = _r(real_p - base_m[m])
            saldo_fim = meta_aj - real_p
            pos += real_p - base_m[m]
            linha["posicao_acum"] = _r(pos)
        elif corrente:
            linha["delta"] = _r(real_p - base_m[m])
            linha["falta"] = _r(meta_aj - real_p)
            linha["posicao_acum"] = _r(pos + real_p - base_m[m])
        meses.append(linha)

    mc = meses[cur]
    fim_mes = _fim_do_mes(hoje)
    du_rest = _dias_uteis(hoje, fim_mes)
    du_passados = _dias_uteis(hoje.replace(day=1), hoje - dt.timedelta(days=1)) if hoje.day > 1 else 0
    real_acum = sum(x["real"] for x in meses[:cur + 1])
    meta_acum = sum(base_m[:cur + 1])
    meta_info = {
        "tem_meta": tem_meta, "fonte": meta.get("fonte"),
        "ano": ano, "mes_corrente": cur + 1,
        "meta_ano": _r(sum(base_m)), "realizado_ano": _r(real_acum),
        "pct_ano": _r(real_acum / sum(base_m) * 100, 1) if tem_meta and sum(base_m) else None,
        "falta_ano": _r(sum(base_m) - real_acum),
        "meta_acum_ate_mes": _r(meta_acum),
        "posicao_acum": mc.get("posicao_acum"),
        "mes": {"meta_base": mc["meta_base"], "saldo_rolado": mc["saldo_rolado"],
                "meta_ajustada": mc["meta_ajustada"], "real": mc["real"], "falta": mc.get("falta"),
                "dias_uteis_restantes": du_rest, "dias_uteis_passados": du_passados,
                "ritmo_necessario_dia": _r(max(mc.get("falta") or 0, 0) / du_rest) if du_rest else None,
                "ritmo_atual_dia": _r(mc["real"] / du_passados) if du_passados else None},
    }

    # --- por UF
    meta_uf = meta.get("premio_por_uf", {})
    is_tot = float(ano_df["is_"].sum()) or 1.0
    ufs = []
    for uf, s in ano_df.groupby(ano_df["uf"].fillna("—")):
        p = float(s["premio"].sum())
        mu = float(meta_uf.get(uf, 0) or 0)
        ufs.append({"uf": uf, "apolices": int(len(s)), "premio": _r(p), "is": _r(s["is_"].sum()),
                    "area_ha": _r(s["area"].sum(), 1), "pct_is": _r(s["is_"].sum() / is_tot * 100, 2),
                    "meta_ano": _r(mu) if mu else None, "pct_meta": _r(p / mu * 100, 1) if mu else None})
    for uf, mu in meta_uf.items():                         # UF com meta e sem venda ainda
        if mu and not any(x["uf"] == uf for x in ufs):
            ufs.append({"uf": uf, "apolices": 0, "premio": 0.0, "is": 0.0, "area_ha": 0.0, "pct_is": 0.0,
                        "meta_ano": _r(mu), "pct_meta": 0.0})
    ufs.sort(key=lambda x: -x["premio"])

    # --- por cultura
    meta_cult = meta.get("por_cultura", {})
    p_tot = float(ano_df["premio"].sum()) or 1.0
    culturas = []
    for c, s in ano_df.groupby("cultura"):
        p = float(s["premio"].sum())
        mc_ = float((meta_cult.get(c) or {}).get("premio", 0) or 0)
        culturas.append({"cultura": c, "apolices": int(len(s)), "premio": _r(p), "area_ha": _r(s["area"].sum(), 1),
                         "pct_premio": _r(p / p_tot * 100, 1), "meta_ano": _r(mc_) if mc_ else None,
                         "pct_meta": _r(p / mc_ * 100, 1) if mc_ else None})
    culturas.sort(key=lambda x: -x["premio"])

    # --- municípios (mapa): na sede municipal; sem sede achada, média das coordenadas (0,05°).
    #     "is" = exposição (importância segurada das apólices do ano); "malha" = contorno do IBGE
    #     para o mapa coroplético (público, não identifica lavoura).
    sedes = _carregar_sedes()
    malha = _carregar_malha()
    munis, sem_sede, sem_malha = [], [], []
    for (mun, uf), s in ano_df.groupby([ano_df["municipio"].fillna("—"), ano_df["uf"].fillna("—")]):
        item = {"municipio": str(mun), "uf": str(uf), "apolices": int(len(s)), "premio": _r(s["premio"].sum(), 0),
                "is": _r(s["is_"].sum(), 0), "area_ha": _r(s["area"].sum(), 0)}
        nome = _chave(mun)
        sede = sedes.get((str(uf), ALIAS_MUNICIPIO.get((str(uf), nome), nome)))
        if sede:
            item["lon"], item["lat"], item["cod"] = round(sede[0], 3), round(sede[1], 3), sede[2]
            if sede[2] in malha:
                item["malha"] = malha[sede[2]]
            else:
                sem_malha.append(f"{mun}/{uf}")
        else:
            pts = s.dropna(subset=["lon", "lat"])
            if len(pts):
                item["lon"] = round(round(float(pts["lon"].mean()) / 0.05) * 0.05, 2)
                item["lat"] = round(round(float(pts["lat"].mean()) / 0.05) * 0.05, 2)
            sem_sede.append(f"{mun}/{uf}")
        munis.append(item)
    munis.sort(key=lambda x: -x["premio"])
    if diag is not None:
        diag = dict(diag, municipios_sem_sede=sem_sede, municipios_sem_malha=sem_malha,
                    fora_do_ciclo={"apolices": int(len(fora_ciclo)), "premio": _r(fora_ciclo["premio"].sum())})

    # --- últimas emissões (sem cliente e sem corretora)
    ult = ano_df.sort_values(["dt_sub", "id"], ascending=[False, False]).head(10)
    ultimas = [{"data": r.dt_sub.strftime("%Y-%m-%d"), "municipio": str(r.municipio or "—"), "uf": str(r.uf or "—"),
                "cultura": r.cultura, "area_ha": _r(r.area, 1), "premio": _r(r.premio, 0)} for r in ult.itertuples()]

    # --- situação das propostas decididas no ano (funil)
    no_ano = df[df["dt_sub"].dt.year == ano]
    situacoes = {str(k): int(v) for k, v in no_ano["situacao"].value_counts().items()}

    dados = {
        "versao": VERSAO,
        "gerado_em": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds"),
        "hoje": hoje.isoformat(),
        "ano": ano,
        "criterio": "Situação = Aprovada · data = fechaSuscripcionProposta · 1 linha = 1 apólice",
        "fonte": {k: v for k, v in (diag or {}).items() if k in ("arquivo", "linhas", "ultima_subscricao", "arquivo_modificado_em")},
        "kpis": kpis, "ritmo": ritmo, "meta": meta_info, "meses": meses,
        "ufs": ufs, "culturas": culturas, "municipios": munis, "ultimas": ultimas,
        "situacoes_ano": situacoes,
        "qualidade": {k: v for k, v in (diag or {}).items() if k not in ("arquivo", "linhas", "ultima_subscricao", "arquivo_modificado_em")},
    }
    if com_corretoras:
        cor = (ano_df.groupby(ano_df["broker"].fillna("—"))
               .agg(apolices=("id", "count"), premio=("premio", "sum")).reset_index()
               .sort_values("premio", ascending=False).head(10))
        dados["corretoras"] = [{"nome": _nome_corretora(r.broker), "apolices": int(r.apolices), "premio": _r(r.premio, 0)}
                               for r in cor.itertuples()]
    return dados


def valores_sensiveis(caminho: str | Path, aba: str = "Propostas") -> set[str]:
    """Nomes de cliente, CPF/CNPJ e e-mails da planilha — só para a conferência de vazamento."""
    cols = ["Nome Do Cliente", "CPF/CNPJ", "Subscritor"]
    bruto = pd.read_excel(caminho, sheet_name=aba, dtype=str)
    vals = set()
    for c in cols:
        if c in bruto.columns:
            for v in bruto[c].dropna().astype(str):
                v = " ".join(v.split()).lower()
                if len(v) >= 6:
                    vals.add(v)
                    dig = "".join(ch for ch in v if ch.isdigit())
                    if len(dig) >= 11:              # CPF/CNPJ sem pontuação também conta
                        vals.add(dig)
    return vals


def conferir_privacidade(dados: dict, sensiveis: set[str]) -> list[str]:
    """Devolve os valores pessoais que apareceriam no JSON (lista vazia = pode gravar)."""
    texto = json.dumps(dados, ensure_ascii=False).lower()
    return sorted(v for v in sensiveis if v in texto)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera o dados.json do painel da TV")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--metas", default=str(CONFIG / "metas.json"))
    ap.add_argument("--saida", default=str(RAIZ / "painel" / "dados.json"))
    ap.add_argument("--hoje", default=None, help="AAAA-MM-DD (padrão: hoje em Brasília)")
    ap.add_argument("--com-corretoras", action="store_true")
    a = ap.parse_args()

    df, diag = ler_planilha(a.xlsx)
    metas = json.loads(Path(a.metas).read_text(encoding="utf-8"))
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else None
    dados = montar_dados(df, metas, hoje=hoje, diag=diag, com_corretoras=a.com_corretoras)

    vazou = conferir_privacidade(dados, valores_sensiveis(a.xlsx))
    if vazou:
        raise SystemExit(f"BLOQUEADO: {len(vazou)} nome(s)/documento(s)/e-mail(s) apareceriam no JSON")

    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    k, m = dados["kpis"], dados["meta"]
    print(f"{dados['ano']}: {k['apolices']} apólices · prêmio R$ {k['premio']:,.2f} · meta {m['pct_ano']}% "
          f"· {len(dados['municipios'])} municípios · {Path(a.saida).stat().st_size/1024:.1f} KB → {a.saida}")
    print("qualidade:", json.dumps(dados["qualidade"], ensure_ascii=False))


if __name__ == "__main__":
    main()
