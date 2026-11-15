"""Monitor de lançamentos de séries e filmes.

Séries: TVMaze (estreias de temporada em streaming).
Filmes: Ingresso.com (em breve no Brasil + sessões no Shopping Palladium, Curitiba).

Uso:  python server.py [--no-browser]
"""
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("PORT") or 8791)
JANELA_DIAS = 30
ATUALIZAR_A_CADA_HORAS = 12

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "db.json"
SITE = BASE / "docs"  # mesma pasta que o GitHub Pages publica
INDEX_PATH = SITE / "index.html"

ING = "https://api-content.ingresso.com/v0"
CIDADE_CURITIBA = 18
CINEMAS_PALLADIUM = {"767": "UCI Palladium", "795": "IMAX Palladium"}

# Plataformas de streaming consideradas (nome no TVMaze -> nome exibido).
PLATAFORMAS = {
    "Netflix": "Netflix",
    "Prime Video": "Prime Video",
    "Disney+": "Disney+",
    "Hulu": "Disney+ (original Hulu)",
    "HBO Max": "HBO Max",
    "Max": "HBO Max",
    "Apple TV+": "Apple TV+",
    "Apple TV": "Apple TV+",
    "Paramount+": "Paramount+",
    "Globoplay": "Globoplay",
    "Crunchyroll": "Crunchyroll",
    "MUBI": "MUBI",
}

GENEROS_PT = {
    "Action": "Ação", "Adult": "Adulto", "Adventure": "Aventura", "Anime": "Anime",
    "Children": "Infantil", "Comedy": "Comédia", "Crime": "Crime", "DIY": "Faça você mesmo",
    "Drama": "Drama", "Espionage": "Espionagem", "Family": "Família", "Fantasy": "Fantasia",
    "Food": "Culinária", "History": "História", "Horror": "Terror", "Legal": "Jurídico",
    "Medical": "Médico", "Music": "Música", "Mystery": "Mistério", "Nature": "Natureza",
    "Romance": "Romance", "Science-Fiction": "Ficção científica", "Sports": "Esportes",
    "Supernatural": "Sobrenatural", "Thriller": "Suspense", "Travel": "Viagem",
    "War": "Guerra", "Western": "Faroeste",
}
TIPOS_PT = {
    "Scripted": "Série", "Animation": "Animação", "Reality": "Reality", "Documentary": "Documentário",
    "Talk Show": "Talk show", "Game Show": "Game show", "Variety": "Variedades",
}

lock = threading.Lock()
estado = {"atualizando": False, "erro": None}


def carregar_db():
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    return {"atualizadoEm": None, "series": {}, "filmes": {}, "assistidos": {}}


def salvar_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DB_PATH)


db = carregar_db()


hosts_via_curl = set()


def baixar_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-lancamentos/1.0", "Accept": "application/json"})
    host = url.split("/")[2]
    try:
        if host in hosts_via_curl:
            raise urllib.error.URLError(ssl.SSLError())
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        if not isinstance(e.reason, ssl.SSLError):
            raise
        hosts_via_curl.add(host)
        # O Python nesta máquina rejeita a cadeia de certificados de alguns sites;
        # o curl do Windows valida o certificado pelo repositório do sistema.
        saida = subprocess.run(["curl", "-sS", "-f", "-m", "40", "-A", "monitor-lancamentos/1.0", url],
                               capture_output=True, check=True).stdout
        return json.loads(saida.decode("utf-8"))


def limpar_html(texto):
    return re.sub(r"<[^>]+>", "", texto or "").strip()


# ---------------------------------------------------------------- séries

def coletar_series(hoje):
    achadas = {}
    for i in range(JANELA_DIAS + 1):
        dia = (hoje + timedelta(days=i)).isoformat()
        try:
            episodios = baixar_json(f"https://api.tvmaze.com/schedule/web?date={dia}")
        except Exception as e:  # um dia com falha não derruba a coleta
            print(f"[series] falha em {dia}: {e}")
            continue
        for ep in episodios:
            if ep.get("number") != 1:
                continue  # só estreias de temporada
            show = (ep.get("_embedded") or {}).get("show") or {}
            canal = (show.get("webChannel") or {}).get("name")
            if canal not in PLATAFORMAS:
                continue
            chave = f"s{show['id']}-{ep.get('season')}"
            generos = [GENEROS_PT.get(g, g) for g in show.get("genres") or []]
            if not generos and show.get("type"):
                generos = [TIPOS_PT.get(show["type"], show["type"])]
            achadas[chave] = {
                "id": chave,
                "titulo": show.get("name"),
                "temporada": ep.get("season"),
                "data": dia,
                "generos": generos,
                "imagem": (show.get("image") or {}).get("medium"),
                "plataforma": PLATAFORMAS[canal],
                "idioma": show.get("language"),
                "sinopse": limpar_html(show.get("summary"))[:400],
                "url": show.get("officialSite") or show.get("url"),
            }
        time.sleep(0.4)  # limite do TVMaze: 20 chamadas / 10 s
    return achadas


# ---------------------------------------------------------------- filmes

def resumo_filme(ev):
    poster = None
    for img in ev.get("images") or []:
        if img.get("type") == "PosterPortrait":
            poster = img.get("url")
    estreia = ((ev.get("premiereDate") or {}).get("localDate") or "")[:10]
    return {
        "id": "f" + str(ev["id"]),
        "titulo": ev.get("title"),
        "tituloOriginal": ev.get("originalTitle"),
        "data": estreia or None,
        "generos": ev.get("genres") or [],
        "imagem": poster or ev.get("imageFeatured"),
        "classificacao": ev.get("contentRating"),
        "duracao": ev.get("duration"),
        "sinopse": (ev.get("synopsis") or "")[:400],
        "url": f"https://www.ingresso.com/filme/{ev.get('urlKey')}?city=curitiba",
        "sessoes": [],
    }


def coletar_sessoes_palladium():
    """Retorna {id_filme: {"evento": {...}, "sessoes": [...]}} para os cinemas do Palladium."""
    por_filme = {}
    for cid, nome in CINEMAS_PALLADIUM.items():
        try:
            dias = baixar_json(f"{ING}/sessions/city/{CIDADE_CURITIBA}/theater/{cid}?partnership=home")
        except Exception as e:
            print(f"[filmes] falha nas sessões de {nome}: {e}")
            continue
        for dia in dias:
            for mov in dia.get("movies") or []:
                reg = por_filme.setdefault("f" + str(mov["id"]), {"evento": mov, "sessoes": []})
                for sala in mov.get("rooms") or []:
                    for s in sala.get("sessions") or []:
                        reg["sessoes"].append({
                            "data": dia["date"],
                            "hora": s.get("time"),
                            "cinema": nome,
                            "sala": sala.get("name"),
                            "tipos": [t.get("alias") for t in s.get("types") or [] if t.get("alias")],
                            "preco": s.get("price"),
                            "url": s.get("siteURL"),
                        })
    for reg in por_filme.values():
        reg["sessoes"].sort(key=lambda s: (s["data"], s["hora"] or ""))
    return por_filme


def coletar_filmes(hoje, existentes):
    limite = (hoje + timedelta(days=JANELA_DIAS)).isoformat()
    achados = {}
    em_breve = baixar_json(f"{ING}/events/coming-soon/partnership/home").get("items", [])
    for ev in em_breve:
        f = resumo_filme(ev)
        if f["data"] and hoje.isoformat() <= f["data"] <= limite:
            achados[f["id"]] = f

    sessoes = coletar_sessoes_palladium()
    # Filmes já em cartaz no Palladium que ainda não conhecemos: busca a data de estreia.
    for fid, reg in sessoes.items():
        if fid in achados or fid in existentes:
            continue
        try:
            ev = baixar_json(f"{ING}/events/{fid[1:]}/partnership/home")
            f = resumo_filme(ev)
        except Exception:
            f = resumo_filme(reg["evento"])
        if not f["data"]:
            f["data"] = reg["sessoes"][0]["data"] if reg["sessoes"] else hoje.isoformat()
        if f["data"] < (hoje - timedelta(days=60)).isoformat():
            continue  # reexibições antigas não são lançamentos
        achados[fid] = f
    return achados, sessoes


# ---------------------------------------------------------------- atualização

def coletar_tudo(hoje, filmes_existentes):
    """Busca séries e filmes. Retorna (series, filmes, sessoes, erros); sessoes=None se os filmes falharam."""
    erros = []
    try:
        series = coletar_series(hoje)
    except Exception as e:
        series = {}
        erros.append(f"séries: {e}")
    try:
        filmes, sessoes = coletar_filmes(hoje, filmes_existentes)
    except Exception as e:
        filmes, sessoes = {}, None
        erros.append(f"filmes: {e}")
    return series, filmes, sessoes, erros


def aplicar(base, series, filmes, sessoes):
    """Junta o que foi coletado ao histórico já guardado."""
    base["series"].update(series)
    base["filmes"].update(filmes)
    if sessoes is not None:
        for fid, f in base["filmes"].items():
            f["sessoes"] = sessoes.get(fid, {}).get("sessoes", [])


def atualizar():
    with lock:
        if estado["atualizando"]:
            return
        estado["atualizando"] = True
        estado["erro"] = None
    try:
        series, filmes, sessoes, erros = coletar_tudo(date.today(), db["filmes"])
        with lock:
            aplicar(db, series, filmes, sessoes)
            db["atualizadoEm"] = datetime.now().isoformat(timespec="seconds")
            salvar_db(db)
            estado["erro"] = "; ".join(erros) or None
        print(f"[ok] {len(series)} séries e {len(filmes)} filmes coletados")
    except Exception as e:
        estado["erro"] = str(e)
        print(f"[erro] {e}")
    finally:
        estado["atualizando"] = False


def atualizar_se_antigo():
    ultimo = db.get("atualizadoEm")
    if not ultimo or datetime.now() - datetime.fromisoformat(ultimo) > timedelta(hours=ATUALIZAR_A_CADA_HORAS):
        threading.Thread(target=atualizar, daemon=True).start()


# ---------------------------------------------------------------- app no celular

def ip_da_rede():
    """IP deste computador na rede local (para abrir no celular pelo Wi-Fi)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # UDP: não envia nada, só escolhe a interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


ARQUIVOS_DO_SITE = {
    "/manifest.json": "application/manifest+json",
    "/sw.js": "text/javascript; charset=utf-8",
    "/avisos.js": "text/javascript; charset=utf-8",
    "/icon-192.png": "image/png",
    "/icon-512.png": "image/png",
    "/apple-touch-icon.png": "image/png",
}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def enviar(self, corpo, tipo="application/json; charset=utf-8", status=200):
        if not isinstance(corpo, bytes):
            corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho == "/":
            self.enviar(INDEX_PATH.read_bytes(), "text/html; charset=utf-8")
        elif caminho in ARQUIVOS_DO_SITE:
            self.enviar((SITE / caminho[1:]).read_bytes(), ARQUIVOS_DO_SITE[caminho])
        elif caminho == "/api/dados":
            atualizar_se_antigo()
            with lock:
                self.enviar({
                    "hoje": date.today().isoformat(),
                    "janelaDias": JANELA_DIAS,
                    "enderecoRede": f"http://{ip_da_rede()}:{PORT}",
                    "atualizadoEm": db.get("atualizadoEm"),
                    "atualizando": estado["atualizando"],
                    "erro": estado["erro"],
                    "series": list(db["series"].values()),
                    "filmes": list(db["filmes"].values()),
                    "assistidos": db["assistidos"],
                })
        else:
            self.enviar({"erro": "não encontrado"}, status=404)

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        except ValueError:
            corpo = {}
        if self.path == "/api/atualizar":
            threading.Thread(target=atualizar, daemon=True).start()
            self.enviar({"ok": True})
        elif self.path == "/api/assistido":
            item = str(corpo.get("id") or "")
            with lock:
                if item not in db["series"] and item not in db["filmes"]:
                    return self.enviar({"erro": "item desconhecido"}, status=400)
                if corpo.get("assistido"):
                    db["assistidos"][item] = date.today().isoformat()
                else:
                    db["assistidos"].pop(item, None)
                salvar_db(db)
                self.enviar({"ok": True, "assistidos": db["assistidos"]})
        else:
            self.enviar({"erro": "não encontrado"}, status=404)


if __name__ == "__main__":
    # 0.0.0.0: aceita conexões da rede local, para abrir no celular pelo Wi-Fi.
    servidor = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Monitor de lançamentos em {url}  (Ctrl+C para sair)")
    print(f"No celular (mesmo Wi-Fi): http://{ip_da_rede()}:{PORT}")
    atualizar_se_antigo()
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
