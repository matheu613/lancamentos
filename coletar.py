"""Coleta os lançamentos e grava docs/data/dados.json (usado pelo site no GitHub Pages).

Roda no GitHub Actions (.github/workflows/atualizar.yml); também funciona no PC:
    python coletar.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone

import server

SAIDA = server.SITE / "data" / "dados.json"
BRASILIA = timezone(timedelta(hours=-3))  # o GitHub roda em UTC


def main():
    if SAIDA.exists():
        base = json.loads(SAIDA.read_text(encoding="utf-8"))
    else:  # primeira vez: aproveita o histórico do programa do PC, se existir
        base = {"series": dict(server.db["series"]), "filmes": dict(server.db["filmes"])}

    agora = datetime.now(BRASILIA)
    series, filmes, sessoes, erros = server.coletar_tudo(agora.date(), base["filmes"])
    for erro in erros:
        print(f"[erro] {erro}")
    if len(erros) == 2:
        sys.exit("Nada foi coletado; dados.json mantido como estava.")

    server.aplicar(base, series, filmes, sessoes)
    base["atualizadoEm"] = agora.isoformat(timespec="seconds")
    base["janelaDias"] = server.JANELA_DIAS
    base["erro"] = "; ".join(erros) or None
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] {len(series)} séries e {len(filmes)} filmes coletados; "
          f"total guardado: {len(base['series'])} séries, {len(base['filmes'])} filmes")


if __name__ == "__main__":
    main()
