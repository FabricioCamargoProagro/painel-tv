# -*- coding: utf-8 -*-
"""
Propósito : rotina do painel da TV SEM o pacote no backend (provisória — quando o backend tiver a rota
            /tv/, a TV passa a usar a rota e esta rotina é desligada).
            1. entra no app de subscrição com uma conta (POST /auth/login, como a tela de login faz);
            2. lê o histórico de versões da planilha de Gestão de Propostas (GET /gestao-propostas/historico)
               e baixa a MAIS RECENTE (GET /gestao-propostas/historico/download/<arquivo>);
            3. gera os agregados com gerar_dados_tv.montar_dados (mesmas regras do Painel Comercial);
            4. confere que nenhum nome/CPF/e-mail da planilha foi parar no JSON (se foi, para);
            5. cifra o JSON (AES-256-GCM; chave derivada de TV_CHAVE por PBKDF2-SHA256) e grava o site
               estático: página + dados.enc.json + estado.json.
            Só LEITURA no backend: não dispara geração nem sincronização. O backend já consulta a matriz
            sozinho a cada 8 h, e as versões que a equipe gera à mão também entram.
Entradas  : variáveis de ambiente (segredos do GitHub):
              SUBSCRICAO_URL   endereço do backend do app (o mesmo que a tela de login usa)
              SUBSCRICAO_EMAIL e SUBSCRICAO_SENHA  conta que entra no app (de preferência só leitura)
              TV_CHAVE         frase-chave que cifra os dados (a mesma vai no endereço da TV, depois do #)
              TV_METAS         conteúdo de config/metas.json (as metas não ficam no repositório público)
            ou, para teste local: --xlsx <planilha> (pula o backend) e --metas <arquivo>.
Saídas    : <saida>/dados.enc.json (cifrado), <saida>/estado.json (sem dado de negócio) e, com
            --pagina <pasta>, a cópia da página (index.html, mapa_uf.js, logo_branca.png).
            No log só sai o que pode ser público (o repositório e os logs do GitHub são abertos).
Como rodar: python coletor_subscricao.py --saida site --pagina painel
            python coletor_subscricao.py --saida site --pagina painel --xlsx planilha.xlsx --metas metas.json
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerar_dados_tv as g  # noqa: E402

BR = dt.timezone(dt.timedelta(hours=-3))
ITERACOES = 200_000
PAGINA = ("index.html", "mapa_uf.js", "logo_branca.png", "tema.js", "tema_natal.js")
CABECALHOS = {"ngrok-skip-browser-warning": "true", "User-Agent": "painel-tv/1 (rotina do painel do escritorio)"}


class Falha(Exception):
    """Erro com mensagem que pode ir para o log público (sem segredo nem dado)."""


def _env(nome: str) -> str:
    v = os.environ.get(nome, "").strip()
    if not v:
        raise Falha(f"falta o segredo {nome}")
    return v


def entrar(url: str, email: str, senha: str) -> str:
    r = requests.post(f"{url}/auth/login", json={"email": email, "password": senha}, headers=CABECALHOS, timeout=60)
    if r.status_code in (400, 401, 403):
        raise Falha(f"login recusado pelo app (HTTP {r.status_code}) — conferir SUBSCRICAO_EMAIL/SUBSCRICAO_SENHA")
    if not r.ok:
        raise Falha(f"login falhou (HTTP {r.status_code})")
    token = (r.json() or {}).get("token")
    if not token:
        raise Falha("login sem token na resposta")
    return token


def versoes_recentes(url: str, token: str, n: int = 3) -> list[dict]:
    """As n versões mais recentes do histórico, da mais nova para a mais antiga (pela data_geracao)."""
    r = requests.get(f"{url}/gestao-propostas/historico", headers={**CABECALHOS, "Authorization": f"Bearer {token}"}, timeout=60)
    if not r.ok:
        raise Falha(f"histórico da gestão de propostas falhou (HTTP {r.status_code})")
    itens = [i for i in (r.json() or {}).get("itens", []) if i.get("arquivo") and i.get("data_geracao")]
    if not itens:
        raise Falha("o histórico não tem nenhuma versão da planilha")
    return sorted(itens, key=lambda i: g._iso_brasilia(i["data_geracao"]), reverse=True)[:n]


ESSENCIAIS = ("Situação", "fechaSuscripcionProposta", "Prêmio total (R$)", "UF", "Cultura")


def planilha_utilizavel(caminho: Path, quando: str | None):
    """Lê e valida; devolve (df, diag) ou None se a versão não tem o formato esperado."""
    try:
        df, diag = g.ler_planilha(caminho, quando=quando)
    except Exception:  # noqa: BLE001 — arquivo que não abre como a planilha de propostas
        return None
    if len(df) == 0 or any(c in diag.get("colunas_faltando", []) for c in ESSENCIAIS):
        return None
    return df, diag


def baixar(url: str, token: str, arquivo: str, destino: Path) -> None:
    alvo = f"{url}/gestao-propostas/historico/download/{urllib.parse.quote(arquivo, safe='')}"
    with requests.get(alvo, headers={**CABECALHOS, "Authorization": f"Bearer {token}"}, timeout=180, stream=True) as r:
        if not r.ok:
            raise Falha(f"download da planilha falhou (HTTP {r.status_code})")
        with open(destino, "wb") as f:
            for bloco in r.iter_content(1 << 16):
                f.write(bloco)


def cifrar(dados: dict, chave: str) -> dict:
    sal, iv = os.urandom(16), os.urandom(12)
    k = hashlib.pbkdf2_hmac("sha256", chave.encode("utf-8"), sal, ITERACOES, dklen=32)
    ct = AESGCM(k).encrypt(iv, json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode("ascii")  # noqa: E731
    return {"v": 1, "kdf": "pbkdf2-sha256", "it": ITERACOES, "salt": b(sal), "iv": b(iv), "ct": b(ct)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Rotina do painel da TV (sem o backend)")
    ap.add_argument("--saida", required=True, help="pasta do site estático")
    ap.add_argument("--pagina", default=None, help="pasta com index.html, mapa_uf.js e logo_branca.png")
    ap.add_argument("--xlsx", default=None, help="teste local: usa esta planilha em vez do backend")
    ap.add_argument("--metas", default=None, help="teste local: arquivo de metas (senão usa TV_METAS)")
    a = ap.parse_args()
    saida = Path(a.saida); saida.mkdir(parents=True, exist_ok=True)
    estado = {"executado_em": dt.datetime.now(BR).isoformat(timespec="seconds"), "ok": False}
    tmpdir = Path(tempfile.mkdtemp(prefix="painel_tv_"))
    if a.pagina:                                   # a página vai sempre — mesmo que a coleta falhe
        h = hashlib.sha1()
        for nome in PAGINA:
            arq = Path(a.pagina) / nome
            if arq.exists():
                h.update(arq.read_bytes())
                shutil.copy2(arq, saida / nome)
        estado["pagina"] = h.hexdigest()[:12]      # a TV compara e recarrega sozinha quando a página muda
    try:
        chave = _env("TV_CHAVE")
        if len(chave) < 16:
            raise Falha("TV_CHAVE curta demais (mínimo 16 caracteres)")
        metas = json.loads(Path(a.metas).read_text(encoding="utf-8")) if a.metas else json.loads(_env("TV_METAS"))

        if a.xlsx:
            planilha, tipo = Path(a.xlsx), "arquivo local"
            lido = planilha_utilizavel(planilha, None)
            if not lido:
                raise Falha("a planilha local não tem o formato da gestão de propostas")
        else:
            url = _env("SUBSCRICAO_URL").rstrip("/")
            token = entrar(url, _env("SUBSCRICAO_EMAIL"), _env("SUBSCRICAO_SENHA"))
            lido = None
            for n, versao in enumerate(versoes_recentes(url, token)):   # a mais nova; se vier ruim, a anterior
                planilha = tmpdir / f"gestao_propostas_{n}.xlsx"
                try:
                    baixar(url, token, versao["arquivo"], planilha)
                except Falha:
                    continue
                lido = planilha_utilizavel(planilha, versao["data_geracao"])
                if lido:
                    tipo = versao.get("tipo", "") + (f" (a {n + 1}ª mais recente)" if n else "")
                    break
            if not lido:
                raise Falha("nenhuma das 3 versões mais recentes do histórico tem o formato esperado")

        df, diag = lido
        dados = g.montar_dados(df, metas, diag=diag)
        dados["fonte"]["versao_tipo"] = tipo
        if g.conferir_privacidade(dados, g.valores_sensiveis(planilha)):
            raise Falha("conferência de privacidade barrou a publicação (dado pessoal no JSON)")

        pacote = cifrar(dados, chave)
        (saida / "dados.enc.json").write_text(json.dumps(pacote, separators=(",", ":")), encoding="utf-8")
        estado.update(ok=True, planilha_de=dados["fonte"].get("arquivo_modificado_em"), tipo_da_versao=tipo)
        print(f"ok · planilha de {estado['planilha_de']} ({tipo}) · dados.enc.json {len(json.dumps(pacote)) / 1024:.0f} KB")
        return 0
    except Falha as e:
        estado["erro"] = str(e)
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — nunca imprime o conteúdo, só o tipo do erro
        estado["erro"] = f"erro inesperado ({type(e).__name__})"
        print(f"ERRO: erro inesperado ({type(e).__name__})", file=sys.stderr)
        return 1
    finally:
        (saida / "estado.json").write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
        shutil.rmtree(tmpdir, ignore_errors=True)   # a planilha (com dado pessoal) nunca sai do runner


if __name__ == "__main__":
    sys.exit(main())
