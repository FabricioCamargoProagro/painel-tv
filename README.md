# painel-tv

Painel da TV do escritório. A rotina `.github/workflows/painel-tv.yml` roda a cada 30 min
(7h–20h de Brasília, seg–sáb), lê a versão mais recente da planilha de propostas no sistema de
origem, gera só números agregados, **cifra** o resultado e publica no GitHub Pages.

- `coletor/rodar.py` — coleta, gera e cifra (AES-256-GCM, chave derivada da frase `TV_CHAVE`).
- `coletor/gerar_dados_tv.py` — regras do painel (as mesmas do painel comercial).
- `painel/` — a página que a TV abre; decifra no próprio navegador.
- `config/` — só dados públicos (contornos do IBGE e sedes municipais). As metas vêm do segredo `TV_METAS`.

Segredos (Settings → Secrets and variables → Actions): `SUBSCRICAO_URL`, `SUBSCRICAO_EMAIL`,
`SUBSCRICAO_SENHA`, `TV_CHAVE`, `TV_METAS`.

A TV abre `https://<usuário>.github.io/painel-tv/#k=<TV_CHAVE>` — o que vem depois do `#` não sai
da TV. Sem a frase, o arquivo publicado é ilegível.

Para desligar: Actions → painel-tv → ⋯ → Disable workflow.
