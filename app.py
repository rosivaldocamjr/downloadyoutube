import logging
from pathlib import Path
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, send_from_directory, g)
import downloader

app = Flask(__name__)
# Para produção, use uma chave secreta real e carregue-a de uma variável de ambiente
app.secret_key = "uma-chave-secreta-muito-melhor-do-que-a-padrao"

# Configura a pasta de saída para os downloads
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Configuração básica de logging para depuração
logging.basicConfig(level=logging.INFO)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        qualidade = request.form.get("qualidade", "best")

        if not url:
            flash("Por favor, insira uma URL válida.")
            return redirect(url_for("index"))

        try:
            # Chama a função de download
            # Nota: Isso ainda é uma operação bloqueante.
            # Para uma aplicação real, use uma fila de tarefas (Celery, RQ).
            logging.info(f"Iniciando download para URL: {url} com qualidade {qualidade}")
            downloaded_file = downloader.download_single(
                url=url,
                outdir=DOWNLOAD_DIR,
                qualidade=qualidade,
            )

            if downloaded_file:
                flash("✅ Download concluído com sucesso!")
                # Armazena o nome do arquivo para ser usado no template
                g.filename = downloaded_file.name
            else:
                flash("❌ Ocorreu um erro e o download não foi concluído.")

        except Exception as e:
            logging.error(f"Erro ao baixar URL {url}: {e}", exc_info=True)
            flash(f"❌ Erro ao baixar: {str(e)}")

        # Renderiza a mesma página, agora com o link de download (se houver)
        return render_template("index.html", filename=getattr(g, 'filename', None))

    return render_template("index.html", filename=None)

@app.route("/downloads/<path:filename>")
def download_file(filename):
    """Rota para servir os arquivos baixados."""
    try:
        return send_from_directory(
            DOWNLOAD_DIR, filename, as_attachment=True
        )
    except FileNotFoundError:
        return "Arquivo não encontrado.", 404